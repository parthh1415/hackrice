/* Dotted glow background — a dot grid with light moving underneath it.

   The first version twinkled: every dot on its own random phase, flaring
   independently. That reads as static, because noise at a 14px pitch is
   texture, not light. What makes the effect is COHERENCE — soft lobes of
   colour drifting across the field, lighting whole neighbourhoods of dots at
   once and leaving them dark again. The dots never animate; the light does.

   So it is drawn the way the real thing works: light first, then a stencil.

     1. The grid is painted once into an offscreen mask (it only changes on
        resize).
     2. Every frame, four radial gradients are drawn additively into a light
        layer — overlapping lobes sum, the way light does.
     3. `destination-in` with the mask cuts that light down to the dots.
     4. A quarter-size copy, scaled back up and added on top, is the bloom.

   Four gradient fills and three drawImages a frame, whatever the dot count.
   Lighting six thousand dots individually costs six thousand draw calls and
   drops frames on a laptop; this costs the same at any pitch.

   This lives on the entrance and nowhere else. On the data screens a moving
   second colour would compete with the one colour that means a limit was
   crossed; on the way in there is nothing to compete with. */

function dottedGlow(canvas, opts = {}) {
  const o = Object.assign({
    gap: 14,          // px between dot centres
    radius: 1.5,      // px
    dot: "rgba(158, 176, 196, 1)",
    dotAlpha: 0.22,   // the grid you can always just about see
    gain: 0.95,       // brightness at the centre of a lobe
    bloom: 0.85,      // how much of the blurred copy is added back
    falloff: 0.72,    // radial fade toward the edges of the viewport
    speed: 1.0,
    /* Blue through violet, deliberately: --loss is the only warm colour in
       this product and it means something. Nothing on the way in may borrow
       it. cx/cy are the centre of each lobe's travel as a fraction of the
       viewport, ax/ay its amplitude, fx/fy its frequency in Hz. */
    lights: [
      { rgb: [40, 170, 255], r: 0.42, cx: 0.30, cy: 0.44, ax: 0.26, ay: 0.20, fx: 0.021, fy: 0.013, p: 0.0 },
      { rgb: [95, 120, 255], r: 0.36, cx: 0.64, cy: 0.56, ax: 0.24, ay: 0.26, fx: 0.016, fy: 0.023, p: 2.1 },
      { rgb: [148, 92, 236], r: 0.32, cx: 0.50, cy: 0.28, ax: 0.30, ay: 0.18, fx: 0.011, fy: 0.019, p: 4.0 },
      { rgb: [0, 205, 232], r: 0.28, cx: 0.80, cy: 0.24, ax: 0.18, ay: 0.24, fx: 0.026, fy: 0.009, p: 5.3 },
    ],
  }, opts);

  const ctx = canvas.getContext && canvas.getContext("2d");
  if (!ctx) return () => {};

  const still = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const surface = (w, h) => {
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(w));
    c.height = Math.max(1, Math.round(h));
    return c;
  };

  let w = 0, h = 0, dpr = 1, raf = 0;
  const t0 = performance.now();
  let mask = null, light = null, blur = null;
  const BLUR = 0.22;  // the bloom layer's scale; small enough to BE the blur

  function build() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    mask = surface(w * dpr, h * dpr);
    light = surface(w * dpr, h * dpr);
    blur = surface(w * dpr * BLUR, h * dpr * BLUR);

    const m = mask.getContext("2d");
    m.setTransform(dpr, 0, 0, dpr, 0, 0);
    m.fillStyle = o.dot;
    const cx = w / 2, cy = h / 2;
    const far = Math.hypot(cx, cy) || 1;
    for (let y = o.gap / 2; y < h; y += o.gap) {
      for (let x = o.gap / 2; x < w; x += o.gap) {
        /* Dots fade toward the edges so the field reads as lit from the middle
           rather than as wallpaper that stops at the crop. Baked into the mask,
           so it applies to the lit dots and the dark ones alike. */
        const d = Math.hypot(x - cx, y - cy) / far;
        const edge = Math.max(0, 1 - Math.pow(d, 1.7) * o.falloff);
        if (edge <= 0.02) continue;
        m.globalAlpha = edge;
        m.beginPath();
        m.arc(x, y, o.radius, 0, Math.PI * 2);
        m.fill();
      }
    }
    m.globalAlpha = 1;
  }

  function frame(now) {
    /* The still frame is not t=0: at zero every lobe sits at its own centre
       with the phases lined up, which is the one arrangement that looks
       deliberate. Six seconds in, they are scattered. */
    const t = still ? 6.0 : ((now - t0) / 1000) * o.speed;
    const span = Math.max(w, h);

    const L = light.getContext("2d");
    L.setTransform(dpr, 0, 0, dpr, 0, 0);
    L.globalCompositeOperation = "source-over";
    L.clearRect(0, 0, w, h);
    L.globalCompositeOperation = "lighter";
    for (const l of o.lights) {
      const k = Math.PI * 2 * t;
      const x = (l.cx + l.ax * Math.sin(k * l.fx + l.p)) * w;
      const y = (l.cy + l.ay * Math.sin(k * l.fy + l.p * 1.7)) * h;
      /* Each lobe breathes on a slower cycle than it travels on, so the field
         never settles into a visible loop. */
      const r = l.r * span * (0.84 + 0.16 * Math.sin(k * 0.007 + l.p));
      const [cr, cg, cb] = l.rgb;
      const g = L.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0.0, `rgba(${cr},${cg},${cb},${o.gain})`);
      g.addColorStop(0.5, `rgba(${cr},${cg},${cb},${o.gain * 0.30})`);
      g.addColorStop(1.0, `rgba(${cr},${cg},${cb},0)`);
      L.fillStyle = g;
      L.fillRect(x - r, y - r, r * 2, r * 2);
    }
    /* The stencil. Everything not on a dot stops existing. */
    L.globalCompositeOperation = "destination-in";
    L.setTransform(1, 0, 0, 1, 0, 0);
    L.drawImage(mask, 0, 0);
    L.globalCompositeOperation = "source-over";

    /* Downscale and back up: bilinear filtering does the blurring for free,
       and a fifth-size buffer is a twenty-fifth of the pixels. */
    const B = blur.getContext("2d");
    B.globalCompositeOperation = "source-over";
    B.clearRect(0, 0, blur.width, blur.height);
    B.drawImage(light, 0, 0, blur.width, blur.height);

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    /* The unlit grid underneath, so the field is legible even where no lobe
       currently reaches. */
    ctx.globalAlpha = o.dotAlpha;
    ctx.drawImage(mask, 0, 0);
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = o.bloom;
    ctx.drawImage(blur, 0, 0, canvas.width, canvas.height);
    ctx.globalAlpha = 1;
    ctx.drawImage(light, 0, 0);
    ctx.globalCompositeOperation = "source-over";

    if (!still) raf = requestAnimationFrame(frame);
  }

  function start() { cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
  function stop() { cancelAnimationFrame(raf); raf = 0; }

  build();
  start();

  let resizeTimer = 0;
  const onResize = () => {
    /* Rebuilding the mask means re-drawing every dot, which is the one
       expensive thing here. Do it once the drag has stopped. */
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (canvas.clientWidth === w && canvas.clientHeight === h) return;
      build();
      if (still) frame(performance.now());
    }, 120);
  };
  window.addEventListener("resize", onResize);
  /* The masthead canvas is sized by the type above it, and that type is still
     a fallback face when this runs — when the real one lands the band changes
     height, the canvas stretches with it, and the grid comes back as ellipses.
     A window resize never fires for that. */
  let ro = null;
  if (window.ResizeObserver) {
    ro = new ResizeObserver(onResize);
    ro.observe(canvas);
  }
  /* A background animation running behind a tab nobody is looking at is pure
     battery. */
  document.addEventListener("visibilitychange", () =>
    document.hidden ? stop() : start());

  return () => {
    stop();
    window.removeEventListener("resize", onResize);
    if (ro) ro.disconnect();
  };
}
