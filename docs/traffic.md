# Traffic counts — design note

> **Status: planning only, 2026-08-26.** The operator's fourth ask; not started. It ships only
> with one sentence on `/privacy` that the operator has signed, because the privacy page
> currently says the access log "records the page and the time" and nothing more — this
> adds a kept, aggregated record, and the page must say so.

## The ask

Hourly counts with **no identifier, ever**: route class, status, bytes, latency, bot or not.
Enough to know whether the site is used and whether it is slow; nothing that could say who.

## What is counted

One row per hour per (route class, status class, bot flag):

| Column | Values | Why |
| --- | --- | --- |
| `hour` | ISO hour, UTC | the grain |
| `route_class` | `home`, `sheet`, `record`, `party`, `parties`, `week`, `stats`, `feed`, `json`, `sitemap`, `data`, `trust` (about/coverage/methodology/corrections/privacy), `subscribe`, `static`, `other` | the page kind, never the page: no docket, no party, no record id |
| `status_class` | `2xx`, `3xx`, `4xx`, `5xx` | health |
| `bot` | 0/1 | a fixed list of substrings matched against the User-Agent *in memory*; the string itself is never written |
| `requests` | count | |
| `bytes` | sum of response bytes | transfer |
| `latency_ms` | four buckets: `<100`, `<500`, `<2000`, `≥2000`, as counts | slow pages are visible; no per-request timing survives |

Twelve route classes × four status classes × two bot flags = at most 96 rows an hour, and
in practice a handful. A month is a few thousand rows.

**What is never in it:** IP address, any hash of one, User-Agent, referrer, query string,
path, docket or party ids, cookies (none exist), session (none exists), country, anything
per request. The row cannot be joined to anything else because nothing else exists.

## Where it is measured, and why not the access log

Caddy's access log already drops the address and User-Agent (ADR 0011) and is kept for
days; it has no bot flag and would need the path to classify the route. Rather than keep a
richer log to aggregate from, the **web app counts in memory**: the existing `http_hygiene`
middleware sees path, status, bytes and elapsed time, classifies the route and the agent on
the spot, increments a counter, and forgets the request. Once an hour the counters are
written and reset. No per-request record exists anywhere, at any point, even transiently on
disk.

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

- [ ] The operator signs the sentence above (or edits it); nothing is built before that.
- [ ] Route-class list confirmed.
- [ ] Retention confirmed (90 days hourly, daily forever).
- [ ] Whether bot/not is worth the User-Agent match at all, given that the string is seen
      in memory either way — the alternative is no bot flag and a simpler sentence.
