"""The bridge has to be honest about which engine actually solved it.

Claiming MATLAB ran when scipy did would be the one thing that turns a
sponsor challenge into a problem.
"""

import json

import numpy as np
import pytest

from minima.matlab_bridge import solve_stabilisation, write_spec

SPEC = dict(
    holdings=[[20.0, 80.0, 0.0], [0.0, 80.0, 20.0]],
    leverage=[6.0, 6.0],
    max_leverage=[6.3, 6.3],
    target_leverage=[5.7, 5.7],
    gamma=0.5,
    adv=[2000.0, 2000.0, 2000.0],
    shock=[0.0, -0.05, 0.0],
    breaches=2,
)


def genuine_fix(spec):
    """A fix that really does clear `spec` — the bridge re-simulates now, so a
    made-up payload is rejected for being wrong rather than for being stale."""
    from minima.search import at_least_n_breaches
    from minima.stabilise import find_cheapest_fix

    fix = find_cheapest_fix(
        condition=at_least_n_breaches(spec["breaches"]),
        holdings=np.array(spec["holdings"]),
        shock=np.array(spec["shock"]),
        leverage=np.array(spec["leverage"]),
        max_leverage=np.array(spec["max_leverage"]),
        target_leverage=np.array(spec["target_leverage"]),
        gamma=spec["gamma"],
        adv=np.array(spec["adv"]),
    )
    assert fix is not None, "fixture has to be fixable or the test proves nothing"
    return {"fund_index": fix.fund, "asset_index": fix.asset,
            "reduction": fix.reduction, "cost": fix.cost, "solver": "patternsearch"}


def test_it_always_returns_an_answer_even_with_no_matlab():
    result = solve_stabilisation(SPEC)

    assert result is None or {"fund_index", "asset_index", "reduction", "cost"} <= result.keys()


def test_it_names_the_engine_that_actually_ran():
    result = solve_stabilisation(SPEC)

    if result is not None:
        assert result["engine"] in ("matlab", "matlab-offline", "python")
        assert result["solver"]


def test_the_spec_it_writes_is_what_matlab_reads(tmp_path):
    path = tmp_path / "spec.json"

    write_spec(SPEC, path)
    loaded = json.loads(path.read_text())

    # every field stabilise.m indexes must survive the round trip
    for key in ("holdings", "leverage", "max_leverage", "target_leverage",
                "gamma", "adv", "shock", "breaches"):
        assert key in loaded
    assert np.array(loaded["holdings"]).shape == (2, 3)


def test_a_stale_matlab_result_is_ignored(tmp_path):
    # MATLAB Online writes a result file by hand; if the parameters have
    # moved on since, using it would silently show the wrong answer
    from minima.matlab_bridge import _spec_fingerprint

    other = dict(SPEC, gamma=0.9)

    assert _spec_fingerprint(SPEC) != _spec_fingerprint(other)


def test_a_stale_result_file_is_not_served_as_a_matched_solve(tmp_path, monkeypatch):
    """The spec file is rewritten on every request, so comparing it to the
    request it was just written from can only ever agree with itself.

    Real sequence: solve for scenario A in MATLAB Online, download the result,
    then move a slider. api._stabilise writes the spec for scenario B and asks
    the bridge, which used to hand back A's answer under scenario B's label.
    """
    from minima import matlab_bridge as mb

    spec_path, out_path = tmp_path / "solve_spec.json", tmp_path / "solve_out.json"
    monkeypatch.setattr(mb, "SPEC_PATH", spec_path)
    monkeypatch.setattr(mb, "OUT_PATH", out_path)

    a = dict(SPEC, gamma=0.9, shock=[-0.40, 0.0, 0.0])
    mb.write_spec(a, spec_path)
    out_path.write_text(json.dumps(genuine_fix(a)))

    assert mb._try_offline(a) is not None, "the result it was actually solved for"

    # slider moves; api writes the new spec before asking the bridge
    mb.write_spec(SPEC, spec_path)

    assert mb._try_offline(SPEC) is None


def test_re_asking_the_same_question_keeps_the_offline_answer(tmp_path, monkeypatch):
    """Rejecting stale results is worthless if it also rejects fresh ones."""
    from minima import matlab_bridge as mb

    spec_path, out_path = tmp_path / "solve_spec.json", tmp_path / "solve_out.json"
    monkeypatch.setattr(mb, "SPEC_PATH", spec_path)
    monkeypatch.setattr(mb, "OUT_PATH", out_path)

    mb.write_spec(SPEC, spec_path)
    out_path.write_text(json.dumps(genuine_fix(SPEC)))

    for _ in range(3):
        mb.write_spec(SPEC, spec_path)  # every request rewrites it
        assert mb._try_offline(SPEC) is not None


def _offline(tmp_path, monkeypatch, payload):
    """Put `payload` on disk as a fresh, fingerprint-matching MATLAB result."""
    from minima import matlab_bridge as mb

    spec_path, out_path = tmp_path / "solve_spec.json", tmp_path / "solve_out.json"
    monkeypatch.setattr(mb, "SPEC_PATH", spec_path)
    monkeypatch.setattr(mb, "OUT_PATH", out_path)
    mb.write_spec(SPEC, spec_path)
    out_path.write_text(json.dumps(payload))
    return mb


NONSENSE = [
    pytest.param({"fund_index": 99, "asset_index": 0, "reduction": 0.3}, id="fund out of range"),
    pytest.param({"fund_index": -1, "asset_index": 0, "reduction": 0.3}, id="negative index wraps"),
    pytest.param({"fund_index": 0, "asset_index": 0, "reduction": 4.0}, id="sells 400% of it"),
    pytest.param({"fund_index": 0, "asset_index": 0, "reduction": -0.2}, id="buys instead"),
    pytest.param({"fund_index": 0, "asset_index": 0, "reduction": float("nan")}, id="nan"),
    pytest.param({"fund_index": 0, "asset_index": 1, "reduction": 0.01}, id="does not clear it"),
]


@pytest.mark.parametrize("payload", NONSENSE)
def test_a_nonsense_solver_result_is_not_handed_to_the_ui(tmp_path, monkeypatch, payload):
    """patternsearch can exit infeasible, and a hand-run file can be anything.

    Every one of these used to go straight through: a negative index silently
    picks the last fund, reduction > 1 flips the position negative, NaN makes
    the whole response invalid JSON, and a reduction that doesn't clear the
    condition is shown as the minima with the cascade still burning.
    """
    mb = _offline(tmp_path, monkeypatch, dict(payload, cost=0.01, solver="patternsearch"))

    assert mb._try_offline(SPEC) is None


def test_a_solver_result_that_actually_works_still_gets_through(tmp_path, monkeypatch):
    mb = _offline(tmp_path, monkeypatch, genuine_fix(SPEC))

    assert mb._try_offline(SPEC)["engine"] == "matlab-offline"


def test_a_bad_matlab_file_falls_through_to_python(tmp_path, monkeypatch):
    """Refusing it is only half the job — the demo still needs an answer."""
    mb = _offline(tmp_path, monkeypatch, {"fund_index": 0, "asset_index": 0,
                                          "reduction": 9.0, "cost": 0.0})

    result = mb.solve_stabilisation(SPEC)

    assert result is not None and result["engine"] == "python"


def test_the_python_path_reports_the_solves_it_actually_did(tmp_path, monkeypatch):
    """The readout sits next to MATLAB's funccount. It used to print
    rows*cols*20 — the size of the search space, not the search."""
    from minima import matlab_bridge as mb

    monkeypatch.setattr(mb, "OUT_PATH", tmp_path / "nothing.json")
    result = mb._python_fallback(SPEC)

    assert result["engine"] == "python"
    rows, cols = np.array(SPEC["holdings"]).shape
    assert 0 < result["evaluations"] < rows * cols * 20


def test_two_solves_at_once_do_not_answer_each_other_s_question():
    """`write_spec` writes one process-global file and `_try_offline` reads it
    back, and the server is threaded — so a second request could clobber
    data/cache/solve_spec.json in the window between the first request's write
    and its read.

    The fingerprint check does its job: the clobbered read is a mismatch, so
    the offline result is refused and the Python solver answers instead. The
    damage is that the SAME url returns two different fixes depending on
    whether anything else happened to be in flight — $2,236,598.53 or
    $2,251,028.20, a $14,430 swing on the one line in this product that tells
    somebody to do something — and `engine.fingerprint` comes back null on the
    unlucky one, which is the field the trace figure is named after.
    """
    import concurrent.futures

    from minima import api

    def solve(leverage):
        out = api.handle(f"/api/stabilise?leverage={leverage}&gamma=0.2&band=1.05&breaches=3", {})
        return (out["engine"]["kind"], round(out["fix"]["sell_usd"], 2),
                out["engine"].get("fingerprint"))

    alone = solve(5)
    seen = set()
    for _ in range(4):
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            both = list(pool.map(solve, [5, 6]))
        seen.add(both[0])

    assert seen == {alone}, (
        f"/api/stabilise?leverage=5 answered {sorted(seen)} under concurrency "
        f"and {alone} alone"
    )
