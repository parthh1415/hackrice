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
  dataset: null,    // provenance for the assumptions panel
  boundary: null,   // last /api/boundary payload, kept so a reflow can redraw
  layout: null,     // rebuilt whenever the measured stage moves
  frame: 0,
  timers: [],
  beat: "idle",
  request: 0,       // ticket of the action that currently owns the stage
  knobs: null,      // the slider positions the run on screen actually answers
};

/* ────────────────────────────── formatting ─────────────────────────────
   Every number is fixed-width and fixed-decimal. Digits must never reflow
   mid-animation — that single detail is the fastest way to look amateur. */

const pct1 = (x) => `${(x * 100).toFixed(1)}%`;
const pct2 = (x) => `${(x * 100).toFixed(2)}%`;

// Two significant figures, not a fixed decimal count. The fix line used
// toFixed(0) for the reduction and pct2 for the cost, which read fine while
// the stabiliser was pinned to its 5% grid. Once the bisection went relative
// the answer dropped to 0.073% and the same line rendered "cut NVDA exposure
// 0% · costs 0.00% of gross assets" — beat 4's entire payoff, as two zeros. A
// formatter that only works at one order of magnitude is a formatter waiting
// for the number to move.
const pctSig = (x) => {
  const v = x * 100;
  if (!isFinite(v) || v === 0) return "0%";
  const dp = Math.min(6, Math.max(0, 1 - Math.floor(Math.log10(Math.abs(v)))));
  return `${v.toFixed(dp)}%`;
};

const usd = (x) => {
  const a = Math.abs(x);
  if (a >= 1e12) return `$${(x / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `$${(x / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(x / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(x / 1e3).toFixed(0)}K`;
  return `$${x.toFixed(0)}`;
};
const mult = (x) => `${x.toFixed(2)}×`;

function el(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function knobs() {
  return {
    leverage: Number($("leverage").value),
    gamma: Number($("gamma").value),
    band: Number($("breachBand").value),
    breaches: Number($("breaches").value),
  };
}

function params() {
  return new URLSearchParams({
    leverage: $("leverage").value,
    gamma: $("gamma").value,
    band: $("breachBand").value,
    breaches: $("breaches").value,
  }).toString();
}

/* Dragging a slider costs nothing and answers nothing — the engine is not
   consulted until a button is pressed. So the knobs say one scenario while
   every number on the stage answers a different one, and the screen gives no
   hint which. Reproduced: leverage dragged 8 → 1.5 and impact 0.20 → 1.00
   with the hero still reading 2.41% and the band still 3.6% / 11.1% / 3.12×,
   all of it from the run before. Replay then re-animates that disowned run
   under the new slider labels, which is the same lie with motion on it.
   Say which settings the numbers belong to, and dim them. */
function checkKnobs() {
  if (!state.run || !state.knobs) return;
  const now = knobs(), was = state.knobs;
  const moved = now.leverage !== was.leverage || now.gamma !== was.gamma ||
                now.band !== was.band || now.breaches !== was.breaches;
  if (moved) setNote("knobs", `showing ${knobLabel(was)} — press Find weakest shock`, true);
  else clearNote("knobs");
}

async function api(path, owns = () => true) {
  const started = performance.now();
  let res;
  try {
    res = await fetch(path, { cache: "no-store" });
  } catch (err) {
    throw Object.assign(new Error(`${path} → ${err.message}`), { transport: true });
  }
  const ms = Math.round(performance.now() - started);
  if (!res.ok) throw Object.assign(new Error(`${path} → ${res.status}`), { transport: true });
  const body = await res.json();
  // a recorded answer must never pass for a live one — but only the answer
  // still on the stage gets to say anything about the engine at all
  if (body && body.cached && owns()) setEngine("cached", cachedLabel(body));
  return { body, ms };
}

/* "cached" was doing two very different jobs with one word. A recording OF
   these slider positions is a replay. A recording of the NEAREST positions we
   happen to have on disk is an answer to a different question — and every
   number downstream of it is then confident and wrong: the hero, the band,
   the fix cost, the "you are here" dot. api.py computes `cached_exact` and
   `cached_for` for precisely this and we were dropping both, so leverage 6.4
   quietly showed the leverage-6 run under the same "cached run" label.
   Kept to the width of the longest live string; the badge sits next to the
   hero and must not push it around. */
function cachedLabel(body) {
  if (body.cached_exact === false) return `recording of ${knobLabel(body.cached_for)}`;
  return body.fallback_reason ? "cached · engine failed" : "cached run";
}

function knobLabel(at) {
  if (!at) return "other settings";
  const bits = [];
  if (at.leverage !== undefined) bits.push(`L ${Number(at.leverage).toFixed(1)}`);
  if (at.gamma !== undefined) bits.push(`γ ${Number(at.gamma).toFixed(2)}`);
  if (at.band !== undefined) bits.push(`band ${Number(at.band).toFixed(2)}`);
  if (at.breaches !== undefined) bits.push(`≥${Number(at.breaches).toFixed(0)}`);
  return bits.length ? bits.join(" ") : "other settings";
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
    // ...minus whatever else the container holds. #sceneNetwork contains only
    // the svg, so this changes nothing there. .split-half is a column of
    // caption + svg + footer, so the parent overstated the svg's height by
    // 72px: the layout was built for a 473px box, written into a 473px
    // viewBox, and then scaled down by the browser to fit the svg's real
    // 401px — both halves of beat 4 rendering at 85% with ~89px of dead
    // space each. Measuring the container is right; measuring ALL of it
    // wasn't.
    let siblings = 0;
    for (const el of svg.parentElement.children) {
      if (el !== svg) siblings += el.getBoundingClientRect().height;
    }
    const height = parent.height - siblings;
    return { width: parent.width, height: height > 40 ? height : parent.height };
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
    // The frame SAYS who is insolvent. The null leverage sitting next to it is
    // only how +inf survives JSON — read the statement, not the side effect, or
    // the label quietly disappears the day that number serialises as a number.
    const lev = frame.leverage[j];
    const broke = frame.insolvent ? Boolean(frame.insolvent[j]) : lev === null;
    svg.appendChild(el("text", {
      x: labelX, y: p.y + 15, "font-family": "var(--mono)", "font-size": 11,
      fill: dead ? "var(--alert)" : ever ? "var(--alert)" : "var(--ink-2)",
      style: "font-variant-numeric:tabular-nums",
    }, broke ? "INSOLVENT" : `L ${lev.toFixed(2)}`));
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
      claimStage();
      // stopAnimations, not clearTimers: the split owns a SECOND queue, and
      // scrubbing away from a running split left that queue advancing the
      // round stamp inside a hidden scene. Go back with Stabilise or Replay
      // and the comparison is sitting on its ending, four rounds past where
      // you left it, with nothing having animated to get there.
      stopAnimations();
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
  cancelCount();
  state.run = null;
  state.knobs = null;
  state.layout = null;
  state.frame = 0;
  $("network").textContent = "";
  $("track").textContent = "";
  $("roundLabel").textContent = "no run";
  $("band").innerHTML = bandHTML(BAND_LABELS.map((l) => [l, "—", ""]));
  $("defendBtn").disabled = true;
}

/* ────────────────────────────── hero number ───────────────────────────── */

/* The count-up runs on requestAnimationFrame, which no queue owns and
   stopAnimations() cannot reach. Click Find weakest shock twice in under half
   a second — which a nervous presenter does — and the first run's count-up
   was still ticking when the second answer landed. If the second answer is
   "nothing breaks this system", clearRun() blanks the hero and the older
   count-up writes its number straight back over the blank and STOPS there:
   the biggest number on screen ends up belonging to a run we have just
   disowned, above a blank band, an empty timeline, and a sub-line saying
   nothing broke. Generation counter; the run that supersedes it decides what
   the hero says instead. */
let countGen = 0;
let countTarget = null;

/* Leaving a finished run on screen — pressing Map the boundary mid-count —
   must land on the true number, not freeze part-way up. */
function settleCount() {
  countGen++;
  if (countTarget === null) return;
  $("heroVal").textContent = `${countTarget.toFixed(2)}%`;
  countTarget = null;
}

/* The run it belonged to is gone; whoever cancelled it owns the hero now. */
function cancelCount() {
  countGen++;
  countTarget = null;
}

function countTo(target) {
  settleCount();
  const node = $("heroVal");
  node.removeAttribute("data-idle");
  const mine = ++countGen;
  countTarget = target;
  const dur = 520;

  const finish = () => {
    if (mine !== countGen) return;
    node.textContent = `${target.toFixed(2)}%`;
    countTarget = null;
  };

  // The count-up is decoration. The number is the product. Anyone who has
  // asked not to be animated at gets the number.
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    finish();
    return;
  }

  // rAF is not a guarantee, and this went wrong twice in the same night.
  // First its timestamp arrived BEHIND the performance.now() captured just
  // before scheduling, so (now - started) went negative and the hero printed
  // -85.66% beside a diagram reading -5.27%. Clamping the subtraction fixed
  // the sign and produced the quieter version of the same failure: the hero
  // sat at 0.00%, in the largest type on the page, and a screenshot of that
  // looks like a finished render rather than a stalled one.
  //
  // So: start the clock on the first frame, so both ends come off one clock,
  // and put a deadline underneath it, so the answer lands even if the frame
  // clock never advances again — which is what a throttled background tab
  // does, and what headless Chrome does under a virtual-time budget.
  let started = null;
  let done = false;
  const deadline = setTimeout(() => { done = true; finish(); }, dur + 120);

  function tick(now) {
    if (mine !== countGen || done) { clearTimeout(deadline); return; }
    if (started === null) started = now;
    const k = Math.max(0, Math.min(1, (now - started) / dur));
    node.textContent = `${(target * k).toFixed(2)}%`;
    if (k < 1) {
      requestAnimationFrame(tick);
    } else {
      clearTimeout(deadline);
      countTarget = null;
    }
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

/* One line under the hero for anything that makes the numbers on screen less
   than a current answer, and a dimming of the numbers it refers to. Kinds so
   that clearing one reason cannot clear another: a failed sweep must not be
   wiped off the screen by nudging a slider. */
let noteKind = null;

function setNote(kind, text, stale) {
  noteKind = kind;
  $("heroNote").textContent = text;
  if (stale) { $("heroVal").dataset.stale = ""; $("band").dataset.stale = ""; }
  else undim();
}

function clearNote(kind) {
  if (kind && noteKind !== kind) return;
  noteKind = null;
  $("heroNote").textContent = "";
  undim();
}

function undim() {
  delete $("heroVal").dataset.stale;
  delete $("band").dataset.stale;
}

/* api.py clamps a knob it cannot honour rather than erroring — a stack trace
   in front of judges is worse — and declares every adjustment in
   params.clamped so the front end can say so. We were dropping it on the
   floor. The sliders cannot reach a clamped value, but a URL can, and a URL
   typo that comes back with a confident answer to a different question is the
   one failure here worth more than a crash. */
function declareClamped(body) {
  const moved = (body.params && body.params.clamped) || [];
  if (!moved.length) return clearNote();
  const c = moved[0];
  setNote("clamped",
    `${c.name} ${c.given} is ${c.reason} — answered at ${c.used}` +
    (moved.length > 1 ? ` (+${moved.length - 1} more)` : ""), false);
}

/* A beat that failed used to change one 11px word in the masthead and nothing
   else. Press Map the boundary or Stabilise with the engine down and the
   stage does not move, the hero, the sub-line and the solver panel all still
   describe the run before it, and the progress readout is frozen mid-count at
   "boundary sweep · elapsed 0.8s" as though it were still working. From the
   floor that is indistinguishable from a button that does nothing. */
function failed(label, note, stale = false, err = null) {
  // Only a request that never came back is an outage. A render that threw on
  // a payload the server delivered fine is our bug, and calling it "engine
  // unreachable" sends whoever is debugging it at 3am to the wrong process.
  const outage = !err || err.transport;
  const why = outage ? "engine unreachable" : "display error";
  setEngine("cached", why);
  setSolver(label, `<span>failed</span> ${why}`);
  setNote("failed", outage ? note : `${label} could not be drawn — ${err.message}`, stale);
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

/* stopAnimations() only stops what is already on the stage. It cannot stop a
   request that is already in the air, and the engine is not always fast — one
   MATLAB solve on a cold laptop is seconds. So the beat the presenter has
   moved ON from lands anyway, and lands LAST:
     press Map the boundary, get impatient, press Find weakest shock → the
     cascade starts, then the boundary answer arrives and puts the phase
     diagram on the stage while the cascade carries on advancing the round
     label and the metrics band underneath it, narrating a scene nobody can
     see. Measured: label ran on from "round 3 · liquidating" to "round 3 / 3"
     with the boundary on screen.
     Or the other order → the presenter is talking to the phase diagram and
     three seconds later the stage yanks itself back to the network.
   Whichever button was pressed LAST owns the stage. Every action takes a
   ticket on the way in and an answer that no longer holds it is dropped. */
function claimStage() {
  return ++state.request;
}
const holdsStage = (ticket) => ticket === state.request;

async function attack() {
  const btn = $("attackBtn");
  btn.disabled = true;
  stopAnimations();
  // The round label describes the run we are about to replace, and it
  // survived the whole fetch — so during a search the stage narrated the
  // PREVIOUS cascade as though it were this one. Same family as the knob
  // note: numbers on screen that answer a question nobody is asking any
  // more. It also made every predicate that waits on this label satisfiable
  // by the state it was waiting to see replaced; an audit found four of five
  // such waits returning on entry against a slow server, one of them on a
  // fast one, reporting both false greens and false reds.
  $("roundLabel").textContent = "searching";
  const ticket = claimStage();
  const mine = () => holdsStage(ticket);
  const stop = startElapsed("critical-shock search");
  try {
    const { body, ms } = await api(`/api/break?${params()}`, mine);
    stop();
    if (!mine()) return;                 // the presenter has moved on
    if (!body.found) {
      clearRun();
      declareClamped(body);
      showScene("network");
      engineBadge(body, "no break found");
      $("heroVal").setAttribute("data-idle", "");
      $("heroVal").textContent = "—";
      $("heroSub").textContent = "nothing breaks this system at these settings — raise leverage or impact";
      setSolver("grid scan + bisection", `<span>searched</span> ${body.tickers.length} names · ${ms}ms`);
      return;
    }
    state.run = normalise(body);
    if (state.dataset) fillAssumptions(state.dataset, body);
    state.layout = null;
    state.knobs = knobs();
    declareClamped(body);
    showScene("network");
    // one frame so the stage has real dimensions before we measure it
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    if (!mine()) return;
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
    if (!mine()) return;
    failed("critical-shock search",
           state.run ? "engine unreachable — this is the previous run, not a new answer"
                     : "engine unreachable — no answer to show",
           Boolean(state.run), err);
    $("heroSub").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
}

async function boundary() {
  const btn = $("boundaryBtn");
  btn.disabled = true;
  stopAnimations();
  const ticket = claimStage();
  const mine = () => holdsStage(ticket);
  settleCount();   // a half-finished count-up must not freeze part-way up
  const stop = startElapsed("boundary sweep");
  try {
    const { body, ms } = await api(`/api/boundary?${params()}`, mine);
    stop();
    if (!mine()) return;                 // the presenter has moved on
    clearNote("failed");
    state.boundary = body;
    showScene("boundary");
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    if (!mine()) return;
    drawBoundary($("boundary"), body);
    engineBadge(body);
    setSolver("parameter sweep",
      `<span>cells</span> ${body.rows * body.cols} <span>·</span> ${ms}ms`);
  } catch (err) {
    stop();
    if (!mine()) return;
    failed("boundary sweep", "the boundary sweep did not run — engine unreachable", false, err);
  } finally {
    btn.disabled = false;
  }
}

async function defend() {
  const btn = $("defendBtn");
  btn.disabled = true;
  stopAnimations();
  const ticket = claimStage();
  const mine = () => holdsStage(ticket);
  settleCount();   // a half-finished count-up must not freeze part-way up
  const stop = startElapsed("minimum-cost stabilisation");
  try {
    const { body, ms } = await api(`/api/stabilise?${params()}`, mine);
    stop();
    if (!mine()) return;                 // the presenter has moved on
    clearNote("failed");
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
      `<b>${f.fund}</b>: sell <b>${usd(f.sell_usd)}</b> of <b>${f.asset}</b> ` +
      `<em>· ${pctSig(f.reduction)} of a ${usd(f.position_usd)} position ` +
      `· costs ${pctSig(f.cost)} of gross assets</em>`;
    showBought(body.bought);

    split.before = normalise({ ...body, ...body.before });
    split.after = normalise({ ...body, ...body.after });
    // ONE layout, shared by both halves. different node positions either side
    // would let a judge think the structure changed rather than one position.
    // let the split grid lay out before measuring either half
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    if (!mine()) return;
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
    if (!mine()) return;
    failed("minimum-cost stabilisation", "stabilise did not run — engine unreachable", false, err);
  } finally {
    btn.disabled = false;
  }
}

/* What the fix actually buys, in the product's own headline metric, stated
   before anyone can catch us not stating it. A judge presses Find weakest
   shock again after Stabilise and has this in ten seconds: a cheapest
   single-position cut defends against THE shock, not against the next one.

   The engine re-searches the patched books and reports whether the movement
   clears its own bisection tolerance. It usually does not — +0.0039pp against
   a ±0.005pp resolution — so the arrow is drawn without a delta and the note
   says so. Printing "+0.00pp" off a number the search cannot resolve would be
   the same fake precision one level up. */
function showBought(b) {
  const line = $("boughtLine");
  if (!b || b.before_pct === undefined) {
    line.hidden = true;
    line.textContent = "";
    return;
  }
  // after_pct null is the strong outcome, not a missing one: the patched books
  // could not be broken at all. Say that rather than hiding the line.
  const broke = b.after_pct !== null;
  const measurable = b.measurable && b.delta_pct !== null;
  const tail = " — defends this shock, not the next one";

  if (!broke) {
    line.hidden = false;
    line.innerHTML =
      `critical distance <b>${b.before_pct.toFixed(2)}%</b> → <b>nothing breaks it</b>` + tail;
    return;
  }

  // No arrow when there is nothing to point at. This read
  // "critical distance 5.27% → 5.28% · no measurable change", which is two
  // different numbers directly beside the claim that they are the same one.
  // 5.2734 and 5.2773 are indistinguishable to a search resolving to
  // 0.010pp, and they only look different because 2dp rounding happens to
  // straddle the boundary between them. A judge reading that line sees us
  // contradict ourselves in the space of six words, on the beat whose whole
  // job is admitting how little the fix bought.
  line.hidden = false;
  line.innerHTML = measurable
    ? `critical distance <b>${b.before_pct.toFixed(2)}%</b> → <b>${b.after_pct.toFixed(2)}%</b>` +
      ` · moves it ${b.delta_pct >= 0 ? "+" : ""}${b.delta_pct.toFixed(2)}pp` + tail
    : `critical distance <b>${b.before_pct.toFixed(2)}%</b> · <b>no measurable change</b>` +
      ` <em>(search resolves to ±${b.resolution_pct.toFixed(3)}pp)</em>` + tail;
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

const split = { before: null, after: null, layout: null, timers: [], frame: 0 };

function clearSplit() {
  stopAnimations();
  showBought(null);
  split.before = split.after = split.layout = null;
  split.frame = 0;
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
    split.frame = t;
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

/* Where a value sits on a swept axis, as a fractional cell index.
   The overlap axis is measured, not constructed: each column is a blend step
   and the axis records the mean cosine similarity that step produced, which
   is steeply nonlinear — 0.00, 0.04, 0.10, 0.18, 0.30, 0.46, 0.63, 0.72,
   0.74, 0.79 … Half the range is spent in the last three columns. The cells
   are still drawn one per column, so interpolating between the two END
   values put the real book four columns right of its own data: the marker
   sat on a pale 1.19× cell while the cascade a screen earlier had reported
   1.87×, and the dot landed in the blue band instead of the red one. Walk
   the array rather than assume it is evenly spaced. */
function axisIndex(values, v) {
  const n = values.length;
  for (let k = 0; k < n - 1; k++) {
    const a = values[k], c = values[k + 1];
    if ((v >= a && v <= c) || (v <= a && v >= c)) {
      return a === c ? k : k + (v - a) / (c - a);
    }
  }
  // outside the swept range — /api/boundary takes `here.leverage` straight
  // off the query string, so a URL can ask for a point this grid never
  // covered. Pin to the edge; the callout still prints the real value.
  return Math.abs(v - values[0]) <= Math.abs(v - values[n - 1]) ? 0 : n - 1;
}

// cells are drawn from their top-left corner, so a value belongs at the
// CENTRE of its cell. Axis labels use these too — one mapping, or the ticks
// and the marker disagree about where the same number lives.
const cellX = (L, cw, col) => L + (col + 0.5) * cw;
const cellY = (T, ch, rows, row) => T + (rows - 1 - row + 0.5) * ch;

/* The band the sweep actually ran at. /api/boundary used to send it twice —
   once bare and once inside `params` — and this caption read the bare copy,
   the one with no record of whether the value had been clamped on the way in.
   `params` is what every other endpoint speaks. */
const bandOf = (b) => (b.params && b.params.band != null ? b.params.band : 1.05);

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

  // Marching squares at the amplification threshold. The plan specified a
  // critical contour and the script says "the critical contour draws" — what
  // actually rendered was five shaded bands, so the eye read the white-to-red
  // STEP as the edge. A presenter describing a line over a heatmap with no
  // line in it is describing a different product.
  const ISO = 1.5;
  const colX = (c) => L + (c + 0.5) * cw;
  const rowY = (r) => T + (b.rows - 1 - r + 0.5) * ch;
  for (let r = 0; r < b.rows - 1; r++) {
    for (let c = 0; c < b.cols - 1; c++) {
      const v = [b.grid[r][c], b.grid[r][c + 1], b.grid[r + 1][c + 1], b.grid[r + 1][c]];
      const q = [[colX(c), rowY(r)], [colX(c + 1), rowY(r)],
                 [colX(c + 1), rowY(r + 1)], [colX(c), rowY(r + 1)]];
      const cross = [];
      for (let k = 0; k < 4; k++) {
        const a = v[k], d = v[(k + 1) % 4];
        if ((a < ISO) === (d < ISO)) continue;
        const t = (ISO - a) / (d - a);
        const pa = q[k], pb = q[(k + 1) % 4];
        cross.push([pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1])]);
      }
      for (let k = 0; k + 1 < cross.length; k += 2) {
        svg.appendChild(el("line", {
          x1: cross[k][0].toFixed(1), y1: cross[k][1].toFixed(1),
          x2: cross[k + 1][0].toFixed(1), y2: cross[k + 1][1].toFixed(1),
          stroke: "var(--ink-0)", "stroke-width": 1.6, "stroke-linecap": "round",
        }));
      }
    }
  }

  const lo = b.leverage_axis[0], hi = b.leverage_axis[b.rows - 1];
  const omin = b.overlap_axis[0], omax = b.overlap_axis[b.cols - 1];
  const mx = cellX(L, cw, axisIndex(b.overlap_axis, b.here.overlap));
  const my = cellY(T, ch, b.rows, axisIndex(b.leverage_axis, b.here.leverage));
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

  label(L - 10, cellY(T, ch, b.rows, 0) + 4, lo.toFixed(1), { anchor: "end" });
  label(L - 10, cellY(T, ch, b.rows, b.rows - 1) + 4, hi.toFixed(1), { anchor: "end" });
  label(cellX(L, cw, 0), B + 20, omin.toFixed(2));
  label(cellX(L, cw, b.cols - 1), B + 20, omax.toFixed(2));
  // two end ticks on a nonlinear axis read as a linear one. The middle
  // column is at overlap ~0.72, not ~0.50 — show it, or the eye reads the
  // marker's horizontal position as a share of the range.
  const midCol = Math.floor((b.cols - 1) / 2);
  label(cellX(L, cw, midCol), B + 20, b.overlap_axis[midCol].toFixed(2));
  label((L + R) / 2, B + 38, "PORTFOLIO OVERLAP →", { ls: "1.4" });
  const yl = el("text", {
    "font-family": "var(--mono)", "font-size": 11, fill: "var(--ink-2)",
    "text-anchor": "middle", "letter-spacing": "1.4",
  }, "GROSS LEVERAGE →");
  yl.setAttribute("transform", `translate(24,${(T + B) / 2}) rotate(-90)`);
  svg.appendChild(yl);

  label(R - 6, T - 10,
    `amplification · contour at ${ISO.toFixed(1)}× · ${b.reference_kind} ` +
    `${Math.abs(b.reference_shock * 100).toFixed(0)}% reference · band ${bandOf(b).toFixed(2)}`,
    { anchor: "end", size: 10 });
}

/* ─────────────────────── assumptions, from live data ───────────────────── */

/* The credibility argument is "holdings are real, everything else is
   declared, here is the list". Asserting the first half on screen while the
   second half lived only in a doc was the weaker half of an honest claim —
   and the panel existed before I rebuilt the UI and got dropped in the
   rewrite without anyone noticing for six hours. */
/* Where the breach-band sensitivity pair was actually measured. Every entry
   has to match before the panel is allowed to say "At these settings" — the
   previous version listed two of the three and quoted the pair at every
   gamma. Add a knob to the model and it belongs here too. */
const MEASURED_AT = [
  [(p, lev) => lev, 5.0],
  [(p) => Number((p.gamma == null ? 0.2 : p.gamma).toFixed(2)), 0.2],
  [(p) => Number(p.breaches), 3],
];

function fillAssumptions(data, run) {
  const p = (run && run.params) || {};
  const lev = p.leverage == null ? 5 : p.leverage;
  const adv = data.tickers
    .map((t, i) => `${t} $${(data.adv[i] / 1e9).toFixed(1)}B`).join(" \u00b7 ");
  const gross = data.holdings.reduce((a, row) => a + row.reduce((x, y) => x + y, 0), 0);
  // 06-30-2026 is the filing's own spelling; a period is an ISO date everywhere
  // else in this product and a judge reads it as a date, not a filename
  const period = String(data.quarter || "")
    .replace(/^(\d{2})-(\d{2})-(\d{4})$/, "$3-$1-$2") || data.quarter;

  const rows = [
    ["measured", "Holdings", `Real, and the only thing here that is. <b>${data.source}</b>, ` +
      `period <b>${period}</b>, ${data.funds.length} managers across ${data.tickers.length} names, ` +
      `<b>$${(gross / 1e9).toFixed(1)}B</b> gross notional. Anyone can reproduce it from EDGAR.`],
    ["declared", "Leverage", `No fund discloses it. It is the slider, applied uniformly at ` +
      `<b>${lev.toFixed(1)}\u00d7</b>, and every number on screen moves when it changes.`],
    // The sensitivity pair is a MEASUREMENT, taken at leverage 5.0, gamma 0.20
    // and the >=3 condition. Quoted unconditionally it drifted badly — at
    // leverage 3.0 the real pair is -4.59% / -57.12%, against the -1.73% /
    // -27.33% printed — so it was gated. The gate then checked leverage and
    // the breach count and forgot gamma, which is the third knob it was
    // measured at, so at gamma 1.00 the panel said "At these settings" over
    // -1.73% / -27.33% when the truth is -1.43% / -17.25% and the 1.02 answer
    // is a different name entirely (AMZN, not NVDA). Two rows below, the same
    // panel prints gamma to 2dp. It contradicted itself on one screen.
    //
    // MEASURED_AT is the whole point: a measurement is only quotable at the
    // settings it was taken at, and "the settings" means all of them.
    ["declared", "Breach band", `<b>${(p.band == null ? 1.05 : p.band).toFixed(2)}</b> \u2014 how far over ` +
      `target a fund runs before it is forced to sell. This swings the headline harder than ` +
      `leverage or impact.` +
      (MEASURED_AT.every(([read, want]) => read(p, lev) === want)
        ? ` At these settings, 1.02 gives \u22121.73% and 1.30 gives \u221227.33%.`
        : ` The pair we measured \u2014 1.02 \u2192 \u22121.73%, 1.30 \u2192 \u221227.33% \u2014 was taken at ` +
          `leverage 5.0, \u03b3 0.20 and \u22653 breaching, and does not describe the current settings.`)],
    ["declared", "Price impact", `A model, not a measurement. <code>\u0394p/p = \u2212\u03b3 \u00b7 (dollars sold) / ADV</code>, ` +
      `linear in participation, \u03b3 = <b>${(p.gamma == null ? 0.2 : p.gamma).toFixed(2)}</b>. ` +
      `At \u03b3=0 there is no contagion and amplification is exactly 1.00 \u2014 that is the control.`],
    // The multi-class clause is here because a reviewer read GOOGL's figure as
    // Class A and concluded our liquidity was understated 1.9x. It is the
    // combined figure — the column sums four Alphabet lines, so the ADV has
    // to cover all four — but nothing on screen said so, which is exactly
    // what makes a fair question land as a caught error.
    ["declared", "ADV", `Order-of-magnitude daily dollar volume. ${adv} ` +
      `GOOGL's column sums Class A, Class C and two depositary-share lines, and its ` +
      `figure is Alphabet's combined volume across them.`],
    ["limit", "What 13F omits", `Long-only US equity, quarterly, filed 45 days late. Options and ` +
      `bond-principal rows are filtered out. Shorts, derivatives and non-US holdings are invisible to us.`],
    ["declared", "Scale", `$${(gross / 1e9).toFixed(1)}B across these names at ${lev.toFixed(1)}\u00d7 implies ` +
      `~$${(gross / lev / 1e9).toFixed(1)}B of system equity, against firms holding far more. ` +
      `<b>The mechanism transfers; the magnitude does not.</b>`],
    ["limit", "Not a prediction", `This computes a stability property of a declared configuration. ` +
      `The shock shown is the smallest the search found under these assumptions \u2014 ` +
      `<b>not a proven threshold.</b>`],
  ];

  $("assumeBody").innerHTML = rows.map(([kind, term, body]) =>
    `<div><dt data-kind="${kind}">${kind} \u00b7 ${term}</dt><dd>${body}</dd></div>`).join("");
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
  // before drawing — is a trap: if the font is slow, NOTHING draws. I shipped
  // that version once and it rendered an empty stage. So draw immediately and
  // let watchStage() correct it. (The fonts are self-hosted now, so this is
  // fast and offline-safe, but the rule stands: never block first paint on a
  // resource you don't control the timing of.)
  watchStage();
  // Provenance for the assumptions panel. Deliberately NOT awaited: awaiting
  // it pushed a whole round trip in front of first paint and every downstream
  // timing shifted with it. Nothing on the stage needs it, so let it land
  // whenever it lands and fill the panel then.
  api("/api/dataset")
    .then(({ body }) => {
      state.dataset = body;
      if (state.run) fillAssumptions(body, state.run);
    })
    .catch(() => { /* panel stays empty; the demo doesn't depend on it */ });
  await attack();
}

/* The slider cannot be id="band": the metrics band already owns that id, and
   getElementById returns the first match in document order — the rail comes
   before the strip, so every paintBand() wrote its five cells into a range
   input and the real band sat on its placeholder dashes for the whole run.
   Two elements, two ids. */
["leverage", "gamma", "breachBand"].forEach((id) =>
  $(id).addEventListener("input", (e) => {
    $(id + "Val").textContent =
      id === "leverage" ? Number(e.target.value).toFixed(1) : Number(e.target.value).toFixed(2);
    checkKnobs();
  })
);
$("breaches").addEventListener("change", checkKnobs);
$("attackBtn").addEventListener("click", attack);
$("replayBtn").addEventListener("click", () => {
  claimStage();          // a sweep still in the air must not steal this back
  if (state.beat === "split" && split.before) return playSplit();
  if (state.run) { showScene("network"); playCascade(); }
});
$("boundaryBtn").addEventListener("click", boundary);
$("assumeBtn").addEventListener("click", () => { $("assumePanel").hidden = false; });
$("assumeClose").addEventListener("click", () => { $("assumePanel").hidden = true; });
$("assumePanel").addEventListener("click", (e) => {
  if (e.target === $("assumePanel")) $("assumePanel").hidden = true;
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $("assumePanel").hidden = true;
});
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
    // whatever round the split is on, not its last — a reflow used to
    // give away the ending and then let the animation rewind into it
    const half = measure($("netBefore"));
    split.layout = computeLayout(split.before, half.width, half.height);
    splitFrame("before", $("netBefore"), split.frame);
    splitFrame("after", $("netAfter"), split.frame);
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
