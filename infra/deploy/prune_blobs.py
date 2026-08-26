#!/usr/bin/env python3
"""Keep the instance's blob directory a cache: S3 is the store (ADR 0012).

Runs on the host after each blob sync. A local blob may be deleted only if S3 holds an
object of the same key — checked against a fresh listing, never assumed — and then only
when it is older than KEEP_DAYS, or when free disk is below the floor, oldest first until
the floor is met again. Captures (raw response bodies) are blobs too and follow the same
rule; the store's rows point at S3 keys by hash, so nothing on the site changes.

    python3 prune_blobs.py /srv/docketyard/data/blobs docketyard-prod [--dry-run]
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

KEEP_DAYS = 30
FLOOR_GB = 20  # free space the instance must keep for the store, WAL, and a wave's tempfiles
TARGET_GB = 28  # prune down to this much free when the floor is breached


def s3_keys(bucket: str) -> set[str]:
    out = subprocess.run(
        [
            "aws",
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket,
            "--prefix",
            "blobs/",
            "--query",
            "Contents[].Key",
            "--output",
            "text",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    keys: set[str] = set()
    for chunk in out.split():
        if chunk.startswith("blobs/"):
            keys.add(chunk)
    return keys


def free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def main(blobs: Path, bucket: str, dry_run: bool) -> None:
    held = s3_keys(bucket)
    if not held:
        sys.exit("S3 listing is empty; refusing to prune anything")
    now = time.time()
    candidates = []
    for path in blobs.glob("*/*"):
        if not path.is_file() or path.suffix == ".tmp":
            continue
        key = f"blobs/{path.parent.name}/{path.name}"
        if key not in held:
            continue  # not yet synced: never touch
        candidates.append((path.stat().st_mtime, path))
    candidates.sort()
    deleted = freed = 0
    for mtime, path in candidates:
        old = now - mtime > KEEP_DAYS * 86400
        tight = free_gb(blobs) < FLOOR_GB or (freed and free_gb(blobs) < TARGET_GB)
        if not (old or tight):
            continue
        size = path.stat().st_size
        if not dry_run:
            os.remove(path)
        deleted += 1
        freed += size
    print(
        f"{'would delete' if dry_run else 'deleted'} {deleted} blobs, {freed / 1e9:.2f} GB;"
        f" {len(candidates)} local blobs are in S3; free {free_gb(blobs):.1f} GB"
    )


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    main(Path(args[0]), args[1], "--dry-run" in sys.argv)
