"""ADR 0024 § Owed 5, settled 2026-09-11: a reading names the dispatch it answers.

The stage stamps `ocr_run.dispatch_id` with the dispatch the container QUOTED and admit
checked; a hand load never stamps; the halt is a join, so a wave load can no longer clear it.
Each test names the failure it stands against — most of them schema-critic's.
"""

import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docketyard.store import db
from docketyard.text import dispatch, load
from docketyard.text.fields import read_head
from tests.test_text_dispatch import PIN, STAMP, _doc, _pin, _spool, _store

EXTRACT = Path(__file__).resolve().parents[1] / "infra" / "extract" / "extract.py"
LATE = "2026-09-10T13:00:00+00:00"  # `_spool`'s own extracted_at
NOW = datetime(2026, 9, 10, 14, 0, tzinfo=UTC)  # the loader's clock, an hour after the reading


@pytest.fixture(autouse=True)
def _loader_clock(monkeypatch):
    """The window is counted back from the LOADER's clock, so the tests fix it."""
    monkeypatch.setattr(dispatch, "clock", lambda: NOW)


def _quoted(tmp_path, sha, quote, *, at="spool", **over):
    """A spool file as the container writes one since the echo: the request's
    `dispatched_at` in the header, AHEAD of `page_text` — `read_head` parses only what
    precedes that key, so admit and the loader both see exactly what the head holds."""
    path = _spool(tmp_path, sha, at=at, **over)
    record = json.loads(path.read_text(encoding="utf-8"))
    text = record.pop("page_text")
    record["dispatched_at"] = quote
    record["page_text"] = text
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _unquoted(tmp_path, sha):
    """A record from the container before the echo."""
    path = _spool(tmp_path, sha)
    record = json.loads(path.read_text(encoding="utf-8"))
    del record["dispatched_at"]
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _hand_over(con, sha, at):
    return con.execute(
        "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
        " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
        (sha, *PIN, at),
    ).lastrowid


def _pass(con, tmp_path):
    problems: list[str] = []
    out = dispatch.run(
        con,
        tmp_path,
        spool=tmp_path / "spool",
        requests=tmp_path / "req",
        problems=problems,
        log=lambda _: None,
    )
    return out, problems


def _stamp_of(con, sha):
    return con.execute(
        "SELECT dispatch_id FROM ocr_run WHERE document_sha256 = ?", (sha,)
    ).fetchone()


def test_the_stage_stamps_the_dispatch_the_container_quoted(tmp_path):
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    did = _hand_over(con, sha, STAMP)
    con.commit()
    _quoted(tmp_path, sha, STAMP)
    out, problems = _pass(con, tmp_path)
    assert out["admitted"] == 1 and out["loaded"].get("loaded") == 1, (out, problems)
    assert _stamp_of(con, sha) == (did,)
    assert out["unanswered"] == 0
    con.close()


def test_a_quote_that_names_no_dispatch_of_this_document_is_quarantined(tmp_path):
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    _hand_over(con, sha, STAMP)
    con.commit()
    _quoted(tmp_path, sha, "2026-09-10T11:11:11+00:00")
    problems: list[str] = []
    assert dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems) == (0, 1)
    assert any("quotes is not one of this document's" in p for p in problems)
    con.close()


def test_a_late_first_reading_is_stamped_with_its_own_request_not_the_latest(tmp_path):
    """The rule refused: "the latest dispatch before ran_at" stamps a document re-dispatched
    after the retry interval with its SECOND request when the first one's reading lands late,
    publishing the first as unanswered for good (schema-critic, 2026-09-11)."""
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    first = _hand_over(con, sha, "2026-09-10T06:00:00+00:00")
    _hand_over(con, sha, "2026-09-10T12:30:00+00:00")
    con.commit()
    _quoted(tmp_path, sha, "2026-09-10T06:00:00+00:00")  # read at 13:00
    out, problems = _pass(con, tmp_path)
    assert out["loaded"].get("loaded") == 1, (out, problems)
    assert _stamp_of(con, sha) == (first,)
    con.close()


def test_a_record_that_quotes_nothing_is_refused_not_stamped_by_inference(tmp_path):
    """A record from the container before the echo. Stamping it by inference would make the
    correction row's claim — every later stamp was quoted — false (schema-critic, 2026-09-11);
    the deploy lands such records BEFORE the migration, which stamps them under its own rule."""
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    _hand_over(con, sha, STAMP)
    con.commit()
    _unquoted(tmp_path, sha)
    problems: list[str] = []
    assert dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems) == (0, 1)
    assert any("it quotes no dispatch" in p for p in problems)
    con.close()


def test_the_migration_window_is_the_stage_window():
    """The migration copies `AUTHORISED_HOURS` as a literal, because it cannot import it."""
    import re

    sql = (Path(db.__file__).parent / "0026_ocr_run_dispatch.sql").read_text(encoding="utf-8")
    windows = re.findall(r"'-(\d+) hours'", sql)
    assert len(windows) >= 2 and {int(h) for h in windows} == {dispatch.AUTHORISED_HOURS}


def test_a_hand_load_is_never_stamped_and_never_clears_the_halt(tmp_path):
    """The gap Owed 5 names: a wave load landing during a container outage satisfied the old
    floor and cleared the halt for documents the parser never read. A hand load passes no
    resolver, so its row is NULL whatever its file quotes — `dispatched_at` is published."""
    con = _store(tmp_path)
    _pin(con)
    shas = [_doc(con, f"{i:02d}") for i in range(dispatch.HALT_AFTER)]
    for sha in shas:
        _hand_over(con, sha, STAMP)
    con.commit()
    root = tmp_path / "root"
    _quoted(tmp_path, shas[0], STAMP, at="root")
    totals = load.run(con, root, tmp_path, log=lambda _: None)
    con.commit()
    assert totals["loaded"] == 1
    assert _stamp_of(con, shas[0]) == (None,)
    assert dispatch.halted(con), "a hand load is not the container answering"
    con.close()


def test_a_restart_after_a_stamp_is_still_a_restart(tmp_path):
    """The stamp is resolved below the restart check and is not part of it, so re-walking a
    root the stage already landed stays free."""
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    _hand_over(con, sha, STAMP)
    con.commit()
    root = tmp_path / "root"
    _quoted(tmp_path, sha, STAMP, at="root")

    def stamp(h):
        return dispatch.answering(con, h.document_sha256, h.ran_at, h.dispatched_at)[0]

    assert load.run(con, root, tmp_path, log=lambda _: None, stamp=stamp)["loaded"] == 1
    con.commit()
    assert load.run(con, root, tmp_path, log=lambda _: None, stamp=stamp)["restart"] == 1
    con.close()


def test_a_malformed_quote_is_refused_not_read_as_absent(tmp_path):
    """Absent falls back to the one unambiguous dispatch; a parser must not choose that
    path by writing a number where the timestamp belongs."""
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    _hand_over(con, sha, STAMP)
    con.commit()
    _quoted(tmp_path, sha, 12)
    problems: list[str] = []
    assert dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems) == (0, 1)
    con.close()


@pytest.mark.parametrize(
    ("dispatched", "ran_at", "why"),
    [
        # back-dated onto a dispatch two months old: the window was measured from ran_at alone
        ("2026-07-01T00:00:00+00:00", "2026-07-01T00:05:00+00:00", "no dispatch precedes it"),
        # a form fromisoformat accepts and the SQL compares as a string
        (STAMP, "20260910T130000", "not in the form the container writes"),
        ("2026-09-10T12:00:00+00:00", "2026-09-11T09:00:00+00:00", "dated in the future"),
        # the canonical form, but year 1: the window's own arithmetic overflows
        (STAMP, "0001-01-01T00:00:00+00:00", "not a plausible timestamp"),
    ],
)
def test_the_parser_cannot_choose_its_clock(tmp_path, dispatched, ran_at, why):
    """Security review, 2026-09-11, confirmed by running `answering`: a compromised parser
    controls `ran_at`, so the window must be counted back from the loader's clock too, the
    form must be the container's own, and a reading cannot be dated ahead of now."""
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    _hand_over(con, sha, dispatched)
    con.commit()
    _quoted(tmp_path, sha, dispatched, extracted_at=ran_at)
    problems: list[str] = []
    assert dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems) == (0, 1)
    assert any(why in p for p in problems), problems
    con.close()


def test_a_dispatch_already_answered_cannot_be_answered_again(tmp_path):
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    did = _hand_over(con, sha, STAMP)
    con.execute(
        "INSERT INTO ocr_run (document_sha256, method, method_version, reading_channel,"
        " render_profile, outcome, ran_at, dispatch_id)"
        " VALUES (?, ?, ?, 'text-layer', 'native', 'read', '2026-09-10T12:30:00+00:00', ?)",
        (sha, *PIN, did),
    )
    con.commit()
    _quoted(tmp_path, sha, STAMP)
    problems: list[str] = []
    assert dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems) == (0, 1)
    con.close()


def test_an_explicit_null_quote_is_refused_at_admit(tmp_path):
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    _hand_over(con, sha, STAMP)
    con.commit()
    _quoted(tmp_path, sha, None)
    problems: list[str] = []
    assert dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems) == (0, 1)
    assert any("quotes is not a timestamp" in p for p in problems)
    con.close()


def test_the_migration_stamps_what_already_landed_only_where_it_is_unambiguous(tmp_path):
    """Readings the stage landed before 0026 would otherwise say "no stage dispatch answered"
    — false — and the halt would fire every pass until twenty stamped ones accrued. Stamped
    under a narrower rule than the loader's, with a correction row naming the boundary."""
    path = tmp_path / "old.sqlite"
    con = db.connect(path, upto=25)
    con.execute(
        "INSERT INTO capture (capture_id, source_system, endpoint, request_params,"
        " response_sha256, http_status, filter_asserted, ingest_mode, captured_at,"
        " table_action) VALUES (1, 's', 'e', '{}', 'x', 200, 1, 'forward', ?, 't')",
        (STAMP,),
    )
    _pin(con)
    stage, hand, twice, stale = (_doc(con, n) for n in "abcd")
    for sha in (stage, hand, twice):
        _hand_over(con, sha, "2026-09-10T23:45:17+00:00")
    _hand_over(con, twice, "2026-09-10T20:00:00+00:00")
    _hand_over(con, stale, "2026-09-08T00:00:00+00:00")
    runs = [(stage, PIN[1]), (hand, "1.28.2"), (twice, PIN[1]), (stale, PIN[1])]
    for sha, version in runs:
        con.execute(
            "INSERT INTO ocr_run (document_sha256, method, method_version, reading_channel,"
            " render_profile, outcome, ran_at) VALUES (?, ?, ?, 'text-layer', 'native', 'read',"
            " '2026-09-10T23:45:30+00:00')",
            (sha, PIN[0], version),
        )
    con.commit()
    con.close()
    con = db.connect(path)  # applies 0026
    stamped = dict(con.execute("SELECT document_sha256, dispatch_id FROM ocr_run"))
    assert stamped[stage] is not None
    assert stamped[hand] is None, "not a declared producer's version: a hand load"
    assert stamped[twice] is None, "two dispatches could be its request"
    assert stamped[stale] is None, "its only dispatch is more than 24 hours before it"
    (note,) = con.execute(
        "SELECT note FROM correction WHERE target_table = 'ocr_run' AND target_key = 'dispatch_id'"
    ).fetchone()
    assert "the 1 rows" in note
    assert "2 rows at a version a dispatch was pinned to were left NULL" in note
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
    fresh = db.connect(tmp_path / "fresh.sqlite")
    assert fresh.execute("SELECT COUNT(*) FROM correction").fetchone()[0] == 0
    fresh.close()


def _extract_module():
    spec = importlib.util.spec_from_file_location("extract_container", EXTRACT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_container_quotes_its_request_ahead_of_the_text(tmp_path):
    """`read_head` parses only what precedes `page_text`, so an echo after it would be
    invisible to admit — and every record would fall back to the time rule."""
    mod = _extract_module()
    mod.BLOBS = tmp_path / "blobs"
    doc = mod.fitz.open()
    doc.new_page().insert_text((72, 72), "Decided: September 9, 2026")
    pdf = doc.tobytes()
    sha = hashlib.sha256(pdf).hexdigest()
    (mod.BLOBS / sha[:2]).mkdir(parents=True)
    (mod.BLOBS / sha[:2] / sha).write_bytes(pdf)
    at = "2026-09-10T23:45:17+00:00"
    record = mod.extract(sha, mod.fitz.VersionBind, at)
    keys = list(record)
    assert keys.index("dispatched_at") < keys.index("page_text")
    path = tmp_path / "r.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert read_head(path)["dispatched_at"] == at
    # a refusal answers a dispatch too
    (mod.BLOBS / "ab").mkdir()
    (mod.BLOBS / "ab" / ("ab" * 32)).write_bytes(b"PK\x03\x04 not a pdf")
    assert mod.extract("ab" * 32, "1.26.0", at)["dispatched_at"] == at
