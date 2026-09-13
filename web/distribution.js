/* The 400 scenarios, drawn. DESIGN.md §4's treatment applied to the page that
   had no picture at all.

   Not a histogram. These losses are heavily right-skewed — most single-name
   shocks do almost nothing and a handful are severe — so a histogram is a
   spike at zero and a thin tail, with the interesting part rendered as four
   bars a pixel high. Sorting the scenarios and plotting loss against rank puts
   the tail on the right where it can be read, shows the improvement at EVERY
   quantile rather than only at the worst, and makes the two crossings of the
   limit line literally countable.

   Both books were scored on identical draws, which is what makes drawing them
   over each other legitimate. */

const DIST = {
  W: 960, H: 420,
  padL: 64, padR: 150, padT: 24, padB: 52,
};

function drawDistribution(svg, { before, after, limit, animate = true }) {
  const ns = "http://www.w3.org/2000/svg";
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute("viewBox", `0 0 ${DIST.W} ${DIST.H}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("role", "img");
  if (!before.length || !after.length) return;

  if (animate && window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    animate = false;
  }

  const bAll = [...before].sort((x, y) => x - y);
  const aAll = [...after].sort((x, y) => x - y);
  const total = Math.min(bAll.length, aAll.length);

  /* Only the tail is drawn. Across 400 draws the great majority are
     single-name shocks that cost both books almost nothing, so the two curves
     sit exactly on top of each other for three quarters of the width and the
     entire story — where they separate, and where each crosses the line — is
     compressed into the last inch. Cutting to the worst quarter puts the
     separation at a readable scale. The counts printed on the chart are still
     out of all 400; nothing is hidden, it is zoomed. */
  const shown = Math.max(2, Math.round(total * 0.25));
  const b = bAll.slice(total - shown);
  const a = aAll.slice(total - shown);
  const n = shown;

  const plotW = DIST.W - DIST.padL - DIST.padR;
  const plotH = DIST.H - DIST.padT - DIST.padB;
  const yMax = Math.max(limit, b[b.length - 1], a[a.length - 1]) * 1.12 || 1;
  const x = (i) => DIST.padL + (i / (n - 1)) * plotW;
  const y = (v) => DIST.padT + plotH - (v / yMax) * plotH;

  const el = (tag, attrs, text) => {
    const e = document.createElementNS(ns, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    svg.appendChild(e);
    return e;
  };
  const path = (arr) =>
    arr.slice(0, n).map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(2)},${y(v).toFixed(2)}`).join("");

  /* Everything above the line is a scenario that cost more than the user said
     they would accept. */
  el("rect", { class: "ds-wash", x: DIST.padL, y: DIST.padT,
               width: plotW, height: Math.max(0, y(limit) - DIST.padT) });

  el("line", { class: "ds-axis", x1: DIST.padL, y1: y(0), x2: DIST.padL + plotW, y2: y(0) });

  el("line", { class: "ds-limit", x1: DIST.padL, y1: y(limit),
               x2: DIST.padL + plotW, y2: y(limit) });
  el("text", { class: "ds-limit-label", x: DIST.padL + plotW + 8, y: y(limit) + 4 },
     `your limit ${(limit * 100).toFixed(2)}%`);

  /* The book as it stands, then the defended book on top — the same
     before/after language the Fix page uses. */
  el("path", { class: "ds-before", d: path(b) });
  const after_ = el("path", { class: "ds-after", d: path(a) });

  /* Where each curve crosses. These two counts ARE the claim the page makes,
     so they are marked on the drawing rather than left to the table. */
  /* Found over the FULL array and then placed in the window, because the
     window is the worst quarter: a book that crossed its limit among the 300
     scenarios that were cut returns index 0 from a search over the slice, and
     the dot was planted at x(0) on the limit line — a point neither curve
     passes through. If the crossing is off the left edge there is no crossing
     to mark on this chart, and marking one anyway is the drawing asserting
     something the data does not. */
  const overFrom = (arr) => {
    const k = arr.findIndex((v) => v >= limit);
    if (k < 0) return null;
    const inWindow = k - (arr.length - shown);
    return inWindow < 0 ? null : inWindow;
  };
  [["ds-cross ds-cross-before", overFrom(bAll), b], ["ds-cross", overFrom(aAll), a]]
    .forEach(([cls, k]) => {
      if (k === null) return;
      el("circle", { class: cls, cx: x(k), cy: y(limit), r: 4.5 });
    });

  /* Counted over ALL the draws, not the slice on screen. */
  const past = (arr) => arr.filter((v) => v >= limit).length;
  el("text", { class: "ds-note", x: DIST.padL + plotW, y: DIST.padT + 16,
               "text-anchor": "end" },
     `past the limit: ${past(bAll)} of ${total}, then ${past(aAll)} of ${total}`);

  /* Axes. Rank is not a quantity anybody reads off, so the x axis is labelled
     at its ends and nowhere else. */
  el("text", { class: "ds-tick", x: DIST.padL - 8, y: y(0) + 4, "text-anchor": "end" }, "0%");
  /* The tick is DRAWN at yMax and was LABELLED with yMax rounded to a whole
     percent — 12.61% of axis wearing a "13%" label, on one of the three y
     references the reader has. A tenth of a point is enough to make the label
     and the line the same number. */
  el("text", { class: "ds-tick", x: DIST.padL - 8, y: y(yMax) + 10, "text-anchor": "end" },
     `${(yMax * 100).toFixed(1)}%`);
  /* "301th" is what naive concatenation gives you, and it is on screen next to
     a chart whose whole argument is that the numbers were done carefully. */
  const ordinal = (k) => {
    const tens = k % 100, ones = k % 10;
    const suffix = (tens >= 11 && tens <= 13) ? "th"
                 : ones === 1 ? "st" : ones === 2 ? "nd" : ones === 3 ? "rd" : "th";
    return `${k}${suffix}`;
  };
  /* Counted from the WORST, because the other end of this axis is "worst case"
     and the caption underneath says "the worst 100 of 400". `total - shown + 1`
     counts from the best — a true rank, of the wrong series — so the axis read
     301st worst to 1st worst, 301 ranks, across 100 plotted points, with the
     count of them printed one line below. */
  el("text", { class: "ds-band", x: DIST.padL, y: DIST.padT + plotH + 24 },
     `${ordinal(shown)} worst`);
  el("text", { class: "ds-band", x: DIST.padL + plotW, y: DIST.padT + plotH + 24,
               "text-anchor": "end" }, "worst case");
  el("text", { class: "ds-band", x: DIST.padL + plotW / 2, y: DIST.padT + plotH + 40,
               "text-anchor": "middle" },
     `the worst ${shown} of ${total} simulated shocks, both books on identical draws`);

  if (animate) {
    /* The defended curve draws itself in over the undefended one, which is the
       page's only animation and says the one thing the page is for. */
    const len = after_.getTotalLength ? after_.getTotalLength() : 0;
    if (len) {
      after_.style.strokeDasharray = `${len}`;
      after_.style.strokeDashoffset = `${len}`;
      requestAnimationFrame(() => requestAnimationFrame(() => {
        after_.style.transition = "stroke-dashoffset 900ms ease-out";
        after_.style.strokeDashoffset = "0";
      }));
    }
  }

  svg.setAttribute("aria-label",
    `The worst ${shown} of ${total} simulated shocks, sorted by loss. The current ` +
    `book exceeds the ${(limit * 100).toFixed(2)}% limit in ${past(bAll)} of all ${total}, ` +
    `the defended book in ${past(aAll)}.`);
}
