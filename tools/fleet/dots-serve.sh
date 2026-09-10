#!/usr/bin/env bash
# The dots.mocr server, restarted whenever it dies (docs/compute-fleet.md).
#
#   tmux new -d -s dots-vllm 'bash ~/docket-yard/tools/fleet/dots-serve.sh'
#
# On 2026-09-06 the server died of CUDA out-of-memory on a 12-megapixel page and stayed
# dead for three days. Two changes here, each honest about what it is worth:
#
#   --gpu-memory-utilization 0.90   was 0.95. The driver is serial, so the KV cache only ever
#                                   holds one 16k request; the 0.5 GB given back is headroom
#                                   for the vision encoder's activations, the thing that OOMed.
#   expandable_segments             the allocator grows segments instead of fragmenting them;
#                                   what vLLM's own docs recommend against fragmentation OOM
#                                   over long runs. Not proven to matter here; costs nothing.
#
# Neither is the guard: the worker refuses pages over 6 MP before they reach the server.
# The loop is the third thing. A server that dies is back in about a minute, and the
# worker, which waits for it, carries on; a server that dies on EVERY start will loop
# here forever at one start a minute, which the fleet monitor shows as STALLED.

set -u
cd ~/ocr-bench || exit 1
LOG=/data/docketyard/ocr/logs/vllm.log
export VLLM_USE_FLASHINFER_SAMPLER=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
while true; do
    echo "$(date -Is) starting vllm" >> "$LOG"
    ./.venv-vllm/bin/vllm serve rednote-hilab/dots.mocr \
        --served-model-name dots-mocr --trust-remote-code \
        --chat-template-content-format string --port 8120 \
        --gpu-memory-utilization 0.90 --max-model-len 16384 >> "$LOG" 2>&1
    echo "$(date -Is) vllm exited $?; restarting in 60 s" >> "$LOG"
    sleep 60
done
