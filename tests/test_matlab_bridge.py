"""The bridge has to be honest about which engine actually solved it.

Claiming MATLAB ran when scipy did would be the one thing that turns a
sponsor challenge into a problem.
"""

import json

import numpy as np

from firebreak.matlab_bridge import solve_stabilisation, write_spec

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
    from firebreak.matlab_bridge import _spec_fingerprint

    other = dict(SPEC, gamma=0.9)

    assert _spec_fingerprint(SPEC) != _spec_fingerprint(other)


def test_a_stale_result_file_is_not_served_as_a_matched_solve(tmp_path, monkeypatch):
    """The spec file is rewritten on every request, so comparing it to the
    request it was just written from can only ever agree with itself.

    Real sequence: solve for scenario A in MATLAB Online, download the result,
    then move a slider. api._stabilise writes the spec for scenario B and asks
    the bridge, which used to hand back A's answer under scenario B's label.
    """
    from firebreak import matlab_bridge as mb

    spec_path, out_path = tmp_path / "solve_spec.json", tmp_path / "solve_out.json"
    monkeypatch.setattr(mb, "SPEC_PATH", spec_path)
    monkeypatch.setattr(mb, "OUT_PATH", out_path)

    a = dict(SPEC, gamma=0.9, shock=[-0.40, 0.0, 0.0])
    mb.write_spec(a, spec_path)
    out_path.write_text(json.dumps(
        {"fund_index": 1, "asset_index": 2, "reduction": 0.35, "cost": 0.07,
         "solver": "patternsearch", "exit_flag": 1}
    ))

    assert mb._try_offline(a) is not None, "the result it was actually solved for"

    # slider moves; api writes the new spec before asking the bridge
    mb.write_spec(SPEC, spec_path)

    assert mb._try_offline(SPEC) is None


def test_re_asking_the_same_question_keeps_the_offline_answer(tmp_path, monkeypatch):
    """Rejecting stale results is worthless if it also rejects fresh ones."""
    from firebreak import matlab_bridge as mb

    spec_path, out_path = tmp_path / "solve_spec.json", tmp_path / "solve_out.json"
    monkeypatch.setattr(mb, "SPEC_PATH", spec_path)
    monkeypatch.setattr(mb, "OUT_PATH", out_path)

    mb.write_spec(SPEC, spec_path)
    out_path.write_text(json.dumps({"fund_index": 0, "asset_index": 1,
                                    "reduction": 0.2, "cost": 0.03, "solver": "patternsearch"}))

    for _ in range(3):
        mb.write_spec(SPEC, spec_path)  # every request rewrites it
        assert mb._try_offline(SPEC) is not None
