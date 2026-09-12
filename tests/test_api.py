from firebreak import api


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
