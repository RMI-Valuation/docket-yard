"""Pull the blob store from S3 onto RMI-AI-MACHINE, incrementally, with the read-only
profile (infra/deploy/README.md: `docketyard-reader`). The AWS CLI is not on this box;
boto3 is (`pip install boto3` in the repo's venv). Only keys under `blobs/<aa>/` are
taken — never the staging area — and a file already present with the right size is
skipped, so a re-run costs one listing.

    python3 pull_blobs.py docketyard-prod /data/docketyard/blobs --profile docketyard-reader
"""

import argparse
import time
from pathlib import Path

import boto3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bucket")
    ap.add_argument("dest")
    ap.add_argument("--profile", default="docketyard-reader")
    ap.add_argument("--prefix", default="blobs/")
    args = ap.parse_args()
    s3 = boto3.Session(profile_name=args.profile).client("s3")
    dest = Path(args.dest)
    seen = taken = skipped = 0
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
            if path.exists() and path.stat().st_size == obj["Size"]:
                skipped += 1
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            s3.download_file(args.bucket, key, str(tmp))
            tmp.replace(path)
            taken += 1
            if taken % 500 == 0:
                print(f"  {taken} pulled, {skipped} present, {time.monotonic() - started:.0f}s")
    print(
        f"done: {seen} blobs in S3, {taken} pulled, {skipped} already present, "
        f"{time.monotonic() - started:.0f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
