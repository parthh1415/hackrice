from minima import api


def test_health_is_boring_and_works():
    assert api.handle("/api/health", {})["ok"] is True


def test_unknown_route_is_a_404_not_a_500():
    try:
        api.handle("/api/nope", {})
    except api.NotFound:
        return
    raise AssertionError("should have raised NotFound")


def test_dataset_endpoint_returns_the_real_books():
    result = api.handle("/api/dataset", {})

    assert len(result["funds"]) >= 2
    assert len(result["tickers"]) == len(result["holdings"][0])
    assert len(result["adv"]) == len(result["tickers"])
    assert result["source"] == "SEC 13F-HR"


def test_break_endpoint_finds_a_shock_and_names_the_ticker():
    result = api.handle("/api/break?leverage=6&gamma=0.5&breaches=2", {})

    assert result["found"] is True
    assert result["magnitude"] < 0
    assert result["asset"] in result["tickers"]
    assert result["trajectory"], "the UI animates this, it can't be empty"
    assert result["metrics"]["amplification"] >= 1.0


def test_break_reports_honestly_when_nothing_breaks():
    result = api.handle("/api/break?leverage=1&gamma=0.5&breaches=2", {})

    assert result["found"] is False


def test_stabilise_returns_an_instruction_in_words():
    result = api.handle("/api/stabilise?leverage=6&gamma=0.5&breaches=2", {})

    assert result["found"] is True
    assert result["fix"]["fund"] in result["funds"]
    assert result["fix"]["asset"] in result["tickers"]
    assert result["after"]["metrics"]["final_loss"] <= result["before"]["metrics"]["final_loss"]


def test_stabilise_names_the_shocked_asset_by_index_too():
    # the split view rings the shocked asset. without an index it falls back
    # to 0, which is right only by accident when the answer happens to be
    # the first ticker.
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})

    assert "asset_index" in result
    assert result["tickers"][result["asset_index"]] == result["asset"]


def test_break_and_stabilise_agree_on_the_shock():
    broke = api.handle("/api/break?leverage=5&gamma=0.2&breaches=3", {})
    fixed = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})

    assert broke["asset_index"] == fixed["asset_index"]
    assert abs(broke["pct"] - fixed["pct"]) < 1e-9


def test_stabilise_declares_which_engine_solved_it():
    result = api.handle("/api/stabilise?leverage=5&gamma=0.2&breaches=3", {})

    engine = result["engine"]
    assert engine["kind"] in ("matlab", "matlab-offline", "python")
    assert engine["name"]
    # the label must not say MATLAB unless MATLAB actually ran
    if engine["kind"] == "python":
        assert "MATLAB" not in engine["name"]
