/* Firebreak front end.
   No framework, no build step — it has to run off a folder on a laptop with
   no wifi at 08:00 Sunday.

   Two rules that everything else follows from:
   1. The frontend never decides whether a cascade happens. It renders frames.
   2. Animation shows causality or it doesn't exist. Breach, then sell, then
      the price falls. Never overlapped — overlapping them is what turns a
      mechanism into a screensaver. */

const NS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);

const DUR_FLOW = 700;
const DUR_BREACH = 140;
const SETTLE_HOLD = 180;

const state = {
  run: null,        // last /api/break payload
  boundary: null,   // last /api/boundary payload, kept so a reflow can redraw
  layout: null,     // rebuilt whenever the measured stage moves
  frame: 0,
  timers: [],
  beat: "idle",
};

/* ────────────────────────────── formatting ─────────────────────────────
   Every number is fixed-width and fixed-decimal. Digits must never reflow
   mid-animation — that single detail is the fastest way to look amateur. */

const pct1 = (x) => `${(x * 100).toFixed(1)}%`;
const pct2 = (x) => `${(x * 100).toFixed(2)}%`;
const mult = (x) => `${x.toFixed(2)}×`;

function el(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function params() {
  return new URLSearchParams({
    leverage: $("leverage").value,
    gamma: $("gamma").value,
    breaches: $("breaches").value,
  }).toString();
}

async function api(path) {
  const started = performance.now();
  const res = await fetch(path, { cache: "no-store" });
  const ms = Math.round(performance.now() - started);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  const body = await res.json();
  // a recorded answer must never pass for a live one
  if (body && body.cached) {
    setEngine("cached", body.fallback_reason ? "cached · engine failed" : "cached run");
  }
  return { body, ms };
}

function clearTimers() {
  state.timers.forEach(clearTimeout);
  state.timers = [];
}
const later = (fn, ms) => state.timers.push(setTimeout(fn, ms));

/* Only one animation may own the stage. The cascade and the split each keep
   their own queue, and neither used to stop when the other started — click
   Stabilise halfway through a cascade and the cascade kept advancing the
   round label, the timeline and the metrics band underneath the split view,
   so the strip at the bottom contradicted the scene above it for four
   seconds. Every action calls this before it takes the stage. */
function stopAnimations() {
  clearTimers();
  split.timers.forEach(clearTimeout);
  split.timers = [];
}

/* ─────────────────────────── deterministic layout ───────────────────────
   Not force-directed. Force layout jitters on every mount and is the
   clearest tell of a student project. Positions are sorted once and frozen,
   so it looks identical in rehearsal and on stage.

   Assets left, portfolios right: the shock enters at an asset and travels
   to portfolios, so causality runs left to right. */

function layoutIsStale(width, height) {
  const L = state.layout;
  return !L || Math.abs(L.width - width) > 8 || Math.abs(L.height - height) > 8;
}

function ensureLayout(run, svg) {
  const { width, height } = measure(svg);
  if (layoutIsStale(width, height)) state.layout = computeLayout(run, width, height);
  return state.layout;
}

function computeLayout(run, width, height) {
  const { assets, portfolios, holdings } = run.topology;

  const exposure = assets.map((_, i) => holdings.reduce((s, row) => s + row[i], 0));
  const gross = holdings.map((row) => row.reduce((a, b) => a + b, 0));
  const maxExp = Math.max(...exposure);
  const maxGross = Math.max(...gross);

  const assetOrder = assets.map((_, i) => i).sort((a, b) => exposure[b] - exposure[a]);
  const fundOrder = portfolios.map((_, j) => j).sort((a, b) => gross[b] - gross[a]);

  const padY = 34;
  const slotA = (height - 2 * padY) / assets.length;
  const slotF = (height - 2 * padY) / portfolios.length;

  // Dividing by the max compresses ten similarly-sized megacaps into ten
  // identical dots — the size channel does nothing. Normalise across the
  // observed range so the actual spread is what you see.
  const minExp = Math.min(...exposure), minGross = Math.min(...gross);
  const spanExp = Math.max(1e-9, maxExp - minExp);
  const spanGross = Math.max(1e-9, maxGross - minGross);

  const assetPos = [], fundPos = [];
  assetOrder.forEach((i, rank) => {
    assetPos[i] = {
      x: width * 0.24,
      y: padY + (rank + 0.5) * slotA,
      r: 5 + 11 * (exposure[i] - minExp) / spanExp,
    };
  });
  fundOrder.forEach((j, rank) => {
    fundPos[j] = {
      x: width * 0.76,
      y: padY + (rank + 0.5) * slotF,
      side: 13 + 15 * (gross[j] - minGross) / spanGross,
    };
  });

  const weights = holdings.map((row, j) => row.map((v) => (gross[j] > 0 ? v / gross[j] : 0)));
  const maxWeight = Math.max(1e-9, ...weights.flat());

  return { assetPos, fundPos, weights, maxWeight, width, height, gross };
}

/* ───────────────────────────── the network ───────────────────────────── */

/* getBoundingClientRect returns 0 before layout flushes, and a viewBox sized
   to a zero box renders the whole diagram at a fraction of scale in the
   corner. Measure the PARENT, which is a laid-out flex/grid child, and refuse
   any measurement that looks like a pre-layout zero. */
function measure(svg) {
  // Measure the CONTAINER, never the svg. An svg sizes itself from its own
  // viewBox when its height can't resolve, so measuring it just reads back
  // whatever we last wrote — the diagram locks to its first guess forever.
  const parent = svg.parentElement && svg.parentElement.getBoundingClientRect();
  if (parent && parent.width > 40 && parent.height > 40) {
    return { width: parent.width, height: parent.height };
  }
  const stage = $("stage").getBoundingClientRect();
  return { width: Math.max(420, stage.width || 900), height: Math.max(280, stage.height || 520) };
}

function drawNetwork(svg, run, frameIndex, opts = {}) {
  const { showBreachAt = null, flows = null, layoutOverride = null } = opts;
  const { width, height } = measure(svg);

  const L = layoutOverride || (svg === $("network") ? ensureLayout(run, svg)
                                                    : computeLayout(run, width, height));
  svg.setAttribute("viewBox", `0 0 ${L.width} ${L.height}`);
  svg.textContent = "";

  const { assets, portfolios, holdings } = run.topology;
  const frame = run.frames[Math.min(frameIndex, run.frames.length - 1)];
  const breachNow = new Set(showBreachAt !== null ? showBreachAt : []);
  const breachedEver = new Set(
    run.frames.slice(0, frameIndex + 1).flatMap((f) => f.breached)
  );
  const defaulted = new Set(frame.defaulted || []);

  const drop = assets.map((_, i) => 1 - frame.prices[i]);
  const worstDrop = Math.max(0.0005, ...drop);

  // column rails — structure where edges are sparse
  [L.assetPos[0], L.fundPos[0]].forEach((p, k) => {
    const x = k === 0 ? L.width * 0.24 : L.width * 0.76;
    svg.appendChild(el("line", {
      x1: x, y1: 22, x2: x, y2: L.height - 22,
      stroke: "var(--rule)", "stroke-width": 1, "stroke-dasharray": "2 4",
    }));
  });

  // Edges carry STRUCTURE. Nodes carry STATE. Recolouring every edge of a
  // breached fund turned 47 of 50 edges red, at which point red stopped
  // meaning "breached" and started meaning "most things". Edges stay neutral;
  // only the flow strokes and the nodes are ever red.
  //
  // This bipartite graph is near-complete, so edge *presence* says almost
  // nothing — the information is entirely in the weights. Opacity scales
  // superlinearly with weight so a 30% position reads and a 2% one recedes
  // to context. Every edge is still drawn; none is hidden.
  holdings.forEach((row, j) =>
    row.forEach((v, i) => {
      if (v <= 0) return;
      const w = L.weights[j][i] / L.maxWeight;
      svg.appendChild(el("line", {
        x1: L.assetPos[i].x, y1: L.assetPos[i].y,
        x2: L.fundPos[j].x, y2: L.fundPos[j].y,
        stroke: "var(--ink-0)",
        opacity: (0.04 + 0.30 * Math.pow(w, 1.8)).toFixed(3),
        "stroke-width": (0.5 + 4.5 * Math.pow(w, 1.3)).toFixed(2),
      }));
    })
  );

  // liquidation flows — dash travelling portfolio → asset
  if (flows) {
    flows.forEach(({ fund, asset, value, maxValue }) => {
      const a = L.assetPos[asset], f = L.fundPos[fund];
      const len = Math.hypot(f.x - a.x, f.y - a.y);
      const path = el("line", {
        x1: f.x, y1: f.y, x2: a.x, y2: a.y,
        stroke: "var(--alert)",
        "stroke-width": (1 + 5 * Math.sqrt(value / maxValue)).toFixed(2),
        "stroke-dasharray": `${len} ${len}`,
        "stroke-dashoffset": len,
      });
      svg.appendChild(path);
      path.animate(
        [{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
        { duration: DUR_FLOW, easing: "cubic-bezier(.4,0,1,1)", fill: "forwards" }
      );
    });
  }

  // assets
  assets.forEach((ticker, i) => {
    const p = L.assetPos[i];
    const severity = drop[i] / worstDrop;
    const hurt = drop[i] > 0.0005;
    // luminance first, hue last: dim white -> full white -> red
    const fill = hurt
      ? severity > 0.55 ? "var(--alert)" : "var(--accent)"
      : "var(--accent-30)";
    svg.appendChild(el("circle", { cx: p.x, cy: p.y, r: p.r.toFixed(1), fill }));
    if (i === run.shock.assetIndex) {
      svg.appendChild(el("circle", {
        cx: p.x, cy: p.y, r: (p.r + 7).toFixed(1), fill: "none",
        stroke: "var(--alert)", "stroke-width": 1, "stroke-dasharray": "2 3",
      }));
    }
    svg.appendChild(el("text", {
      x: p.x - p.r - 12, y: p.y + 4, "text-anchor": "end",
      "font-family": "var(--mono)", "font-size": 12, "font-weight": 500,
      fill: hurt ? "var(--ink-0)" : "var(--ink-2)",
    }, ticker));
    // live readout — density from data, never decoration
    svg.appendChild(el("text", {
      x: p.x - p.r - 12, y: p.y + 17, "text-anchor": "end",
      "font-family": "var(--mono)", "font-size": 11,
      fill: hurt ? "var(--alert)" : "var(--ink-2)",
      style: "font-variant-numeric:tabular-nums",
    }, hurt ? `−${(drop[i] * 100).toFixed(2)}%` : "0.00%"));
  });

  // portfolios
  portfolios.forEach((name, j) => {
    const p = L.fundPos[j];
    const now = breachNow.has(j);
    const ever = breachedEver.has(j);
    const dead = defaulted.has(j);
    const fill = dead ? "var(--alert-45)" : ever ? "var(--alert)" : "var(--accent-30)";
    const s = p.side;
    svg.appendChild(el("rect", {
      x: p.x - s / 2, y: p.y - s / 2, width: s, height: s, fill,
    }));
    if (dead) {
      svg.appendChild(el("line", {
        x1: p.x - s / 2, y1: p.y + s / 2, x2: p.x + s / 2, y2: p.y - s / 2,
        stroke: "var(--ink-0)", "stroke-width": 1,
      }));
    }
    if (now) {
      const ring = el("rect", {
        x: p.x - s / 2 - 6, y: p.y - s / 2 - 6, width: s + 12, height: s + 12,
        fill: "none", stroke: "var(--alert)", "stroke-width": 2,
        class: "pulse",   // fill-box + centre origin, or scale() throws it off the node
      });
      svg.appendChild(ring);
      ring.animate(
        [{ opacity: 1, transform: "scale(1)" }, { opacity: .35, transform: "scale(1.12)" }],
        { duration: 520, easing: "cubic-bezier(.4,0,1,1)",
          fill: "forwards", iterations: 1 }
      );
    }
    // clear the BREACH RING, not just the node — the ring reaches s/2+7 and a
    // label at s/2+12 left only 3px on the widest fund.
    const labelX = p.x + s / 2 + 18;
    svg.appendChild(el("text", {
      x: labelX, y: p.y + 1, "font-family": "var(--mono)",
      "font-size": 12, "font-weight": 500,
      fill: ever ? "var(--ink-0)" : "var(--ink-2)",
    }, name));
    const lev = frame.leverage[j];
    svg.appendChild(el("text", {
      x: labelX, y: p.y + 15, "font-family": "var(--mono)", "font-size": 11,
      fill: dead ? "var(--alert)" : ever ? "var(--alert)" : "var(--ink-2)",
      style: "font-variant-numeric:tabular-nums",
    }, lev === null ? "INSOLVENT" : `L ${lev.toFixed(2)}`));
  });

  svg.appendChild(el("text", {
    x: L.width * 0.24, y: 16, "text-anchor": "middle", "font-family": "var(--mono)",
    "font-size": 10, fill: "var(--ink-2)", "letter-spacing": "1.4",
  }, "ASSETS"));
  svg.appendChild(el("text", {
    x: L.width * 0.76, y: 16, "text-anchor": "middle", "font-family": "var(--mono)",
    "font-size": 10, fill: "var(--ink-2)", "letter-spacing": "1.4",
  }, "PORTFOLIOS"));
}

/* ─────────────────────────── the cascade, in order ──────────────────────
   Round t: ring who breached → they sell → the price falls.
   Three phases, never overlapped. That sequence IS the argument. */

function flowsFor(run, t) {
  const frame = run.frames[t];
  if (!frame.sold) return null;
  const out = [];
  let maxValue = 0;
  frame.sold.forEach((row, fund) =>
    row.forEach((value, asset) => {
      if (value > 0) { out.push({ fund, asset, value }); maxValue = Math.max(maxValue, value); }
    })
  );
  return out.length ? out.map((f) => ({ ...f, maxValue })) : null;
}

function showRound(t, { animate = false } = {}) {
  const run = state.run;
  state.frame = t;
  paintTimeline(t);
  paintBand(run, t);

  if (!animate || t === 0) {
    drawNetwork($("network"), run, t);
    $("roundLabel").textContent = t === 0 ? "shock applied" : `round ${t} / ${run.frames.length - 1}`;
    return;
  }

  const prev = t - 1;
  const breachers = run.frames[t].breached;

  // 1 — they're over the limit
  $("roundLabel").textContent = `round ${t} · breach`;
  drawNetwork($("network"), run, prev, { showBreachAt: breachers });

  // 2 — they sell
  later(() => {
    $("roundLabel").textContent = `round ${t} · liquidating`;
    drawNetwork($("network"), run, prev, {
      showBreachAt: breachers, flows: flowsFor(run, t),
    });
  }, DUR_BREACH);

  // 3 — the price falls
  later(() => {
    $("roundLabel").textContent = `round ${t} / ${run.frames.length - 1}`;
    drawNetwork($("network"), run, t);
  }, DUR_BREACH + DUR_FLOW);
}

function playCascade() {
  stopAnimations();
  const run = state.run;
  showRound(0);
  const step = DUR_BREACH + DUR_FLOW + SETTLE_HOLD;
  for (let t = 1; t < run.frames.length; t++) {
    later(() => showRound(t, { animate: true }), (t - 1) * step + 260);
  }
}

/* ───────────────────────────── timeline ───────────────────────────────── */

function paintTimeline(current) {
  const track = $("track");
  track.textContent = "";
  state.run.frames.forEach((_, t) => {
    const seg = document.createElement("button");
    seg.className = "tl-seg";
    seg.dataset.state = t === current ? "current" : t < current ? "done" : "idle";
    seg.title = t === 0 ? "shock applied" : `round ${t}`;
    seg.addEventListener("click", () => {
      clearTimers();
      // the strip belongs to the cascade. clicking it while boundary or split
      // is up used to redraw a hidden #network — the label changed, nothing
      // moved, and the split kept its own contradictory round counter.
      if (state.beat !== "network") showScene("network");
      showRound(t);
    });
    track.appendChild(seg);
  });
}

/* ───────────────────────────── metrics band ───────────────────────────── */

const BAND_LABELS = ["Shock loss", "After cascade", "Amplification", "Breaches", "Rounds"];

const bandHTML = (cells) => cells
  .map(([l, v, s]) =>
    `<div class="cell"${s ? ` data-state="${s}"` : ""}><span class="v num">${v}</span><span class="l">${l}</span></div>`)
  .join("");

function paintBand(run, t) {
  const m = run.metrics;
  const breachedSoFar = new Set(run.frames.slice(0, t + 1).flatMap((f) => f.breached)).size;
  $("band").innerHTML = bandHTML([
    [BAND_LABELS[0], pct1(m.shock_loss), ""],
    [BAND_LABELS[1], pct1(m.final_loss), "hot"],
    [BAND_LABELS[2], mult(m.amplification), "hot"],
    [BAND_LABELS[3], `${breachedSoFar}`, breachedSoFar ? "hot" : ""],
    [BAND_LABELS[4], `${t} / ${run.frames.length - 1}`, ""],
  ]);
}

/* Everything downstream of a run, back to blank. Without this the no-break
   answer left the PREVIOUS cascade sitting on the stage: the hero read
   "nothing breaks this system at these settings" while the band under it
   read 9.1% loss, 1.87× amplification and 4 breaches, Stabilise was still
   enabled, and Replay would cheerfully re-animate the run we had just
   disowned. Two contradictory answers on screen at once. */
function clearRun() {
  stopAnimations();
  state.run = null;
  state.layout = null;
  state.frame = 0;
  $("network").textContent = "";
  $("track").textContent = "";
  $("roundLabel").textContent = "no run";
  $("band").innerHTML = bandHTML(BAND_LABELS.map((l) => [l, "—", ""]));
  $("defendBtn").disabled = true;
}

/* ────────────────────────────── hero number ───────────────────────────── */

function countTo(target) {
  const node = $("heroVal");
  node.removeAttribute("data-idle");
  const started = performance.now();
  const dur = 520;
  function tick(now) {
    const k = Math.min(1, (now - started) / dur);
    node.textContent = `${(target * k).toFixed(2)}%`;
    if (k < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

/* ───────────────────────────── engine badge ───────────────────────────── */

function setEngine(mode, text) {
  const badge = $("badge");
  badge.dataset.mode = mode;
  $("badgeText").textContent = text;
}

/* api() puts a cached answer on the badge, and then each caller used to
   stamp "engine live" over it two lines later — so a replayed run was
   indistinguishable from a solved one, which is the precise thing the
   cached badge exists to prevent. A cached answer keeps its own wording. */
function engineBadge(body, liveText = "engine live") {
  if (!body.cached) setEngine("live", liveText);
}

function setSolver(name, stats) {
  $("solverName").textContent = name;
  $("solverStats").innerHTML = stats;
}

/* Any action that can exceed 3s shows incremental progress within 500ms.
   No indeterminate spinners exist in this app — a spinner says "we don't
   know what's happening", which is the opposite of what we want a judge
   to think while MATLAB works. */
function startElapsed(label) {
  const t0 = performance.now();
  setEngine("busy", "solving");
  const id = setInterval(() => {
    const s = ((performance.now() - t0) / 1000).toFixed(1);
    setSolver(label, `<span>elapsed</span> ${s}s`);
  }, 100);
  return () => clearInterval(id);
}

/* ────────────────────────────── scenes ────────────────────────────────── */

function showScene(which) {
  state.beat = which;
  ["sceneNetwork", "sceneBoundary", "sceneSplit"].forEach((id) => {
    $(id).hidden = id !== ({ network: "sceneNetwork", boundary: "sceneBoundary", split: "sceneSplit" }[which]);
  });
}

/* ────────────────────────────── actions ───────────────────────────────── */

async function attack() {
  const btn = $("attackBtn");
  btn.disabled = true;
  stopAnimations();
  const stop = startElapsed("critical-shock search");
  try {
    const { body, ms } = await api(`/api/break?${params()}`);
    stop();
    if (!body.found) {
      clearRun();
      showScene("network");
      engineBadge(body, "no break found");
      $("heroVal").setAttribute("data-idle", "");
      $("heroVal").textContent = "—";
      $("heroSub").textContent = "nothing breaks this system at these settings — raise leverage or impact";
      setSolver("grid scan + bisection", `<span>searched</span> ${body.tickers.length} names · ${ms}ms`);
      return;
    }
    state.run = normalise(body);
    state.layout = null;
    showScene("network");
    // one frame so the stage has real dimensions before we measure it
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    ensureLayout(state.run, $("network"));

    countTo(body.pct);
    $("heroSub").textContent =
      `${body.asset} · ${body.breached.length} of ${body.funds.length} funds forced to sell` +
      (body.converged ? "" : " · did not converge");
    engineBadge(body);
    setSolver("grid scan + bisection",
      `<span>names</span> ${body.tickers.length} <span>· step</span> 1.0% <span>·</span> ${ms}ms`);
    $("defendBtn").disabled = false;
    playCascade();
  } catch (err) {
    stop();
    setEngine("cached", "engine unreachable");
    $("heroSub").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
}

async function boundary() {
  const btn = $("boundaryBtn");
  btn.disabled = true;
  stopAnimations();
  const stop = startElapsed("boundary sweep");
  try {
    const { body, ms } = await api(`/api/boundary?${params()}`);
    stop();
    state.boundary = body;
    showScene("boundary");
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    drawBoundary($("boundary"), body);
    engineBadge(body);
    setSolver("parameter sweep",
      `<span>cells</span> ${body.rows * body.cols} <span>·</span> ${ms}ms`);
  } catch (err) {
    stop();
    setEngine("cached", "engine unreachable");
  } finally {
    btn.disabled = false;
  }
}

async function defend() {
  const btn = $("defendBtn");
  btn.disabled = true;
  stopAnimations();
  const stop = startElapsed("minimum-cost stabilisation");
  try {
    const { body, ms } = await api(`/api/stabilise?${params()}`);
    stop();
    showScene("split");
    engineBadge(body);

    if (!body.found) {
      // The banner used to be the only thing this branch wrote, so it landed
      // on top of the previous run's panels — "no single-position cut clears
      // it" above a before/after comparison that did clear it, stamped with
      // an identical-shock line naming a shock that is no longer the one we
      // are solving. Wipe the halves; there is nothing to compare.
      clearSplit();
      $("fixLine").hidden = false;
      $("fixLine").innerHTML = `<b>No single-position cut clears it.</b> <em>this system needs more than one change</em>`;
      return;
    }
    const f = body.fix;
    $("fixLine").hidden = false;
    $("fixLine").innerHTML =
      `<b>${f.fund}</b>: cut <b>${f.asset}</b> exposure ${(f.reduction * 100).toFixed(0)}% ` +
      `<em>· costs ${pct2(f.cost)} of gross assets</em>`;

    split.before = normalise({ ...body, ...body.before });
    split.after = normalise({ ...body, ...body.after });
    // ONE layout, shared by both halves. different node positions either side
    // would let a judge think the structure changed rather than one position.
    // let the split grid lay out before measuring either half
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const half = measure($("netBefore"));
    split.layout = computeLayout(split.before, half.width, half.height);
    playSplit();

    const line = (r) =>
      `${pct1(r.metrics.final_loss)} loss · ${r.breached.length} breaches · amp ${r.metrics.amplification.toFixed(2)}×`;
    $("footBefore").textContent = line(body.before);
    $("footAfter").textContent = line(body.after);
    $("shockStamp").textContent = `identical shock · ${body.pct.toFixed(2)}% ${body.asset}`;

    const e = body.engine || {};
    setSolver(e.name || "minimum-cost search",
      `<span>${e.note || ""}</span><br>${e.evaluations || 0} evals · ${e.solve_ms || ms}ms` +
      (e.exit_flag !== undefined ? ` · <span>exit</span> ${e.exit_flag}` : ""));
  } catch (err) {
    stop();
    setEngine("cached", "engine unreachable");
  } finally {
    btn.disabled = false;
  }
}

/* Flatten the API's payload into the shape the stage draws from. */
function normalise(body) {
  return {
    topology: {
      assets: body.tickers,
      portfolios: body.funds,
      holdings: body.holdings,
      adv: body.adv,
    },
    shock: { assetIndex: body.asset_index ?? 0, ticker: body.asset, pct: body.pct },
    frames: body.trajectory,
    metrics: body.metrics,
    breached: body.breached,
    converged: body.converged,
  };
}

/* ──────────────────────── split view: both sides, in lockstep ───────────
   The point of beat 4 is that the shock is IDENTICAL. So both sides replay
   at the same tempo from round 0 and you watch them diverge, rather than
   comparing two still pictures and taking our word for it. */

const split = { before: null, after: null, layout: null, timers: [] };

function clearSplit() {
  stopAnimations();
  split.before = split.after = split.layout = null;
  $("netBefore").textContent = "";
  $("netAfter").textContent = "";
  $("footBefore").textContent = "—";
  $("footAfter").textContent = "—";
  $("shockStamp").textContent = "—";
  $("splitRound").textContent = "—";
}

function splitFrame(side, svg, t) {
  const run = split[side];
  const clamped = Math.min(t, run.frames.length - 1);
  const breachers = clamped > 0 ? run.frames[clamped].breached : [];
  drawNetwork(svg, run, clamped, {
    layoutOverride: split.layout,
    showBreachAt: breachers.length ? breachers : null,
  });
}

function playSplit() {
  stopAnimations();
  const longest = Math.max(split.before.frames.length, split.after.frames.length);
  const step = DUR_BREACH + DUR_FLOW + SETTLE_HOLD;

  const draw = (t) => {
    splitFrame("before", $("netBefore"), t);
    splitFrame("after", $("netAfter"), t);
    $("splitRound").textContent =
      t === 0 ? "shock applied — identical on both sides" : `round ${t} of ${longest - 1}`;
  };

  draw(0);
  for (let t = 1; t < longest; t++) {
    split.timers.push(setTimeout(() => draw(t), (t - 1) * step + 420));
  }
}

/* ───────────────────────────── phase diagram ──────────────────────────── */

function drawBoundary(svg, b) {
  const m = measure(svg);
  const W = Math.max(520, m.width), H = Math.max(300, m.height);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.textContent = "";

  const L = 74, R = W - 40, T = 34, B = H - 56;
  const cw = (R - L) / b.cols, ch = (B - T) / b.rows;

  const band = (a) =>
    a < 1.05 ? ["var(--accent)", 0.30]
    : a < 1.30 ? ["var(--accent)", 0.62]
    : a < 1.80 ? ["var(--alert)", 0.35]
    : a < 3.00 ? ["var(--alert)", 0.62]
    : ["var(--alert)", 0.92];

  for (let r = 0; r < b.rows; r++) {
    for (let c = 0; c < b.cols; c++) {
      const [fill, opacity] = band(b.grid[r][c]);
      svg.appendChild(el("rect", {
        x: (L + c * cw).toFixed(2), y: (T + (b.rows - 1 - r) * ch).toFixed(2),
        width: (cw + 0.6).toFixed(2), height: (ch + 0.6).toFixed(2), fill, opacity,
      }));
    }
  }
  svg.appendChild(el("rect", {
    x: L, y: T, width: R - L, height: B - T,
    fill: "none", stroke: "var(--rule-hi)", "stroke-width": 1,
  }));

  const lo = b.leverage_axis[0], hi = b.leverage_axis[b.rows - 1];
  const omin = b.overlap_axis[0], omax = b.overlap_axis[b.cols - 1];
  const mx = L + ((b.here.overlap - omin) / (omax - omin)) * (R - L);
  const my = T + ((hi - b.here.leverage) / (hi - lo)) * (B - T);
  svg.appendChild(el("circle", { cx: mx, cy: my, r: 7, fill: "none", stroke: "var(--ink-0)", "stroke-width": 2 }));
  svg.appendChild(el("circle", { cx: mx, cy: my, r: 2, fill: "var(--ink-0)" }));

  const label = (x, y, t, o = {}) => svg.appendChild(el("text", {
    x, y, "font-family": "var(--mono)", "font-size": o.size || 11,
    fill: o.fill || "var(--ink-2)", "text-anchor": o.anchor || "middle",
    "letter-spacing": o.ls || "0",
    style: "font-variant-numeric:tabular-nums",
  }, t));

  // flip the callout to the left of the marker when it would overrun, and put
  // it on a plate — #616161 over pale amplification cells is unreadable
  const sub = `L ${b.here.leverage.toFixed(1)} · overlap ${b.here.overlap.toFixed(2)}`;
  const plateW = Math.max(96, sub.length * 6.6) + 14;
  const flip = mx + 14 + plateW > R;
  const px = flip ? mx - 14 - plateW : mx + 14;
  svg.appendChild(el("rect", {
    x: px - 6, y: my - 20, width: plateW, height: 34,
    fill: "var(--bg-0)", opacity: 0.82,
  }));
  label(px, my - 6, "YOU ARE HERE", { fill: "var(--ink-0)", anchor: "start", ls: "1.2" });
  label(px, my + 9, sub, { anchor: "start", fill: "var(--ink-1)" });

  label(L - 10, B + 3, lo.toFixed(1), { anchor: "end" });
  label(L - 10, T + 8, hi.toFixed(1), { anchor: "end" });
  label(L + 2, B + 20, omin.toFixed(2), { anchor: "start" });
  label(R, B + 20, omax.toFixed(2), { anchor: "end" });
  label((L + R) / 2, B + 38, "PORTFOLIO OVERLAP →", { ls: "1.4" });
  const yl = el("text", {
    "font-family": "var(--mono)", "font-size": 11, fill: "var(--ink-2)",
    "text-anchor": "middle", "letter-spacing": "1.4",
  }, "GROSS LEVERAGE →");
  yl.setAttribute("transform", `translate(24,${(T + B) / 2}) rotate(-90)`);
  svg.appendChild(yl);

  label(R - 6, T - 10, `amplification · ${b.reference_kind} ${Math.abs(b.reference_shock * 100).toFixed(0)}% reference`,
    { anchor: "end", size: 10 });
}

/* ──────────────────────────────── boot ────────────────────────────────── */

async function boot() {
  try {
    await api("/api/health");
    setEngine("live", "engine live");
  } catch {
    setEngine("cached", "server down");
    return;
  }
  // Geist reflows the masthead when it lands, which changes the stage height
  // and invalidates the layout. The obvious fix — await document.fonts.ready
  // before drawing — is a trap: if the font CDN is slow or blocked, NOTHING
  // draws. I shipped that version and it rendered an empty stage. So draw
  // immediately and let watchStage() correct it when the font arrives. Never
  // block first paint on a third-party request.
  watchStage();
  await attack();
}

["leverage", "gamma"].forEach((id) =>
  $(id).addEventListener("input", (e) => {
    $(id + "Val").textContent =
      id === "gamma" ? Number(e.target.value).toFixed(2) : Number(e.target.value).toFixed(1);
  })
);
$("attackBtn").addEventListener("click", attack);
$("replayBtn").addEventListener("click", () => {
  if (state.beat === "split" && split.before) return playSplit();
  if (state.run) { showScene("network"); playCascade(); }
});
$("boundaryBtn").addEventListener("click", boundary);
$("defendBtn").addEventListener("click", defend);
/* A window resize listener is not enough. The Geist webfont lands after
   first paint, reflows the masthead, and the stage changes height — so the
   layout was computed against a box that no longer exists and the diagram
   renders short. Observe the stage itself and it follows every reflow,
   font load included. */
function watchStage() {
  if (typeof ResizeObserver === "undefined") return;
  let settle = null;
  new ResizeObserver(() => {
    clearTimeout(settle);
    settle = setTimeout(redrawCurrentScene, 60);
  }).observe($("stage"));
}

function redrawCurrentScene() {
  if (state.beat === "network" && state.run) {
    drawNetwork($("network"), state.run, state.frame);
  } else if (state.beat === "split" && split.before) {
    const half = measure($("netBefore"));
    split.layout = computeLayout(split.before, half.width, half.height);
    splitFrame("before", $("netBefore"), split.before.frames.length - 1);
    splitFrame("after", $("netAfter"), split.after.frames.length - 1);
  } else if (state.beat === "boundary" && state.boundary) {
    drawBoundary($("boundary"), state.boundary);
  }
}

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(redrawCurrentScene, 120);
});

boot();
