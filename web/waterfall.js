/* The cascade waterfall. DESIGN.md §4.

   The gap between 7.23% and 10.00% is the product's whole argument, and for
   most of this project's life it was a number in a table. This draws it.

   Hand-written SVG, no charting library. Two halves on purpose: cascadeBands()
   turns two payloads into the numbers, drawWaterfall() turns numbers into
   shapes. The arithmetic is where a chart lies — a plausible picture drawn
   from a wrong cumulative is indistinguishable from a right one — so it lives
   in a pure function the harness can check against the payload it came from.

   Nothing here hardcodes a round count, a limit, or a colour. Bands come from
   trajectory.length and the fills come from classes in shell.css. */

/* Cumulative portfolio loss at each step of the cascade.

   The trajectory's frame 0 is the shock alone — verified against the payload:
   its loss equals direct_loss to the last digit, and exactly one name has
   moved. Frames 1..n are the deleveraging rounds, and the last one lands on
   cascade_loss. So the bands are Direct, Round 1, … Round n, which is exactly
   what §4 asks for and also what the data already is.

   The observer model: loss = 1 − (weights · prices + cash). The book takes the
   price damage and does not join the network. */
function cascadeBands(full, cascade) {
  const w = {};
  (full.portfolio.holdings || []).forEach((h) => { w[h.symbol] = h.weight; });
  const cash = w.CASH || 0;
  const vector = cascade.tickers.map((t) => w[t] || 0);
  const lossAt = (prices) =>
    1 - (vector.reduce((acc, v, i) => acc + v * prices[i], 0) + cash);

  let prev = 0;
  return (cascade.trajectory || []).map((frame, i) => {
    const to = lossAt(frame.prices);
    const band = { label: i === 0 ? "Direct" : `Round ${i}`, from: prev, to };
    prev = to;
    return band;
  });
}

/* Where the cumulative first reaches the limit: the index of the band it
   happens in. Returns null when the book never crosses — a real outcome this
   app is careful about elsewhere, and the picture has to be able to say it too.

   `b.from < limit` cannot currently change the answer. The cumulative only
   rises (prices only fall in a deleveraging cascade, and the harness asserts
   it), so the first band whose close reaches the limit always has an open
   below it. Mutating that half of the condition away leaves both the break
   point and a 45% shock reporting the same band. It stays because without it
   this function depends silently on monotonicity holding somewhere else. */
function crossingOf(bands, limit) {
  for (let i = 0; i < bands.length; i++) {
    const b = bands[i];
    if (b.to >= limit && b.from < limit) return { index: i, value: limit };
  }
  return null;
}

const WF = {
  W: 960, H: 480,
  padL: 64, padR: 148, padT: 28, padB: 68,
  /* 160ms each, 60ms apart, per §4. Four bands come in at 340ms. */
  dur: 160, stagger: 60,
};

function drawWaterfall(svg, { bands, limit, animate = true }) {
  const ns = "http://www.w3.org/2000/svg";
  /* §4 wants the whole sequence behind prefers-reduced-motion, with the final
     state rendered instantly. The transitions are set as inline styles — CSS
     cannot take them back — so the query is asked here rather than there. */
  if (animate && window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    animate = false;
  }
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute("viewBox", `0 0 ${WF.W} ${WF.H}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("role", "img");

  if (!bands.length) return;

  const plotW = WF.W - WF.padL - WF.padR;
  const plotH = WF.H - WF.padT - WF.padB;
  const final = bands[bands.length - 1].to;
  /* §4: domain 0 to max(limit, final) x 1.15. The headroom is what keeps the
     limit line off the frame edge when the book stops just short of it. */
  const yMax = Math.max(limit, final) * 1.15 || 1;
  const y = (v) => WF.padT + (v / yMax) * plotH;

  const bandW = plotW / bands.length;
  const barW = bandW * 0.62;
  const barX = (i) => WF.padL + i * bandW + (bandW - barW) / 2;

  const el = (tag, attrs, text) => {
    const n = document.createElementNS(ns, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    svg.appendChild(n);
    return n;
  };

  const cross = crossingOf(bands, limit);

  /* The wash goes down first, under everything: the area between the line the
     user drew and where they actually ended up. Only drawn when they ended up
     past it. */
  if (final > limit) {
    el("rect", { class: "wf-wash", x: WF.padL, y: y(limit),
                 width: plotW, height: Math.max(0, y(final) - y(limit)) });
  }

  /* Zero rule, and the axis. Loss increases downward from 0 at the top. */
  el("line", { class: "wf-axis", x1: WF.padL, y1: y(0), x2: WF.padL + plotW, y2: y(0) });
  el("text", { class: "wf-tick", x: WF.padL - 8, y: y(0) + 4, "text-anchor": "end" }, "0%");

  /* The limit line is already drawn before the first segment moves. */
  el("line", { class: "wf-limit", x1: WF.padL, y1: y(limit), x2: WF.padL + plotW, y2: y(limit) });
  el("text", { class: "wf-limit-label", x: WF.padL + plotW + 8, y: y(limit) + 4 },
     `your limit ${(limit * 100).toFixed(2)}%`);

  bands.forEach((b, i) => {
    const top = y(b.from);
    const bottom = y(b.to);
    const h = Math.max(bottom - top, 0);
    const x = barX(i);

    /* §4: ink while the cumulative is under the limit; the band that crosses is
       split at the crossing point and everything after it is loss. */
    const past = cross !== null && i > cross.index;
    const splits = cross !== null && i === cross.index;

    const seg = (yTop, yBot, cls) => {
      const r = el("rect", { class: cls, x, y: yTop,
                             width: barW, height: Math.max(yBot - yTop, 0) });
      if (animate) {
        r.style.transformOrigin = `${x}px ${yTop}px`;
        r.style.transform = "scaleY(0)";
        r.style.transition = `transform ${WF.dur}ms ease-out ${i * WF.stagger}ms`;
      }
      return r;
    };

    if (splits) {
      const cut = y(cross.value);
      seg(top, cut, "wf-seg");
      seg(cut, bottom, "wf-seg wf-seg-loss");
    } else {
      seg(top, bottom, past ? "wf-seg wf-seg-loss" : "wf-seg");
    }

    /* The running total, at the level it actually reaches, in the empty space
       to the LEFT of its own bar.

       Two placements were wrong before this one. Centred above the bar put the
       close at the open — number and position describing different moments,
       and "7.23%" hard against the 0% rule. Centred below put it across the
       connector, and on the Break page, where the book lands within a rounding
       of its limit, it put "9.85%" on top of the dashed limit line.

       Left of the bar at the close level is clear in both: the connector
       arrives at the PREVIOUS close, which in a falling waterfall is always
       above this one. */
    el("text", { class: "wf-val", x: x - 6, y: bottom + 4, "text-anchor": "end" },
       `${(b.to * 100).toFixed(2)}%`);

    el("text", { class: "wf-band", x: x + barW / 2, y: WF.padT + plotH + 36,
                 "text-anchor": "middle" }, b.label);

    /* 1px connector carrying this band's close across to the next one's open. */
    if (i < bands.length - 1) {
      el("line", { class: "wf-connect", x1: x + barW, y1: bottom,
                   x2: barX(i + 1), y2: bottom });
    }

    if (h === 0) {
      /* A round that moved nothing still happened, and a zero-height rect draws
         as nothing at all — which reads as a missing round rather than a
         quiet one. */
      el("line", { class: "wf-flat", x1: x, y1: top, x2: x + barW, y2: top });
    }
  });

  if (animate) {
    /* One frame later, so the browser has the from-state before the to-state.
       Without this the transition has nothing to interpolate and every segment
       simply appears. */
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        svg.querySelectorAll(".wf-seg").forEach((r) => { r.style.transform = "scaleY(1)"; });
      });
    });
  }

  svg.setAttribute("aria-label",
    `Cumulative portfolio loss across ${bands.length} steps, ending at ` +
    `${(final * 100).toFixed(2)}% against a limit of ${(limit * 100).toFixed(2)}%.`);
}
