"""MATLAB's boundary sweep and Python's have to be the same sweep.

`matlab/boundary.m` recomputes the whole 16x16 grid with `cascade.m` rather
than plotting numbers Python handed it, and the Boundary page shows the result
as a surface directly under the heatmap of Python's grid. Two pictures of the
same system, side by side, from two independent implementations — which is
worth something only if they agree, and is actively misleading if they drift.

The agreement was printed once when the figure was generated. That is a claim
about one machine at one moment; this is the claim as a test. If either engine
changes, this fails before the figure gets a chance to contradict the map above
it.
"""

import json
import pathlib

import numpy as np
import pytest

from minima import api
from minima.engine import run_cascade

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "cache" / "boundary_out.json"
SPEC = ROOT / "data" / "cache" / "boundary_spec.json"


@pytest.fixture(scope="module")
def matlab():
    if not OUT.exists():
        pytest.skip("no MATLAB boundary result committed; run matlab/boundary.m")
    result = json.loads(OUT.read_text())
    current_assets = len(api.load_dataset()["tickers"])
    if result.get("asset_count") != current_assets:
        pytest.skip("stale MATLAB boundary result; rerun matlab/boundary.m")
    return result


def test_the_committed_result_is_a_full_sweep(matlab):
    """Guard the guard: half a grid would make the comparison vacuous."""
    grid = np.array(matlab["grid"], dtype=float)
    assert grid.shape == (api._ROWS, api._COLS), grid.shape
    assert np.all(np.isfinite(grid)), "MATLAB returned a non-finite amplification"
    # a sweep that found no cliff is not this dataset's sweep
    assert grid.min() == pytest.approx(1.0, abs=1e-9)
    assert grid.max() > 2.0, grid.max()


def test_matlab_and_python_compute_the_same_boundary(matlab):
    """The figure and the map underneath it describe one system or neither."""
    gamma = matlab.get("gamma")
    band = matlab.get("band")
    if gamma is None or band is None:
        spec = json.loads(SPEC.read_text()) if SPEC.exists() else {}
        gamma = spec.get("gamma", 0.2)
        band = spec.get("band", 1.05)

    data = api.load_dataset()
    base = np.array(data["holdings"], dtype=float)
    adv = np.array(data["adv"], dtype=float)
    shock = np.zeros(base.shape[1])
    shock[0] = api._REF_SHOCK

    mine = []
    for lev in np.linspace(1.5, 8.0, api._ROWS):
        row = []
        for blend in np.linspace(-1.0, 1.0, api._COLS):
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
        mine.append(row)

    theirs = np.round(np.array(matlab["grid"], dtype=float), 4)
    worst = float(np.max(np.abs(theirs - np.array(mine))))
    assert worst <= 1e-4, (
        f"MATLAB's sweep and this engine's differ by {worst:.2e}. The Boundary "
        "page draws both — the surface would be contradicting the heatmap "
        "directly above it."
    )


def test_matlab_recorded_its_own_agreement(matlab):
    """boundary.m refuses to draw when it disagrees. Keep that record honest."""
    recorded = matlab.get("max_abs_diff_vs_python")
    assert recorded is not None, "boundary.m no longer records the comparison"
    assert recorded <= 1e-4, recorded
