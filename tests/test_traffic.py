"""Hourly counts with no identifier (docs/traffic.md): the middleware counts kind of page,
status class, size, speed and crawler-or-not, and forgets the request; the numbers go to a
file beside the store, never into it; old hours fold into days."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from docketyard.store import traffic
from docketyard.web.app import create_app
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
    assert traffic.is_bot("Mozilla/5.0 (compatible; Googlebot/2.1)") and traffic.is_bot(None)
    assert not traffic.is_bot("Mozilla/5.0 (Windows NT 10.0) Firefox/128.0")


def test_counts_are_aggregates_and_fold_into_days(tmp_path):
    path = build_store(tmp_path)
    counts = tmp_path / "traffic.sqlite"
    app = create_app(path, traffic_path=counts)
    with TestClient(app) as client:
        client.get("/d/FD-36873", headers={"User-Agent": "Firefox/128"})
        client.get("/d/FD-36873/sub/1", headers={"User-Agent": "Firefox/128"})
        client.get("/p/999999", headers={"User-Agent": "Googlebot"})
        client.get("/search", params={"q": "peoria"}, headers={"User-Agent": "Firefox/128"})
        now = datetime.now(UTC)
        assert traffic.flush(app.state.traffic, counts, now, all_hours=True) >= 3
    con = traffic.connect(counts)
    rows = con.execute(
        "SELECT route_class, status_class, bot, requests FROM traffic_hour ORDER BY 1, 2, 3"
    ).fetchall()
    assert ("sheet", "2xx", 0, 2) in rows and ("party", "4xx", 1, 1) in rows
    assert ("search", "2xx", 0, 1) in rows
    cols = {r[1] for r in con.execute("PRAGMA table_info(traffic_hour)")}
    assert not cols & {"path", "ip", "user_agent", "referer", "query"}  # nothing else exists
    # a second flush of the same hour adds to the row; a restart never loses a row's hour
    app.state.traffic.record("/d/FD-1", 200, 10, 5.0, "Firefox", now)
    traffic.flush(app.state.traffic, counts, now, all_hours=True)
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


def test_the_store_never_holds_counts(tmp_path):
    path = build_store(tmp_path)
    with TestClient(create_app(path)) as client:
        client.get("/")
    import sqlite3

    con = sqlite3.connect(path)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    assert not {n for n in names if n.startswith("traffic")}
    con.close()
