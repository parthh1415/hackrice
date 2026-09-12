/* Provenance harness: every number on screen, checked against the payload.
 *
 * smoke.js asserts the app builds a sane DOM. This one asserts the DOM says
 * what the engine said. Different job: a frontend that derives a number
 * instead of reading it will pass every shape check in smoke.js and still
 * put a figure on stage that the API never produced.
 *
 * Everything here is compared programmatically against a second, independent
 * fetch of the same endpoint — never against a constant copied out of a doc.
 *
 * Needs a server up — it fetches the real endpoints off ORIGIN below.
 *
 *   npm --prefix tests/ui install                     # once
 *   PYTHONPATH=src python3 -m firebreak.server &      # or FIREBREAK_DEMO=1
 *   node tests/ui/provenance.js
 */
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
// off __dirname, not off an absolute path into one laptop's home directory.
// hardcoded, this harness read whatever that machine happened to have in
// web/ — so on a fresh clone it tested someone else's working tree, or
// nothing at all.
const WEB = path.resolve(__dirname, "..", "..", "web");
const ORIGIN = "http://localhost:8765";

const BOX = { stage: [1154, 610], network: [1154, 610],
              netBefore: [570, 540], netAfter: [570, 540], boundary: [1154, 610] };

const html = fs.readFileSync(WEB + "/index.html", "utf8")
  .replace(/<link[^>]*fonts\.googleapis[^>]*>/g, "");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: ORIGIN + "/" });
const { window } = dom;
const d = window.document;

window.Element.prototype.getBoundingClientRect = function () {
  const b = BOX[this.id] || BOX[this.parentElement && this.parentElement.id] || [1154, 610];
  return { width: b[0], height: b[1], top: 0, left: 0, right: b[0], bottom: b[1], x: 0, y: 0 };
};
window.Element.prototype.animate = () => ({ finished: Promise.resolve() });
window.ResizeObserver = class { observe() {} disconnect() {} };
window.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
window.fetch = async (u, o) => {
  const r = await fetch(ORIGIN + u, o);
  return { ok: r.ok, status: r.status, json: () => r.json() };
};

const errors = [];
window.onerror = (m) => errors.push("onerror: " + m);
process.on("unhandledRejection", (r) => errors.push("rejection: " + ((r && r.message) || r)));

try { window.eval(fs.readFileSync(WEB + "/app.js", "utf8")); }
catch (e) { errors.push("throw at eval: " + e.message); }

let failures = 0;
const check = (name, cond, detail = "") => {
  if (!cond) failures++;
  console.log(`  [${cond ? "pass" : "FAIL"}] ${name}${detail ? "  — " + detail : ""}`);
};
const eq = (name, got, want) => check(name, got === want, `rendered ${JSON.stringify(got)} · payload ${JSON.stringify(want)}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const text = (id) => d.getElementById(id).textContent;
const svg = (id) => d.getElementById(id);
const api = (p) => fetch(ORIGIN + p).then((r) => r.json());
const texts = (id) => [...svg(id).querySelectorAll("text")].map((t) => t.textContent);

// the frontend's own formatters, restated so a change to either side shows up
const pct1 = (x) => `${(x * 100).toFixed(1)}%`;
const pct2 = (x) => `${(x * 100).toFixed(2)}%`;
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

/* A regex that stops matching must fail as a failed check, not as a
   TypeError on null. This harness died outright at "exposure (\d+)%" once
   the fix line was reworded — one throw, and every assertion after it went
   unrun. */
const grab = (name, id, re) => {
  const m = text(id).match(re);
  if (!m) { check(name, false, `no match for ${re} in ${JSON.stringify(text(id))}`); return null; }
  return m[1];
};
const mult = (x) => `${x.toFixed(2)}×`;

const band = () => [...d.querySelectorAll("#band .v")].map((e) => e.textContent);
/* The round label reads "round t / n" at the end of every round, not only the
   last one, so waiting on that shape samples the band mid-cascade. Wait for
   the round that equals the total. */
/* Wait for THIS run, not for whatever is still on screen.

   This used to poll only for `round N / N`, which the previous run leaves
   sitting in the label for the whole of the next fetch — so the predicate was
   satisfiable by the state it existed to see replaced. An audit instrumented
   every call: against a slow server all four post-boot waits returned on
   entry with zero polls, and one already did so on a fast machine. Both
   directions of wrong came out of that: the DEFAULTING scenario asserted the
   previous run's DOM against the new run's payload and reported ten app bugs
   that do not exist, while the DEMO scenario's twelve checks all passed
   without observing a single repaint, because the stale state and the
   expected state happened to coincide.

   `state.request` is the app's own generation counter — claimStage()
   increments it, holdsStage() compares against it — so a run that has not
   started cannot satisfy this, and neither can the run before.

   My first attempt polled for the label to pass through "searching", which
   attack() now writes before fetching. That does not work and is worth
   recording: the live endpoints answer in 13-43ms and the poll runs every
   20ms, so the transient is routinely missed and every wait timed out. A
   predicate that depends on CATCHING a state is a race; one that depends on
   a counter having moved is not. */
const generation = () => (window.state ? window.state.request : null);

const settled = async (since = null) => {
  const before = since;
  for (let i = 0; i < 900; i++) {
    const moved = before === null || generation() !== before;
    const m = text("roundLabel").match(/^round (\d+) \/ (\d+)$/);
    if (moved && m && m[1] === m[2]) return;
    await sleep(20);
  }
  check("settled() timed out waiting for a run to finish", false,
        `label "${text("roundLabel")}", generation ${generation()} (was ${before})`);
};

/* Click and wait for the run that click starts. */
const runAttack = async (id = "attackBtn") => {
  const before = generation();
  d.getElementById(id).dispatchEvent(new window.Event("click"));
  await settled(before);
};

const QS = "leverage=5&gamma=0.2&breaches=3";

const setKnob = (id, v) => {
  const e = d.getElementById(id);
  e.value = v;
  e.dispatchEvent(new window.Event("input"));
};

/* Drive the sliders to a scenario, let the cascade finish, then check every
   number the settled stage shows against a second fetch of the same query. */
async function checkRun(label, knobs) {
  const qs = `leverage=${knobs.leverage}&gamma=${knobs.gamma}&breaches=${knobs.breaches}`;
  console.log(`\n${label}  (${qs})`);
  setKnob("leverage", String(knobs.leverage));
  setKnob("gamma", String(knobs.gamma));
  d.getElementById("breaches").value = String(knobs.breaches);
  const _gen = generation();
  d.getElementById("attackBtn").dispatchEvent(new window.Event("click"));
  // The sleep(1200) that used to carry this past the previous run's label is
  // gone: it was a magic number that happened to exceed the fetch time on one
  // machine, not a barrier. The generation counter is the barrier.
  await settled(_gen);

  const run = await api(`/api/break?${qs}`);
  const last = run.trajectory[run.trajectory.length - 1];
  const rounds = run.trajectory.length - 1;
  const m = run.metrics, bd = band();

  eq("hero percentage is payload pct", text("heroVal"), `${run.pct.toFixed(2)}%`);
  check("hero subtitle counts funds from the payload",
        text("heroSub").startsWith(`${run.asset} · ${run.breached.length} of ${run.funds.length} funds`),
        text("heroSub"));
  eq("shock loss", bd[0], pct1(m.shock_loss));
  eq("final loss", bd[1], pct1(m.final_loss));
  eq("amplification", bd[2], mult(m.amplification));
  /* paintBand counts breaches by unioning frames[0..t].breached rather than
     reading run.breached. At the settled frame the two MUST agree or the band
     contradicts the hero subtitle three inches above it. */
  eq("breach count at the settled frame equals run.breached", bd[3], String(run.breached.length));
  eq("round counter equals the engine's round count", bd[4], `${rounds} / ${rounds}`);
  eq("engine's own `rounds` matches the frame count", rounds, run.rounds);

  const netText = texts("network");
  /* drawNetwork renders `1 - frame.prices[i]`, which is only a price drop
     because engine.py normalises prices to 1.0 at t0. Assert the invariant
     rather than trusting the comment. */
  check("every price starts at or below 1.0", last.prices.every((p) => p <= 1 + 1e-12),
        last.prices.filter((p) => p > 1).join(","));
  const wantDrops = last.prices.map((p) => (1 - p > 0.0005 ? `−${((1 - p) * 100).toFixed(2)}%` : "0.00%"));
  check("per-asset drop readouts all present and equal 1 − price",
        wantDrops.every((s) => netText.includes(s)),
        wantDrops.filter((s) => !netText.includes(s)).join(" ") || "ok");
  const wantLev = last.leverage.map((v) => (v === null ? "INSOLVENT" : `L ${v.toFixed(2)}`));
  check("per-fund leverage readouts equal frame.leverage",
        wantLev.every((s) => netText.includes(s)),
        wantLev.filter((s) => !netText.includes(s)).join(" ") || "ok");
  /* The dashed ring is the only thing on the network that says WHICH name was
     shocked. `assetIndex: body.asset_index ?? 0` has a comment in api.py
     admitting the fallback is "correct only when the answer happens to be the
     first name" — and nothing tested it, because at the demo settings the
     answer IS the first name. Hardcoding it to 0 scored 47/47 while ringing
     NVDA on a run whose shocked asset is AMZN. */
  const shocked = [...svg("network").querySelectorAll("circle")]
    .filter((c) => c.getAttribute("stroke-dasharray") === "2 3");
  check("exactly one asset is ringed as the shocked one", shocked.length === 1,
        `${shocked.length} rings`);
  if (shocked.length === 1) {
    const plain = [...svg("network").querySelectorAll("circle")]
      .filter((c) => c.getAttribute("stroke-dasharray") !== "2 3");
    const ringed = plain.reduce((best, c) =>
      Math.abs(+c.getAttribute("cy") - +shocked[0].getAttribute("cy")) <
      Math.abs(+best.getAttribute("cy") - +shocked[0].getAttribute("cy")) ? c : best, plain[0]);
    const labels = [...svg("network").querySelectorAll("text")]
      .filter((t) => run.tickers.includes(t.textContent));
    const named = labels.reduce((best, t) =>
      Math.abs(+t.getAttribute("y") - +ringed.getAttribute("cy")) <
      Math.abs(+best.getAttribute("y") - +ringed.getAttribute("cy")) ? t : best, labels[0]);
    eq("the ring is around the asset the payload says was shocked",
       named.textContent, run.asset);
  }

  check("defaulted funds read INSOLVENT rather than a stale multiple",
        run.defaulted.every((j) => last.leverage[j] === null),
        `defaulted ${JSON.stringify(run.defaulted)}`);
  return run;
}

/* The README has warned about this for weeks: "with no server on 8765 every
   fetch fails and the output is noise, so check the server is up before
   believing a red run." It cost an hour anyway — eight checks failed with a
   hero reading "—", which looks exactly like a rendering regression and is
   not one. A warning in a README is not a check. This is. */
async function requireServer() {
  try {
    const res = await fetch(ORIGIN + "/api/break?asset=NVDA&leverage=5&gamma=0.2&breaches=3");
    if (!res.ok) throw new Error("HTTP " + res.status);
  } catch (e) {
    console.log(`\nNO SERVER at ${ORIGIN} — ${e.message}`);
    console.log("Every check below would fail for that reason alone. Start it with:");
    console.log("  FIREBREAK_DEMO=1 PYTHONPATH=src python3 -m firebreak.server");
    process.exit(2);
  }
}

(async () => {
  await requireServer();
  // Boot. No generation to compare against because nothing here started the
  // run — the app auto-attacks on load — so this one waits on the label
  // alone, which is sound exactly once, before any run exists to go stale.
  await settled();

  const run = await checkRun("DEMO SCENARIO — hero, band, network readouts",
                             { leverage: 5, gamma: 0.2, breaches: 3 });
  const m = run.metrics;

  /* A run where funds actually die: leverage counts go null, the band's
     breach union has to survive funds dropping out of over_limit(), and
     `1 - price` has to stay a price drop when prices hit the floor. */
  const dead = await checkRun("DEFAULTING SCENARIO — every fund insolvent",
                              { leverage: 8, gamma: 1, breaches: 5 });
  check("this scenario really did default funds", dead.defaulted.length > 0,
        `defaulted ${JSON.stringify(dead.defaulted)}`);

  setKnob("leverage", "5"); setKnob("gamma", "0.2");
  d.getElementById("breaches").value = "3";
  const _gen = generation();
  d.getElementById("attackBtn").dispatchEvent(new window.Event("click"));
  // The sleep(1200) that used to carry this past the previous run's label is
  // gone: it was a magic number that happened to exceed the fetch time on one
  // machine, not a barrier. The generation counter is the barrier.
  await settled(_gen);

  console.log("\nBOUNDARY — the marker must sit on its own data");
  /* Deliberately NOT the default band. At 1.05 the caption's old fallback
     (`b.band || 1.05`) printed the right answer by accident, so every check
     here passed while the caption was in fact ignoring the payload. A knob
     is only tested at a setting where being wrong looks different. */
  const BBAND = 1.3;
  const bandSlider = d.getElementById("breachBand");
  bandSlider.value = String(BBAND);
  bandSlider.dispatchEvent(new window.Event("input"));
  await sleep(200);
  d.getElementById("boundaryBtn").dispatchEvent(new window.Event("click"));
  await sleep(12000);
  const b = await api(`/api/boundary?leverage=5&gamma=0.2&band=${BBAND}`);
  check("the boundary ran at the band the slider asked for",
        b.params.band === BBAND, `payload ${b.params.band} vs slider ${BBAND}`);
  const bsvg = svg("boundary");
  const vb = (bsvg.getAttribute("viewBox") || "0 0 0 0").split(" ").map(Number);
  const W = vb[2], H = vb[3];
  const L = 74, R = W - 40, T = 34, Bm = H - 56;
  const cw = (R - L) / b.cols, ch = (Bm - T) / b.rows;
  const ring = [...bsvg.querySelectorAll("circle")].find((c) => c.getAttribute("r") === "7");
  check("you-are-here marker drawn", !!ring);
  const mx = +ring.getAttribute("cx"), my = +ring.getAttribute("cy");
  check("marker is inside the plot box", mx >= L && mx <= R && my >= T && my <= Bm, `${mx},${my}`);

  // which cell did it land on, and does that cell's axis value bracket the
  // real system? this is the whole point of the diagram.
  const col = Math.min(b.cols - 1, Math.max(0, Math.floor((mx - L) / cw)));
  const rowTop = Math.min(b.rows - 1, Math.max(0, Math.floor((my - T) / ch)));
  const row = b.rows - 1 - rowTop;
  const near = (axis, k, v) => {
    const loV = axis[Math.max(0, k - 1)], hiV = axis[Math.min(axis.length - 1, k + 1)];
    return v >= Math.min(loV, hiV) && v <= Math.max(loV, hiV);
  };
  check("marker column brackets the real overlap", near(b.overlap_axis, col, b.here.overlap),
        `col ${col} = overlap ${b.overlap_axis[col]}, system is at ${b.here.overlap}`);
  check("marker row brackets the real leverage", near(b.leverage_axis, row, b.here.leverage),
        `row ${row} = leverage ${b.leverage_axis[row]}, system is at ${b.here.leverage}`);
  /* The cell under the dot is the amplification a judge reads off this map.
     It has to be in the same ballpark as the number the cascade just showed,
     or the two screens contradict each other. (Not equal: the map uses a
     fixed −5% single-name reference shock, the run uses the critical one.)

     This is a fair comparison only when the run's critical shock is close to
     the map's reference shock, and that is a property of the settings, not an
     invariant. It was asserted unconditionally and passed for one reason: at
     the default band the critical shock is 5.27% and the reference is 5%, so
     the two land inside the tolerance by coincidence. At band 1.30 the
     critical shock is 27.33% while the map still sweeps at 5% — nothing
     cascades there, so the cell reads 1.00 against a run at 1.43 and the
     check reports a contradiction that is really two different questions.
     Matching the bands does not fix it; that was my first attempt and it
     failed the same way. State the precondition, check it, then compare. */
  const refPct = Math.abs(b.reference_shock * 100);
  const cmpMap = await api(`/api/boundary?leverage=5&gamma=0.2&band=1.05`);
  const cmpRun = await api(`/api/break?leverage=5&gamma=0.2&band=1.05&breaches=3`);
  const nearest = (axis, v) => axis.reduce(
    (bi, x, i) => (Math.abs(x - v) < Math.abs(axis[bi] - v) ? i : bi), 0);
  check("the comparison run's critical shock is near the map's reference shock",
        Math.abs(cmpRun.pct - refPct) < 1.0,
        `critical ${cmpRun.pct.toFixed(2)}% vs reference ${refPct.toFixed(2)}%`);
  const cellAmp = cmpMap.grid[nearest(cmpMap.leverage_axis, cmpMap.here.leverage)]
                            [nearest(cmpMap.overlap_axis, cmpMap.here.overlap)];
  check("amplification under the marker agrees with the run, where the shocks match",
        Math.abs(cellAmp - cmpRun.metrics.amplification) < 0.25,
        `map cell ${cellAmp.toFixed(2)}× vs run ${cmpRun.metrics.amplification.toFixed(2)}× at band 1.05`);

  const btext = texts("boundary");
  check("callout repeats here.leverage and here.overlap",
        btext.includes(`L ${b.here.leverage.toFixed(1)} · overlap ${b.here.overlap.toFixed(2)}`),
        btext.find((t) => t.startsWith("L ")) || "missing");
  check("axis ticks are payload values", btext.includes(b.overlap_axis[0].toFixed(2)) &&
        btext.includes(b.overlap_axis[b.cols - 1].toFixed(2)) &&
        btext.includes(b.leverage_axis[0].toFixed(1)) &&
        btext.includes(b.leverage_axis[b.rows - 1].toFixed(1)));
  /* Exact-matching the whole caption made this a format test, and it broke
     the moment the caption honestly gained the contour level and the breach
     band. What matters is provenance: every number in it comes from the
     payload, not from a literal in the drawing code. */
  const caption = btext.find((t) => t.startsWith("amplification")) || "";
  check("reference shock label is the payload's",
        caption.includes(`${b.reference_kind} ${Math.abs(b.reference_shock * 100).toFixed(0)}% reference`),
        caption || "missing");
  /* No fallback here. This line used to read `b.params.band != null ? ... :
     1.05`, mirroring the drawing code's own `b.band || 1.05` — so when the
     bare `band` field was removed from /api/boundary and the caption silently
     started printing 1.05 at every setting, the check computed 1.05 too and
     passed. A test that applies the same default as the code it checks cannot
     see that default being wrong. The payload must state the band. */
  check("the boundary payload states its breach band",
        b.params && typeof b.params.band === "number",
        JSON.stringify(b.params));
  check("caption's breach band is the payload's",
        caption.includes(`band ${b.params.band.toFixed(2)}`), caption);
  eq("solver readout cell count", text("solverStats").replace(/\s+/g, " ").trim().split(" ")[1],
     String(b.rows * b.cols));

  /* Back to the default before anything downstream. The boundary section
     deliberately runs at 1.30; every section after it fetches its expected
     payload at the default, so leaving the slider moved makes the UI right
     and the expectations wrong — ten failures that all say "the band works". */
  bandSlider.value = "1.05";
  bandSlider.dispatchEvent(new window.Event("input"));
  const _gen0 = generation();
  d.getElementById("attackBtn").dispatchEvent(new window.Event("click"));
  // This was the one attack in the file with no settle discipline in front of
  // it, and the audit caught its settled() returning on entry with zero polls
  // on a fast machine — so defendBtn below was being clicked while this
  // attack was still in flight, and the two raced on claimStage(). Masked
  // only because the stale state it read was the demo state this reset was
  // trying to produce.
  await settled(_gen0);

  console.log("\nSPLIT VIEW — footers and fix line against /api/stabilise");
  d.getElementById("defendBtn").dispatchEvent(new window.Event("click"));
  await sleep(9000);
  const s = await api(`/api/stabilise?${QS}`);
  const foot = (r) => `${pct1(r.metrics.final_loss)} loss · ${r.breached.length} breaches · amp ${r.metrics.amplification.toFixed(2)}×`;
  eq("before footer", text("footBefore"), foot(s.before));
  eq("after footer", text("footAfter"), foot(s.after));
  eq("identical-shock stamp repeats the hero's shock", text("shockStamp"),
     `identical shock · ${s.pct.toFixed(2)}% ${s.asset}`);
  check("stamp and hero quote the same shock", text("shockStamp").includes(run.pct.toFixed(2)),
        `${text("shockStamp")} vs hero ${run.pct.toFixed(2)}%`);
  const fx = s.fix;
  eq("fix sell amount", grab("fix sell amount", "fixLine", /sell (\$[\d.]+[KMBT]?) of/), usd(fx.sell_usd));
  eq("fix reduction", grab("fix reduction", "fixLine", /· ([\d.]+%) of a/), pctSig(fx.reduction));
  eq("fix position size", grab("fix position size", "fixLine", /of a (\$[\d.]+[KMBT]?) position/),
     usd(fx.position_usd));
  eq("fix cost", grab("fix cost", "fixLine", /costs ([\d.]+%)/), pctSig(fx.cost));
  check("fix names the payload's fund and asset",
        text("fixLine").startsWith(`${fx.fund}: sell `) && text("fixLine").includes(` of ${fx.asset} `),
        text("fixLine"));

  /* The numbers must also agree with EACH OTHER, not just with the payload.
     This harness compares the DOM against the payload and stops there, so a
     server sending sell_usd = position * 0.5 passed all 58 checks on a line
     reading "sell $1.2B of NVDA · 0.073% of a $2.4B position" — every field
     faithfully rendered, the sentence arithmetically absurd. Faithfully
     reproducing a wrong number is still showing a wrong number. */
  const gross = s.holdings.reduce((t, row) => t + row.reduce((a, b) => a + b, 0), 0);
  const position = s.holdings[fx.fund_index][fx.asset_index];
  const agrees = (a, b, rel) => Math.abs(a - b) <= Math.abs(b) * rel + 1e-9;
  check("position_usd is the holding it names",
        agrees(fx.position_usd, position, 1e-9), `${fx.position_usd} vs ${position}`);
  check("gross_usd is the sum of the book",
        agrees(fx.gross_usd, gross, 1e-9), `${fx.gross_usd} vs ${gross}`);
  check("sell_usd is that position times that reduction",
        agrees(fx.sell_usd, position * fx.reduction, 1e-9),
        `${fx.sell_usd} vs ${position * fx.reduction}`);
  check("cost and the dollar figures price the same trade",
        agrees(fx.cost, fx.sell_usd / gross, 1e-9),
        `cost ${fx.cost} vs sell/gross ${fx.sell_usd / gross}`);

  /* Three numbers on beat 4 that nothing was reading back. Each renders a
     visibly wrong value under mutation while every other check stays green:
     "round 3 of 4" on a three-round cascade, "999 evals" where the payload
     says 124, and a critical distance three inches from the hero disagreeing
     with it. */
  const rounds = Math.max(s.before.trajectory.length, s.after.trajectory.length) - 1;
  const label = text("splitRound");
  const denom = (label.match(/round \d+ of (\d+)/) || [])[1];
  check("the split's round label counts the rounds the payload has",
        label.includes("shock applied") || Number(denom) === rounds,
        `"${label}" · payload has ${rounds} rounds`);

  const evals = text("solverStats").replace(/\s+/g, " ");
  check("the solver readout states the payload's evaluation count",
        evals.includes(`${s.engine.evaluations} evals`),
        `${evals} · payload ${s.engine.evaluations}`);
  /* The exit flag is the solver's own verdict on whether it converged, and it
     is the difference between "MATLAB found this" and "MATLAB gave up and we
     printed the last thing it held". Rendered right beside the evals count and
     checked by nothing. */
  check("and the solver's own exit flag",
        s.engine.exit_flag === undefined || evals.includes(`exit ${s.engine.exit_flag}`),
        `${evals} · payload exit_flag ${s.engine.exit_flag}`);
  eq("the solver readout names the engine that actually ran",
     text("solverName").trim(), s.engine.name);

  /* The whole bought line against the payload's own bought block, not just
     its opening number. smoke.js regex-matches two phrases out of it and
     nothing reads the rest — and this line is where the product admits how
     little the fix bought, so every figure in it is load-bearing. */
  const bought = text("boughtLine");
  const measurable = s.bought.measurable;
  check("the bought line takes the branch the payload's `measurable` asks for",
        measurable ? /moves it [+-]/.test(bought) : /no measurable change/.test(bought),
        `measurable=${measurable} · ${bought}`);
  if (measurable) {
    eq("and states the payload's delta",
       (bought.match(/moves it ([+-][\d.]+)pp/) || [])[1],
       `${s.bought.delta_pct >= 0 ? "+" : ""}${s.bought.delta_pct.toFixed(2)}`);
  } else {
    eq("and states the payload's own resolution, not a literal",
       (bought.match(/resolves to ±([\d.]+)pp/) || [])[1],
       s.bought.resolution_pct.toFixed(3));
    check("an unmeasurable result shows no arrow between two numbers",
          !bought.includes("→"),
          "an arrow here points from one number to another we just called indistinguishable");
  }

  eq("the bought line opens on the run's OWN critical distance",
     (text("boughtLine").match(/critical distance ([\d.]+)%/) || [])[1],
     s.bought.before_pct.toFixed(2));
  check("and that is the number the hero is showing",
        text("boughtLine").includes(`${run.pct.toFixed(2)}%`), text("boughtLine"));

  console.log("\nPRECISION — stated decimals, and no borrowed rounding");
  const bd = band();   // still the demo cascade's; the split has its own footers
  check("amplification is 2dp everywhere", /^\d+\.\d{2}×$/.test(bd[2]) &&
        /amp \d+\.\d{2}×$/.test(text("footBefore")) && /amp \d+\.\d{2}×$/.test(text("footAfter")),
        `${bd[2]} / ${text("footBefore")} / ${text("footAfter")}`);
  check("losses are 1dp everywhere", /^\d+\.\d%$/.test(bd[0]) && /^\d+\.\d%$/.test(bd[1]) &&
        /^\d+\.\d% loss/.test(text("footBefore")) && /^\d+\.\d% loss/.test(text("footAfter")),
        `${bd[0]} ${bd[1]} / ${text("footBefore")} / ${text("footAfter")}`);
  /* Not 2dp any more. The cost is significant-figure formatted because the
     answer moved three orders of magnitude when the stabiliser started
     bisecting, and a fixed 2dp rendered it as "0.00%". What matters is that
     it carries real digits, not how many places it uses to do it. */
  check("cost renders with real precision, never as zero",
        /costs 0?\.?\d*[1-9]\d*% of gross assets/.test(text("fixLine")), text("fixLine"));
  /* This used to assert the reduction lands exactly on the solver's 5% grid,
     with a comment warning that "if that ever stops being true, 0dp starts
     hiding a real difference". It stopped being true, the 0dp did hide a real
     difference — beat 4 read "cut NVDA exposure 0%" — and this check sat
     behind a crash two hundred lines up, so nobody heard it. Inverted: the
     answer must NOT be quantised to the grid, because resolving the depth is
     the whole point of the search. */
  check("the reduction is not pinned to the solver's 5% grid",
        Math.abs(fx.reduction * 20 - Math.round(fx.reduction * 20)) > 1e-9, String(fx.reduction));
  check("the rendered reduction keeps enough precision to be non-zero",
        /· 0?\.?\d*[1-9]\d*% of a/.test(text("fixLine")), text("fixLine"));

  console.log("\nUNITS — fractions vs percentages");
  check("pct is a percentage, metrics are fractions",
        run.pct > 1 && m.shock_loss < 1 && m.final_loss < 1 && s.fix.cost < 1,
        `pct ${run.pct} · shock_loss ${m.shock_loss} · cost ${s.fix.cost}`);
  check("hero is not double-scaled", Math.abs(parseFloat(text("heroVal")) - run.pct) < 0.005);
  check("adv is in dollars, not millions", run.adv.every((a) => a > 1e6), String(run.adv[0]));

  /* A recording of the nearest settings we have on disk is an answer to a
     different question. The badge has to say which question, or the hero
     number reads as an answer to the sliders the judge is looking at. */
  console.log("\nPROVENANCE — a near-match recording must name its own settings");
  const realFetch = window.fetch;
  const stub = (extra) => {
    window.fetch = async (u, o) => {
      const r = await realFetch(u, o);
      const j = await r.json();
      return { ok: r.ok, status: r.status, json: async () => ({ ...j, ...extra }) };
    };
  };
  const badge = () => [d.getElementById("badge").dataset.mode, text("badgeText")];

  stub({ cached: true, cached_exact: true });
  d.getElementById("attackBtn").dispatchEvent(new window.Event("click"));
  await sleep(4000);
  eq("an exact recording still reads as a plain replay", badge().join("/"), "cached/cached run");

  stub({ cached: true, cached_exact: false, cached_for: { leverage: 6, gamma: 0.2, breaches: 3 } });
  d.getElementById("attackBtn").dispatchEvent(new window.Event("click"));
  await sleep(4000);
  eq("a near-match recording names the settings it was recorded at",
     badge().join("/"), "cached/recording of L 6.0 γ 0.20 ≥3");
  check("the cached label stays inside the live label's width",
        text("badgeText").length <= 30, `${text("badgeText").length}ch`);
  window.fetch = realFetch;

  check("no runtime errors", errors.length === 0, errors.join("; "));
  /* The failure this whole file names in its docstring — a frontend that
     DERIVES a number instead of reading the one the engine sent — and the one
     case it could not see. `mult(m.amplification)` and
     `mult(m.final_loss / m.shock_loss)` render identically, forever, because
     the engine defines amplification as exactly that ratio. Comparing the DOM
     to the payload cannot separate them: both agree by construction.

     So break the construction. Stub the field to something the ratio cannot
     produce and see which one reaches the screen. A UI reading the field
     prints the stub; a UI recomputing it prints the ratio. */
  console.log("\nDERIVED vs READ — the number must come off the payload");
  window.fetch = async (u, o) => {
    const r = await realFetch(u, o);
    const j = await r.json();
    if (u.includes("/api/break") && j.metrics) {
      j.metrics = { ...j.metrics, amplification: 9.99 };
    }
    return { ok: r.ok, status: r.status, json: async () => j };
  };
  // Poll for the repaint rather than calling settled(): its condition was
  // already satisfied by the previous run, so it returned instantly and the
  // assertion read a stale band. A wait that can be satisfied by the state
  // you are trying to replace is not a wait.
  const before = band()[2];
  d.getElementById("attackBtn").dispatchEvent(new window.Event("click"));
  let shown = before;
  for (let i = 0; i < 120 && shown === before; i++) {
    await sleep(100);
    shown = band()[2];
  }
  window.fetch = realFetch;
  eq("amplification is read from the payload, not recomputed from the losses",
     shown, "9.99×");

  console.log(`\n${failures ? failures + " FAILURES" : "all checks passed"}`);
  process.exit(failures ? 1 : 0);
})().catch((e) => {
  /* An exception in here used to end the run quietly: the async IIFE rejected,
     the rejection handler filed it in `errors` that nothing would go on to
     read, and node exited 0 having printed a section heading and no checks
     under it. A harness that stops early has to say so louder than one that
     fails. */
  console.log(`\n  [FAIL] harness threw before finishing — ${e && e.stack || e}`);
  console.log("\nINCOMPLETE");
  process.exit(1);
});
