/* Floating paths — the entrance's background.

   Thirty-six cubic Béziers per side, mirrored, sweeping from off the top-left
   to off the bottom-right, each one drawing and undrawing itself on its own
   clock. Ported from a React/framer-motion component; this app has no build
   step, so the geometry is generated here and the motion is CSS.

   The one trick worth knowing: `pathLength="1"` remaps a path's length to 1,
   so stroke-dasharray and stroke-dashoffset take fractions instead of user
   units. That is what framer-motion's pathLength and pathOffset compile down
   to, and with it the animation is four keyframes of CSS rather than a rAF
   loop — which matters, because 72 animated paths on a requestAnimationFrame
   loop is a different kind of project.

   Monochrome on purpose. The instruments downstream use exactly one colour and
   it means a limit was crossed; the way in does not get to borrow it. */

function floatingPaths(svg, opts = {}) {
  const o = Object.assign({
    count: 36,
    position: 1,     // 1 and -1 give the two mirrored fans
    minDur: 20,      // seconds
    durSpread: 10,
    seed: 1,
  }, opts);

  const ns = "http://www.w3.org/2000/svg";
  /* Deterministic, so the two fans differ from each other but a reload does
     not reshuffle the whole background. */
  let s = o.seed * 9301 + 49297;
  const rand = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };

  const g = document.createElementNS(ns, "g");
  for (let i = 0; i < o.count; i++) {
    const p = o.position;
    const d =
      `M-${380 - i * 5 * p} -${189 + i * 6}` +
      `C-${380 - i * 5 * p} -${189 + i * 6} -${312 - i * 5 * p} ${216 - i * 6} ` +
      `${152 - i * 5 * p} ${343 - i * 6}` +
      `C${616 - i * 5 * p} ${470 - i * 6} ${684 - i * 5 * p} ${875 - i * 6} ` +
      `${684 - i * 5 * p} ${875 - i * 6}`;

    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", d);
    path.setAttribute("pathLength", "1");
    path.setAttribute("stroke-width", (0.5 + i * 0.03).toFixed(2));
    /* The far paths are thin and faint, the near ones heavier — the fan reads
       as depth rather than as thirty-six equal lines. */
    path.setAttribute("stroke-opacity", (0.10 + i * 0.03).toFixed(3));
    path.style.animationDuration = `${(o.minDur + rand() * o.durSpread).toFixed(1)}s`;
    /* A negative delay starts each path partway through its own cycle, so the
       field is already in motion on the first frame instead of all seventy-two
       setting off together. */
    path.style.animationDelay = `${(-rand() * 20).toFixed(1)}s`;
    g.appendChild(path);
  }
  svg.appendChild(g);
  return g;
}
