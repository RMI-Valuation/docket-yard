#!/usr/bin/env bash
# Bring a fleet machine up: tmux sessions for its role, each started only if it is not
# already running (docs/compute-fleet.md § Running it).
#
#   bash ~/docket-yard/tools/fleet/fleet-up.sh coordinator   # the box that holds the queue
#   bash ~/docket-yard/tools/fleet/fleet-up.sh worker        # a GPU box reading for it
#   bash ~/docket-yard/tools/fleet/fleet-up.sh all           # both on one box (how it began)
#   tmux ls                                                  # the sessions
#   tmux attach -t dots-worker                               # watch one; detach with C-b d
#
#   coordinator:  fleet-queue    the lease calls and the blobs on :8131   (queue_server.py)
#                 fleet-monitor  the status page and the scrape on :8130  (monitor.py)
#                 dots-collect   reading documents every ten minutes      (pagequeue.py collect)
#   worker:       dots-vllm      the server, restarted when it dies       (dots-serve.sh)
#                 dots-worker    the worker, restarted when it exits      (below)
#
# DY_FLEET_DATA is the data root (default /data/docketyard): `<root>/blobs`, `<root>/ocr`,
# the queue at `<root>/ocr/queue.sqlite`, the token at `<root>/fleet.token`. A worker
# whose queue is elsewhere names it in `<root>/fleet-node` (one line, `http://<host>:8131`)
# and reads blobs from its own `<root>/blobs` if that exists, else fetches them. DY_FLEET_PY
# is the interpreter (default the node's paddle venv; the coordinator needs only python3).
#
# The worker exits 0 when the queue is empty, 2 when the server has been gone half an hour,
# 3 when the server dies on two different pages in a row, 4 when a failure was nobody's we
# named (an import, a queue that stopped answering), 5 when too many pages failed in a row.
# The loop below restarts it after a minute whatever the code, so a refilled queue or a
# returned server is picked up without anyone typing, and a worker failing on every start is
# throttled to one attempt a minute — which the monitor shows as STALLED.

set -u
ROLE=${1:-all}
FLEET=~/docket-yard/tools/fleet
DATA=${DY_FLEET_DATA:-/data/docketyard}
OCR=$DATA/ocr
DB=$OCR/queue.sqlite
PY=${DY_FLEET_PY:-~/ocr-bench/.venv-paddle/bin/python}
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

if [ "$ROLE" = coordinator ] || [ "$ROLE" = all ]; then
    COLLECT="$PY $FLEET/pagequeue.py --db $DB collect --out $OCR"
    up fleet-queue "$PY $FLEET/queue_server.py --db $DB --blobs $DATA/blobs \
        --token-file $DATA/fleet.token --port 8131 >> $LOG/queue-server.log 2>&1"
    up fleet-monitor "$PY $FLEET/monitor.py --db $DB --port 8130 >> $LOG/monitor.log 2>&1"
    up dots-collect "while true; do $COLLECT >> $LOG/dots-collect.log 2>&1; sleep 600; done"
fi

if [ "$ROLE" = worker ] || [ "$ROLE" = all ]; then
    if [ "$ROLE" = worker ]; then
        NODE=$(cat "$DATA/fleet-node")
        QUEUE="--queue $NODE --token-file $DATA/fleet.token"
        [ -d "$DATA/blobs" ] && QUEUE="$QUEUE --blobs $DATA/blobs"
    else
        QUEUE="--db $DB --blobs $DATA/blobs"
    fi
    WORKER="$PY $FLEET/dots_worker.py $QUEUE --scratch $OCR/.render --stop-file $OCR/.stop"
    up dots-vllm "bash $FLEET/dots-serve.sh"
    up dots-worker "while true; do $WORKER >> $LOG/dots-worker.log 2>&1; \
        echo \"\$(date -Is) worker exited \$?\" >> $LOG/dots-worker.log; sleep 60; done"
fi
