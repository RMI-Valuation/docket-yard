# Grafana Cloud — the rules and the dashboard

`provision.py` carries every alert rule the documents promise and one dashboard, and writes
them into the Grafana Cloud stack by API. The rules ARE the promises: `docs/alerts.md` § The
heartbeat (the six freshness thresholds), ADR 0019 (absence as the death detector, the schema
gap, the store's refusals, the host's vitals, the ad-hoc gauge from the 2026-09-06 outage),
and `docs/compute-fleet.md` § The monitor (stalled, failing, absent). A threshold changes
here and in its document in the same commit.

```
GRAFANA_URL=https://<stack>.grafana.net \
GRAFANA_SA_TOKEN=<service account token> \
GRAFANA_CONTACT_EMAIL=<where alerts go> \
python infra/grafana/provision.py --dry-run     # then without --dry-run
```

The token is a Grafana service account (the stack's own Administration → Users and access →
Service accounts, not the Cloud portal's access policies, which cannot reach this API): basic
role Editor plus the fixed role **Alerting provisioning writer**, which Editor does not carry
and the provisioning endpoints require. Created once, kept with the other credentials outside
this repository (`.docketyard` and `*.token` are git-ignored). The script is idempotent: fixed
UIDs, create-or-update, nothing deleted, and the rules stay editable in the UI
(`X-Disable-Provenance`).

**Provisioned 2026-09-10 into the operator's stack**: all seventeen rules evaluated healthy on
first evaluation (eleven Normal with data, seven Normal with no data — the filters that return
nothing while things are fine), and a temporary always-firing rule was routed by the
alertmanager to the contact point and then deleted, proving the path to mail. This is the
half of ADR 0019 that had not been done: production's absence detector exists from this day.

What it writes: a folder "Docket Yard"; an email contact point; a notification-policy route
matching `service=docket_yard` (every rule carries that label) to it; seventeen rules in two
groups, `production` and `fleet`; a dashboard, "Docket Yard — the record and the fleet".

Series that arrived before the `service` external label was set carry `service="node"`;
every rule and panel selects `docket_yard` or `docket_yard_fleet`, so those never match, and
the free tier's fourteen-day retention ages them out.
