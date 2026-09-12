import numpy as np

from firebreak.thirteenf import build_holdings, parse_info_table

# trimmed-down version of a real infotable — namespaced, because that's
# what SEC actually serves and it's what breaks naive XML parsing
SAMPLE = """<?xml version="1.0" ?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable"
                  xmlns:n1="http://www.sec.gov/edgar/document/thirteenf/informationtable"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <infoTable>
    <nameOfIssuer>NVIDIA CORPORATION</nameOfIssuer>
    <cusip>67066G104</cusip>
    <value>1000</value>
    <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NVIDIA CORPORATION</nameOfIssuer>
    <cusip>67066G104</cusip>
    <value>500</value>
    <shrsOrPrnAmt><sshPrnamt>5</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NVIDIA CORPORATION</nameOfIssuer>
    <cusip>67066G104</cusip>
    <value>9999</value>
    <shrsOrPrnAmt><sshPrnamt>99</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <putCall>Call</putCall>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>7777</value>
    <shrsOrPrnAmt><sshPrnamt>77</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <putCall>Put</putCall>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>300</value>
    <shrsOrPrnAmt><sshPrnamt>3</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>SOME CONVERTIBLE NOTE</nameOfIssuer>
    <cusip>111111111</cusip>
    <value>4444</value>
    <shrsOrPrnAmt><sshPrnamt>44</sshPrnamt><sshPrnamtType>PRN</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


def test_option_rows_do_not_count_as_stock():
    positions = parse_info_table(SAMPLE)

    # the 9999 call and the 7777 put must not be in here
    assert positions["67066G10"] == 1500.0
    assert positions["03783310"] == 300.0


def test_duplicate_rows_for_one_issuer_are_added_up():
    positions = parse_info_table(SAMPLE)

    # NVDA was reported twice by different managers: 1000 + 500
    assert positions["67066G10"] == 1500.0


def test_bond_principal_is_not_a_share_position():
    positions = parse_info_table(SAMPLE)

    assert "11111111" not in positions


def test_namespaced_xml_parses_at_all():
    positions = parse_info_table(SAMPLE)

    assert len(positions) == 2


def test_holdings_matrix_lines_up_with_the_universe():
    universe = {"67066G10": "NVDA", "03783310": "AAPL", "59491810": "MSFT"}
    books = {
        "Alpha": {"67066G10": 600.0, "03783310": 400.0},
        "Beta": {"03783310": 250.0, "59491810": 750.0},
    }

    funds, tickers, matrix, _ = build_holdings(books, universe)

    assert funds == ["Alpha", "Beta"]
    assert tickers == ["NVDA", "AAPL", "MSFT"]
    np.testing.assert_allclose(matrix, [[600.0, 400.0, 0.0], [0.0, 250.0, 750.0]])


def test_a_fund_holding_nothing_in_the_universe_is_dropped():
    universe = {"67066G10": "NVDA"}
    books = {"Alpha": {"67066G10": 600.0}, "Empty": {"99999999": 100.0}}

    funds, _, matrix, _ = build_holdings(books, universe)

    assert funds == ["Alpha"]
    assert matrix.shape == (1, 1)


def test_share_classes_of_one_issuer_collapse_into_one_column():
    # Alphabet files under four CUSIPs. Mapping only one of them captured
    # 48% of Citadel's position and 15% of Millennium's — heterogeneous, so
    # it doesn't cancel, it just invents dispersion in the overlap metric.
    universe = {
        "02079K10": "GOOGL",  # class A
        "02079K30": "GOOGL",  # class C
        "67066G10": "NVDA",
    }
    books = {"Alpha": {"02079K10": 900.0, "02079K30": 1070.0, "67066G10": 500.0}}

    funds, tickers, matrix, _ = build_holdings(books, universe)

    assert tickers == ["GOOGL", "NVDA"]
    np.testing.assert_allclose(matrix, [[1970.0, 500.0]])


def test_ticker_column_order_is_first_appearance():
    universe = {"67066G10": "NVDA", "02079K10": "GOOGL", "02079K30": "GOOGL"}
    books = {"Alpha": {"67066G10": 1.0, "02079K30": 2.0}}

    _, tickers, _, _ = build_holdings(books, universe)

    assert tickers == ["NVDA", "GOOGL"]


def test_dropped_funds_are_reported_so_parameter_vectors_can_follow():
    # Per-fund leverage is a vector built from the manager list, not a dict.
    # Drop the third of five books and everything from index 2 onward slides
    # up one seat: "Empty"'s leverage lands on D, D's on E, E's on nobody.
    universe = {"67066G10": "NVDA"}
    books = {
        "A": {"67066G10": 10.0},
        "B": {"67066G10": 20.0},
        "Empty": {"99999999": 30.0},
        "D": {"67066G10": 40.0},
        "E": {"67066G10": 50.0},
    }
    leverage = [2.0, 3.0, 4.0, 5.0, 6.0]  # one per manager, original order

    funds, _, matrix, kept = build_holdings(books, universe)

    assert funds == ["A", "B", "D", "E"]
    assert kept == [0, 1, 3, 4]
    assert [leverage[i] for i in kept] == [2.0, 3.0, 5.0, 6.0]
    # the slide the caller would otherwise get, spelled out
    assert leverage[: len(funds)] == [2.0, 3.0, 4.0, 5.0]
    assert len(kept) == matrix.shape[0]
