/* Headless smoke test for the frontend.
 *
 * Screen recording is blocked for this terminal and the Chrome extension
 * isn't set up, so nothing here can take a screenshot. This runs the real
 * app.js against the real server in jsdom instead and asserts the DOM it
 * builds — which catches every class of bug except "it looks wrong".
 *
 *   cd /tmp/domtest && npm install jsdom
 *   node ~/Desktop/firebreak/tests/ui/smoke.js
 */
const { JSDOM } = require("jsdom");
const fs = require("fs");
const WEB = "/Users/parthsrivastava/Desktop/firebreak/web";
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

(async () => {
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
  check("fix instruction shown", /cut/i.test(d.getElementById("fixLine").textContent),
        d.getElementById("fixLine").textContent.trim().slice(0, 80));
  check("identical-shock stamp", /%/.test(d.getElementById("shockStamp").textContent),
        d.getElementById("shockStamp").textContent);
  check("both feet populated",
        d.getElementById("footBefore").textContent.includes("loss") &&
        d.getElementById("footAfter").textContent.includes("loss"));
  check("no errors across all four beats", errors.length === 0, errors.join("; "));

  console.log(`\n${failures ? failures + " FAILURES" : "all checks passed"}`);
  process.exit(failures ? 1 : 0);
})();
