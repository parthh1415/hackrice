/* Shared across pages. State lives in sessionStorage because these are real
   separate documents, not tabs pretending to be pages. */

const FB = {
  get state() {
    try { return JSON.parse(sessionStorage.getItem("fb") || "{}"); }
    catch { return {}; }
  },
  set(patch) {
    const next = { ...this.state, ...patch };
    sessionStorage.setItem("fb", JSON.stringify(next));
    return next;
  },
  clear() { sessionStorage.removeItem("fb"); },
};

async function api(path, payload) {
  const res = await fetch(path, payload
    ? { method: "POST", cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload) }
    : { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

const usd = (x) => {
  const a = Math.abs(x);
  if (a >= 1e9) return `$${(x / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(x / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(x / 1e3).toFixed(1)}K`;
  return `$${x.toFixed(0)}`;
};
const usdExact = (x) => `$${Math.round(x).toLocaleString("en-US")}`;
const pct = (x, dp = 2) => `${(x * 100).toFixed(dp)}%`;

/* Any API field the server is allowed to send as null. `x.toFixed()` on one of
   those throws, and when it happens inside a template literal the whole
   innerHTML assignment is skipped — the page renders its heading over an empty
   div rather than showing anything wrong, which is how verify.html went blank
   exactly when the fix had worked best. Render the absence instead. */
const num = (x, dp = 2, dash = "—") =>
  (x === null || x === undefined || !Number.isFinite(x)) ? dash : x.toFixed(dp);

/* The nav locks pages you have not earned yet. A link to an analysis that
   does not exist leads to a page explaining it does not exist, which is a
   worse answer than a link that is visibly not ready. */
function paintNav(current) {
  const s = FB.state;
  /* A page missing from this map reads as `undefined`, and `!undefined` locks
     it. `assumptions` was missing, so the Model link was dead on every page
     including its own — the page was reachable only by typing its URL. Nothing
     about the methodology depends on having run an analysis, so it is always
     open. */
  const has = { portfolio: true, analysis: !!s.result, cascade: !!s.result,
                defend: !!(s.result && s.result.fix),
                verify: !!(s.result && s.result.validation),
                assumptions: true };
  document.querySelectorAll(".nav-links a").forEach((a) => {
    const page = a.dataset.page;
    if (page === current) a.setAttribute("aria-current", "page");
    if (!has[page]) a.setAttribute("data-locked", "");
    else a.removeAttribute("data-locked");
  });
  const set = (id, v) => { const n = document.getElementById(id); if (n) n.textContent = v; };
  set("navPf", "");
  const pf = document.getElementById("navPf");
  if (pf) pf.innerHTML = `BOOK <b>${s.portfolio
    ? (s.portfolio.source === "demo" ? "DEMO_01" : "IMPORTED") : "—"}</b>`;
  const lim = document.getElementById("navLimit");
  if (lim) lim.innerHTML = `LIMIT <b>${s.limit ? pct(s.limit, 2) : "—"}</b>`;
  const sh = document.getElementById("navShock");
  if (sh) sh.innerHTML = s.result && s.result.found
    ? `SHOCK <b class="down">${s.result.asset} −${s.result.pct.toFixed(2)}%</b>`
    : `SHOCK <b>NOT RUN</b>`;

  // clock and engine status, the way a terminal wears them
  const tick = () => {
    const c = document.getElementById("navClock");
    if (c) c.textContent = new Date().toLocaleTimeString("en-GB", { hour12: false });
  };
  tick();
  if (!window.__fbClock) window.__fbClock = setInterval(tick, 1000);

  fetch("/api/health", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw 0; return r.json(); })
    .then((h) => {
      const dot = document.getElementById("navEngine");
      const txt = document.getElementById("navEngineText");
      if (dot) { dot.textContent = "●"; dot.className = "up"; }
      if (txt) txt.textContent = h && h.cached ? "REPLAY" : "ENGINE LIVE";
    })
    .catch(() => {
      const dot = document.getElementById("navEngine");
      const txt = document.getElementById("navEngineText");
      if (dot) { dot.textContent = "●"; dot.className = "down"; }
      if (txt) txt.textContent = "OFFLINE";
    });
}

/* ?demo on ANY page: seed the demo book and run the analysis if state is
   empty. Makes every page a shareable link that opens ready — and it is the
   only way to screenshot a downstream page from a cold browser, which is how
   the last three rendering bugs were found. */
async function seedDemoIfAsked() {
  const q = new URLSearchParams(location.search);
  if (!q.has("demo")) return false;
  const s = FB.state;
  if (s.result && s.result.found) return false;
  /* ?limit= travels with ?demo, so a link carries the whole scenario. Passed
     through unvalidated on purpose: the engine decides what is in range and
     reports back when it had to pull a number in, and a second opinion here
     would only be a second place for the two to disagree. */
  const asked = Number(q.get("limit"));
  const limit = Number.isFinite(asked) && q.has("limit") ? asked : (s.limit || 0.10);
  try {
    const demo = await api("/api/portfolio/demo");
    FB.set({ portfolio: demo.portfolio, rows: null, limit });
    const full = await api(`/api/portfolio/full?limit=${limit}`, {});
    FB.set({ result: full });
    return true;
  } catch { return false; }
}

/* What a result was computed FOR. Two of these differing means the answer on
   the downstream pages belongs to a portfolio or a limit the user has since
   changed, and showing it is the client-side version of the mix-up api.py
   refuses to make on the server: somebody else's book, labelled as theirs. */
function scenarioKey(portfolio, limit) {
  const rows = ((portfolio && portfolio.holdings) || [])
    .map((h) => `${h.symbol}:${h.market_value}`).sort().join(",");
  return `${rows}@${limit}`;
}

/* Drop a result that no longer answers the current question. Returns true if
   it dropped one, so a caller can repaint. */
function invalidateStaleResult() {
  const s = FB.state;
  if (!s.result) return false;
  const answered = scenarioKey(s.result.portfolio, s.result.params && s.result.params.limit);
  const asking = scenarioKey(s.portfolio, s.limit);
  if (answered === asking) return false;
  FB.set({ result: null });
  return true;
}

function requireResult(current) {
  const s = FB.state;
  if (!s.result || !s.result.found) {
    document.querySelector("main").innerHTML =
      `<div class="wrap page"><div class="card"><div class="empty">
         <h2>No analysis yet</h2>
         <p class="lede" style="margin:0 auto">Run a reverse stress test first — this page
         shows what that produced.</p>
         <div style="margin-top:20px"><a class="btn btn-primary" href="analysis.html">Go to analysis</a></div>
       </div></div></div>`;
    paintNav(current);
    return null;
  }
  return s.result;
}
