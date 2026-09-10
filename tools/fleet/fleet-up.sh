#!/usr/bin/env bash
# Bring the fleet's node up on RMI-AI-MACHINE: tmux sessions, each started only if it
# is not already running (docs/compute-fleet.md § Running it). Five sessions:
#
#   bash ~/docket-yard/tools/fleet/fleet-up.sh          # start what is not running
#   tmux ls                                             # the sessions
#   tmux attach -t dots-worker                          # watch one; detach with C-b d
#
#   dots-vllm      the server, restarted when it dies         (dots-serve.sh)
#   dots-worker    the worker, restarted when it exits         (below)
#   dots-collect   reading documents every ten minutes         (pagequeue.py collect)
#   fleet-monitor  the status page and the scrape on :8130     (monitor.py)
#   fleet-queue    the lease calls and the blobs on :8131, for another machine's worker
#                  (queue_server.py; the token is one line in /data/docketyard/fleet.token)
#
# The worker exits 0 when the queue is empty, 2 when the server has been gone half an hour,
# 3 when the server dies on two different pages in a row, 4 when a failure was nobody's we
# named (a missing blob, an import), 5 when too many pages failed in a row. The loop below
# restarts it after a minute whatever the code, so a refilled queue or a returned server is
# picked up without anyone typing, and a worker failing on every start is throttled to one
# attempt a minute — which the monitor shows as STALLED, since nothing is being read.

set -u
FLEET=~/docket-yard/tools/fleet
OCR=/data/docketyard/ocr
DB=$OCR/queue.sqlite
PY=~/ocr-bench/.venv-paddle/bin/python
LOG=$OCR/logs
mkdir -p "$LOG"

up() {  # up <session> <command>
    if tmux has-session -t "$1" 2>/dev/null; then
        echo "$1: running"
    else
        tmux new-session -d -s "$1" "$2"
        echo "$1: started"
    fi
}

WORKER="$PY $FLEET/dots_worker.py --db $DB --blobs /data/docketyard/blobs --scratch $OCR/.render"
COLLECT="$PY $FLEET/pagequeue.py --db $DB collect --out $OCR"

up dots-vllm "bash $FLEET/dots-serve.sh"
up dots-worker "while true; do $WORKER >> $LOG/dots-worker.log 2>&1; \
    echo \"\$(date -Is) worker exited \$?\" >> $LOG/dots-worker.log; sleep 60; done"
up dots-collect "while true; do $COLLECT >> $LOG/dots-collect.log 2>&1; sleep 600; done"
up fleet-monitor "$PY $FLEET/monitor.py --db $DB --port 8130 >> $LOG/monitor.log 2>&1"
up fleet-queue "$PY $FLEET/queue_server.py --db $DB --blobs /data/docketyard/blobs     --token-file /data/docketyard/fleet.token --port 8131 >> $LOG/queue-server.log 2>&1"
