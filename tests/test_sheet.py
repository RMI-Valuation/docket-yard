"""The docket-sheet projection over a small real-shaped record."""

import pytest
from fastapi.testclient import TestClient

from docketyard.capture import records
from docketyard.capture.stb import DECISIONS, DOCKETS, FILINGS
from docketyard.ingest import dockets, observations
from docketyard.store import db, sheet
from docketyard.web.app import create_app
from tests.test_dockets_parse import make_body
from tests.test_observations import body_of, decision_row, filing_row
from tests.test_web import build_store


@pytest.fixture
def con():
    return db.connect(":memory:")


def save(con, data_dir, body, action):
    cid = records.save_capture(
        con,
        data_dir,
        source_system="stb-ajax",
        endpoint="test",
        table_action=action,
        request_params=[],
        body=body,
        http_status=200,
        ingest_mode="forward",
    )
    records.set_verdict(con, cid, filter_asserted=True, row_count=0, reported_total=0)
    return cid


def build(con, tmp_path):
    dockets.ingest_capture(
        con,
        tmp_path,
        save(
            con,
            tmp_path,
            make_body([("FD_36873", "UP/NS CONTROL"), ("FD_36873_1", "PEORIA SUB")], total=2),
            DOCKETS,
        ),
    )
    filings = (
        filing_row(fid="311981", date="8/25/2026", filed_for="NRDC", ftype="Motion")
        + filing_row(fid="311977", date="8/24/2026", filed_for="UP", ftype="Reply")
        + filing_row(
            docket="FD_36873_1", fid="311900", date="8/24/2026", filed_for="PPU", ftype="Letter"
        )
    )
    observations.ingest_capture(con, tmp_path, save(con, tmp_path, body_of(filings, 3), FILINGS))
    decisions = decision_row(did="53210", date="8/24/2026", summary="ORDERED REPLIES DUE")
    observations.ingest_capture(
        con, tmp_path, save(con, tmp_path, body_of(decisions, 1), DECISIONS)
    )


def test_sheet_merges_family_newest_first(con, tmp_path):
    build(con, tmp_path)
    parent = con.execute("SELECT docket_id FROM docket WHERE raw_docket='FD_36873'").fetchone()[0]
    s = sheet.docket_sheet(con, parent)
    assert s is not None
    assert s.title == "UP/NS CONTROL"
    assert [m.raw_docket for m in s.sub_dockets] == ["FD_36873_1"]
    # the index carries what the record holds for each proceeding on its own: the
    # sub-docket has one filing and no decision of its own, while the parent holds two
    # filings and a decision — so this page is a case with phases, not a series index
    assert [(m.filings, m.decisions, m.last_activity) for m in s.sub_dockets] == [
        (1, 0, "2026-08-24")
    ]
    assert s.is_index is False
    assert (s.filings, s.decisions) == (3, 1)
    assert [(e.kind, e.date, e.record_id) for e in s.entries] == [
        ("filing", "2026-08-25", "311981"),
        ("decision", "2026-08-24", "53210"),  # same day: decision before filings
        ("filing", "2026-08-24", "311977"),
        ("filing", "2026-08-24", "311900"),  # the sub-docket's entry, labelled as such
    ]
    assert s.entries[3].docket_raw == "FD_36873_1"
    decision = s.entries[1]
    assert decision.summary == "ORDERED REPLIES DUE" and decision.deciding_body == "Chief Counsel"
    assert decision.date_printed == "8/24/2026"  # the quoted form travels with the entry
    assert decision.attachments[0].url.endswith("53210.pdf")
    assert decision.attachments[0].document_sha256 is None  # not fetched yet
    assert s.last_checked is not None


def test_sub_docket_sheet_is_its_own(con, tmp_path):
    build(con, tmp_path)
    sub = con.execute("SELECT docket_id FROM docket WHERE raw_docket='FD_36873_1'").fetchone()[0]
    s = sheet.docket_sheet(con, sub)
    assert s is not None and s.sub_dockets == [] and s.filings == 1


def test_unknown_docket(con):
    assert sheet.docket_sheet(con, 999) is None


def test_a_sub_docket_sheet_can_reach_its_series(tmp_path):
    """`_family` is asked for the page's OWN id and a sub-docket has no children, so the
    family list came back holding only itself: no parent link, no siblings, no way back.
    On AB 167 that is 952 of 995 proceedings ending in a cul-de-sac
    (navigation-review.md § C)."""
    path = build_store(tmp_path)
    con = db.connect(path)
    sub_id = con.execute("SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873_1'").fetchone()[
        0
    ]
    family_id = con.execute(
        "SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873'"
    ).fetchone()[0]
    child = sheet.docket_sheet(con, sub_id)
    assert child.series is not None
    assert child.series.raw_docket == "FD_36873"  # the number, and nothing it must scan for
    assert child.sub_dockets == []  # unchanged: a sub-docket has no children
    # a family is nobody's child, and says nothing it cannot back
    assert sheet.docket_sheet(con, family_id).series is None
    con.close()
    client = TestClient(create_app(path))
    page = client.get("/d/FD-36873/sub/1").text
    assert '<a href="/d/FD-36873">FD 36873</a>' in page
    assert "Before the Surface Transportation Board" not in page  # the way up replaces it
    assert "Before the Surface Transportation Board" in client.get("/d/FD-36873").text
