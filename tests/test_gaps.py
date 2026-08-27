"""The operator's record of an outage: open, close, listed on /coverage, cited by the late
alert entries it covers — and refused when it would say something untrue."""

import pytest
from fastapi.testclient import TestClient

from docketyard import cli
from docketyard.store import db, gaps
from docketyard.web.app import create_app
from tests.test_web import build_store


def test_a_gap_is_recorded_then_closed_and_shown(tmp_path, capsys):
    path = build_store(tmp_path)
    con = db.connect(path)
    gid = gaps.open_gap(con, "captures", since="2026-08-26T00:30", note="poller crashed")
    assert gaps.get(con, gid).started_at == "2026-08-26T00:30:00+00:00"  # naive = UTC
    with pytest.raises(ValueError, match="still open"):
        gaps.open_gap(con, "captures")
    with pytest.raises(ValueError, match="cannot end before"):
        gaps.close_gap(con, gid, at="2026-08-25T00:00")
    with pytest.raises(ValueError, match="address"):
        gaps.open_gap(con, "delivery", note="mail to cam@example.org bounced")
    with pytest.raises(ValueError, match="future"):
        gaps.open_gap(con, "delivery", since="2999-01-01")
    with pytest.raises(ValueError, match="ISO"):
        gaps.open_gap(con, "delivery", since="yesterday")
    with pytest.raises(ValueError, match="one of"):
        gaps.open_gap(con, "weather")
    page = TestClient(create_app(path)).get("/coverage").text
    assert "poller crashed" in page and "open" in page
    row = gaps.close_gap(con, gid, at="2026-08-26T02:00:00-04:00")
    assert row.ended_at == "2026-08-26T06:00:00+00:00"  # normalised to UTC
    with pytest.raises(ValueError, match="was closed"):
        gaps.close_gap(con, gid)
    assert [g.gap_id for g in gaps.list_gaps(con)] == [gid]
    con.close()
    # the CLI is the same module, and refuses the same way
    db_arg = ["--db", str(path)]
    assert cli.main(db_arg + ["gap", "open", "documents", "--note", "S3 sync stalled"]) == 0
    assert cli.main(db_arg + ["gap", "open", "documents"]) == 1
    out = capsys.readouterr().out
    assert "gap 2 open: documents" in out and "refused: gap 2 for documents is still open" in out
    assert cli.main(db_arg + ["gap", "close", "2"]) == 0
    assert cli.main(db_arg + ["gap", "list"]) == 0
    assert "documents" in capsys.readouterr().out


def test_a_recorded_gap_is_cited_by_the_late_entries_it_covers(tmp_path):
    """The catch-up alert may be built before the operator records the gap: recording it
    afterwards still points the late entries at it."""
    path = build_store(tmp_path)
    con = db.connect(path)
    captured = con.execute("SELECT MIN(captured_at) FROM capture").fetchone()[0]
    event_id = con.execute("SELECT MIN(event_id) FROM event").fetchone()[0]
    # a late alert entry that cites nothing (built before the gap was recorded)
    sub = con.execute(
        "INSERT INTO subscription (email_hash, email_enc, docket_id, cadence, status,"
        " high_water_event_id, created_at) VALUES ('h', 'c', 1, 'pass', 'active', 0, ?)"
        " RETURNING subscription_id",
        (captured,),
    ).fetchone()[0]
    alert = con.execute(
        "INSERT INTO alert (email_hash, email_enc, cadence, status, created_at, sent_at,"
        " message_id) VALUES ('h', 'c', 'pass', 'sent', ?, ?, 'm') RETURNING alert_id",
        (captured, captured),
    ).fetchone()[0]
    con.execute(
        "INSERT INTO alert_event (alert_id, subscription_id, event_id, late) VALUES (?, ?, ?, 1)",
        (alert, sub, event_id),
    )
    con.commit()
    cited = lambda: con.execute("SELECT late_gap_id FROM alert_event").fetchone()[0]  # noqa: E731
    gid = gaps.open_gap(con, "captures", since="2000-01-01")
    assert cited() == gid
    # a documents gap covers no entry, and an entry already cited keeps its citation
    other = gaps.open_gap(con, "documents", since="2000-01-01")
    assert gaps.cite(con, other) == 0 and cited() == gid
    # the catch-up capture runs AFTER the outage ends: closing the gap at the true end
    # still cites it (within the lateness threshold) ...
    from datetime import datetime, timedelta

    t = datetime.fromisoformat(captured)
    gaps.close_gap(con, gid, at=(t - timedelta(hours=1)).isoformat())
    assert cited() == gid
    # ... but an end too far before the capture releases the entry for a later gap
    con.execute(
        "UPDATE coverage_gap SET ended_at = ? WHERE gap_id = ?",
        ((t - timedelta(hours=5)).isoformat(), gid),
    )
    assert gaps.cite(con, gid) == 0 and cited() is None
    later = gaps.open_gap(con, "captures", since=(t - timedelta(hours=2)).isoformat())
    assert cited() == later
