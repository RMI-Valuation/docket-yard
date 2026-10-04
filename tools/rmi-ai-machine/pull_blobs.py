"""Pull the blob store from S3 onto RMI-AI-MACHINE, incrementally, with the read-only
profile (infra/deploy/README.md: `docketyard-reader`). The AWS CLI is not on this box;
boto3 is (`pip install boto3` in the repo's venv). Only keys under `blobs/<aa>/` are
taken — never the staging area.

**A download is landed only when it HASHES to its name** (ADR 0002: the name is the sha), so
nothing this pulls is ever wrong under its name. **A file already present is kept on its size
by default, and on its hash with `--verify`**: hashing every present file made a no-op re-run
read the whole mirror (tens of GB) to confirm nothing changed, and the client already verifies
every document it serves, mirror hits included (code review, 2026-10-03). A same-size wrong
file — what migration 0018 warns a size comparison lets through — is caught at the reader
without it, and here at once with it.

    python3 pull_blobs.py docketyard-prod /data/docketyard/blobs --profile docketyard-reader
    python3 pull_blobs.py docketyard-prod /data/docketyard/blobs --verify   # hash what is there
"""

import argparse
import hashlib
import sys
import time
from pathlib import Path

CHUNK = 1 << 20


def digest_of(path: Path) -> str:
    """The file's sha256, streamed: a document in this record reaches 1.07 GB."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def held(path: Path, sha: str, size: int, *, verify: bool = False) -> bool:
    """Whether the mirror already holds this object: present at the store's size, and with
    `verify`, hashing to its own name (the check that settles it)."""
    try:
        if path.stat().st_size != size:
            return False
    except FileNotFoundError:
        return False
    return digest_of(path) == sha if verify else True


def main() -> int:
    import boto3  # here, not at the top: the checks above are tested where boto3 is not

    ap = argparse.ArgumentParser()
    ap.add_argument("bucket")
    ap.add_argument("dest")
    ap.add_argument("--profile", default="docketyard-reader")
    ap.add_argument("--prefix", default="blobs/")
    ap.add_argument("--verify", action="store_true", help="hash every present file, not size")
    args = ap.parse_args()
    s3 = boto3.Session(profile_name=args.profile).client("s3")
    dest = Path(args.dest)
    seen = taken = skipped = refused = 0
    started = time.monotonic()
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=args.bucket, Prefix=args.prefix)
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(args.prefix) :]
            if rel.startswith(".tmp/") or "/" not in rel or rel.endswith(".tmp"):
                continue  # the staging area or a half-written sibling: never a blob
            seen += 1
            path = dest / rel
            if held(path, path.name, obj["Size"], verify=args.verify):
                skipped += 1
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            s3.download_file(args.bucket, key, str(tmp))
            got = digest_of(tmp)
            if got != path.name:
                # A corrupt object in the store, or a download gone wrong: either way it is
                # never landed under a name it does not hash to, and the run says so.
                tmp.unlink(missing_ok=True)
                refused += 1
                print(f"  {key} hashes to {got}: not landed", file=sys.stderr, flush=True)
                continue
            tmp.replace(path)
            taken += 1
            if taken % 500 == 0:
                print(f"  {taken} pulled, {skipped} present, {time.monotonic() - started:.0f}s")
    print(
        f"done: {seen} blobs in S3, {taken} pulled, {skipped} already present, "
        f"{refused} refused for not hashing to their name, {time.monotonic() - started:.0f}s"
    )
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
