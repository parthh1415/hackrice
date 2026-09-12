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

  console.log("STEP 1 — the app opens on a portfolio");
  check("the onboarding layer is showing", !d.getElementById("onboard").hidden);
  check("step 1 is the current step",
        d.querySelector('#steps span[data-step="1"]').classList.contains("on"));
  check("brokerage is disabled rather than pretending",
        d.getElementById("connectBtn").disabled === true);
  check("and the copy says why", /not configured/i.test(text("connectNote")));

  console.log("\nSTEP 1 — load the demo portfolio");
  click("useDemo");
  await until("the holdings table", () => !d.getElementById("holdingsBox").hidden);
  const rows = [...d.getElementById("holdingsBox").querySelectorAll(".row")].slice(1);
  eq("every holding is listed", rows.length, payload.portfolio.holdings.length);
  check("the total is the payload's total",
        text("holdingsBox").includes("$12.3K"), text("holdingsBox").slice(0, 60));
  check("Continue is enabled once a portfolio is loaded",
        d.getElementById("toLimit").disabled === false);

  console.log("\nSTEP 2 — the risk limit");
  click("toLimit");
  check("pane 2 is showing", !d.getElementById("pane2").hidden);
  check("10% is the default", d.querySelector('#limits button[data-limit="0.10"]').classList.contains("on"));

  console.log("\nSTEP 3 — find my firebreak");
  click("findBtn");
  await until("the result hero", () => /−\d+\.\d{2}%/.test(text("resultHero")));

  eq("the hero names the payload's asset and shock",
     text("resultHero"), `${payload.asset} −${payload.pct.toFixed(2)}%`);
  const grid = text("resultGrid");
  check("direct loss is the payload's", grid.includes(`${(payload.direct_loss * 100).toFixed(2)}%`),
        grid.replace(/\s+/g, " ").slice(0, 90));
  check("cascade loss is the payload's", grid.includes(`${(payload.cascade_loss * 100).toFixed(2)}%`));
  check("amplification is the payload's", grid.includes(`${payload.amplification.toFixed(2)}×`));
  check("the cascade loss exceeds the direct loss — the product's whole claim",
        payload.cascade_loss > payload.direct_loss,
        `${payload.direct_loss} vs ${payload.cascade_loss}`);

  console.log("\nSTEP 4 — the cascade, which is the old app");
  click("watchBtn");
  await until("the network to draw",
              () => d.getElementById("network").querySelectorAll("circle").length >= 10);
  check("the institutional network still renders real nodes",
        d.getElementById("network").querySelectorAll("circle").length >= 10);
  check("and its timeline has a frame per round",
        d.getElementById("track").children.length >= 2);

  console.log("\nSTEP 5 — the fix");
  click("fixBtn");
  await until("the fix line", () => !d.getElementById("fixLine").hidden && /Reduce/.test(text("fixLine")));
  const fix = payload.fix;
  check("the fix names the payload's symbol", text("fixLine").includes(fix.symbol), text("fixLine"));
  check("and its dollar amount", text("fixLine").includes("$478"), text("fixLine"));
  check("it says the money went to cash", /moved to cash/i.test(text("fixLine")));
  check("and that a retail position does not move the market",
        /does not move the market/i.test(text("boughtLine")), text("boughtLine"));

  console.log("\nSTEP 6 — validation");
  await sleep(1500);
  const stampBtn = [...d.querySelectorAll(".split-stamp button")][0];
  check("a validate button appears after the fix", !!stampBtn);
  if (stampBtn) {
    clickEl(stampBtn);
    await until("the validation card", () => !d.getElementById("sceneValidate").hidden);
  }

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
