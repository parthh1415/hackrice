/* The shell: the rail, the numbered stepper, and the footer strip. DESIGN.md §3.

   One entry point. `paintShell(current)` builds the rail if it is not there,
   updates the step marks and the strip, and then hands off to paintNav for the
   locking and the limit readout. Pages call this instead of paintNav — two
   functions painting one rail is how the nav and the status bar came to
   disagree about the same state before. */

/* The sequence is the product, so the stepper is the product's own order.
   `page` matches paintNav's map and the data-page hooks the harness reads.
   `done` is what the step produces — a step is ticked when its output exists
   AND you are past it. Availability is a different question, and paintNav
   already answers that one; ticking every unlocked step would put a tick on
   steps you have not taken yet. */
const FB_STEPS = [
  { page: "portfolio",   href: "index.html",       label: "Portfolio", done: (s) => !!s.portfolio },
  { page: "limit",       href: "index.html#limit", label: "Limit",     done: (s) => !!s.limit },
  { page: "analysis",    href: "analysis.html",    label: "Break",     done: (s) => !!s.result },
  { page: "cascade",     href: "cascade.html",     label: "Cascade",   done: (s) => !!s.result },
  { page: "defend",      href: "defend.html",      label: "Fix",       done: (s) => !!(s.result && s.result.fix) },
  { page: "verify",      href: "verify.html",      label: "Validate",  done: (s) => !!(s.result && s.result.validation) },
];

/* Reference screens. Unnumbered, below a rule — neither is a step and neither
   needs an analysis to be true. */
const FB_REFS = [
  { page: "boundary",    href: "boundary.html",    label: "Boundary" },
  { page: "assumptions", href: "assumptions.html", label: "Model" },
];

/* A tick, drawn rather than typed. ✓ is in no subset of any font this app
   ships, so as a character it would fall through to the system UI font at a
   weight nothing else on the page uses. 1px stroke, cut to match --rule. */
const FB_TICK =
  '<svg viewBox="0 0 12 12" fill="none" aria-hidden="true">' +
  '<path d="M2 6.5 L4.75 9.25 L10 3" stroke="currentColor" stroke-width="1"/></svg>';

function buildShell() {
  const rail = document.createElement("nav");
  rail.className = "rail";

  const row = (s, numbered, i) =>
    `<li><a href="${s.href}" data-page="${s.page}">` +
      `<span class="step-n">${numbered ? i + 1 : ""}</span>` +
      `<span class="step-label">${s.label}</span>` +
      `<span class="step-state" data-for="${s.page}"></span>` +
    `</a></li>`;

  rail.innerHTML =
    `<a class="rail-mark" href="index.html">Firebreak</a>` +
    `<div class="nav-links">` +
      `<ol class="stepper">${FB_STEPS.map((s, i) => row(s, true, i)).join("")}</ol>` +
      `<ul class="rail-refs">${FB_REFS.map((s) => row(s, false)).join("")}</ul>` +
    `</div>` +
    `<div class="rail-foot">` +
      `<span><span id="railSource">—</span> · <span id="railMs">—</span></span>` +
      `<span id="navEngineText">…</span>` +
    `</div>`;

  document.body.insertBefore(rail, document.body.firstChild);

  /* The strip reports the last round trip, so it has to hear about round trips.
     api() fires this; nothing polls. */
  document.addEventListener("fb:latency", paintStrip);
  return rail;
}

/* The entrance and the instruments used to be two different products to look
   at: one with light moving under it, one flat. This puts the same field
   behind the title of every page — quieter, shorter, and cut off by a rule
   above the first card, so the screens that carry numbers still carry them on
   plain paper.

   Done here rather than in seven files of markup: every page already has one
   `.col > header`, so the band is built around whatever that header holds and
   no page has to know about it. */
function dressMasthead() {
  const header = document.querySelector(".col > header");
  if (!header || header.parentNode.classList.contains("masthead")) return;

  const band = document.createElement("div");
  band.className = "masthead";
  const canvas = document.createElement("canvas");
  canvas.className = "masthead-glow";
  canvas.setAttribute("aria-hidden", "true");

  header.parentNode.insertBefore(band, header);
  band.appendChild(canvas);
  band.appendChild(header);

  /* Dimmer and slower than the entrance, and with the lobes kept low and wide
     so the light sits under the words rather than crossing them. The entrance
     is atmosphere; this is a letterhead. */
  if (typeof dottedGlow === "function") {
    dottedGlow(canvas, {
      gap: 13,
      dotAlpha: 0.16,
      gain: 0.62,
      bloom: 0.6,
      falloff: 0.45,
      speed: 0.55,
      lights: [
        { rgb: [40, 170, 255], r: 0.34, cx: 0.22, cy: 0.55, ax: 0.22, ay: 0.12, fx: 0.019, fy: 0.012, p: 0.0 },
        { rgb: [95, 120, 255], r: 0.30, cx: 0.58, cy: 0.48, ax: 0.24, ay: 0.14, fx: 0.014, fy: 0.021, p: 2.1 },
        { rgb: [148, 92, 236], r: 0.26, cx: 0.86, cy: 0.60, ax: 0.16, ay: 0.12, fx: 0.010, fy: 0.017, p: 4.0 },
      ],
    });
  }
}

/* `demo · 14ms`. Both halves measured: the source is what the book says it is,
   and the milliseconds are what the stopwatch in api() recorded. */
function paintStrip() {
  const s = FB.state;
  const src = document.getElementById("railSource");
  if (src) {
    src.textContent = !s.portfolio ? "no book"
      : s.portfolio.source === "demo" ? "demo" : "imported";
  }
  const ms = document.getElementById("railMs");
  if (ms) {
    const v = lastResponseMs();
    ms.textContent = v === null ? "—" : `${Math.round(v)}ms`;
  }
}

function paintShell(current) {
  const rail = document.querySelector(".rail") || buildShell();
  const s = FB.state;
  const at = FB_STEPS.findIndex((x) => x.page === current);

  FB_STEPS.forEach((step, i) => {
    const cell = rail.querySelector(`.step-state[data-for="${step.page}"]`);
    if (!cell) return;
    /* The Limit step shows the limit rather than a tick. The number is the
       better proof that the step was taken, and paintNav is already the one
       thing that writes it — hence the id, and hence this step sitting outside
       the mark logic entirely rather than being written twice. */
    if (step.page === "limit") {
      cell.className = "step-state step-val";
      cell.id = "navLimit";
      return;
    }
    if (step.page === current) {
      cell.className = "step-state step-here";
      cell.innerHTML = "";
    /* `at` is -1 on Boundary and Model, which are reference screens and not
       steps. Comparing `at > i` there ticks nothing, so walking to Model from
       a finished analysis emptied the whole stepper — the work was still done,
       the rail just stopped saying so. Off the sequence, every completed step
       is behind you. */
    } else if ((at === -1 || at > i) && step.done(s)) {
      cell.className = "step-state step-mark";
      cell.innerHTML = FB_TICK;
    } else {
      cell.className = "step-state";
      cell.innerHTML = "";
    }
  });

  dressMasthead();
  paintStrip();
  paintNav(current);
}
