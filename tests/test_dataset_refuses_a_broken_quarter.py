"""The two refusals in `load_dataset`, which nothing reached.

Both are one `if` each, both only reachable through `load_dataset(refresh=True)`,
and a mutation sweep removed each of them with all 218 tests green. They are the
guards standing between "we could not assemble this quarter" and a holdings
matrix that looks entirely normal and is wrong.

The missing-manager one is the nastier of the two, and the reason is worth
stating: taking a CIK away does not produce a missing fund, which anybody would
notice. It produces Two Sigma **present at half its real size**, because its
other registrant still filed — the exact multi-CIK undercount `manager_ciks`
exists to prevent, with the row count and `fund_indices` both looking right.

Neither needs the network. Stubbing `latest_filings` and `fetch_positions`
reaches both in milliseconds, which is why "it needs a refresh" was never a
good reason for them to go untested.
"""

import json
import pathlib

import pytest

from firebreak import dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "data" / "universe.json").read_text())
QUARTER = "06-30-2026"


def fake_edgar(monkeypatch, tmp_path, periods, silent=()):
    """Every configured CIK files a token book, except those told to go quiet."""
    positions = {cusip: 1_000_000.0 for cusip in CONFIG["cusips"]}

    def latest_filings(cik, look_back=8):
        if cik in silent:
            return ("Quiet Manager", "", [])
        return ("Manager", periods.get(cik, QUARTER),
                [{"accession": f"{cik:018d}", "period": periods.get(cik, QUARTER),
                  "raw_period": periods.get(cik, QUARTER),
                  "amendment_type": None, "is_amendment": False,
                  "filing_date": "2026-08-14"}])

    monkeypatch.setattr(dataset, "latest_filings", latest_filings)
    monkeypatch.setattr(dataset, "fetch_positions", lambda cik, acc: dict(positions))
    monkeypatch.setattr(dataset, "CACHE", tmp_path / "dataset.json")


def all_ciks():
    out = []
    for ciks in dataset.manager_ciks(CONFIG).values():
        out.extend(ciks)
    return out


def test_a_manager_that_files_nothing_stops_the_build(monkeypatch, tmp_path):
    quiet = dataset.manager_ciks(CONFIG)["Two Sigma"][0]
    fake_edgar(monkeypatch, tmp_path, {}, silent={quiet})

    with pytest.raises(RuntimeError, match="silently absent"):
        dataset.load_dataset(refresh=True)


def test_and_it_would_otherwise_be_a_half_sized_fund_not_a_missing_one():
    """Why that refusal has to be an error rather than a shrug.

    Two Sigma files under two CIKs. Drop one and the fund is still present,
    still in `funds`, still in `fund_indices` — just holding half of what it
    should. Nothing about the shape of the output says anything is wrong,
    which is why the guard cannot be a warning.

    Built through `assemble` directly so it shows the consequence without
    needing the guard lifted.
    """
    ciks = dataset.manager_ciks(CONFIG)["Two Sigma"]
    assert len(ciks) > 1, "this test needs a manager filing under several CIKs"

    per_cik = {cusip: 1_000_000.0 for cusip in CONFIG["cusips"]}
    whole = {c: dict(per_cik) for c in ("Citadel", "Two Sigma")}
    whole["Two Sigma"] = {k: v * len(ciks) for k, v in per_cik.items()}
    halved = {"Citadel": dict(per_cik), "Two Sigma": dict(per_cik)}

    args = (CONFIG["cusips"], CONFIG["adv_usd_millions"], QUARTER)
    full = dataset.assemble(whole, *args)
    short = dataset.assemble(halved, *args)

    assert full["funds"] == short["funds"], "the fund does not go missing"
    assert full["fund_indices"] == short["fund_indices"], "nor do the indices move"

    i = full["funds"].index("Two Sigma")
    assert sum(short["holdings"][i]) == pytest.approx(sum(full["holdings"][i]) / len(ciks)), (
        "losing one registrant should halve the book, which is the whole point: "
        "an undercount that looks structurally identical to the real thing"
    )


def test_managers_reporting_different_quarters_stop_the_build(monkeypatch, tmp_path):
    late = all_ciks()[0]
    fake_edgar(monkeypatch, tmp_path, {late: "03-31-2026"})

    with pytest.raises(RuntimeError, match="different periods"):
        dataset.load_dataset(refresh=True)


def test_a_clean_quarter_still_builds(monkeypatch, tmp_path):
    """So the two refusals above cannot be satisfied by refusing everything."""
    fake_edgar(monkeypatch, tmp_path, {})
    data = dataset.load_dataset(refresh=True)

    assert data["quarter"] == QUARTER
    assert len(data["funds"]) == len(CONFIG["managers"])
    assert all(sum(row) > 0 for row in data["holdings"])
