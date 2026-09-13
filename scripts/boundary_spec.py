#!/usr/bin/env python3
"""Dump the boundary sweep's inputs, and Python's own answer, for MATLAB.

matlab/boundary.m recomputes the same 16x16 sweep with cascade.m and draws it.
Shipping a figure that disagrees with the app's own boundary page would be
worse than shipping no figure, so this writes Python's grid alongside the
inputs and the MATLAB side is checked against it.

    PYTHONPATH=src python3 scripts/boundary_spec.py
"""

import json
import pathlib

import numpy as np

from firebreak import api
from firebreak.engine import run_cascade
from firebreak.matlab_bridge import read_palette

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "cache" / "boundary_spec.json"


def main(gamma=0.2, band=1.05):
    data = api.load_dataset()
    base = np.array(data["holdings"], dtype=float)
    adv = np.array(data["adv"], dtype=float)

    shock = np.zeros(base.shape[1])
    shock[0] = api._REF_SHOCK

    levs = np.linspace(1.5, 8.0, api._ROWS)
    blends = np.linspace(-1.0, 1.0, api._COLS)

    grid = []
    for lev in levs:
        row = []
        for blend in blends:
            holdings = api.blend_toward_mean(base, blend)
            m = holdings.shape[0]
            r = run_cascade(
                holdings=holdings,
                leverage=np.full(m, lev),
                max_leverage=np.full(m, lev * band),
                target_leverage=np.full(m, min(max(1.0, lev * 0.95), lev * band)),
                gamma=gamma, adv=adv, shock=shock,
            )
            row.append(round(float(r.amplification), 4))
        grid.append(row)

    overlaps = [round(api.mean_overlap(api.blend_toward_mean(base, b)), 4)
                for b in blends]

    spec = {
        "holdings": base.tolist(),
        "adv": adv.tolist(),
        "gamma": gamma,
        "band": band,
        "ref_shock": api._REF_SHOCK,
        "levs": levs.tolist(),
        "blends": blends.tolist(),
        "overlaps": overlaps,
        "here": {"leverage": 5.0, "overlap": api.mean_overlap(base)},
        "asset_count": int(base.shape[1]),
        "python_grid": grid,
    }
    # so the surface is drawn in whatever the app is currently wearing
    palette = read_palette()
    if palette:
        spec["palette"] = palette
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec))
    flat = [a for r in grid for a in r]
    print(f"wrote {OUT.relative_to(ROOT)}  "
          f"({len(levs)}x{len(blends)} cells, min {min(flat):.4f}, max {max(flat):.4f})")


if __name__ == "__main__":
    main()
