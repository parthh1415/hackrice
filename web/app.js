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
  layout: null,     // computed once per topology, never re-run
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
  return { body, ms };
}

function clearTimers() {
  state.timers.forEach(clearTimeout);
  state.timers = [];
}
const later = (fn, ms) => state.timers.push(setTimeout(fn, ms));

/* ─────────────────────────── deterministic layout ───────────────────────
   Not force-directed. Force layout jitters on every mount and is the
   clearest tell of a student project. Positions are sorted once and frozen,
   so it looks identical in rehearsal and on stage.

   Assets left, portfolios right: the shock enters at an asset and travels
   to portfolios, so causality runs left to right. */

function computeLayout(run, width, height) {
  const { assets, portfolios, holdings } = run.topology;

  const exposure = assets.map((_, i) => holdings.reduce((s, row) => s + row[i], 0));
  const gross = holdings.map((row) => row.reduce((a, b) => a + b, 0));
  const maxExp = Math.max(...exposure);
  const maxGross = Math.max(...gross);

  const assetOrder = assets.map((_, i) => i).sort((a, b) => exposure[b] - exposure[a]);
  const fundOrder = portfolios.map((_, j) => j).sort((a, b) => gross[b] - gross[a]);

  const padY = 40;
  const slotA = (height - 2 * padY) / assets.length;
  const slotF = (height - 2 * padY) / portfolios.length;

  const assetPos = [], fundPos = [];
  assetOrder.forEach((i, rank) => {
    assetPos[i] = {
      x: width * 0.24,
      y: padY + (rank + 0.5) * slotA,
      r: 4 + 10 * Math.sqrt(exposure[i] / maxExp),
    };
  });
  fundOrder.forEach((j, rank) => {
    const side = 10 + 14 * Math.sqrt(gross[j] / maxGross);
    fundPos[j] = { x: width * 0.76, y: padY + (rank + 0.5) * slotF, side };
  });

  const weights = holdings.map((row, j) => row.map((v) => (gross[j] > 0 ? v / gross[j] : 0)));

  return { assetPos, fundPos, weights, width, height, gross };
}

/* ───────────────────────────── the network ───────────────────────────── */

function drawNetwork(svg, run, frameIndex, opts = {}) {
  const { showBreachAt = null, flows = null, layoutOverride = null } = opts;
  const box = svg.getBoundingClientRect();
  const width = Math.max(420, box.width || 700);
  const height = Math.max(280, box.height || 420);

  const L = layoutOverride || state.layout || computeLayout(run, width, height);
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

  // edges, straight — a curve implies a flow direction that isn't there at rest
  holdings.forEach((row, j) =>
    row.forEach((v, i) => {
      if (v <= 0) return;
      const live = breachedEver.has(j);
      svg.appendChild(el("line", {
        x1: L.assetPos[i].x, y1: L.assetPos[i].y,
        x2: L.fundPos[j].x, y2: L.fundPos[j].y,
        stroke: live ? "var(--alert-45)" : "var(--rule-hi)",
        "stroke-width": (0.5 + 6 * L.weights[j][i]).toFixed(2),
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
      });
      svg.appendChild(ring);
      ring.animate(
        [{ opacity: 1, transform: "scale(1)" }, { opacity: .35, transform: "scale(1.12)" }],
        { duration: 520, easing: "cubic-bezier(.4,0,1,1)",
          fill: "forwards", iterations: 1 }
      );
    }
    svg.appendChild(el("text", {
      x: p.x + s / 2 + 12, y: p.y + 1, "font-family": "var(--mono)",
      "font-size": 12, "font-weight": 500,
      fill: ever ? "var(--ink-0)" : "var(--ink-2)",
    }, name));
    const lev = frame.leverage[j];
    svg.appendChild(el("text", {
      x: p.x + s / 2 + 12, y: p.y + 15, "font-family": "var(--mono)", "font-size": 11,
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
  clearTimers();
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
    seg.addEventListener("click", () => { clearTimers(); showRound(t); });
    track.appendChild(seg);
  });
}

/* ───────────────────────────── metrics band ───────────────────────────── */

function paintBand(run, t) {
  const m = run.metrics;
  const breachedSoFar = new Set(run.frames.slice(0, t + 1).flatMap((f) => f.breached)).size;
  const cells = [
    ["Shock loss", pct1(m.shock_loss), ""],
    ["After cascade", pct1(m.final_loss), "hot"],
    ["Amplification", mult(m.amplification), "hot"],
    ["Breaches", `${breachedSoFar}`, breachedSoFar ? "hot" : ""],
    ["Rounds", `${t} / ${run.frames.length - 1}`, ""],
  ];
  $("band").innerHTML = cells
    .map(([l, v, s]) =>
      `<div class="cell"${s ? ` data-state="${s}"` : ""}><span class="v num">${v}</span><span class="l">${l}</span></div>`)
    .join("");
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
  const stop = startElapsed("critical-shock search");
  try {
    const { body, ms } = await api(`/api/break?${params()}`);
    stop();
    if (!body.found) {
      setEngine("live", "no break found");
      $("heroVal").setAttribute("data-idle", "");
      $("heroVal").textContent = "—";
      $("heroSub").textContent = "nothing breaks this system at these settings — raise leverage or impact";
      setSolver("grid scan + bisection", `<span>searched</span> ${body.tickers.length} names · ${ms}ms`);
      return;
    }
    state.run = normalise(body);
    state.layout = null;
    showScene("network");
    state.layout = computeLayout(state.run, $("network").getBoundingClientRect().width || 700,
                                 $("network").getBoundingClientRect().height || 420);

    countTo(body.pct);
    $("heroSub").textContent =
      `${body.asset} · ${body.breached.length} of ${body.funds.length} funds forced to sell` +
      (body.converged ? "" : " · did not converge");
    setEngine("live", "engine live");
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
  const stop = startElapsed("boundary sweep");
  try {
    const { body, ms } = await api(`/api/boundary?${params()}`);
    stop();
    showScene("boundary");
    drawBoundary($("boundary"), body);
    setEngine("live", "engine live");
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
  const stop = startElapsed("minimum-cost stabilisation");
  try {
    const { body, ms } = await api(`/api/stabilise?${params()}`);
    stop();
    showScene("split");
    setEngine("live", "engine live");

    if (!body.found) {
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
    const halfW = $("netBefore").getBoundingClientRect().width || 420;
    const halfH = $("netBefore").getBoundingClientRect().height || 360;
    split.layout = computeLayout(split.before, halfW, halfH);
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
  split.timers.forEach(clearTimeout);
  split.timers = [];
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
  const box = svg.getBoundingClientRect();
  const W = Math.max(520, box.width || 720), H = Math.max(300, box.height || 420);
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

  label(Math.min(mx + 14, R - 90), my - 6, "YOU ARE HERE", { fill: "var(--ink-0)", anchor: "start", ls: "1.2" });
  label(Math.min(mx + 14, R - 90), my + 10,
    `L ${b.here.leverage.toFixed(1)} · overlap ${b.here.overlap.toFixed(2)}`, { anchor: "start" });

  label(L - 10, B + 3, lo.toFixed(1), { anchor: "end" });
  label(L - 10, T + 8, hi.toFixed(1), { anchor: "end" });
  label(L, B + 18, omin.toFixed(2));
  label(R, B + 18, omax.toFixed(2));
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
  // never an empty stage — the first frame is a thumbnail
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
window.addEventListener("resize", () => {
  if (!state.run) return;
  state.layout = null;
  state.layout = computeLayout(state.run,
    $("network").getBoundingClientRect().width || 700,
    $("network").getBoundingClientRect().height || 420);
  if (state.beat === "network") drawNetwork($("network"), state.run, state.frame);
});

boot();
