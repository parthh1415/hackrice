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
const mult = (x) => `${x.toFixed(2)}×`;

const band = () => [...d.querySelectorAll("#band .v")].map((e) => e.textContent);
/* The round label reads "round t / n" at the end of every round, not only the
   last one, so waiting on that shape samples the band mid-cascade. Wait for
   the round that equals the total. */
const settled = async () => {
  for (let i = 0; i < 900; i++) {
    const m = text("roundLabel").match(/^round (\d+) \/ (\d+)$/);
    if (m && m[1] === m[2]) return;
    await sleep(50);
  }
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
  d.getElementById("attackBtn").dispatchEvent(new window.Event("click"));
  await sleep(1200);
  await settled();

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
  check("defaulted funds read INSOLVENT rather than a stale multiple",
        run.defaulted.every((j) => last.leverage[j] === null),
        `defaulted ${JSON.stringify(run.defaulted)}`);
  return run;
}

(async () => {
  await sleep(1000);
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
  d.getElementById("attackBtn").dispatchEvent(new window.Event("click"));
  await sleep(1200);
  await settled();

  console.log("\nBOUNDARY — the marker must sit on its own data");
  d.getElementById("boundaryBtn").dispatchEvent(new window.Event("click"));
  await sleep(12000);
  const b = await api(`/api/boundary?leverage=5&gamma=0.2`);
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
     fixed −5% single-name reference shock, the run uses the critical one.) */
  const cellAmp = b.grid[row][col];
  check("amplification under the marker agrees with the run",
        Math.abs(cellAmp - m.amplification) < 0.25,
        `map cell ${cellAmp.toFixed(2)}× vs run ${m.amplification.toFixed(2)}×`);

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
  const bband = b.params && b.params.band != null ? b.params.band : 1.05;
  check("caption's breach band is the payload's",
        caption.includes(`band ${bband.toFixed(2)}`), caption);
  eq("solver readout cell count", text("solverStats").replace(/\s+/g, " ").trim().split(" ")[1],
     String(b.rows * b.cols));

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
  eq("fix reduction", text("fixLine").match(/exposure (\d+)%/)[1], (fx.reduction * 100).toFixed(0));
  eq("fix cost", text("fixLine").match(/costs ([\d.]+%)/)[1], pct2(fx.cost));
  check("fix names the payload's fund and asset",
        text("fixLine").startsWith(`${fx.fund}: cut ${fx.asset} `), text("fixLine"));

  console.log("\nPRECISION — stated decimals, and no borrowed rounding");
  const bd = band();   // still the demo cascade's; the split has its own footers
  check("amplification is 2dp everywhere", /^\d+\.\d{2}×$/.test(bd[2]) &&
        /amp \d+\.\d{2}×$/.test(text("footBefore")) && /amp \d+\.\d{2}×$/.test(text("footAfter")),
        `${bd[2]} / ${text("footBefore")} / ${text("footAfter")}`);
  check("losses are 1dp everywhere", /^\d+\.\d%$/.test(bd[0]) && /^\d+\.\d%$/.test(bd[1]) &&
        /^\d+\.\d% loss/.test(text("footBefore")) && /^\d+\.\d% loss/.test(text("footAfter")),
        `${bd[0]} ${bd[1]} / ${text("footBefore")} / ${text("footAfter")}`);
  check("cost is 2dp", /costs \d+\.\d{2}% of gross assets/.test(text("fixLine")), text("fixLine"));
  /* The reduction grid is 1/20ths, so 0dp is exact rather than rounded —
     if that ever stops being true, 0dp starts hiding a real difference. */
  check("reduction lands exactly on the solver's 5% grid",
        Math.abs(fx.reduction * 20 - Math.round(fx.reduction * 20)) < 1e-9, String(fx.reduction));

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
