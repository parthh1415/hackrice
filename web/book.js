/* The book as area. The Portfolio page is the first screen anyone sees and it
   was a table — which is the right tool for reading a value off a row, and the
   wrong one for the question this page exists to raise.

   That question is not "what do I own", it is "where does my money sit in
   somebody else's crowd". So area is what you own and shade is how much of
   that name the five modelled books hold, in days of its own volume. A big
   dark tile is a large position in a name the institutions are packed into,
   which is precisely the exposure the rest of the product goes on to price.

   Squarified treemap, because slice-and-dice degenerates into slivers the
   moment a book has more than a handful of names and a real brokerage export
   has twenty. */

function _worst(row, w, h) {
  const s = row.reduce((a, x) => a + x.area, 0);
  if (s <= 0) return Infinity;
  const side = Math.min(w, h);
  const len = s / Math.max(w, h) === 0 ? 0 : s / side;
  let worst = 0;
  for (const t of row) {
    const a = t.area;
    worst = Math.max(worst, Math.max((side * side * a) / (s * s), (s * s) / (side * side * a)));
  }
  return worst;
}

/* Standard squarified layout (Bruls, Huizing, van Wijk). Returns each item
   with an {x, y, w, h} rectangle in the box given. */
function squarify(items, box) {
  const out = [];
  let rest = items.filter((i) => i.value > 0).slice().sort((a, b) => b.value - a.value);
  const total = rest.reduce((a, i) => a + i.value, 0);
  if (!total) return out;

  let { x, y, w, h } = box;
  const scale = (w * h) / total;
  rest = rest.map((i) => ({ ...i, area: i.value * scale }));

  while (rest.length) {
    const vertical = w < h;
    const side = Math.min(w, h);
    const row = [rest[0]];
    let i = 1;
    while (i < rest.length &&
           _worst([...row, rest[i]], w, h) <= _worst(row, w, h)) {
      row.push(rest[i]); i++;
    }
    const rowArea = row.reduce((a, t) => a + t.area, 0);
    const thickness = rowArea / side;
    let off = 0;
    for (const t of row) {
      const len = t.area / thickness;
      out.push(vertical
        ? { ...t, x: x + off, y, w: len, h: thickness }
        : { ...t, x, y: y + off, w: thickness, h: len });
      off += len;
    }
    if (vertical) { y += thickness; h -= thickness; }
    else { x += thickness; w -= thickness; }
    rest = rest.slice(row.length);
  }
  return out;
}

function drawBook(svg, { holdings, days, total }) {
  const ns = "http://www.w3.org/2000/svg";
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const W = 960, H = 300;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("role", "img");

  const items = (holdings || [])
    .filter((h) => h.market_value > 0)
    .map((h) => ({ symbol: h.symbol, value: h.market_value, weight: h.weight,
                   days: (days || {})[h.symbol] }));
  if (!items.length) return;

  const tiles = squarify(items, { x: 0, y: 0, w: W, h: H });
  /* Shade against the most crowded name in THIS book, so the scale is the
     reader's own portfolio rather than an absolute nobody has a feel for. */
  const maxDays = Math.max(0.0001, ...items.map((i) => i.days || 0));

  const el = (tag, attrs, text) => {
    const e = document.createElementNS(ns, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    svg.appendChild(e);
    return e;
  };

  for (const t of tiles) {
    /* Cash has no crowding because nobody is forced to sell it — it is the one
       thing in the book that cannot transmit. It gets no fill at all rather
       than the lightest shade, which would read as "barely crowded". */
    const isCash = t.days == null;
    const k = isCash ? 0 : Math.min(1, (t.days || 0) / maxDays);
    el("rect", {
      class: `bk-tile${isCash ? " bk-cash" : ""}`,
      x: t.x + 1, y: t.y + 1, width: Math.max(0, t.w - 2), height: Math.max(0, t.h - 2),
      "fill-opacity": isCash ? 0 : (0.14 + 0.74 * k).toFixed(3),
    });

    /* Each line is drawn only if its tile can actually hold it. The width gate
       matters most for the crowding line, which is the longest string on the
       tile — without it the small tiles on the right of a real twenty-name
       book render "0.7 days of vo" and spill over their own edges. */
    /* Each gate is the baseline the line is actually drawn at, plus room for
       the descender. They used to sit BELOW their own baselines — h > 34 for a
       line at y + 38, h > 52 for one at y + 56 — so a tile in the few pixels
       between gate and baseline had its second line drawn under its own bottom
       edge, and on the bottom row that is under the viewBox, where it is
       clipped away entirely. A sweep of random eight-to-twenty-six-name books
       hit it about one time in seven. */
    if (t.w > 62 && t.h > 44) {
      el("text", { class: "bk-sym", x: t.x + 10, y: t.y + 22 }, t.symbol);
      el("text", { class: "bk-wt", x: t.x + 10, y: t.y + 38 },
         `${(t.weight * 100).toFixed(1)}%`);
      /* Both spellings of the crowding line share one baseline, so they share
         one height gate; only the width decides which of them fits. */
      if (!isCash && t.h > 62) {
        el("text", { class: "bk-days", x: t.x + 10, y: t.y + 56 },
           t.w > 150 ? `${t.days.toFixed(1)} days of volume` : `${t.days.toFixed(1)}d`);
      }
    }
  }

  svg.setAttribute("aria-label",
    `The book by value. ${items.length} holdings, shaded by how many days of ` +
    `their own trading volume the five modelled books hold.`);
}
