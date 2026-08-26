"""The bulk snapshot: the public record as one SQLite file, cut nightly (M9, capability F5).

What leaves the box is a copy of the store with every table that could name a reader
dropped — subscriptions, tokens, alerts, suppression — *including their ciphertext* (ADR
0011, 0014: nothing about a reader is published, readable or not). Everything else is the
record itself and its provenance, rebuildable from the Board's own files. The manifest
(`index.json`) is measured from the file it describes; the page that offers the download
is generated from the manifest, so it cannot claim a file that is not there.

Data licence: CC0 1.0 (the operator's decision, 2026-08-26) — the Board's records are U.S.
government works and the compilation is dedicated to the public domain.
"""

import gzip
import hashlib
import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from importlib import resources
from pathlib import Path

PRIVATE_TABLES = (
    "alert_event",
    "alert",
    "subscription_token",
    "subscription",
    "email_suppression",
)
LATEST = "docketyard-latest.sqlite.gz"
LICENCE = "CC0-1.0"
LICENCE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"


@dataclass(frozen=True)
class File:
    name: str
    bytes: int
    sha256: str
    built_at: str  # ISO UTC


@dataclass(frozen=True)
class Manifest:
    built_at: str
    licence: str
    licence_url: str
    schema_version: int
    counts: dict  # measured from the snapshot itself
    omitted_tables: list[str]
    latest: File
    dated: list[File]  # kept archives, newest first
    schema: str  # file name


def scrub(src: Path, dst: Path) -> None:
    """A consistent copy of the store with the private tables gone and the space reclaimed."""
    if dst.exists():
        dst.unlink()
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        con.execute("VACUUM INTO ?", (str(dst),))
    finally:
        con.close()
    out = sqlite3.connect(dst)
    try:
        out.execute("PRAGMA foreign_keys = OFF")
        for table in PRIVATE_TABLES:
            out.execute(f"DROP TABLE IF EXISTS {table}")
        out.commit()
        out.execute("VACUUM")
        left = {r[0] for r in out.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert not left & set(PRIVATE_TABLES), "a private table survived the scrub"
    finally:
        out.close()


def _counts(path: Path) -> dict:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {
            "dockets": con.execute("SELECT COUNT(*) FROM docket").fetchone()[0],
            "filings": con.execute("SELECT COUNT(DISTINCT stb_filing_id) FROM filing").fetchone()[
                0
            ],
            "decisions": con.execute(
                "SELECT COUNT(DISTINCT stb_decision_id) FROM decision_record"
            ).fetchone()[0],
            "events": con.execute("SELECT COUNT(*) FROM event").fetchone()[0],
            "documents": con.execute("SELECT COUNT(*) FROM document").fetchone()[0],
            "parties": con.execute("SELECT COUNT(*) FROM party").fetchone()[0],
            "schema_version": con.execute("PRAGMA user_version").fetchone()[0],
        }
    finally:
        con.close()


def _schema_sql(path: Path) -> str:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"
            " ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, name"
        ).fetchall()
    finally:
        con.close()
    return ";\n\n".join(r[0] for r in rows) + ";\n"


def _gzip(src: Path, dst: Path) -> None:
    with open(src, "rb") as f, gzip.open(dst, "wb", compresslevel=6) as g:
        shutil.copyfileobj(f, g)


def _file(path: Path, built_at: str) -> File:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return File(path.name, path.stat().st_size, h.hexdigest(), built_at)


def dump(
    db_path: Path, out_dir: Path, today: date | None = None, now: str | None = None
) -> Manifest:
    """Cut tonight's snapshot into `out_dir`: `docketyard-latest.sqlite.gz` always; a dated
    copy kept when today is the first of a month (older dated copies from other days are
    removed), plus `schema.sql`, the licence, and `index.json` measured from the files."""
    today = today or date.today()
    built_at = now or datetime.now(UTC).isoformat(timespec="seconds")
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / ".building.sqlite"
    scrub(db_path, work)
    counts = _counts(work)
    dated_name = f"docketyard-{today.isoformat()}.sqlite.gz"
    tmp = out_dir / ".building.sqlite.gz"
    _gzip(work, tmp)
    work.unlink()
    tmp.replace(out_dir / LATEST)
    if today.day == 1:
        shutil.copyfile(out_dir / LATEST, out_dir / dated_name)
    for old in out_dir.glob("docketyard-????-??-??.sqlite.gz"):
        if old.name != dated_name and not old.name.endswith("-01.sqlite.gz"):
            old.unlink()
    (out_dir / "schema.sql").write_text(_schema_sql(db_path), encoding="utf-8", newline="\n")
    (out_dir / "LICENSE.txt").write_text(
        resources.files("docketyard").joinpath("LICENSE-DATA.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    dated = sorted(out_dir.glob("docketyard-????-??-??.sqlite.gz"), reverse=True)
    manifest = Manifest(
        built_at=built_at,
        licence=LICENCE,
        licence_url=LICENCE_URL,
        schema_version=counts.pop("schema_version"),
        counts=counts,
        omitted_tables=list(PRIVATE_TABLES),
        latest=_file(out_dir / LATEST, built_at),
        dated=[_file(p, built_at) for p in dated],
        schema="schema.sql",
    )
    (out_dir / "index.json").write_text(
        json.dumps(asdict(manifest), indent=1), encoding="utf-8", newline="\n"
    )
    return manifest


def read_manifest(out_dir: Path) -> Manifest | None:
    p = out_dir / "index.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return Manifest(
        built_at=d["built_at"],
        licence=d["licence"],
        licence_url=d["licence_url"],
        schema_version=d["schema_version"],
        counts=d["counts"],
        omitted_tables=d["omitted_tables"],
        latest=File(**d["latest"]),
        dated=[File(**f) for f in d["dated"]],
        schema=d["schema"],
    )
