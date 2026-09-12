/* Headless smoke test for the frontend.
 *
 * Screen recording is blocked for this terminal and the Chrome extension
 * isn't set up, so nothing here can take a screenshot. This runs the real
 * app.js against the real server in jsdom instead and asserts the DOM it
 * builds — which catches every class of bug except "it looks wrong".
 *
 * Needs a server up — it fetches the real endpoints off ORIGIN below.
 *
 *   npm --prefix tests/ui install                     # once
 *   PYTHONPATH=src python3 -m firebreak.server &      # or FIREBREAK_DEMO=1
 *   node tests/ui/smoke.js
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
let reflow = () => {};
window.ResizeObserver = class { constructor(cb) { reflow = cb; } observe() {} disconnect() {} };
/* rAF hands its callback a DOMHighResTimeStamp — the same clock as
   performance.now(). Feeding it Date.now() instead makes (now - started) a
   number in the trillions, so every performance.now()-based easing reaches
   k=1 on its first frame. countTo() finished instantly under this shim, which
   is why the check below never saw an intermediate step and why a count-up
   that outlived its own run was invisible here for so long. */
window.requestAnimationFrame = (cb) => setTimeout(() => cb(window.performance.now()), 16);
window.fetch = async (u, o) => {
  const r = await fetch(ORIGIN + u, o);
  return { ok: r.ok, status: r.status, json: () => r.json() };
};

const errors = [];
window.addEventListener("error", (e) => errors.push("error: " + e.message));
window.onerror = (m) => errors.push("onerror: " + m);
process.on("unhandledRejection", (r) => errors.push("rejection: " + ((r && r.message) || r)));

try { window.eval(fs.readFileSync(WEB + "/app.js", "utf8")); }
catch (e) { errors.push("throw at eval: " + e.message); }

let failures = 0;
const check = (name, cond, detail = "") => {
  if (!cond) failures++;
  console.log(`  [${cond ? "pass" : "FAIL"}] ${name}${detail ? "  — " + detail : ""}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const svg = (id) => d.getElementById(id);

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
  await sleep(6000);

  console.log("BEAT 1+2 — attack and cascade");
  const net = svg("network");
  const vb = (net.getAttribute("viewBox") || "").split(" ").map(Number);
  check("no runtime errors", errors.length === 0, errors.join("; "));
  check("hero number populated", /^\d+\.\d{2}%$/.test(d.getElementById("heroVal").textContent),
        d.getElementById("heroVal").textContent);
  check("viewBox matches the stage", vb[2] > 1000 && vb[3] > 500, net.getAttribute("viewBox"));
  check("assets drawn", net.querySelectorAll("circle").length >= 10);
  check("edges drawn", net.querySelectorAll("line").length >= 40);
  check("readouts inside the diagram", net.querySelectorAll("text").length >= 30);
  check("timeline has a segment per frame", d.getElementById("track").children.length >= 2);
  check("metrics band filled", [...d.querySelectorAll("#band .v")].every((e) => e.textContent !== "—"));

  const nodesInBounds = [...net.querySelectorAll("circle")].every((c) => {
    const cy = +c.getAttribute("cy"), cx = +c.getAttribute("cx");
    return cy > 0 && cy < vb[3] && cx > 0 && cx < vb[2];
  });
  check("every node inside the viewBox", nodesInBounds);

  console.log("\nSCRUB — timeline");
  d.getElementById("track").children[0].dispatchEvent(new window.Event("click"));
  await sleep(300);
  check("scrub redraws without error", errors.length === 0, errors.join("; "));

  console.log("\nBEAT 3 — boundary");
  d.getElementById("boundaryBtn").dispatchEvent(new window.Event("click"));
  await sleep(9000);
  const b = svg("boundary");
  check("boundary scene visible", !d.getElementById("sceneBoundary").hasAttribute("hidden"));
  check("grid cells drawn", b.querySelectorAll("rect").length > 200,
        b.querySelectorAll("rect").length + " rects");
  check("you-are-here marker", b.textContent.includes("YOU ARE HERE"));

  console.log("\nBEAT 4 — defend");
  d.getElementById("defendBtn").dispatchEvent(new window.Event("click"));
  await sleep(9000);
  check("split scene visible", !d.getElementById("sceneSplit").hasAttribute("hidden"));
  check("before side drawn", svg("netBefore").querySelectorAll("circle").length >= 10);
  check("after side drawn", svg("netAfter").querySelectorAll("circle").length >= 10);
  // Was /cut/i — which passed happily while the line read "cut NVDA exposure
  // 0% · costs 0.00% of gross assets". Grepping for a verb tells you the
  // sentence was built; it tells you nothing about whether the numbers in it
  // survived the formatter. Assert the numbers.
  const fixText = d.getElementById("fixLine").textContent;
  check("fix instruction shown", /sell/i.test(fixText), fixText.trim().slice(0, 90));
  check("it names a dollar amount, not just a fraction", /\$[\d.]+[KMBT]?/.test(fixText),
        (fixText.match(/\$[\d.]+[KMBT]?/g) || []).join(" "));
  check("no number in it has been rounded away to zero",
        !/(^|[\s·])0%/.test(fixText) && !/\$0(\s|$)/.test(fixText),
        fixText.trim().slice(0, 90));
  check("identical-shock stamp", /%/.test(d.getElementById("shockStamp").textContent),
        d.getElementById("shockStamp").textContent);
  check("both feet populated",
        d.getElementById("footBefore").textContent.includes("loss") &&
        d.getElementById("footAfter").textContent.includes("loss"));
  check("no errors across all four beats", errors.length === 0, errors.join("; "));

  /* The webfont lands after first paint and reflows the masthead, so the
     stage resizes and the ResizeObserver redraws — routinely while the
     split is still animating. It must redraw the round that is on screen,
     not the last one, or it shows the ending and then rewinds into it. */
  console.log("\nREFLOW — a redraw must not skip to the ending");
  d.getElementById("defendBtn").dispatchEvent(new window.Event("click"));
  // Capped. This was `while (...) await sleep(20)` with no iteration limit, so
  // if defend() ever failed the harness spun forever, printed nothing and
  // never exited — the exact silent-hang failure requireServer() was added to
  // prevent, sitting forty lines below it.
  let waited = 0;
  while (!/^shock applied/.test(d.getElementById("splitRound").textContent)) {
    if (waited >= 15000) {
      check("the split reaches its first frame", false,
            `splitRound stuck at "${d.getElementById("splitRound").textContent}" after 15s`);
      break;
    }
    await sleep(20);
    waited += 20;
  }
  const round0 = svg("netBefore").innerHTML;
  reflow();
  await sleep(150);                       // handler is debounced 60ms
  check("split redraw keeps the round it is on",
        /^shock applied/.test(d.getElementById("splitRound").textContent) &&
        svg("netBefore").innerHTML === round0,
        d.getElementById("splitRound").textContent);
  await sleep(6000);                      // let the split finish

  /* ── from here down: the paths a demo actually stumbles into ────────── */

  const css = fs.readFileSync(WEB + "/style.css", "utf8");
  const reserved = (sel) => {
    const rule = css.match(new RegExp(`\\${sel}\\s*\\{([^}]*)\\}`))[1];
    return Number(rule.match(/(?:min-)?width:\s*([\d.]+)ch/)[1]);
  };
  const set = (id, v) => {
    const e = d.getElementById(id);
    e.value = v;
    e.dispatchEvent(new window.Event("input"));
  };
  const click = (id) => d.getElementById(id).dispatchEvent(new window.Event("click"));
  const text = (id) => d.getElementById(id).textContent;

  /* Both of these are reserved a fixed ch width so digits can't shove the
     layout around mid-animation. The reservation is only honest if nothing
     the app writes is longer than it, so read the number out of the CSS and
     watch every string that lands in the element. */
  console.log("\nFIXED WIDTHS — nothing may outgrow its reservation");
  const seen = { roundLabel: new Set(), heroVal: new Set() };
  const sampler = setInterval(() => {
    seen.roundLabel.add(text("roundLabel"));
    seen.heroVal.add(text("heroVal"));
  }, 25);

  set("leverage", "1.5");      // 58.34% — the widest hero the sliders can reach
  click("attackBtn");
  await sleep(7000);
  clearInterval(sampler);

  const longest = (s) => [...s].reduce((a, b) => (b.length > a.length ? b : a), "");
  const worstLabel = longest(seen.roundLabel), worstHero = longest(seen.heroVal);
  check("round label fits .tl-label", worstLabel.length <= reserved(".tl-label"),
        `"${worstLabel}" is ${worstLabel.length}ch, reserved ${reserved(".tl-label")}ch`);
  check("hero number fits .hero-val", worstHero.length <= reserved(".hero-val"),
        `"${worstHero}" is ${worstHero.length}ch, reserved ${reserved(".hero-val")}ch`);
  check("hero counted to a 2-decimal percent", /^\d+\.\d{2}%$/.test(text("heroVal")), text("heroVal"));
  check("every count-up step had 2 decimals",
        [...seen.heroVal].every((v) => v === "—" || /^\d+\.\d{2}%$/.test(v)),
        [...seen.heroVal].filter((v) => v !== "—" && !/^\d+\.\d{2}%$/.test(v)).join(",") || "ok");
  check("re-running attack raised no errors", errors.length === 0, errors.join("; "));

  console.log("\nFORMATTING — fixed decimals in the band");
  const band = [...d.querySelectorAll("#band .v")].map((e) => e.textContent);
  check("shock loss is 1dp", /^\d+\.\d%$/.test(band[0]), band[0]);
  check("final loss is 1dp", /^\d+\.\d%$/.test(band[1]), band[1]);
  check("amplification is 2dp", /^\d+\.\d{2}×$/.test(band[2]), band[2]);
  check("rounds reads t / n", /^\d+ \/ \d+$/.test(band[4]), band[4]);

  /* The cascade and the split each own a timer queue. Whichever scene takes
     the stage must stop the other, or the strip along the bottom keeps
     narrating a run that is no longer on screen. */
  console.log("\nRACE — leaving a scene must stop its animation");
  click("replayBtn");
  await sleep(400);                       // cascade is mid-round, more rounds queued
  const running = [text("roundLabel"), band4(d)].join("|");
  click("boundaryBtn");
  /* Snapshot straight away and compare while the sweep is still fetching —
     the cancel has to happen when boundary() starts, not when it finishes,
     or the cascade narrates over the scene that replaced it. */
  const frozen = [text("roundLabel"), band4(d)].join("|");
  await sleep(1600);
  check("cascade was still mid-flight when the boundary took over",
        running === frozen && /round \d/.test(frozen), frozen);
  check("cascade stops the moment the boundary takes the stage",
        [text("roundLabel"), band4(d)].join("|") === frozen, frozen);
  await sleep(8000);                      // let the sweep land
  check("boundary scene took the stage", !d.getElementById("sceneBoundary").hasAttribute("hidden"));

  console.log("\nSCRUB — the timeline belongs to the cascade");
  d.getElementById("track").children[1].dispatchEvent(new window.Event("click"));
  await sleep(200);
  check("scrubbing from another scene comes back to the network",
        !d.getElementById("sceneNetwork").hasAttribute("hidden") &&
        d.getElementById("sceneBoundary").hasAttribute("hidden"));

  /* "nothing breaks this system" used to print over the previous cascade,
     which was still on the stage saying the opposite. */
  console.log("\nEMPTY ANSWER — no break found");
  set("leverage", "1.5"); set("gamma", "0");
  d.getElementById("breaches").value = "5";
  click("attackBtn");
  await sleep(3000);
  check("hero goes idle", text("heroVal") === "—" && d.getElementById("heroVal").hasAttribute("data-idle"));
  check("band is blanked", [...d.querySelectorAll("#band .v")].every((e) => e.textContent === "—"),
        [...d.querySelectorAll("#band .v")].map((e) => e.textContent).join(" "));
  check("timeline is emptied", d.getElementById("track").children.length === 0);
  check("round label says no run", text("roundLabel") === "no run", text("roundLabel"));
  check("network is cleared", svg("network").querySelectorAll("circle").length === 0);
  check("stabilise is disabled with no run", d.getElementById("defendBtn").disabled);
  click("replayBtn");
  await sleep(300);
  check("replay does nothing with no run", text("roundLabel") === "no run", text("roundLabel"));

  console.log("\nEMPTY ANSWER — no single-position fix");
  d.getElementById("defendBtn").disabled = false;    // reach the branch directly
  click("defendBtn");
  await sleep(3000);
  check("banner explains there is no single cut", /No single-position cut/.test(text("fixLine")));
  check("before half is cleared", svg("netBefore").querySelectorAll("circle").length === 0);
  check("after half is cleared", svg("netAfter").querySelectorAll("circle").length === 0);
  check("stale outcome readouts are gone",
        text("footBefore") === "—" && text("footAfter") === "—",
        `${text("footBefore")} / ${text("footAfter")}`);
  check("stale shock stamp is gone", text("shockStamp") === "—", text("shockStamp"));

  /* A cached answer must never wear the live badge. */
  console.log("\nPROVENANCE — a replayed answer says so");
  const realFetch = window.fetch;
  window.fetch = async (u, o) => {
    const r = await realFetch(u, o);
    const j = await r.json();
    return { ok: r.ok, status: r.status, json: async () => ({ ...j, cached: true }) };
  };
  set("leverage", "5"); set("gamma", "0.2");
  d.getElementById("breaches").value = "3";
  click("attackBtn");
  await sleep(4000);
  check("cached run is not badged live", d.getElementById("badge").dataset.mode === "cached",
        `${d.getElementById("badge").dataset.mode} / ${text("badgeText")}`);

  console.log("\nERROR PATH — the engine dies");
  window.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  click("attackBtn");
  await sleep(1500);
  check("badge reports the engine is unreachable",
        d.getElementById("badge").dataset.mode === "cached", text("badgeText"));
  check("the reason is on screen", /500|unreachable/i.test(text("heroSub")), text("heroSub"));
  check("attack button is usable again", !d.getElementById("attackBtn").disabled);
  click("boundaryBtn");
  await sleep(1200);
  check("boundary button is usable again", !d.getElementById("boundaryBtn").disabled);
  check("a dead engine raises no unhandled rejection", errors.length === 0, errors.join("; "));
  window.fetch = realFetch;

  /* ── impatience: the presenter clicks faster than the animations ─────── */

  /* countTo() runs on requestAnimationFrame, which neither timer queue owns.
     Two attacks inside half a second used to leave the first run's count-up
     ticking, and if the second answer is "nothing breaks this system" it
     wrote its number back over the blanked hero and stopped there — the
     biggest number on screen belonging to a run the band, the timeline and
     the sub-line had all just disowned. */
  console.log("\nIMPATIENCE — a superseded run must let go of the hero");
  window.fetch = realFetch;
  set("leverage", "1.5"); set("gamma", "0.2");
  d.getElementById("breaches").value = "2";
  click("attackBtn");
  await sleep(70);                        // the count-up is mid-flight
  window.fetch = async (u, o) => {        // a recording comes off disk this fast
    const r = await realFetch(u, o);
    const j = await r.json();
    return { ok: r.ok, status: r.status, json: async () => ({ ...j, found: false }) };
  };
  click("attackBtn");
  await sleep(200);
  check("a disowned count-up does not write over the idle hero",
        !(d.getElementById("heroVal").hasAttribute("data-idle") && text("heroVal") !== "—"),
        `hero="${text("heroVal")}" idle=${d.getElementById("heroVal").hasAttribute("data-idle")}`);
  await sleep(700);
  check("hero settles idle", text("heroVal") === "—", text("heroVal"));
  window.fetch = realFetch;

  /* stopAnimations() cannot stop a request already in the air. Hold the sweep
     and the answer to the beat the presenter moved ON from lands last. */
  console.log("\nIMPATIENCE — the last button pressed owns the stage");
  const slow = (ms) => async (u, o) => {
    if (u.startsWith("/api/boundary")) await sleep(ms);
    return realFetch(u, o);
  };
  window.fetch = slow(2600);
  click("boundaryBtn");
  await sleep(80);
  click("attackBtn");                     // cascade starts while the sweep flies
  await sleep(2800);                      // the sweep has now landed
  const stageAt = d.getElementById("sceneBoundary").hasAttribute("hidden") ? "network" : "boundary";
  const labelAt = text("roundLabel");
  await sleep(1400);
  check("a late sweep does not take a stage the presenter left",
        stageAt === "network", stageAt);
  check("and nothing narrates a scene that is not on screen",
        text("roundLabel") === labelAt || stageAt === "network",
        `${labelAt} → ${text("roundLabel")} on ${stageAt}`);
  window.fetch = realFetch;
  await sleep(4200);

  /* The split owns a SECOND timer queue. The timeline handler used to clear
     only the cascade's, so scrubbing away left the comparison advancing
     inside a hidden scene and sitting on its ending when you came back. */
  console.log("\nIMPATIENCE — leaving the split stops the split");
  click("attackBtn");
  await sleep(4200);
  click("defendBtn");
  await sleep(1200);
  const splitAt = text("splitRound");
  d.getElementById("track").children[0].dispatchEvent(new window.Event("click"));
  await sleep(1800);
  check("the split's clock stops when the timeline takes the stage",
        text("splitRound") === splitAt, `${splitAt} → ${text("splitRound")}`);

  /* The knobs are free to move; the numbers are not free to pretend they
     moved with them. */
  console.log("\nSTALE — the knobs move, the numbers do not");
  click("attackBtn");
  await sleep(4200);
  const heroWas = text("heroVal");
  set("leverage", "8");
  await sleep(120);
  check("moving a knob marks the run it disowns",
        text("heroNote") !== "" &&
        d.getElementById("heroVal").hasAttribute("data-stale"),
        `hero ${heroWas} → ${text("heroVal")}, note "${text("heroNote")}"`);
  set("leverage", "1.5");
  await sleep(120);
  check("putting it back clears the mark", text("heroNote") === "", text("heroNote"));

  /* A beat that did not run must say so where the eye already is. */
  console.log("\nERROR PATH — a beat that failed says which beat");
  window.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  click("boundaryBtn");
  await sleep(1200);
  check("a failed sweep names itself on screen", /did not run/.test(text("heroNote")),
        `note "${text("heroNote")}"`);
  check("and its progress readout stops counting",
        !/elapsed/.test(d.getElementById("solverStats").textContent),
        d.getElementById("solverStats").textContent);
  window.fetch = realFetch;

  /* ── the three things a hostile judge asks for ─────────────────────── */

  /* Two elements shared id="band" — the new slider and the metrics strip.
     getElementById returns the first in document order, so every paintBand()
     wrote its five cells into a range input and the strip sat on its
     placeholder dashes for the whole run. */
  console.log("\nIDS — nothing may share an id");
  const ids = [...d.querySelectorAll("[id]")].map((e) => e.id);
  const dupes = ids.filter((x, i) => ids.indexOf(x) !== i);
  check("every id in the document is unique", dupes.length === 0, dupes.join(","));

  console.log("\nBREACH BAND — the slider must reach the engine");
  set("leverage", "5"); set("gamma", "0.2");
  d.getElementById("breaches").value = "3";
  set("breachBand", "1.05");
  click("attackBtn");
  await sleep(4600);
  const at105 = text("heroVal");
  set("breachBand", "1.30");
  check("the band label tracks the slider", text("breachBandVal") === "1.30", text("breachBandVal"));
  click("attackBtn");
  await sleep(4600);
  const at130 = text("heroVal");
  check("moving the band moves the headline", at105 !== at130, `${at105} → ${at130}`);
  check("band 1.30 gives the engine's answer", at130 === "27.33%", at130);
  check("the metrics band still updates", [...d.querySelectorAll("#band .v")].every((e) => e.textContent !== "—"),
        [...d.querySelectorAll("#band .v")].map((e) => e.textContent).join(" "));
  set("breachBand", "1.05");
  click("attackBtn");
  await sleep(4600);

  /* A cheapest single-position cut defends against THE shock, not the next
     one. Say so before a judge presses Find weakest shock again and finds it. */
  console.log("\nWHAT THE FIX BOUGHT — stated, not buried");
  click("defendBtn");
  await sleep(4600);
  const bought = d.getElementById("boughtLine");
  check("the split says what the fix bought", !bought.hidden && /critical distance/.test(bought.textContent),
        `hidden=${bought.hidden} "${bought.textContent.slice(0, 90)}"`);
  check("it names the limit of the claim", /not the next one/.test(bought.textContent));
  check("an unmeasurable move is not printed as a delta",
        !/no measurable change/.test(bought.textContent) || !/[+-]\d+\.\d\dpp/.test(bought.textContent),
        bought.textContent);

  console.log("\nASSUMPTIONS — reachable in one click, and populated");
  const panel = d.getElementById("assumePanel");
  check("the panel is collapsed by default", panel.hidden);
  click("assumeBtn");
  check("one click opens it", !panel.hidden);
  const rows = [...d.getElementById("assumeBody").querySelectorAll("div")];
  const body = d.getElementById("assumeBody").textContent;
  check("it lists every assumption", rows.length >= 8, rows.length + " rows");
  check("holdings are declared real, with their source", /SEC 13F-HR/.test(body) && /2026-06-30/.test(body), 
        (body.match(/period [^,]+/) || [""])[0]);
  check("leverage is declared not measured", /No fund discloses it/.test(body));
  check("the breach band's influence is stated", /1\.30 gives/.test(body));
  check("the impact model is written down", /ADV/.test(body) && /contagion/.test(body));
  check("the non-claim is stated", /not a proven threshold/i.test(body));
  check("scale is bounded", /mechanism transfers/.test(body));
  const kinds = new Set(rows.map((r) => r.querySelector("dt").dataset.kind));
  check("every row says whether it is measured or declared",
        [...kinds].every((k) => ["measured", "declared", "limit"].includes(k)), [...kinds].join(","));
  check("it does not cover the stage",
        !/inset\s*:\s*0/.test(css.match(/\.overlay\s*\{([^}]*)\}/)[1]),
        css.match(/\.overlay\s*\{([^}]*)\}/)[1].replace(/\s+/g, " ").trim().slice(0, 70));
  click("assumeClose");
  check("close puts it away", panel.hidden);

  console.log("\nCOUNT-UP — the hero under a stale frame clock");
  // requestAnimationFrame hands the callback the FRAME's start time, which can
  // pre-date the performance.now() the animation captured a moment earlier.
  // Then (now - started) is negative, and a clamp that only caught the top end
  // let the hero render -85.66% while the diagram beside it read -5.27%. Hand
  // it a timestamp from five seconds ago and watch.
  const realRaf = window.requestAnimationFrame;
  window.requestAnimationFrame = (cb) => realRaf(() => cb(window.performance.now() - 5000));
  const samples = [];
  click("attackBtn");
  for (let i = 0; i < 80; i++) { samples.push(text("heroVal")); await sleep(25); }
  window.requestAnimationFrame = realRaf;
  const negative = samples.find((v) => v.trim().startsWith("-"));
  check("the hero never counts through a negative percentage",
        !negative, negative ? `saw ${negative}` : `${samples.length} samples, none negative`);

  // The skew leaves the count parked at 0.00% — k only reaches 1 once five
  // seconds of real time have passed — so re-run it on an honest clock before
  // asking where it landed. Asserting the landing while still skewed would
  // fail the fixed build too, which is a test that proves nothing.
  click("attackBtn");
  await sleep(4000);
  check("and on an honest clock it still lands on the real answer",
        /^\d+\.\d{2}%$/.test(text("heroVal")), text("heroVal"));

  console.log("\nCOUNT-UP — the hero when the frame clock never advances");
  // Clamping the interpolation turned "-85.66%" into "0.00%" — the same
  // failure, quieter, and a screenshot of 0.00% in 48px type looks like a
  // finished render rather than a stalled one. Reproduce the stall exactly:
  // hand the animation one frame, then freeze. A throttled background tab
  // does this, and so does headless Chrome under a virtual-time budget.
  // Freeze the CLOCK, not the frames. Withholding the callbacks themselves
  // also stalls the rAF-await inside attack(), so the run never reaches the
  // count-up at all and the test measures a deadlock it caused. Frames keep
  // arriving here; every one of them just reports the same timestamp, which
  // is exactly what headless Chrome does under a virtual-time budget and what
  // a throttled tab does to a judge's laptop.
  const liveRaf = window.requestAnimationFrame;
  window.requestAnimationFrame = (cb) => liveRaf(() => cb(1000));
  click("attackBtn");
  await sleep(2500);
  window.requestAnimationFrame = liveRaf;
  check("the number still arrives when the animation cannot run",
        /^\d+\.\d{2}%$/.test(text("heroVal")) && text("heroVal") !== "0.00%",
        text("heroVal"));

  console.log(`\n${failures ? failures + " FAILURES" : "all checks passed"}`);
  process.exit(failures ? 1 : 0);
})().catch((e) => {
  // Reaching here means the harness itself broke — a helper used before its
  // `const`, a missing element. Without this the process just runs out of work
  // and exits 0, reporting a clean run that stopped a third of the way in.
  console.log(`\nHARNESS ABORTED: ${e && e.stack ? e.stack : e}`);
  process.exit(1);
});

const band4 = (d) => [...d.querySelectorAll("#band .v")].map((e) => e.textContent).join(" ");
