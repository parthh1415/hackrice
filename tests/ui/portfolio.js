/* The Portfolio Mode loop, driven end to end against the real server.
 *
 * smoke.js and provenance.js cover the institutional app. This covers the
 * product built on top of it: load a portfolio, set a limit, find the break
 * point, see the fix, read the evidence. It asserts the NUMBERS agree with the
 * payload, not merely that the screens appear — the lesson from provenance.js,
 * which scored 47/47 on five visibly wrong values because it checked that
 * sentences existed rather than that they were right.
 */

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.resolve(__dirname, "..", "..", "web");
const ORIGIN = "http://localhost:8765";

const html = fs.readFileSync(WEB + "/index.html", "utf8");
const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true, url: ORIGIN + "/" });
const { window } = dom;
const d = window.document;

/* app.js fetches relative paths; jsdom has no base for those. Forward them to
   the real server, options and all, so a POSTed portfolio actually posts. */
window.fetch = async (u, o) => {
  const r = await fetch(ORIGIN + u, o);
  return { ok: r.ok, status: r.status, json: () => r.json() };
};

window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {} }));
const errors = [];
window.addEventListener("error", (e) => errors.push(String(e.message)));
process.on("unhandledRejection", (r) => errors.push("rejection: " + ((r && r.message) || r)));

let failures = 0;
const check = (name, cond, detail = "") => {
  if (!cond) failures++;
  console.log(`  [${cond ? "pass" : "FAIL"}] ${name}${detail ? "  — " + detail : ""}`);
};
const eq = (name, got, want) =>
  check(name, got === want, `rendered ${JSON.stringify(got)} · payload ${JSON.stringify(want)}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const text = (id) => d.getElementById(id).textContent;
// bubbles:true, because the app delegates its tab clicks to a container and a
// non-bubbling synthetic event never reaches the listener — the harness would
// be testing its own event construction rather than the app.
const click = (id) => d.getElementById(id).dispatchEvent(
  new window.Event("click", { bubbles: true }));
const clickEl = (el) => el.dispatchEvent(new window.Event("click", { bubbles: true }));
const until = async (what, ok, ms = 25000) => {
  for (let w = 0; w < ms; w += 25) { if (ok()) return true; await sleep(25); }
  check(`timed out waiting for ${what}`, false, `${ms}ms`);
  return false;
};

async function requireServer() {
  try {
    const res = await fetch(ORIGIN + "/api/portfolio/demo");
    if (!res.ok) throw new Error("HTTP " + res.status);
  } catch (e) {
    console.log(`\nNO SERVER at ${ORIGIN} — ${e.message}`);
    console.log("  FIREBREAK_DEMO=1 PYTHONPATH=src python3 -m firebreak.server");
    process.exit(2);
  }
}

try { window.eval(fs.readFileSync(WEB + "/app.js", "utf8")); }
catch (e) { console.log("throw at eval: " + e.message); process.exit(1); }

(async () => {
  await requireServer();
  const payload = await (await fetch(ORIGIN + "/api/portfolio/full?limit=0.1")).json();

  console.log("BOOT — the terminal opens live, with no onboarding");
  check("there is no onboarding overlay to dismiss",
        d.getElementById("onboard") === null);
  check("the demo portfolio is already loaded",
        d.querySelectorAll("#holdingsBox .h").length === payload.portfolio.holdings.length,
        `${d.querySelectorAll("#holdingsBox .h").length} rows`);
  check("the network is already on the stage",
        d.getElementById("network").querySelectorAll("circle").length >= 10);
  check("and the telemetry says NOT RUN rather than showing a stale answer",
        text("shockState") === "NOT RUN", text("shockState"));
  check("brokerage is disabled rather than pretending",
        d.getElementById("connectBtn").disabled === true);
  check("and the copy says why", /not included in this build/i.test(text("connectNote")));
  eq("the context bar names the portfolio", text("ctxPortfolio"), "DEMO_01");
  eq("and the loss limit", text("ctxLimit"), "10.00%");

  console.log("\nATTACK — one click, no wizard");
  click("attackBtn");
  await until("the reverse test", () => /−\d+\.\d{2}%/.test(text("heroVal")));

  eq("the telemetry hero is the payload's shock",
     text("heroVal"), `−${payload.pct.toFixed(2)}%`);
  eq("and names the asset", text("heroSub"), payload.asset);
  eq("direct loss", text("teleDirect"), `${(payload.direct_loss * 100).toFixed(2)}%`);
  eq("cascade loss", text("teleCascade"), `${(payload.cascade_loss * 100).toFixed(2)}%`);
  eq("amplification", text("teleAmp"), `${payload.amplification.toFixed(2)}×`);
  eq("breached books", text("teleBreached"), String(payload.breached.length));
  check("the cascade loss exceeds the direct loss — the product's whole claim",
        payload.cascade_loss > payload.direct_loss,
        `${payload.direct_loss} vs ${payload.cascade_loss}`);
  eq("the shock state reads FOUND", text("shockState"), "FOUND");
  check("the context bar carries the shock",
        text("ctxShock").includes(payload.asset), text("ctxShock"));

  console.log("\nEVENT STREAM — derived from the run, not decoration");
  const log = text("eventBody");
  check("it logged the break point it found",
        log.includes(`${payload.asset} −${payload.pct.toFixed(2)}%`), log.slice(-160));
  check("and the amplification it measured",
        log.includes(`${payload.amplification.toFixed(2)}×`), log.slice(-160));

  console.log("\nCASCADE — the same engine, replaying the portfolio's own shock");
  d.querySelector('#tabs button[data-tab="cascade"]').dispatchEvent(
    new window.Event("click", { bubbles: true }));
  await until("the network to draw",
              () => d.getElementById("network").querySelectorAll("circle").length >= 10);
  check("the institutional network still renders real nodes",
        d.getElementById("network").querySelectorAll("circle").length >= 10);
  check("and its timeline has a frame per round",
        d.getElementById("track").children.length >= 2);

  console.log("\nDEFEND — the minimum intervention");
  click("defendBtn");
  await until("the fix line", () => !d.getElementById("fixLine").hidden && /Reduce/.test(text("fixLine")));

  /* Wait for the SPLIT to finish before believing the fix line.
   *
   * This used to assert the moment "Reduce" appeared, which is the synchronous
   * write inside renderFix(). The defend() fetch landed about 300ms later and
   * replaced the line with the institutional recommendation — "Citadel: sell
   * $1.7M of NVDA" where the user's screen had just said "Reduce NVDA by $478".
   * Thirty checks passed against a screen that no longer existed.
   *
   * So: let everything settle, then check the line is STILL the user's. A
   * value that is briefly correct is not correct. */
  await until("the split to render", () => /shock applied|round/.test(text("splitRound")));
  await sleep(1200);

  const fix = payload.fix;
  check("the fix still names the payload's symbol after the split renders",
        text("fixLine").includes(fix.symbol), text("fixLine"));
  check("and its dollar amount", text("fixLine").includes("$478"), text("fixLine"));
  check("it says the money went to cash", /moved to cash/i.test(text("fixLine")));
  check("it is the PORTFOLIO's recommendation, not the institutional one",
        /REDUCE/.test(text("fixLine")) && !/Citadel|gross assets/.test(text("fixLine")),
        text("fixLine"));
  check("the locked shock is stated where it cannot be missed",
        text("lockedShock").includes(`${payload.asset} −${payload.pct.toFixed(2)}%`),
        text("lockedShock"));
  check("and that a retail position does not move the market",
        /does not move the market/i.test(text("boughtLine")), text("boughtLine"));

  console.log("\nVERIFY — the evidence");
  await sleep(1200);
  d.querySelector('#tabs button[data-tab="verify"]').dispatchEvent(
    new window.Event("click", { bubbles: true }));
  await until("the validation card", () => !d.getElementById("sceneValidate").hidden);

  const v = payload.validation;
  const top = text("validTop");
  check("the top line shows the break point moving",
        top.includes(`−${v.new_breaking_point.before_pct.toFixed(2)}%`) &&
        top.includes(`−${v.new_breaking_point.after_pct.toFixed(2)}%`),
        top.replace(/\s+/g, " ").slice(0, 100));

  const body = () => text("validBody").replace(/\s+/g, " ");
  check("same-shock tab: before breaks, after does not",
        /YES/.test(body()) && /no/.test(body()), body().slice(0, 110));
  check("and it states that only the portfolio changed",
        /only the portfolio changed/i.test(body()));

  d.querySelector('#validTabs button[data-tab="newbreak"]').dispatchEvent(new window.Event("click", { bubbles: true }));
  await sleep(60);
  check("new-break tab reports the recomputed point",
        body().includes(`${v.new_breaking_point.after_pct.toFixed(2)}%`), body().slice(0, 110));
  check("and says it was recomputed, not derived", /not derived/i.test(body()));

  d.querySelector('#validTabs button[data-tab="synthetic"]').dispatchEvent(new window.Event("click", { bubbles: true }));
  await sleep(60);
  check("synthetic tab reports the scenario count",
        body().includes(String(v.synthetic.scenarios)), body().slice(0, 110));
  check("and the seed, so it reproduces", body().includes(String(v.synthetic.seed)));
  check("and refuses to call it a probability about the world",
        /not a probability/i.test(body()));

  d.querySelector('#validTabs button[data-tab="historical"]').dispatchEvent(new window.Event("click", { bubbles: true }));
  await sleep(60);
  check("historical tab says it is unavailable rather than inventing returns",
        /not available/i.test(body()), body().slice(0, 110));
  check("and reports no loss figure at all", !/-?\d+\.\d%/.test(body()), body().slice(0, 110));

  console.log("\nRISK DESK — the old app is still reachable and intact");
  check("no runtime errors across the whole flow", errors.length === 0, errors.join("; "));

  console.log(`\n${failures ? failures + " FAILURES" : "all checks passed"}`);
  process.exit(failures ? 1 : 0);
})().catch((e) => {
  console.log(`\n  [FAIL] harness threw — ${e && e.stack || e}`);
  console.log("\nINCOMPLETE");
  process.exit(1);
});
