"""`tools/fleet/`: the lease's promises, and seed → read → collect → re-seed against a real
route root and the real loader. Claims are exclusive; a dead lease returns; a lost lease
drops its answer; the server dying spends one attempt on the page in flight and none on the
rest; a final failure must be the page's own; a collected document is whole when every
failure is the page's, re-read when one is not; and what `collect` writes is what
`docketyard text load` takes. The box tools are not packages, so they load from their paths.
"""

import importlib.util
import json
import sys
import time
import types
from pathlib import Path

import pytest

from docketyard.store import db
from docketyard.text import load
from tests.test_documents import (  # noqa: F401 — the fixture registers itself here too
    _store_with_document,
    no_store_in_the_environment,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "rmi-ai-machine"))


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pq = _module("pagequeue", ROOT / "tools" / "fleet" / "pagequeue.py")
monitor = _module("monitor", ROOT / "tools" / "fleet" / "monitor.py")
ocr_wave = _module("ocr_wave", ROOT / "tools" / "rmi-ai-machine" / "ocr_wave.py")

A, B = "a" * 64, "b" * 64
PAGES = [(A, 1), (A, 2), (B, 1)]
KEY = pq.PASSES["dots"]["key"]


@pytest.fixture
def q(tmp_path):
    queue = pq.Queue(tmp_path / "q.sqlite")
    queue.register("w1", "dots", {**KEY, "host": "x"})
    queue.register("w2", "dots", {**KEY, "host": "y"})
    assert queue.seed("dots", PAGES, reread=set()) == 3
    assert queue.seed("dots", PAGES, reread=set()) == 0  # idempotent
    yield queue
    queue.con.close()


def test_a_wrong_key_is_refused(q):
    with pytest.raises(pq.KeyMismatch):
        q.register("w3", "dots", {**KEY, "render_profile": "150"})


def test_claims_are_exclusive(q):
    first = q.claim("w1", "dots", 2, 60)
    second = q.claim("w2", "dots", 2, 60)
    assert {j["job_id"] for j in first}.isdisjoint(j["job_id"] for j in second)
    assert len(first) + len(second) == 3
    assert q.claim("w1", "dots", 2, 60) == []


def test_an_expired_lease_returns_the_page_and_a_lost_lease_drops_its_answer(q):
    jobs = q.claim("w1", "dots", 1, 0)
    time.sleep(0.01)
    again = q.claim("w2", "dots", 1, 60)
    assert again[0]["job_id"] == jobs[0]["job_id"]
    assert again[0]["attempts"] == 1  # as read before this claim's own +1
    assert q.done("w1", jobs[0]["job_id"], "late") is False
    assert q.done("w2", jobs[0]["job_id"], "[]") is True
    assert q.status()["passes"]["dots"]["done"] == 1


def test_the_last_attempt_expiring_fails_the_page_for_a_reason_that_is_not_the_pages(q):
    j = q.claim("w1", "dots", 1, 0)[0]["job_id"]
    for _ in range(2):
        time.sleep(0.01)
        q.claim("w1", "dots", 1, 0)
    time.sleep(0.01)
    q.reap()
    row = q.con.execute("SELECT state, error FROM job WHERE job_id = ?", (j,)).fetchone()
    assert (row["state"], row["error"]) == ("failed", "lease expired on attempt 3")
    assert not row["error"].startswith(pq.PAGE_OWNED)


def test_server_death_spends_one_attempt_on_the_page_in_flight_and_none_on_the_rest(q):
    ids = [j["job_id"] for j in q.claim("w1", "dots", 3, 60)]
    q.fail("w1", ids[0], "server: refused", final=False)
    q.release("w1", ids[1:])
    attempts = dict(q.con.execute("SELECT job_id, attempts FROM job WHERE state = 'pending'"))
    assert attempts == {ids[0]: 1, ids[1]: 0, ids[2]: 0}
    for _ in range(2):  # the same page brings the server down twice more: its last attempt
        again = q.claim("w1", "dots", 1, 60)
        assert again[0]["job_id"] == ids[0]
        q.fail("w1", ids[0], "server: refused", final=False)
    row = q.con.execute("SELECT state, error FROM job WHERE job_id = ?", (ids[0],)).fetchone()
    assert (row["state"], row["error"]) == ("failed", "server: refused")


def test_a_final_failure_must_be_the_pages_own(q):
    a, b = q.claim("w1", "dots", 2, 60)
    with pytest.raises(ValueError):
        q.fail("w1", a["job_id"], "server: 500", final=True)
    q.fail("w1", a["job_id"], "page: oversize: 12.0 MP", final=True)
    q.fail("w1", b["job_id"], "flaky", final=False)
    states = dict(q.con.execute("SELECT job_id, state FROM job"))
    assert (states[a["job_id"]], states[b["job_id"]]) == ("failed", "pending")


def test_collectable_waits_for_every_page(q):
    a, b, c = q.claim("w1", "dots", 3, 60)  # a, b are document A; c is B
    q.done("w1", a["job_id"], "[]")
    assert q.collectable("dots") == []
    q.fail("w1", b["job_id"], "page: finish_reason length", final=True)
    assert q.collectable("dots") == [A]
    assert [p["state"] for p in q.pages_of("dots", A)] == ["done", "failed"]
    q.done("w1", c["job_id"], "[]")
    assert sorted(q.collectable("dots")) == [A, B]


def test_status_and_the_alarms_watch_pages_read_not_pages_finished(q):
    s = q.status()["passes"]["dots"]
    assert (s["pending"], s["leased"], s["done"], s["failed"]) == (3, 0, 0, 0)
    assert s["last_read_age_seconds"] is None
    assert monitor.stalled(q.status(), 1800) == ["dots"]  # owed, never read
    a, b = q.claim("w1", "dots", 2, 60)
    q.fail("w1", a["job_id"], "page: oversize", final=True)
    assert monitor.stalled(q.status(), 1800) == ["dots"]  # a failure is not a read
    q.done("w1", b["job_id"], "[]")
    s = q.status()["passes"]["dots"]
    assert s["last_read_age_seconds"] < 5
    assert s["last_hour"] == {"done": 1, "failed": 1}
    assert monitor.stalled(q.status(), 1800) == []
    assert monitor.failing(q.status()) == []  # one failure is under the floor
    text = monitor.metrics(q.status(), 1800)
    assert 'docket_yard_fleet_last_read_known{pass="dots"} 1' in text
    assert 'docket_yard_fleet_stalled{pass="dots"} 0' in text
    assert "-1" not in text


def test_the_monitor_never_creates_a_queue(tmp_path):
    with pytest.raises(FileNotFoundError):
        pq.Queue(tmp_path / "missing.sqlite", readonly=True)
    assert not (tmp_path / "missing.sqlite").exists()


# --- seed → read → collect → re-seed, through the real loader ------------------------------


def _route_root(out: Path, sha: str, classes: dict[int, str]) -> None:
    doc = {"document_sha256": sha, "pages": {str(n): {"class": c} for n, c in classes.items()}}
    ocr_wave._write(ocr_wave.shard(out / "route", sha), doc)


def test_seed_read_collect_and_reseed(tmp_path):
    path, sha = _store_with_document(tmp_path)
    out = tmp_path / "ocr"
    _route_root(out, sha, {1: "clean", 2: "degraded", 3: "degraded", 4: "graphic"})
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", "dots", {**KEY, "host": "x"})

    n = pq.seed_pass(q, "dots", out)
    assert (n["documents"], n["pages"], n["new"], n["whole"]) == (1, 2, 2, 0)
    assert pq.seed_pass(q, "dots", out)["new"] == 0  # open: already queued

    # page 2 read, page 3 the page's own failure: the document is whole with it failed
    a, b = q.claim("w1", "dots", 2, 60)
    q.done("w1", a["job_id"], json.dumps([{"category": "Text", "text": "faint fax page"}]))
    q.fail("w1", b["job_id"], "page: oversize: 12.0 MP at 200 DPI", final=True)
    assert pq.collect_pass(q, "dots", out) == 1
    written = ocr_wave.shard(out / "dots", sha)
    doc = json.loads(written.read_text(encoding="utf-8"))
    assert doc["outcome"] == "read" and doc["pages_failed"] == 1
    assert doc["page_failures"] == [
        {"page_no": 3, "reason": "oversize", "detail": "oversize: 12.0 MP at 200 DPI"}
    ]
    assert doc["page_failure_classifier"] == ocr_wave.CLASSIFIER
    assert doc["pages"] == [
        {
            "page_no": 2,
            "text": "faint fax page",
            "member": "engine/pages/0",
            "route": ocr_wave.route_of("degraded"),
        }
    ]
    assert doc["engine"]["pages"][0]["blocks"][0]["text"] == "faint fax page"
    manifest = json.loads((out / "dots" / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["producers"][0]["host"] == "x"

    con = db.connect(path)
    reading = load.from_reading(doc, b"{}", load.run_outcomes(con), load.failure_reasons(con))
    assert load.load_reading(con, tmp_path, reading)
    con.commit()
    # the failed page lands as a row under the run, page-owned by the store's own vocabulary
    assert con.execute(
        "SELECT r.pages_failed, f.page_no, f.reason, v.page_owned, f.detail"
        " FROM ocr_page_failure f JOIN ocr_run r USING (run_id)"
        " JOIN page_failure_reason_vocab v USING (reason)"
    ).fetchall() == [(1, 3, "oversize", 1, "oversize: 12.0 MP at 200 DPI")]
    con.close()

    # a second seed leaves a whole document alone — the failure was the page's
    n = pq.seed_pass(q, "dots", out)
    assert (n["whole"], n["set_aside"], n["new"]) == (1, 0, 0)
    assert written.exists()

    # a failure that was NOT the page's makes it a re-read: file set aside, pages queued anew
    q.con.execute("UPDATE job SET error = 'server: died on every attempt' WHERE state = 'failed'")
    n = pq.seed_pass(q, "dots", out)
    assert (n["whole"], n["set_aside"], n["new"]) == (0, 1, 2)
    assert not written.exists() and written.with_suffix(".json.superseded").exists()
    assert q.status()["passes"]["dots"]["pending"] == 2
    assert q.collectable("dots") == []


def test_a_reread_verdict_stands_when_the_file_is_already_gone(tmp_path):
    out = tmp_path / "ocr"
    _route_root(out, A, {1: "degraded"})
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", "dots", {**KEY, "host": "x"})
    pq.seed_pass(q, "dots", out)
    (j,) = q.claim("w1", "dots", 1, 60)
    for _ in range(2):  # the server died on it three times: a foreign failure, collected
        q.fail("w1", j["job_id"], "server: refused", final=False)
        q.claim("w1", "dots", 1, 60)
    q.fail("w1", j["job_id"], "server: refused", final=False)
    assert pq.collect_pass(q, "dots", out) == 1
    ocr_wave.shard(out / "dots", A).unlink()  # an earlier walk renamed it, then aborted
    n = pq.seed_pass(q, "dots", out)
    assert (n["set_aside"], n["new"]) == (1, 1)
    assert q.status()["passes"]["dots"]["pending"] == 1


def test_a_whole_document_whose_reading_is_gone_is_read_again_not_silenced(tmp_path):
    """A restore whose queue is NEWER than its file tree. The queue says `whole`; the reading
    document is absent. Counting it whole would silence the document for ever — nothing else
    queues it again and nothing ever collects it, which is the 2026-09-06 shape. It is re-read.
    Found by the schema critic on the ADR 0025 addendum, 2026-09-19."""
    out = tmp_path / "ocr"
    _route_root(out, A, {1: "degraded"})
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", "dots", {**KEY, "host": "x"})
    pq.seed_pass(q, "dots", out)
    (j,) = q.claim("w1", "dots", 1, 60)
    q.done("w1", j["job_id"], "[]")
    assert pq.collect_pass(q, "dots", out) == 1
    assert q.known("dots", A) == "whole"

    ocr_wave.shard(out / "dots", A).unlink()  # restored from a queue newer than the files
    n = pq.seed_pass(q, "dots", out)
    assert n["whole"] == 0, "a document with no reading document on disk is not whole"
    assert (n["set_aside"], n["new"]) == (1, 1)
    # counted apart, because nothing was partial and nothing was renamed: this number is how
    # the operator learns a restore was skewed rather than that the fleet failed a wave
    assert n["missing_reading"] == 1
    assert q.status()["passes"]["dots"]["pending"] == 1


def test_an_operators_page_owned_failure_keeps_the_document_whole(tmp_path):
    out = tmp_path / "ocr"
    _route_root(out, A, {1: "degraded", 2: "degraded"})
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", "dots", {**KEY, "host": "x"})
    pq.seed_pass(q, "dots", out)
    a, b = q.claim("w1", "dots", 2, 60)
    q.done("w1", a["job_id"], "[]")
    q.release("w1", [b["job_id"]])

    class Args:
        db, job, error, page_owned = tmp_path / "q.sqlite", b["job_id"], "kills the engine", True

    pq.cmd_fail(Args)
    assert pq.collect_pass(q, "dots", out) == 1
    assert q.known("dots", A) == "whole"
    Args.page_owned = False  # without the flag it would have been the operator's, and re-read
    row = q.con.execute("SELECT error FROM job WHERE job_id = ?", (b["job_id"],)).fetchone()
    assert row["error"].startswith("page: operator:")


def test_every_error_the_queue_writes_maps_to_a_reason_page_owned_iff_page(tmp_path):
    """ONE classifier (`ocr_wave.failure_reason`) for the store's `page_failure_reason_vocab`,
    and it must agree with the queue's `page:` rule: a page-owned reason is final in the queue
    (not retried in that pass), so a disagreement either re-reads a page for ever or files a
    transient failure as final in the queue."""
    con = db.connect(tmp_path / "s.sqlite")
    vocab = dict(con.execute("SELECT reason, page_owned FROM page_failure_reason_vocab"))
    con.close()
    assert ocr_wave.FAILURE_REASONS == vocab
    assert pq.PAGE_OWNED == ocr_wave.PAGE_OWNED == "page:"

    # `_reap`'s and `cmd_fail`'s words, produced by the code that writes them
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", "dots", {**KEY, "host": "x"})
    q.seed("dots", PAGES, reread=set())
    j = q.claim("w1", "dots", 1, 0)[0]["job_id"]
    for _ in range(2):
        time.sleep(0.01)
        q.claim("w1", "dots", 1, 0)
    time.sleep(0.01)
    q.reap()
    others = [r["job_id"] for r in q.con.execute("SELECT job_id FROM job WHERE job_id <> ?", (j,))]

    class Args:
        db, job, error, page_owned = tmp_path / "q.sqlite", others[0], "kills the engine", True

    pq.cmd_fail(Args)
    Args.job, Args.error, Args.page_owned = others[1], "held for the Mac " + "x" * 600, False
    pq.cmd_fail(Args)
    written = dict(q.con.execute("SELECT job_id, error FROM job WHERE state = 'failed'"))
    assert len(written[others[1]]) == 500  # `cmd_fail` bounds what it writes
    expected = {
        written[j]: "lease-expired",
        written[others[0]]: "operator-page",
        written[others[1]]: "operator",
        # `dots_worker.py`'s words, as its three `q.fail` calls format its exceptions
        "page: finish_reason length": "cut-answer",
        "page: oversize: 8.4 MP at 200 DPI": "oversize",
        "page: render: RuntimeError: cannot rasterise": "render",
        "page: timeout: 600s with the server healthy": "timeout",
        "server: HTTP 500": "server",
        "server: URLError: <urlopen error [Errno 111] Connection refused>": "server",
        "server: timeout 600s and the server unhealthy": "server",
        "blob: not on the node": "document-bytes",
        "blob: will not open: FileDataError: cannot open broken document": "document-bytes",
        "blob: has 3 pages, the route says 4": "document-bytes",
        "flaky": "unclassified",
        None: "unclassified",
    }
    for error, reason in expected.items():
        assert ocr_wave.failure_reason(error) == reason, error
        assert vocab[reason] == int((error or "").startswith(pq.PAGE_OWNED)), error

    # the detail: a closed shape per reason or nothing, and the loader re-checks the same shapes
    assert ocr_wave.DETAIL_SHAPES == load.DETAIL_SHAPES
    shaped = {
        "page: finish_reason length": "finish_reason length",
        "page: oversize: 8.4 MP at 200 DPI": "oversize: 8.4 MP at 200 DPI",
        "page: timeout: 600s with the server healthy": "timeout: 600s with the server healthy",
        "server: HTTP 500": "HTTP 500",
        written[j]: "lease expired on attempt 3",
    }
    for error in expected:
        entry = ocr_wave.page_failure(1, error)
        assert entry.get("detail") == shaped.get(error), error
        assert load.shaped_detail(entry["reason"], entry.get("detail")) == entry.get("detail")
    # a finish reason outside the enumeration keeps its reason and loses its words
    unlisted = ocr_wave.page_failure(1, "page: finish_reason something_new")
    assert unlisted == {"page_no": 1, "reason": "cut-answer"}
    # free text inside a shape-bearing reason is still free text
    assert "detail" not in ocr_wave.page_failure(1, "page: oversize: 8.4 MP at 200 DPI /data/x")
    assert load.shaped_detail("server", "HTTP 500 from queue-host") is None


def test_a_page_owned_failure_nobody_named_skips_only_that_document(tmp_path):
    """One unnamed `page:` word must not stall the batch: its document is left uncollected for
    a later run, and every other document is still written."""
    out = tmp_path / "ocr"
    _route_root(out, A, {1: "degraded"})
    _route_root(out, B, {1: "degraded"})
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", "dots", {**KEY, "host": "x"})
    pq.seed_pass(q, "dots", out)
    jobs = {j["document_sha256"]: j["job_id"] for j in q.claim("w1", "dots", 2, 60)}
    q.fail("w1", jobs[A], "page: a cause nobody has named", final=True)
    q.done("w1", jobs[B], "[]")
    assert pq.collect_pass(q, "dots", out) == 1
    assert not ocr_wave.shard(out / "dots", A).exists()
    assert ocr_wave.shard(out / "dots", B).exists()
    assert q.collectable("dots") == [A]  # still owed: named in the classifier, then collected


def test_the_old_drivers_file_is_whole_only_if_it_says_so(tmp_path):
    out = tmp_path / "ocr"
    _route_root(out, A, {1: "degraded"})
    _route_root(out, B, {1: "degraded"})
    ocr_wave._write(
        ocr_wave.shard(out / "dots", A), {"outcome": "read", "pages_failed": 0, "pages": []}
    )
    ocr_wave._write(ocr_wave.shard(out / "dots", B), {"outcome": "failed", "pages_failed": 1})
    ocr_wave._write(ocr_wave.shard(out / "ppocr-second", B), {"reading_role": "second"})
    q = pq.Queue(tmp_path / "q.sqlite")
    n = pq.seed_pass(q, "dots", out)
    assert (n["whole"], n["set_aside"], n["new"]) == (1, 1, 1)
    assert ocr_wave.shard(out / "dots", A).exists()
    assert not ocr_wave.shard(out / "dots", B).exists()
    assert not ocr_wave.shard(out / "ppocr-second", B).exists()  # measured against old text


# --- the tabular pass: HunyuanOCR-1.5 at 150 DPI (ocr-plan.md decision 6) ------------------------

TAB = pq.PASSES["tabular"]["key"]
hw = _module("hunyuan_worker", ROOT / "tools" / "fleet" / "hunyuan_worker.py")
TABLE_RAW = (
    "# Rate schedule\n\n"
    "<table><tr><th>Commodity</th><th>Rate</th></tr><tr><td>Coal</td><td>1.25</td></tr></table>"
    "\n\nIssued 2026"
)
TABLE_TEXT = "# Rate schedule\n[table]\nCommodity\tRate\nCoal\t1.25\n[end table]\nIssued 2026"


def test_seeding_tabular_queues_only_the_tabular_pages(tmp_path):
    out = tmp_path / "ocr"
    _route_root(out, A, {1: "tabular", 2: "degraded", 3: "tabular", 4: "clean"})
    _route_root(out, B, {1: "degraded", 2: "graphic"})
    q = pq.Queue(tmp_path / "q.sqlite")
    n = pq.seed_pass(q, "tabular", out)
    assert (n["documents"], n["pages"], n["new"]) == (1, 2, 2)
    rows = q.con.execute("SELECT pass, document_sha256, page_no FROM job ORDER BY page_no")
    assert [tuple(r) for r in rows] == [("tabular", A, 1), ("tabular", A, 3)]
    assert set(q.status()["passes"]) == {"tabular"}  # nothing queued for dots


def test_the_tabular_pass_refuses_any_other_key(tmp_path):
    q = pq.Queue(tmp_path / "q.sqlite")
    with pytest.raises(pq.KeyMismatch):
        q.register("w", "tabular", {**KEY, "host": "x"})  # a dots worker
    with pytest.raises(pq.KeyMismatch):
        q.register("w", "tabular", {**TAB, "render_profile": "200", "host": "x"})
    with pytest.raises(pq.KeyMismatch):
        q.register("w", "dots", {**TAB, "host": "x"})
    q.register("w", "tabular", {**TAB, "host": "x", "engine": "transformers"})


def test_collect_tabular_writes_a_reading_the_loader_takes(tmp_path):
    path, sha = _store_with_document(tmp_path)
    out = tmp_path / "ocr"
    _route_root(out, sha, {1: "clean", 2: "tabular", 3: "tabular"})
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", "tabular", {**TAB, "host": "x"})
    assert pq.seed_pass(q, "tabular", out)["new"] == 2
    a, b = q.claim("w1", "tabular", 2, 60)
    q.done("w1", a["job_id"], TABLE_RAW)
    q.fail("w1", b["job_id"], "page: finish_reason length", final=True)
    assert pq.collect_pass(q, "dots", out) == 0  # another pass's collect does not take it
    assert pq.collect_pass(q, "tabular", out) == 1
    doc = json.loads(ocr_wave.shard(out / "hunyuan-tabular", sha).read_text(encoding="utf-8"))
    assert (doc["method"], doc["method_version"], doc["render_profile"]) == (
        "hunyuan-ocr",
        "1.5",
        "150",
    )
    assert (doc["reading_role"], doc["payload_kind"]) == ("primary", "hunyuan-ocr.json")
    assert doc["outcome"] == "read" and doc["pages_failed"] == 1
    assert doc["pages"] == [
        {
            "page_no": 2,
            "text": TABLE_TEXT,
            "member": "engine/pages/0",
            "route": ocr_wave.route_of("tabular"),
        }
    ]
    assert doc["engine"]["pages"] == [{"page_no": 2, "raw": TABLE_RAW}]  # the answer, whole
    manifest = json.loads((out / "hunyuan-tabular" / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["pass"] == "tabular" and manifest["key"] == TAB

    con = db.connect(path)
    reading = load.from_reading(doc, b"{}", load.run_outcomes(con), load.failure_reasons(con))
    assert load.load_reading(con, tmp_path, reading)
    con.commit()
    # the cut answer lands as main's per-page failure row, in the classifier's own words
    assert con.execute(
        "SELECT f.page_no, f.reason, v.page_owned, f.detail FROM ocr_page_failure f"
        " JOIN page_failure_reason_vocab v USING (reason)"
    ).fetchall() == [(3, "cut-answer", 1, "finish_reason length")]
    con.close()
    assert pq.seed_pass(q, "tabular", out)["whole"] == 1  # the failure was the page's


def test_hunyuan_page_flattens_tables_and_keeps_the_answer_whole():
    assert ocr_wave.hunyuan_page(2, TABLE_RAW) == ({"page_no": 2, "raw": TABLE_RAW}, TABLE_TEXT)
    prose = "Decided: September 1, 2026\n\nBy the Board.\n"
    assert ocr_wave.hunyuan_page(1, prose) == (
        {"page_no": 1, "raw": prose},
        "Decided: September 1, 2026\n\nBy the Board.",
    )
    # collect writes what was posted; the worker never posts '' (the next test)
    assert ocr_wave.hunyuan_page(3, "") == ({"page_no": 3, "raw": ""}, "")


def test_an_empty_answer_is_refused_and_never_posted_as_done(q):
    """A tabular page has a table on it: '' is the model failing, not a blank page. Posted as
    done, collect would write `read` with no text and the next seed would call it whole."""
    a, b = q.claim("w1", "dots", 2, 60)
    assert hw.post_answer(q, "w1", a["job_id"], " \n") == "empty"
    row = q.con.execute(
        "SELECT state, attempts, error FROM job WHERE job_id = ?", (a["job_id"],)
    ).fetchone()
    assert (row["state"], row["attempts"], row["error"]) == ("pending", 1, hw.EMPTY_ANSWER)
    assert not row["error"].startswith(pq.PAGE_OWNED)
    assert q.con.execute("SELECT COUNT(*) FROM result").fetchone()[0] == 0
    assert hw.post_answer(q, "w1", b["job_id"], TABLE_RAW) == "done"
    assert hw.post_answer(q, "w1", b["job_id"], TABLE_RAW) == "lost"  # no longer leased


def test_a_generation_that_spends_every_token_without_eos_is_cut():
    assert hw.generation_failure(4096, 4096, False) == "finish_reason length"
    assert hw.generation_failure(4096, 4096, True) is None  # ended exactly at the budget
    assert hw.generation_failure(812, 4096, True) is None


class _OOM(Exception):
    pass


def test_out_of_memory_retries_once_with_the_cache_emptied_then_is_the_cards():
    def is_oom(e):
        return isinstance(e, _OOM)

    calls, emptied = [], []

    def once_then_ok():
        calls.append(1)
        if len(calls) == 1:
            raise _OOM
        return "answer"

    assert hw.read_with_oom_retry(once_then_ok, is_oom, lambda: emptied.append(1)) == "answer"
    assert (len(calls), len(emptied)) == (2, 1)

    def always():
        raise _OOM

    with pytest.raises(hw.GpuOutOfMemory):  # the card's, never PageFailed
        hw.read_with_oom_retry(always, is_oom, lambda: None)

    def broken():
        raise ValueError("not memory")

    with pytest.raises(ValueError):  # not an OOM: the engine's, handled by the loop
        hw.read_with_oom_retry(broken, is_oom, lambda: None)

    # two OOMs on the same page is still that page's retry; on a different page, the card
    assert not hw.card_at_fault(None, (A, 1))
    assert not hw.card_at_fault((A, 1), (A, 1))
    assert hw.card_at_fault((A, 1), (A, 2))


@pytest.mark.parametrize("error", ["gpu: oom", "engine: RuntimeError: CUDA error"])
def test_a_page_given_back_keeps_its_attempt_spent_and_is_not_the_pages_own(q, error):
    """The engine raising on a page, or the card running out of memory on it: the page in
    flight spends its attempt (claimed first again, it would otherwise loop for ever), the
    pages after it do not, and after max_attempts the document is re-read, never whole."""
    ids = [j["job_id"] for j in q.claim("w1", "dots", 3, 60)]  # A p1, A p2, B p1
    hw.give_back(q, "w1", ids, 0, error)
    attempts = dict(q.con.execute("SELECT job_id, attempts FROM job WHERE state = 'pending'"))
    assert attempts == {ids[0]: 1, ids[1]: 0, ids[2]: 0}
    for _ in range(2):
        (again,) = q.claim("w1", "dots", 1, 60)
        assert again["job_id"] == ids[0]  # first in claim order, attempt by attempt
        hw.give_back(q, "w1", [again["job_id"]], 0, error)
    row = q.con.execute("SELECT state, error FROM job WHERE job_id = ?", (ids[0],)).fetchone()
    assert (row["state"], row["error"]) == ("failed", error)
    assert not row["error"].startswith(pq.PAGE_OWNED)
    a2 = q.claim("w1", "dots", 1, 60)[0]["job_id"]
    q.done("w1", a2, "[]")
    q.mark_collected(
        "dots", A, {"ran_at": "t", "outcome": "read", "pages": [{}], "pages_failed": 1}
    )
    assert q.known("dots", A) == "reread"


def test_a_card_short_of_memory_claims_nothing(q):
    free, need = 1 * hw.GIB, hw.MIN_HEADROOM
    assert hw.short_of_memory(free, 0, 0, need)
    assert hw.short_of_memory(free, 2 * hw.GIB, 1 * hw.GIB, need) is None  # its own cache counts
    assert hw.short_of_memory(8 * hw.GIB, 0, 0, hw.MIN_FREE_TO_LOAD) is None
    jobs, why = hw.claim_if_room(q, "w1", 4, 60, lambda: (free, 0, 0))
    assert jobs is None and "GiB" in why
    assert q.claimable("tabular") == 0 and q.claimable("dots") == 3  # nothing leased
    q.seed("tabular", [(A, 1)], reread=set())
    q.register("w1", "tabular", {**TAB, "host": "x"})
    jobs, why = hw.claim_if_room(q, "w1", 4, 60, lambda: (8 * hw.GIB, 0, 0))
    assert why is None and [j["page_no"] for j in jobs] == [1]


def test_the_weights_revision_is_the_loaded_hash_else_the_caches_ref(tmp_path):
    assert hw.weights_revision("tencent/HunyuanOCR", "abc", tmp_path) == "abc"
    assert hw.weights_revision("tencent/HunyuanOCR", None, tmp_path) is None
    ref = tmp_path / "models--tencent--HunyuanOCR" / "refs" / "main"
    ref.parent.mkdir(parents=True)
    ref.write_text("47644ecc4fc854efa4f505155158831f36773ee4\n", encoding="utf-8")
    rev = hw.weights_revision("tencent/HunyuanOCR", None, tmp_path)
    assert rev == "47644ecc4fc854efa4f505155158831f36773ee4"


# --- the transport: the same promises through queue_server.py and RemoteQueue -----------------

import socket  # noqa: E402
import threading  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

qs = _module("queue_server", ROOT / "tools" / "fleet" / "queue_server.py")
TOKEN = "t" * 40


@pytest.fixture
def remote(tmp_path):
    db = tmp_path / "q.sqlite"
    local = pq.Queue(db)
    local.seed("dots", PAGES, reread=set())
    blobs = tmp_path / "blobs"
    (blobs / "aa").mkdir(parents=True)
    (blobs / "aa" / A).write_bytes(b"%PDF-1.4 fake")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    t = threading.Thread(target=qs.serve, args=(db, blobs, TOKEN, port, "127.0.0.1"), daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/nothing", timeout=1)
        except urllib.error.HTTPError:
            break
        except urllib.error.URLError:
            time.sleep(0.05)
    yield pq.RemoteQueue(url, TOKEN), local
    local.con.close()


def test_the_transport_carries_the_lease(remote):
    r, local = remote
    r.register("far/dots", "dots", {**KEY, "host": "far"})
    with pytest.raises(pq.KeyMismatch):
        r.register("bad", "dots", {**KEY, "render_profile": "150"})
    jobs = r.claim("far/dots", "dots", 2, 60)
    assert [j["page_no"] for j in jobs] == [1, 2]
    r.extend("far/dots", [jobs[1]["job_id"]], 120)
    assert r.done("far/dots", jobs[0]["job_id"], "[]") is True
    with pytest.raises(ValueError):
        r.fail("far/dots", jobs[1]["job_id"], "server: x", final=True)
    r.fail("far/dots", jobs[1]["job_id"], "page: cut", final=True)
    r.release("far/dots", [])
    s = local.status()
    assert (s["passes"]["dots"]["done"], s["passes"]["dots"]["failed"]) == (1, 1)
    assert s["workers"][0]["producer"]["host"] == "far"
    assert r.blob(A) == b"%PDF-1.4 fake"
    with pytest.raises(urllib.error.HTTPError) as e:
        r.blob(B)
    assert e.value.code == 404


# --- how a reader is told to stop (ADR 0025 addendum, proposal 1) -----------------------------

stopping_mod = _module("stopping", ROOT / "tools" / "fleet" / "stopping.py")


@pytest.fixture(autouse=True)
def _restore_signal_handlers():
    """`Stop.install()` replaces this process's handlers, and a test that left them installed
    would break Ctrl-C for the rest of the run — a flag set on a discarded object, and pytest
    never interrupted. Every test in this file gets its handlers put back."""
    import signal as signal_mod

    saved = {
        s: signal_mod.getsignal(s)
        for s in (signal_mod.SIGTERM, signal_mod.SIGINT)
        if hasattr(signal_mod, s.name)
    }
    yield
    for sig, handler in saved.items():
        if handler is not None:
            signal_mod.signal(sig, handler)


def test_a_signal_stops_a_reader_the_way_the_stop_file_does(tmp_path):
    """jobd preempts by signalling the scope. The reader must yield the same way it yields to
    the stop file — before the next page, releasing what is unspent."""
    import signal as signal_mod

    s = stopping_mod.Stop(tmp_path / "nothing")
    assert s() is False
    s._catch(signal_mod.SIGTERM, None)
    assert s() is True
    assert "SIGTERM" in s.why("3 pages released unspent")
    assert s.signal_name == "SIGTERM"
    # a second SIGTERM changes nothing — the first named who stopped us. (A second SIGINT is
    # different on purpose: it is the operator's escape hatch, tested below.)
    s._catch(signal_mod.SIGTERM, None)
    assert s.signal_name == "SIGTERM", "the first signal wins"


def test_a_signal_does_not_latch_but_the_stop_file_does(tmp_path):
    """THE distinction. The stop file is a latch a person clears — a reader that starts while
    it exists reads nothing. A preempt means 'not now, on this machine', so it must leave
    nothing behind: writing a stop file on a signal would take the pass down until a human
    noticed. The flag lives in the process and dies with it."""
    flag = tmp_path / ".stop-tabular"
    s = stopping_mod.Stop(flag).install()
    s._catch(__import__("signal").SIGTERM, None)
    assert s() is True
    assert not flag.exists(), "a signal must never write the operator's latch"
    assert stopping_mod.Stop(flag)() is False, "the next placement reads normally"

    flag.write_text("")
    assert stopping_mod.Stop(flag)() is True, "the operator's latch does survive"


def test_the_grace_budget_is_read_from_the_broker_not_assumed(monkeypatch):
    """`JOBD_CHECKPOINT_GRACE_S` is the budget before SIGKILL. A bad value must not stop a
    reader yielding — only stop it knowing how long it had."""
    monkeypatch.setenv("JOBD_CHECKPOINT_GRACE_S", "25")
    assert stopping_mod.grace_seconds() == 25.0
    for bad in ("", "   ", "soon", "-5", "0"):
        monkeypatch.setenv("JOBD_CHECKPOINT_GRACE_S", bad)
        assert stopping_mod.grace_seconds() == stopping_mod.DEFAULT_GRACE_S
    monkeypatch.delenv("JOBD_CHECKPOINT_GRACE_S")
    assert stopping_mod.grace_seconds() == stopping_mod.DEFAULT_GRACE_S


def test_the_clean_yield_is_announced_only_when_a_signal_caused_it(tmp_path, capsys):
    """`jobd-checkpoint-complete` tells the broker the yield was tidy. The stop file is not a
    broker, so it says nothing there."""
    flag = tmp_path / ".stop"
    flag.write_text("")
    stopping_mod.Stop(flag).checkpoint_complete()
    assert capsys.readouterr().out == ""

    s = stopping_mod.Stop(tmp_path / "nothing")
    s._catch(__import__("signal").SIGTERM, None)
    s.checkpoint_complete()
    assert stopping_mod.CHECKPOINT_COMPLETE in capsys.readouterr().out


def test_the_yield_refunds_the_attempt_and_says_so(q, capsys):
    """The yield against a REAL queue, since this is the one place every branch of both loops
    releases. A stop is nobody's fault, so a page given back here costs nothing: it returns to
    `pending` with its attempt refunded, and the broker is told the yield was tidy."""
    import signal as signal_mod

    q.register("w1", "dots", {**KEY, "host": "x"})
    jobs = q.claim("w1", "dots", 2, 60)
    ids = [j["job_id"] for j in jobs]
    assert q.status()["passes"]["dots"]["leased"] == 2

    s = stopping_mod.Stop(None)
    s._catch(signal_mod.SIGTERM, None)
    lines = []
    assert stopping_mod.yield_now(q, "w1", ids, 0, s, lines.append) == 0

    state = q.status()["passes"]["dots"]
    assert (state["leased"], state["pending"]) == (0, len(PAGES))
    row = q.con.execute("SELECT attempts FROM job WHERE job_id = ?", (ids[0],)).fetchone()
    assert row["attempts"] == 0, "a stop must not spend the page's attempt"
    assert "SIGTERM" in lines[0] and "2 pages released unspent" in lines[0]
    assert stopping_mod.CHECKPOINT_COMPLETE in capsys.readouterr().out


def test_the_yield_tells_the_broker_only_after_the_pages_are_back(q, capsys):
    """Ordering matters: `jobd-checkpoint-complete` claims the yield was clean, so it must not
    be printed when the release itself failed."""
    import signal as signal_mod

    class Refuses:
        def release(self, *a):
            raise RuntimeError("the coordinator is gone")

    s = stopping_mod.Stop(None)
    s._catch(signal_mod.SIGTERM, None)
    with pytest.raises(RuntimeError):
        stopping_mod.yield_now(Refuses(), "w1", [1, 2], 0, s, lambda _: None)
    assert stopping_mod.CHECKPOINT_COMPLETE not in capsys.readouterr().out


def test_a_second_ctrl_c_still_kills(tmp_path):
    """The first Ctrl-C asks for a clean yield, which waits for the page in flight. The second
    is the operator's escape hatch from a page that will not end, and must not be swallowed."""
    import signal as signal_mod

    s = stopping_mod.Stop(tmp_path / "nothing").install()
    s._catch(signal_mod.SIGINT, None)
    assert s() is True
    # the second press must both restore the default AND be delivered — restoring alone leaves
    # this press consumed, so the operator would need a third
    with pytest.raises(KeyboardInterrupt):
        s._catch(signal_mod.SIGINT, None)
    # Python's own default, not SIG_DFL: SIG_DFL terminates the process unwinding nothing
    assert signal_mod.getsignal(signal_mod.SIGINT) is signal_mod.default_int_handler


def test_install_really_installs(tmp_path):
    """Every other test drives `_catch` directly. If `install()` ever swallowed a real failure
    the suite would stay green while no reader honoured a signal, so prove the handler is on
    the signal — and on POSIX, prove delivery."""
    import os
    import signal as signal_mod

    s = stopping_mod.Stop(tmp_path / "nothing").install()
    handler = signal_mod.getsignal(signal_mod.SIGTERM)
    # `s._catch` builds a fresh bound method on every access, so compare what it is bound to
    assert getattr(handler, "__self__", None) is s
    assert getattr(handler, "__func__", None) is type(s)._catch
    if os.name == "posix":
        os.kill(os.getpid(), signal_mod.SIGTERM)
        assert s() is True and s.signal_name == "SIGTERM"


def test_both_lease_loops_honour_the_signal(tmp_path):
    """The loops are duplicated deliberately, so a rule must land in both. Neither may keep
    its own stop-file-only predicate, and every branch that can be interrupted mid-page must
    yield rather than blame the page — `PageFailed` in dots is the one that failed FINALLY."""
    import re

    for name in ("dots_worker.py", "hunyuan_worker.py"):
        src = (ROOT / "tools" / "fleet" / name).read_text(encoding="utf-8")
        assert "from stopping import Stop, yield_now" in src, name
        assert "Stop(args.stop_file).install()" in src, name
        assert not re.search(r"def stopping\(\)", src), f"{name} still has its own predicate"
        # the guard before the claim, and a yield from a mid-page branch
        assert src.count("stopping()") >= 3, f"{name} checks the stop in too few places"
        assert "yield_now(" in src, name
    dots = (ROOT / "tools" / "fleet" / "dots_worker.py").read_text(encoding="utf-8")
    page_failed = dots.split("except PageFailed as e:")[1].split("except ")[0]
    assert "stopping()" in page_failed, "a stop must not be recorded as a cut page"


# --- backing the coordinator up (ADR 0025 addendum, proposal 3) -------------------------------

backup = _module("backup", ROOT / "tools" / "fleet" / "backup.py")


def test_the_queue_is_snapshotted_soundly_while_it_is_being_written(tmp_path):
    """`queue_server.py` serves the queue while this runs, so the copy is taken through
    SQLite's backup API rather than `cp`. A writer is kept busy throughout to prove the copy
    is a faithful image of one instant and not a torn file."""
    import sqlite3 as sq
    import threading

    src = tmp_path / "queue.sqlite"
    q = pq.Queue(src)
    q.seed("dots", PAGES, reread=set())
    q.register("w1", "dots", {**KEY, "host": "x"})

    stop = threading.Event()

    def churn():
        con = sq.connect(src, timeout=60)
        con.execute("PRAGMA busy_timeout=60000")
        n = 0
        while not stop.is_set():
            con.execute("UPDATE worker SET last_seen = ? WHERE name = 'w1'", (f"t{n}",))
            con.commit()
            n += 1
        con.close()

    writer = threading.Thread(target=churn, daemon=True)
    writer.start()
    try:
        facts = backup.snapshot_queue(src, tmp_path / "copy.sqlite", min_jobs=1)
    finally:
        stop.set()
        writer.join(timeout=5)

    assert facts["integrity"] == "ok"
    assert facts["counts"]["job"] == len(PAGES)
    assert facts["job_states"]["pending"] == len(PAGES)
    assert "worker" in facts["counts"], "tables are enumerated, not hardcoded"
    q.con.close()


def test_a_suspiciously_empty_queue_is_refused_rather_than_called_a_backup(tmp_path):
    src = tmp_path / "queue.sqlite"
    q = pq.Queue(src)
    q.seed("dots", PAGES, reread=set())
    with pytest.raises(ValueError, match="under the floor"):
        backup.snapshot_queue(src, tmp_path / "copy.sqlite", min_jobs=len(PAGES) + 1)
    q.con.close()


def test_a_new_root_is_backed_up_without_anyone_editing_the_tool(tmp_path):
    """THE REASON IT IS A DENY-LIST. An allow-list of known roots would omit the next pass
    from every backup with no warning and a zero exit."""
    ocr = tmp_path / "ocr"
    (ocr / "route" / "aa").mkdir(parents=True)
    (ocr / "route" / "aa" / "x.json").write_text("{}")
    (ocr / "a-pass-nobody-has-written-yet" / "bb").mkdir(parents=True)
    (ocr / "a-pass-nobody-has-written-yet" / "bb" / "y.json").write_text("{}")
    (ocr / "blobs").mkdir()
    (ocr / "ppocr-cache").mkdir()
    (ocr / "loose.csv").write_text("x")
    snap = tmp_path / "queue.sqlite"
    snap.write_bytes(b"not really a database")

    built = backup.build_tarball(tmp_path, snap, tmp_path / "out.tar.gz")
    taken = {r["root"] for r in built["roots"]}
    assert "a-pass-nobody-has-written-yet" in taken
    skipped = {s["name"] for s in built["skipped"]}
    assert {"blobs", "ppocr-cache"} <= skipped, "and every omission is NAMED"
    # a loose file falls on the side of keeping too — the re-read's page list is one, and it
    # decides what that pass owes
    assert "loose.csv" in built["loose_files"]


def test_the_queues_own_files_are_refused_because_the_snapshot_is_the_queue(tmp_path):
    """A stale `-wal` beside the snapshot would describe a different instant from the copy the
    backup actually took."""
    ocr = tmp_path / "ocr"
    ocr.mkdir(parents=True)
    for name in ("queue.sqlite", "queue.sqlite-wal", "queue.sqlite-shm"):
        (ocr / name).write_text("x")
    snap = tmp_path / "queue.sqlite"
    snap.write_bytes(b"x")

    built = backup.build_tarball(tmp_path, snap, tmp_path / "out.tar.gz")
    assert built["loose_files"] == []
    refused = {s["name"] for s in built["skipped"] if "snapshotted instead" in s["why"]}
    assert refused == {"queue.sqlite", "queue.sqlite-wal", "queue.sqlite-shm"}


def test_the_manifest_counts_what_the_archive_holds(tmp_path):
    """Counted inside the loop that adds, so the number is true by construction. A separate
    walk could disagree with the archive and nothing would ever notice."""
    ocr = tmp_path / "ocr"
    (ocr / "route" / "aa").mkdir(parents=True)
    for i in range(7):
        (ocr / "route" / "aa" / f"{i}.json").write_text("{}")
    snap = tmp_path / "queue.sqlite"
    snap.write_bytes(b"x")
    out = tmp_path / "out.tar.gz"
    built = backup.build_tarball(tmp_path, snap, out)

    import tarfile as tf

    with tf.open(out) as tar:
        members = [m.name for m in tar.getmembers() if m.isfile()]
    assert built["files"] == len(members) == 8  # 7 readings + the queue


def test_the_queue_is_the_last_thing_in_the_archive(tmp_path):
    """The documented restore order is files before the queue, because a queue newer than its
    file tree makes the seed count documents whole with no reading on disk. The archive
    carries that order; a tidy-up that moved this would invert it silently."""
    ocr = tmp_path / "ocr"
    (ocr / "route" / "aa").mkdir(parents=True)
    (ocr / "route" / "aa" / "x.json").write_text("{}")
    snap = tmp_path / "queue.sqlite"
    snap.write_bytes(b"x")
    out = tmp_path / "out.tar.gz"
    backup.build_tarball(tmp_path, snap, out)

    import tarfile as tf

    with tf.open(out) as tar:
        names = [m.name for m in tar.getmembers() if m.isfile()]
    assert names[-1] == "ocr/queue.sqlite"


def test_a_stored_object_is_checked_by_checksum_not_only_by_size():
    """Two files of the same length pass a size check. `ChecksumMode=ENABLED` puts the store's
    own digest in the response, so there is no reason to accept the weaker test."""
    import base64 as b64

    digest = "ab" * 32
    good = b64.b64encode(bytes.fromhex(digest)).decode()
    assert backup.verify({"ContentLength": 10, "ChecksumSHA256": good}, 10, digest) is None
    assert "wrong size" in backup.verify({"ContentLength": 9, "ChecksumSHA256": good}, 10, digest)
    other = b64.b64encode(bytes.fromhex("cd" * 32)).decode()
    assert "wrong checksum" in backup.verify(
        {"ContentLength": 10, "ChecksumSHA256": other}, 10, digest
    )
    assert "no SHA-256" in backup.verify({"ContentLength": 10}, 10, digest)


# --- asking for a reader when one is owed (ADR 0025 addendum, proposal 2) ---------------------

resubmit = _module("resubmit", ROOT / "tools" / "fleet" / "resubmit.py")


def _status(owed: int, workers=()):
    return {"passes": {"dots": {"claimable": owed, "leased": 0}}, "workers": list(workers)}


def _decide(status, live=(), terminal=(), idle_for=900):
    return resubmit.decide(status, "dots", idle_for, list(live), list(terminal), 120.0, 3)


def test_a_reader_is_asked_for_only_when_pages_are_owed_and_nobody_is_reading():
    go, why = _decide(_status(12))
    assert go is True and "12 owed" in why

    go, why = _decide(_status(0))
    assert go is False and "nothing claimable" in why, "a drained queue is not relaunched"


def test_pages_leased_to_a_dead_reader_still_count_as_owed():
    """`claimable`, not `pending`: a reader killed after its grace leaves its batch leased for
    up to the lease, and those pages are claimable now because a claim reaps first. Gating on
    `pending` would idle the pass for 45 minutes at the end of a wave."""
    leased_only = {"passes": {"dots": {"pending": 0, "claimable": 4}}, "workers": []}
    go, _ = _decide(leased_only)
    assert go is True


def test_a_job_the_broker_still_holds_stops_a_second_one():
    go, why = _decide(_status(12), live=[{"id": 77, "state": "running", "cmd": ["x"]}])
    assert go is False and "broker holds 1 job" in why and "77" in why


def test_a_reader_the_broker_never_started_also_stops_one():
    """THE SECOND QUESTION. `fleet-up.sh`'s restart loop can run a reader the broker knows
    nothing about, and asking only the broker would put a second one on the same pass."""
    holding = {"name": "far/dots", "pass": "dots", "last_seen_age_seconds": 20, "holding": 4}
    assert _decide(_status(12))[0] is True, "nothing reading yet"
    go, why = _decide(_status(12, [holding]))
    assert go is False and "far/dots" in why and "double up" in why


def test_a_worker_that_yielded_its_pages_is_not_reading():
    """A yield releases everything, so `holding` drops to 0 — and the next tick must submit at
    once rather than wait out `--idle-for`. Holding is what separates working from gone."""
    yielded = {"name": "far/dots", "pass": "dots", "last_seen_age_seconds": 5, "holding": 0}
    go, _ = _decide(_status(12, [yielded]))
    assert go is True

    slow = {"name": "far/dots", "pass": "dots", "last_seen_age_seconds": 610, "holding": 4}
    go, _ = _decide(_status(12, [slow]))
    assert go is False, "a reader on a page longer than the 600s timeout is still reading"


def test_another_passs_reader_does_not_hold_this_pass_back():
    other = {"name": "far/tabular", "pass": "tabular", "last_seen_age_seconds": 5, "holding": 4}
    assert _decide(_status(12, [other]))[0] is True
    # and the same on the broker's side: a tabular job must not block a dots submission
    tabular_job = {"id": 9, "state": "running", "cmd": ["python", "hunyuan_worker.py", "tabular"]}
    assert resubmit.for_pass(tabular_job, "dots") is False
    assert resubmit.for_pass(tabular_job, "tabular") is True


def test_a_job_whose_command_cannot_be_read_counts_as_ours():
    """Waiting behind another pass's reader is cheaper than putting a second one on this one."""
    assert resubmit.for_pass({"id": 1, "cmd": None}, "dots") is True
    assert resubmit.for_pass({"id": 1, "cmd": ["something", "opaque"]}, "dots") is True


def test_a_reader_dying_on_arrival_stops_the_next_submission():
    """A reader that exits in seconds goes terminal at once, so the next tick would see nothing
    running and submit again — for ever, with no signal. ADR 0025 addendum: the resubmitter
    owns every exit, not only a preempt."""
    quick = [
        {
            "id": i,
            "state": "failed",
            "cmd": ["dots_worker.py"],
            "started_at": "2026-09-19T10:00:00+00:00",
            "finished_at": "2026-09-19T10:00:09+00:00",
        }
        for i in range(3)
    ]
    go, why = _decide(_status(12), terminal=quick)
    assert go is False and "died inside" in why

    healthy = [{**quick[0], "finished_at": "2026-09-19T18:00:00+00:00"}, *quick[1:]]
    go, _ = _decide(_status(12), terminal=healthy)
    assert go is True, "one long run breaks the streak"


def test_a_pass_the_queue_does_not_know_is_refused_not_assumed_empty():
    go, why = _decide({"passes": {}, "workers": []})
    assert go is False and "no pass" in why


def test_an_unrecognised_job_state_counts_as_live_not_finished():
    """`assigned` was exactly this — a reader dispatched but not yet started. Asking only for
    the states this file knows would make a new one invisible, and invisible means 'submit'."""
    assert "assigned" not in resubmit.TERMINAL
    assert {"completed", "failed", "cancelled", "preempted", "orphaned"} <= resubmit.TERMINAL
    assert "something_jobd_adds_later" not in resubmit.TERMINAL


def test_claimable_counts_what_a_claim_could_lease_now(q):
    """The gate asks this before it loads a model (2026-09-11: an empty queue cost 222 worker
    launches in 37 minutes). A live lease is not claimable; an expired one is, while it has an
    attempt left; a page out of attempts never is."""
    assert q.claimable("dots") == 3
    [job] = q.claim("w1", "dots", 1, 60)
    assert q.claimable("dots") == 2
    q.con.execute("UPDATE job SET lease_until = 0 WHERE job_id = ?", (job["job_id"],))
    assert q.claimable("dots") == 3  # the reap a claim runs first would return it
    q.con.execute("UPDATE job SET attempts = max_attempts WHERE job_id = ?", (job["job_id"],))
    assert q.claimable("dots") == 2


def test_the_transport_answers_what_is_claimable(remote):
    r, _ = remote
    assert r.claimable("dots") == 3
    req = urllib.request.Request(
        r.url + "/pending?pass=nope", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 400  # a pass the queue does not know is refused, not zero
    with pytest.raises(urllib.error.HTTPError) as e:
        pq.RemoteQueue(r.url, "x" * 40).claimable("dots")
    assert e.value.code == 401


def test_the_transport_refuses_a_bad_token(remote):
    r, _ = remote
    bad = pq.RemoteQueue(r.url, "x" * 40)
    with pytest.raises(urllib.error.HTTPError) as e:
        bad.claim("w", "dots", 1, 60)
    assert e.value.code == 401
    with pytest.raises(urllib.error.HTTPError) as e:
        bad.blob(A)
    assert e.value.code == 401


def test_a_page_number_outside_the_document_is_the_documents_failure_at_both_ends():
    """Copilot on PR #34, 2026-09-17: page 0 passed the upper-bound check and `doc[0 - 1]`
    would have read the LAST page, silently."""
    assert hw.page_index(1, 3) == 0 and hw.page_index(3, 3) == 2
    for no in (0, -1, 4):
        with pytest.raises(hw.DocumentFailed, match="has 3 pages, the route says"):
            hw.page_index(no, 3)


def test_a_queue_that_refuses_registration_is_the_environments_exit():
    """Copilot on PR #34, 2026-09-17: a locked queue, an HTTP error or a key mismatch at
    register crashed the worker with an unclassified exit code."""

    class Refusing:
        def register(self, name, pass_, producer):
            raise RuntimeError("database is locked")

    class Accepting:
        def register(self, name, pass_, producer):
            self.got = (name, pass_, producer)

    assert hw.register_or_exit(Refusing(), "w1", "tabular", {}) == hw.EXIT_ENVIRONMENT
    q = Accepting()
    assert hw.register_or_exit(q, "w1", "tabular", {"k": 1}) is None
    assert q.got == ("w1", "tabular", {"k": 1})


# --- the text-layer re-read: a pass seeded from a page list, over separately routed pages ----


def _page_list(path: Path, rows: list[tuple[str, int, str]]) -> Path:
    """The queue builder's shape (tools/rmi-ai-machine/text_quality_queue.py): a header, then
    a row per page. Only `sha`, `page` and the flag column matter to the seed."""
    import csv as _csv

    with path.open("w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["text_id", "sha", "page", "score", "prose"])
        for i, (sha, page, prose) in enumerate(rows):
            w.writerow([1000 + i, sha, page, "0.21", prose])
    return path


def _reread_route(out: Path, sha: str, classes: dict[int, str], version: str = "provisional-1"):
    """`ocr_wave.py route-list`'s output: the re-read's own route root, apart from the wave's."""
    doc = {
        "document_sha256": sha,
        "method": ocr_wave.ROUTER,
        "method_version": version,
        "pages": {str(n): {"class": c} for n, c in classes.items()},
    }
    ocr_wave._write(ocr_wave.shard(out / ocr_wave.ROOTS["reread_route"], sha), doc)


def _zero() -> dict:
    return {
        "documents": 0,
        "pages": 0,
        "whole": 0,
        "set_aside": 0,
        "new": 0,
        "missing_reading": 0,
        "listed_pages": 0,
        "topped_up": 0,
        "unrouted_documents": 0,
        "unrouted_pages": 0,
    }


@pytest.fixture
def listed(monkeypatch):
    """`reread` under another root, so a test's files never collide with a real one's."""
    spec = {**pq.PASSES["reread"], "root": "listed-test"}
    monkeypatch.setitem(pq.PASSES, "listed", spec)
    monkeypatch.setitem(ocr_wave.ROOTS, "listed-test", "listed-test")
    return "listed"


def test_the_loader_refuses_an_ocr_reading_whose_page_names_no_route():
    """WHY THE RE-READ'S PAGES ARE ROUTED FIRST (schema-critic and /code-review, 2026-09-18).
    The first design gave a re-read page no route, since the router never saw it — but an `ocr`
    reading whose page names no routed class is refused by the loader (ADR 0021 D4) and by
    `document_text`'s own CHECK, so every page read would have been thrown away. Proved through
    the loader; the first version of this test built `load.Page(...)` by hand and so skipped the
    validation it looked like it was making."""
    doc = ocr_wave.reading_document(
        A,
        pq.PASSES["reread"]["key"],
        "second",
        "dots.mocr.json",
        [{"blocks": [{"text": "re-read prose"}]}],
        [{"page_no": 4, "text": "re-read prose", "member": "engine/pages/0"}],  # no route
        page_failures=[],
    )
    assert doc["reading_channel"] == "ocr" and doc["reading_role"] == "second"
    with pytest.raises(load.Unreadable, match="names the class it was routed as"):
        load.from_reading(doc, b"{}", {"read": 1}, {})


def test_a_pass_whose_pages_are_not_routed_refuses_to_seed(monkeypatch, tmp_path):
    """The guard that fires before any machine time is spent, rather than at the loader hours
    later and per document."""
    monkeypatch.setitem(pq.PASSES, "unrouted-test", {**pq.PASSES["reread"], "route_root": None})
    q = pq.Queue(tmp_path / "q.sqlite")
    lst = _page_list(tmp_path / "p.csv", [(A, 1, "1")])
    with pytest.raises(pq.Unloadable, match="ADR 0021 D4"):
        pq.seed_from_list(q, "unrouted-test", tmp_path / "ocr", lst)


def test_the_seed_skips_a_page_that_has_no_route_and_reports_it(listed, tmp_path):
    out = tmp_path / "ocr"
    q = pq.Queue(tmp_path / "q.sqlite")
    _reread_route(out, A, {2: "degraded"})  # page 7 listed but never routed; B not routed at all
    rows = [(A, 2, "1"), (A, 7, "1"), (B, 1, "1")]
    n = pq.seed_from_list(q, listed, out, _page_list(tmp_path / "p.csv", rows))
    assert (n["documents"], n["pages"], n["new"]) == (1, 1, 1)
    assert (n["unrouted_documents"], n["unrouted_pages"]) == (1, 1)
    assert [tuple(r) for r in q.con.execute("SELECT document_sha256, page_no FROM job")] == [(A, 2)]


def test_the_reread_routes_live_apart_from_the_waves(listed, tmp_path):
    """A route document under `route/` is read by `seed_pass` for every routed pass, so writing
    these text-layer documents there would have pulled any `degraded` page of them into `dots`
    (schema-critic, 2026-09-18). They go under `route-reread` instead."""
    out = tmp_path / "ocr"
    _reread_route(out, A, {1: "degraded", 2: "degraded"})
    q = pq.Queue(tmp_path / "q.sqlite")
    assert pq.seed_pass(q, "dots", out)["new"] == 0  # the wave's route root is untouched
    assert pq.PASSES["reread"]["route_root"] != pq.PASSES["dots"]["route_root"]
    assert (
        pq.seed_from_list(q, listed, out, _page_list(tmp_path / "p.csv", [(A, 1, "1")]))["new"] == 1
    )


def test_each_re_read_page_carries_its_own_class_and_the_routers_own_version(listed, tmp_path):
    """No single class selects these pages — the list does — so a reading that named one class
    would be false on most of them. And the stanza quotes the ROUTE DOCUMENT's method version,
    not this module's constant, so a page routed by an earlier router says so (ADR 0007)."""
    out = tmp_path / "ocr"
    _reread_route(out, A, {1: "degraded", 2: "graphic"}, version="provisional-0")
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", listed, {**KEY, "host": "x"})
    pq.seed_from_list(q, listed, out, _page_list(tmp_path / "p.csv", [(A, 1, "1"), (A, 2, "1")]))
    for job in q.claim("w1", listed, 2, 60):
        q.done("w1", job["job_id"], json.dumps([{"category": "Text", "text": "read"}]))
    assert pq.collect_pass(q, listed, out) == 1

    doc = json.loads(ocr_wave.shard(out / "listed-test", A).read_text(encoding="utf-8"))
    assert doc["reading_role"] == "second" and doc["reading_channel"] == "ocr"
    assert [p["route"] for p in doc["pages"]] == [
        {"class": "degraded", "method": ocr_wave.ROUTER, "method_version": "provisional-0"},
        {"class": "graphic", "method": ocr_wave.ROUTER, "method_version": "provisional-0"},
    ]
    # and it is a reading the loader takes, which is the whole point of routing first
    _, loaded = load.from_reading(doc, b"{}", {"read": 1}, {}).body()
    assert [p.route.route_class for p in loaded] == ["degraded", "graphic"]


def test_a_page_list_seeds_only_the_pages_it_names_and_only_where_the_flag_is_set(listed, tmp_path):
    out = tmp_path / "ocr"
    q = pq.Queue(tmp_path / "q.sqlite")
    _reread_route(out, A, {2: "degraded", 7: "clean", 9: "graphic"})
    _reread_route(out, B, {1: "degraded"})
    rows = [(A, 2, "1"), (A, 7, "1"), (A, 9, "0"), (B, 1, "0")]
    n = pq.seed_from_list(q, listed, out, _page_list(tmp_path / "p.csv", rows), column="prose")
    assert (n["documents"], n["pages"], n["new"], n["listed_pages"]) == (1, 2, 2, 2)
    assert [
        tuple(r) for r in q.con.execute("SELECT document_sha256, page_no FROM job ORDER BY page_no")
    ] == [(A, 2), (A, 7)]
    # without the column every listed page is taken, both documents
    q2 = pq.Queue(tmp_path / "q2.sqlite")
    n2 = pq.seed_from_list(q2, listed, out, _page_list(tmp_path / "p.csv", rows))
    assert (n2["documents"], n2["pages"]) == (2, 4)


def test_a_wider_list_tops_up_a_document_the_queue_already_calls_whole(listed, tmp_path):
    """What a list-seeded pass owes a document is NOT fixed — the score's lexicon grows with
    the record and the operator can move the cut — so `whole` must not be taken at its word.
    The first version dropped the new pages silently (/code-review and schema-critic)."""
    out = tmp_path / "ocr"
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", listed, {**KEY, "host": "x"})
    _reread_route(out, A, {1: "degraded", 2: "degraded"})
    one = _page_list(tmp_path / "a.csv", [(A, 1, "1")])
    assert pq.seed_from_list(q, listed, out, one)["new"] == 1
    (job,) = q.claim("w1", listed, 5, 60)
    q.done("w1", job["job_id"], json.dumps([{"category": "Text", "text": "one"}]))
    assert pq.collect_pass(q, listed, out) == 1
    written = ocr_wave.shard(out / pq.PASSES[listed]["root"], A)
    assert written.exists()

    # the same list again: nothing owed, the document stays whole
    assert pq.seed_from_list(q, listed, out, one) == {**_zero(), "whole": 1, "listed_pages": 1}

    # a wider list: the document is read AGAIN, whole, and its file set aside
    two = _page_list(tmp_path / "b.csv", [(A, 1, "1"), (A, 2, "1")])
    n = pq.seed_from_list(q, listed, out, two)
    assert (n["topped_up"], n["documents"], n["pages"], n["new"]) == (1, 1, 2, 2)
    assert not written.exists() and written.with_suffix(".json.superseded").exists()


def test_a_page_list_seed_sets_aside_a_document_a_non_page_failure_left_partial(listed, tmp_path):
    out = tmp_path / "ocr"
    lst = _page_list(tmp_path / "p.csv", [(A, 1, "1"), (A, 2, "1")])
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", listed, {**KEY, "host": "x"})
    _reread_route(out, A, {1: "degraded", 2: "degraded"})
    assert pq.seed_from_list(q, listed, out, lst)["new"] == 2
    assert pq.seed_from_list(q, listed, out, lst)["new"] == 0  # open: already queued

    a, b = q.claim("w1", listed, 2, 60)
    q.done("w1", a["job_id"], json.dumps([{"category": "Text", "text": "one"}]))
    q.con.execute(
        "UPDATE job SET state = 'failed', error = 'server: died' WHERE job_id = ?",
        (b["job_id"],),
    )
    q.con.commit()
    assert pq.collect_pass(q, listed, out) == 1
    written = ocr_wave.shard(out / pq.PASSES[listed]["root"], A)

    n = pq.seed_from_list(q, listed, out, lst)  # not the page's fault: read it again whole
    assert (n["set_aside"], n["new"]) == (1, 2)
    assert not written.exists() and written.with_suffix(".json.superseded").exists()


def test_the_two_seeds_refuse_each_others_pass(listed, tmp_path):
    out = tmp_path / "ocr"
    q = pq.Queue(tmp_path / "q.sqlite")
    _reread_route(out, A, {1: "degraded"})
    with pytest.raises(ValueError, match="seeded from a page list"):
        pq.seed_pass(q, "reread", out)
    with pytest.raises(ValueError, match="seeded from the route"):
        pq.seed_from_list(q, "dots", out, _page_list(tmp_path / "p.csv", [(A, 1, "1")]))
    with pytest.raises(ValueError, match="names no page"):
        pq.seed_from_list(
            q, listed, out, _page_list(tmp_path / "e.csv", [(A, 1, "0")]), column="prose"
        )


def test_the_page_list_reader_takes_gzip_and_the_flag_column(tmp_path):
    import gzip as _gzip

    plain = _page_list(tmp_path / "p.csv", [(A, 1, "1"), (A, 2, "0")])
    gz = tmp_path / "p.csv.gz"
    gz.write_bytes(_gzip.compress(plain.read_bytes()))
    assert ocr_wave.page_list(gz) == {A: {1, 2}}
    assert ocr_wave.page_list(gz, "prose") == {A: {1}}
    assert ocr_wave.page_list(plain, "prose") == {A: {1}}


def test_the_worker_can_run_either_dots_pass_and_no_other(monkeypatch):
    # `dots_worker` imports pymupdf at the top ON PURPOSE — "so a venv without it fails here,
    # not per page" — and CI installs no pymupdf, so importing the module for its constants
    # needs a stand-in. It is never called: this test reads PASSES_HERE and DPI and nothing else
    if "fitz" not in sys.modules:
        monkeypatch.setitem(sys.modules, "fitz", types.ModuleType("fitz"))
    worker = _module("dots_worker", ROOT / "tools" / "fleet" / "dots_worker.py")
    assert set(worker.PASSES_HERE) == {"dots", "reread"}  # every pass whose key is dots.mocr's
    assert "tabular" not in worker.PASSES_HERE
    assert worker.DPI == int(pq.PASSES["reread"]["key"]["render_profile"])


def test_reseeding_a_pass_whose_root_is_not_its_key_sets_the_file_aside(tmp_path):
    """`tabular`'s root is `hunyuan-tabular`, not `tabular`. The set-aside branch looked its
    root up in ROOTS a second time, which is a no-op for `dots` and a KeyError for every other
    pass — it would have crashed the tabular pass's first re-seed after a partial collection."""
    out = tmp_path / "ocr"
    _route_root(out, A, {1: "tabular", 2: "tabular"})
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", "tabular", {**TAB, "host": "x"})
    assert pq.seed_pass(q, "tabular", out)["new"] == 2

    a, b = q.claim("w1", "tabular", 2, 60)
    q.done("w1", a["job_id"], json.dumps([{"category": "Text", "text": "a cell"}]))
    q.con.execute(
        "UPDATE job SET state = 'failed', error = 'blob: missing on the node' WHERE job_id = ?",
        (b["job_id"],),
    )
    q.con.commit()
    assert pq.collect_pass(q, "tabular", out) == 1
    written = ocr_wave.shard(out / pq.PASSES["tabular"]["root"], A)
    assert written.exists()

    n = pq.seed_pass(q, "tabular", out)  # the blob miss was not the page's: read it again
    assert (n["set_aside"], n["new"]) == (1, 2)
    assert not written.exists() and written.with_suffix(".json.superseded").exists()


def test_collect_skips_a_document_whose_route_is_missing_instead_of_raising(listed, tmp_path):
    """`reread-collect` is a tmux service on a ten-minute loop. One document with no route
    document used to raise out of the batch and crash-loop it, losing every other document's
    collection with it (/code-review, 2026-09-18)."""
    out = tmp_path / "ocr"
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", listed, {**KEY, "host": "x"})
    _reread_route(out, A, {1: "degraded"})
    _reread_route(out, B, {1: "degraded"})
    pq.seed_from_list(q, listed, out, _page_list(tmp_path / "p.csv", [(A, 1, "1"), (B, 1, "1")]))
    for job in q.claim("w1", listed, 2, 60):
        q.done("w1", job["job_id"], json.dumps([{"category": "Text", "text": "read"}]))

    ocr_wave.shard(out / ocr_wave.ROOTS["reread_route"], A).unlink()  # the route goes missing
    assert pq.collect_pass(q, listed, out) == 1  # B is still written
    assert ocr_wave.shard(out / "listed-test", B).exists()
    assert not ocr_wave.shard(out / "listed-test", A).exists()
    # and A is left in the queue, so a later run collects it once the route is back
    _reread_route(out, A, {1: "degraded"})
    assert pq.collect_pass(q, listed, out) == 1
    assert ocr_wave.shard(out / "listed-test", A).exists()


def test_a_top_up_does_not_carry_an_unrouted_page_back_in(listed, tmp_path):
    """The top-up queues the pages held plus the pages listed; only the listed half had been
    filtered against the routes (/code-review, 2026-09-18)."""
    out = tmp_path / "ocr"
    q = pq.Queue(tmp_path / "q.sqlite")
    q.register("w1", listed, {**KEY, "host": "x"})
    _reread_route(out, A, {1: "degraded", 2: "degraded"})
    pq.seed_from_list(q, listed, out, _page_list(tmp_path / "a.csv", [(A, 1, "1")]))
    (job,) = q.claim("w1", listed, 5, 60)
    q.done("w1", job["job_id"], json.dumps([{"category": "Text", "text": "one"}]))
    assert pq.collect_pass(q, listed, out) == 1

    # page 1's route is withdrawn and page 3 is listed but never routed
    _reread_route(out, A, {2: "degraded"})
    n = pq.seed_from_list(
        q, listed, out, _page_list(tmp_path / "b.csv", [(A, 2, "1"), (A, 3, "1")])
    )
    assert n["topped_up"] == 1 and n["unrouted_pages"] == 1
    assert [
        tuple(r)
        for r in q.con.execute(
            "SELECT document_sha256, page_no FROM job WHERE state = 'pending' ORDER BY page_no"
        )
    ] == [(A, 2)]


def test_routing_a_second_list_keeps_the_first_runs_routes(tmp_path, monkeypatch):
    """Prose first, then the rest: the second list names other pages of the same documents. A
    fresh route document would erase the first run's classes and the pages it already read
    would lose them (/code-review, 2026-09-18)."""
    out = tmp_path / "ocr"
    _reread_route(out, A, {1: "degraded"})
    path = ocr_wave.shard(out / ocr_wave.ROOTS["reread_route"], A)
    held = json.loads(path.read_text(encoding="utf-8"))["pages"]

    # what run_route_list builds for a second list, without the layout model
    route = {"document_sha256": A, "pages": dict(held)}
    route["pages"]["2"] = {"class": "graphic", "regions": 3, "labels": []}
    ocr_wave._write(path, {**json.loads(path.read_text(encoding="utf-8")), **route})

    assert pq._routed_pages(out / ocr_wave.ROOTS["reread_route"], A) == {1, 2}
    assert pq._page_routes(out / ocr_wave.ROOTS["reread_route"], A)[1]["class"] == "degraded"


def test_a_page_outside_the_document_is_recorded_with_no_class(tmp_path):
    """So the seed skips it AND the resume check converges: without an entry the document was
    re-rendered through the layout model on every run (/code-review, 2026-09-18)."""
    out = tmp_path / "ocr"
    doc = {
        "document_sha256": A,
        "method": ocr_wave.ROUTER,
        "method_version": "provisional-1",
        "pages": {
            "1": {"class": "degraded"},
            "9": {"class": None, "error": "page 9 outside a 3-page document"},
        },
    }
    ocr_wave._write(ocr_wave.shard(out / ocr_wave.ROOTS["reread_route"], A), doc)
    root = out / ocr_wave.ROOTS["reread_route"]
    assert pq._routed_pages(root, A) == {1}  # 9 is not offered to the queue
    assert 9 not in pq._page_routes(root, A)
    assert all(str(no) in doc["pages"] for no in (1, 9))  # but the resume check is satisfied
