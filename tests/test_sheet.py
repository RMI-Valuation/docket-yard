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


def test_an_entry_icon_is_defined_once_and_referenced(tmp_path):
    """Every entry link carried its own inline `<svg>` with four `<path>` children: 2,233
    copies on FD 36873, roughly 11,000 of the page's 27,537 elements. That DOM cost is what
    `navigation-review.md` § D measured, and the `<symbol>`/`<use>` collapse is the cheaper
    of the two moves it asked to be priced before pagination."""
    path = build_store(tmp_path)
    page = TestClient(create_app(path)).get("/d/FD-36873").text
    assert page.count("<symbol ") == 2  # one definition per icon
    assert page.count("<use ") >= 1  # and every link references one
    assert 'href="#i-board"' in page
    # the definitions are the only place the paths appear
    assert page.count('d="M6 3h8l5 5v13H6z"') == 1
    assert page.count('d="M12 3v10"') == 1
    # the icons stay hidden from the accessibility tree; the link carries the label
    assert page.count('<svg class="vh"') == 1
    assert "The Board’s own file for" in page


def test_a_series_sheet_does_not_build_the_entries_it_never_renders(tmp_path):
    """`/d/AB-167` assembled all 2,628 entries of its 995 sub-dockets — a payload and an
    attachment query EACH — and the template then rendered none of them, in 399 KB of prose
    over 866 records of work, on every request (navigation-review.md A7). Each proceeding
    keeps its entries at its own address, which the index links."""
    path = build_store(tmp_path)
    con = db.connect(path)
    parent = con.execute(
        "INSERT INTO docket (raw_docket, prefix, sequence) VALUES ('AB_167', 'AB', 167)"
    ).lastrowid
    for sub in range(1, sheet.SERIES_SUBS + 2):
        con.execute(
            "INSERT INTO docket (raw_docket, prefix, sequence, sub_sequence, suffix,"
            " parent_docket_id) VALUES (?, 'AB', 167, ?, 'X', ?)",
            (f"AB_167_{sub}_X", sub, parent),
        )
    con.commit()
    s = sheet.docket_sheet(con, parent)
    assert s.is_index and s.entries == []  # the series itself carries none
    assert len(s.sub_dockets) == sheet.SERIES_SUBS + 1
    assert (s.filings, s.decisions, s.comments) == (0, 0, 0)
    assert s.parties == []  # not rendered on a series, so not resolved either

    # a family that IS a case still builds its entries, and its counts still fold
    case = con.execute("SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873'").fetchone()[0]
    c = sheet.docket_sheet(con, case)
    assert not c.is_index and c.entries
    assert c.filings == 2 and c.decisions == 1  # by the Board's id, not two rows
    con.close()

    client = TestClient(create_app(path))
    page = client.get("/d/AB-167")
    assert page.status_code == 200 and 'href="/d/AB-167/sub/1X"' in page.text
    # and the JSON twin says the same thing the page does (shape 2)
    body = client.get("/d/AB-167.json").json()
    assert body["docket"]["entries"] == [] and body["docket"]["is_index"] is True
    assert len(body["docket"]["sub_dockets"]) == sheet.SERIES_SUBS + 1


def test_one_entry_agrees_with_the_sheet_and_does_not_build_it(tmp_path):
    """A record page reading one row off a fully-built sheet took production down three
    times on 2026-09-02: FD 35087 holds 12,031 of the record's 34,255 comments, every
    comment page assembled all of them — a payload and an attachment query EACH — at a
    measured 21.5 s a page, and this site's own sitemap offers a crawler all 12,031
    addresses. `one_entry` fetches the copies of the ONE record instead.

    Both halves are asserted, because either alone would be worthless: the entry must be
    the SAME entry the sheet lists (or the page quietly disagrees with the list it came
    from), and getting it must not cost the whole docket."""
    path = build_store(tmp_path)
    con = db.connect(path)
    case = con.execute("SELECT docket_id FROM docket WHERE raw_docket = 'FD_36873'").fetchone()[0]

    full = sheet.docket_sheet(con, case)
    assert full is not None and full.entries
    for listed in full.entries:
        got = sheet.one_entry(con, case, listed.kind, listed.record_id)
        assert got is not None, f"{listed.kind} {listed.record_id} is on the sheet but not found"
        context, entry = got
        # the same entry, field for field — including the family fold's `also_in`
        assert entry == listed
        assert (context.raw_docket, context.title) == (full.raw_docket, full.title)

    # and it does not assemble the docket to find one row. `_attachments` runs once per
    # entry the sheet builds, so counting it counts the work: the whole sheet against one.
    calls: list[str] = []
    real = sheet._attachments

    def counted(*a, **k):
        calls.append(a[1])
        return real(*a, **k)

    sheet._attachments = counted
    try:
        pick = full.entries[0]
        calls.clear()
        sheet.one_entry(con, case, pick.kind, pick.record_id)
        targeted = len(calls)
        calls.clear()
        sheet.docket_sheet(con, case)
        whole = len(calls)
    finally:
        sheet._attachments = real
    con.close()
    # the cost is the number of COPIES of that one record across the family — one, unless
    # it was entered in a docket AND its sub-docket, which is the fold `also_in` records
    assert targeted == 1 + len(pick.also_in)
    assert whole > targeted  # the sheet builds every entry; the lookup builds one record's

    # unknown records are a miss, not a crash, and the kind is checked
    con = db.connect(path)
    assert sheet.one_entry(con, case, "comment", "EI-000000") is None
    assert sheet.one_entry(con, case, "filing", "no-such-id") is None
    with pytest.raises(ValueError):
        sheet.one_entry(con, case, "nonsense", "1")
    con.close()


def test_one_entry_agrees_about_parties_too(tmp_path):
    """The equivalence test above cannot see this: `build_store` seeds no party spans, so
    `parties` is `[]` on both sides and agrees vacuously. This one uses a store that has
    resolved parties.

    It is the case that caught a real defect. `components_of_filings` filters
    `WHERE f.docket_id IN (...)`, and `docket_sheet` passed it `filing_pk` values — right by
    accident, because the map is keyed by filing_pk and a store's pk range usually covers
    its docket ids. `one_entry` passing ONE pk matched no docket and answered `[]`, so the
    record page would have shown a filing as filed for nobody while the sheet listing it
    named the party."""
    from tests.test_registers import _store

    _, con = _store(tmp_path)
    seen = 0
    for docket_id in [r[0] for r in con.execute("SELECT docket_id FROM docket")]:
        s = sheet.docket_sheet(con, docket_id)
        if s is None:
            continue
        for listed in s.entries:
            got = sheet.one_entry(con, docket_id, listed.kind, listed.record_id)
            assert got is not None
            assert got[1] == listed, f"{listed.record_id}: {got[1].parties} != {listed.parties}"
            seen += 1 if listed.parties else 0
    con.close()
    assert seen, "the fixture resolved no parties — this test would prove nothing"


def test_neighbours_agree_with_the_sheet_for_every_entry(con, tmp_path):
    """THE DRIFT GUARD for the record page's targeted read. `entry_and_neighbours` orders the
    family from three small queries so the rail stops building a whole sheet to name one
    record's neighbours; if its order or its family-fold ever diverged from `docket_sheet`'s,
    "next" would point at something the sheet does not list — silently, and only on the
    dockets where the two disagree. `sort_key` is shared for that reason; this asserts the
    sharing works.

    Measured on a production copy 2026-09-03: 232.6 ms to 21.5 ms on FD 35087 (12,633
    entries), 10.8x, with the same neighbours at every sampled position."""
    build(con, tmp_path)
    parent = con.execute("SELECT docket_id FROM docket WHERE raw_docket='FD_36873'").fetchone()[0]
    s = sheet.docket_sheet(con, parent)
    assert s is not None and len(s.entries) == 4

    for i, entry in enumerate(s.entries):
        got = sheet.entry_and_neighbours(con, parent, entry.kind, entry.record_id)
        assert got is not None, f"{entry.kind} {entry.record_id} is on the sheet and unfindable"
        here, prev, nxt = got.entry, got.prev, got.next
        assert (here.kind, here.record_id) == (entry.kind, entry.record_id)
        want_prev = s.entries[i - 1] if i > 0 else None
        want_next = s.entries[i + 1] if i + 1 < len(s.entries) else None
        for got_side, want in ((prev, want_prev), (nxt, want_next)):
            if want is None:
                assert got_side is None
            else:
                assert got_side is not None
                assert (got_side.kind, got_side.record_id) == (want.kind, want.record_id)
                # the neighbour is built by the same three builders, so its links work
                assert got_side.docket_raw == want.docket_raw
                assert [a.url for a in got_side.attachments] == [a.url for a in want.attachments]

    first = sheet.entry_and_neighbours(con, parent, s.entries[0].kind, s.entries[0].record_id)
    last = sheet.entry_and_neighbours(con, parent, s.entries[-1].kind, s.entries[-1].record_id)
    assert first is not None and first.prev is None
    assert last is not None and last.next is None


def test_neighbours_reach_the_sub_dockets_entry_from_the_parent(con, tmp_path):
    """The sheet merges the family, so the entry after the parent's last filing is the
    SUB-DOCKET's — and the rail's "next" has to cross that boundary exactly as the sheet
    does, or the last record of a parent looks like the end of the proceeding."""
    build(con, tmp_path)
    parent = con.execute("SELECT docket_id FROM docket WHERE raw_docket='FD_36873'").fetchone()[0]
    got = sheet.entry_and_neighbours(con, parent, "filing", "311977")
    assert got is not None
    nxt = got.next
    assert nxt is not None
    assert (nxt.kind, nxt.record_id, nxt.docket_raw) == ("filing", "311900", "FD_36873_1")


def test_neighbours_of_an_unknown_record_are_nothing(con, tmp_path):
    build(con, tmp_path)
    parent = con.execute("SELECT docket_id FROM docket WHERE raw_docket='FD_36873'").fetchone()[0]
    assert sheet.entry_and_neighbours(con, parent, "filing", "no-such-id") is None


def test_neighbours_name_the_entrys_own_parties_and_no_others(tmp_path):
    """The rail links the components THIS filing was filed for. `party_names` is keyed by
    representative and is meant to cover the entry's own `parties` and stop there — the
    sheet's Parties block, which names the whole family's, cost 65.4 ms of a 92.8 ms sheet
    on FD 36873 and is what this read exists to avoid."""
    from tests.test_registers import _store

    _, con = _store(tmp_path)
    named = 0
    for docket_id in [r[0] for r in con.execute("SELECT docket_id FROM docket")]:
        s = sheet.docket_sheet(con, docket_id)
        if s is None:
            continue
        for listed in s.entries:
            view = sheet.entry_and_neighbours(con, docket_id, listed.kind, listed.record_id)
            assert view is not None
            assert set(view.party_names) == set(view.entry.parties), listed.record_id
            named += len(view.party_names)
    con.close()
    assert named, "the fixture resolved no parties — this test would prove nothing"
