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

/* The nav locks pages you have not earned yet. A link to an analysis that
   does not exist leads to a page explaining it does not exist, which is a
   worse answer than a link that is visibly not ready. */
function paintNav(current) {
  const s = FB.state;
  const has = { portfolio: true, analysis: !!s.result, cascade: !!s.result,
                defend: !!(s.result && s.result.fix), verify: !!(s.result && s.result.validation) };
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
  if (!new URLSearchParams(location.search).has("demo")) return false;
  const s = FB.state;
  if (s.result && s.result.found) return false;
  try {
    const demo = await api("/api/portfolio/demo");
    FB.set({ portfolio: demo.portfolio, rows: null, limit: s.limit || 0.10 });
    const full = await api(`/api/portfolio/full?limit=${s.limit || 0.10}`, {});
    FB.set({ result: full });
    return true;
  } catch { return false; }
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
