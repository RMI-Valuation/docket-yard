"""The own-fused rule (ADR 0018 addendum of 2026-09-14, Accepted): a footnote digit fused onto the
document's own docket keys as that docket. `STB Finance Docket No. 340071` in a decision filed in
FD 34007 is FD 34007 — one function holds the rule, the finding carries its key, and `load` checks
both rather than trusting them."""

import json

import pytest

from docketyard.citator import find, keys, load, resolve, walk
from tests.test_citator_pipeline import SHA, _batch, _load_verb, _scored, _store
from tests.test_citator_retraction import OLD, _load, _older, _reading, _walked
from tests.test_citator_walk import _page

OWN = {"FD 36873", "FD 36873 (1)"}  # `_store`'s family for SHA
CAPTION = "STB Finance Docket No. 368731\nKANSAS CITY RAILWAY\n\nIn FD 36873 the Board said so.\n"


def test_the_rule_keys_a_fused_six_digit_number_as_the_own_docket_and_nothing_else():
    assert keys.own_key("FD 368731", OWN) == "FD 36873"
    assert keys.own_key("FD 368731", {"EP 445"}) == "FD 368731", "not own: stays as printed"
    assert keys.own_key("EP 368731", OWN) == "EP 368731", "another prefix's number"
    assert keys.own_key("FD 36873", {"FD 3687"}) == "FD 36873", "five digits is rule 2's, not this"
    assert keys.own_key("FD 368731 (1)", OWN) == "FD 368731 (1)", "only a bare number can fuse"
    assert keys.own_key("NOR 253517", {"NOR 253517", "NOR 25351"}) == "NOR 253517", "own already"
    assert keys.own_key(None, OWN) is None


def test_both_printed_forms_are_one_finding_on_the_own_key_and_it_verifies():
    """Item 8: 177 of the 346 pages print both forms, and the span check accepts both."""
    [f] = find.find(CAPTION, OWN)
    assert (f["key"], f["target"], f["kind"]) == (
        "FD 36873",
        "Finance Docket No. 368731",
        "caption",
    )
    assert [raw for _, _, raw in f["spans"]] == ["Finance Docket No. 368731", "FD 36873"]

    doc = {"document_sha256": SHA, "findings": [{**f, "page": 1}]}
    find.verify_spans([(1, CAPTION)], doc, OWN)
    # the same file checked against a family that no longer holds FD 36873 departs
    with pytest.raises(find.Departed, match="keys as 'FD 368731'"):
        find.verify_spans([(1, CAPTION)], doc, {"EP 445"})


def test_a_load_keys_it_as_the_own_docket_and_records_the_rule_on_the_reading(tmp_path):
    con = _store(tmp_path)
    _page(con, SHA, 1, CAPTION + "See EP 445, slip op. at 3.\n")
    con.commit()
    stamps = _scored(con, extractor_version=find.FINDER_VERSION)

    doc = next(walk.documents(con))
    load.load_document(con, doc, keys.registry(con), keys.works(con), stamps)
    rows = {
        key: (raw, json.loads(location))
        for key, raw, location in con.execute(
            "SELECT target_key, cited_raw, source_location FROM citation_reading"
            " WHERE superseded_by IS NULL"
        )
    }
    assert set(rows) == {"FD 36873", "EP 445"}
    raw, location = rows["FD 36873"]
    assert raw == "Finance Docket No. 368731", "cited_raw stays as printed"
    assert len(location["spans"]) == 2
    assert location["key_rule"] == {
        "rule": "own-fused",
        "printed_keys": ["FD 368731"],
        "own": ["FD 36873", "FD 36873 (1)"],
    }
    assert "key_rule" not in rows["EP 445"][1], "recorded only where the rule shaped the key"
    assert con.execute(
        "SELECT outcome, cited_docket_id FROM citation_resolution"
        " WHERE target_key = 'FD 36873' AND superseded_by IS NULL"
    ).fetchone() == ("resolved", 1)


def test_load_refuses_a_key_the_rule_does_not_give(tmp_path):
    """Item 7: a forged key, and a finding the rule no longer re-keys because `own` changed."""
    con = _store(tmp_path)
    stamps = _scored(con)
    con.commit()  # the cards survive the rollback below, which undoes only the load
    forged = {"page": 4, "key": "FD 36873", "target": "EP 445", "quoted": "See EP 445."}
    with pytest.raises(find.Departed, match="keys as 'EP 445'"):
        _load(con, _walked(forged), stamps)
    keyless = _walked(forged)
    keyless["findings"][0].pop("key")  # a key recomputed at load would skip the check
    with pytest.raises(find.Departed, match="carries key None"):
        _load(con, keyless, stamps)

    stale = {"page": 4, "key": "FD 36873", "target": "FD 368731", "quoted": "FD 368731"}
    _load(con, _walked(stale), stamps)  # the family holds FD 36873: it loads
    con.rollback()
    con.execute("DELETE FROM decision_attachment")  # and now no decision carries the document
    with pytest.raises(find.Departed, match="keys as 'FD 368731'"):
        _load(con, _walked(stale), stamps)


def test_a_held_six_digit_docket_is_never_re_keyed_and_the_load_names_it(tmp_path, capsys):
    """Item 3: counted apart from a fault, named on every run, nothing written."""
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence, sub_sequence, suffix,"
        " parent_docket_id) VALUES (5, 'FD_368731', 'FD', 368731, NULL, NULL, NULL)"
    )
    _scored(con, extractor_version=find.FINDER_VERSION)
    con.commit()
    finding = {"page": 4, "key": "FD 36873", "target": "FD 368731", "quoted": "FD 368731"}
    doc = _walked(finding) | {"method_version": find.FINDER_VERSION}

    assert _load_verb(tmp_path, _batch(tmp_path, one=doc)) == 3
    out = capsys.readouterr().out
    assert "'refused_fused_held': 1" in out and SHA in out
    assert con.execute("SELECT count(*) FROM citation").fetchone()[0] == 0


def test_an_older_finders_six_digit_key_points_at_the_own_key_and_its_reading_follows(tmp_path):
    """Item 11: decision 2's successor shape, and the 2026-09-13 addendum's reading retirement."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _older(con, 4, "FD 368731")
    _reading(con, 4, "FD 368731", "text-layer", OLD)
    now = {"page": 4, "key": "FD 36873", "target": "FD 368731", "quoted": "FD 368731 KANSAS CITY"}

    result = _load(con, _walked(now), stamps)
    assert (result.retracted, result.readings_retired) == (1, 1)
    citation, reading = con.execute(
        "SELECT c.citation_id, r.reading_id FROM citation c JOIN citation_reading r"
        " USING (citing_document, page, target_kind, target_key)"
        " WHERE c.target_key = 'FD 36873' AND c.superseded_by IS NULL AND r.superseded_by IS NULL"
    ).fetchone()
    assert con.execute(
        "SELECT superseded_by FROM citation WHERE target_key = 'FD 368731'"
    ).fetchone() == (citation,)
    assert con.execute(
        "SELECT superseded_by FROM citation_reading WHERE target_key = 'FD 368731'"
    ).fetchone() == (reading,)


def test_a_six_digit_key_no_longer_printed_is_not_pointed_at_the_own_key(tmp_path):
    """Item 11's shape is used only where the rule fired: a page whose text now prints only the
    own key retires the old six-digit key at itself rather than claiming a re-key."""
    con = _store(tmp_path)
    stamps = _scored(con)
    _older(con, 4, "FD 368731")
    now = {"page": 4, "target": "FD 36873", "quoted": "FD 36873 KANSAS CITY"}
    assert _load(con, _walked(now), stamps).retracted == 1
    assert con.execute(
        "SELECT 1 FROM citation WHERE target_key = 'FD 368731' AND superseded_by = citation_id"
    ).fetchone()


def test_a_benchmark_reading_records_every_printed_form_the_rule_re_keyed(tmp_path):
    """Items 3 and 4 on a reading with no offsets: the second printed form is seen as well."""
    con = _store(tmp_path)
    stamps = _scored(con)
    page = "In FD 36873 the Board said so.\nSTB Finance Docket No. 368731\n"
    doc = find.findings_document([(4, page)], document_sha256=SHA, own=OWN, text_ref="benchmark")
    [f] = doc["findings"]
    assert "spans" not in f and f["printed"] == ["FD 36873", "Finance Docket No. 368731"]

    _load(con, doc | {"method_version": "v1"}, stamps)  # `_scored`'s finder
    location = json.loads(
        con.execute(
            "SELECT source_location FROM citation_reading WHERE superseded_by IS NULL"
        ).fetchone()[0]
    )
    assert location["key_rule"]["printed_keys"] == ["FD 368731"]


def test_the_served_date_anchors_on_either_printed_form():
    """Item 9: the window anchors on the finding's key, through the rule for the document."""
    held, works = {"FD 36873": 1}, {(1, "2021-03-12"): "52526"}
    line = "STB Finance Docket No. 368731 (STB served Mar. 12, 2021)"
    printed = "Finance Docket No. 368731"
    r = resolve.resolve("FD 36873", held, works, line, printed, OWN)
    assert (r.outcome, r.method, r.decision_id) == ("resolved", resolve.RULE_1, "52526")
    assert resolve.resolve("FD 36873", held, works, line, printed, set()).decision_id is None


def test_load_reads_the_walks_family_for_one_document(tmp_path):
    con = _store(tmp_path)
    assert walk.own_of(con, SHA) == walk.own_by_document(con)[SHA] == OWN
    assert walk.own_of(con, "e" * 64) == set()
