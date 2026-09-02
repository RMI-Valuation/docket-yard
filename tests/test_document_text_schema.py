"""Migration 0018 — the record's own text (ADR 0021, ADR 0022), and the checks that hold it.

Every test here pins something a review round found and the schema now enforces, so that
loosening the schema breaks a test rather than a published page. The names say which.
"""

import sqlite3
from pathlib import Path

import pytest

from docketyard.store import db, dump

STAMP = "2026-09-02T00:00:00+00:00"
SHA = "d" * 64


def _store(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', ?)",
        (SHA, STAMP),
    )
    return con


def _reading(con, **over):
    row = {
        "document_sha256": SHA,
        "page_no": 1,
        "method": "dots.mocr",
        "method_version": "1.5",
        "render_profile": "150",
        "reading_channel": "ocr",
        "reading_role": "primary",
        "route_class": "degraded",
        "route_method": "pp-doclayoutv3",
        "route_method_version": "3.0",
        "text": "abandonment in Perry County",
        "text_sha256": "a" * 64,
        "confidence": 0,
        "confidence_state": "unmeasured",
        "asserted_at": STAMP,
    }
    row.update(over)
    cols = ", ".join(row)
    con.execute(
        f"INSERT INTO document_text ({cols}) VALUES ({', '.join('?' * len(row))})",
        list(row.values()),
    )
    return con.execute("SELECT last_insert_rowid()").fetchone()[0]


def _human(con, **over):
    """All four encodings of "human" are bound to each other, so a human row sets all four."""
    row = {
        "method": "human",
        "method_version": "unversioned",
        "render_profile": "human",
        "reading_channel": "human",
        "reading_role": "human",
        "confidence_state": "human",
        "route_class": None,
        "route_method": None,
        "route_method_version": None,
    }
    row.update(over)
    return _reading(con, **row)


# --- ADR 0021 D5: empty is a reading, failure is a count -----------------------------------


def test_a_page_read_as_blank_is_a_row_and_not_an_absence(tmp_path):
    """The benchmark's runner treated empty output as an error and dropped the page, which
    penalised the safest behaviour — Tesseract lost the two graphic pages it correctly
    emitted nothing for. The store must not repeat it."""
    con = _store(tmp_path)
    _reading(con, text="", text_sha256="e" * 64)
    assert con.execute("SELECT text FROM document_text").fetchone()[0] == ""


def test_ocr_run_appends_where_extraction_run_replaces(tmp_path):
    """`ran_at` is in the key. `extraction_run` replaces on a re-run, which is why its own
    header forbids deriving a published coverage number from it; the coverage page reads
    this one, so a retry must not erase the attempt it followed."""
    con = _store(tmp_path)
    for ran_at, outcome, failed in (
        ("2026-09-02T01:00:00+00:00", "failed", 4),
        ("2026-09-02T02:00:00+00:00", "read", 0),
    ):
        con.execute(
            "INSERT INTO ocr_run (document_sha256, method, method_version, reading_channel,"
            " render_profile, outcome, pages_read, pages_failed, ran_at)"
            " VALUES (?, 'dots.mocr', '1.5', 'ocr', '300', ?, 9, ?, ?)",
            (SHA, outcome, failed, ran_at),
        )
    rows = con.execute("SELECT outcome, pages_failed FROM ocr_run ORDER BY ran_at").fetchall()
    assert rows == [("failed", 4), ("read", 0)], "the failed attempt must survive the retry"


# --- ADR 0021 D9: the display is single-valued by construction -----------------------------


def test_two_live_primaries_on_one_page_are_refused(tmp_path):
    """The natural key carries method_version and render_profile PRECISELY so a re-run
    inserts rather than collides — so without this index the first re-run leaves two live
    primaries and the display rule has no answer. An earlier draft of ADR 0021 missed it."""
    con = _store(tmp_path)
    _reading(con)
    with pytest.raises(sqlite3.IntegrityError):
        _reading(con, method_version="1.6")  # a re-run at a new version, not superseding


def test_a_re_run_may_take_the_page_once_the_outgoing_primary_is_retired(tmp_path):
    """Cross-key supersession: the incoming row has a different natural key from the row it
    displaces, so the writer must retire the outgoing primary explicitly."""
    con = _store(tmp_path)
    old = _reading(con)
    con.execute(
        "UPDATE document_text SET superseded_by = ?, superseded_at = ? WHERE text_id = ?",
        (old, STAMP, old),  # retire at itself first, as 0009's idiom does
    )
    new = _reading(con, method_version="1.6")
    con.execute("UPDATE document_text SET superseded_by = ? WHERE text_id = ?", (new, old))
    live = con.execute("SELECT text_id FROM document_text WHERE superseded_by IS NULL").fetchall()
    assert live == [(new,)]


def test_the_text_layer_and_an_ocr_reading_cannot_both_be_primary(tmp_path):
    """A born-digital page that is also OCR'd would have two primaries by construction."""
    con = _store(tmp_path)
    _reading(
        con,
        reading_channel="text-layer",
        method="pymupdf",
        render_profile="native",
        route_class=None,
        route_method=None,
        route_method_version=None,
    )
    with pytest.raises(sqlite3.IntegrityError):
        _reading(con)


# --- ADR 0021 D1 and D9: "human" is encoded three ways and they are bound ------------------


def test_a_model_row_cannot_claim_the_human_display_role(tmp_path):
    """Unbound, a model row written with reading_role 'human' would win the display and be
    unprotected by the trigger, which fires on confidence_state."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _reading(con, reading_role="human")


def test_a_human_row_keys_are_pinned(tmp_path):
    """`citator.methods.HUMAN_VERSION` is a DATED convention; carried into this key it would
    put two live human rows on one page the day that date changes."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _human(con, method_version="2026-09-01")  # HUMAN_VERSION, which is dated


def test_a_model_pass_may_not_supersede_a_human_reading(tmp_path):
    con = _store(tmp_path)
    human = _human(con)
    model = _reading(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "UPDATE document_text SET superseded_by = ?, superseded_at = ? WHERE text_id = ?",
            (model, STAMP, human),
        )


# --- ADR 0021 D1: the review key must parse back into its columns --------------------------


def test_a_slash_in_a_key_column_is_refused(tmp_path):
    """A HuggingFace-style engine id (`rednote-hilab/dots.ocr`) would render a review key
    that cannot be parsed back to columns and could collide with a different split."""
    con = _store(tmp_path)
    for col in ("method", "method_version", "render_profile"):
        with pytest.raises(sqlite3.IntegrityError):
            _reading(con, **{col: "rednote-hilab/dots.ocr"})


def test_document_text_can_be_named_by_a_review_action(tmp_path):
    """Without the review_target_vocab row, ADR 0021's promise that a human correction has
    an author on the day the table ships is false: review_action foreign-keys to it."""
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO reviewer (email_hash, email_enc, credit_name, granted_at, granted_note)"
        " VALUES ('h', 'e', 'The operator', ?, 'seed')",
        (STAMP,),
    )
    con.execute(
        "INSERT INTO review_action (reviewer_id, queue, target_table, target_keyed,"
        " target_key, target_key_version, method_version, decision, asserted_at)"
        " VALUES (1, 'correction', 'document_text', 'natural', ?, 'verbatim', '1',"
        " 'accepted', ?)",
        (f"{SHA}/1/dots.mocr/1.5/150", STAMP),
    )
    assert con.execute("SELECT count(*) FROM review_action").fetchone()[0] == 1


# --- ADR 0021 D7 / ADR 0017 D3: the assertion gate is shut ---------------------------------


def test_no_reading_can_claim_a_measured_confidence(tmp_path):
    """class_vocab is left empty for this stage on purpose, so a measurement cannot exist to
    point at. The gate is a constraint, not a convention."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO class_measurement (measured_target, class, extraction_method,"
            " extraction_method_version, reading_channel, benchmark_date, score_file,"
            " precision, measured_at) VALUES ('document_text', 'clean', 'dots.mocr', '1.5',"
            " 'ocr', '2026-09-02', 'runs/x.json', 0.9, ?)",
            (STAMP,),
        )


# --- ADR 0021 D4: absence must not mean three things ---------------------------------------


def test_pagination_records_why_a_document_has_no_page_count(tmp_path):
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO document_pagination (document_sha256, outcome, method, method_version,"
        " asserted_at) VALUES (?, 'not-paginable', 'pymupdf', '1.28.2', ?)",
        (SHA, STAMP),
    )
    assert con.execute("SELECT page_count FROM document_pagination").fetchone()[0] is None
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(  # 'paginated' without a count is the ambiguity the outcome removes
            "INSERT INTO document_pagination (document_sha256, outcome, method,"
            " method_version, asserted_at) VALUES (?, 'paginated', 'pymupdf', '1', ?)",
            (SHA, STAMP),
        )


def test_a_re_pagination_supersedes_rather_than_updating(tmp_path):
    """page_count is the DENOMINATOR of the coverage arithmetic, in the one new table the
    snapshot publishes. An UPDATE would move a published number with nothing recording it."""
    con = _store(tmp_path)

    def paginate(count):
        con.execute(
            "INSERT INTO document_pagination (document_sha256, outcome, page_count,"
            " had_text_layer, method, method_version, asserted_at)"
            " VALUES (?, 'paginated', ?, 1, 'pymupdf', '1.28.2', ?)",
            (SHA, count, STAMP),
        )
        return con.execute("SELECT last_insert_rowid()").fetchone()[0]

    first = paginate(12)
    # The live index forbids two live rows, so the order is forced and it is 0009's: retire
    # the outgoing row AT ITSELF, insert the replacement, then repoint. Inserting first
    # fails, because for that instant two rows would be live on one document.
    with pytest.raises(sqlite3.IntegrityError):
        paginate(13)
    con.execute(
        "UPDATE document_pagination SET superseded_by = ?, superseded_at = ?"
        " WHERE pagination_id = ?",
        (first, STAMP, first),
    )
    second = paginate(13)
    con.execute(
        "UPDATE document_pagination SET superseded_by = ? WHERE pagination_id = ?",
        (second, first),
    )
    live = con.execute(
        "SELECT pagination_id, page_count FROM document_pagination WHERE superseded_by IS NULL"
    ).fetchall()
    assert live == [(second, 13)]


# --- ADR 0022 D3: what the public snapshot carries -----------------------------------------


def test_the_text_is_held_and_the_pagination_is_published(tmp_path):
    con = _store(tmp_path)
    con.commit()
    con.close()
    manifest = dump.dump(Path(tmp_path / "s.sqlite"), out_dir=tmp_path / "public")
    ddl = (tmp_path / "public" / "schema.sql").read_text(encoding="utf-8")
    assert "document_pagination" in ddl and "ocr_run" in ddl
    for held in ("document_text", "page_fts", "text_payload"):
        assert held not in ddl, f"{held} must not reach the CC0 snapshot"
    assert manifest.schema_version == db.MIGRATIONS[-1][0]


def test_a_view_over_a_held_table_does_not_survive_into_the_snapshot(tmp_path):
    """`DROP TABLE` silently no-ops on a view, and the allowlist enumerated `type = 'table'`
    — so a held view would have shipped as a CREATE VIEW over a table just dropped, and the
    check that exists to catch exactly that could not see it."""
    con = _store(tmp_path)
    con.commit()
    con.close()
    dump.dump(Path(tmp_path / "s.sqlite"), out_dir=tmp_path / "public")
    ddl = (tmp_path / "public" / "schema.sql").read_text(encoding="utf-8")
    assert "document_text_display" not in ddl
    assert "docket_current" in ddl, "the one public view stays, now by decision not by luck"


# --- ADR 0021 D4 and D8: what an unenforced decision costs ---------------------------------


def test_an_ocr_reading_must_know_the_class_it_was_routed_as(tmp_path):
    """PP-OCRv6 is the routed reader for BOTH the clean and the graphic tier, so `method`
    does not recover the route — and every CER is per tier, so the day the gate opens each
    row must know its class. Re-running the router is not a recovery: it will have changed."""
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _reading(con, route_class=None, route_method=None, route_method_version=None)


def test_a_band_names_the_reading_it_is_a_distance_from(tmp_path):
    """A distance whose second operand is unidentified is an ADR 0007 gap, and the primary it
    was measured against is superseded routinely."""
    con = _store(tmp_path)
    primary = _reading(con)
    with pytest.raises(sqlite3.IntegrityError):  # a distance with no operand
        _reading(
            con,
            method="ppocrv6",
            reading_role="second",
            agreement_distance=0.04,
            agreement_method="normalised-edit-distance",
            agreement_method_version="1",
        )
    _reading(
        con,
        method="ppocrv6",
        reading_role="second",
        agreement_distance=0.04,
        agreement_against=primary,
        agreement_method="normalised-edit-distance",
        agreement_method_version="1",
    )


def test_a_second_reading_sits_beside_a_live_primary(tmp_path):
    """The positive case for the agreement pair: `document_text_one_primary` must not
    accidentally forbid the second reading the confidence signal is computed from."""
    con = _store(tmp_path)
    _reading(con)
    _reading(con, method="ppocrv6", reading_role="second")
    assert (
        con.execute("SELECT count(*) FROM document_text WHERE superseded_by IS NULL").fetchone()[0]
        == 2
    )


def test_a_primary_may_not_carry_a_band(tmp_path):
    con = _store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _reading(
            con,
            agreement_distance=0.04,
            agreement_against=1,
            agreement_method="d",
            agreement_method_version="1",
        )


def test_supersession_columns_travel_together(tmp_path):
    """The CHECK that makes `citator.load._retire` unusable here as shipped: it writes
    `superseded_by` alone."""
    con = _store(tmp_path)
    row = _reading(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE document_text SET superseded_by = ? WHERE text_id = ?", (row, row))


# --- ADR 0021 D9: the display view IS the rule ---------------------------------------------


def test_a_live_human_reading_hides_the_primary_from_the_display(tmp_path):
    con = _store(tmp_path)
    primary = _reading(con)
    assert [r[0] for r in con.execute("SELECT text_id FROM document_text_display")] == [primary]
    human = _human(con, text="abandonment in Ferry County", text_sha256="b" * 64)
    assert [r[0] for r in con.execute("SELECT text_id FROM document_text_display")] == [human]


def test_retiring_the_human_reading_returns_the_primary_to_the_display(tmp_path):
    con = _store(tmp_path)
    primary = _reading(con)
    human = _human(con)
    con.execute(
        "UPDATE document_text SET superseded_by = ?, superseded_at = ? WHERE text_id = ?",
        (human, STAMP, human),
    )
    assert [r[0] for r in con.execute("SELECT text_id FROM document_text_display")] == [primary]


def test_a_second_reading_never_reaches_the_display(tmp_path):
    con = _store(tmp_path)
    _reading(con)
    _reading(con, method="ppocrv6", reading_role="second")
    assert [r[0] for r in con.execute("SELECT reading_role FROM document_text_display")] == [
        "primary"
    ]


# --- the trigger ALLOW path, which only a comment asserted ---------------------------------


def test_a_human_reading_may_be_superseded_by_another_human_reading(tmp_path):
    con = _store(tmp_path)
    first = _human(con)
    con.execute(  # retire at self, per the forced order
        "UPDATE document_text SET superseded_by = ?, superseded_at = ? WHERE text_id = ?",
        (first, STAMP, first),
    )
    second = _human(con, text="corrected again", text_sha256="c" * 64)
    con.execute("UPDATE document_text SET superseded_by = ? WHERE text_id = ?", (second, first))
    assert [r[0] for r in con.execute("SELECT text_id FROM document_text_display")] == [second]


# --- ADR 0022 D3: the snapshot ------------------------------------------------------------


def test_the_published_schema_has_no_dangling_foreign_key(tmp_path):
    """A PUBLIC table referencing a HELD one loads fine as DDL and fails at a third party's
    `foreign_key_check`. No shipped table had ever done it; `ocr_run` nearly became the first
    by foreign-keying `reading_vocab`, which the snapshot drops."""
    import re

    con = _store(tmp_path)
    con.commit()
    con.close()
    dump.dump(Path(tmp_path / "s.sqlite"), out_dir=tmp_path / "public")
    ddl = (tmp_path / "public" / "schema.sql").read_text(encoding="utf-8")
    present = set(re.findall(r"CREATE (?:VIRTUAL )?TABLE (\w+)", ddl))
    assert not set(re.findall(r"REFERENCES (\w+)", ddl)) - present


# --- the migration path production actually takes ------------------------------------------


def test_a_populated_store_migrates_from_17_to_18(tmp_path):
    """Every other test builds from scratch. This one exercises `db.migrate`'s post-script
    `PRAGMA foreign_key_check` over a store that already holds rows."""
    path = tmp_path / "s.sqlite"
    con = db.connect(path, upto=17)
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, 1, 'pdf', ?)",
        (SHA, STAMP),
    )
    con.commit()
    con.close()
    con = db.connect(path)  # the migration production will run
    assert con.execute("PRAGMA user_version").fetchone()[0] == 18
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    _reading(con)


# --- the page index, on whatever SQLite is running -----------------------------------------


def test_the_page_index_matches_snippets_and_rebuilds(tmp_path):
    """ADR 0022 D4 rests on FTS5 external content working over a VIEW. The migration header
    claims it was verified on 3.50.4; production links a different libsqlite3, so the claim
    belongs in a test that runs wherever the code does."""
    con = _store(tmp_path)
    text_id = _reading(con)
    con.execute(
        "INSERT INTO page_fts (rowid, text) SELECT text_id, text FROM document_text_display"
    )
    hit = [(text_id,)]
    assert con.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH 'Perry'").fetchall() == hit
    snippet = con.execute(
        "SELECT snippet(page_fts, 0, '[', ']', '...', 5) FROM page_fts WHERE page_fts MATCH 'Perry'"
    ).fetchone()[0]
    assert "[Perry]" in snippet
    con.execute("INSERT INTO page_fts (page_fts) VALUES ('rebuild')")
    assert con.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH 'Perry'").fetchall() == hit


def test_a_human_insert_silently_removes_the_primary_from_the_index_source(tmp_path):
    """The loader trap: a row leaves the view with NO write to that row, so a trigger on the
    primary would never fire. Pinned so the loader's obligation is not rediscovered."""
    con = _store(tmp_path)
    primary = _reading(con)
    _human(con)
    assert (
        con.execute(
            "SELECT count(*) FROM document_text_display WHERE text_id = ?", (primary,)
        ).fetchone()[0]
        == 0
    )
