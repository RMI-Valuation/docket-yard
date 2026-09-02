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
import json
import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from docketyard.capture import records
from docketyard.store.db import utcnow

PRIVATE_TABLES = (
    "alert_event",
    "alert",
    "subscription_token",
    "subscription",
    "email_suppression",
    # A reviewer is not a reader, but the row holds an address: `email_hash` and `email_enc`,
    # the same pair every other account carries (migration 0015, ADR 0016 under ADR 0014).
    # Never published, and `_SUSPECT_COLUMN` would fail the dump loudly if this were missed.
    "reviewer_token",
    "reviewer",
)
# Replication bookkeeping (Litestream keeps two tables in the store); not record, not published.
TOOL_TABLES = ("_litestream_lock", "_litestream_seq")
# VIEWS ARE NOT TABLES, and they need their own tuple for the second reason below rather than
# the first. `DROP TABLE` on a view RAISES — "use DROP VIEW to delete view <name>", and
# `IF EXISTS` does not suppress it, only "no such table" — so a held view mis-filed among the
# tables fails the dump loudly, which is the property we want. What it would NOT do is get
# noticed: the unknown check below enumerates `type = 'table'`, so an unclassified view was
# invisible, and the snapshot would ship a `CREATE VIEW` over a table it had just dropped.
# Migration 0018's display view selects from `document_text`, which is held, so it goes too.
HELD_VIEWS = ("document_text_display",)
# And the views that stay. `docket_current` has been in the snapshot since migration 0001 and
# had never been classified, because until the check below counted views there was nothing to
# classify it against — it is a projection over `docket` and `event`, both public, so it was
# right by luck rather than by decision. Named now, which is the point of an allowlist.
PUBLIC_VIEWS = frozenset({"docket_current"})
# The search index (migrations 0010 and 0012): derived, rebuilt from the record when it
# changes, and it carries party names — the held layer — so the snapshot ships it EMPTY: the
# tables stay (a restored copy is at the release's schema and `docketyard search rebuild`
# remakes it), the rows go.
DERIVED_TABLES = ("search_doc", "search_meta")
# The FTS index's tables are not listed by hand: SQLite names an FTS5 virtual table's
# shadows `<name>_<suffix>` and may change the set between versions, so `scrub` derives
# them from `PRAGMA table_list` instead — a renamed shadow would otherwise fail the
# allowlist on the next SQLite upgrade (deferred 2026-08-26). Only rows SQLite itself
# types `shadow` qualify: a hand-made `CREATE TABLE search_fts_anything`, or a second FTS
# index over held data, is type `table`/`virtual` and still fails the dump loudly.
# Derived work held back pending the enriched-layer licence review (docs/licensing.md).
# The citator block (migration 0014) is the enriched layer this module's own docstring
# already promised would join the party module here; it ships EMPTY today, and holding it
# back now means the licence question is answered before an edge is published rather than
# after. Listed children before parents: `scrub` drops with foreign keys OFF, so the order
# is not required today — it is kept so the list stays correct if that ever changes.
HELD_TABLES = (
    # Migration 0018, ADR 0022 D3. A machine transcription of a US government work is a
    # derived assertion with a measured error rate, not the Board's own words, and
    # `licensing.md` places it in neither of its two buckets — so it is held while that
    # question is open. Held can become public later; public cannot become held.
    #
    # `page_fts` is held rather than emptied because only held is SAFE for it: emptied and
    # rebuilt errors on an external-content index whose content view has just been dropped,
    # and its surviving %_data/%_idx shadows would hold a positional inverted index from
    # which the withheld text is largely reconstructible. Dropping takes the shadows with it.
    #
    # `text_payload` holds digests of blob-tier objects that carry that same text, so
    # publishing it would name the withheld artefacts one indirection away.
    "page_fts",
    "document_text",
    # its only referrer is `document_text`, so publishing it would ship an orphan taxonomy of
    # the held layer's own method. The tiers are public on /methodology; the table is not.
    "route_class_vocab",
    "text_payload",
    "filing_party_link",
    "filing_party_span",
    "party_relationship",
    "relationship_vocab",
    "party_name",
    "party",
    # ADR 0016 publishes a reviewer's CREDIT NAME beside a reviewed assertion, and counts
    # per reviewer only on opt-in. `review_action` is one row per decision, so publishing it
    # would give a per-reviewer count nobody consented to — and it is provenance about the
    # held citator layer besides, so it is held with it.
    "review_action",
    "review_decision_vocab",
    "review_queue_vocab",
    "review_target_vocab",
    "citation_treatment",
    "citation_judgement",
    "citation_resolution",
    "citation_reading",
    "citation",
    "citation_key",
    "decision_decided_date",
    "extraction_run",
    "assertion_method",
    "class_measurement",
    "class_vocab",
    "measured_target_vocab",
    "judgement_value_vocab",
    "judgement_vocab",
    "treatment_vocab",
    "outcome_vocab",
    "date_kind_vocab",
    "reading_vocab",
    "target_kind_vocab",
    "decision_work",
)
HELD_REASON = (
    "The party module (entity resolution, aliases, successions) and the citator (citation"
    " edges, their readings, resolutions and judgements) are derived work whose licence"
    " awaits review; they are withheld until then, not dedicated by default."
)
PUBLIC_TABLES = frozenset(
    {
        *DERIVED_TABLES,  # present and empty, see above
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
        # Migration 0018, ADR 0022 D3. Pagination of a federal document, carrying its own
        # method, version and timestamp — it publishes WITH its provenance, which is what a
        # per-page table without one would not have done. `ocr_run` says which documents are
        # image-only and which reads failed, which is coverage and belongs beside
        # `coverage_gap`. Their vocabularies come with them or the DDL does not load.
        "document_pagination",
        "pagination_outcome_vocab",
        "ocr_run",
        "run_outcome_vocab",
        "correction",
        "enviro_comment",
        "enviro_comment_attachment",
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
        # Tables first, then views: an external-content FTS5 index names its content source,
        # so `page_fts` goes before `document_text_display` does. FTS5's xDestroy does not
        # read the source, so the order is not load-bearing today — it is free insurance
        # against a future index that does.
        for table in PRIVATE_TABLES + HELD_TABLES + TOOL_TABLES:
            out.execute(f"DROP TABLE IF EXISTS {table}")
        for view in HELD_VIEWS:
            out.execute(f"DROP VIEW IF EXISTS {view}")
        # A correction NAMES the row it amends, and since migration 0014 it names it by the
        # row's own key — `<sha256>/<page>/<target_kind>/<target_key>` for a citation. So a
        # correction against a held table republishes the held row's identity through a
        # table that stays public. Dropping the parent is not enough; the pointer has to go
        # with it. (The party module has the same shape with an opaque integer, which says
        # less but is the same leak.)
        out.executemany(
            "DELETE FROM correction WHERE target_table = ?", [(t,) for t in HELD_TABLES]
        )
        for table in DERIVED_TABLES:
            out.execute(f"DELETE FROM {table}")
        out.execute("INSERT INTO search_fts (search_fts) VALUES ('rebuild')")  # now empty
        out.commit()
        out.execute("VACUUM")
        q = out.execute
        # Views are enumerated beside tables, so an unclassified one raises `Unsafe` like
        # anything else. Before migration 0018 the store held none and this read `type =
        # 'table'`; a view over a dropped table is a broken `schema.sql` and the check that
        # exists to catch exactly that could not see it.
        left = {
            r[0]
            for r in q("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
            if not r[0].startswith("sqlite_")
        }
        # the FTS index and its shadows (see the note above PUBLIC_TABLES): `search_fts`
        # itself, plus rows PRAGMA table_list types `shadow` under its prefix — a type only
        # SQLite mints. Anything else named into that namespace stays on the unknown list.
        shadows = {"search_fts"} & left
        shadows |= {
            name
            for _, name, kind, *_ in q("PRAGMA table_list")
            if kind == "shadow" and name.startswith("search_fts_")
        }
        unknown = left - PUBLIC_TABLES - PUBLIC_VIEWS - shadows
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
            # by (number, row ref): the row ref folds a comment entered in a docket and
            # its sub-docket, and keeps apart the two numbers the Board gave to two
            # different comments — the number alone is not unique (measured)
            "environmental_comments": q(
                "SELECT COUNT(*) FROM (SELECT 1 FROM enviro_comment"
                " GROUP BY comment_number, COALESCE(stb_row_ref, ''))"
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
    return records.sha256_of_file(path)


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
