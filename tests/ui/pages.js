/* The six-page product loop, driven end to end against the real server.
 *
 * This replaces smoke.js and provenance.js, which drove web/app.js — the
 * single-page app. No page in web/ loads app.js any more, so those harnesses
 * were exercising a file that never reaches a user: 612 lines and eight
 * mutation entries scoring green against dead code. A suite that reports
 * frontend coverage it does not have is worse than one that reports none.
 *
 * The pages are real separate documents that pass state through
 * sessionStorage, so this walks them the way a browser does — render a page,
 * carry its sessionStorage forward, render the next. Every assertion compares
 * what is ON SCREEN against the payload the server actually sent. That is the
 * lesson provenance.js learned the hard way: it scored 47/47 on five visibly
 * wrong numbers because it checked that sentences existed, not that they were
 * right.
 *
 *   npm --prefix tests/ui install                     # once
 *   PYTHONPATH=src python3 -m firebreak.server &
 *   node tests/ui/pages.js
 */
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.resolve(__dirname, "..", "..", "web");
const ORIGIN = "http://localhost:8765";

let failures = 0;
/* detail is printed only on failure. Hanging "X not in Y" off a [pass] line
   reads as a contradiction and trains you to skim the output. */
const check = (name, cond, detail = "") => {
  if (!cond) failures++;
  console.log(`  [${cond ? "pass" : "FAIL"}] ${name}${!cond && detail ? "  — " + detail : ""}`);
};
const eq = (name, got, want) =>
  check(name, got === want, got === want ? "" : `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
const has = (name, hay, needle) =>
  check(name, String(hay).includes(needle), String(hay).includes(needle) ? "" : `${JSON.stringify(needle)} not in ${JSON.stringify(String(hay).slice(0, 200))}`);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* Wait for a condition, not for a duration. A fixed sleep between a fetch and
   a DOM read is a bet on the server's latency, and it is the bet that made the
   old harnesses collapse to 2 passes when the fetch was delayed by 3s. */
async function until(cond, ms = 8000, step = 20) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (cond()) return true;
    await sleep(step);
  }
  return false;
}

/* Load one page the way a browser would: parse it, seed the sessionStorage a
   previous page left behind, then run shared.js and the page's own inline
   script in document order. Returns the window plus whatever navigation the
   page asked for, so a redirect is observable instead of silent. */
async function load(file, store, query = "") {
  /* the file comes off disk, the query string goes into the document's URL —
     pages read location.search, and jsdom will not find "analysis.html?x" on
     the filesystem. */
  const html = fs.readFileSync(path.join(WEB, file), "utf8")
    .replace(/<link[^>]*fonts\.googleapis[^>]*>/g, "");
  const dom = new JSDOM(html, {
    runScripts: "outside-only", pretendToBeVisual: true,
    url: ORIGIN + "/" + file + query,
  });
  const { window } = dom;

  for (const k in store) window.sessionStorage.setItem(k, store[k]);

  window.fetch = async (u, o) => {
    const r = await fetch(u.startsWith("http") ? u : ORIGIN + u, o);
    return { ok: r.ok, status: r.status, json: () => r.json() };
  };
  window.Element.prototype.animate = () => ({ finished: Promise.resolve() });
  window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  window.matchMedia = window.matchMedia ||
    (() => ({ matches: false, addListener() {}, removeListener() {} }));
  /* rAF hands its callback a performance.now() timestamp. Feeding it Date.now()
     makes every (now - started) elapsed-time easing land at k=1 on frame one,
     which is how a count-up that outlived its own run stayed invisible here. */
  window.requestAnimationFrame = (cb) => setTimeout(() => cb(window.performance.now()), 16);

  const navigated = [];
  window.location.replace = (u) => navigated.push(String(u));
  window.location.assign = (u) => navigated.push(String(u));

  const errors = [];
  window.addEventListener("error", (e) => errors.push("error: " + e.message));
  window.onerror = (m) => errors.push("onerror: " + m);

  /* Classic scripts share one global lexical environment, so `const FB` in
     shared.js is visible to the page's own script. An indirect window.eval()
     per script does NOT reproduce that — each eval gets a fresh lexical scope
     that is thrown away, and every page died on "FB is not defined". Joining
     them in document order is what the browser actually gives them. */
  const code = [...window.document.querySelectorAll("script")].map((s) => {
    const src = s.getAttribute("src");
    return src ? fs.readFileSync(path.join(WEB, src), "utf8") : s.textContent;
  }).join("\n;\n");
  try { window.eval(code); }
  catch (e) { errors.push("throw: " + e.message); }
  return { window, d: window.document, errors, navigated,
           dump: () => ({ fb: window.sessionStorage.getItem("fb") }) };
}

const txt = (d, id) => { const n = d.getElementById(id); return n ? n.textContent.trim() : null; };

/* body.textContent includes the source of every <script> in the document. A
   check that greps it for a string the page is SUPPOSED to render matches the
   line of JS that would render it, and passes before the page has done
   anything — which is exactly how "a clamped limit says so" went green against
   a document that showed no such thing. Read what a person can see. */
function visibleText(d) {
  const body = d.body.cloneNode(true);
  body.querySelectorAll("script,style,template").forEach((n) => n.remove());
  return body.textContent;
}

(async () => {
  console.log("PAGES");

  /* ---- what the server says, so every screen below has something to be
     wrong against. The pages call these same endpoints. ---- */
  const demo = await (await fetch(ORIGIN + "/api/portfolio/demo")).json();
  const full = await (await fetch(ORIGIN + "/api/portfolio/full?limit=0.10", {
    method: "POST", headers: { "content-type": "application/json" }, body: "{}",
  })).json();
  check("server returned a break point to check the screens against",
        full.found === true, full.reason || "");
  if (!full.found) { process.exit(1); }

  /* ---- 1. portfolio ---- */
  {
    const p = await load("index.html", {});
    check("index.html runs clean", p.errors.length === 0, p.errors.join("; "));
    p.d.getElementById("useDemo").dispatchEvent(new p.window.Event("click"));
    const ok = await until(() => p.d.getElementById("pfCard") &&
                                 !p.d.getElementById("pfCard").hidden);
    check("the demo portfolio renders", ok);

    eq("holdings count on screen matches the payload",
       p.d.querySelectorAll("#pfRows tr").length, demo.portfolio.holdings.length);
    const wantTotal = "$" + Math.round(demo.portfolio.total_value).toLocaleString("en-US");
    eq("total value matches the payload", txt(p.d, "pfTotal"), wantTotal);

    /* weights are a fraction server-side and a percent on screen. A page that
       forgets the ×100 still renders a plausible-looking number. */
    const firstW = demo.portfolio.holdings[0].weight;
    const cells = [...p.d.querySelectorAll("#pfRows tr")][0].querySelectorAll("td");
    eq("first holding's weight is scaled to a percent",
       cells[2].textContent.trim(), `${(firstW * 100).toFixed(1)}%`);
    check("weights are not printed as raw fractions",
          Math.abs(firstW - 1) > 1e-9 ? cells[2].textContent.trim() !== `${firstW.toFixed(1)}%` : true);

    /* The fourth column used to be a bar restating the Weight beside it. It
       carries how much of each name the five modelled books hold, in days of
       that name's own average volume — the property that decides how hard the
       cascade lands, and the reason GOOGL falls 5.31% on a shock to a
       different name. */
    const ds = await (await fetch(ORIGIN + "/api/dataset")).json();
    const daysOf = (sym) => {
      const i = ds.tickers.indexOf(sym);
      if (i < 0 || !ds.adv[i]) return null;
      return ds.holdings.reduce((a, row) => a + row[i], 0) / ds.adv[i];
    };
    await until(() => /days of volume/.test(visibleText(p.d)), 4000);
    const crowdRows = [...p.d.querySelectorAll("#pfRows tr")].map((tr) =>
      [...tr.querySelectorAll("td")].map((td) => td.textContent.trim()));
    let checkedOne = false;
    for (const row of crowdRows) {
      const want = daysOf(row[0]);
      if (want == null) { eq(`${row[0]} has no volume figure to show`, row[3], "—"); continue; }
      eq(`${row[0]}'s crowding is its institutional holdings over its own ADV`,
         row[3], `${want.toFixed(1)} days of volume`);
      checkedOne = true;
    }
    check("at least one holding was checked against the dataset", checkedOne);

    /* A <label for> is never in the tab order and the file input it wraps is
       display:none, so one of the two ways to load a portfolio could not be
       operated without a mouse. */
    const importLabel = p.d.getElementById("csvLabel");
    check("the CSV import is reachable by keyboard", !!importLabel &&
          importLabel.tabIndex >= 0, importLabel ? `tabIndex ${importLabel.tabIndex}` : "no label");
    let opened = 0;
    p.d.getElementById("csvFile").click = () => { opened++; };
    importLabel.dispatchEvent(new p.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    importLabel.dispatchEvent(new p.window.KeyboardEvent("keydown", { key: " ", bubbles: true }));
    eq("and Enter and Space both open the file picker", opened, 2);

    var store = p.dump();
  }

  /* ---- 2. analysis ---- */
  {
    const a = await load("analysis.html", store);
    check("analysis.html runs clean", a.errors.length === 0, a.errors.join("; "));
    const ok = await until(() => a.d.getElementById("resultCard") &&
                                 !a.d.getElementById("resultCard").hidden);
    check("the break point renders", ok, a.navigated.join(",") || txt(a.d, "sub") || "");

    eq("the headline shock matches the payload",
       txt(a.d, "big"), `${full.asset} −${full.pct.toFixed(2)}%`);
    has("the sub-line quotes the cascade loss the engine returned",
        txt(a.d, "bigSub"), `${(full.cascade_loss * 100).toFixed(2)}%`);

    const stats = [...a.d.querySelectorAll("#stats .v")].map((n) => n.textContent.trim());
    eq("direct loss tile", stats[0], `${(full.direct_loss * 100).toFixed(2)}%`);
    eq("after-cascade tile", stats[1], `${(full.cascade_loss * 100).toFixed(2)}%`);
    eq("amplification tile", stats[2], `${full.amplification.toFixed(2)}×`);
    eq("rounds tile", stats[3], String(full.rounds));

    /* amplification is reported by the engine, not divided out on screen. If a
       page ever recomputes it from the two losses it will drift from the
       engine's own number the moment the engine changes how it is defined. */
    check("after-cascade loss is worse than the direct loss",
          full.cascade_loss > full.direct_loss,
          `${full.cascade_loss} vs ${full.direct_loss}`);

    /* Loss attribution. Contributions are weight x fall, so they must sum to
       the portfolio loss — and the total is printed, which is what makes the
       claim checkable on screen rather than asserted in a caption. */
    {
      const w = {}; full.portfolio.holdings.forEach((h) => { w[h.symbol] = h.weight; });
      const cells = [...a.d.querySelectorAll("#attrRows tr")].map((tr) =>
        [...tr.querySelectorAll("td")].map((td) => td.textContent.trim()));
      check("the attribution table renders a row per modelled holding",
            cells.length >= Object.keys(w).length, `${cells.length} rows`);

      const total = cells.find((c) => /^Total$/i.test(c[0]));
      check("it carries a total", !!total, cells.map((c) => c[0]).join(","));
      if (total) {
        eq("and the total equals the cascade loss the engine returned",
           total[5].replace(/[^\d.]/g, ""), (full.cascade_loss * 100).toFixed(2));
      }

      /* the thesis, as an assertion: a name nobody shocked still falls. */
      const unshocked = cells.filter((c) => c[2] === "—" && !/^(Total|CASH)$/i.test(c[0]));
      check("at least one unshocked holding still loses money to contagion",
            unshocked.length > 0 && unshocked.every((c) => /\d/.test(c[4])),
            unshocked.map((c) => `${c[0]}:${c[4]}`).join(" "));

      /* and the shocked name is the one the search found, marked as such */
      const shockedRow = cells.find((c) => /shocked/i.test(c[0]));
      check("the shocked name is flagged and is the one the search found",
            !!shockedRow && shockedRow[0].startsWith(full.asset),
            shockedRow ? shockedRow[0] : "none flagged");

      /* Contagion is the fall MINUS the shock, so on the shocked name it has to
         be a small remainder. Printing the whole fall there would credit the
         cascade with damage the shock itself did — and would still look like a
         plausible number, which is why the check has to compare the two. */
      if (shockedRow) {
        const n = (t) => Number(String(t).replace(/[^\d.]/g, "")) || 0;
        check("contagion on the shocked name is the remainder, not its whole fall",
              n(shockedRow[4]) < n(shockedRow[3]) - 1,
              `contagion ${shockedRow[4]} against a total fall of ${shockedRow[3]}`);
      }
    }

    store = a.dump();
  }

  /* ---- 3. cascade ---- */
  {
    const c = await load("cascade.html", store);
    check("cascade.html runs clean", c.errors.length === 0, c.errors.join("; "));
    const ok = await until(() => c.d.querySelectorAll("#net circle").length > 0);
    check("the network draws", ok, c.navigated.join(",") || "");

    const cas = await (await fetch(ORIGIN + `/api/cascade?asset=${encodeURIComponent(full.asset)}` +
      `&magnitude=${Math.abs(full.magnitude)}&leverage=${full.params.leverage}` +
      `&gamma=${full.params.gamma}&band=${full.params.band}`)).json();

    eq("one node per modelled ticker", c.d.querySelectorAll("#net circle").length, cas.tickers.length);
    eq("one box per modelled fund", c.d.querySelectorAll("#net rect").length, cas.funds.length);

    /* An asset nobody shocked must read 0.00%, not -0.00%. The minus sign is
       written by hand in front of the formatter, so a price of exactly 1.0
       used to render as a loss of negative zero. */
    const labels = [...c.d.querySelectorAll("#net text")].map((n) => n.textContent);
    check("no asset reports a negative zero", !labels.some((t) => t === "−0.00%"),
          labels.filter((t) => /0\.00%/.test(t)).join(" "));
    /* A name that has not moved shows nothing rather than 0.00%: nine of ten
       reading zero is dead ink, and it made the frame where contagion arrives
       look identical to the one before it. */
    check("an unmoved name shows no figure at all", !labels.some((t) => t === "0.00%"),
          labels.filter((t) => t === "0.00%").length + " zeros drawn");

    /* Rows are ordered by how much institutional money sits in each name, so
       the crowded ones are at the top and position on screen is an argument. */
    const own = cas.tickers.map((_, i) => cas.holdings.reduce((a, r) => a + r[i], 0));
    const drawn = [...c.d.querySelectorAll("#net text")]
      .filter((n) => cas.tickers.includes(n.textContent))
      .sort((a, b) => Number(a.getAttribute("y")) - Number(b.getAttribute("y")))
      .map((n) => n.textContent);
    const wanted = cas.tickers.map((t, i) => [t, own[i]])
      .sort((a, b) => b[1] - a[1]).map((x) => x[0]);
    eq("the most crowded name is drawn at the top", drawn[0], wanted[0]);
    eq("and the rows are in crowding order throughout", drawn.join(","), wanted.join(","));

    const f0 = cas.trajectory[0];
    const shocked = cas.tickers[f0.prices.findIndex((p) => p < 1 - 1e-9)];
    eq("the shocked name on screen is the one the search found", shocked, full.asset);
    const wantDrop = `−${((1 - Math.min(...f0.prices)) * 100).toFixed(2)}%`;
    check("the shocked name's drop matches the trajectory", labels.includes(wantDrop),
          `${wantDrop} not among ${labels.filter((t) => /%/.test(t)).join(" ")}`);

    /* The round log narrates `breached`, which is a STATE (who was over the
       limit at the start of the round), and it must not be read out as a
       transition. A book already over at round t-1 has not "crossed" at t. */
    const lines = [...c.d.querySelectorAll("#log tr")].map((tr) =>
      tr.textContent.replace(/\s+/g, " ").trim());
    eq("one log line per trajectory frame", lines.length, cas.trajectory.length);
    for (let t = 2; t < cas.trajectory.length; t++) {
      const prev = new Set(cas.trajectory[t - 1].breached || []);
      const carried = (cas.trajectory[t].breached || [])
        .filter((j) => prev.has(j)).map((j) => cas.funds[j]);
      const said = lines[t] || "";
      const crossed = said.split(";")[0];
      const wrong = carried.filter((n) => crossed.includes(n) && /crossed/.test(crossed));
      check(`round ${t} does not say a book crossed when it was already over`,
            wrong.length === 0, `${wrong.join(", ")} in: ${said}`);
    }

    /* The animation had never been driven in a test — only screenshotted at
       rest, which proves the idle state and nothing else. Step it with Next
       rather than Play so the assertions are not racing a 900ms interval, and
       check the loss tile against a loss computed here from the trajectory's
       own prices rather than against the number the page derived. */
    {
      const w = {}; full.portfolio.holdings.forEach((h) => { w[h.symbol] = h.weight; });
      const vec = cas.tickers.map((t) => w[t] || 0);
      const cashW = w.CASH || 0;
      const lossAt = (prices) =>
        1 - (vec.reduce((a, v, i) => a + v * prices[i], 0) + cashW);
      const round = () => c.d.querySelector(".card-header").textContent;
      const tile = (k) => [...c.d.querySelectorAll(".stat")]
        .find((n) => n.querySelector(".k").textContent.toLowerCase().includes(k))
        .querySelector(".v").textContent.trim();

      eq("it opens on the shock, before any selling", tile("round"),
         `0 / ${cas.trajectory.length - 1}`);

      /* The diagram's edges used to be drawn from static position sizes in a
         fixed grey, so every frame came out identical — fifty lines redrawn
         each tick to look exactly the same, while `sold` sat in the payload
         carrying the actual cascade. The flow layer has to move with it. */
      const step = (t) => {
        c.d.getElementById("playBtn").dispatchEvent(new c.window.Event("click"));  // home
        c.d.getElementById("playBtn").dispatchEvent(new c.window.Event("click"));  // stop
        for (let k = 0; k < t; k++)
          c.d.getElementById("nextBtn").dispatchEvent(new c.window.Event("click"));
      };
      const flow = () => [...c.d.querySelectorAll("#net line")]
        .filter((l) => (l.getAttribute("stroke") || "").includes("359"));
      const soldAt = (t) => (cas.trajectory[t].sold || []).flat().filter((v) => v > 0).length;
      eq("no forced selling is drawn on the shock frame", flow().length, soldAt(0));
      for (let t = 0; t < cas.trajectory.length; t++) {
        if (t > 0) {
          c.d.getElementById("nextBtn").dispatchEvent(new c.window.Event("click"));
          await sleep(30);
        }
        eq(`round ${t}: the counter matches the frame shown`, tile("round"),
           `${t} / ${cas.trajectory.length - 1}`);
        eq(`round ${t}: books over limit matches the trajectory`,
           tile("over limit"), String((cas.trajectory[t].breached || []).length));
        eq(`round ${t}: the loss shown is the loss at that frame's prices`,
           tile("loss so far"), `${(lossAt(cas.trajectory[t].prices) * 100).toFixed(2)}%`);
        eq(`round ${t}: one flow edge per sale the engine actually made`,
           flow().length, soldAt(t));
      }
      /* Deleveraging chasing itself down to nothing is the one idea this page
         exists to land, so the picture has to get quieter as it goes. */
      const widest = [];
      for (let t = 0; t < cas.trajectory.length; t++) {
        const total = (cas.trajectory[t].sold || []).flat().reduce((a, b) => a + b, 0);
        widest.push(total);
      }
      check("the forced selling peaks in the first round and decays after it",
            widest[1] > 0 && widest.slice(1).every((v, i, a) => i === 0 || v < a[i - 1]),
            widest.map((v) => (v / 1e9).toFixed(2) + "B").join(" -> "));

      /* And the DRAWING has to decay with it. Scaling each frame to its own
         busiest edge makes the last round's trickle as thick as the first
         round's flood — the picture then says the cascade never weakens, which
         is the opposite of what it exists to show. Counting edges cannot see
         that; the widths have to be compared across rounds. */
      const widestStroke = [];
      for (let t = 0; t < cas.trajectory.length; t++) {
        step(t);
        await sleep(20);
        widestStroke.push(Math.max(0, ...flow().map((l) => Number(l.getAttribute("stroke-width")))));
      }
      check("and the drawing decays with it, rather than rescaling each frame",
            widestStroke[1] > widestStroke[widestStroke.length - 1] * 1.5,
            widestStroke.map((v) => v.toFixed(2)).join(" -> "));

      /* the last frame has to be the answer the rest of the app reports, or the
         animation is telling a different story from every other page. */
      check("the final round's loss is the cascade loss the engine returned",
            Math.abs(lossAt(cas.trajectory[cas.trajectory.length - 1].prices) - full.cascade_loss) < 5e-5,
            `${lossAt(cas.trajectory[cas.trajectory.length - 1].prices)} vs ${full.cascade_loss}`);

      for (let i = 0; i < 3; i++)
        c.d.getElementById("nextBtn").dispatchEvent(new c.window.Event("click"));
      await sleep(30);
      eq("Next past the end stays on the last frame", tile("round"),
         `${cas.trajectory.length - 1} / ${cas.trajectory.length - 1}`);

      c.d.getElementById("playBtn").dispatchEvent(new c.window.Event("click"));
      await sleep(60);
      eq("Play from the end restarts at the shock", tile("round"),
         `0 / ${cas.trajectory.length - 1}`);
      c.d.getElementById("playBtn").dispatchEvent(new c.window.Event("click"));  // stop the timer

      /* Prev and Next used to leave the timer running, so stepping during
         playback raced it: three Nexts inside one 900ms tick landed on the
         last frame with the button reading "Replay", reporting a playthrough
         in which the middle rounds were never drawn. */
      const btn = () => c.d.getElementById("playBtn").textContent;
      c.d.getElementById("playBtn").dispatchEvent(new c.window.Event("click"));
      for (let i = 0; i < cas.trajectory.length; i++)
        c.d.getElementById("nextBtn").dispatchEvent(new c.window.Event("click"));
      await sleep(250);
      eq("stepping during playback takes over from the timer", tile("round"),
         `${cas.trajectory.length - 1} / ${cas.trajectory.length - 1}`);
      eq("and the button describes where we actually are", btn(), "Replay");

      c.d.getElementById("prevBtn").dispatchEvent(new c.window.Event("click"));
      await sleep(30);
      eq("stepping back off the end stops saying Replay", btn(), "Play");
      eq("and shows the frame before the last", tile("round"),
         `${cas.trajectory.length - 2} / ${cas.trajectory.length - 1}`);
    }

    /* A cascade that settles on the shock alone has one frame and nothing to
       animate. Play used to fire the interval once, clamp and relabel — a
       900ms pause pretending to be a playthrough. */
    {
      const rows = [{ symbol: "NVDA", market_value: 100000 }];
      const one = await (await fetch(ORIGIN + "/api/portfolio/full?limit=0.03", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ holdings: rows, source: "csv" }),
      })).json();
      const onecas = one.found && await (await fetch(ORIGIN +
        `/api/cascade?asset=${one.asset}&magnitude=${Math.abs(one.magnitude)}` +
        `&leverage=${one.params.leverage}&gamma=${one.params.gamma}&band=${one.params.band}`)).json();
      if (onecas && onecas.trajectory.length === 1) {
        const z = await load("cascade.html", { fb: JSON.stringify(
          { portfolio: one.portfolio, rows, limit: 0.03, result: one }) });
        await until(() => z.d.querySelectorAll("#net circle").length > 0);
        check("a one-frame cascade renders without error", z.errors.length === 0,
              z.errors.join("; "));
        const zt = [...z.d.querySelectorAll(".stat")]
          .find((n) => n.querySelector(".k").textContent.toLowerCase().includes("round"))
          .querySelector(".v").textContent.trim();
        eq("and counts itself honestly", zt, "0 / 0");
        eq("and offers Replay rather than a playthrough that cannot happen",
           z.d.getElementById("playBtn").textContent, "Replay");
        /* and pressing it must not arm an interval that has nowhere to go —
           one tick, a clamp and a relabel is a 900ms pause pretending to be an
           animation. Checking the label alone misses that entirely. */
        z.d.getElementById("playBtn").dispatchEvent(new z.window.Event("click"));
        eq("pressing Play on a one-frame cascade settles immediately",
           z.d.getElementById("playBtn").textContent, "Replay");
        await sleep(1100);
        eq("and is still settled a tick later, having armed nothing",
           z.d.getElementById("playBtn").textContent, "Replay");
      } else {
        check("a one-frame cascade is still reachable to test", false,
              "no single-frame trajectory found; the checks above did not run");
      }
    }

    store = c.dump();
  }

  /* ---- 4. defend ---- */
  {
    const v = await load("defend.html", store);
    check("defend.html runs clean", v.errors.length === 0, v.errors.join("; "));
    const ok = await until(() => v.d.getElementById("root").textContent.trim().length > 40);
    check("the fix renders", ok, v.navigated.join(",") || "");
    const body = v.d.getElementById("root").textContent;

    if (full.fix) {
      has("the fix names the position the solver picked", body, full.fix.symbol);
      has("the dollar size of the cut matches the solver",
          body, "$" + Math.round(full.fix.dollars).toLocaleString("en-US"));
      has("the loss before the fix is the one that breached", body,
          `${(full.validation.identical_shock.before_loss * 100).toFixed(2)}%`);
      has("the loss after the fix is the one the replay scored", body,
          `${(full.validation.identical_shock.after_loss * 100).toFixed(2)}%`);
      /* the whole promise of the product: after < limit <= before */
      check("the fix actually lands the portfolio under its own limit",
            full.validation.identical_shock.after_loss < full.params.limit + 1e-12,
            `${full.validation.identical_shock.after_loss} vs ${full.params.limit}`);
    } else {
      has("a refusal says so instead of printing a fix", body, "No single-position change");
    }
    store = v.dump();
  }

  /* ---- 5. verify ---- */
  {
    const v = await load("verify.html", store);
    check("verify.html runs clean", v.errors.length === 0, v.errors.join("; "));
    const ok = await until(() => visibleText(v.d).includes("%"));
    check("the evidence renders", ok, v.navigated.join(",") || "");
    const body = visibleText(v.d);
    const val = full.validation;

    has("the replayed shock is the same shock", body, `${full.pct.toFixed(2)}%`);
    has("the new break point is on screen", body, `${val.new_breaking_point.after_pct.toFixed(2)}%`);
    check("the new break point is further out than the old one",
          val.new_breaking_point.after_pct > val.new_breaking_point.before_pct,
          `${val.new_breaking_point.after_pct} vs ${val.new_breaking_point.before_pct}`);

    /* Survival is printed as a count out of the scenarios, not a rounded
       percentage: 98% and 99% are 392/400 and 396/400, and at a 5% limit the
       same rounding turns 80.25 and 80.75 into 80% and 81% — a difference of
       two scenarios, invisible. */
    const syn = val.synthetic;
    has("survival is a count of scenarios, not a rounded percentage", body,
        `${Math.round(syn.before.survival * syn.scenarios)} / ${syn.scenarios}`);
    has("and the defended count too", body,
        `${Math.round(syn.after.survival * syn.scenarios)} / ${syn.scenarios}`);
    /* the draws have a range and it is reported; the page must quote it
       rather than leave "400 simulated stresses" unqualified. */
    if (syn.shock_range_pct) {
      has("the range the shocks were drawn from is on screen", body,
          `${syn.shock_range_pct[0]}–${syn.shock_range_pct[1]}%`);
    }

    /* historical replay ships no data, and the page must say so rather than
       print a number computed from returns nobody has. */
    if (val.historical && val.historical.available === false) {
      check("historical replay is declared unavailable, not faked",
            /not available|No price history/i.test(body));
      check("and prints no percentage of its own",
            !/historical[^%]{0,400}\d+\.\d+%/i.test(body));
    }
    store = v.dump();
  }

  /* ---- 6. assumptions ---- */
  {
    const a = await load("assumptions.html", store);
    check("assumptions.html runs clean", a.errors.length === 0, a.errors.join("; "));
    check("the model page has content", visibleText(a.d).trim().length > 200);

    /* The solver strip. docs/devpost.md claims the engine name, evaluation
       count and exit flag are on screen; this is the check that keeps that
       claim true, since the redesign silently dropped them once already. */
    /* The card hardcoded its knobs and omitted `breaches` entirely, so it
       answered a 2-breach question while the pitch quotes the 3-breach one —
       Renaissance's $441,665 against Citadel's $1,731,560, four clicks apart
       with no label on either. It has to describe the run this session did. */
    const kp = full.params;
    const st = await (await fetch(ORIGIN +
      `/api/stabilise?leverage=${kp.leverage}&gamma=${kp.gamma}&band=${kp.band}` +
      `&breaches=${kp.breaches}&asset=0`)).json();
    const shown = await until(() => a.d.getElementById("engineCard") &&
                                    !a.d.getElementById("engineCard").hidden);
    check("the solver provenance card renders", shown);
    const eb = a.d.getElementById("engineRows").textContent;
    has("the engine names itself", eb, st.engine.name);
    has("the evaluation count is the solver's own", eb, String(st.engine.evaluations));
    has("the exit flag is the solver's own", eb, String(st.engine.exit_flag));
    /* solve_ms is a live wall-clock measurement — the page's solve and this
       harness's are two different runs, so the exact figure will not match and
       asserting it would be flaky. What matters is that a missing timing says
       so instead of rendering as 0 ms. */
    check("the solve time is a duration, or says it was not recorded",
          st.engine.solve_ms != null ? /\b\d+(\.\d+)? ms\b/.test(eb)
                                     : eb.includes("not recorded"), eb.slice(0, 200));
    has("the card names the breach count it is answering", eb, `${kp.breaches}+ breaching`);
    has("and the patch it found, which is what the pitch quotes", eb, st.fix.fund);
    has("with the dollar figure from that same scenario", eb,
        "$" + Math.round(st.fix.sell_usd).toLocaleString("en-US"));

    if (st.bought && st.bought.measurable === false) {
      has("an unmeasurable change is reported as unmeasurable, not as a number",
          eb, "no measurable change");
    }
  }

  /* ---- the CSV parser ---- */
  {
    /* It had no coverage at all. The old version was line.split(",") and an
       unanchored /market_?value|value/ over findIndex, which takes the
       LEFTMOST match — so a file with a cost-basis column left of its
       market-value column priced the whole book off the cost basis, and said
       "Loaded 4 holdings". */
    const p = await load("index.html", {});
    const parse = p.window.parseCsv;
    check("index.html exposes a parser that can be driven directly", typeof parse === "function");

    const ok = (name, text, expect) => {
      try {
        const got = parse(text).rows.map((r) => `${r.symbol}=${r.market_value ?? (r.quantity + "x" + r.price)}`).join(",");
        eq(name, got, expect);
      } catch (e) { check(name, false, "refused: " + e.message); }
    };
    const refuses = (name, text, needle) => {
      try { parse(text); check(name, false, "accepted it"); }
      catch (e) { check(name, e.message.includes(needle), `message was: ${e.message}`); }
    };

    ok("a real market_value column wins over a cost-basis column to its left",
       "symbol,book_value,market_value\nNVDA,1,3600\nMSFT,2,3150", "NVDA=3600,MSFT=3150");
    ok("quoted thousands separators survive",
       'symbol,market_value\nNVDA,"3,600"\nMSFT,"3,150"', "NVDA=3600,MSFT=3150");
    ok("a BOM and CRLF do not break the header",
       "\uFEFFsymbol,market_value\r\nNVDA,3600\r\nMSFT,3150", "NVDA=3600,MSFT=3150");
    ok("quantity and price with no value column",
       "symbol,quantity,price\nNVDA,20,180", "NVDA=20x180");

    /* These strings are set with textContent, so a backtick is a backtick on
       screen — seven of them were reaching the user as literal punctuation
       around words like `symbol`. */
    const errorText = (text) => { try { parse(text); return ""; } catch (e) { return e.message; } };
    check("error messages carry no literal markdown backticks",
          !["symbol,market_value\nNVDA,3,600", "ticker,foo\nNVDA,1",
            "symbol,book_value\nNVDA,1200", "symbol,market_value\nNVDA,-1"]
            .some((t) => errorText(t).includes("`")),
          ["symbol,book_value\nNVDA,1200"].map(errorText).join(" | "));

    refuses("an unquoted 3,600 is refused, not read as 3",
            "symbol,market_value\nNVDA,3,600\nMSFT,3,150", "fields where the header has");
    refuses("a market value that disagrees with quantity x price is refused",
            "symbol,quantity,price,market_value\nNVDA,20,180,9999", "two different claims");
    refuses("a negative market value is refused",
            "symbol,market_value\nNVDA,-3600\nMSFT,3150\nCASH,1050", "negative market value");
    refuses("an accounting negative is refused too",
            "symbol,market_value\nNVDA,(3600)\nMSFT,3150", "negative market value");
    refuses("a cost-basis column alone is named, not silently used",
            "symbol,book_value\nNVDA,1200", "book_value");
    refuses("an unreadable number is refused rather than becoming NaN",
            "symbol,market_value\nNVDA,n/a", "not a number");

    /* A real Fidelity Positions export. Every quirk in here is one the file
       actually has: "Current Value" rather than market_value, dollar signs and
       quoted thousands, a settlement fund suffixed with **, a "Pending
       Activity" line that is not a holding, and two lines of legal footer. */
    const FIDELITY = [
      "Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Percent Of Account,Cost Basis Total,Type",
      'Z12345678,INDIVIDUAL,NVDA,NVIDIA CORP,20.000,$180.00,"$3,600.00",29.27%,"$2,700.00",Cash',
      'Z12345678,INDIVIDUAL,MSFT,MICROSOFT CORP,7.000,$450.00,"$3,150.00",25.61%,"$3,000.00",Cash',
      'Z12345678,INDIVIDUAL,SPAXX**,FIDELITY GOVERNMENT MONEY MARKET,1050.000,$1.00,"$1,050.00",8.54%,"$1,050.00",Cash',
      "Z12345678,INDIVIDUAL,Pending Activity,,,,$0.00,0.00%,,",
      '"Brokerage services are provided by Fidelity Brokerage Services LLC (FBS), Member NYSE, SIPC."',
      '"Date downloaded 09/12/2026 6:41 PM ET"',
    ].join("\n");
    const fid = (() => { try { return parse(FIDELITY); } catch (e) { return { error: e.message }; } })();
    check("a Fidelity positions export parses", !fid.error, fid.error);
    if (!fid.error) {
      eq("its Current Value column is read as the market value",
         fid.rows.map((r) => `${r.symbol}=${r.market_value}`).join(","),
         "NVDA=3600,MSFT=3150,CASH=1050");
      eq("the settlement fund is counted as cash", fid.cashRolled, 1);
      eq("the Pending Activity line is set aside", fid.skipped, 1);
      eq("and the legal footer is not mistaken for data", fid.footer, 2);
    }
    /* The footer rule must not eat real rows: a two-column file's data rows are
       also "narrow", and stripping them left "header row only — no holdings". */
    const narrow = parse("symbol,market_value\nNVDA,3600\nCASH,1050");
    eq("a two-column file keeps both of its rows", narrow.rows.length, 2);
    eq("and reports no footer", narrow.footer, 0);

    const blank = parse("symbol,market_value\nNVDA,3600\nMSFT,3150\n,6750");
    eq("a row with no symbol is skipped", blank.rows.length, 2);
    eq("and counted, so the note can say so", blank.skipped, 1);
  }

  /* ---- a limit the engine had to pull into range ---- */
  {
    /* The nav reads the limit from state and the page reads the one the engine
       used. If those are allowed to diverge, a clamped limit puts 95% and 90%
       on the same screen with nothing to reconcile them. */
    const c = await load("analysis.html", {}, "?demo&limit=0.95");
    /* Assert the two NUMBERS rather than a sentence — the wording of this
       notice has already changed once, and a check pinned to prose fails on an
       edit that improves it while missing one that drops a figure. */
    const ok = await until(() => /\b95%/.test(visibleText(c.d)));
    check("a clamped limit says so instead of silently using another number", ok,
          visibleText(c.d).trim().slice(0, 200));
    const seen = visibleText(c.d);
    check("and names both the limit asked for and the one used",
          /\b95%/.test(seen) && /\b90%/.test(seen), seen.slice(0, 200));
    const navLimit = txt(c.d, "navLimit") || "";
    check("the nav shows the limit the engine used, not the one that was refused",
          navLimit.includes("90"), navLimit);
  }

  /* ---- 6. boundary ---- */
  {
    /* /api/boundary computed this grid for the whole life of the project and
       nothing fetched it. Every number on the page has to come off the payload
       rather than out of the drawing. */
    const bd = await load("boundary.html", store);
    check("boundary.html runs clean", bd.errors.length === 0, bd.errors.join("; "));
    const drew = await until(() => bd.d.querySelectorAll("#map rect[data-i]").length > 0);
    check("the map draws", drew, bd.navigated.join(",") || "");

    const kp = full.params;
    const b = await (await fetch(ORIGIN +
      `/api/boundary?leverage=${kp.leverage}&gamma=${kp.gamma}&band=${kp.band}`)).json();
    const cells = [...bd.d.querySelectorAll("#map rect[data-i]")];
    eq("one cell per computed pair", cells.length, b.grid.length * b.overlap_axis.length);

    /* the fill IS the reading, so it has to follow the value */
    const band = (a) => a < 1.0005 ? "#111111" : a < 1.5 ? "#603800"
      : a < 2.0 ? "#a46400" : a < 2.5 ? "#ea9602" : "#ffd083";
    const wrong = cells.filter((c) =>
      c.getAttribute("fill") !== band(b.grid[+c.dataset.i][+c.dataset.j]));
    check("every cell's colour matches its own amplification", wrong.length === 0,
          wrong.slice(0, 3).map((c) => `[${c.dataset.i},${c.dataset.j}] ${c.getAttribute("fill")}`).join(" "));

    /* the readings down the column the real books actually sit in */
    const jN = b.overlap_axis.reduce((k, o, j) =>
      Math.abs(o - b.here.overlap) < Math.abs(b.overlap_axis[k] - b.here.overlap) ? j : k, 0);
    const col = b.grid.map((r) => r[jN]);
    const iC = col.findIndex((a) => a >= 1.5);
    const tile = (k) => [...bd.d.querySelectorAll(".stat")]
      .find((n) => n.querySelector(".k").textContent.toLowerCase().includes(k))
      .querySelector(".v").textContent.trim();

    eq("critical leverage is the first computed row over 1.5x",
       tile("critical leverage"), `${b.leverage_axis[iC].toFixed(2)}×`);
    eq("the headroom is that row minus where the books actually are",
       tile("headroom"),
       `${b.leverage_axis[iC] - b.here.leverage >= 0 ? "+" : "−"}${Math.abs(b.leverage_axis[iC] - b.here.leverage).toFixed(2)}×`);
    eq("the count of amplifying cells is counted, not asserted",
       tile("cells over"),
       `${b.grid.flat().filter((a) => a >= 1.5).length} / ${b.grid.flat().length}`);
    eq("the worst cell is the maximum of the grid",
       tile("worst"), `${Math.max(...b.grid.flat()).toFixed(2)}×`);

    /* the table is the map's key, so its column has to be the map's column */
    const rows = [...bd.d.querySelectorAll("#rows tr")].map((tr) =>
      [...tr.querySelectorAll("td")].map((td) => td.textContent.trim()));
    eq("a table row per leverage", rows.length, b.leverage_axis.length);
    const top = rows[0];
    check("the table runs top-down from the highest leverage",
          top[0].startsWith(b.leverage_axis[b.leverage_axis.length - 1].toFixed(2)), top[0]);
    check("and its middle column is the same column the tiles read",
          top[1].includes(b.grid[b.grid.length - 1][jN].toFixed(2)), top[1]);

    /* the contour is drawn on cell edges — an interpolated curve would be a
       line through points the model never computed, on a page whose own
       header says nothing is interpolated. */
    let crossings = 0;
    for (let i = 0; i < b.grid.length; i++)
      for (let j = 0; j < b.overlap_axis.length - 1; j++)
        if ((b.grid[i][j] >= 1.5) !== (b.grid[i][j + 1] >= 1.5)) crossings++;
    for (let i = 0; i < b.grid.length - 1; i++)
      for (let j = 0; j < b.overlap_axis.length; j++)
        if ((b.grid[i][j] >= 1.5) !== (b.grid[i + 1][j] >= 1.5)) crossings++;
    const contour = [...bd.d.querySelectorAll("#map line")]
      .filter((l) => (l.getAttribute("stroke") || "") === "#d9d9d9");
    eq("one contour segment per edge the threshold actually crosses",
       contour.length, crossings);

    /* the marker is placed by value: 5.0x is not a row and 0.7117 is not a
       column, so snapping it to the nearest cell would put it where the books
       are not. */
    const marker = [...bd.d.querySelectorAll("#map circle")]
      .find((c) => c.getAttribute("r") === "5.5");
    check("the map marks where the books actually are", !!marker);
    if (marker) {
      const my = Number(marker.getAttribute("cy"));
      const rowY = (i) => 458 - 28 * (i + 1) + 14;
      const iLo = b.leverage_axis.findIndex((l) => l > b.here.leverage) - 1;
      check("and places it between two rows rather than on one",
            my < rowY(iLo) && my > rowY(iLo + 1),
            `marker at ${my}, rows at ${rowY(iLo)} and ${rowY(iLo + 1)}`);
    }
  }

  /* ---- a partly-modelled book, and the disclosure that must follow it ---- */
  {
    /* A real brokerage export is mostly funds outside the ten-name universe —
       half a Fidelity book is often one S&P ETF. Excluding them is offered
       with its price attached, and the note then has to appear on every page
       that shows a number about what is left. A disclosure that appears only
       where you agreed to it stops being one the moment you click through. */
    const rows = [
      { symbol: "VOO", market_value: 13000 }, { symbol: "NVDA", market_value: 3600 },
      { symbol: "MSFT", market_value: 3150 }, { symbol: "VTI", market_value: 5220 },
      { symbol: "CASH", market_value: 6030 },
    ];
    const post = (q) => fetch(ORIGIN + q, { method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ holdings: rows, source: "csv" }) }).then((r) => r.json());

    const refused = await post("/api/portfolio/full?limit=0.10");
    check("an unmodellable book is refused", refused.refused === true);
    const kept = await post("/api/portfolio/full?limit=0.10&exclude_unmodelled=1");
    check("and can be answered on the modellable part when asked", kept.found === true,
          kept.reason || "");

    const seeded = { fb: JSON.stringify({ portfolio: kept.portfolio, rows,
      limit: 0.10, excludeUnmodelled: true, result: kept }) };
    for (const page of ["cascade.html", "defend.html", "verify.html",
                        "boundary.html", "assumptions.html"]) {
      const pg = await load(page, seeded);
      await until(() => !!pg.d.getElementById("exclBanner"), 4000);
      const banner = pg.d.getElementById("exclBanner");
      check(`${page} says what was left out of its numbers`, !!banner,
            "no exclusion banner");
      if (banner) {
        const t = banner.textContent;
        check(`${page} names the excluded holdings and the share`,
              t.includes("VOO") && t.includes("VTI") && /58\.8%/.test(t),
              t.replace(/\s+/g, " ").slice(0, 110));
      }
    }

    /* and it must NOT appear when nothing was excluded */
    const clean = await load("defend.html", store);
    await sleep(250);
    check("a fully modelled book carries no such banner",
          !clean.d.getElementById("exclBanner"));
  }

  /* ---- the demo path, walked rather than deep-linked ---- */
  {
    /* Every check above seeds sessionStorage and loads one page. This is the
       route a presenter actually takes: cold browser, click the button, follow
       the call to action on each screen. It is the one thing that must not be
       broken five minutes before a demo, and nothing was testing it — a CTA
       pointing at the wrong page would have passed everything else here. */
    const next = (doc, re) => [...doc.querySelectorAll("a.btn")]
      .find((b) => re.test(b.textContent));

    let p = await load("index.html", {});
    p.d.getElementById("useDemo").dispatchEvent(new p.window.Event("click"));
    const loaded = await until(() => p.d.querySelectorAll("#pfRows tr").length > 0);
    check("cold start: the demo book loads from the button", loaded, p.errors.join("; "));
    const run = next(p.d, /run reverse stress test/i);
    check("and offers the run", !!run && run.getAttribute("href") === "analysis.html",
          run ? run.getAttribute("href") : "no CTA");

    let carried = p.dump();
    const legs = [
      ["analysis.html", /see why the loss grows/i, "cascade.html", () =>
        (txt(legDoc, "big") || "").includes(full.asset)],
      ["cascade.html", /cheapest single-position fix/i, "defend.html", () =>
        legDoc.querySelectorAll("#net circle").length > 0],
      ["defend.html", /check it actually helped/i, "verify.html", () =>
        legDoc.getElementById("root").textContent.includes(full.fix.symbol)],
    ];
    var legDoc = null;
    for (const [page, ctaRe, wantsHref, ready] of legs) {
      const leg = await load(page, carried);
      legDoc = leg.d;
      const ok = await until(ready);
      check(`${page} renders on the way through`, ok, leg.errors.join("; "));
      check(`${page} runs clean on the way through`, leg.errors.length === 0,
            leg.errors.join("; "));
      const cta = next(leg.d, ctaRe);
      check(`${page} offers the next step`, !!cta && cta.getAttribute("href") === wantsHref,
            cta ? `${cta.textContent.trim()} -> ${cta.getAttribute("href")}` : "no CTA matched");
      carried = leg.dump();
    }

    const end = await load("verify.html", carried);
    const arrived = await until(() => end.d.querySelectorAll("#root .card").length >= 4);
    check("and the walk ends on the evidence", arrived, end.errors.join("; "));
  }

  /* ---- the nav must not offer a page the state cannot answer ---- */
  {
    /* Arriving here with no analysis must produce the explicit "nothing to
       show yet" state — never an empty network, which reads as "no contagion"
       rather than "no answer". */
    const cold = await load("cascade.html", {});
    await sleep(300);
    check("a cold visit to cascade.html says there is no analysis yet",
          /No analysis yet/i.test(visibleText(cold.d)),
          visibleText(cold.d).trim().slice(0, 120));
    check("and draws no network, which would read as an all-clear",
          cold.d.querySelectorAll("#net circle").length === 0,
          cold.d.querySelectorAll("#net circle").length + " nodes drawn");

    const nav = await load("index.html", {});
    const locked = [...nav.d.querySelectorAll('.nav-links a[data-locked]')].map((n) => n.dataset.page);
    check("with no result, the downstream pages are locked in the nav",
          ["analysis", "cascade", "defend", "verify"].every((p) => locked.includes(p)),
          "locked: " + locked.join(","));
    /* A page absent from paintNav's map reads as undefined and gets locked.
       `assumptions` was missing, so ui.css's pointer-events:none killed the
       Model link on all six pages including its own — the methodology was
       reachable only by typing the URL. */
    check("the Model link is never locked — it needs no analysis to be true",
          !locked.includes("assumptions"), "locked: " + locked.join(","));
  }

  /* ---- a result must not outlive the question it answered ---- */
  {
    /* index.html wrote portfolio/limit and left `result` alone, so the nav kept
       Cascade/Defend/Verify unlocked and they rendered the PREVIOUS book. The
       server refuses this mix-up by design; it used to happen on the client. */
    const other = { symbol: "JPM", market_value: 50000 };
    const stale = JSON.parse(store.fb);
    const p = await load("index.html", {
      fb: JSON.stringify({ ...stale,
        portfolio: { source: "csv", total_value: 100000,
          holdings: [other, { symbol: "CASH", market_value: 50000, weight: 0.5 }] }}),
    });
    await sleep(200);
    const st = JSON.parse(p.window.sessionStorage.getItem("fb") || "{}");
    check("a new book drops the answer computed for the old one", !st.result,
          st.result ? "result kept: " + (st.result.asset || "?") : "");

    const p2 = await load("index.html", { fb: store.fb });
    await sleep(200);
    const kept = JSON.parse(p2.window.sessionStorage.getItem("fb") || "{}");
    check("but returning to the page with the same book keeps its answer", !!kept.result);

    p2.d.querySelector('#limits button[data-limit="0.25"]')
      .dispatchEvent(new p2.window.Event("click", { bubbles: true }));
    await sleep(200);
    const moved = JSON.parse(p2.window.sessionStorage.getItem("fb") || "{}");
    check("changing the limit drops an answer computed for the old limit", !moved.result,
          moved.result ? "kept" : "");
    const pressed = [...p2.d.querySelectorAll("#limits button")]
      .filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.limit);
    eq("and the control shows the limit that is actually set", pressed.join(","), "0.25");
  }

  /* ---- the best possible outcome must still render ---- */
  {
    /* When the defended book has no break point in the tested range the engine
       sends after_pct: null and omits moved_pp. Four .toFixed calls on those
       threw inside the template literal, so root.innerHTML never assigned and
       verify rendered its heading over an empty page — blank exactly when the
       fix worked best. */
    const rows = [{ symbol: "NVDA", market_value: 25000 }, { symbol: "CASH", market_value: 75000 }];
    const safeFull = await (await fetch(ORIGIN + "/api/portfolio/full?limit=0.15", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ holdings: rows, source: "csv" }),
    })).json();
    const nb = safeFull.validation && safeFull.validation.new_breaking_point;
    if (safeFull.found && nb && nb.after_unbreakable) {
      const v = await load("verify.html", { fb: JSON.stringify(
        { portfolio: safeFull.portfolio, rows, limit: 0.15, result: safeFull }) });
      const ok = await until(() => v.d.getElementById("root").children.length > 0);
      check("verify renders when the defended book has no break point in range", ok,
            v.errors.join("; "));
      check("and it runs clean", v.errors.length === 0, v.errors.join("; "));
      const body = visibleText(v.d);
      check("it says there is none in range rather than printing NaN or a null",
            /none in range/.test(body) && !/NaN|null|undefined/.test(body),
            body.slice(0, 220));
    } else {
      check("the unbreakable case is still reachable to test", false,
            "no book produced after_unbreakable; the check above is not running");
    }
  }

  /* ---- the before/after table has to add up ---- */
  {
    /* The proceeds go to cash. A book with no CASH row had nowhere to put them,
       so the Defended column came up short by the size of the cut, directly
       under the sentence saying the portfolio is worth the same afterwards. */
    const rows = [{ symbol: "NVDA", market_value: 50000 }, { symbol: "JPM", market_value: 50000 }];
    const noCash = await (await fetch(ORIGIN + "/api/portfolio/full?limit=0.10", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ holdings: rows, source: "csv" }),
    })).json();
    check("a book with no cash row still gets a fix to check", !!noCash.fix, noCash.reason || "");
    if (noCash.fix) {
      const v = await load("defend.html", { fb: JSON.stringify(
        { portfolio: noCash.portfolio, rows, limit: 0.10, result: noCash }) });
      await until(() => v.d.querySelectorAll("#root tbody tr").length > 0);
      const cells = [...v.d.querySelectorAll("#root tbody tr")].map((tr) =>
        [...tr.querySelectorAll("td")].map((td) => td.textContent.trim()));
      const money = (t) => Number(String(t).replace(/[^0-9.-]/g, "")) || 0;
      const totalRow = cells.find((c) => /^Total$/i.test(c[0]));
      check("the table carries a total, so 'worth the same' is checkable", !!totalRow,
            cells.map((c) => c[0]).join(","));
      if (totalRow) {
        check("current and defended totals agree",
              Math.abs(money(totalRow[1]) - money(totalRow[2])) <= 1,
              `${totalRow[1]} vs ${totalRow[2]}`);
        eq("and the total is the portfolio's own value",
           money(totalRow[1]), Math.round(noCash.portfolio.total_value));
      }
    }
  }

  console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
  process.exit(failures ? 1 : 0);
})().catch((e) => {
  console.log("HARNESS ABORTED: " + (e && e.stack || e));
  process.exit(1);
});
