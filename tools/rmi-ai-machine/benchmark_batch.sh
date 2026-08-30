#!/usr/bin/env bash
# Benchmark step 2, more local candidates: pull each Ollama model in turn and run
# benchmark_run.py over the sixty sampled decisions with the current prompt, so every
# run is scorable against the checked sheet (docs/extraction-benchmark.md § Step 2).
#
# Runs on RMI-AI-MACHINE, unattended:
#     nohup bash benchmark_batch.sh > /data/docketyard/benchmark/batch.log 2>&1 &
# Re-runnable: benchmark_run.py skips decisions already answered, so a model that was
# interrupted resumes where it stopped. Nothing here reads labels.csv.
#
# Sizing (12 GB VRAM, 64 GB RAM): dense models to 14B sit on the GPU at Q4; the MoE
# candidates run split across CPU and GPU, slower per page but with ~3B active parameters.
# The first entry re-runs qwen3:14b on the current prompt — the scored run predates
# `target_kind` and was placed by the scorer's fallback, so it is not a fair baseline.

set -u
TEXT=/data/docketyard/benchmark/text
OUT=/data/docketyard/benchmark/runs
MODELS=(
  qwen3:14b
  qwen2.5:14b
  gemma3:12b
  phi4:14b
  mistral-nemo:12b
  llama3.1:8b
  qwen3:30b-a3b
  gpt-oss:20b
)

cd "$(dirname "$0")"
for m in "${MODELS[@]}"; do
  echo "===== $m  $(date -Is)"
  if ! ollama pull "$m"; then
    echo "$m: pull failed, skipping"
    continue
  fi
  start=$(date +%s)
  python3 benchmark_run.py --model "$m" --text-dir "$TEXT" --out "$OUT"
  echo "$m: finished in $(( ($(date +%s) - start) / 60 )) min"
  # free the VRAM for the next one
  ollama stop "$m" 2>/dev/null || true
done
echo "===== batch done $(date -Is)"
