#!/usr/bin/env python3
"""Docket Yard's alert rules and dashboard, provisioned into Grafana Cloud by API.

    GRAFANA_URL=https://<stack>.grafana.net GRAFANA_SA_TOKEN=<service account token> \\
    GRAFANA_CONTACT_EMAIL=<address> python infra/grafana/provision.py [--dry-run]

THE RULES ARE THE PROMISES, IN CODE. ADR 0019 moved detection off the box into Grafana Cloud
and said the thresholds `docs/alerts.md` states would become alert rules there; on
2026-09-10 the operator noted that metrics had been arriving for eight days and no rule or
dashboard had ever been written — the exact gap ADR 0019 was accepted to close. Every rule
below quotes the document it enforces. A threshold that changes here changes there in the
same commit (CLAUDE.md: published pages and internal specs come from one source).

Idempotent: rules carry fixed UIDs and are created or updated; the folder, the contact point,
the notification policy route and the dashboard likewise. Nothing is deleted. The token is a
Grafana service account with the Editor role (Administration → Service accounts), created
once and held outside the repository; the metrics-write token cannot do this.

Standard library only.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

FOLDER_UID = "docket-yard"
FOLDER_TITLE = "Docket Yard"
CONTACT_POINT = "docket-yard-email"
DASHBOARD_UID = "docket-yard-record"

PROD = 'service="docket_yard"'
FLEET = 'service="docket_yard_fleet"'
BOXES = 'service=~"docket_yard_fleet"'

# --- what the documents promise, as numbers -----------------------------------------------
H, D = 3600, 86400
FRESHNESS = {
    # docs/alerts.md § The heartbeat — the six timestamps and their thresholds
    "last_forward_capture": (
        3 * H,
        "the poller is dead, or every pass is refused (nonce, WAF, criteria)",
    ),
    "last_event": (
        6 * D,
        "records fetch but nothing is recorded: the parser or the ledger write broke",
    ),
    "last_enviro_capture": (3 * H, "the comment poll is dead, refused, or its parser broke"),
    "last_enviro_event": (
        21 * D,
        "comments parse but none is recorded (21 days: the measured longest silence is 14)",
    ),
    "last_document": (
        6 * D,
        "records arrive but their files do not: the fetch broke or the WAF refuses GETs",
    ),
    "oldest_pending_alert": (
        3 * H,
        "alerts are built but mail does not leave: SES, credentials, the sender",
    ),
}

DISK = (
    f'node_filesystem_avail_bytes{{{PROD},mountpoint="/"}}'
    f' / node_filesystem_size_bytes{{{PROD},mountpoint="/"}}'
)
MEM = f"node_memory_MemAvailable_bytes{{{PROD}}} / node_memory_MemTotal_bytes{{{PROD}}}"
REFUSED = f'docket_yard_document_store_refused_total{{{PROD},kind=~"mismatch|absent"}}'
BOX_MEM = f"node_memory_MemAvailable_bytes{{{BOXES}}} / node_memory_MemTotal_bytes{{{BOXES}}}"


def rules(ds: str) -> list[dict]:
    """Every rule: title, PromQL, `for`, severity, and the sentence a person reads at 3 a.m."""
    out = []

    def rule(uid, title, expr, for_, severity, summary, group, gt=0):
        out.append(
            {
                "uid": f"dy-{uid}",
                "title": title,
                "ruleGroup": group,
                "folderUID": FOLDER_UID,
                "condition": "B",
                "for": for_,
                # absence is alerted on explicitly, below, where it means something
                "noDataState": "OK",
                "execErrState": "Error",
                "labels": {"severity": severity, "service": "docket_yard"},
                "annotations": {"summary": summary},
                "data": [
                    {
                        "refId": "A",
                        "relativeTimeRange": {"from": 600, "to": 0},
                        "datasourceUid": ds,
                        "model": {"refId": "A", "expr": expr, "instant": True, "range": False},
                    },
                    {
                        "refId": "B",
                        "datasourceUid": "__expr__",
                        "model": {
                            "refId": "B",
                            "type": "threshold",
                            "expression": "A",
                            "conditions": [{"evaluator": {"type": "gt", "params": [gt]}}],
                        },
                    },
                ],
            }
        )

    # ADR 0019 § 3: the primary death detector is an alert on ABSENCE. A dead box cannot
    # report its own death; only the series ceasing to arrive can.
    rule(
        "prod-absent",
        "Production: no metrics for 10 minutes",
        f"absent(docket_yard_up{{{PROD}}})",
        "10m",
        "critical",
        "The instance, the web process or Alloy has stopped reporting. ADR 0019: a dead box"
        " cannot report its own death; this is the rule that notices. Check the box, then"
        " `docker compose ps` — and whether the maintenance flag is up"
        " (X-Docketyard-Maintenance).",
        "production",
    )
    rule(
        "prod-web-down",
        "Production: web did not answer the scrape",
        f"docket_yard_up{{{PROD}}} == 0",
        "5m",
        "critical",
        "Alloy reached the box but the web process did not answer /metrics. webwatch restarts"
        " it when unhealthy; if this persists the restart is not taking.",
        "production",
    )
    for kind, (limit, meaning) in FRESHNESS.items():
        human = f"{limit // D} days" if limit >= D else f"{limit // H} hours"
        rule(
            f"prod-stale-{kind.replace('_', '-')}",
            f"Production: {kind} older than {human}",
            f'docket_yard_freshness_age_seconds{{{PROD},kind="{kind}"}}'
            f' and on(kind) docket_yard_freshness_known{{{PROD},kind="{kind}"}} == 1',
            "15m",
            "warning" if limit >= D else "critical",
            f"docs/alerts.md § The heartbeat: {meaning}. Threshold {human}. A null timestamp"
            " (never happened) does not fire this; only a known timestamp going stale does.",
            "production",
            gt=limit,
        )
    rule(
        "prod-schema-gap",
        "Production: store schema differs from the image's",
        f"docket_yard_schema_version{{{PROD}}} != docket_yard_schema_expected{{{PROD}}}",
        "15m",
        "critical",
        "The image wants a migration the store has not had, or the store is ahead of the image."
        " A deploy in flight looks like this for a minute; fifteen minutes is a deploy that"
        " stopped (`docker compose logs migrate`). Rollback is a Litestream restore, not a tag.",
        "production",
    )
    rule(
        "prod-store-refused",
        "Production: the document store refused a known document",
        f"increase({REFUSED}[1h])",
        "0m",
        "critical",
        "S3 answered a content-addressed key with the wrong bytes (mismatch) or nothing (absent):"
        " the store has lost or corrupted a document. Somebody must go and look. `unreachable`"
        " is an outage and is deliberately not this rule.",
        "production",
    )
    rule(
        "prod-load",
        "Production: load average above 4 on 2 vCPUs for 15 minutes",
        f"node_load5{{{PROD}}}",
        "15m",
        "warning",
        "The 2026-09-06 outage reached a load of 20 with the record fresh and the site unable to"
        " serve. Check docketyard_adhoc_* (an ad-hoc job pinning a core) and the blobs timer.",
        "production",
        gt=4,
    )
    rule(
        "prod-adhoc-hog",
        "Production: an ad-hoc process has been busy for an hour",
        f"docketyard_adhoc_busy_seconds{{{PROD}}}",
        "5m",
        "warning",
        "infra/deploy/adhoc_watch.sh: something in the user slice has held a core for an hour."
        " The 2026-09-06 outage was a `python3 -` heredoc that never got EOF and ran 22 hours."
        " The slice is capped at half a core now; this says the cap is being leaned on.",
        "production",
        gt=3600,
    )
    rule(
        "prod-disk",
        "Production: root filesystem under 10% free",
        f"{DISK} < 0.10",
        "15m",
        "warning",
        "The blob cache prunes to keep 20 GB free; if this fires the prune is not keeping up or"
        " something else is filling the disk (a dry-run copy of the store, a log).",
        "production",
    )
    rule(
        "prod-memory",
        "Production: under 10% memory available",
        f"{MEM} < 0.10",
        "15m",
        "warning",
        "8 GB box. A documents wave was OOM-killed at 1.37 GB RSS on the old 2 GB instance;"
        " streaming fixed that, but a new consumer can do it again.",
        "production",
    )

    # docs/compute-fleet.md § The monitor, and what detection means — the three rules
    rule(
        "fleet-stalled",
        "Fleet: pages owed and none read for 30 minutes",
        f"docket_yard_fleet_stalled{{{FLEET}}}",
        "10m",
        "critical",
        "The queue owes pages and no worker has read one in half an hour: a server that has not"
        " come back, a worker loop that stopped, a box that is off. The 2026-09-06 run died"
        " unnoticed for three days; this is the rule that notices. Open the monitor on the"
        " coordinator (:8130) and the workers' logs.",
        "fleet",
    )
    rule(
        "fleet-failing",
        "Fleet: more pages failed than read in the last hour",
        f"docket_yard_fleet_failing{{{FLEET}}}",
        "10m",
        "critical",
        "The fleet is finishing pages briskly and most of them are failures — a worker whose"
        " environment is wrong, or a document set the guard refuses. Failures by reason are on"
        " the monitor page.",
        "fleet",
    )
    rule(
        "fleet-absent",
        "Fleet: no metrics from the coordinator for 10 minutes",
        f"absent(docket_yard_fleet_last_read_known{{{FLEET}}})",
        "10m",
        "critical",
        "The coordinator, its monitor or its Alloy is gone. The workers keep their leases for"
        " 45 minutes and then stop; nothing is lost, and nothing is read.",
        "fleet",
    )
    return out


def dashboard(ds: str) -> dict:
    name = "{{__name__}}"

    def panel(title, exprs, x, y, w=12, h=8, unit=None, kind="timeseries", legend=None):
        return {
            "type": kind,
            "title": title,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "datasource": {"type": "prometheus", "uid": ds},
            "targets": [
                {"refId": chr(65 + i), "expr": e, "legendFormat": legend or "{{kind}}"}
                for i, e in enumerate(exprs)
            ],
            "fieldConfig": {"defaults": {"unit": unit} if unit else {}, "overrides": []},
            "options": {},
        }

    panels = [
        panel(
            "Record freshness (age of the newest row, by kind)",
            [f"docket_yard_freshness_age_seconds{{{PROD}}}"],
            0,
            0,
            unit="s",
        ),
        panel(
            "Web up / schema",
            [
                f"docket_yard_up{{{PROD}}}",
                f"docket_yard_schema_version{{{PROD}}}",
                f"docket_yard_schema_expected{{{PROD}}}",
            ],
            12,
            0,
            kind="stat",
            legend=name,
        ),
        panel("Load (5 min) on 2 vCPUs", [f"node_load5{{{PROD}}}"], 0, 8, legend="load5"),
        panel(
            "Ad-hoc busy seconds (user slice)",
            [f"docketyard_adhoc_busy_seconds{{{PROD}}}"],
            12,
            8,
            unit="s",
            legend="busy",
        ),
        panel(
            "Store refusals (1h increase, by kind)",
            [f"increase(docket_yard_document_store_refused_total{{{PROD}}}[1h])"],
            0,
            16,
            legend="{{kind}}",
        ),
        panel("Disk and memory available", [DISK, MEM], 12, 16, unit="percentunit", legend=name),
        panel(
            "Fleet: pages by state",
            [f"docket_yard_fleet_jobs{{{FLEET}}}"],
            0,
            24,
            legend="{{pass}} {{state}}",
        ),
        panel(
            "Fleet: pages in the last hour, by outcome",
            [f"docket_yard_fleet_pages_last_hour{{{FLEET}}}"],
            12,
            24,
            legend="{{pass}} {{outcome}}",
        ),
        panel(
            "Fleet: seconds since a page was read",
            [f"docket_yard_fleet_last_read_age_seconds{{{FLEET}}}"],
            0,
            32,
            unit="s",
            legend="{{pass}}",
        ),
        panel(
            "Fleet: stalled / failing",
            [f"docket_yard_fleet_stalled{{{FLEET}}}", f"docket_yard_fleet_failing{{{FLEET}}}"],
            12,
            32,
            kind="stat",
            legend=name,
        ),
        panel(
            "Fleet: workers, seconds since last seen",
            [f"docket_yard_fleet_worker_last_seen_age_seconds{{{FLEET}}}"],
            0,
            40,
            w=24,
            unit="s",
            legend="{{worker}}",
        ),
        panel("Fleet boxes: load (5 min)", [f"node_load5{{{BOXES}}}"], 0, 48, legend="{{host}}"),
        panel(
            "Fleet boxes: memory available",
            [BOX_MEM],
            12,
            48,
            unit="percentunit",
            legend="{{host}}",
        ),
    ]
    return {
        "uid": DASHBOARD_UID,
        "title": "Docket Yard — the record and the fleet",
        "tags": ["docket-yard"],
        "timezone": "utc",
        "schemaVersion": 39,
        "time": {"from": "now-24h", "to": "now"},
        "refresh": "1m",
        "panels": panels,
    }


# --- the API ---------------------------------------------------------------------------------


class Grafana:
    def __init__(self, url: str, token: str, dry: bool):
        self.url, self.token, self.dry = url.rstrip("/"), token, dry

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.url + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-Disable-Provenance": "true",  # editable in the UI afterwards
            },
        )
        if self.dry and method != "GET":
            print(f"  would {method} {path}")
            return {}
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 404:
                return None
            raise SystemExit(f"{method} {path} -> {e.code}: {detail}") from e

    def upsert(self, path: str, uid: str, body: dict, label: str):
        exists = self.call("GET", f"{path}/{uid}")
        if exists is None:
            self.call("POST", path, body)
            print(f"  created {label}")
        else:
            self.call("PUT", f"{path}/{uid}", body)
            print(f"  updated {label}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Provision Docket Yard's Grafana rules and dashboard")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    url, token = os.environ.get("GRAFANA_URL"), os.environ.get("GRAFANA_SA_TOKEN")
    email = os.environ.get("GRAFANA_CONTACT_EMAIL")
    if not (url and token and email):
        print("set GRAFANA_URL, GRAFANA_SA_TOKEN and GRAFANA_CONTACT_EMAIL", file=sys.stderr)
        return 2
    g = Grafana(url, token, args.dry_run)

    sources = g.call("GET", "/api/datasources") or []
    prom = [d for d in sources if d.get("type") == "prometheus"]
    if not prom:
        print("no Prometheus data source in this stack", file=sys.stderr)
        return 2
    ds = prom[0]["uid"]
    print(f"data source: {prom[0]['name']} ({ds})")

    print("folder")
    if g.call("GET", f"/api/folders/{FOLDER_UID}") is None:
        g.call("POST", "/api/folders", {"uid": FOLDER_UID, "title": FOLDER_TITLE})
        print("  created")
    else:
        print("  exists")

    print("contact point")
    cp = {
        "name": CONTACT_POINT,
        "type": "email",
        "settings": {"addresses": email, "singleEmail": True},
        "disableResolveMessage": False,
    }
    points = g.call("GET", "/api/v1/provisioning/contact-points") or []
    existing = [c for c in points if c["name"] == CONTACT_POINT]
    if existing:
        g.call("PUT", f"/api/v1/provisioning/contact-points/{existing[0]['uid']}", cp)
        print("  updated")
    else:
        g.call("POST", "/api/v1/provisioning/contact-points", cp)
        print("  created")

    print("notification policy route")
    tree = g.call("GET", "/api/v1/provisioning/policies") or {}
    routes = tree.get("routes") or []
    ours = {
        "receiver": CONTACT_POINT,
        "object_matchers": [["service", "=", "docket_yard"]],
        "group_by": ["alertname"],
        "group_wait": "1m",
        "group_interval": "5m",
        "repeat_interval": "4h",
    }
    tree["routes"] = [r for r in routes if r.get("receiver") != CONTACT_POINT] + [ours]
    if not tree.get("receiver"):
        tree["receiver"] = CONTACT_POINT
    g.call("PUT", "/api/v1/provisioning/policies", tree)
    print("  set")

    print("alert rules")
    for r in rules(ds):
        g.upsert("/api/v1/provisioning/alert-rules", r["uid"], r, r["title"])

    print("dashboard")
    g.call(
        "POST",
        "/api/dashboards/db",
        {"dashboard": dashboard(ds), "folderUid": FOLDER_UID, "overwrite": True},
    )
    print(f"  {DASHBOARD_UID} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
