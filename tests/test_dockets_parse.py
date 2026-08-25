"""Parsing, the silent-failure trap assertions, and request shaping."""

import json

import pytest

from docketyard.capture import stb
from docketyard.ingest import dockets


def make_row(stb_id: str, title: str) -> str:
    return (
        f'<tr class="stb-row"><td><a class="stb-button-folder" data-stb-id="{stb_id}"'
        f' href="#{stb_id}"><svg></svg></a></td>'
        f"<td>{stb_id}</td><td>{title}</td>"
        f'<td><a href="#">Generate Service List</a></td></tr>'
    )


def make_body(rows: list[tuple[str, str]], total: int) -> bytes:
    rows_html = "".join(make_row(sid, title) for sid, title in rows)
    return json.dumps({"success": True, "data": {"rows": rows_html, "total": total}}).encode()


# --- docket id decomposition ---------------------------------------------------------


def test_parse_parent_docket():
    assert dockets.parse_docket_id("EP_749_0") == dockets.ParsedDocket("EP", 749, None, None)


def test_parse_bare_parent_form():
    # Both parent spellings observed live 2026-08-25: FD_36873 (bare) and FD_36339_0.
    assert dockets.parse_docket_id("FD_36873") == dockets.parse_docket_id("FD_36873_0")


def test_parse_sub_docket_with_suffix():
    assert dockets.parse_docket_id("AB_55_785_X") == dockets.ParsedDocket("AB", 55, 785, "X")


def test_parse_normalises_suffix_case():
    assert dockets.parse_docket_id("AB_32_98_x") == dockets.parse_docket_id("AB_32_98_X")


def test_parse_rejects_garbage():
    for bad in ("", "FD", "FD_x_0", "36873_FD_0", "WB25-53"):
        assert dockets.parse_docket_id(bad) is None


# --- response decoding ---------------------------------------------------------------


def test_parse_rows_extracts_id_and_title():
    parsed = dockets.parse_response(
        make_body([("FD_36339_0", "WISCONSIN RAPIDS &#8212; LEASE")], total=1)
    )
    assert parsed.total == 1 and parsed.skipped == 0
    assert parsed.rows[0].stb_id == "FD_36339_0"
    assert "—" in parsed.rows[0].title  # entities decoded


def test_row_regex_tolerates_tr_attributes():
    # make_row already emits <tr class="stb-row">; zero skipped proves the regex copes
    parsed = dockets.parse_response(make_body([("EP_749_0", "T")], total=1))
    assert parsed.skipped == 0 and len(parsed.rows) == 1


def test_markup_drift_is_counted_not_swallowed():
    body = json.dumps(
        {"success": True, "data": {"rows": "<tr><td>no id here</td></tr>", "total": 5}}
    ).encode()
    parsed = dockets.parse_response(body)
    assert parsed.rows == [] and parsed.skipped == 1


def test_number_cell_must_corroborate_the_id():
    row = make_row("EP_749_0", "T").replace("<td>EP_749_0</td>", "<td>SOMETHING ELSE</td>")
    body = json.dumps({"success": True, "data": {"rows": row, "total": 1}}).encode()
    assert dockets.parse_response(body).skipped == 1


def test_nonce_expiry_body_zero_raises():
    # WordPress answers an expired nonce with HTTP 200 and the literal body `0`
    with pytest.raises(ValueError):
        dockets.parse_response(b"0")


def test_non_json_body_raises():
    with pytest.raises(ValueError):
        dockets.parse_response(b"<html>WAF interstitial</html>")


# --- the positive filter assertion ---------------------------------------------------


def test_unfiltered_request_is_vacuously_asserted():
    parsed = dockets.parse_response(make_body([("EP_749_0", "T")], total=1))
    assert dockets.assert_filter([], parsed) is True


def test_ignored_criteria_detected():
    # THE trap: criteria silently ignored -> full unfiltered set comes back. Rows that do
    # not match the sent criteria must fail the assertion.
    parsed = dockets.parse_response(
        make_body([("EP_749_0", "T"), ("AB_55_785_X", "T")], total=10000)
    )
    assert dockets.assert_filter([("docketNum_one", "FD")], parsed) is False


def test_matching_criteria_asserted():
    parsed = dockets.parse_response(make_body([("FD_36873_0", "T"), ("FD_36873_1", "T")], total=2))
    criteria = [("docketNum_one", "FD"), ("docketNum_two", "36873")]
    assert dockets.assert_filter(criteria, parsed) is True


def test_unverifiable_criterion_quarantines():
    # a criterion this code cannot check must never be marked asserted
    parsed = dockets.parse_response(make_body([("FD_36873_0", "T")], total=1))
    assert dockets.assert_filter([("docketTitle", "MERGER")], parsed) is False


def test_zero_rows_with_criteria_is_a_signal_not_a_result():
    empty = dockets.ParsedResponse(rows=[], total=0, skipped=0)
    assert dockets.assert_filter([("docketNum_one", "FD")], empty) is False


def test_nonzero_total_with_no_rows_quarantines_even_unfiltered():
    drifted = dockets.ParsedResponse(rows=[], total=10000, skipped=0)
    assert dockets.assert_filter([], drifted) is False


def test_skipped_rows_quarantine():
    parsed = dockets.ParsedResponse(
        rows=dockets.parse_response(make_body([("FD_1_0", "T")], total=2)).rows,
        total=2,
        skipped=1,
    )
    assert dockets.assert_filter([], parsed) is False


def test_display_cap_detected():
    assert dockets.hit_display_cap(stb.DISPLAY_CAP) is True
    assert dockets.hit_display_cap(stb.DISPLAY_CAP - 1) is False


# --- request shaping -----------------------------------------------------------------


def test_build_fields_uses_the_criteria_array_form():
    fields = stb.build_fields(
        "stb_hook_table_dockets",
        "abc123",
        [("docketNum_one", "FD"), ("docketNum_two", "36873")],
        page=2,
        per_page=50,
    )
    d = dict(fields)
    # the trap: plain POST fields are silently ignored; only the array form filters
    assert d["search-criteria[0][name]"] == "docketNum_one"
    assert d["search-criteria[0][value]"] == "FD"
    assert d["search-criteria[1][name]"] == "docketNum_two"
    assert d["search-criteria[1][value]"] == "36873"
    assert "docketNum_one" not in d and "docketNum_two" not in d
    assert d["page"] == "2" and d["per-page"] == "50"


def test_nonce_parser_survives_attribute_reordering():
    page = (
        '<table class="x" data-stb-nonce="AB12cd" other="y"'
        ' data-stb-action="stb_hook_table_dockets">'
        '\n<div data-stb-action="stb_hook_table_filings"\n data-stb-nonce="ff00aa">'
    )
    nonces = stb.parse_nonces(page)
    assert nonces["stb_hook_table_dockets"] == "AB12cd"
    assert nonces["stb_hook_table_filings"] == "ff00aa"
