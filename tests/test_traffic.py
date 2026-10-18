"""Hourly counts with no identifier (docs/traffic.md): the middleware counts kind of page,
status class, size, speed and crawler-or-not, and forgets the request; the numbers go to a
file beside the store, never into it; old hours fold into days."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from docketyard.store import traffic
from docketyard.web.app import create_app
from tests.test_alerts import FakeSender
from tests.test_web import build_store


def test_route_classes_carry_no_identifier():
    assert traffic.route_class("/d/FD-36873") == "sheet"
    assert traffic.route_class("/d/FD-36873/sub/1.json") == "json"
    assert traffic.route_class("/d/FD-36873/feed") == "feed"
    assert traffic.route_class("/p/3") == "party" and traffic.route_class("/p/3/feed") == "feed"
    assert traffic.route_class("/filing/311981") == "record"
    assert traffic.route_class("/search") == traffic.route_class("/suggest") == "search"
    assert traffic.route_class("/s/confirm/abc") == "subscribe"
    assert traffic.route_class("/about") == "trust" and traffic.route_class("/zzz") == "other"
    assert traffic.is_bot("Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert traffic.is_bot("Python-urllib/3.12")  # the compose healthcheck
    assert not traffic.is_bot("Mozilla/5.0 (Windows NT 10.0) Firefox/128.0")
    assert not traffic.is_bot(None)  # a stripped User-Agent is a reader


def test_counts_are_aggregates_and_fold_into_days(tmp_path):
    path = build_store(tmp_path)
    counts = tmp_path / "traffic.sqlite"
    app = create_app(path, traffic_path=counts)
    with TestClient(app) as client:
        client.get("/d/FD-36873", headers={"User-Agent": "Firefox/128"})
        client.get("/d/FD-36873/sub/1", headers={"User-Agent": "Firefox/128"})
        client.get("/p/999999", headers={"User-Agent": "Googlebot"})
        client.get("/search", params={"q": "peoria"}, headers={"User-Agent": "Firefox/128"})
        client.head("/d/FD-36873", headers={"User-Agent": "curl/8.0"})
        now = datetime.now(UTC)
        assert traffic.flush(app.state.traffic, counts, now) >= 3
    con = traffic.connect(counts)
    rows = con.execute(
        "SELECT route_class, status_class, bot, requests FROM traffic_hour ORDER BY 1, 2, 3"
    ).fetchall()
    assert ("sheet", "2xx", 0, 2) in rows and ("party", "4xx", 1, 1) in rows
    assert ("search", "2xx", 0, 1) in rows
    # sizes are rounded up to the grain before summing: an exact length would name a page
    assert (
        con.execute(
            "SELECT bytes FROM traffic_hour WHERE route_class = 'sheet' AND bot = 0"
        ).fetchone()[0]
        == 2 * traffic.SIZE_GRAIN
    )
    # a HEAD is a request with no bytes sent
    assert con.execute(
        "SELECT requests, bytes FROM traffic_hour WHERE route_class = 'sheet' AND bot = 1"
    ).fetchone() == (1, 0)
    cols = {r[1] for r in con.execute("PRAGMA table_info(traffic_hour)")}
    assert not cols & {"path", "ip", "user_agent", "referer", "query"}  # nothing else exists
    # a second flush of the same hour adds to the row; a restart never loses a row's hour
    app.state.traffic.record("/d/FD-1", 200, 10, 5.0, "Firefox", now)
    traffic.flush(app.state.traffic, counts, now)
    assert (
        con.execute("SELECT requests FROM traffic_hour WHERE route_class = 'sheet'").fetchone()[0]
        == 3
    )
    # fold: hourly rows older than the retention become daily rows, summed
    old = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H")
    traffic.write(con, [(old, "sheet", "2xx", 0, 5, 500, 5, 0, 0, 0)])
    assert traffic.fold(con, now) == 1
    assert con.execute("SELECT requests FROM traffic_day").fetchone() == (5,)
    left = con.execute("SELECT COUNT(*) FROM traffic_hour WHERE hour = ?", (old,)).fetchone()
    assert left == (0,)
    con.close()
    report = traffic.report(counts, days=1)
    assert report[0][0] == "sheet" and report[0][1] == 3  # readers, not crawlers, lead
    # the daily rows count in a long report
    long = {r[0]: r[1] for r in traffic.report(counts, days=120)}
    assert long["sheet"] == 8
    # a failed write gives the rows back
    app.state.traffic.record("/", 200, 1, 1.0, "Firefox", now)
    try:
        traffic.flush(app.state.traffic, tmp_path / "no-such-dir" / "t.sqlite", now)
    except Exception:  # noqa: BLE001
        pass
    assert app.state.traffic.drain() != []


def test_an_unhandled_error_is_counted_as_a_5xx(tmp_path):
    path = build_store(tmp_path)
    counts = tmp_path / "traffic.sqlite"
    app = create_app(path, traffic_path=counts)

    @app.get("/boom")
    def boom():
        raise RuntimeError("x")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/boom", headers={"User-Agent": "Firefox"}).status_code == 500
        rows = app.state.traffic.drain()  # before the shutdown flush takes them
    assert any(r[1] == "other" and r[2] == "5xx" for r in rows)


def test_a_mounted_file_is_counted_as_its_own_class(tmp_path):
    """A mount rewrites the scope's root_path as it routes, so the path read after the
    response was `/site.css` and every asset counted as `other` — production held no
    `static` row at all until 2026-10-13. The path is taken before the app sees it."""
    path = build_store(tmp_path)
    app = create_app(path, traffic_path=tmp_path / "traffic.sqlite")
    with TestClient(app) as client:
        assert client.get("/static/site.css", headers={"User-Agent": "Firefox"}).status_code == 200
        rows = app.state.traffic.drain()
    assert [(r[1], r[2]) for r in rows] == [("static", "2xx")]


def test_the_store_never_holds_counts(tmp_path):
    path = build_store(tmp_path)
    with TestClient(create_app(path)) as client:
        client.get("/")
    import sqlite3

    con = sqlite3.connect(path)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    assert not {n for n in names if n.startswith("traffic")}
    con.close()


def test_the_traffic_doc_states_the_row_bound_the_code_has():
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[1] / "docs" / "traffic.md").read_text(encoding="utf-8")
    bound = len(traffic.ROUTE_CLASSES) * 4 * 2
    assert f"at most {bound} rows an hour" in doc


def test_the_weekly_digest_goes_once_on_monday_with_the_table(tmp_path):
    from datetime import UTC, datetime

    path = tmp_path / "traffic.sqlite"
    counter = traffic.Counter()
    when = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)  # a Tuesday
    counter.record("/d/FD-36873", 200, 70_000, 120.0, "Mozilla/5.0", when)
    counter.record("/d/FD-36873", 200, 70_000, 40.0, "Googlebot/2.1", when)
    counter.record("/nope", 404, 0, 5.0, None, when)
    traffic.flush(counter, path, when)
    text = traffic.digest_text(path, now=when)  # the window ends where the fixture does
    assert "sheet" in text and "total" in text and "FD-36873" not in text  # kinds, never pages
    sender = FakeSender()
    monday_early = datetime(2026, 8, 31, 5, 30, tzinfo=UTC)
    monday = datetime(2026, 8, 31, 6, 30, tzinfo=UTC)
    assert not traffic.digest_due(path, when) and not traffic.digest_due(path, monday_early)
    assert traffic.digest_due(path, monday)
    assert traffic.send_digest(path, sender, "", monday) is False  # no recipient: nothing
    assert traffic.send_digest(path, None, "op@example.org", monday) is False  # no mail
    assert traffic.send_digest(path, sender, "op@example.org", monday) is True
    out = sender.sent[-1]
    assert out.to == "op@example.org" and "week to 2026-08-31" in out.subject
    assert "readers" in out.text and "sheet" in out.text
    # once: a later pass the same Monday sends nothing; next Monday it does again
    assert traffic.send_digest(path, sender, "op@example.org", monday.replace(hour=23)) is False
    assert traffic.digest_due(path, datetime(2026, 9, 7, 6, 5, tzinfo=UTC))


def test_the_digest_covers_the_week_its_subject_names(tmp_path):
    """`send_digest` built its subject from `now` and its table from the wall clock — the
    same instant in a pass, and two different ones anywhere else, which is why this file's
    fixture aged out of its own window and started failing a week after it was written
    (2026-09-01)."""
    from datetime import UTC, datetime

    path = tmp_path / "traffic.sqlite"
    counter = traffic.Counter()
    when = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
    counter.record("/d/FD-36873", 200, 70_000, 120.0, "Mozilla/5.0", when)
    traffic.flush(counter, path, when)
    # inside the window that ends where the fixture does...
    assert "sheet" in traffic.digest_text(path, now=when)
    # ...and outside one that ends a fortnight later, whatever the clock says
    assert "sheet" not in traffic.digest_text(path, now=when + timedelta(days=14))
    sender = FakeSender()
    monday = datetime(2026, 8, 31, 6, 30, tzinfo=UTC)
    assert traffic.send_digest(path, sender, "op@example.org", monday) is True
    out = sender.sent[-1]
    assert "week to 2026-08-31" in out.subject
    assert "sheet" in out.text  # the subject's week is the table's week


def test_the_operator_report_draws_the_counts_and_nothing_else(tmp_path):
    """docs/traffic.md § The operator's report: one file from traffic.sqlite, every day in
    the window drawn (an empty day is a zero, not a gap), no outside fetch, no store read."""
    from docketyard.store import traffic_report

    counts = tmp_path / "traffic.sqlite"
    now = datetime(2026, 10, 13, 15, tzinfo=UTC)
    con = traffic.connect(counts)
    traffic.write(
        con,
        [
            ("2026-10-13T14", "search", "2xx", 0, 4, 0, 4, 0, 0, 0),
            ("2026-10-13T14", "record", "2xx", 1, 9, 0, 0, 9, 0, 0),
            ("2026-10-10T03", "static", "2xx", 0, 2, 0, 2, 0, 0, 0),
            ("2026-10-02T03", "record", "5xx", 0, 1, 0, 0, 0, 0, 1),
        ],
    )
    con.close()
    page = traffic_report.render(counts, now=now)
    assert "2026-10-02 to 2026-10-13" in page
    for d in range(2, 14):  # a row for every one of the twelve days, the empty ones as zeros
        assert f"<tr><td>2026-10-{d:02d}</td>" in page
    assert "<tr><td>2026-10-05</td><td>0</td><td>0</td>" in page
    assert "http://" not in page and "https://" not in page  # opens from disk, fetches nothing
    assert "<td>search</td><td>4</td>" in page
    # the window narrows to the last N days; the 5xx on 2026-10-02 falls out of it
    week = traffic_report.render(counts, days=7, now=now)
    assert "2026-10-07 to 2026-10-13" in week and "<td>record</td><td>0</td><td>9</td>" in week
    assert not (tmp_path / "docketyard.sqlite").exists()


def test_the_report_tiles_ignore_the_window_and_the_file_stays_unpublished(tmp_path):
    """Code review, 2026-10-13: the tiles' week before came from the window, so `--days 7`
    read 'nothing before'; a row dated after `now` raised KeyError; a fractional axis tick
    printed as a whole number; and nothing stopped the report landing in `public/`."""
    import pytest

    from docketyard.store import traffic_report

    counts = tmp_path / "traffic.sqlite"
    now = datetime(2026, 10, 13, 15, tzinfo=UTC)
    con = traffic.connect(counts)
    traffic.write(
        con,
        [
            ("2026-10-12T10", "static", "3xx", 0, 6, 0, 6, 0, 0, 0),  # a 304 is a reader
            ("2026-10-03T10", "static", "2xx", 0, 3, 0, 3, 0, 0, 0),  # the week before
            ("2026-10-14T01", "home", "2xx", 0, 1, 0, 1, 0, 0, 0),  # after `now`
        ],
    )
    con.close()
    week = traffic_report.render(counts, days=7, now=now)
    assert "▲ 100% on the 7 days before" in week  # 6 assets against 3, outside the window
    assert traffic_report._compact(0.25) == "0.25" and traffic_report._compact(999_950) == "1.0M"
    (tmp_path / "public").mkdir()
    with pytest.raises(ValueError):
        traffic_report.write(counts, tmp_path / "public" / "t.html")
    assert not (tmp_path / "public" / "t.html").exists()
    assert traffic_report.write(counts, tmp_path / "t.html").exists()


def test_the_report_reads_full_days_and_shares_in_points(tmp_path):
    """Code review, 2026-10-18: rows all after `now` raised IndexError; an empty `--days`
    window said 'no counts yet' over non-zero tiles; the tiles and the hour profile read
    today's part day against whole days; the fast share moved by a percent of itself."""
    from docketyard.store import traffic_report

    now = datetime(2026, 10, 13, 15, tzinfo=UTC)
    ahead = tmp_path / "ahead" / "traffic.sqlite"
    ahead.parent.mkdir()
    con = traffic.connect(ahead)
    traffic.write(con, [("2026-10-14T01", "home", "2xx", 0, 1, 0, 1, 0, 0, 0)])
    con.close()
    assert "2026-10-13 to 2026-10-13, no counts in it" in traffic_report.render(ahead, now=now)

    counts = tmp_path / "traffic.sqlite"
    con = traffic.connect(counts)
    traffic.write(
        con,
        [
            # today, at 10:00 UTC: in neither the tiles nor the hour profile
            ("2026-10-13T10", "search", "2xx", 0, 50, 0, 0, 0, 50, 0),
            # the last 7 full days: 3 of 4 under 500 ms
            ("2026-10-12T22", "search", "2xx", 0, 4, 0, 3, 0, 1, 0),
            # the 7 before: 1 of 2 under 500 ms
            ("2026-10-04T22", "search", "2xx", 0, 2, 0, 1, 0, 1, 0),
        ],
    )
    con.close()
    page = traffic_report.render(counts, now=now)
    assert "▲ 100% on the 7 days before" in page  # searches 4 against 2, today's 50 left out
    assert "▲ 25 points on the 7 days before" in page  # 75% against 50%, not ▲ 50%
    assert "the 30 full days before today" in page
    hod = traffic.by_hour_of_day(
        counts, datetime(2026, 10, 12, tzinfo=UTC), datetime(2026, 10, 13, tzinfo=UTC)
    )
    assert [(hh, req) for hh, _r, _s, _b, req in hod] == [("22", 4)]
    # an empty window over older counts says so, not 'no counts yet'
    old = traffic_report.render(counts, days=1, now=now + timedelta(days=3))
    assert "2026-10-16 to 2026-10-16, no counts in it" in old and "no counts yet" not in old
