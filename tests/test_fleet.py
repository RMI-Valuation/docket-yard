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
    assert load.load_reading(con, tmp_path, load.from_reading(doc, b"{}", load.run_outcomes(con)))
    con.commit()
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


def test_the_transport_refuses_a_bad_token(remote):
    r, _ = remote
    bad = pq.RemoteQueue(r.url, "x" * 40)
    with pytest.raises(urllib.error.HTTPError) as e:
        bad.claim("w", "dots", 1, 60)
    assert e.value.code == 401
    with pytest.raises(urllib.error.HTTPError) as e:
        bad.blob(A)
    assert e.value.code == 401
