#!/usr/bin/env bash
# After the extraction batch (and its follow-up) fully drain, run the role classifier
# over the sixty decisions with two local models. Resumable per decision.
#
#     nohup bash benchmark_roles_followup.sh > /data/docketyard/benchmark/roles.log 2>&1 &
#
# The pgrep patterns are bracketed so this script's own command line never matches.
set -u
cd "$(dirname "$0")"
# the box's own walk store has no decision_record rows (measured 2026-08-30), so the
# workstation ships a copy of the production store to sit beside the benchmark data
REG=/data/docketyard/benchmark/registry.sqlite
while pgrep -f '[b]enchmark_batch\.sh' > /dev/null || pgrep -f '[b]enchmark_batch_followup\.sh' > /dev/null; do
  sleep 300
done
echo "===== roles  $(date -Is)  registry=$REG"
for m in qwen3:14b llama3.1:8b; do
  echo "===== roles $m  $(date -Is)"
  ollama pull "$m" || continue
  python3 benchmark_roles.py --model "$m" --text-dir /data/docketyard/benchmark/text \
    --registry "$REG" --out /data/docketyard/benchmark/runs-roles
  ollama stop "$m" 2>/dev/null || true
done
echo "===== roles done  $(date -Is)"
