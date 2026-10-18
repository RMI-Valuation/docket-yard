"""The operator's traffic report: one self-contained HTML file drawn from `traffic.sqlite`
(docs/traffic.md § The operator's report).

Written to a path the operator names and served nowhere: the counts stay the operator's, as
the note says, and nothing here reads the store. Numbers by kind of page only — the file
holds nothing the table `docketyard traffic` prints does not already hold, drawn by day and
by hour of the day. No script or font is fetched; it opens from disk.

"No crawler mark" is the honest name for what the digest calls readers: a User-Agent that
does not say it is a crawler. Measured 2026-10-13, most of that column is machines that do
not say so — ~100k a day in early October, level across all 24 hours, against fewer than a
thousand searches in a month — so the report draws the page kinds side by side and leaves
the reading to the operator rather than naming a number of people.
"""

import html
import json
import math
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from docketyard.store import traffic

# the kinds a reader's own browser asks for besides the page: fetched when a page is drawn,
# rarely by a scraper. Counted as `other` until the fix of 2026-10-13 (a mount rewrote the
# path the middleware read), so the series starts that day.
ASSETS = "static"
# record pages and their machine forms: where a scrape of the record lands
RECORD = ("sheet", "record", "document", "party", "json", "feed")
# the page kinds a person reaches by hand far more often than a crawl does
BY_HAND = ("home", "search", "trust", "subscribe", "parties", "stats", "register", "static")
WHAT = {
    "home": "the front page",
    "sheet": "docket sheets (/d/…)",
    "record": "filing and decision pages",
    "document": "the Board's files, served (/document/…)",
    "party": "party pages (/p/…)",
    "parties": "the party index",
    "search": "search, suggest and the citation resolver",
    "week": "the week pages",
    "stats": "/stats",
    "register": "the court and protective-order registers",
    "feed": "RSS/Atom feeds",
    "json": "the JSON of sheets and records",
    "sitemap": "sitemaps and robots.txt",
    "data": "/data, /api, llms.txt, OpenAPI",
    "trust": "about, methodology, coverage, corrections, privacy",
    "subscribe": "subscribing and its token links",
    "static": "stylesheet and fonts",
    "other": "everything else: mostly probes for paths that do not exist",
}
HOUR_DAYS = 30  # the hour-of-day profile's window
# answered without an error: a 304 is a returning browser revalidating its copy, and leaving
# 3xx out would drop the repeat readers first
ANSWERED = ("2xx", "3xx")


def _compact(n: float) -> str:
    """1,284 → 1.3K, 2,500,000 → 2.5M; a fractional axis tick keeps its fraction."""
    n = float(n)
    for div, suffix in ((1e6, "M"), (1e3, "K")):
        if abs(n) >= div * 0.9995:
            v = n / div
            return f"{v:.0f}{suffix}" if round(v, 1) >= 100 or v == int(v) else f"{v:.1f}{suffix}"
    return f"{n:.0f}" if n == int(n) else f"{n:g}"


def _nice_max(v: float, ticks: int = 4) -> tuple[float, float]:
    """A clean top for the axis and its step: 1, 2, 2.5 or 5 times a power of ten."""
    if v <= 0:
        return 1.0, 0.25
    raw = v / ticks
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return step * ticks, step


def _tip(title: str, rows: list[tuple[str, float, str]]) -> str:
    """The hover readout as an attribute: a title and (series, value, colour var) rows. The
    script builds the box with textContent, never markup."""
    data = {"t": title, "r": [[name, f"{value:,.0f}", var] for name, value, var in rows]}
    return html.escape(json.dumps(data), quote=True)


def _top_rounded(x: float, y: float, w: float, h: float, r: float = 4) -> str:
    """A column with a 4px rounded data end and a square foot on the baseline."""
    r = min(r, h, w / 2)
    return (
        f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
        f"H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z"
    )


def columns(
    labels: list[str],
    series: list[tuple[str, str, list[float]]],
    tick: list[str] | None = None,
    titles: list[str] | None = None,
    height: int = 220,
    width: int = 960,
) -> str:
    """Stacked columns, one per label, a 2px surface gap between segments; each column is
    its own hover target. `tick` is the x label drawn under a column (blank for none)."""
    left, right, top, bottom = 52, 8, 10, 26
    plot_w, plot_h = width - left - right, height - top - bottom
    n = max(len(labels), 1)
    totals = [sum(s[2][i] for s in series) for i in range(len(labels))]
    ymax, step = _nice_max(max(totals, default=0))
    band = plot_w / n
    bar = min(24.0, max(band - 2, 1.0))
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" class="cols">']
    v = 0.0
    while v <= ymax + 1e-9:
        y = top + plot_h - plot_h * v / ymax
        cls = "base" if v == 0 else "grid"
        out.append(
            f'<line class="{cls}" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/>'
        )
        out.append(
            f'<text class="tick" x="{left - 6}" y="{y + 4:.1f}" '
            f'text-anchor="end">{_compact(v)}</text>'
        )
        v += step
    for i in range(len(labels)):
        x = left + band * i + (band - bar) / 2
        base = top + plot_h
        drawn = [(name, var, vals[i]) for name, var, vals in series if vals[i] > 0]
        for j, (_name, var, value) in enumerate(drawn):
            h = plot_h * value / ymax
            gap = 2 if j else 0  # the surface gap between touching segments
            seg = max(h - gap, 0.5)
            y = base - h
            if j == len(drawn) - 1:
                out.append(f'<path d="{_top_rounded(x, y, bar, seg)}" style="fill:var({var})"/>')
            else:
                out.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar:.1f}" height="{seg:.1f}" '
                    f'style="fill:var({var})"/>'
                )
            base = y
        tip = _tip((titles or labels)[i], [(name, vals[i], var) for name, var, vals in series])
        out.append(
            f'<rect class="hit" x="{left + band * i:.1f}" y="{top}" width="{band:.1f}" '
            f'height="{plot_h}" data-tip="{tip}" tabindex="0"/>'
        )
        if tick and tick[i]:
            out.append(
                f'<text class="tick" x="{left + band * i + band / 2:.1f}" '
                f'y="{height - 8}" text-anchor="middle">{html.escape(tick[i])}</text>'
            )
    out.append("</svg>")
    return "".join(out)


def panel(name: str, days: list[str], values: list[float]) -> str:
    """One small multiple: a 2px line over a 10% wash on its own scale, the peak labelled,
    each day a hover target."""
    width, height, left, top, bottom = 300, 96, 4, 16, 16
    plot_w, plot_h = width - 2 * left, height - top - bottom
    peak = max(values, default=0) or 1
    n = len(values)
    xs = [left + (plot_w * i / (n - 1) if n > 1 else plot_w / 2) for i in range(n)]
    ys = [top + plot_h - plot_h * v / peak for v in values]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))
    base = top + plot_h
    area = f"{xs[0]:.1f},{base} {line} {xs[-1]:.1f},{base}" if n else ""
    out = [
        '<figure class="panel">',
        f"<figcaption><b>{html.escape(name)}</b> <span>{_compact(sum(values))} · "
        f"{html.escape(WHAT.get(name, ''))}</span></figcaption>",
        f'<svg viewBox="0 0 {width} {height}" role="img">',
        f'<line class="base" x1="{left}" x2="{width - left}" y1="{base}" y2="{base}"/>',
        f'<text class="tick" x="{left}" y="11">peak {_compact(max(values, default=0))}/day</text>',
    ]
    if n:
        out.append(f'<polygon class="wash" points="{area}"/>')
        out.append(f'<polyline class="line" points="{line}"/>')
        slot = plot_w / max(n, 1)
        for i, day in enumerate(days):
            tip = _tip(day, [(name, values[i], "--s1")])
            out.append(
                f'<rect class="hit" x="{xs[i] - slot / 2:.1f}" y="{top}" '
                f'width="{slot:.1f}" height="{plot_h}" data-tip="{tip}" tabindex="0"/>'
            )
        out.append(f'<text class="tick" x="{left}" y="{height - 3}">{days[0][5:]}</text>')
        out.append(
            f'<text class="tick" x="{width - left}" y="{height - 3}" '
            f'text-anchor="end">{days[-1][5:]}</text>'
        )
    out.append("</svg>")
    out.append("</figure>")
    return "".join(out)


def latency_bars(rows: list[tuple[str, list[float]]]) -> str:
    """One 100% bar per kind of page across the four latency buckets, fast to slow, on an
    ordinal ramp (slower is darker on light, brighter on dark)."""
    width, left, row_h = 960, 110, 26
    height = row_h * len(rows) + 6
    plot_w = width - left - 60
    names = ("under 100 ms", "100–500 ms", "500 ms–2 s", "2 s and over")
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" class="lat">']
    for r, (route, buckets) in enumerate(rows):
        total = sum(buckets) or 1
        y = 4 + r * row_h
        out.append(
            f'<text class="label" x="{left - 8}" y="{y + 15}" '
            f'text-anchor="end">{html.escape(route)}</text>'
        )
        x = left
        for k, count in enumerate(buckets):
            w = plot_w * count / total
            if w <= 0:
                continue
            gap = 2 if x > left else 0
            out.append(
                f'<rect x="{x + gap:.1f}" y="{y}" width="{max(w - gap, 0.5):.1f}" '
                f'height="18" style="fill:var(--o{k + 1})"/>'
            )
            x += w
        slow = 100 * (buckets[2] + buckets[3]) / total
        out.append(
            f'<text class="tick" x="{left + plot_w + 6}" y="{y + 14}">{slow:.1f}% slow</text>'
        )
        tip = _tip(route, [(names[k], buckets[k], f"--o{k + 1}") for k in range(4)])
        out.append(
            f'<rect class="hit" x="0" y="{y - 2}" width="{width}" height="{row_h}" '
            f'data-tip="{tip}" tabindex="0"/>'
        )
    out.append("</svg>")
    legend = "".join(
        f'<span><i class="sw" style="background:var(--o{k + 1})"></i>{names[k]}</span>'
        for k in range(4)
    )
    return f'<div class="legend">{legend}</div>' + "".join(out)


def _tile(label: str, now: float, before: float | None, unit: str = "", note: str = "") -> str:
    """A share (`unit` "%") moves by points, never by a percent of itself; `before` None
    is a week before with nothing in it, which a share of 0% is not."""
    if unit == "%" and before is not None:
        change = now - before
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "")
        delta = f"{arrow} {abs(change):.0f} points on the 7 days before"
    elif unit != "%" and before:
        change = 100 * (now - before) / before
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "")
        delta = f"{arrow} {abs(change):.0f}% on the 7 days before"
    else:
        delta = "nothing in the 7 days before"
    value = f"{now:.1f}{unit}" if unit else _compact(now)
    return (
        f'<div class="tile"><div class="tl">{html.escape(label)}</div>'
        f'<div class="tv">{value}</div><div class="td">{delta}</div>'
        + (f'<div class="tn">{html.escape(note)}</div>' if note else "")
        + "</div>"
    )


def _tiles(rows: list[tuple], today: date) -> str:
    """The last 7 full days against the 7 before, from their own 14 days of rows, whatever
    window the rest of the report draws. Today is left out: a part day against a whole
    week before reads as a fall when nothing fell."""
    weeks = [[0.0] * 8 for _ in range(2)]  # unmarked, crawler, assets, search, 5xx, fast, all
    for day, route, status, bot, req, _size, lt100, lt500, *_slow in rows:
        age = (today - date.fromisoformat(day)).days
        if not 1 <= age <= 14:
            continue
        w = weeks[(age - 1) // 7]
        w[1 if bot else 0] += req
        if not bot and status in ANSWERED:
            w[2] += req if route == ASSETS else 0
            w[3] += req if route == "search" else 0
        w[4] += req if status == "5xx" else 0
        w[5] += lt100 + lt500
        w[6] += req
    now, before = weeks
    return "".join(
        [
            _tile("Requests, no crawler mark", now[0], before[0]),
            _tile("Requests, declared crawlers", now[1], before[1]),
            _tile(
                "Asset loads, no crawler mark",
                now[2],
                before[2],
                note="a browser drawing a page asks for these; counted from 2026-10-13",
            ),
            _tile("Searches, no crawler mark", now[3], before[3]),
            _tile("Server errors (5xx)", now[4], before[4]),
            _tile(
                "Answered under 500 ms",
                100 * now[5] / (now[6] or 1),
                100 * before[5] / before[6] if before[6] else None,
                unit="%",
            ),
        ]
    )


def render(path: str | Path, days: int | None = None, now: datetime | None = None) -> str:
    """The whole report as one HTML string: everything held when `days` is None, else
    the last `days` days. `now` fixes the clock for a test."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    today = now.date()
    since = "" if days is None else (today - timedelta(days=days - 1)).isoformat()
    rows = traffic.daily(path, since)
    # the window's own first day when one is asked for: a quiet start is zeros, not missing.
    # Never after today: rows all dated after `now` (a lagging clock) still draw today
    first = min(date.fromisoformat(since or (rows[0][0] if rows else today.isoformat())), today)
    span = [(first + timedelta(days=i)).isoformat() for i in range((today - first).days + 1)]
    idx = {d: i for i, d in enumerate(span)}
    n = len(span)

    def zeros() -> list[float]:
        return [0.0] * n

    unmarked, crawler, err4, err5 = zeros(), zeros(), zeros(), zeros()
    by_route: dict[str, list[float]] = {}
    summary: dict[str, list[float]] = {}  # route → unmarked, crawler, 3xx, 4xx, 5xx, bytes
    lat: dict[str, list[float]] = {}
    counted = False
    for day, route, status, bot, req, size, *buckets in rows:
        if day not in idx:  # dated after `now` (a lagging clock): outside the window
            continue
        counted = True
        i = idx[day]
        (crawler if bot else unmarked)[i] += req
        if status == "4xx":
            err4[i] += req
        elif status == "5xx":
            err5[i] += req
        if not bot and status in ANSWERED:
            by_route.setdefault(route, zeros())[i] += req
        s = summary.setdefault(route, [0.0] * 6)
        s[1 if bot else 0] += req
        if status in ("3xx", "4xx", "5xx"):
            s[{"3xx": 2, "4xx": 3, "5xx": 4}[status]] += req
        s[5] += size
        lat.setdefault(route, [0.0] * 4)
        for k, b in enumerate(buckets):
            lat[route][k] += b

    def route_sum(names) -> list[float]:
        out = zeros()
        for name in names:
            for i, v in enumerate(by_route.get(name, ())):
                out[i] += v
        return out

    assets = by_route.get(ASSETS, zeros())
    searches = by_route.get("search", zeros())
    tiles = _tiles(traffic.daily(path, (today - timedelta(days=14)).isoformat()), today)

    # a tick under every Monday on a long span, every day on a short one
    ticks = [d[5:] if n <= 14 or date.fromisoformat(d).weekday() == 0 else "" for d in span]
    titles = [
        f"{d} ({date.fromisoformat(d):%a})" + (", so far" if d == span[-1] else "") for d in span
    ]
    daily_chart = columns(
        span,
        [("no crawler mark", "--s1", unmarked), ("declared crawler", "--s2", crawler)],
        tick=ticks,
        titles=titles,
    )

    order = sorted(by_route, key=lambda r: -sum(by_route[r]))
    hand = [r for r in order if r in BY_HAND]
    rest = [r for r in order if r not in BY_HAND]
    panels_hand = "".join(panel(r, span, by_route[r]) for r in hand)
    panels_rest = "".join(panel(r, span, by_route[r]) for r in rest)

    # full days only, ending yesterday: today's hours not yet reached would read as quiet
    hod_days = min(HOUR_DAYS, days or HOUR_DAYS)
    hod_until = datetime.combine(today, time(), UTC)
    hod_since = hod_until - timedelta(days=hod_days)
    hod_record, hod_hand = [0.0] * 24, [0.0] * 24
    for hh, route, status, bot, req in traffic.by_hour_of_day(path, hod_since, hod_until):
        if bot or status not in ANSWERED:
            continue
        if route in RECORD:
            hod_record[int(hh)] += req
        elif route in BY_HAND:
            hod_hand[int(hh)] += req
    hours = [f"{h:02d}" for h in range(24)]
    hour_ticks = [h if int(h) % 3 == 0 else "" for h in hours]
    hour_titles = [f"{h}:00–{h}:59 UTC" for h in hours]
    hod_a = columns(
        hours, [("record pages", "--s1", hod_record)], hour_ticks, hour_titles, 240, 480
    )
    hod_b = columns(hours, [("by-hand pages", "--s1", hod_hand)], hour_ticks, hour_titles, 240, 480)

    lat_rows = sorted(
        ((r, b) for r, b in lat.items() if sum(b) >= 50),
        key=lambda rb: -(rb[1][2] + rb[1][3]) / (sum(rb[1]) or 1),
    )
    lat_chart = latency_bars(lat_rows)

    err_chart = columns(
        span,
        [("4xx", "--s1", err4), ("5xx", "--s2", err5)],
        tick=ticks,
        titles=titles,
        height=160,
    )

    table = "".join(
        f"<tr><td>{html.escape(r)}</td>"
        + "".join(f"<td>{v:,.0f}</td>" for v in s[:5])
        + f"<td>{s[5] / 1e6:,.1f}</td>"
        + f"<td>{100 * (lat[r][0] + lat[r][1]) / ((sum(lat[r])) or 1):.0f}%</td></tr>"
        for r, s in sorted(summary.items(), key=lambda kv: -kv[1][0])
    )
    record_days, hand_days = route_sum(RECORD), route_sum(BY_HAND)
    day_rows = "".join(
        f"<tr><td>{d}</td><td>{unmarked[i]:,.0f}</td><td>{crawler[i]:,.0f}</td>"
        f"<td>{record_days[i]:,.0f}</td><td>{hand_days[i]:,.0f}</td>"
        f"<td>{searches[i]:,.0f}</td><td>{assets[i]:,.0f}</td><td>{err4[i]:,.0f}</td>"
        f"<td>{err5[i]:,.0f}</td></tr>"
        for i, d in reversed(list(enumerate(span)))
    )
    window = f"{span[0]} to {span[-1]}" + ("" if counted else ", no counts in it")
    return _PAGE.format(
        window=window,
        generated=now.strftime("%Y-%m-%d %H:%M UTC"),
        tiles=tiles,
        daily=daily_chart,
        panels_hand=panels_hand or "<p>None in this window.</p>",
        panels_rest=panels_rest or "<p>None in this window.</p>",
        hod_days=hod_days,
        hod_a=hod_a,
        hod_b=hod_b,
        lat=lat_chart,
        err=err_chart,
        table=table,
        day_rows=day_rows,
        record=", ".join(RECORD),
        by_hand=", ".join(BY_HAND),
    )


def write(path: str | Path, out: str | Path, days: int | None = None) -> Path:
    """The report to `out`, refused anywhere under the published directory beside the
    store (`public/`, served at /data/files): the counts are the operator's."""
    out = Path(out)
    public = (Path(path).parent / "public").resolve()
    if out.resolve().is_relative_to(public):
        raise ValueError(f"{out} is under {public}, which is published at /data/files")
    out.write_text(render(path, days=days), encoding="utf-8", newline="\n")
    return out


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Docket Yard Traffic</title>
<style>
:root {{
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --base: #c3c2b7; --ring: rgba(11,11,11,0.10);
  --s1: #2a78d6; --s2: #eb6834;
  --o1: #86b6ef; --o2: #3987e5; --o3: #1c5cab; --o4: #0d366b;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --base: #383835; --ring: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926;
    --o1: #184f95; --o2: #256abf; --o3: #5598e7; --o4: #9ec5f4;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --base: #383835; --ring: rgba(255,255,255,0.10);
  --s1: #3987e5; --s2: #d95926;
  --o1: #184f95; --o2: #256abf; --o3: #5598e7; --o4: #9ec5f4;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1040px; margin: 0 auto; padding: 24px 16px 64px; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
h2 {{ font-size: 17px; margin: 36px 0 4px; }}
p {{ margin: 4px 0 12px; color: var(--ink2); max-width: 75ch; }}
.meta {{ color: var(--muted); font-size: 13px; }}
.card {{ background: var(--surface); border: 1px solid var(--ring); border-radius: 8px;
  padding: 16px; overflow-x: auto; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px; margin-top: 16px; }}
.tile {{ background: var(--surface); border: 1px solid var(--ring); border-radius: 8px;
  padding: 12px; }}
.tl {{ font-size: 13px; color: var(--ink2); }}
.tv {{ font-size: 26px; font-weight: 600; margin: 2px 0; }}
.td, .tn {{ font-size: 12px; color: var(--muted); }}
svg {{ display: block; width: 100%; height: auto; min-width: 560px; }}
.panels svg, .two svg {{ min-width: 0; }}
.grid {{ stroke: var(--grid); stroke-width: 1; }}
.base {{ stroke: var(--base); stroke-width: 1; }}
.tick {{ fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }}
.label {{ fill: var(--ink2); font-size: 12px; }}
.line {{ fill: none; stroke: var(--s1); stroke-width: 2; stroke-linejoin: round;
  stroke-linecap: round; vector-effect: non-scaling-stroke; }}
.wash {{ fill: var(--s1); opacity: 0.1; }}
.hit {{ fill: transparent; cursor: default; outline: none; }}
.hit:hover, .hit:focus {{ fill: var(--ink); opacity: 0.05; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--ink2);
  margin: 0 0 8px; }}
.sw {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px;
  margin-right: 6px; vertical-align: -1px; }}
.panels {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px; }}
.panel {{ margin: 0; background: var(--surface); border: 1px solid var(--ring);
  border-radius: 8px; padding: 10px 12px 8px; }}
.panel figcaption {{ font-size: 13px; }}
.panel figcaption span {{ color: var(--muted); }}
.two {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 12px; }}
.two h3 {{ font-size: 14px; margin: 0 0 6px; font-weight: 600; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px;
  font-variant-numeric: tabular-nums; }}
th, td {{ padding: 4px 8px; border-bottom: 1px solid var(--grid); text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ color: var(--ink2); font-weight: 600; }}
details summary {{ cursor: pointer; color: var(--ink2); margin: 8px 0; }}
#tip {{ position: fixed; pointer-events: none; display: none; background: var(--surface);
  border: 1px solid var(--ring); border-radius: 6px; padding: 8px 10px; font-size: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12); z-index: 10; }}
#tip .t {{ color: var(--ink2); margin-bottom: 4px; }}
#tip .r {{ display: flex; align-items: center; gap: 8px; }}
#tip .k {{ width: 12px; height: 2px; }}
#tip b {{ font-variant-numeric: tabular-nums; }}
#tip span {{ color: var(--muted); }}
</style></head>
<body><main>
<h1>Docket Yard traffic</h1>
<div class="meta">{window} · generated {generated} · from traffic.sqlite, served nowhere</div>
<p>Hourly counts of requests by kind of page, response code, size and speed, and whether the
User-Agent called itself a crawler. Nothing else is kept: no address, browser, page or
identifier. So this report cannot count people, and it does not try.</p>

<h2>The last 7 full days</h2>
<p>The 7 days before today against the 7 before those; today, so far, is left out. "No
crawler mark" means the User-Agent did not say it was a crawler. Most of these requests come
from machines that do not say so.</p>
<div class="tiles">{tiles}</div>

<h2>Requests by day</h2>
<p>Every kind of page and every response. The latest column is today, so far.</p>
<div class="card"><div class="legend"><span><i class="sw" style="background:var(--s1)"></i>no
crawler mark</span><span><i class="sw" style="background:var(--s2)"></i>declared
crawler</span></div>{daily}</div>

<h2>Pages people reach by hand</h2>
<p>Requests answered 2xx or 3xx with no crawler mark, by day, each panel on its own scale.
A crawl of the record seldom lands on these pages: {by_hand}.</p>
<div class="panels">{panels_hand}</div>

<h2>The record pages and everything else</h2>
<p>The same measure for the other kinds of page. A scrape of the record lands here, so a
spike here means a machine at least as often as it means a reader.</p>
<div class="panels">{panels_rest}</div>

<h2>Hour of the day, the {hod_days} full days before today</h2>
<p>Requests answered 2xx or 3xx with no crawler mark, by UTC hour. US working hours fall
from about 13:00 to 23:00 UTC. A profile that stays level around the clock is machine-shaped.</p>
<div class="two"><div class="card"><h3>Record pages ({record})</h3>{hod_a}</div>
<div class="card"><h3>By-hand pages</h3>{hod_b}</div></div>

<h2>Speed by kind of page</h2>
<p>The share of requests in each latency band, every response included, sorted with the
slowest kind first. Kinds with fewer than 50 requests are left out.</p>
<div class="card">{lat}</div>

<h2>Errors by day</h2>
<p>4xx is mostly probes for paths that do not exist (the <i>other</i> kind of page). 5xx is
ours.</p>
<div class="card"><div class="legend"><span><i class="sw" style="background:var(--s1)"></i>4xx
</span><span><i class="sw" style="background:var(--s2)"></i>5xx</span></div>{err}</div>

<h2>By kind of page, whole window</h2>
<div class="card"><table>
<tr><th>kind</th><th>no crawler mark</th><th>crawler</th><th>3xx</th><th>4xx</th><th>5xx</th>
<th>MB (64 KB grain)</th><th>&lt;500 ms</th></tr>{table}</table></div>

<details><summary>Every day as a table</summary><div class="card"><table>
<tr><th>day</th><th>no crawler mark</th><th>crawler</th><th>record</th>
<th>by-hand</th><th>search</th><th>assets</th><th>4xx</th><th>5xx</th></tr>
{day_rows}</table></div></details>
</main>
<div id="tip"></div>
<script>
(function () {{
  var tip = document.getElementById("tip");
  function show(el, x, y) {{
    var d = JSON.parse(el.getAttribute("data-tip"));
    tip.textContent = "";
    var t = document.createElement("div"); t.className = "t"; t.textContent = d.t;
    tip.appendChild(t);
    d.r.forEach(function (r) {{
      var row = document.createElement("div"); row.className = "r";
      var k = document.createElement("i"); k.className = "k";
      k.style.background = "var(" + r[2] + ")";
      var b = document.createElement("b"); b.textContent = r[1];
      var s = document.createElement("span"); s.textContent = r[0];
      row.appendChild(k); row.appendChild(b); row.appendChild(s); tip.appendChild(row);
    }});
    tip.style.display = "block";
    var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(x + 14, window.innerWidth - w - 8) + "px";
    tip.style.top = Math.max(y - h - 10, 8) + "px";
  }}
  document.addEventListener("pointermove", function (e) {{
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (el) show(el, e.clientX, e.clientY); else tip.style.display = "none";
  }});
  document.addEventListener("focusin", function (e) {{
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (!el) return;
    var r = el.getBoundingClientRect(); show(el, r.left + r.width / 2, r.top);
  }});
  document.addEventListener("focusout", function () {{ tip.style.display = "none"; }});
}})();
</script>
</body></html>
"""
