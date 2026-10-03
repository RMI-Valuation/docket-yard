#!/usr/bin/env python3
"""Put the coordinator's derived work somewhere that is not the coordinator.

    python3 backup.py --data /data/docketyard --bucket rmi-fleet-backups \\
        --profile fleet-backup --prefix docket-yard/

WHAT IS COPIED: **everything derived, and nothing cached.** Every directory under `ocr/` except
a named exclusion list, plus a snapshot of the queue — 569 MB compressed on 2026-09-19 against
a 114 GB data root. The exclusions are the blob mirror and the engine cache, which are caches
of a store that is always retrievable (ADR 0022 D2), the render scratch, and the logs.

**A DENY-LIST, NOT AN ALLOW-LIST, AND THE REASON MATTERS.** An earlier draft globbed the roots
it knew, so a pass added later would have been absent from every backup with no warning, no
manifest entry and a zero exit — `hunyuan-tabular` had already had to be hand-added, which was
the proof. A backup's unknowns must fall on the side of keeping, so anything new under `ocr/`
is taken by default and everything skipped is named in the log and in the manifest. Omission is
a decision someone can read, never an accident of a pattern.

It does NOT try to skip passes already loaded into the record, though `dots` and the `ppocr`
roots are. Whether a reading is loaded is a fact in the store on the instance, not on this box,
so a tool here cannot evaluate it — and a backup rule its own program cannot check is a rule
that will be wrong quietly.

NONE OF IT IS IRREPLACEABLE, and the backup is not justified by pretending otherwise. Every
artefact here can be produced again: re-running the router costs a layout pass and yields a
different method version, which seeding records per page rather than hiding (`_page_routes`);
re-reading costs GPU time, about 43 hours for the pages read by 2026-09-19. This exists so a
rebuilt box, a bad restore or a mistake does not cost those hours.

THE QUEUE IS COPIED THROUGH SQLITE'S BACKUP API, NEVER `cp`. `queue_server.py` serves it while
this runs. `Connection.backup` with the default `pages=-1` copies the whole database under one
read transaction, so in WAL mode the copy is a faithful image of one instant — not a torn file,
which is what a `cp` of a served database gives you. `integrity_check` and a row-count floor on
the COPY are what say so; the hash then proves the transfer of that copy to S3.

TWO ORDERINGS ARE LOAD-BEARING. **Do not tidy either away.**
  1. The queue is snapshotted BEFORE the roots are walked, so the archive's file tree is never
     older than its queue. A restore whose queue is newer than its files makes the seed count
     documents whole with no reading on disk (`pagequeue._decide`), which is the silence this
     project has already been bitten by once.
  2. The queue is added to the tar LAST, matching the documented restore order — files first,
     then the queue.

THE WRITER CANNOT DELETE. `fleet-backup-writer` holds `PutObject`, `GetObject` and `ListBucket`
on one bucket and no delete action at all, so this cannot destroy a previous backup even if it
is wrong, and retention is a bucket lifecycle rule enforced where this credential has no reach.
The prune is the part of a backup most likely to misbehave, so there is no prune.

EACH RUN IS A NEW DATED KEY, and `IfNoneMatch` makes that true in the code rather than in the
bucket's configuration: a second run that somehow produced the same key is refused by S3 rather
than overwriting a good copy.

Standard library plus boto3, which the coordinator already has.
"""

import argparse
import base64
import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

EXIT_ENVIRONMENT = 4
CHUNK = 1024 * 1024
# a single PUT is capped at 5 GB. Past that S3 fails loudly with EntityTooLarge — and the fix
# is NOT simply switching to multipart, because a multipart object's checksum is the composite
# `-N` form and would no longer equal the digest computed here (see `verify`)
MAX_SINGLE_PUT = 5 * 1000**3

# Caches of things that survive without us, plus scratch and logs. Everything else under `ocr/`
# is taken. `logs` is operational history: the producer identities that matter are in the
# queue's `worker` table, which is backed up.
NEVER = {"blobs", "ppocr-cache", ".render", "logs", ".backup-tmp"}


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)


def tool_version() -> str:
    """What produced this backup. Every other derived assertion here carries a method version
    (ADR 0007); a manifest that cannot say which code wrote it is not comparable with another."""
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def snapshot_queue(src: Path, dst: Path, min_jobs: int) -> dict:
    """A consistent copy of the queue while it is being served, and the facts that say it is
    sound. The timeouts match the queue's own (`pagequeue.Queue`): the server serialises every
    handler thread onto one connection, so the 5 s default would fail a backup at exactly the
    times one matters — a pass running hard."""
    if not src.exists():
        raise FileNotFoundError(src)
    with (
        contextlib.closing(sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=60)) as source,
        contextlib.closing(sqlite3.connect(dst, timeout=60)) as out,
    ):
        source.execute("PRAGMA busy_timeout=60000")
        source.backup(out)

    # the snapshot must be self-contained: a sibling -wal would hold content the tar never adds
    for sidecar in (dst.with_name(dst.name + "-wal"), dst.with_name(dst.name + "-shm")):
        if sidecar.exists():
            raise ValueError(
                f"the snapshot left {sidecar.name} beside it; it is not self-contained"
            )

    with contextlib.closing(sqlite3.connect(f"file:{dst}?mode=ro", uri=True)) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        # enumerated, not hardcoded: a table added to the schema should start being described
        # rather than silently stop being mentioned
        tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in sorted(tables)}
        states = dict(con.execute("SELECT state, count(*) FROM job GROUP BY state"))

    if integrity != "ok":
        raise ValueError(f"the snapshot is not sound: integrity_check said {integrity!r}")
    if counts.get("job", 0) < max(1, min_jobs):
        raise ValueError(
            f"the snapshot holds {counts.get('job', 0)} jobs, under the floor of {min_jobs};"
            " refusing to call that a backup"
        )
    return {"integrity": integrity, "counts": counts, "job_states": states}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def build_tarball(data: Path, queue_snapshot: Path, out: Path) -> dict:
    """Every derived root plus the queue snapshot, counted from what was ACTUALLY added.

    Walked file by file rather than with `tar.add`'s recursion, for two reasons. A file can
    vanish mid-walk — `ocr_wave._write` renames a `.json.tmp` away in milliseconds and three
    collect loops run every ten minutes — and `tar.add` would abort the whole run on it. And
    counting inside the loop makes the manifest true by construction, where a separate
    `rglob` count could disagree with the archive and nothing would ever notice."""
    ocr = data / "ocr"
    roots, loose, skipped, files, vanished = [], [], [], 0, 0
    with tarfile.open(out, "w:gz") as tar:
        for path in sorted(ocr.iterdir()):
            if path.is_file():
                # loose files fall on the side of keeping too, for the same reason directories
                # do — the re-read's page list is one, and it is the INPUT that decides what
                # that pass owes. Only the queue's own files are refused: the snapshot below is
                # the queue, and a stale `-wal` beside it would describe a different instant
                if path.name.startswith("queue.sqlite"):
                    skipped.append({"name": path.name, "why": "the queue; snapshotted instead"})
                    continue
                tar.add(path, arcname=f"ocr/{path.name}", recursive=False)
                loose.append(path.name)
                files += 1
                continue
            if not path.is_dir():
                skipped.append({"name": path.name, "why": "neither a file nor a directory"})
                continue
            if path.name in NEVER:
                skipped.append({"name": path.name, "why": "excluded: a cache, scratch or logs"})
                continue
            n = 0
            for dirpath, _dirnames, filenames in os.walk(path):
                for name in sorted(filenames):
                    f = Path(dirpath) / name
                    try:
                        tar.add(f, arcname=f"ocr/{f.relative_to(ocr)}", recursive=False)
                    except FileNotFoundError:
                        vanished += 1  # written and renamed away while we walked; not an error
                        continue
                    n += 1
            roots.append({"root": path.name, "files": n})  # kept even at 0: "empty" is not "gone"
            files += n
        # LAST, so a restore lays the files down before the queue that describes them
        tar.add(queue_snapshot, arcname="ocr/queue.sqlite")
    return {
        "roots": roots,
        "loose_files": sorted(loose),
        "skipped": skipped,
        "files": files + 1,
        "vanished_while_walking": vanished,
        "bytes": out.stat().st_size,
    }


def verify(head: dict, size: int, digest: str) -> str | None:
    """What is wrong with the stored object, or None. The checksum is the point: two files of
    the same length pass a size check, and `ChecksumMode="ENABLED"` already put S3's own
    digest in the response."""
    if head.get("ContentLength") != size:
        return f"wrong size: sent {size}, stored {head.get('ContentLength')}"
    want = base64.b64encode(bytes.fromhex(digest)).decode()
    got = head.get("ChecksumSHA256")
    if got is None:
        return "the store returned no SHA-256; it cannot be verified"
    if got != want:
        return f"wrong checksum: computed {want}, stored {got}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True, type=Path, help="the coordinator's data root")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", default="docket-yard/")
    ap.add_argument("--profile", default="fleet-backup")
    ap.add_argument(
        "--tmp",
        type=Path,
        default=None,
        help="where the tarball is built; defaults beside the data, NOT /tmp, which is a tmpfs"
        " on the coordinator and would build a half-gigabyte archive in RAM",
    )
    ap.add_argument("--min-jobs", type=int, default=1, help="refuse a suspiciously empty queue")
    ap.add_argument("--keep-local", type=Path, help="also leave the tarball here")
    ap.add_argument("--dry-run", action="store_true", help="build and verify, upload nothing")
    args = ap.parse_args()

    queue = args.data / "ocr" / "queue.sqlite"
    if not queue.exists():
        log(f"no queue at {queue}; this is not a coordinator. exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    prefix = (args.prefix.rstrip("/") + "/") if args.prefix.strip("/") else ""

    work_root = args.tmp or (args.data / ".backup-tmp")
    try:
        work_root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log(f"cannot use {work_root} ({type(e).__name__}: {e}); exit {EXIT_ENVIRONMENT}")
        return EXIT_ENVIRONMENT
    free = shutil.disk_usage(work_root).free
    if free < 3 * 1000**3:
        log(f"only {free / 1e9:.1f} GB free at {work_root}; refusing to build a tarball there")
        return EXIT_ENVIRONMENT

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(prefix="dy-backup-", dir=work_root) as tmp:
        work = Path(tmp)
        # BEFORE the walk: the archive's files must never be older than its queue
        try:
            facts = snapshot_queue(queue, work / "queue.sqlite", args.min_jobs)
        except (OSError, ValueError, sqlite3.Error) as e:
            extra = ""
            if isinstance(e, sqlite3.OperationalError) and "unable to open" in str(e):
                extra = " — is the queue server down with an uncheckpointed -wal?"
            log(f"the queue snapshot failed ({type(e).__name__}: {e}){extra}; exit 4")
            return EXIT_ENVIRONMENT
        log(
            f"queue: integrity {facts['integrity']}, "
            + ", ".join(f"{k} {v}" for k, v in facts["counts"].items())
        )

        tarball = work / f"dy-coordinator-{stamp}.tar.gz"
        try:
            built = build_tarball(args.data, work / "queue.sqlite", tarball)
        except OSError as e:
            log(f"building the tarball failed ({type(e).__name__}: {e}); exit {EXIT_ENVIRONMENT}")
            return EXIT_ENVIRONMENT
        digest = sha256_of(tarball)
        log(
            f"tarball: {built['bytes'] / 1e6:.1f} MB, {built['files']} files, "
            f"roots {[r['root'] for r in built['roots']]}"
        )
        if built["skipped"]:
            log("  skipped: " + ", ".join(f"{s['name']} ({s['why']})" for s in built["skipped"]))
        if built["vanished_while_walking"]:
            log(f"  {built['vanished_while_walking']} file(s) vanished while walking (expected)")
        if built["bytes"] > MAX_SINGLE_PUT:
            log(f"the tarball is over {MAX_SINGLE_PUT / 1e9:.0f} GB, the single-PUT cap; exit 4")
            return EXIT_ENVIRONMENT

        manifest = {
            "taken_at": stamp,
            "host": os.uname().nodename if hasattr(os, "uname") else "",
            "tool": "tools/fleet/backup.py",
            "tool_version": tool_version(),
            "sha256": digest,
            "queue": facts,
            **built,
        }

        if args.keep_local:
            args.keep_local.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tarball, args.keep_local / tarball.name)  # not read_bytes(): 569 MB
            log(f"kept a local copy at {args.keep_local / tarball.name}")
        if args.dry_run:
            log(f"dry run: would upload {prefix}{tarball.name} (sha256 {digest[:16]}…)")
            return 0

        import boto3  # noqa: PLC0415 — only when something is actually uploaded

        s3 = boto3.Session(profile_name=args.profile).client("s3")
        key = f"{prefix}{tarball.name}"
        try:
            with tarball.open("rb") as fh:
                # streamed, not read into memory; S3 recomputes the checksum and REJECTS a body
                # that does not match, so a corrupt transfer cannot land at all
                s3.put_object(
                    Bucket=args.bucket,
                    Key=key,
                    Body=fh,
                    ChecksumAlgorithm="SHA256",
                    IfNoneMatch="*",
                )
            head = s3.head_object(Bucket=args.bucket, Key=key, ChecksumMode="ENABLED")
        except Exception as e:  # noqa: BLE001 — botocore builds its errors at runtime
            log(f"upload failed ({type(e).__name__}: {e}); exit {EXIT_ENVIRONMENT}")
            return EXIT_ENVIRONMENT

        # VERIFIED BEFORE ANYTHING ASSERTS IT. The manifest is written only now: the credential
        # holds no delete, so a manifest put before this check would permanently describe a bad
        # object as good, and nothing could take it back
        wrong = verify(head, built["bytes"], digest)
        if wrong:
            log(f"THE STORED OBJECT IS NOT WHAT WAS SENT — {wrong}; no manifest written; exit 4")
            return EXIT_ENVIRONMENT
        try:
            s3.put_object(
                Bucket=args.bucket,
                Key=f"{key}.manifest.json",
                Body=json.dumps({**manifest, "verified": True}, indent=1).encode(),
                IfNoneMatch="*",
            )
        except Exception as e:  # noqa: BLE001
            log(f"the object is good but its manifest did not upload ({type(e).__name__}: {e})")
            return EXIT_ENVIRONMENT
        log(f"uploaded s3://{args.bucket}/{key}")
        log(f"  verified against the store: {head['ContentLength']} bytes, sha256 matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
