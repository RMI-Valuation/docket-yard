"""The bulk snapshot: the public record as one SQLite file, cut nightly (M9, capability F5).

What leaves the box is a copy of the store with every table that could name a reader
dropped — subscriptions, tokens, alerts, suppression — *including their ciphertext* (ADR
0011, 0014: nothing about a reader is published, readable or not). Everything else is the
record itself and its provenance, rebuildable from the Board's own files.

Two safeguards, because a leak here would be licensed CC0 the moment it was served:

- The copy is built in a working directory that is **not** served, and only finished
  files are moved into the public one; the unscrubbed copy never has a URL.
- The scrub is an allowlist. After the named private tables are dropped, every table
  left must be one the snapshot is known to publish, and no surviving column may look
  like a recipient, a token or ciphertext. A future migration that adds a reader table
  under a new name fails the dump rather than publishing it.

The manifest (`index.json`) is measured from the files it describes; the page that offers
the download is generated from the manifest, so it cannot claim a file that is not there.

Data licence: CC0 1.0 (the operator's decision, 2026-08-26) for the **raw index** — the
Board's records are U.S. government works and the compilation of them is dedicated to the
public domain. The **enriched layer** (the party module today; the citator later) is held
out of the snapshot and the JSON until the attorney review `docs/licensing.md` records is
done: a dedication cannot be withdrawn, so nothing irreversible happens before it.
"""

import gzip
import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from docketyard.store.db import utcnow

PRIVATE_TABLES = (
    "alert_event",
    "alert",
    "subscription_token",
    "subscription",
    "email_suppression",
)
# Derived work held back pending the enriched-layer licence review (docs/licensing.md).
HELD_TABLES = (
    "filing_party_link",
    "filing_party_span",
    "party_relationship",
    "relationship_vocab",
    "party_name",
    "party",
)
HELD_REASON = (
    "The party module (entity resolution, aliases, successions) is derived work whose licence"
    " awaits review; it is withheld until then, not dedicated by default."
)
PUBLIC_TABLES = frozenset(
    {
        "capture",
        "event",
        "docket",
        "filing",
        "filing_attachment",
        "decision_record",
        "decision_attachment",
        "document",
        "document_source",
        "walk_slice",
        "coverage_gap",
        "correction",
    }
)
_SUSPECT_COLUMN = re.compile(r"email|token|secret|_enc$|recipient|address", re.I)
LATEST = "docketyard-latest.sqlite.gz"
SCHEMA = "schema.sql"
LICENCE = "CC0-1.0"
LICENCE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
_DATED = "docketyard-????-??-??.sqlite.gz"


class Unsafe(RuntimeError):
    """The scrubbed copy still holds something that must not be published."""


@dataclass(frozen=True)
class File:
    name: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class Manifest:
    built_at: str
    licence: str
    licence_url: str
    schema_version: int
    counts: dict  # measured from the snapshot itself
    omitted_tables: list[str]  # reader tables: never published
    held_tables: list[str]  # derived work withheld pending its licence
    held_reason: str
    latest: File
    dated: list[File]  # kept archives, newest first
    schema: str = SCHEMA  # file name


def scrub(src: Path, dst: Path) -> tuple[dict, int, str]:
    """A consistent copy of the store with the private tables gone and the space reclaimed.
    Returns what was measured from the copy: counts, schema version, and its DDL — the
    schema published is the snapshot's own, not the live store's."""
    if dst.exists():
        dst.unlink()
    con = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)  # encoded path
    try:
        con.execute("VACUUM INTO ?", (str(dst),))
    finally:
        con.close()
    out = sqlite3.connect(dst)
    try:
        out.execute("PRAGMA foreign_keys = OFF")
        for table in PRIVATE_TABLES + HELD_TABLES:
            out.execute(f"DROP TABLE IF EXISTS {table}")
        out.commit()
        out.execute("VACUUM")
        q = out.execute
        left = {
            r[0]
            for r in q("SELECT name FROM sqlite_master WHERE type = 'table'")
            if not r[0].startswith("sqlite_")
        }
        unknown = left - PUBLIC_TABLES
        if unknown:
            raise Unsafe(f"tables not on the public allowlist: {sorted(unknown)}")
        for table in sorted(left):
            for col in [r[1] for r in q(f"PRAGMA table_info({table})")]:
                if _SUSPECT_COLUMN.search(col):
                    raise Unsafe(f"{table}.{col} looks like reader data")
        counts = {
            "dockets": q("SELECT COUNT(*) FROM docket").fetchone()[0],
            "filings": q("SELECT COUNT(DISTINCT stb_filing_id) FROM filing").fetchone()[0],
            "decisions": q(
                "SELECT COUNT(DISTINCT stb_decision_id) FROM decision_record"
            ).fetchone()[0],
            "events": q("SELECT COUNT(*) FROM event").fetchone()[0],
            "documents": q("SELECT COUNT(*) FROM document").fetchone()[0],
        }
        version = q("PRAGMA user_version").fetchone()[0]
        ddl = q(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"
            " ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, name"
        ).fetchall()
        schema = ";\n\n".join(r[0] for r in ddl) + f";\n\nPRAGMA user_version = {version};\n"
    finally:
        out.close()
    return counts, version, schema


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _file(path: Path, known: dict[str, File]) -> File:
    """An archive never changes once written: its hash from last night's manifest stands."""
    size = path.stat().st_size
    prior = known.get(path.name)
    if prior and prior.bytes == size:
        return prior
    return File(path.name, size, _sha256(path))


def _put(out_dir: Path, name: str, text: str) -> None:
    """Write a served file atomically: a reader never sees a torn one."""
    tmp = out_dir / f".{name}.tmp"
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out_dir / name)


def dump(
    db_path: Path, out_dir: Path, today: date | None = None, now: str | None = None
) -> Manifest:
    """Cut tonight's snapshot into `out_dir`: `docketyard-latest.sqlite.gz` always; the
    first cut of each month kept as a dated archive (whatever day it runs on — a missed
    first does not lose the month); plus `schema.sql`, the licence, and `index.json`
    measured from the files. The copy is built beside `out_dir`, never inside it."""
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir.parent / ".dump-work"  # not served
    work_dir.mkdir(exist_ok=True)
    prior = read_manifest(out_dir)
    known = {f.name: f for f in prior.dated} if prior else {}
    work = work_dir / "snapshot.sqlite"
    try:
        counts, version, schema = scrub(db_path, work)
        packed = work_dir / "snapshot.sqlite.gz"
        with open(work, "rb") as f, gzip.open(packed, "wb", compresslevel=9) as g:
            shutil.copyfileobj(f, g)
    finally:
        work.unlink(missing_ok=True)
    packed.replace(out_dir / LATEST)
    month = today.strftime("%Y-%m")
    dated: list[Path] = []
    have_month = any(p.name.startswith(f"docketyard-{month}-") for p in out_dir.glob(_DATED))
    if not have_month:
        shutil.copyfile(out_dir / LATEST, out_dir / f"docketyard-{today.isoformat()}.sqlite.gz")
    for p in out_dir.glob(_DATED):
        dated.append(p)
    _put(out_dir, SCHEMA, schema)
    _put(
        out_dir,
        "LICENSE.txt",
        resources.files("docketyard").joinpath("LICENSE-DATA.txt").read_text(encoding="utf-8"),
    )
    manifest = Manifest(
        built_at=now or utcnow(),
        licence=LICENCE,
        licence_url=LICENCE_URL,
        schema_version=version,
        counts=counts,
        omitted_tables=list(PRIVATE_TABLES),
        held_tables=list(HELD_TABLES),
        held_reason=HELD_REASON,
        latest=File(LATEST, (out_dir / LATEST).stat().st_size, _sha256(out_dir / LATEST)),
        dated=[_file(p, known) for p in sorted(dated, reverse=True)],
    )
    _put(out_dir, "index.json", json.dumps(asdict(manifest), indent=1))
    return manifest


def read_manifest(out_dir: Path) -> Manifest | None:
    p = out_dir / "index.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return Manifest(
            **{**d, "latest": File(**d["latest"]), "dated": [File(**f) for f in d["dated"]]}
        )
    except (ValueError, KeyError, TypeError):  # a manifest from another shape: not offered
        return None
