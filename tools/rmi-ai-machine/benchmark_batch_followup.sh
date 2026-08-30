#!/usr/bin/env bash
# Wait for the running benchmark batch to exit, then run benchmark_batch.sh again so that
# models appended to its list while it ran are picked up. Models already answered skip
# through in seconds (benchmark_run.py skips a decision whose JSON exists).
#
#     nohup bash benchmark_batch_followup.sh >> /data/docketyard/benchmark/batch.log 2>&1 &
#
# The pgrep pattern is bracketed so it does not match this script's own command line.
set -u
cd "$(dirname "$0")"
while pgrep -f '[b]enchmark_batch\.sh' > /dev/null; do
  sleep 120
done
echo "===== follow-up batch  $(date -Is)"
exec bash benchmark_batch.sh
