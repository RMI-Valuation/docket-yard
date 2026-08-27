# Traffic counts — design note

> **Status: built 2026-08-26** (`store/traffic.py`, counted in the web tier's middleware,
> `docketyard traffic` for the operator). The operator signed the privacy sentence below on
> 2026-08-26 and it is on `/privacy` verbatim. This note is the source the code follows.

## The ask

Hourly counts with **no identifier, ever**: route class, status, bytes, latency, bot or not.
Enough to know whether the site is used and whether it is slow; nothing that could say who.

## What is counted

One row per hour per (route class, status class, bot flag):

| Column | Values | Why |
| --- | --- | --- |
| `hour` | ISO hour, UTC | the grain |
| `route_class` | `home`, `sheet`, `record`, `document`, `party`, `parties`, `search` (`/search` and `/suggest`), `week`, `stats`, `feed`, `json`, `sitemap` (and robots), `data`, `trust` (about/contribute/coverage/methodology/corrections/privacy), `subscribe` (and the token and SES paths), `static`, `other` — `ROUTE_CLASSES` in `store/traffic.py` | the page kind, never the page: no docket, no party, no record id |
| `status_class` | `2xx`, `3xx`, `4xx`, `5xx` | health |
| `bot` | 0/1 | a fixed list of substrings matched against the User-Agent *in memory* (`_BOT_MARKS`; the compose healthcheck's `Python-urllib` is one); a missing User-Agent is a reader; the string itself is never written |
| `requests` | count | |
| `bytes` | sum of response sizes, each **rounded up to 64 KB** first | transfer volume — never a page: an exact length would identify a sheet in an hour with one reader (security review, 2026-08-26) |
| `latency_ms` | four buckets: `<100`, `<500`, `<2000`, `≥2000`, as counts | slow pages are visible; no per-request timing survives |

Seventeen route classes × four status classes × two bot flags = at most 136 rows an hour,
and in practice a handful. A month is a few thousand rows.

**What is never in it:** IP address, any hash of one, User-Agent, referrer, query string,
path, docket or party ids, cookies (none exist), session (none exists), country, anything
per request, a page's exact length. The row cannot be joined to anything else because nothing else exists.

## Where it is measured, and why not the access log

Caddy's access log already drops the address and User-Agent (ADR 0011) and is kept for
days; it has no bot flag and would need the path to classify the route. Rather than keep a
richer log to aggregate from, the **web app counts in memory**: the existing `http_hygiene`
middleware sees path, status, bytes and elapsed time, classifies the route and the agent on
the spot, increments a counter, and forgets the request. Just after every hour boundary,
and at shutdown, the counters are written (additively, so a partial hour is safe) and
reset; a crash loses at most the hour in progress. An unhandled error is counted as the
5xx the reader saw; a HEAD counts zero bytes. No per-request record exists anywhere, at
any point, even transiently on disk.

The server is a reader with one exception (subscriptions). Counts are a second, separate
exception: they go to a **separate file**, `data/traffic.sqlite`, never into the store —
the store is the record of the Board's proceedings and stays free of anything about readers;
the snapshot (`/data`) and the JSON never see the counts.

## What is published

Nothing, at first. `/stats` says "nothing about readers" and keeps saying it; the counts are
for the operator (a `docketyard traffic` command printing the last day/week). Publishing an
aggregate later — "requests per day, all readers" — is a separate decision with its own
sentence on `/privacy`.

## Retention

Hourly rows are kept **90 days**, then folded to daily rows kept indefinitely (the daily row
has the same columns; it is a sum, not a sample). Both numbers are stated on `/privacy`.

## The privacy sentence (for the operator to sign)

Proposed, to be added under "Reading is anonymous", after the access-log bullet:

> The site keeps hourly counts of requests by kind of page, response code, size and speed,
> and whether the visitor looked like a crawler — numbers only, with no address, browser,
> page or identifier of any sort, kept for 90 days by the hour and indefinitely by the day.

## Open

- [x] The operator signed the sentence (2026-08-26).
- [x] Route classes as listed (plus `search`, added with the search box); retention 90 days
      hourly, daily indefinitely; bot/not from a fixed substring list, matched in memory.
- [ ] Publishing any aggregate is a separate decision with its own sentence.
