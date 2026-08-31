"""Slice paging and the resumable backfill walk, against a scripted fake endpoint."""

import json

import pytest

from docketyard.capture import walk
from docketyard.capture.stb import DOCKET_PREFIXES, DOCKETS, EXPECTED_EMPTY_PREFIXES, FILINGS
from docketyard.store import db, projections
from tests.test_dockets_parse import make_body
from tests.test_observations import body_of, filing_row

# Verbatim from the live endpoint, 2026-08-31. The TWO-WORD table name is the point: a
# fixture naming a one-word table let a detector that could not span a space pass every
# test in this file while failing on the real thing (ultrareview).
NO_RESULTS = (
    b'{"success":false,"data":{"error":"<p>There are no environmental comments'
    b' available at this time.<\\/p>\\n"}}'
)


class FakeEndpoint:
    """Answers pages from prefix -> ids; can misreport total, or go dark after N requests
    (an expired nonce) until refresh_nonces() is called."""

    def __init__(self, data: dict[str, list[str]], *, total_override=None, dark_after=None):
        self.data = data
        self.total_override = total_override
        self.dark_after = dark_after
        self.requests = 0
        self.refreshes = 0
        self.sorts: set[tuple[str, str]] = set()

    def refresh_nonces(self):
        self.refreshes += 1
        self.dark_after = None

    def query_table(self, action, criteria, *, page, per_page, sort_by, sort_order):
        self.requests += 1
        self.sorts.add((sort_by, sort_order))
        if self.dark_after is not None and self.requests > self.dark_after:
            return 200, NO_RESULTS, []
        prefix = dict(criteria).get("docketNum_one", "")
        ids = self.data.get(prefix, [])
        per_page = min(per_page, 50)  # the server clamp
        chunk = ids[(page - 1) * per_page : page * per_page]
        if not chunk:
            return 200, NO_RESULTS, []
        total = self.total_override if self.total_override is not None else len(ids)
        if action == FILINGS:
            rows = "".join(filing_row(docket=f"{prefix}_36873", fid=i.split("_")[1]) for i in chunk)
            return 200, body_of(rows, total), []
        return 200, make_body([(i, f"title {i}") for i in chunk], total=total), []


def ids(prefix, n):
    return [f"{prefix}_{i}_0" for i in range(1, n + 1)]


def run_slice(con, ep, tmp_path, prefix, **kw):
    return walk.capture_slice(
        con, ep, DOCKETS, [("docketNum_one", prefix)], data_dir=tmp_path, log=lambda *_: None, **kw
    )


@pytest.fixture
def con():
    return db.connect(":memory:")


# --- one slice -----------------------------------------------------------------------


def test_short_page_ends_the_slice(con, tmp_path):
    ep = FakeEndpoint({"FD": ids("FD", 66)})
    r = run_slice(con, ep, tmp_path, "FD")
    assert (r.rows, r.captures, r.status) == (66, 2, "done")
    assert ep.sorts == {("docketNum", "asc")}  # the pinned, measured-stable sort


def test_exactly_full_last_page_ends_on_a_reconciled_envelope(con, tmp_path):
    ep = FakeEndpoint({"FD": ids("FD", 100)})
    r = run_slice(con, ep, tmp_path, "FD")
    assert (r.rows, r.captures, r.status) == (100, 3, "done")
    # the envelope capture is asserted-vacuously and consumed, never pending
    assert projections.pending_capture_ids(con, DOCKETS) == [1, 2]
    assert projections.status(con)["captures_quarantined"] == 0


def test_short_page_that_does_not_reconcile_is_partial(con, tmp_path):
    # the endpoint promised 80 rows but the pages stopped at 66: the index moved, or a page
    # was lost — never recorded as done
    ep = FakeEndpoint({"FD": ids("FD", 66)}, total_override=80)
    assert run_slice(con, ep, tmp_path, "FD").status == "partial"


def test_envelope_on_page_one_is_the_trap_unless_the_census_expects_it(con, tmp_path):
    ep = FakeEndpoint({})
    trap = run_slice(con, ep, tmp_path, "FD")
    assert trap.status == "partial" and trap.envelope_on_first_page
    assert projections.status(con)["captures_quarantined"] == 1  # judged, not unjudged
    assert run_slice(con, ep, tmp_path, "ARB", expected_empty=True).status == "empty"


def test_mid_slice_envelope_refreshes_the_nonce_once_and_continues(con, tmp_path):
    # 173 pages of FD; the nonce expires after request 2, the retry with a fresh nonce
    # lands, the slice completes and reconciles
    ep = FakeEndpoint({"FD": ids("FD", 120)}, dark_after=2)
    r = run_slice(con, ep, tmp_path, "FD")
    assert (r.rows, r.status, ep.refreshes) == (120, "done", 1)
    assert projections.status(con)["captures_quarantined"] == 1  # the dark response, kept


def test_capped_slice_is_its_own_status(con, tmp_path):
    ep = FakeEndpoint({"AB": ids("AB", 60)}, total_override=10_000)
    r = run_slice(con, ep, tmp_path, "AB", pages=2)
    assert r.capped and r.status == "capped"


def test_quarantined_rows_are_not_counted(con, tmp_path):
    # page 2 answers with foreign rows (criteria silently dropped): those rows never count
    class Drift(FakeEndpoint):
        def query_table(self, action, criteria, **kw):
            if kw["page"] == 2:
                return 200, make_body([("EP_1_0", "x")] * 1, total=51), []
            return super().query_table(action, criteria, **kw)

    ep = Drift({"FD": ids("FD", 51)})
    r = run_slice(con, ep, tmp_path, "FD")
    assert r.status == "partial" and r.rows == 50


def test_filings_slice_uses_the_filings_sort_and_parser(con, tmp_path):
    ep = FakeEndpoint({"FD": ids("FD", 3)})
    r = walk.capture_slice(
        con, ep, FILINGS, [("docketNum_one", "FD")], data_dir=tmp_path, log=lambda *_: None
    )
    assert r.status == "done" and r.rows == 3
    assert ep.sorts == {("officialFilingDate", "desc")}


# --- the walk ------------------------------------------------------------------------


def test_walk_records_every_prefix_and_resumes(con, tmp_path):
    data = {"FD": ids("FD", 3), "AB": ids("AB", 51)}
    data |= {
        p: ids(p, 1)
        for p in DOCKET_PREFIXES
        if p not in ("FD", "AB") and p not in EXPECTED_EMPTY_PREFIXES
    }
    ep = FakeEndpoint(data)
    summary = walk.walk_dockets(con, ep, data_dir=tmp_path, log=lambda *_: None)
    assert summary["done"] == len(DOCKET_PREFIXES) - len(EXPECTED_EMPTY_PREFIXES)
    assert summary["empty"] == len(EXPECTED_EMPTY_PREFIXES) and summary["partial"] == 0
    assert walk.slice_status(con, f"{DOCKETS}:ARB") == "empty"
    # a rerun skips done AND empty: no second quarantined capture per empty prefix
    before = projections.status(con)["captures_quarantined"]
    again = walk.walk_dockets(con, ep, data_dir=tmp_path, log=lambda *_: None)
    assert again["skipped"] == len(DOCKET_PREFIXES)
    assert projections.status(con)["captures_quarantined"] == before
    criteria = json.loads(
        con.execute(
            "SELECT criteria FROM walk_slice WHERE slice_key=?", (f"{DOCKETS}:AB",)
        ).fetchone()[0]
    )
    assert criteria == [["docketNum_one", "AB"]]


def test_walk_that_captures_nothing_is_a_failure_not_thirty_four_empties(con, tmp_path):
    ep = FakeEndpoint({})  # a renamed sort key or dead nonce answers every prefix this way
    summary = walk.walk_dockets(con, ep, data_dir=tmp_path, log=lambda *_: None)
    assert summary["done"] == 0
    assert summary["partial"] == len(DOCKET_PREFIXES) - len(EXPECTED_EMPTY_PREFIXES)
    assert summary["empty"] == len(EXPECTED_EMPTY_PREFIXES)


def test_walk_isolates_a_failing_slice(con, tmp_path):
    class Explodes(FakeEndpoint):
        def query_table(self, action, criteria, **kw):
            if dict(criteria)["docketNum_one"] == "AB":
                raise RuntimeError("403 from the WAF")
            return super().query_table(action, criteria, **kw)

    ep = Explodes({"FD": ids("FD", 2), "AB": ids("AB", 2)})
    summary = walk.walk(
        con, ep, DOCKETS, walk.docket_prefix_slices()[:11], data_dir=tmp_path, log=lambda *_: None
    )
    assert walk.slice_status(con, f"{DOCKETS}:AB") == "partial"
    assert walk.slice_status(con, f"{DOCKETS}:FD") == "done"
    assert summary["partial"] >= 1 and summary["done"] >= 1
