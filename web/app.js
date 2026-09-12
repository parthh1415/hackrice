/* Firebreak front end. No framework, no build step — it has to run from a
   folder on a laptop with no wifi at 8am Sunday. */

const NS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);

const state = {
  data: null,      // last /api/break payload
  frame: 0,        // which cascade round we're showing
  timer: null,
};

/* ------------------------------------------------------------------ utils */

const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;

function el(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function params() {
  return new URLSearchParams({
    leverage: $("leverage").value,
    gamma: $("gamma").value,
    breaches: $("breaches").value,
  }).toString();
}

async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

/* ------------------------------------------------------------- the network */

/* Assets down the left, funds down the right, one edge per position.
   Edge opacity is the weight of that position in that fund's book, so the
   crowded names are visibly thick before anything even happens. */
function drawNetwork(svg, data, frame) {
  svg.textContent = "";

  const W = 560, H = 360, PAD = 26;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const { tickers, funds, holdings } = data;
  const snap = data.trajectory[Math.min(frame, data.trajectory.length - 1)];
  const breached = new Set(snap.breached);
  const everBreached = new Set(
    data.trajectory.slice(0, frame + 1).flatMap((s) => s.breached)
  );

  const ax = 150, fx = W - 150;
  const ay = (i) => PAD + ((i + 0.5) / tickers.length) * (H - 2 * PAD);
  const fy = (j) => PAD + ((j + 0.5) / funds.length) * (H - 2 * PAD);

  const rowTotals = holdings.map((r) => r.reduce((a, b) => a + b, 0));
  const priceDrop = tickers.map((_, i) => 1 - snap.prices[i]);
  const worstDrop = Math.max(0.001, ...priceDrop);

  // edges first so nodes sit on top
  holdings.forEach((row, j) =>
    row.forEach((v, i) => {
      if (v <= 0) return;
      const weight = v / rowTotals[j];
      const live = everBreached.has(j);
      svg.appendChild(
        el("line", {
          x1: ax, y1: ay(i), x2: fx, y2: fy(j),
          stroke: live ? "var(--breach)" : "var(--rule-2)",
          "stroke-width": (0.4 + weight * 5).toFixed(2),
          opacity: live ? 0.55 : 0.3,
        })
      );
    })
  );

  tickers.forEach((t, i) => {
    const severity = priceDrop[i] / worstDrop;
    const fill =
      priceDrop[i] < 0.001 ? "var(--rule-2)"
        : severity > 0.6 ? "var(--breach)"
        : "var(--stress)";
    const shocked = i === data.asset_index;
    svg.appendChild(el("circle", { cx: ax, cy: ay(i), r: 5 + severity * 4, fill }));
    if (shocked) {
      svg.appendChild(el("circle", {
        cx: ax, cy: ay(i), r: 12, fill: "none",
        stroke: "var(--breach)", "stroke-width": 1.2, "stroke-dasharray": "2 2",
      }));
    }
    const label = el("text", {
      x: ax - 18, y: ay(i) + 3.5, "text-anchor": "end",
      "font-family": "var(--mono)", "font-size": 10,
      fill: priceDrop[i] > 0.001 ? "var(--ink)" : "var(--muted)",
    }, t);
    svg.appendChild(label);
    if (priceDrop[i] > 0.0005) {
      svg.appendChild(el("text", {
        x: ax - 18, y: ay(i) + 14, "text-anchor": "end",
        "font-family": "var(--mono)", "font-size": 8, fill: "var(--breach)",
      }, `-${(priceDrop[i] * 100).toFixed(1)}%`));
    }
  });

  funds.forEach((f, j) => {
    const now = breached.has(j);
    const ever = everBreached.has(j);
    const fill = now ? "var(--breach)" : ever ? "var(--stress)" : "var(--stable)";
    svg.appendChild(el("rect", {
      x: fx - 6, y: fy(j) - 6, width: 12, height: 12, fill,
    }));
    if (now) {
      svg.appendChild(el("rect", {
        x: fx - 11, y: fy(j) - 11, width: 22, height: 22, fill: "none",
        stroke: "var(--breach)", "stroke-width": 1.2,
      }));
    }
    svg.appendChild(el("text", {
      x: fx + 18, y: fy(j) + 3.5, "font-family": "var(--mono)", "font-size": 10,
      fill: ever ? "var(--ink)" : "var(--muted)",
    }, f));
    svg.appendChild(el("text", {
      x: fx + 18, y: fy(j) + 14, "font-family": "var(--mono)", "font-size": 8,
      fill: now ? "var(--breach)" : "var(--muted)",
    }, `L ${snap.leverage[j].toFixed(2)}`));
  });

  svg.appendChild(el("text", {
    x: ax, y: 13, "text-anchor": "middle", "font-family": "var(--mono)",
    "font-size": 8, fill: "var(--muted)", "letter-spacing": "1.2",
  }, "ASSETS"));
  svg.appendChild(el("text", {
    x: fx, y: 13, "text-anchor": "middle", "font-family": "var(--mono)",
    "font-size": 8, fill: "var(--muted)", "letter-spacing": "1.2",
  }, "FUNDS"));
}

/* ------------------------------------------------------------- the animation */

function showFrame(i) {
  state.frame = i;
  const data = state.data;
  drawNetwork($("network"), data, i);

  const pips = $("pips");
  pips.textContent = "";
  for (let k = 0; k < data.trajectory.length; k++) {
    const pip = document.createElement("span");
    pip.className = "pip" + (k === i ? " on" : k < i ? " done" : "");
    pips.appendChild(pip);
  }
  $("roundLabel").textContent =
    i === 0 ? "shock applied" : `round ${i} of ${data.trajectory.length - 1}`;

  const snap = data.trajectory[i];
  const everBreached = new Set(
    data.trajectory.slice(0, i + 1).flatMap((s) => s.breached)
  );
  const rows = $("fundRows");
  rows.textContent = "";
  data.funds.forEach((f, j) => {
    const row = document.createElement("div");
    row.className = "fund-row" + (everBreached.has(j) ? " breached" : "");
    row.innerHTML =
      `<span class="f-name">${f}</span>` +
      `<span class="f-lev">L ${snap.leverage[j].toFixed(2)}</span>` +
      `<span class="f-tag">${everBreached.has(j) ? "breached" : "within"}</span>`;
    rows.appendChild(row);
  });
}

function play() {
  clearInterval(state.timer);
  let i = 0;
  showFrame(0);
  state.timer = setInterval(() => {
    i += 1;
    if (i >= state.data.trajectory.length) return clearInterval(state.timer);
    showFrame(i);
  }, 850);
}

/* ------------------------------------------------- the phase diagram (scene 2) */

/* Leverage up the side, crowding across the bottom, amplification as the fill.
   The boundary isn't drawn on — it's wherever the cells cross the threshold,
   which is the whole point. */
function drawBoundary(svg, b, here) {
  svg.textContent = "";
  const W = 520, H = 340, L = 58, R = W - 18, T = 18, B = H - 44;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const rows = b.rows, cols = b.cols;
  const cw = (R - L) / cols, chh = (B - T) / rows;

  const band = (a) =>
    a < 1.05 ? ["var(--stable)", 0.85]
    : a < 1.3 ? ["var(--stable)", 0.4]
    : a < 1.8 ? ["var(--stress)", 0.5]
    : a < 3   ? ["var(--breach)", 0.5]
    :           ["var(--breach)", 0.9];

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const [fill, opacity] = band(b.grid[r][c]);
      svg.appendChild(el("rect", {
        x: (L + c * cw).toFixed(2),
        y: (T + (rows - 1 - r) * chh).toFixed(2),
        width: (cw + 0.5).toFixed(2), height: (chh + 0.5).toFixed(2),
        fill, opacity,
      }));
    }
  }

  svg.appendChild(el("rect", {
    x: L, y: T, width: R - L, height: B - T,
    fill: "none", stroke: "var(--rule-2)", "stroke-width": 1,
  }));

  // where the real system sits
  const lo = b.leverage_axis[0], hi = b.leverage_axis[rows - 1];
  const ox = b.overlap_axis, omin = ox[0], omax = ox[cols - 1];
  const mx = L + ((here.overlap - omin) / (omax - omin)) * (R - L);
  const my = T + ((hi - here.leverage) / (hi - lo)) * (B - T);
  svg.appendChild(el("circle", { cx: mx, cy: my, r: 6, fill: "none",
    stroke: "var(--ink)", "stroke-width": 1.8 }));
  svg.appendChild(el("circle", { cx: mx, cy: my, r: 2, fill: "var(--ink)" }));
  svg.appendChild(el("text", {
    x: Math.min(mx + 10, R - 100), y: my - 6, "font-family": "var(--mono)",
    "font-size": 9, fill: "var(--ink)", "letter-spacing": "0.8",
  }, "YOU ARE HERE"));
  svg.appendChild(el("text", {
    x: Math.min(mx + 10, R - 100), y: my + 6, "font-family": "var(--mono)",
    "font-size": 8, fill: "var(--muted)",
  }, `L ${here.leverage.toFixed(1)} · overlap ${here.overlap.toFixed(2)}`));

  const tick = (x, y, t, anchor) => svg.appendChild(el("text", {
    x, y, "text-anchor": anchor || "middle", "font-family": "var(--mono)",
    "font-size": 8, fill: "var(--muted)",
  }, t));
  tick(L - 6, B + 2, lo.toFixed(1), "end");
  tick(L - 6, T + 6, hi.toFixed(1), "end");
  tick(L, B + 13, omin.toFixed(2));
  tick(R, B + 13, omax.toFixed(2));
  tick((L + R) / 2, B + 28, "PORTFOLIO OVERLAP  \u2192");
  const ylab = el("text", {
    "text-anchor": "middle", "font-family": "var(--mono)",
    "font-size": 8, fill: "var(--muted)",
  }, "GROSS LEVERAGE  \u2192");
  ylab.setAttribute("transform", `translate(16,${(T + B) / 2}) rotate(-90)`);
  svg.appendChild(ylab);
}

async function loadBoundary() {
  const btn = $("boundaryBtn");
  btn.disabled = true; btn.textContent = "sweeping\u2026";
  try {
    const b = await api(`/api/boundary?${params()}`);
    $("scene2").hidden = false;
    drawBoundary($("boundary"), b, b.here);
    $("boundaryNote").textContent =
      `${b.rows}\u00d7${b.cols} runs of the engine, ${Math.abs(b.reference_shock * 100).toFixed(0)}% ` +
      `reference shock on ${state.data ? state.data.tickers[0] : "the first name"}, \u03b3 ${b.gamma}`;
  } catch (err) {
    $("boundaryNote").textContent = `error: ${err.message}`;
  } finally {
    btn.disabled = false; btn.textContent = "map the boundary";
  }
}

/* ------------------------------------------------------------------ actions */

async function findWeakestShock() {
  const btn = $("breakBtn");
  btn.disabled = true;
  btn.textContent = "searching…";
  $("stabiliseBtn").disabled = true;

  try {
    const data = await api(`/api/break?${params()}`);
    if (!data.found) {
      $("heroVal").textContent = "—";
      $("heroVal").className = "val idle";
      $("heroSub").textContent =
        "nothing breaks this system at these settings. raise leverage or impact.";
      $("metrics").textContent = "";
      return;
    }
    state.data = data;

    $("heroVal").className = "val";
    $("heroVal").textContent = `${data.pct.toFixed(2)}%`;
    $("heroSub").textContent =
      `a ${data.pct.toFixed(2)}% drop in ${data.asset} is enough — ` +
      `${data.breached.length} of ${data.funds.length} funds forced to sell`;

    renderMetrics(data.metrics, data);
    $("scene1").hidden = false;
    play();
    $("stabiliseBtn").disabled = false;
  } catch (err) {
    $("heroSub").textContent = `engine error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "find weakest shock";
  }
}

function renderMetrics(m, data) {
  const box = $("metrics");
  box.textContent = "";
  const cells = [
    ["shock loss", pct(m.shock_loss), ""],
    ["after cascade", pct(m.final_loss), "hot"],
    ["amplification", `${m.amplification.toFixed(2)}×`, "hot"],
    ["breaches", `${data.breached.length}`, "hot"],
    ["rounds", `${data.rounds}`, ""],
  ];
  for (const [lab, val, cls] of cells) {
    const cell = document.createElement("div");
    cell.className = `metric ${cls}`;
    cell.innerHTML = `<span class="m-val">${val}</span><span class="m-lab">${lab}</span>`;
    box.appendChild(cell);
  }
}

async function stabilise() {
  const btn = $("stabiliseBtn");
  btn.disabled = true;
  btn.textContent = "solving…";
  try {
    const r = await api(`/api/stabilise?${params()}`);
    const box = $("scene3");
    box.hidden = false;
    if (!r.found) {
      $("fixCard").innerHTML =
        `<span class="f-do">No single-position cut clears it.</span>` +
        `<span class="f-cost">this system needs more than one change</span>`;
      $("beforeAfter").textContent = "";
      return;
    }
    const f = r.fix;
    $("fixCard").innerHTML =
      `<span class="f-do">${f.fund}: cut ${f.asset} exposure by ` +
      `${(f.reduction * 100).toFixed(0)}%.</span>` +
      `<span class="f-cost">costs ${pct(f.cost, 2)} of the system's gross assets</span>`;

    $("beforeAfter").innerHTML =
      pane("before", "before", r.before, r) + pane("after", "after firebreak", r.after, r);
  } catch (err) {
    $("fixCard").textContent = `error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "stabilise";
  }
}

function pane(cls, label, result, r) {
  return (
    `<div class="${cls}"><span class="ba-lab">${label}</span>` +
    `<div class="ba-val">${pct(result.metrics.final_loss)}</div>` +
    `<div class="ba-sub">${result.breached.length} breaches · ` +
    `amp ${result.metrics.amplification.toFixed(2)}× · ` +
    `same ${r.pct.toFixed(2)}% ${r.asset} shock</div></div>`
  );
}

/* -------------------------------------------------------------------- boot */

async function boot() {
  try {
    await api("/api/health");
    $("dot").className = "dot up";
    $("state").textContent = "engine connected";
    const data = await api("/api/dataset");
    $("provenance").textContent =
      `${data.funds.length} managers · ${data.tickers.length} names · ` +
      `${data.source} filed ${data.quarter}`;
    $("advList").textContent = data.tickers
      .map((t, i) => `${t} $${(data.adv[i] / 1e9).toFixed(1)}B`)
      .join(" · ");
  } catch {
    $("state").textContent = "server down";
  }
}

["leverage", "gamma"].forEach((id) =>
  $(id).addEventListener("input", (e) => {
    $(id + "Val").textContent =
      id === "gamma" ? Number(e.target.value).toFixed(2) : Number(e.target.value).toFixed(1);
  })
);
$("breakBtn").addEventListener("click", findWeakestShock);
$("stabiliseBtn").addEventListener("click", stabilise);
$("replayBtn").addEventListener("click", () => state.data && play());
$("boundaryBtn").addEventListener("click", loadBoundary);

boot();
