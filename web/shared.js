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
  const badge = document.getElementById("navBadge");
  if (badge && s.portfolio) {
    badge.textContent = s.portfolio.source === "demo" ? "Demo portfolio" : "Imported";
  }
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
