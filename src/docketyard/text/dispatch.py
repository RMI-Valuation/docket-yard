"""The forward pass's text stage: hand new material to the parser, load what came back.

ADR 0024 D4, D9 and D10. The queue decides WHAT (`text/queue.py`); this decides WHETHER, WHEN
and what to do with the answer, and it is the only thing that writes `extraction_dispatch`.

THE ORDER IS THE DESIGN, and each step exists because of the failure the one before it has:

1. **Read the pin.** `producer_declaration` holds it (D6), and nothing here invents one. With
   no declaration the stage does nothing and says so: a poller that writes its own constant
   drifts silently from the container, and the silent direction is the container moving ahead,
   leaving every document the new version could read exhausted for ever at a pin that no
   longer exists. Declaring is an operator's act — `docketyard text pin`.

2. **Load first, dispatch second.** The spool is drained at the TOP of the stage, before this
   pass asks for anything, because the parser is asynchronous: what it wrote is the answer to
   an earlier pass's request. Draining first also means the reconciliation below sees this
   pass's own landings.

3. **Reconcile, and let the answer bound the ask.** D4's halt is A QUERY, not a state: dispatch
   is capped at one canary while the last `HALT_AFTER` dispatches show no matching successful
   run. Held as a flag it either never clears — nothing dispatched means nothing lands means
   the condition holds for ever — or it clears every other pass, halving a dead container's
   burn rate instead of stopping it. The canary keeps the condition measurable, so recovery is
   automatic and needs no operator.

   The test is landed-AND-READ, not landed. A container that is up and failing every document
   lands rows, so a ratio measured on landing alone never halts and the whole backlog retires
   at one attempt each.

4. **Write the dispatch rows and COMMIT before the request file exists.** D4: a hand-off the
   record does not remember is this decision's own failure. `forward_pass` threads one
   connection through every stage and `commit()` commits everything open on it, so this is
   ordering, not isolation — and the house `try/except: con.rollback()` is deliberately NOT
   wrapped around the enqueue, because it would roll back dispatch rows for bytes the parser
   has already been handed, and the bound would stop being a bound for the most likely failure
   there is.

5. **Enqueue.** One request file naming the documents. See `infra/extract/extract.py` for why
   the poller enqueues rather than invoking a container.

WHAT THIS STAGE NEVER DOES: open a PDF, or let a counted failure vanish. D10 requires the
loader's `unreadable`, `failed` and `aborted` counts to reach the pass's `problems`, because
`store.batches.run` RETURNS them rather than raising and a bare `try/except` would see a
clean pass.
"""

import json
import time
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from sqlite3 import Connection

from docketyard.store.db import utcnow
from docketyard.text import load, paginate, queue
from docketyard.text.fields import read_head

CHANNEL, RENDER, ROLE = queue.CHANNEL, queue.RENDER, "primary"
# How many recent dispatches must go unanswered before the stage stops asking for more than a
# canary. One pass's worth is too few — a single container restart would trip it — and a day's
# worth is too many, because at 48 passes a day that is most of the backlog burnt before the
# halt engages. Twenty is about two passes of a full queue.
HALT_AFTER = 20


def _pin(con: Connection) -> tuple[str, str] | None:
    return load.pinned(con, CHANNEL, RENDER, ROLE)


def unanswered(con: Connection, *, window: int = HALT_AFTER) -> int:
    """Of the last `window` dispatches, how many have no successful run at or after them.

    THE FLOOR `ran_at >= dispatched_at` IS A NARROWING, NOT A PROOF, and ADR 0024 § Owed 5
    says so: neither table records which producer wrote it, so a wave load landing during a
    container outage can satisfy this and clear the halt for documents the parser never read.
    `ocr_run.ran_at` is the parser's own clock from a spool header that may have been written
    on the enrichment box weeks earlier, which is what the floor excludes. A producer column
    settles it and `ADD COLUMN` survives publication.
    """
    return con.execute(
        "SELECT COUNT(*) FROM (SELECT x.document_sha256, x.dispatched_at"
        "   FROM extraction_dispatch x"
        "  ORDER BY x.dispatched_at DESC, x.dispatch_id DESC LIMIT ?) recent"
        " WHERE NOT EXISTS (SELECT 1 FROM ocr_run r"
        "                    WHERE r.document_sha256 = recent.document_sha256"
        "                      AND r.reading_channel = ? AND r.render_profile = ?"
        "                      AND r.outcome = 'read' AND r.ran_at >= recent.dispatched_at)",
        (window, CHANNEL, RENDER),
    ).fetchone()[0]


def halted(con: Connection, *, window: int = HALT_AFTER) -> bool:
    """Whether every one of the last `window` dispatches went unanswered — and only when
    there have been that many, or an empty table would read as a dead container and the stage
    would never start."""
    dispatched = con.execute("SELECT COUNT(*) FROM extraction_dispatch").fetchone()[0]
    return dispatched >= window and unanswered(con, window=window) >= window


# How long after a dispatch a reading of it is still the answer to it. Bounded rather than
# open-ended: "any document ever dispatched" grows into the whole forward record, and the
# boundary would weaken every month on its own (code review, 2026-09-10). A reading cannot
# honestly arrive later than the attempts that would have been spent asking for it again.
AUTHORISED_HOURS = queue.EXTRACT_RETRY_HOURS * (queue.EXTRACT_ATTEMPTS + 1)


def _authorised(con: Connection, sha: str, ran_at: str) -> bool:
    """Whether a dispatch of this document PRECEDES the reading and is recent enough to be
    what it answers. `ran_at` is the parser's own clock and therefore untrusted; the window is
    what stops a compromised parser back-dating a reading onto a dispatch from months ago."""
    if not ran_at:
        return False
    try:
        floor = (datetime.fromisoformat(ran_at) - timedelta(hours=AUTHORISED_HOURS)).isoformat()
    except ValueError:
        return False
    return (
        con.execute(
            "SELECT 1 FROM extraction_dispatch WHERE document_sha256 = ?"
            "   AND dispatched_at <= ? AND dispatched_at >= ? LIMIT 1",
            (sha, ran_at, floor),
        ).fetchone()
        is not None
    )


def admit(con: Connection, spool: Path, ready: Path, problems: list[str]) -> tuple[int, int]:
    """Move each spool file into the loader's own directory, or into quarantine. Returns
    (admitted, quarantined).

    **THIS IS THE TRUST BOUNDARY, and ADR 0024 D4 assigns it here by name**: "`ocr_run`
    records what actually ran, and the loader holds both, so 'the spool file disagrees with
    the dispatch' is a detectable event and the loader's to report." Without it the check
    exists only in one direction — `unanswered` walks dispatches that got no run, and so
    never notices a run nobody asked for (security review, 2026-09-10).

    WHY IT MATTERS, granting D2's own premise. The parser exists in isolation because
    `pymupdf` is a large C library with a CVE history, parsing the least trusted input this
    project handles. Suppose a hostile PDF takes it: the isolation holds — no store, no key,
    no network — but the spool is a read-write mount, and the loader accepts a record on two
    tests only, that its digest matches its filename and that the digest exists in
    `document`. A compromised parser could therefore write a `primary` reading for ANY of the
    hundred thousand documents in the record, displace the live one, and have the forged text
    indexed and served with provenance naming a producer that never read those bytes. The
    difference this makes is between lying about the twenty-five documents it was handed and
    rewriting the record.

    THE KEY IS CHECKED TOO, not only the document. This directory has exactly one legitimate
    producer and it can write exactly one shape: `text-layer` / `native` / `primary` at the
    declared pin. An `ocr` reading here is not a reading this stage asked for, whatever its
    digest, and `pinned` constrains only keys the registry holds — so an undeclared key would
    otherwise be free to displace the text layer through the cross-key supersede path.

    AND IT IS A HAND-OFF, NOT A PRE-PASS. The parser writes into the spool continuously, so
    checking the spool and then letting the loader walk the same directory leaves a window
    between the two in which a file can land unchecked — the boundary bypassed by timing,
    under exactly the threat model it exists for (code review, 2026-09-10). So the check MOVES
    the file: `spool/` is the parser's to write and this stage's to drain, `ready/` is the
    loader's alone and nothing else writes it. A file arriving mid-pass is simply next pass's.

    Quarantined rather than deleted: the file is evidence, and a stage that destroys what it
    refuses cannot be investigated.
    """
    if not spool.is_dir():
        return 0, 0
    admitted = refused = 0
    held = spool.parent / "quarantine"
    for shard in sorted(p for p in spool.iterdir() if p.is_dir()):
        for path in sorted(shard.glob("*.json")):
            try:
                head = read_head(path)
            except (OSError, ValueError) as e:
                problems.append(f"text spool: {path.name[:12]} unreadable ({e})")
                continue
            sha, ran_at = head.get("document_sha256"), head.get("extracted_at") or ""
            why = None
            if not isinstance(sha, str) or sha != path.stem:
                why = "its digest is not its filename"
            elif head.get("tool") is None or head.get("reading_role") is not None:
                why = "it is not an extraction record, which is all this stage produces"
            elif not _authorised(con, sha, ran_at):
                why = "no dispatch precedes it"
            if why is None:
                target = ready / shard.name / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                path.replace(target)
                admitted += 1
                continue
            held.mkdir(parents=True, exist_ok=True)
            path.replace(held / path.name)
            problems.append(f"text spool: quarantined {path.name[:12]} — {why}")
            refused += 1
    return admitted, refused


def sweep(con: Connection, spool: Path) -> int:
    """Delete the spool files whose reading is now in the store (ADR 0024 D9).

    "A file is removed only after the loader reports a landed outcome — never on
    `unreadable`, `failed` or `aborted`, or a parse failure would destroy the raw D5 needs a
    reason from." Landing is asked of the STORE rather than of the loader's counts, which are
    per pass and not per file: an `ocr_run` row at this reading's own key and `ran_at` is
    exactly what the loader writes when a reading lands, and it is what a restart reads to
    return `restart` without re-parsing.

    Without this the spool grows without bound and every pass re-walks the whole of it
    (security review, 2026-09-10).
    """
    if not spool.is_dir():
        return 0
    gone = 0
    for shard in sorted(p for p in spool.iterdir() if p.is_dir()):
        for path in sorted(shard.glob("*.json")):
            try:
                head = read_head(path)
            except (OSError, ValueError):
                continue  # left alone deliberately: it is the raw a reason comes from
            landed = con.execute(
                "SELECT 1 FROM ocr_run WHERE document_sha256 = ? AND method = ?"
                "   AND method_version = ? AND reading_channel = ? AND render_profile = ?"
                "   AND ran_at = ? LIMIT 1",
                (
                    head.get("document_sha256"),
                    head.get("tool"),
                    head.get("tool_version"),
                    CHANNEL,
                    RENDER,
                    head.get("extracted_at"),
                ),
            ).fetchone()
            if landed:
                path.unlink(missing_ok=True)
                gone += 1
    return gone


def _clear(ready: Path, held: Path, problems: list[str]) -> int:
    """Move aside what the loader walked and did not land. See the caller for why."""
    if not ready.is_dir():
        return 0
    moved = 0
    for shard in sorted(p for p in ready.iterdir() if p.is_dir()):
        for path in sorted(shard.glob("*.json")):
            held.mkdir(parents=True, exist_ok=True)
            path.replace(held / path.name)
            problems.append(f"text spool: {path.name[:12]} was refused by the loader")
            moved += 1
    return moved


def held_locally(blobs: Path, shas: list[str]) -> tuple[list[str], list[str]]:
    """(present, pruned). The blob pool on this box is a CACHE, not the store: S3 is the
    store, and `prune_blobs.py` deletes local copies over thirty days old to keep the disk
    free. The parser has `network_mode: none` and no credentials, so it cannot fetch what is
    not there — it would write "no blob on this box", the stub would count as an attempt, and
    three passes later the document would leave the queue for ever having never been read
    (code review, 2026-09-10).

    So they are not dispatched, and they are COUNTED: no attempt is spent, and the number is
    reported rather than being a silence. Twenty-five `stat` calls a pass.
    """
    present, pruned = [], []
    for sha in shas:
        (present if (blobs / sha[:2] / sha).is_file() else pruned).append(sha)
    return present, pruned


def enqueue(requests: Path, shas: list[str], at: str) -> Path:
    """One request file, written `.tmp` and renamed so the parser never reads a half-written
    list. Named for the moment it was written, so the parser's own `sorted()` is oldest-first
    and a backlog of requests drains in the order the record made them — plus a digest of the
    list, because two enqueues in one second (a hand `poll` run beside the container's) would
    otherwise be one filename, and the loser's dispatch rows are already committed: those
    documents would burn an attempt and never be parsed (code review, 2026-09-10)."""
    requests.mkdir(parents=True, exist_ok=True)
    stamp = at.replace(":", "").replace("-", "")
    unique = sha256(" ".join(shas).encode()).hexdigest()[:8]
    target = requests / f"{stamp}-{unique}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"dispatched_at": at, "documents": shas}, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(target)
    return target


def run(
    con: Connection,
    data_dir,
    *,
    spool: Path,
    requests: Path,
    problems: list[str],
    limit: int = queue.EXTRACT_LIMIT,
    log=print,
) -> dict:
    """One pass of the stage. Returns the summary; every counted failure reaches `problems`."""
    out: dict = {"loaded": {}, "paginated": {}, "dispatched": 0}
    pin = _pin(con)
    if pin is None:
        out["skipped"] = "no producer pinned for text-layer/native/primary"
        return out
    method, version = pin
    out["pin"] = f"{method}@{version}"

    # 1. ADMIT WHAT WAS ASKED FOR, into the loader's own directory. This is the boundary
    # between the container that parses hostile bytes and the one that holds the store, and it
    # is a MOVE rather than a check so that nothing can land between the check and the walk.
    ready = spool.parent / "ready"
    out["admitted"], out["quarantined"] = admit(con, spool, ready, problems)

    # 2. drain what the parser has already written. `paginate` first: it reads the same
    # records and writes the page-count denominator ADR 0022 D3 publishes, without which a
    # forward document's /text page prints "the page count is not yet recorded" about a
    # number the machine had just computed.
    started = time.monotonic()
    aborted = False
    if ready.is_dir():
        for name, pass_ in (("paginated", paginate), ("loaded", load)):
            try:
                totals = pass_.run(con, ready, data_dir) if pass_ is load else pass_.run(con, ready)
            except Exception as e:  # noqa: BLE001 — the stage must never cost the pass
                con.rollback()
                aborted = True
                problems.append(f"text {name}: aborted ({type(e).__name__}: {e})")
                continue
            out[name] = dict(totals)
            aborted = aborted or bool(totals.get("aborted"))
            # D10: `batches.run` RETURNS these rather than raising, so a bare try/except sees
            # a clean pass. They are counted failures and they belong in `problems`.
            for word in ("unreadable", "failed", "aborted"):
                if totals.get(word):
                    problems.append(f"text {name}: {totals[word]} {word}")

    out["swept"] = sweep(con, ready)
    # WHAT THE LOADER REFUSED MUST ALSO LEAVE, or the directory grows without bound and every
    # pass re-walks and re-refuses it, one problem line at a time, for ever — the failure the
    # sweep was added to prevent, arriving through the file the sweep will not touch (code
    # review, 2026-09-10). Only after a load that did NOT abort: an abort is the store being
    # busy, which says nothing about the file, and D9 forbids destroying the raw a reason comes
    # from. Quarantined, not deleted, for the same reason.
    if not aborted:
        out["refused"] = _clear(ready, spool.parent / "quarantine", problems)

    # 3. the halt is a query, asked after this pass's own landings are in
    out["unanswered"] = unanswered(con)
    if halted(con):
        limit = 1
        out["halted"] = True
        problems.append(
            f"text extraction: the last {HALT_AFTER} dispatches have no successful run."
            " Sending one canary this pass; check the `extract` container."
        )

    # THE BUDGET STOPS THE STAGE STARTING NEW WORK (D3), it does not interrupt what is
    # running: the drain above is one `batches.run` and killing it mid-batch is the abort
    # that idiom exists to avoid. So a pass whose drain has already spent the budget asks for
    # nothing more, and the next pass — thirty minutes later, with the spool now shorter —
    # picks it up.
    if time.monotonic() - started > queue.EXTRACT_BUDGET_SECONDS:
        out["over_budget"] = True
        return out

    # 4. the queue, at the pin now in force
    since = (datetime.now(UTC) - timedelta(hours=queue.EXTRACT_RETRY_HOURS)).isoformat(
        timespec="seconds"
    )
    shas = queue.due(con, method=method, version=version, since=since, limit=limit)
    shas, pruned = held_locally(Path(data_dir) / "blobs", shas)
    if pruned:
        out["pruned"] = len(pruned)
        problems.append(
            f"text extraction: {len(pruned)} document(s) due have no blob on this box"
            " (the cache is pruned at 30 days); not dispatched, so no attempt is spent"
        )
    if not shas:
        return out

    # 5. the dispatch rows, COMMITTED before the request file exists
    at = utcnow()
    con.executemany(
        "INSERT INTO extraction_dispatch (document_sha256, pinned_method,"
        " pinned_method_version, dispatched_at) VALUES (?, ?, ?, ?)",
        [(sha, method, version, at) for sha in shas],
    )
    con.commit()
    if con.in_transaction:  # pragma: no cover — `commit` above makes this false
        raise RuntimeError("the dispatch rows are not committed; refusing to hand off")

    # 6. enqueue. NOT wrapped in the house rollback: it would roll back dispatch rows for
    # bytes the parser has already been handed.
    try:
        enqueue(requests, shas, at)
    except OSError as e:
        problems.append(f"text extraction: could not enqueue ({type(e).__name__}: {e})")
        return out
    out["dispatched"] = len(shas)
    log(f"text extraction: handed {len(shas)} documents to {method}@{version}")
    return out
