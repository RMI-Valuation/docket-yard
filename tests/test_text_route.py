"""`docketyard text route` and migration 0032 — the router's verdict as its own page-grain
assertion (ADR 0021 addendum, 2026-09-15): the table's invariants, then the pass.
"""

import argparse
import json
import sqlite3
from pathlib import Path

import pytest

from docketyard import cli
from docketyard.store import db, dump
from docketyard.text import route
from docketyard.text.fields import Unreadable
from tests.test_text_load import SHA_A, SHA_B, STAMP, _store

ROUTED = "2026-09-05T12:00:00+00:00"  # the router's clock
LATER = "2026-09-20T12:00:00+00:00"  # a later router run
LATEST = "2026-09-22T12:00:00+00:00"  # a later one still
NOW = "2026-09-15T00:00:00+00:00"  # the store's clock at a load
AFTER = "2026-09-25T00:00:00+00:00"  # the store's clock at a later load
ROUTER = "pp-doclayoutv3+regions"


def _paginate(con, sha, count):
    con.execute(
        "INSERT INTO document_pagination (document_sha256, outcome, page_count, had_text_layer,"
        " method, method_version, asserted_at, confidence, confidence_state)"
        " VALUES (?, 'paginated', ?, 0, 'pymupdf', '1.24.10', ?, 0, 'unmeasured')",
        (sha, count, STAMP),
    )
    con.commit()


def _record(sha, pages, *, version="provisional-1", routed_at=ROUTED, dpi=150):
    """A route file as `ocr_wave.py run-paddle` writes it."""
    return {
        "document_sha256": sha,
        "method": ROUTER,
        "method_version": version,
        "layout_model": "PP-DocLayoutV3",
        "region_cut": 13,
        "dpi": dpi,
        "routed_at": routed_at,
        "pages": {
            str(n): page if isinstance(page, dict) else {"class": page, "regions": 3, "labels": []}
            for n, page in pages.items()
        },
    }


def _route(con, record, now=NOW):
    return route.route_document(con, route.from_record(record, route.classes(con)), now=now)


def _write(root, record, name=None):
    sha = name or record["document_sha256"]
    (root / sha[:2]).mkdir(parents=True, exist_ok=True)
    (root / sha[:2] / f"{sha}.json").write_text(json.dumps(record), encoding="utf-8")


def _live(con, sha=SHA_A):
    return con.execute(
        "SELECT page_no, route_class, method_version, render_profile, region_count, routed_at,"
        " asserted_at FROM page_route WHERE document_sha256 = ? AND superseded_by IS NULL"
        " ORDER BY page_no",
        (sha,),
    ).fetchall()


def _insert(con, **over):
    row = {
        "document_sha256": SHA_A,
        "page_no": 1,
        "route_class": "tabular",
        "method": ROUTER,
        "method_version": "provisional-1",
        "render_profile": "150",
        "confidence": 0,
        "confidence_state": "unmeasured",
        "routed_at": ROUTED,
        "asserted_at": NOW,
    }
    row.update(over)
    cur = con.execute(
        f"INSERT INTO page_route ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
        list(row.values()),
    )
    return cur.lastrowid


# --- migration 0032: the table ---------------------------------------------------------------


def test_one_live_route_per_page(tmp_path):
    con = _store(tmp_path)
    first = _insert(con)
    with pytest.raises(sqlite3.IntegrityError):
        _insert(con, route_class="clean", method_version="provisional-2")
    _insert(con, page_no=2)  # another page is another verdict
    con.execute(
        "UPDATE page_route SET superseded_by = ?, superseded_at = ? WHERE route_id = ?",
        (first, AFTER, first),
    )
    second = _insert(con, route_class="clean", method_version="provisional-2")
    con.execute("UPDATE page_route SET superseded_by = ? WHERE route_id = ?", (second, first))
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_the_supersession_pair_travels_together(tmp_path):
    con = _store(tmp_path)
    rid = _insert(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE page_route SET superseded_by = ? WHERE route_id = ?", (rid, rid))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE page_route SET superseded_at = ? WHERE route_id = ?", (AFTER, rid))


def test_both_clocks_and_the_render_are_required(tmp_path):
    con = _store(tmp_path)
    for column in ("routed_at", "asserted_at", "render_profile"):
        with pytest.raises(sqlite3.IntegrityError):
            _insert(con, **{column: None})
        with pytest.raises(sqlite3.IntegrityError):
            _insert(con, **{column: ""})


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("route_class", "clean"),
        ("method", "another-router"),
        ("method_version", "provisional-2"),
        ("render_profile", "200"),
        ("region_count", 9),
        ("note", "x"),
        ("routed_at", LATER),
        ("asserted_at", AFTER),
        ("page_no", 2),
    ],
)
def test_a_verdict_is_superseded_never_edited(tmp_path, column, value):
    con = _store(tmp_path)
    rid = _insert(con)
    with pytest.raises(sqlite3.IntegrityError, match="superseded, never edited"):
        con.execute(f"UPDATE page_route SET {column} = ? WHERE route_id = ?", (value, rid))


def test_a_retirement_is_forward_only(tmp_path):
    con = _store(tmp_path)
    old = _insert(con)
    con.execute(  # step one of the idiom: retire at itself, both columns in one statement
        "UPDATE page_route SET superseded_by = ?, superseded_at = ? WHERE route_id = ?",
        (old, AFTER, old),
    )
    new = _insert(con, route_class="clean", method_version="provisional-2")
    con.execute("UPDATE page_route SET superseded_by = ? WHERE route_id = ?", (new, old))
    later = _insert(con, page_no=2)
    for sql, args in (
        ("UPDATE page_route SET superseded_by = ? WHERE route_id = ?", (later, old)),  # re-point
        ("UPDATE page_route SET superseded_by = NULL WHERE route_id = ?", (old,)),  # un-retire
    ):
        with pytest.raises(sqlite3.IntegrityError, match="un-retired or re-pointed"):
            con.execute(sql, args)
    for at in (ROUTED, None):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute("UPDATE page_route SET superseded_at = ? WHERE route_id = ?", (at, old))
    assert con.execute(
        "SELECT superseded_by, superseded_at FROM page_route WHERE route_id = ?", (old,)
    ).fetchone() == (new, AFTER)


def test_a_route_class_must_be_in_the_vocabulary_and_measured_is_unreachable(tmp_path):
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _insert(con, route_class="spreadsheet")
    with pytest.raises(sqlite3.IntegrityError):
        _insert(con, confidence_state="measured", score_row_id=1, measured_target="page_route")
    with pytest.raises(sqlite3.IntegrityError):
        _insert(con, confidence_state="human")  # "human" is bound to the method too


def test_a_model_pass_may_not_supersede_a_human_route(tmp_path):
    con = _store(tmp_path)
    human = _insert(con, method="human", confidence_state="human", confidence=1)
    con.execute(
        "UPDATE page_route SET superseded_by = ?, superseded_at = ? WHERE route_id = ?",
        (human, AFTER, human),
    )
    model = _insert(con, route_class="clean")
    with pytest.raises(sqlite3.IntegrityError, match="human page route"):
        con.execute("UPDATE page_route SET superseded_by = ? WHERE route_id = ?", (model, human))


def test_the_route_is_held_from_the_snapshot_and_leaves_no_dangling_key(tmp_path):
    import re

    con = _store(tmp_path)
    _insert(con)
    con.commit()
    con.close()
    assert "page_route" in dump.HELD_TABLES
    # children before parents: the verdict sits above its class vocabulary
    assert dump.HELD_TABLES.index("page_route") < dump.HELD_TABLES.index("route_class_vocab")
    manifest = dump.dump(Path(tmp_path / "s.sqlite"), out_dir=tmp_path / "public")
    ddl = (tmp_path / "public" / "schema.sql").read_text(encoding="utf-8")
    assert "page_route" not in ddl and "page_route" in manifest.held_tables
    ddl = ddl.replace('"', "")
    present = set(re.findall(r"CREATE (?:VIRTUAL )?TABLE (\w+)", ddl))
    assert not set(re.findall(r"REFERENCES (\w+)", ddl)) - present


# --- the pass --------------------------------------------------------------------------------


def test_a_route_file_loads_one_row_per_page_on_two_clocks(tmp_path):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 3)
    assert _route(con, _record(SHA_A, {1: "clean", 2: "tabular", 3: "graphic"})) == "loaded"
    # asserted_at is the store's clock at the load; routed_at the router's, from the file
    assert _live(con) == [
        (1, "clean", "provisional-1", "150", 3, ROUTED, NOW),
        (2, "tabular", "provisional-1", "150", 3, ROUTED, NOW),
        (3, "graphic", "provisional-1", "150", 3, ROUTED, NOW),
    ]
    state = con.execute("SELECT DISTINCT confidence, confidence_state FROM page_route").fetchall()
    assert state == [(0, "unmeasured")]
    # the reading's own route_class is never back-filled from here (ADR 0021 addendum, 2)
    assert con.execute("SELECT COUNT(*) FROM document_text").fetchone() == (0,)


def test_the_same_verdict_again_writes_nothing_and_another_render_is_another_verdict(tmp_path):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 2)
    assert _route(con, _record(SHA_A, {1: "tabular", 2: "clean"})) == "loaded"
    again = _record(SHA_A, {1: "tabular", 2: "clean"}, routed_at=LATER)
    again["pages"]["1"]["regions"] = 9  # a region count is not the verdict
    assert _route(con, again, now=AFTER) == "unchanged"
    assert con.execute("SELECT COUNT(*) FROM page_route").fetchone() == (2,)
    rendered = _record(SHA_A, {1: "tabular", 2: "clean"}, routed_at=LATER, dpi=200)
    assert _route(con, rendered, now=AFTER) == "superseded"
    assert [r[3] for r in _live(con)] == ["200", "200"]


def test_a_new_router_version_supersedes_on_the_stores_clock(tmp_path):
    """The store's clock and the router's are different values here on purpose: a pass that
    wrote `routed_at` into `asserted_at` or `superseded_at` fails this test."""
    con = _store(tmp_path)
    _paginate(con, SHA_A, 2)
    _route(con, _record(SHA_A, {1: "tabular", 2: "clean"}), now=NOW)
    old = dict(con.execute("SELECT page_no, route_id FROM page_route").fetchall())
    newer = _record(SHA_A, {1: "tabular", 2: "degraded"}, version="confirmed-1", routed_at=LATER)
    assert _route(con, newer, now=AFTER) == "superseded"
    assert _live(con) == [
        (1, "tabular", "confirmed-1", "150", 3, LATER, AFTER),
        (2, "degraded", "confirmed-1", "150", 3, LATER, AFTER),
    ]
    for page_no, rid in old.items():
        by, at, asserted = con.execute(
            "SELECT superseded_by, superseded_at, asserted_at FROM page_route WHERE route_id = ?",
            (rid,),
        ).fetchone()
        successor = con.execute(
            "SELECT page_no FROM page_route WHERE route_id = ? AND superseded_by IS NULL", (by,)
        ).fetchone()
        assert by != rid and successor == (page_no,)
        assert at == AFTER and asserted == NOW  # left the record when the next one entered it
    # and a different class at the SAME version supersedes too — from a file routed LATER still:
    # at LATER itself it would be stale, an equal instant being refused (the first loaded wins)
    same = _record(SHA_A, {1: "graphic", 2: "degraded"}, version="confirmed-1", routed_at=LATEST)
    assert _route(con, same, now=AFTER) == "superseded"
    assert [r[1] for r in _live(con)] == ["graphic", "degraded"]


def test_an_older_file_with_a_differing_verdict_is_refused_whatever_its_version(tmp_path):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 2)
    _route(con, _record(SHA_A, {1: "clean", 2: "clean"}, version="confirmed-1", routed_at=LATER))
    before = _live(con)
    older_other_version = _record(SHA_A, {1: "tabular", 2: "clean"}, routed_at=ROUTED)
    assert _route(con, older_other_version, now=AFTER) == "stale"
    older_same_version = _record(
        SHA_A, {1: "tabular", 2: "clean"}, version="confirmed-1", routed_at=ROUTED
    )
    assert _route(con, older_same_version, now=AFTER) == "stale"
    assert _live(con) == before
    assert con.execute("SELECT COUNT(*) FROM page_route").fetchone() == (2,)
    # an older file that AGREES is simply unchanged
    agreeing = _record(SHA_A, {1: "clean", 2: "clean"}, version="confirmed-1", routed_at=ROUTED)
    assert _route(con, agreeing, now=AFTER) == "unchanged"


def test_an_equal_time_file_with_a_differing_verdict_is_stale_and_the_first_wins(tmp_path):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 1)
    assert _route(con, _record(SHA_A, {1: "clean"}, routed_at=ROUTED)) == "loaded"
    same_instant = _record(SHA_A, {1: "tabular"}, routed_at="2026-09-05T14:00:00+02:00")
    assert _route(con, same_instant, now=AFTER) == "stale"
    assert [r[1] for r in _live(con)] == ["clean"]


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("2026-09-05T12:00:00Z", "2026-09-05T12:00:00+00:00"),
        ("2026-09-05T17:00:00+05:00", "2026-09-05T12:00:00+00:00"),
        ("2026-09-05T07:00:00-05:00", "2026-09-05T12:00:00+00:00"),
        ("2026-09-05T12:00:00.734512+00:00", "2026-09-05T12:00:00+00:00"),
    ],
)
def test_routed_at_is_stored_in_one_utc_shape(tmp_path, given, stored):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 1)
    assert _route(con, _record(SHA_A, {1: "tabular"}, routed_at=given)) == "loaded"
    assert _live(con)[0][5] == stored


@pytest.mark.parametrize(
    "given",
    [
        "2026-09-05T12:00:00",
        "2026-09-05",  # a date alone is not an instant
        "0001-01-01T00:00:00+01:00",  # parses, then overflows in UTC: refused, not raised out
        "yesterday",
        "",
        20260905,
    ],
)
def test_routed_at_without_a_zone_or_a_shape_is_unreadable(tmp_path, given):
    con = _store(tmp_path)
    with pytest.raises(Unreadable, match="routed_at"):
        route.from_record(_record(SHA_A, {1: "tabular"}, routed_at=given), route.classes(con))


def test_the_store_refuses_a_routed_at_in_any_other_shape(tmp_path):
    con = _store(tmp_path)
    for bad in ("2026-09-05T12:00:00", "2026-09-05T12:00:00Z", "2026-09-05T17:00:00+05:00"):
        with pytest.raises(sqlite3.IntegrityError):
            _insert(con, routed_at=bad)


def test_a_page_above_the_live_count_refuses_the_whole_document(tmp_path):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 2)
    _paginate(con, SHA_B, 1)
    root = tmp_path / "route"
    _write(root, _record(SHA_A, {1: "tabular", 2: "clean", 3: "clean"}))
    _write(root, _record(SHA_B, {1: "tabular"}))
    lines = []
    totals = route.run(con, root, log=lines.append)
    assert totals["failed"] == 1 and totals["loaded"] == 1
    assert _live(con, SHA_A) == []  # nothing of the refused document, not even page 1
    assert any("above the document's live page count 2" in line for line in lines)
    # and a document with no page count to check against is refused the same way
    con.execute("DELETE FROM document_pagination WHERE document_sha256 = ?", (SHA_B,))
    with pytest.raises(Unreadable, match="no live paginated page count"):
        _route(con, _record(SHA_B, {1: "clean"}, version="confirmed-1", routed_at=LATER))


def test_an_errored_page_above_the_live_count_refuses_the_document_too(tmp_path):
    """A page the router failed on still NAMES a page: above the live count it is the same
    mismatch — a route for bytes that are not the bytes paginated — and it writes no row to be
    caught by later (Copilot, PR #36)."""
    con = _store(tmp_path)
    _paginate(con, SHA_A, 2)
    error = {"class": "unrouted", "regions": 0, "labels": [], "error": "RuntimeError: render"}
    with pytest.raises(Unreadable, match="page 7 is above the document's live page count 2"):
        _route(con, _record(SHA_A, {1: "tabular", 7: error}))
    assert con.execute("SELECT COUNT(*) FROM page_route").fetchone() == (0,)


def test_a_page_the_router_failed_on_writes_no_verdict_and_is_counted(tmp_path):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 3)
    error = {"class": "unrouted", "regions": 0, "labels": [], "error": "RuntimeError: render"}
    root = tmp_path / "route"
    _write(root, _record(SHA_A, {1: "tabular", 2: error, 3: dict(error)}))
    totals = route.run(con, root, log=lambda _: None)
    assert totals["loaded"] == 1 and totals["route_error_pages"] == 2
    assert [r[0] for r in _live(con)] == [1]
    assert con.execute("SELECT COUNT(*) FROM page_route WHERE note IS NOT NULL").fetchone() == (0,)


def test_a_file_that_classified_nothing_is_not_a_success(tmp_path):
    """Every page errored, or none was named: nothing attached, and the exit status says so
    rather than reading the empty plan as `unchanged` (Copilot, PR #36)."""
    con = _store(tmp_path)
    _paginate(con, SHA_A, 2)
    error = {"class": "unrouted", "regions": 0, "labels": [], "error": "RuntimeError: render"}
    assert _route(con, _record(SHA_A, {})) == "no_verdicts"
    root = tmp_path / "route"
    _write(root, _record(SHA_A, {1: error, 2: dict(error)}))
    totals = route.run(con, root, log=lambda _: None)
    assert totals["no_verdicts"] == 1 and totals["route_error_pages"] == 2
    assert con.execute("SELECT COUNT(*) FROM page_route").fetchone() == (0,)
    assert "no_verdicts" not in route.ATTACHED
    con.close()
    ns = argparse.Namespace(db=str(tmp_path / "s.sqlite"), what="route", root=str(root))
    assert cli._text(ns) == 1


def test_a_file_that_omits_a_live_page_loads_the_rest_and_says_so(tmp_path):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 3)
    assert _route(con, _record(SHA_A, {1: "clean", 2: "clean", 3: "clean"})) == "loaded"
    partial = _record(SHA_A, {1: "tabular"}, version="confirmed-1", routed_at=LATER)
    assert _route(con, partial, now=AFTER) == "omits_live_pages"
    # what it named is loaded; what it did not name stays live, retired by nothing
    assert [(r[0], r[1]) for r in _live(con)] == [(1, "tabular"), (2, "clean"), (3, "clean")]
    assert "omits_live_pages" in route.ATTACHED  # rows landed: it met its document


def test_a_person_verdict_is_held_against_the_pass(tmp_path):
    """A person's row names no router run, so its `routed_at` may be NULL; the pass holds it
    before any comparison, so staleness never reads the NULL."""
    con = _store(tmp_path)
    _paginate(con, SHA_A, 1)
    human = dict(method="human", confidence_state="human", confidence=1, routed_at=None)
    rid = _insert(con, route_class="clean", **human)
    assert _route(con, _record(SHA_A, {1: "tabular"})) == "human_held"
    assert [r[1] for r in _live(con)] == ["clean"]
    # the trigger's IS NOT tolerates the NULL: an unrelated write passes, an edit of it does not
    con.execute("UPDATE page_route SET confidence = 1 WHERE route_id = ?", (rid,))
    with pytest.raises(sqlite3.IntegrityError, match="superseded, never edited"):
        con.execute("UPDATE page_route SET routed_at = ? WHERE route_id = ?", (ROUTED, rid))
    # and only a person's row may leave it out; a person's row may not hold a malformed one
    with pytest.raises(sqlite3.IntegrityError):
        _insert(con, page_no=2, routed_at=None)
    for bad in ("yesterday", "2026-09-05T12:00:00Z", ""):
        with pytest.raises(sqlite3.IntegrityError):
            _insert(con, page_no=2, route_class="clean", **{**human, "routed_at": bad})
    _insert(con, page_no=2, route_class="clean", **human)  # NULL is still a person's to leave


@pytest.mark.parametrize("method", ["human", ""])
def test_a_route_file_must_name_a_machine_router(tmp_path, method):
    con = _store(tmp_path)
    record = {**_record(SHA_A, {1: "tabular"}), "method": method}
    with pytest.raises(Unreadable, match="method"):
        route.from_record(record, route.classes(con))


def test_an_unknown_document_is_counted_and_skipped_and_the_exit_status_says_so(tmp_path):
    con = _store(tmp_path)
    _paginate(con, SHA_A, 1)
    root = tmp_path / "route"
    stranger = "c" * 64
    _write(root, _record(stranger, {1: "tabular"}))
    _write(root, _record(SHA_A, {1: "spreadsheet"}))  # not in the vocabulary
    totals = route.run(con, root, log=lambda _: None)
    assert totals["unknown_document"] == 1 and totals["unreadable"] == 1
    assert con.execute("SELECT COUNT(*) FROM page_route").fetchone() == (0,)
    con.close()
    ns = argparse.Namespace(db=str(tmp_path / "s.sqlite"), what="route", root=str(root))
    assert cli._text(ns) == 1  # nothing attached is not a success
    _write(root, _record(SHA_A, {1: "tabular"}))
    assert cli._text(ns) == 0  # the stranger is skipped; the store took what it holds
    _write(root, _record(SHA_A, {1: "tabular", 2: "clean"}))  # above the count of 1
    assert cli._text(ns) == 1
    ns.root = str(tmp_path / "nowhere")
    assert cli._text(ns) == 1


def test_a_route_file_without_a_render_is_unreadable(tmp_path):
    con = _store(tmp_path)
    for dpi in (None, 0, "150", True):
        with pytest.raises(Unreadable, match="dpi"):
            route.from_record(_record(SHA_A, {1: "tabular"}, dpi=dpi), route.classes(con))


def test_route_is_wired_under_text(tmp_path, capsys):
    db_path = str(tmp_path / "s.sqlite")
    assert cli.main(["--db", db_path, "text", "route", str(tmp_path / "nowhere")]) == 1
    assert "is not a directory of route files" in capsys.readouterr().out


def test_db_registers_0032():
    assert (32, "0032_page_route.sql") in db.MIGRATIONS
