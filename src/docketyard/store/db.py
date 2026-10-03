"""SQLite connection, the migration runner, and the one JSON codec.

Migrations are monotonic (ADR 0010) and stamped via PRAGMA user_version *inside* each
script's own transaction, so an interrupted migration rolls back whole. A script is applied
once and never edited afterwards — schema change means a new numbered script.
"""

import json
import re
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from sqlite3 import Connection
from sqlite3 import connect as _connect

from docketyard.store import display

# CONTIGUOUS 1..N, IN ORDER, and `migrate` refuses anything else before applying a script. It
# skips every version at or below the stamp, so a branch that registers 0032 ahead of 0030 and
# 0031 would stamp a store at 32 and leave those two unapplied for ever.
MIGRATIONS: list[tuple[int, str]] = [
    (1, "schema.sql"),
    (2, "0002_filings_decisions.sql"),
    (3, "0003_walk_slices.sql"),
    (4, "0004_subscriptions.sql"),
    (5, "0005_encrypted_addresses.sql"),
    (6, "0006_parties.sql"),
    (7, "0007_party_subscriptions.sql"),
    (8, "0008_webhooks.sql"),
    (9, "0009_party_ids_permanent.sql"),
    (10, "0010_search.sql"),
    (11, "0011_enviro_comments.sql"),
    (12, "0012_search_comments.sql"),
    (13, "0013_search_caption.sql"),
    (14, "0014_citations.sql"),
    (15, "0015_review.sql"),
    (16, "0016_citation_kind.sql"),
    (17, "0017_reviewer_sessions.sql"),
    (18, "0018_document_text.sql"),
    (19, "0019_decided_date_rebuild.sql"),
    (20, "0020_display_mask.sql"),
    (21, "0021_attachment_by_document.sql"),
    (22, "0022_not_paginable_run.sql"),
    # 0023 is DRAFTED AGAINST A PROPOSED ADR (0024). It is registered, because there is
    # no mechanism to hold a migration back and pretending otherwise is how a header
    # comes to state a rule the code does not enforce. The gate is the DEPLOY: the
    # nightly dump publishes its table under CC0, so shipping it freezes a shape ADR
    # 0024 has not yet been accepted to justify.
    (23, "0023_extraction_dispatch.sql"),
    # 0024 is ADR 0024 § Owed 1 and carries the same deploy gate as 0023: its table is
    # public, so shipping it freezes a shape the Proposed ADR has not been accepted to
    # justify. It ships EMPTY either way — nothing declares a pin yet.
    (24, "0024_producer_declaration.sql"),
    # 0025 admits ('citation_resolution', 'work') to the class vocabulary so the work column
    # of the sixty-decision sheet can be declared when it is checked. It writes no
    # measurement, so the work grain stays shut the day it applies.
    (25, "0025_work_class.sql"),
    # 0026 settles ADR 0024 § Owed 5: `ocr_run.dispatch_id`, stamped by the stage from what the
    # container quoted, so the halt is a proof. Deploy by infra/deploy/README.md: stop
    # `extract`, let one pass land the old container's records, stop `ingest`, then migrate.
    (26, "0026_ocr_run_dispatch.sql"),
    # 0027 indexes `enviro_comment_attachment` by document, as 0021 did its two siblings: a
    # comment's attachment was given a text address on 2026-09-11, so page search asks it.
    (27, "0027_comment_attachment_by_document.sql"),
    # 0028 applies ADR 0026 (Accepted 2026-09-12): a citation reading names the text it read.
    # A REBUILD of `citation_reading` — `text_id`, `text_ref`, `superseded_at` and the spans'
    # own method — because an ALTER can add a column but cannot constrain one on a table that
    # already holds retired rows, nor correct 0014's declared `source_location` shape, which
    # SQLite keeps verbatim in `sqlite_master`. MIGRATING, so it goes behind the wall
    # (ADR 0020); the pass that fills `text_id` and the spans is a separate RE-LOAD.
    (28, "0028_reading_names_its_text.sql"),
    # 0029 applies ADR 0018's addendum (Accepted 2026-09-13): a retraction retires the key's
    # readings too, each with a retirement row, and the 903 already stranded are retired here.
    # MIGRATING, so it goes behind the wall; a key a person decided aborts it whole, and the
    # runbook's pre-check (`infra/deploy/0029-precheck.sql`) names that key first.
    (29, "0029_retire_retracted_readings.sql"),
    # 0030 pays migration 0014's owed item 7: the veto's trigger (ADR 0018 D7; addendum of
    # 2026-09-15, accepted 2026-09-16). Triggers only, on held tables; a store already holding a
    # violation refuses it whole.
    (30, "0030_veto_trigger.sql"),
    # 0031 settles ADR 0024 § Owed 2's second half (addendum 2026-09-15, accepted
    # 2026-09-16): a row per page a pass failed, under its `ocr_run`, with a reason from a
    # vocabulary that says whether the failure is the page's own. ADDITIVE — two tables, no
    # rebuild — so not behind the wall.
    # MERGE AND DEPLOY IN NUMBER ORDER: `migrate` skips every version <= the stamped one, so a
    # store already stamped 32 by a branch merged first would never apply 0031, and nothing
    # here would say so.
    (31, "0031_ocr_page_failure.sql"),
    # 0032 applies ADR 0021's addendum (2026-09-15, accepted 2026-09-16): the router's verdict as
    # its own page-grain assertion, so a tabular page no engine read can say so. A new held table
    # and no rebuild. Deploy after 0030 and 0031, never before: `migrate` skips any number at or
    # below the stamped version.
    (32, "0032_page_route.sql"),
    # 0033 rebuilds the search index to place a record in every proceeding it was entered in,
    # with filings and every decision indexed (docs/search-v2.md). Derived and disposable; the
    # next pass rebuilds it.
    (33, "0033_search_placements.sql"),
    # 0034 rebuilds `decision_decided_date` (0 rows everywhere) for the ADR 0023 addendum of
    # 2026-09-16: the page in the key, the text a quotation read. Written as 0033 and renumbered
    # at acceptance, 0033 having shipped first. A store holding rows refuses it.
    (34, "0034_decided_date_page_key.sql"),
]


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def dump_json(value) -> str:
    """The single JSON encoder for persisted columns — stable text, comparable bytes."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def load_json(text: str):
    return json.loads(text)


def connect(path: str | Path, upto: int | None = None) -> Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = _connect(path, timeout=30)  # a wave and the poller share the store; wait, do not fail
    display.register(con)  # the display view needs it, and migration 0020 creates that view
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA foreign_keys = ON")
    migrate(con, upto=upto)
    return con


def _script(name: str) -> str:
    return resources.files("docketyard.store").joinpath(name).read_text(encoding="utf-8")


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _schema(con: Connection) -> dict[tuple[str, str], tuple[str, str | None]]:
    """Every schema object, `(type, lower name) -> (lower tbl_name, sql)`, for `_fk_scope` —
    the TEMP schema too, prefixed `temp.`: a `CREATE TEMP TRIGGER ... ON main.t` an earlier
    script left on this connection fires into tables a later script never names, and lives in
    `sqlite_temp_master`, not `sqlite_master` (schema-critic, 2026-10-03)."""
    out = {}
    for prefix, master in (("", "sqlite_master"), ("temp.", "sqlite_temp_master")):
        for kind, name, table, sql in con.execute(
            f"SELECT type, name, tbl_name, sql FROM {master}"
        ):
            out[(kind, prefix + name.lower())] = (table.lower(), sql)
    return out


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _needs_full_check(script: str, before: dict, after: dict) -> bool:
    """Where `_fk_scope`'s over-approximation does not reach, the full check runs instead
    (schema-critic, 2026-10-03): a script touching `writable_schema` can move a table's
    contents with no name in its text and no visible DDL diff; and a table whose name is not a
    plain word (`"doc ument"`, `café`) is invisible to the word match. Neither occurs in this
    store's migrations, so this never costs the five minutes it saves elsewhere."""
    if "writable_schema" in script.lower():
        return True
    names = {name.removeprefix("temp.") for (_, name) in (*before, *after)}
    return any(not _WORD.fullmatch(n) for n in names if not n.startswith("sqlite_"))


def _fk_scope(con: Connection, script: str, before: dict) -> list[str]:
    """The tables a script COULD have left with a dangling foreign key, so `migrate` checks
    those and not the whole store: `PRAGMA foreign_key_check` unscoped was 280 s a script on
    the 4.28 GB production copy (measured 2026-09-10), fifteen minutes behind the wall for a
    three-migration release, mostly spent on tables the scripts never touched (deferred.md,
    the release review of v2026.09.10..HEAD).

    SOUND BY OVER-APPROXIMATION, never by parsing SQL. With enforcement off, a script can
    break a reference only by writing a row: into a CHILD (a reference to nothing), or out of
    a PARENT (a delete, an update of the key, a drop-and-rebuild), which strands the parent's
    children. Cascades do not run with enforcement off, so the rows written are those of
    tables the script reaches, and it reaches a table by naming it or through a trigger. So:

    1. every table or view whose name appears as a WORD anywhere in the script — comments
       included, which costs a check and never misses one;
    2. every object whose DDL the script created, dropped or changed (an `ALTER TABLE ...
       RENAME` rewrites references in other tables' DDL), by its table;
    3. closed over TRIGGERS, before the script and after it (a trigger it fired and then
       dropped still wrote): a trigger on a table in scope brings in every name in its body;
    4. then every table holding a foreign key to anything in scope — the children a parent's
       write could strand. Not iterated: a child is checked, not written.
    """
    after = _schema(con)
    objects = {
        name.removeprefix("temp.")
        for (kind, name) in (*before, *after)
        if kind in ("table", "view")
    }
    scope = {w.lower() for w in _WORD.findall(script)} & objects
    scope |= {
        table
        for key in before.keys() | after.keys()
        if before.get(key) != after.get(key)
        for table in (before.get(key, (None,))[0], after.get(key, (None,))[0])
        if table
    }
    triggers = [
        (table, sql or "")
        for schema in (before, after)
        for (kind, _), (table, sql) in schema.items()
        if kind == "trigger"
    ]
    grew = True
    while grew:
        reached = {
            w.lower() for table, sql in triggers if table in scope for w in _WORD.findall(sql)
        } & objects
        grew = not reached <= scope
        scope |= reached
    tables = sorted(
        name for (kind, name) in after if kind == "table" and not name.startswith("temp.")
    )
    children = {
        child
        for child in tables
        for row in con.execute(f"PRAGMA main.foreign_key_list({_quoted(child)})")
        if row[2].lower() in scope
    }
    return [t for t in tables if t in scope | children]


def migrate(con: Connection, upto: int | None = None) -> int:
    """Apply every migration above the stamped version (or up to `upto`, for tests that
    build an older store). Foreign-key enforcement is OFF while a script runs — SQLite's
    documented rebuild procedure: with it on, `DROP TABLE` of a parent cascades into its
    children and silently empties them — and `foreign_key_check` must be clean after."""
    versions = [version for version, _ in MIGRATIONS]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError(
            f"MIGRATIONS must be numbered contiguously 1..N in order, and is {versions}: a"
            " version registered past a gap stamps the store beyond it, and the gap is then"
            " skipped for ever. Nothing was applied."
        )
    applied = con.execute("PRAGMA user_version").fetchone()[0]
    if applied == 0:
        tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'")
        if tables.fetchone()[0]:
            raise RuntimeError(
                "database has tables but no schema version — not a docketyard store, or a"
                " partially written one. data/ is disposable: delete it and re-run."
            )
    con.commit()  # the pragma is a no-op inside a transaction
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        for version, script in MIGRATIONS:
            if version <= applied or (upto is not None and version > upto):
                continue
            text = _script(script)
            before = _schema(con)
            con.executescript(text)
            stamped = con.execute("PRAGMA user_version").fetchone()[0]
            if stamped != version:
                raise RuntimeError(f"migration {script} did not stamp user_version {version}")
            if _needs_full_check(text, before, _schema(con)):
                broken = con.execute("PRAGMA main.foreign_key_check").fetchall()
            else:
                broken = [
                    row
                    for table in _fk_scope(con, text, before)
                    for row in con.execute(
                        f"PRAGMA main.foreign_key_check({_quoted(table)})"
                    ).fetchall()
                ]
            if broken:
                raise RuntimeError(f"migration {script} left dangling foreign keys: {broken[:5]}")
            applied = version
    except BaseException:
        # A statement that fails to PARSE partway raises with the script's own `BEGIN` still
        # open, and a caller that kept the connection and committed would keep whatever ran
        # before it — a half-applied migration under an unchanged `user_version` (the schema
        # critic, 2026-09-13; production is safe only because `migrate`'s connection closes).
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")
    con.commit()
    return applied
