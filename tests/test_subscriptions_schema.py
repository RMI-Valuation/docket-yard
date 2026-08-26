"""Migrations 0004/0005: the subscription tables and the constraints the promises rest on."""

import sqlite3

import pytest

from docketyard.store import db


def _docket(con):
    return con.execute(
        "INSERT INTO docket (raw_docket, prefix, sequence) VALUES ('FD_36873', 'FD', 36873)"
    ).lastrowid


def _subscribe(con, email, docket_id, cadence="pass", status="pending", mark=None):
    return con.execute(
        "INSERT INTO subscription (email_hash, email_enc, docket_id, cadence, status,"
        " high_water_event_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, 't', ?)",
        (
            email,
            "enc:" + email,
            docket_id,
            cadence,
            status,
            mark,
            "t" if status == "pending" else None,
        ),
    ).lastrowid


def _event(con, docket_id):
    if not con.execute("SELECT COUNT(*) FROM capture").fetchone()[0]:
        con.execute(
            "INSERT INTO capture (source_system, endpoint, request_params, response_sha256,"
            " http_status, filter_asserted, ingest_mode, captured_at, table_action)"
            " VALUES ('s', 'e', '[]', 'x', 200, 1, 'forward', 't', 'a')"
        )
    cur = con.execute(
        "INSERT INTO event (event_type, docket_id, recorded_at, capture_id, source_key,"
        " payload, payload_version) VALUES ('filing_observed', ?, 't', 1, ?, '{}', 1)",
        (docket_id, f"k{con.execute('SELECT COUNT(*) FROM event').fetchone()[0]}"),
    )
    return cur.lastrowid


def _alert(con, status):
    return con.execute(
        "INSERT INTO alert (email_hash, email_enc, cadence, status, created_at) VALUES ('h', 'e',"
        " 'pass', ?, 't')",
        (status,),
    ).lastrowid


def _carry(con, alert_id, subscription_id, event_id):
    con.execute(
        "INSERT INTO alert_event (alert_id, subscription_id, event_id) VALUES (?, ?, ?)",
        (alert_id, subscription_id, event_id),
    )


def test_migration_applies_and_stamps():
    con = db.connect(":memory:")
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.MIGRATIONS[-1][0]
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"subscription", "subscription_token", "alert", "alert_event"} <= tables
    assert {"email_suppression", "coverage_gap"} <= tables


def test_one_live_subscription_per_address_and_docket():
    con = db.connect(":memory:")
    d = _docket(con)
    _subscribe(con, "a@example.org", d)
    with pytest.raises(sqlite3.IntegrityError):
        _subscribe(con, "a@example.org", d, cadence="daily")
    with pytest.raises(sqlite3.IntegrityError):  # cadence is a closed set
        _subscribe(con, "b@example.org", d, cadence="weekly")
    with pytest.raises(sqlite3.IntegrityError):  # there is no cancelled state to retain
        _subscribe(con, "c@example.org", d, status="cancelled")


def test_active_requires_a_high_water_mark():
    """An active row without a mark would alert the whole ledger; it is refused."""
    con = db.connect(":memory:")
    d = _docket(con)
    with pytest.raises(sqlite3.IntegrityError):
        _subscribe(con, "a@example.org", d, status="active")
    _subscribe(con, "a@example.org", d, status="active", mark=0)
    with pytest.raises(sqlite3.IntegrityError):  # and a pending row must carry its expiry
        con.execute(
            "INSERT INTO subscription (email_hash, email_enc, docket_id, cadence, status,"
            " created_at) VALUES ('b', 'e', ?, 'pass', 'pending', 't')",
            (d,),
        )


def test_an_event_reaches_a_subscription_at_most_once():
    con = db.connect(":memory:")
    d = _docket(con)
    s = _subscribe(con, "a@example.org", d, status="active", mark=0)
    e = _event(con, d)
    a1, a2 = (_alert(con, "pending") for _ in (1, 2))
    _carry(con, a1, s, e)
    with pytest.raises(sqlite3.IntegrityError):  # same event, a second alert, same subscriber
        _carry(con, a2, s, e)
    with pytest.raises(sqlite3.IntegrityError):  # 'sent' means a time and a provider id
        con.execute("UPDATE alert SET status = 'sent' WHERE alert_id = ?", (a1,))


def test_unsubscribe_cascades_tokens_and_alert_events():
    """ADR 0011: deleting the subscription takes its tokens and its docket-linked alert
    history with it. The address's `alert` rows are the unsubscribe code's job (no FK)."""
    con = db.connect(":memory:")
    d = _docket(con)
    s = _subscribe(con, "a@example.org", d, status="active", mark=0)
    e = _event(con, d)
    con.execute(
        "INSERT INTO subscription_token (token_sha256, subscription_id, purpose, created_at)"
        " VALUES ('hash', ?, 'unsubscribe', 't')",
        (s,),
    )
    with pytest.raises(sqlite3.IntegrityError):  # a confirmation link always expires
        con.execute(
            "INSERT INTO subscription_token (token_sha256, subscription_id, purpose, created_at)"
            " VALUES ('hash2', ?, 'confirm', 't')",
            (s,),
        )
    _carry(con, _alert(con, "pending"), s, e)
    con.execute("DELETE FROM subscription WHERE subscription_id = ?", (s,))
    assert con.execute("SELECT COUNT(*) FROM subscription_token").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM alert_event").fetchone()[0] == 0
    # the address may subscribe again as a brand-new row with a fresh mark
    _subscribe(con, "a@example.org", d)


def test_rebuilding_subscription_keeps_its_dependants(tmp_path):
    """Migration 0007 drops and recreates `subscription`; with foreign keys enforced that
    DROP would cascade into tokens and alert events (measured). The runner turns them off
    per script and checks integrity after."""
    path = tmp_path / "s.sqlite"
    con = db.connect(path, upto=6)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 6
    d = _docket(con)
    s = _subscribe(con, "h", d, status="active", mark=0)
    e = _event(con, d)
    con.execute(
        "INSERT INTO subscription_token (token_sha256, subscription_id, purpose, created_at)"
        " VALUES ('tok', ?, 'unsubscribe', 't')",
        (s,),
    )
    _carry(con, _alert(con, "pending"), s, e)
    con.commit()
    con.close()
    con = db.connect(path)  # migrates 6 -> 7
    assert con.execute("PRAGMA user_version").fetchone()[0] == 7
    assert con.execute("SELECT COUNT(*) FROM subscription_token").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM alert_event").fetchone()[0] == 1
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1  # enforcement is back on
    con.execute("DELETE FROM subscription WHERE subscription_id = ?", (s,))
    assert con.execute("SELECT COUNT(*) FROM subscription_token").fetchone()[0] == 0  # cascades
