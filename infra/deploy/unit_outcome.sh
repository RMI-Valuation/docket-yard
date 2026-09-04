#!/bin/sh
# /srv/docketyard/unit_outcome.sh <unit prefix> <0|1> — one gauge per periodic unit, for Alloy's
# textfile collector: 1 written by docketyard-failed@.service (OnFailure=), 0 by the unit's own
# ExecStartPost on the next success. Atomic rename, so the collector never reads a half file.
set -eu
dir=/srv/docketyard/data/metrics
mkdir -p "$dir"
f="$dir/$1.prom"
{
  echo "# HELP docketyard_unit_failed 1 while the unit's last run failed, 0 once a run succeeds"
  echo "# TYPE docketyard_unit_failed gauge"
  echo "docketyard_unit_failed{unit=\"$1\"} $2"
  echo "# HELP docketyard_unit_outcome_seconds when that outcome was written, unix time"
  echo "# TYPE docketyard_unit_outcome_seconds gauge"
  echo "docketyard_unit_outcome_seconds{unit=\"$1\"} $(date +%s)"
} > "$f.tmp"
mv "$f.tmp" "$f"
