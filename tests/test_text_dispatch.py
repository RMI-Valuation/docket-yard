"""The forward pass's text stage: the queue's terms, and the dispatcher's order and halt.

ADR 0024 says the queue is the ONLY filter that exists, because D2 hands the container an
explicit list. So every term it drops is a term nothing else will, and each of these tests
names the failure that follows from losing one: the 1.07 GB application that OOM-killed the
wave twice, the `.xlsx` and `.zip` a parser would raise on, a single failure silencing a
document for ever, and a dead container burning every attempt in the record.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from docketyard.store import db
from docketyard.text import dispatch, load, queue

STAMP = "2026-09-10T12:00:00+00:00"
PIN = ("pymupdf", "1.26.0")


def _store(tmp_path):
    con = db.connect(tmp_path / "s.sqlite")
    con.execute(
        "INSERT INTO capture (capture_id, source_system, endpoint, request_params,"
        " response_sha256, http_status, filter_asserted, ingest_mode, captured_at,"
        " table_action) VALUES (1, 's', 'e', '{}', 'x', 200, 1, 'forward', ?, 't')",
        (STAMP,),
    )
    # a wave's capture: backfill, and asserted. D1 excludes it by MODE, not by assertion.
    con.execute(
        "INSERT INTO capture (capture_id, source_system, endpoint, request_params,"
        " response_sha256, http_status, filter_asserted, ingest_mode, captured_at,"
        " table_action) VALUES (2, 's', 'e', '{}', 'y', 200, 1, 'backfill', ?, 't')",
        (STAMP,),
    )
    # a forward capture that did NOT assert its filter — the endpoint's first trap
    con.execute(
        "INSERT INTO capture (capture_id, source_system, endpoint, request_params,"
        " response_sha256, http_status, filter_asserted, ingest_mode, captured_at,"
        " table_action) VALUES (3, 's', 'e', '{}', 'z', 200, 0, 'forward', ?, 't')",
        (STAMP,),
    )
    return con


def _doc(con, name, *, capture=1, media="pdf", size=1024, seen=STAMP, blobs=None):
    """A document in the store. `blobs` puts its bytes on the box too — the blob pool is a
    CACHE, and a document whose local copy has been pruned is deliberately not dispatched."""
    sha = name * 64 if len(name) == 1 else name.ljust(64, "0")
    if blobs is not None:
        (blobs / sha[:2]).mkdir(parents=True, exist_ok=True)
        (blobs / sha[:2] / sha).write_bytes(b"%PDF-1.4 ...")
    con.execute(
        "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
        " VALUES (?, ?, ?, ?)",
        (sha, size, media, seen),
    )
    con.execute(
        "INSERT INTO document_source (document_sha256, source_url, capture_id, observed_at)"
        " VALUES (?, ?, ?, ?)",
        (sha, f"https://example.test/{sha}", capture, seen),
    )
    return sha


def _run(con, sha, *, outcome="read", channel="text-layer", render="native", at=STAMP):
    con.execute(
        "INSERT INTO ocr_run (document_sha256, method, method_version, reading_channel,"
        " render_profile, outcome, ran_at) VALUES (?, 'pymupdf', '1.26.0', ?, ?, ?, ?)",
        (sha, channel, render, outcome, at),
    )


# A cutoff AFTER every dispatch these tests write, so the retry interval blocks nothing
# unless a test asks it to. The interval is per DOCUMENT and the cap is per PIN, and a
# default that silently applied both would hide which of them a test was actually exercising.
AFTER = "2026-09-11T00:00:00+00:00"


def _due(con, **over):
    terms = {"method": PIN[0], "version": PIN[1], "since": AFTER}
    return queue.due(con, **(terms | over))


def test_the_queue_is_forward_scope_and_the_mode_is_what_decides_it(tmp_path):
    """D1: the instance owns a document when a capture that observed it ran in `forward` mode
    and asserted its filter. A wave's own documents are excluded at capture time so the walk
    is not swamped by a running backfill, and a capture that did not assert what it asked for
    is trusted by nothing downstream — the endpoint's first trap, applied where it always is."""
    con = _store(tmp_path)
    mine = _doc(con, "a")
    _doc(con, "b", capture=2)  # a wave's
    _doc(con, "c", capture=3)  # forward, filter not asserted
    assert _due(con) == [mine]
    con.close()


def test_a_document_seen_by_both_a_wave_and_the_watch_is_in_scope(tmp_path):
    """`document_source` rows ACCUMULATE and are never repointed, which is why D1 joins them
    rather than `observed_in_event` — current state, and it moves. A replaced archive file
    mints a new document under the re-check's forward capture, and no record filter would
    reach it."""
    con = _store(tmp_path)
    sha = _doc(con, "a", capture=2)
    con.execute(
        "INSERT INTO document_source (document_sha256, source_url, capture_id, observed_at)"
        " VALUES (?, 'https://example.test/again', 1, ?)",
        (sha, STAMP),
    )
    assert _due(con) == [sha]
    con.close()


def test_the_size_and_media_terms_belong_to_the_queue(tmp_path):
    """D3, and the reason it is stated twice in the ADR: D2 hands the container an EXPLICIT
    LIST, so the queue is the only filter there is. Without these the queue dispatches the
    1.07 GB application that OOM-killed the wave twice, and every `.xlsx`, `.zip` and `.docx`
    the record holds — the container dies, the attempt burns, and the document is exhausted
    without ever being read or refused with a reason."""
    con = _store(tmp_path)
    ok = _doc(con, "a")
    _doc(con, "b", size=(64 << 20) + 1)
    _doc(con, "c", media="zip")
    _doc(con, "d", media=None)
    assert _due(con) == [ok]
    census = queue.census(con, method=PIN[0], version=PIN[1], since=AFTER)
    assert census["forward"] == 4
    assert (census["media_null"], census["media_other"], census["oversize"]) == (1, 1, 1)
    assert census["due"] == 1
    con.close()


def test_the_census_tells_a_terminal_count_from_one_in_flight(tmp_path):
    """§ Owed 6: without the split a reader cannot tell a document the stage has given up on
    at this version from one it is still waiting on — "handed over and nothing came back"
    and "in flight" were one number."""
    con = _store(tmp_path)
    due, resting, spent = _doc(con, "a"), _doc(con, "b"), _doc(con, "c")
    _run(con, _doc(con, "d"))

    def hand_over(sha, at):
        con.execute(
            "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
            " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
            (sha, *PIN, at),
        )

    hand_over(resting, "2026-09-10T11:00:00+00:00")
    for _ in range(queue.EXTRACT_ATTEMPTS):
        hand_over(spent, "2026-09-01T00:00:00+00:00")
    # spent AND recent is exhausted: the attempts are the terminal fact
    hand_over(spent, "2026-09-10T11:30:00+00:00")
    c = queue.census(con, method=PIN[0], version=PIN[1], since="2026-09-10T06:00:00+00:00")
    assert (c["due"], c["resting"], c["exhausted"], c["already_read"]) == (1, 1, 1, 1)
    assert c["eligible"] == c["due"] + c["resting"] + c["exhausted"]
    assert _due(con, since="2026-09-10T06:00:00+00:00") == [due]
    con.close()


def test_methodology_publishes_the_queue_from_its_own_constants(tmp_path):
    """The sentence and the table come from the constants and the census, so they cannot
    drift from what the stage does; with no pin the page says nothing is being handed over."""
    from fastapi.testclient import TestClient

    from docketyard.web.app import create_app
    from tests.test_web import build_store

    path = build_store(tmp_path)
    body = TestClient(create_app(path)).get("/methodology").text
    assert "No reader is declared at present" in body
    for phrase in (
        f"at most {queue.EXTRACT_LIMIT} files",
        f"a PDF of {queue.EXTRACT_MAX_BYTES >> 20} MB or less",
        f"no sooner than {queue.EXTRACT_RETRY_HOURS} hours",
        f"at most {queue.EXTRACT_ATTEMPTS} times",
        f"the last {dispatch.HALT_AFTER} hand-offs",
    ):
        assert phrase in body, phrase
    con = db.connect(path)
    load.declare_producer(con, queue.CHANNEL, queue.RENDER, dispatch.ROLE, *PIN, by="test")
    con.commit()
    con.close()
    body = TestClient(create_app(path)).get("/methodology").text
    assert "No reader is declared" not in body
    assert "The reader: pymupdf 1.26.0" in body and "All files from the watch" in body


def test_a_failed_run_does_not_silence_a_document_for_ever(tmp_path):
    """D4: the OUTCOME is part of the read test, not the row's existence. Under "no row at
    that key" one `failed` would silence this queue for that document at every version and
    after a single attempt, and the release that fixes those bytes would change nothing."""
    con = _store(tmp_path)
    read = _doc(con, "a")
    failed = _doc(con, "b")
    skipped = _doc(con, "c")
    _run(con, read, outcome="read")
    _run(con, failed, outcome="failed")
    _run(con, skipped, outcome="not-paginable")
    assert set(_due(con)) == {failed, skipped}
    con.close()


def test_a_read_at_another_version_counts_and_another_channel_does_not(tmp_path):
    """D6: the read test never mentions the version — under "no run at the PINNED version" a
    point release would re-read 74,295 documents and rewrite about 1.1M rows. But it is of
    ONE reading key: an OCR pass over the same document says nothing about its text layer."""
    con = _store(tmp_path)
    old = _doc(con, "a")
    ocr = _doc(con, "b")
    con.execute(
        "INSERT INTO ocr_run (document_sha256, method, method_version, reading_channel,"
        " render_profile, outcome, ran_at) VALUES (?, 'pymupdf', '0.9.0', 'text-layer',"
        " 'native', 'read', ?)",
        (old, STAMP),
    )
    _run(con, ocr, channel="ocr", render="150")
    assert _due(con) == [ocr]
    con.close()


def test_the_attempt_cap_is_per_pin_and_the_interval_is_per_document(tmp_path):
    """D4, both halves and both for a stated reason. The count is per pin so a version bump
    is the reset — otherwise a document that burned its attempts on one `pymupdf` release is
    out for ever. The interval is per DOCUMENT, or a pin that flaps re-dispatches with no
    interval at all."""
    con = _store(tmp_path)
    sha = _doc(con, "a")
    for _ in range(queue.EXTRACT_ATTEMPTS):
        con.execute(
            "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
            " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
            (sha, *PIN, STAMP),
        )
    assert _due(con) == [], "exhausted at this pin"
    assert _due(con, version="1.27.0") == [sha], "a version bump is the reset"
    # ...and the interval is per DOCUMENT, so a bump does not re-ask inside it
    assert _due(con, version="1.27.0", since="2026-09-10T00:00:00+00:00") == []
    con.close()


def test_newest_first(tmp_path):
    """D3's promise: a decision served this morning is read this pass, and the archive
    documents D1 admits drain from the recent end backwards."""
    con = _store(tmp_path)
    old = _doc(con, "a", seen="2026-01-01T00:00:00+00:00")
    new = _doc(con, "b", seen="2026-09-10T23:00:00+00:00")
    assert _due(con) == [new, old]
    assert _due(con, limit=1) == [new]
    con.close()


# --- the dispatcher -------------------------------------------------------------------


def _pin(con):
    load.declare_producer(con, dispatch.CHANNEL, dispatch.RENDER, dispatch.ROLE, *PIN)
    con.commit()


def test_the_stage_does_nothing_until_a_producer_is_pinned(tmp_path):
    """D6: the poller READS a pin and never invents one. With none declared the stage does
    nothing and says so, which is the safe direction — a poller carrying its own constant
    drifts silently from the container, and the silent direction is the container moving
    ahead, leaving every document the new version could read exhausted at a pin that no
    longer exists."""
    con = _store(tmp_path)
    _doc(con, "a")
    problems: list[str] = []
    out = dispatch.run(
        con,
        tmp_path,
        spool=tmp_path / "spool",
        requests=tmp_path / "req",
        problems=problems,
        log=lambda _: None,
    )
    assert out["skipped"].startswith("no producer pinned")
    assert not (tmp_path / "req").exists(), "nothing was handed over"
    assert con.execute("SELECT COUNT(*) FROM extraction_dispatch").fetchone() == (0,)
    con.close()


def test_the_dispatch_is_committed_before_the_request_exists(tmp_path):
    """D4: a hand-off the record does not remember is this decision's own failure. The rows
    are written and COMMITTED first, and the stage refuses to enqueue while it still holds a
    transaction."""
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a", blobs=tmp_path / "blobs")
    con.commit()
    problems: list[str] = []
    out = dispatch.run(
        con,
        tmp_path,
        spool=tmp_path / "spool",
        requests=tmp_path / "req",
        problems=problems,
        log=lambda _: None,
    )
    assert out["dispatched"] == 1
    assert not con.in_transaction
    rows = con.execute(
        "SELECT document_sha256, pinned_method, pinned_method_version FROM extraction_dispatch"
    ).fetchall()
    assert rows == [(sha, *PIN)]
    written = list((tmp_path / "req").glob("*.json"))
    assert len(written) == 1
    body = json.loads(written[0].read_text(encoding="utf-8"))
    assert body["documents"] == [sha]
    assert not list((tmp_path / "req").glob("*.tmp")), "renamed, never left half written"
    con.close()


def test_the_halt_is_a_query_and_sends_one_canary(tmp_path):
    """D4: held as a FLAG the halt either never clears — nothing dispatched means nothing
    lands means the condition holds for ever — or it clears every other pass, halving a dead
    container's burn rate instead of stopping it. As a query with a canary, recovery is
    automatic and the condition stays measurable."""
    con = _store(tmp_path)
    _pin(con)
    shas = [_doc(con, f"{i:02d}", blobs=tmp_path / "blobs") for i in range(dispatch.HALT_AFTER + 5)]
    for sha in shas[: dispatch.HALT_AFTER]:
        con.execute(
            "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
            " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
            (sha, *PIN, STAMP),
        )
    con.commit()
    assert dispatch.halted(con), "nothing landed for the last window of dispatches"
    problems: list[str] = []
    out = dispatch.run(
        con,
        tmp_path,
        spool=tmp_path / "spool",
        requests=tmp_path / "req",
        problems=problems,
        log=lambda _: None,
    )
    assert out["halted"] and out["dispatched"] == 1, "one canary, not a full queue"
    assert any("canary" in p for p in problems)
    con.close()


def test_a_landing_clears_the_halt_without_an_operator(tmp_path):
    """The other half: the query is asked again next pass, so a container that comes back
    clears its own halt. The floor `ran_at >= dispatched_at` is what stops a wave load
    landing during an outage from clearing it — a narrowing, not a proof (§ Owed 5)."""
    con = _store(tmp_path)
    _pin(con)
    shas = [_doc(con, f"{i:02d}") for i in range(dispatch.HALT_AFTER)]
    for sha in shas:
        con.execute(
            "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
            " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
            (sha, *PIN, STAMP),
        )
    # a run that predates its dispatch does not answer it
    _run(con, shas[0], at="2026-01-01T00:00:00+00:00")
    con.commit()
    assert dispatch.halted(con)
    _run(con, shas[0], at="2026-09-10T13:00:00+00:00")
    con.commit()
    assert not dispatch.halted(con)
    con.close()


def test_an_empty_dispatch_table_is_not_a_dead_container(tmp_path):
    """Or the stage would never start: with nothing dispatched, every one of the last
    `HALT_AFTER` dispatches is trivially unanswered."""
    con = _store(tmp_path)
    assert not dispatch.halted(con)
    con.close()


def test_the_retry_interval_holds_across_passes(tmp_path):
    """`EXTRACT_ATTEMPTS` alone means a container down for 90 minutes burns every attempt of
    everything dispatched in those three passes, and they leave the queue unread for ever with
    no `ocr_run` row and nothing raised. The interval is what stops that."""
    con = _store(tmp_path)
    _pin(con)
    _doc(con, "a", blobs=tmp_path / "blobs")
    con.commit()
    problems: list[str] = []
    args = {
        "spool": tmp_path / "spool",
        "requests": tmp_path / "req",
        "problems": problems,
        "log": lambda _: None,
    }
    assert dispatch.run(con, tmp_path, **args)["dispatched"] == 1
    assert dispatch.run(con, tmp_path, **args)["dispatched"] == 0, "inside the interval"
    assert con.execute("SELECT COUNT(*) FROM extraction_dispatch").fetchone() == (1,)
    con.close()


@pytest.mark.parametrize("hours", [0, queue.EXTRACT_RETRY_HOURS + 1])
def test_the_interval_is_measured_from_the_dispatch(tmp_path, hours):
    con = _store(tmp_path)
    sha = _doc(con, "a")
    when = (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")
    con.execute(
        "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
        " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
        (sha, *PIN, when),
    )
    since = (datetime.now(UTC) - timedelta(hours=queue.EXTRACT_RETRY_HOURS)).isoformat(
        timespec="seconds"
    )
    assert _due(con, since=since) == ([] if hours == 0 else [sha])
    con.close()


# --- the trust boundary (security review, 2026-09-10) ----------------------------------


def _spool(tmp_path, sha, *, at="spool", **over):
    """A spool file as the parser writes one."""
    record = {
        "document_sha256": sha,
        "size_bytes": 10,
        "method": "text-layer",
        "method_version": "2",
        "tool": PIN[0],
        "tool_version": PIN[1],
        "extracted_at": "2026-09-10T13:00:00+00:00",
        "pages": 1,
        "chars": 5,
        "image_only": False,
        "text_sha256": "0" * 64,
        "page_text": ["hello"],
    } | over
    path = tmp_path / at / sha[:2] / f"{sha}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_a_reading_nobody_asked_for_is_quarantined_and_never_loaded(tmp_path):
    """THE TRUST BOUNDARY. Grant D2's own premise — a hostile PDF takes the parser. The
    isolation holds, but the spool is a read-write mount, and the loader's only identity
    tests are that a record's digest is its filename and that the digest is a document this
    record holds. Without this check a compromised parser could write a `primary` reading for
    ANY of the hundred thousand documents in the store, displace the live one, and have the
    forged text indexed and served with provenance naming a producer that never read those
    bytes (security review, 2026-09-10; ADR 0024 D4 assigns the check here by name)."""
    con = _store(tmp_path)
    _pin(con)
    asked = _doc(con, "a")
    never = _doc(con, "b")
    con.execute(
        "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
        " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
        (asked, *PIN, STAMP),
    )
    con.commit()
    _spool(tmp_path, asked)
    _spool(tmp_path, never)
    problems: list[str] = []
    admitted, refused = dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems)
    assert (admitted, refused) == (1, 1)
    assert (tmp_path / "quarantine" / f"{never}.json").is_file(), "kept as evidence"
    # THE CHECK IS A MOVE, so the loader's directory holds only what was asked for and a file
    # landing mid-pass cannot slip between the check and the walk
    assert (tmp_path / "ready" / asked[:2] / f"{asked}.json").is_file()
    assert not any(p.is_dir() and any(p.iterdir()) for p in (tmp_path / "spool").iterdir())
    assert any("no dispatch precedes it" in p for p in problems)
    con.close()


def test_a_dispatch_after_the_reading_does_not_authorise_it(tmp_path):
    """The dispatch must PRECEDE the reading. Otherwise a parser that had been handed one
    document could pre-write records for every other and have them accepted the moment any
    later pass happened to dispatch those documents."""
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    con.execute(
        "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
        " pinned_method_version, dispatched_at) VALUES (?, ?, ?, '2026-09-10T23:00:00+00:00')",
        (sha, *PIN),
    )
    con.commit()
    _spool(tmp_path, sha, extracted_at="2026-09-10T13:00:00+00:00")
    problems: list[str] = []
    assert dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems) == (0, 1)
    con.close()


def test_only_the_shape_this_stage_produces_is_accepted(tmp_path):
    """One legitimate producer writes into this directory and it can write one shape. An
    `ocr` reading here is not a reading this stage asked for, and `pinned` constrains only
    keys the registry HOLDS — so an undeclared key would otherwise be free to displace the
    text layer through the cross-key supersede path."""
    con = _store(tmp_path)
    _pin(con)
    sha = _doc(con, "a")
    con.execute(
        "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
        " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
        (sha, *PIN, STAMP),
    )
    con.commit()
    # a reading document, not an extraction record: it names its own role and channel
    path = tmp_path / "spool" / sha[:2] / f"{sha}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "document_sha256": sha,
                "method": "dots.mocr",
                "method_version": "1.5",
                "render_profile": "150",
                "reading_channel": "ocr",
                "reading_role": "primary",
                "tool": "smuggled",
                "extracted_at": "2026-09-10T13:00:00+00:00",
                "ran_at": "2026-09-10T13:00:00+00:00",
                "outcome": "read",
                "pages": [{"page_no": 1, "text": "forged"}],
            }
        ),
        encoding="utf-8",
    )
    problems: list[str] = []
    assert dispatch.admit(con, tmp_path / "spool", tmp_path / "ready", problems) == (0, 1)
    assert any("not an extraction record" in p for p in problems)
    con.close()


def test_a_landed_reading_is_swept_and_an_unlanded_one_is_kept(tmp_path):
    """ADR 0024 D9: a file is removed only after the loader reports a landed outcome, never
    on `unreadable`, `failed` or `aborted`, or a parse failure would destroy the raw D5 needs
    a reason from. Without the sweep the spool grows without bound and every pass re-walks
    the whole of it (security review, 2026-09-10)."""
    con = _store(tmp_path)
    landed = _doc(con, "a")
    waiting = _doc(con, "b")
    _spool(tmp_path, landed, at="ready")
    _spool(tmp_path, waiting, at="ready")
    con.execute(
        "INSERT INTO ocr_run (document_sha256, method, method_version, reading_channel,"
        " render_profile, outcome, ran_at) VALUES (?, ?, ?, 'text-layer', 'native', 'read',"
        " '2026-09-10T13:00:00+00:00')",
        (landed, *PIN),
    )
    con.commit()
    assert dispatch.sweep(con, tmp_path / "ready") == 1
    assert not (tmp_path / "ready" / landed[:2] / f"{landed}.json").exists()
    assert (tmp_path / "ready" / waiting[:2] / f"{waiting}.json").is_file()
    con.close()


def test_a_document_whose_blob_was_pruned_is_not_dispatched(tmp_path):
    """The blob pool on the box is a CACHE — S3 is the store, and `prune_blobs.py` deletes
    local copies over thirty days old. The parser has `network_mode: none` and no credentials,
    so it cannot fetch what is not there: it would write "no blob on this box", the stub would
    count as an attempt, and three passes later the document would leave the queue for ever
    having never been read. So it is not dispatched, no attempt is spent, and the number is
    reported rather than being a silence (code review, 2026-09-10)."""
    con = _store(tmp_path)
    _pin(con)
    here = _doc(con, "a", blobs=tmp_path / "blobs")
    _doc(con, "b")  # in the store, pruned from the box
    con.commit()
    problems: list[str] = []
    out = dispatch.run(
        con,
        tmp_path,
        spool=tmp_path / "spool",
        requests=tmp_path / "req",
        problems=problems,
        log=lambda _: None,
    )
    assert (out["dispatched"], out["pruned"]) == (1, 1)
    assert any("no blob on this box" in p for p in problems)
    rows = con.execute("SELECT document_sha256 FROM extraction_dispatch").fetchall()
    assert rows == [(here,)], "no attempt is spent on what cannot be read"
    con.close()


def test_a_refusal_records_why(tmp_path):
    """ADR 0024 D5, and § Owed 2 until 2026-09-10: "a refusal recording THAT it failed and
    never WHY is an ADR 0007 assertion missing its reason." Both producers write one — "not a
    PDF", the exception, "no blob on this box" — and `load.Header` had no field to carry it,
    so every reason was dropped at the boundary and `ocr_run.note` stayed NULL. The first
    thing that goes wrong in production is diagnosable from the record or it is not."""
    con = _store(tmp_path)
    sha = _doc(con, "a")
    con.commit()
    _spool(
        tmp_path,
        sha,
        at="ready",
        outcome="not-paginable",
        note="not a PDF",
        page_text=None,
    )
    path = tmp_path / "ready" / sha[:2] / f"{sha}.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    del body["page_text"]  # a stub: the header fields, an outcome, a reason, and no pages
    path.write_text(json.dumps(body), encoding="utf-8")

    load.run(con, tmp_path / "ready", tmp_path)
    con.commit()
    assert con.execute(
        "SELECT outcome, note, pages_read FROM ocr_run WHERE document_sha256 = ?", (sha,)
    ).fetchone() == ("not-paginable", "not a PDF", 0)
    con.close()


def test_a_reason_is_bounded_and_never_invented(tmp_path):
    """It comes from a parser that has just read a file a third party wrote, so it is bounded
    rather than trusted — an exception's text can carry a page of a malformed PDF. And a
    reading with nothing to say says nothing: a row with no reason is different from a row
    asserting that nothing went wrong."""
    from docketyard.text.load import _note

    assert _note({"note": "  no blob on this box  "}) == "no blob on this box"
    assert _note({"note": "x" * 5000}) == "x" * load.NOTE_MAX
    assert _note({}) is None
    assert _note({"note": "   "}) is None
    assert _note({"note": 17}) is None
