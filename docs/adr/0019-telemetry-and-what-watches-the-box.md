# ADR 0019 — Telemetry, and what watches the box

- **Status:** Proposed
- **Date:** 2026-09-02

## Context

ADR 0012 settled the principle: **heartbeats live off the box, because a dead box cannot
report its own death.** The mechanism chosen for it was a GitHub Actions schedule that asks
`/health` for its freshness once an hour and fails loudly when a threshold in
`docs/alerts.md` is crossed. That principle is right and is not in question here. The
mechanism was measured against a real outage on 2026-09-02 and did not hold.

**What the outage established**, all of it from `sar` and the capture ledger rather than
inference:

- The last successful capture was **03:26:31 UTC**; the next was **10:18:31**, immediately
  after a manual reboot. The record went unkept for **6 h 52 m**.
- The instance stopped answering at **05:06** — so the poller had already been dead for
  **100 minutes while the site served normally**. A reader visiting at 04:00 saw a working
  site with a silently stale record.
- Load average left 0.45 and reached 13 at **02:10**, then held 15–21 on two vCPUs until
  06:40, at ~82% CPU with negligible iowait. That is **75 minutes of warning before captures
  stopped** and nearly three hours before the site fell over.
- The heartbeat fired at **09:39** — a detection time of **6 h 13 m** against a stated
  three-hour intent, because GitHub runs that hourly cron at three-to-five hour intervals
  (measured over 2026-09-01: 05:11, 10:08, 14:54, 18:32, 21:47, 00:15). `docs/alerts.md`
  therefore describes a guarantee its scheduler does not deliver.
- **The cause is still unestablished.** Container logs died with the containers, and the only
  reason a timeline exists at all is that `sysstat` happened to be installed. Nothing was
  recording the box's own vital signs.

So there are two separate failures. Detection was slow, and when it did arrive there was
almost nothing to diagnose with. The first is a mechanism problem; the second is an absence
of instrumentation.

RMI Valuation already answers this for the sibling platform. Its **ADR 0022** chose
Prometheus-style metrics with **Grafana Cloud's free tier** as the sink and a **Grafana
Alloy** container doing the scraping and `remote_write` — instrumentation vendor-neutral and
code-owned, secrets from the environment, nothing baked into an image. That decision has
shipped and is running. This ADR does not re-litigate it; it adopts it, and records the two
places where this project's shape differs.

## Decision

1. **`/metrics` on the web app, in the Prometheus text exposition format** — bearer-token
   guarded, and **404 rather than 401 when no token is configured**, matching the sibling's
   posture so the surface does not exist unless it is deliberately turned on. The numbers are
   the ones `projections.freshness()` already computes for `/health`: capture, event,
   document and pending-alert ages. **No new dependency.** Six gauges in a documented text
   format is standard-library work, and `pyproject.toml`'s rule is that a dependency earns
   its place. The metric *grammar* is what outlives the sink — that is ADR 0022's own
   argument, and it costs nothing to honour.

2. **Grafana Alloy runs as a compose service** beside `web`, `ingest`, `litestream` and
   `caddy`. It scrapes `/metrics` over localhost with the token, and — because this project
   runs on an **instance** rather than a container service — it also runs
   `prometheus.exporter.unix` for load, CPU, memory and disk. The sibling could not do that.
   The scrape interval is 60 s and the collector set is **chosen explicitly rather than left
   at its defaults**, because the free tier is 10,000 series and the unix exporter is chatty.
   Endpoint, username and token arrive as environment variables; none of them enters this
   repository, which is public.

3. **The primary death detector is an alert on absence, evaluated in Grafana Cloud.** This is
   the load-bearing part of the decision. Alloy runs on the box and dies with it; it does not
   report the death. What reports the death is Grafana Cloud noticing that the series stopped
   arriving, and Grafana Cloud is off the box. **ADR 0012's principle is unchanged — only its
   mechanism moves**, from a scheduler that runs when it feels like it to one that evaluates
   every minute.

4. **`docs/alerts.md` keeps ownership of *what* is checked**; Grafana owns *when* and *how
   loudly*. The silent-failure decomposition — no captures, captures but no events, events but
   no deliveries — is a statement about this record and belongs in the repository. The
   thresholds move to alert rules. The document is corrected in the same change, because it
   currently publishes a three-hour detection guarantee that was not true.

5. **The GitHub heartbeat stays, demoted.** It is free, it is genuinely independent of both
   the box and Grafana, and it asks the question a reader would ask — over HTTPS, from
   outside. It is no longer the primary and its slowness is no longer a defect, because it is
   no longer what we rely on.

6. **Bounded cardinality is a design rule, not an optimisation** — no docket number, party id
   or URL ever becomes a label.

## Consequences

Detection of a dead box goes from hours to minutes, and detection of a *stale but serving*
box — the failure that actually happened, and the one a reader cannot see — becomes possible
at all. The next incident is diagnosed from recorded vital signs instead of from whatever
`sysstat` happened to keep. Load became abnormal 75 minutes before the record stopped being
kept, so there is a real prospect of alerting before a gap opens rather than after.

The costs are honest and small. One more container in production and one more external
service in the path of knowing whether things work — though not in the path of *serving*,
which still degrades to exactly what it is today if Grafana is unreachable. Free-tier bounds
(10k series, 14-day retention) mean retention is short: this is an alerting and
recent-diagnosis tool, not an archive, and anything that needs to be kept belongs in the
store as a row. Two more secrets to hold.

What it forecloses: very little. The exposition is a standard format and the grammar is
portable, so changing sink means pointing a different scraper at the same endpoint.

## Cost of reversing

Cheap, and deliberately so. Remove a compose service and a route; delete two environment
variables. Nothing in the store depends on it, no published page renders from it, and no
assertion carries it as provenance. Fourteen days after removal the sink has forgotten it
too. This is a two-way door and is written down because it changes the production topology
ADR 0012 fixed, not because it is hard to undo.

## Validation

Against `docs/validation-queries.md` this changes nothing: it adds no table, no column and no
assertion, so all five queries are untouched, and no figure any page publishes moves.

Against **ADR 0012** it is an amendment in the same direction rather than a reversal — the
heartbeat stays off the box, and the sentence "a dead box cannot report its own death" is the
reason the primary alert is absence-of-data evaluated remotely rather than anything Alloy
does locally.

Against **ADR 0007** nothing here is a derived assertion about the record; these are
operational measurements about a machine, they never reach a reader, and they carry no
provenance because they assert nothing about the Board's proceedings.

Against **ADR 0011** the metrics carry no reader data and no identifiers. `/metrics` is
counted with `/health` among the paths that are never cached and are disallowed to crawlers,
and it is additionally token-guarded, which `/health` is not.

Against the sibling's **ADR 0022**, the differences are two and both are consequences of
topology: no `prometheus_client` dependency, because six gauges do not earn one; and host
metrics are in scope, because this runs on an instance and that project does not.
