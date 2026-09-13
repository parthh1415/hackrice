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

/* The rail's footer strip prints the last response time. DESIGN.md wants
   11-20ms and `cached: false` proved on screen rather than asserted in a
   slide, and a number like that is only worth printing if it was measured.
   Every call goes through here, so here is where the stopwatch lives. */
let _lastMs = null;
const lastResponseMs = () => _lastMs;

async function api(path, payload) {
  const t0 = performance.now();
  const res = await fetch(path, payload
    ? { method: "POST", cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload) }
    : { cache: "no-store" });
  /* "/api/portfolio/full?limit=0.1 → 500" is a stack trace wearing a sentence.
     The user cannot act on a route; they can act on "the engine is not
     answering". The route is still in the console for whoever is debugging. */
  if (!res.ok) {
    console.error("firebreak:", path, res.status);
    throw new Error(`the engine returned HTTP ${res.status}. Check the server on port 8765.`);
  }
  const body = await res.json();
  /* Timed to the end of the body read, not to the first byte — the strip
     claims "the engine answered", and it has not answered until the answer is
     in hand. The event lets the strip repaint without polling for it. */
  _lastMs = performance.now() - t0;
  document.dispatchEvent(new CustomEvent("fb:latency", { detail: { ms: _lastMs, path } }));
  return body;
}

const usd = (x) => {
  const a = Math.abs(x);
  if (a >= 1e9) return `$${(x / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(x / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(x / 1e3).toFixed(1)}K`;
  return `$${x.toFixed(0)}`;
};
/* Whole dollars, except where whole dollars would throw the number away. A
   six-cent fix on a tiny book rendered as "$0", so the defend page read "Sell
   $0 of NVDA" — an instruction to do nothing, for a cut that is real. Below
   $10 the cents are most of the number, so they are shown. The demo's $478 is
   unaffected, which matters because the script says it out loud. */
const usdExact = (x) => {
  const n = Number(x) || 0;
  return Math.abs(n) < 10 && n !== 0
    ? `$${n.toFixed(2)}`
    : `$${Math.round(n).toLocaleString("en-US")}`;
};
const pct = (x, dp = 2) => `${(x * 100).toFixed(dp)}%`;

/* Any API field the server is allowed to send as null. `x.toFixed()` on one of
   those throws, and when it happens inside a template literal the whole
   innerHTML assignment is skipped — the page renders its heading over an empty
   div rather than showing anything wrong, which is how verify.html went blank
   exactly when the fix had worked best. Render the absence instead. */
/* A loss, with the minus written by the formatter rather than by hand in front
   of it. `"−" + pct(x)` prints "−0.00%" for anything that rounds to zero — a
   loss of negative zero — which is how the cascade diagram once reported nine
   untouched names. The same construction was still on the analysis page's
   attribution table, where a fuzz of 39 portfolios hit it in 24. Below half a
   basis point there is nothing to report, so it says so. */
const loss = (x, dp = 2) =>
  (Math.abs(x) * 100 < 0.5 * Math.pow(10, -dp) ? "—" : `−${pct(Math.abs(x), dp)}`);

const num = (x, dp = 2, dash = "—") =>
  (x === null || x === undefined || !Number.isFinite(x)) ? dash : x.toFixed(dp);

/* The nav locks pages you have not earned yet. A link to an analysis that
   does not exist leads to a page explaining it does not exist, which is a
   worse answer than a link that is visibly not ready. */
function paintNav(current) {
  const s = FB.state;
  /* the bar reports the same state the nav does, so they cannot disagree */
  if (document.querySelector(".statusbar")) paintStatusBar(current);
  paintExclusionBanner(current);
  /* A page missing from this map reads as `undefined`, and `!undefined` locks
     it. `assumptions` was missing, so the Model link was dead on every page
     including its own — the page was reachable only by typing its URL. Nothing
     about the methodology depends on having run an analysis, so it is always
     open. */
  /* `limit` is the stepper's step 2. It is a section of the portfolio page
     rather than a page of its own, and it is open whenever that page is —
     which is always. Absent from this map it would read as `undefined` and
     the rail would lock its own second step. */
  const has = { portfolio: true, limit: true, analysis: !!s.result, cascade: !!s.result,
                defend: !!(s.result && s.result.fix),
                verify: !!(s.result && s.result.validation),
                /* Neither of these needs an analysis: the boundary sweeps the
                   whole configuration space and the model page describes it.
                   They read the session's knobs when there are some and fall
                   back to the engine's declared defaults when there are not. */
                boundary: true,
                assumptions: true };
  document.querySelectorAll(".nav-links a").forEach((a) => {
    const page = a.dataset.page;
    if (page === current) a.setAttribute("aria-current", "page");
    /* pointer-events:none stops the mouse and nothing else — Tab then Enter
       still navigated to a page the state cannot answer. */
    if (!has[page]) {
      a.setAttribute("data-locked", "");
      a.setAttribute("aria-disabled", "true");
      a.tabIndex = -1;
    } else {
      a.removeAttribute("data-locked");
      a.removeAttribute("aria-disabled");
      a.removeAttribute("tabindex");
    }
  });
  const set = (id, v) => { const n = document.getElementById(id); if (n) n.textContent = v; };
  set("navPf", "");
  const pf = document.getElementById("navPf");
  if (pf) pf.innerHTML = `BOOK <b>${s.portfolio
    ? (s.portfolio.source === "demo" ? "DEMO_01" : "IMPORTED") : "—"}</b>`;
  const lim = document.getElementById("navLimit");
  /* the limit was printed three ways on one screen: LIMIT 10.00% here, YOUR
     LIMIT 10% in the tiles, "a limit of 10%" in the prose. It is a round
     number the user picked from four buttons; two decimals were inventing
     precision the choice does not have. */
  /* The value only. The word "LIMIT" used to be written here, which meant the
     rail could not label it in its own voice without two places writing one
     element. The label is markup now; this writes the number. */
  if (lim) lim.textContent = s.limit ? pct(s.limit, 0) : "—";
  const sh = document.getElementById("navShock");
  /* Three states, not two. A search that ran and found nothing is not the same
     as a search that never ran, and calling it "NOT RUN" is simply false — the
     user pressed the button and waited. It is also the more interesting
     result: no single-name fall inside the tested range crosses the limit. */
  if (sh) sh.innerHTML = !s.result
    ? `SHOCK <b>NOT RUN</b>`
    : s.result.found
      ? `SHOCK <b class="down">${s.result.asset} −${s.result.pct.toFixed(2)}%</b>`
      : `SHOCK <b>NONE FOUND</b>`;

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
      /* "REPLAY" is also the cascade page's transport button, one click away,
         where it means something entirely different. */
      if (txt) txt.textContent = h && h.cached ? "cached" : "engine live";
    })
    .catch(() => {
      const dot = document.getElementById("navEngine");
      const txt = document.getElementById("navEngineText");
      if (dot) { dot.textContent = "●"; dot.className = "down"; }
      if (txt) txt.textContent = "offline";
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

/* If part of the book was set aside, say so on every page that shows a number
   about it. A disclosure that appears only on the screen where you agreed to
   it stops being a disclosure the moment you click through — and the pages
   after that one are the ones with the money on them. */
/* The pages whose numbers describe the user's own book. Boundary sweeps the
   five institutional books across a configuration space and Model describes
   the method — neither reads a holding, so "not in any number below" is simply
   untrue there, and a banner that overclaims is the same defect as one that
   under-discloses. */
const BOOK_PAGES = new Set(["portfolio", "analysis", "cascade", "defend", "verify"]);

function paintExclusionBanner(current) {
  const note = FB.state.result && FB.state.result.excluded_note;
  const existing = document.getElementById("exclBanner");
  if (!note || !BOOK_PAGES.has(current)) { if (existing) existing.remove(); return; }
  const names = (note.excluded || []).map((e) => e.symbol).join(", ");
  const bar = existing || document.createElement("div");
  bar.id = "exclBanner";
  bar.className = "excl";
  bar.innerHTML =
    `<b>${pct(note.excluded_fraction, 1)} of this book is not modelled and is not in any ` +
    `number below.</b> ${names} — ${usdExact(note.excluded_value)} of ` +
    `${usdExact(note.whole_book_value)} — ${(note.excluded || []).length > 1 ? "are" : "is"} ` +
    `outside the ten-name universe. Everything here describes the rest.`;
  if (!bar.isConnected) {
    /* The shell's content column is <main class="col">; the old chrome wraps
       its content in .wrap. A banner that silently fails to mount is a
       disclosure that disappears the moment a page is converted, so this
       matches both rather than the one that happened to exist first. */
    const main = document.querySelector("main .wrap, main.col");
    if (main) main.insertBefore(bar, main.firstChild);
  }
}

function requireResult(current) {
  const s = FB.state;
  if (!s.result || !s.result.found) {
    /* "Run a reverse stress test first" is wrong when they already did and it
       came back empty. That is not an error and not a missing step — it is the
       answer, and it has an action attached: lower the limit. */
    const ran = !!s.result;
    const limit = s.limit ? pct(s.limit, 0) : "your limit";
    /* Keep the page's own header. Replacing all of <main> stripped the eyebrow
       and the h1, so an empty state read as an error screen — a lone card at
       the top of 700px of black, on a page that had just been announcing what
       it was. */
    const header = document.querySelector("main .stack.gap-3");
    let head = "";
    if (header) {
      /* the page's lede is still its placeholder at this point — the script
         that fills it never got there — so it would render as a bare em dash
         under the headline. The empty state says the same thing properly. */
      const clone = header.cloneNode(true);
      clone.querySelectorAll(".lede").forEach((n) => n.remove());
      head = clone.outerHTML;
    }
    /* and each page says what IT cannot do, rather than every page but defend
       claiming there is nothing to "verify". */
    const verb = { cascade: "trace", defend: "defend", verify: "verify",
                   boundary: "place you on" }[current] || "show";
    document.querySelector("main").innerHTML = ran
      ? `<div class="wrap page stack gap-8">${head}<div class="card"><div class="empty">
           <h2>No break point to ${verb}</h2>
           <p class="lede" style="margin:0 auto">At a ${limit} limit, no single-name fall
           inside the tested range crossed it — so there is nothing here to
           ${verb}. That is the edge of what was tested, not a clean bill of health.</p>
           <div class="row gap-4" style="margin-top:20px;justify-content:center">
             <a class="btn btn-primary" href="index.html">Lower the limit</a>
             <a class="btn btn-outline" href="analysis.html">Back to the analysis</a></div>
         </div></div></div>`
      : `<div class="wrap page stack gap-8">${head}<div class="card"><div class="empty">
           <h2>No analysis yet</h2>
           <p class="lede" style="margin:0 auto">Run a reverse stress test first — this page
           shows what that produced.</p>
           <div class="row gap-4" style="margin-top:20px;justify-content:center">
             <a class="btn btn-primary" href="analysis.html">Go to analysis</a></div>
         </div></div></div>`;
    paintNav(current);
    return null;
  }
  return s.result;
}

/* ── keyboard, and the bar that tells you it exists ──────────────────────
   Straight out of the OpenTerminal reference in the redesign plan: a terminal
   is keyboard-first, and the shortcuts live on screen rather than in a manual
   nobody opens. This also gives every page a floor, which is what stops the
   viewport ending in half a screen of black.

   Pages are numbered in workflow order, and a number that is not earned yet
   does nothing rather than landing you on an empty screen — the same rule the
   nav already follows. */
/* Key, href, data-page, and the name the rail gives it. The label used to be
   derived from the data-page value with a capitalise and one special case for
   `assumptions`, which worked only while the page names and the screen names
   were the same word. They are not any more — the rail says Break, Fix and
   Validate — and a keyboard panel that calls them Analysis, Defend and Verify
   is the app disagreeing with itself about what its own screens are called.

   The numbering follows the stepper, so Limit is 2 and everything after it
   shifts. Until the rail is on every page, `2` finds no link on the pages that
   still carry the old nav and does nothing there, the same as a locked page. */
const FB_PAGES = [
  ["1", "index.html", "portfolio", "Portfolio"],
  ["2", "index.html#limit", "limit", "Limit"],
  ["3", "analysis.html", "analysis", "Break"],
  ["4", "cascade.html", "cascade", "Cascade"],
  ["5", "defend.html", "defend", "Fix"],
  ["6", "verify.html", "verify", "Validate"],
  ["7", "boundary.html", "boundary", "Boundary"],
  ["8", "assumptions.html", "assumptions", "Model"],
];

/* Remembered so a repaint after the data lands keeps this page's own keys. */
let _statusExtra = null;

function paintStatusBar(current, extra) {
  if (extra !== undefined) _statusExtra = extra;
  else extra = _statusExtra;
  const s = FB.state;
  /* Repaint rather than bail. The first paint happens before the demo book has
     been fetched, so bailing left "no book loaded" sitting under a table full
     of holdings. */
  const bar = document.querySelector(".statusbar") || document.createElement("div");
  bar.className = "statusbar";
  const keys = [[`1–${FB_PAGES.length}`, "page"], ["?", "keys"]].concat(extra || []);
  bar.innerHTML = keys
    .map(([k, label]) => `<span class="k"><kbd>${k}</kbd>${label}</span>`)
    .join('<span class="sep">│</span>') +
    `<span class="right">
       <span class="k">${s.portfolio ? (s.portfolio.holdings.length + " holdings") : "no book loaded"}</span>
       <span class="sep">│</span>
       <span class="k">SEC 13F-HR · ${(s.result && s.result.params) ? "λ " + s.result.params.leverage.toFixed(1) : "Q2 2026"}</span>
     </span>`;
  if (!bar.isConnected) document.body.appendChild(bar);
}

function bindKeys(current, extraHandlers) {
  document.addEventListener("keydown", (ev) => {
    /* never steal a key from someone typing, and never from a chord the
       browser owns */
    const t = ev.target;
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;

    const page = FB_PAGES.find(([k]) => k === ev.key);
    if (page) {
      const link = document.querySelector(`.nav-links a[data-page="${page[2]}"]`);
      if (link && !link.hasAttribute("data-locked")) location.href = page[1];
      return;
    }
    if (ev.key === "?") { ev.preventDefault(); toggleKeyHelp(); return; }
    if (ev.key === "Escape") { const d = document.getElementById("keyHelp"); if (d) d.hidden = true; return; }
    if (extraHandlers && extraHandlers[ev.key]) { ev.preventDefault(); extraHandlers[ev.key](); }
  });
}

function toggleKeyHelp() {
  let d = document.getElementById("keyHelp");
  /* Built hidden, so the toggle at the end has something to flip. It used to
     be built visible and then immediately toggled off, so the FIRST press of
     `?` created the panel and hid it — the key appeared to do nothing until
     you pressed it twice, on every page. */
  if (!d) {
    d = document.createElement("div");
    d.id = "keyHelp";
    d.hidden = true;
    d.className = "keyhelp";
    d.innerHTML = `<div class="card"><div class="card-header">Keyboard</div>
      <div class="card-body tight"><table><tbody>
        ${FB_PAGES.map(([k, , , label]) =>
          `<tr><td style="width:70px"><kbd>${k}</kbd></td><td class="t">${label}</td></tr>`).join("")}
        <tr><td><kbd>←</kbd> <kbd>→</kbd></td><td class="t">Step the cascade (Cascade page)</td></tr>
        <tr><td><kbd>space</kbd></td><td class="t">Play or pause the cascade</td></tr>
        <tr><td><kbd>?</kbd></td><td class="t">This list</td></tr>
        <tr><td><kbd>esc</kbd></td><td class="t">Close</td></tr>
      </tbody></table></div></div>`;
    document.body.appendChild(d);
  }
  d.hidden = !d.hidden;
}
