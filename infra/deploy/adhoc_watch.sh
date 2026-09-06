#!/bin/sh
# /srv/docketyard/adhoc_watch.sh — how long has ad-hoc work been busy? A GAUGE, not a verdict.
#
# ADR 0019: the alert lives in Grafana Cloud, off the box; nothing here decides anything. This
# writes into the same textfile directory `unit_outcome.sh` uses and Alloy's unix exporter
# reads (config.alloy).
#
# WHAT IT WATCHES AND WHY. The 2026-09-06 outage was a query left running for 22 hours. The
# no-data alert would not have caught it: the record was fresh and the poller was fine — the
# site simply could not serve. What was anomalous was an ad-hoc process still burning CPU a
# day after somebody typed it, and nothing measured that.
#
# The signal is the ELAPSED time of the longest-running BUSY process in the user slice. Busy
# matters: an idle ssh session is legitimately open for hours at 0% CPU, and reporting it
# would make the gauge meaningless. A run that finished leaves 0, so a threshold in Grafana
# reads "something ad-hoc has been working for longer than N", which is the question.
set -eu
dir=/srv/docketyard/data/metrics
mkdir -p "$dir"
f="$dir/adhoc.prom"
floor=${ADHOC_CPU_FLOOR:-5}   # percent, below which a process is idle rather than working

longest=0
busiest=0
for stat in /proc/[0-9]*/cgroup; do
    pid=${stat#/proc/}
    pid=${pid%/cgroup}
    grep -q 'user\.slice' "$stat" 2>/dev/null || continue
    # `ps` rather than /proc arithmetic: pcpu here is CPU over the process's whole life, which
    # is the average this gauge wants — a spike does not raise it and a long grind does.
    read -r etimes pcpu <<EOF || continue
$(ps -o etimes=,pcpu= -p "$pid" 2>/dev/null)
EOF
    [ -n "${etimes:-}" ] || continue
    # integer compare without bc: pcpu is like `99.3`, so cut at the point
    [ "${pcpu%%.*}" -ge "$floor" ] 2>/dev/null || continue
    [ "$etimes" -gt "$longest" ] 2>/dev/null && longest=$etimes
    [ "${pcpu%%.*}" -gt "$busiest" ] 2>/dev/null && busiest=${pcpu%%.*}
done

{
  echo "# HELP docketyard_adhoc_busy_seconds elapsed seconds of the longest-running busy process in the user slice"
  echo "# TYPE docketyard_adhoc_busy_seconds gauge"
  echo "docketyard_adhoc_busy_seconds $longest"
  echo "# HELP docketyard_adhoc_busiest_percent CPU percent of the busiest process in the user slice"
  echo "# TYPE docketyard_adhoc_busiest_percent gauge"
  echo "docketyard_adhoc_busiest_percent $busiest"
  echo "# HELP docketyard_adhoc_seen_seconds when this was measured, unix time"
  echo "# TYPE docketyard_adhoc_seen_seconds gauge"
  echo "docketyard_adhoc_seen_seconds $(date +%s)"
} > "$f.tmp"
mv "$f.tmp" "$f"
