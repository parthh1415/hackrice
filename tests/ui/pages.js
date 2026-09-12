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
    const st = await (await fetch(ORIGIN + "/api/stabilise?leverage=5.0&gamma=0.2&band=1.05&asset=0")).json();
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
    const ok = await until(() => /asked for a/.test(visibleText(c.d)));
    check("a clamped limit says so instead of silently using another number", ok,
          visibleText(c.d).trim().slice(0, 160));
    has("and names both the limit asked for and the one used",
        visibleText(c.d), "95% limit");
    const navLimit = txt(c.d, "navLimit") || "";
    check("the nav shows the limit the engine used, not the one that was refused",
          navLimit.includes("90"), navLimit);
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
