"""SQLite connection, the migration runner, and the one JSON codec.

Migrations are monotonic (ADR 0010) and stamped via PRAGMA user_version *inside* each
script's own transaction, so an interrupted migration rolls back whole. A script is applied
once and never edited afterwards — schema change means a new numbered script.
"""

import json
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from sqlite3 import Connection
from sqlite3 import connect as _connect

MIGRATIONS: list[tuple[int, str]] = [
    (1, "schema.sql"),
    (2, "0002_filings_decisions.sql"),
    (3, "0003_walk_slices.sql"),
    (4, "0004_subscriptions.sql"),
    (5, "0005_encrypted_addresses.sql"),
    (6, "0006_parties.sql"),
    (7, "0007_party_subscriptions.sql"),
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
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA foreign_keys = ON")
    migrate(con, upto=upto)
    return con


def migrate(con: Connection, upto: int | None = None) -> int:
    """Apply every migration above the stamped version (or up to `upto`, for tests that
    build an older store). Foreign-key enforcement is OFF while a script runs — SQLite's
    documented rebuild procedure: with it on, `DROP TABLE` of a parent cascades into its
    children and silently empties them — and `foreign_key_check` must be clean after."""
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
            sql = resources.files("docketyard.store").joinpath(script).read_text(encoding="utf-8")
            con.executescript(sql)
            stamped = con.execute("PRAGMA user_version").fetchone()[0]
            if stamped != version:
                raise RuntimeError(f"migration {script} did not stamp user_version {version}")
            broken = con.execute("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise RuntimeError(f"migration {script} left dangling foreign keys: {broken[:5]}")
            applied = version
    finally:
        con.execute("PRAGMA foreign_keys = ON")
    con.commit()
    return applied
