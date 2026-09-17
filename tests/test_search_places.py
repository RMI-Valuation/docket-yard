"""Search built out (docs/search-v2.md), the index half: filings and every decision are rows
found once, and each is PLACED in every proceeding it was entered in, by the sheet rule, with
that entry's own printed date and type; a document reaches its owners' rows."""

from docketyard.store import db, search
from tests.test_web import build_store


def _places(con, path):
    (doc_id,) = con.execute("SELECT doc_id FROM search_doc WHERE path = ?", (path,)).fetchone()
    return sorted(
        con.execute(
            "SELECT d.raw_docket, p.prefix, p.date_kind, p.date, p.type_kind, p.type"
            " FROM search_place p JOIN docket d ON d.docket_id = p.group_docket_id"
            " WHERE p.doc_id = ?",
            (doc_id,),
        ).fetchall()
    )


def _event(con):
    return con.execute("SELECT MIN(observed_in_event) FROM filing").fetchone()[0]


def test_a_filing_is_found_by_its_type_and_filed_for_and_placed_where_it_was_entered(tmp_path):
    con = db.connect(build_store(tmp_path))
    counts = search.rebuild(con)
    # two filing ids, three filing rows: 311981 was entered in FD 36873 and its sub-docket
    assert counts["filing"] == 2 and counts["decision"] == 1
    hits = search.search(con, "NRDC", kinds=("filing",))
    assert [h.path for h in hits] == ["/filing/311981"] and hits[0].title == "Filing 311981"
    # the kinds a caller did not ask for stay out: /suggest and MCP keep today's
    assert all(h.kind != "filing" for h in search.search(con, "NRDC"))
    assert all(h.kind != "filing" for h in search.search(con, "motion"))
    # the sub-docket has a caption of its own, so it is its own proceeding: two placements,
    # each with the entry's own date and type
    assert _places(con, "/filing/311981") == [
        ("FD_36873", "FD", "filed", "2026-08-25", "filing", "Motion"),
        ("FD_36873_1", "FD", "filed", "2026-08-25", "filing", "Motion"),
    ]
    # a docket places itself; the decision entered in both is placed in both
    assert _places(con, "/d/FD-36873") == [("FD_36873", "FD", None, None, None, None)]
    assert [p[0] for p in _places(con, "/decision/53210")] == ["FD_36873", "FD_36873_1"]
    con.close()


def test_a_record_in_two_families_is_placed_in_both_and_a_folded_sub_docket_in_its_family(
    tmp_path,
):
    """573 filings sit in more than one family on the 2026-09-17 restore; folded to one, a
    filter for the other family's prefix would miss them (schema-critic, 2026-09-17)."""
    con = db.connect(build_store(tmp_path))
    ev = _event(con)
    con.executescript(
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence) VALUES (10, 'NOR_42000',"
        " 'NOR', 42000);"
        # a sub-docket with no caption of its own is its family's proceeding
        "INSERT INTO docket (docket_id, raw_docket, prefix, sequence, sub_sequence,"
        " parent_docket_id) VALUES (11, 'FD_36873_2', 'FD', 36873, 2, 1);"
    )
    con.execute(
        "INSERT INTO filing (docket_id, stb_filing_id, filing_type, filed_date, filed_for_raw,"
        " observed_in_event) VALUES (10, '311981', 'Motion', '2026-08-25', 'NRDC', ?)",
        (ev,),
    )
    con.execute(
        "INSERT INTO filing (docket_id, stb_filing_id, filing_type, filed_date, filed_for_raw,"
        " observed_in_event) VALUES (11, '311900', 'Motion', '2026-08-24', 'PPU', ?)",
        (ev,),
    )
    con.commit()
    search.rebuild(con, force=True)
    assert {p[1] for p in _places(con, "/filing/311981")} == {"FD", "NOR"}
    assert [p[0] for p in _places(con, "/filing/311981")] == [
        "FD_36873",
        "FD_36873_1",
        "NOR_42000",
    ]
    # 311900: its own sub-docket, and FD 36873 through the uncaptioned Sub-No. 2 — once
    assert [p[0] for p in _places(con, "/filing/311900")] == ["FD_36873", "FD_36873_1"]
    # still one row found: the body names every docket, so any number finds it
    assert [h.path for h in search.search(con, "42000", kinds=("filing",))] == ["/filing/311981"]
    con.close()


def test_a_first_fetch_moves_the_signature_and_maps_the_document_to_its_owner(tmp_path):
    """A first fetch appends no event, so the signature did not see it and a new document's
    pages would have had no owner until something unrelated moved (schema-critic)."""
    con = db.connect(build_store(tmp_path))
    search.rebuild(con)
    before = search.signature(con)
    assert search.rebuild(con) == {"unchanged": True, "build": 1}
    sha = "ab" * 32
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 10, 'pdf', '2026-09-17T00:00:00+00:00')",
        (sha,),
    )
    con.execute(
        "UPDATE filing_attachment SET document_sha256 = ? WHERE filing_pk IN"
        " (SELECT filing_pk FROM filing WHERE stb_filing_id = '311981')",
        (sha,),
    )
    con.commit()
    assert search.signature(con) != before
    counts = search.rebuild(con)
    # both copies of 311981 carry the file, and both reach the one row
    assert counts["documents"] == 1
    (owner,) = con.execute(
        "SELECT s.path FROM search_document m JOIN search_doc s USING (doc_id)"
        " WHERE m.document_sha256 = ?",
        (sha,),
    ).fetchone()
    assert owner == "/filing/311981"
    con.close()


def test_a_decision_is_found_by_its_type_as_the_board_prints_it(tmp_path):
    """3,880 decision rows print no summary; the type in the body is what finds them."""
    con = db.connect(build_store(tmp_path))
    con.execute("UPDATE decision_record SET decision_type = 'Notice of Exemption'")
    con.commit()
    search.rebuild(con, force=True)
    assert [h.path for h in search.search(con, "notice of exemption")] == ["/decision/53210"]
    con.close()
