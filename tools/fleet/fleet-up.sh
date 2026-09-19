#!/usr/bin/env bash
# Bring a fleet machine up: tmux sessions for its role, each started only if it is not
# already running (docs/compute-fleet.md § Running it).
#
#   bash ~/docket-yard/tools/fleet/fleet-up.sh coordinator   # the box that holds the queue
#   bash ~/docket-yard/tools/fleet/fleet-up.sh worker        # a GPU box reading for it
#   bash ~/docket-yard/tools/fleet/fleet-up.sh all           # both on one box (how it began)
#   DY_FLEET_HUNYUAN_PY=<venv>/bin/python \
#       bash ~/docket-yard/tools/fleet/fleet-up.sh tabular   # the tabular pass's worker, opt-in
#   bash ~/docket-yard/tools/fleet/fleet-up.sh reread        # the text-layer re-read, opt-in
#   tmux ls                                                  # the sessions
#   tmux attach -t dots-worker                               # watch one; detach with C-b d
#
#   coordinator:  fleet-queue    the lease calls and the blobs on :8131   (queue_server.py)
#                 fleet-monitor  the status page and the scrape on :8130  (monitor.py)
#                 dots-collect   reading documents every ten minutes      (pagequeue.py collect)
#                 tabular-collect  the same for the tabular pass; writes nothing until seeded
#                 reread-collect   the same for the re-read; writes nothing until seeded
#   worker:       dots-vllm      the server, restarted when it dies       (dots-serve.sh)
#                 dots-worker    the worker, restarted when it exits      (below)
#   tabular:      tabular-worker HunyuanOCR in-process, restarted when it exits (hunyuan_worker.py)
#   reread:       reread-worker  the SAME dots worker and the SAME dots server, claiming the
#                                `reread` queue instead (`--pass reread`); its own role because
#                                it shares the card with `dots-worker` and only one of the two
#                                should hold it. Its stop file is `<root>/ocr/.stop-reread`
#
# `tabular` is its own role, never part of `worker` or `all`: the model runs in the worker's
# own process on the same card the dots server holds at 90%, so the operator stops
# `dots-vllm` first on a shared card. It needs DY_FLEET_HUNYUAN_PY, a venv with transformers
# 5.x, torch with CUDA and pymupdf (not the paddle venv). Its stop file is `<root>/ocr/.stop-tabular`.
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
    # A BLOB MISS IS A FETCH ONLY IF THIS FILE EXISTS (ADR 0025 addendum 5-6, Accepted
    # 2026-09-19). `$DATA/store.env` holds DY_S3_BUCKET, AWS_ACCESS_KEY_ID,
    # AWS_SECRET_ACCESS_KEY and AWS_REGION for a READ-ONLY credential; it is in no
    # repository, the same way `fleet.token` is not. Without it the coordinator starts
    # and says so, and a document the mirror has lost is a 404 again - which is what
    # failed 728 pages on 2026-09-18. Sourced into the ENVIRONMENT, never passed in argv:
    # `ps` is readable by every user on the box.
    STORE_ENV="$DATA/store.env"
    if [ -f "$STORE_ENV" ]; then
        QUEUE_ENV="set -a; . $STORE_ENV; set +a;"
        echo "fleet-queue: blob refetch enabled from $STORE_ENV"
    else
        QUEUE_ENV=""
        echo "fleet-queue: no $STORE_ENV, so a blob the mirror lacks is a 404"
    fi
    up fleet-queue "$QUEUE_ENV $PY $FLEET/queue_server.py --db $DB --blobs $DATA/blobs \
        --token-file $DATA/fleet.token --port 8131 >> $LOG/queue-server.log 2>&1"
    up fleet-monitor "$PY $FLEET/monitor.py --db $DB --port 8130 >> $LOG/monitor.log 2>&1"
    up dots-collect "while true; do $COLLECT >> $LOG/dots-collect.log 2>&1; sleep 600; done"
    up tabular-collect "while true; do $COLLECT --pass tabular >> $LOG/tabular-collect.log 2>&1; \
        sleep 600; done"
    up reread-collect "while true; do $COLLECT --pass reread >> $LOG/reread-collect.log 2>&1; \
        sleep 600; done"
fi

if [ "$ROLE" = tabular ]; then
    HPY=${DY_FLEET_HUNYUAN_PY:?set DY_FLEET_HUNYUAN_PY to the HunyuanOCR venv python}
    if [ -f "$DATA/fleet-node" ]; then
        QUEUE="--queue $(cat "$DATA/fleet-node") --token-file $DATA/fleet.token"
        [ -d "$DATA/blobs" ] && QUEUE="$QUEUE --blobs $DATA/blobs"
    else
        QUEUE="--db $DB --blobs $DATA/blobs"
    fi
    TWORKER="$HPY $FLEET/hunyuan_worker.py $QUEUE --scratch $OCR/.render \
        --stop-file $OCR/.stop-tabular"
    up tabular-worker "while true; do $TWORKER >> $LOG/tabular-worker.log 2>&1; \
        echo \"\$(date -Is) worker exited \$?\" >> $LOG/tabular-worker.log; sleep 60; done"
fi

if [ "$ROLE" = worker ] || [ "$ROLE" = all ] || [ "$ROLE" = reread ]; then
    if [ "$ROLE" = all ]; then
        QUEUE="--db $DB --blobs $DATA/blobs"
    else
        NODE=$(cat "$DATA/fleet-node")
        QUEUE="--queue $NODE --token-file $DATA/fleet.token"
        [ -d "$DATA/blobs" ] && QUEUE="$QUEUE --blobs $DATA/blobs"
    fi
    up dots-vllm "bash $FLEET/dots-serve.sh"   # one server serves either pass: one key
fi

if [ "$ROLE" = worker ] || [ "$ROLE" = all ]; then
    WORKER="$PY $FLEET/dots_worker.py $QUEUE --scratch $OCR/.render --stop-file $OCR/.stop"
    up dots-worker "while true; do $WORKER >> $LOG/dots-worker.log 2>&1; \
        echo \"\$(date -Is) worker exited \$?\" >> $LOG/dots-worker.log; sleep 60; done"
fi

if [ "$ROLE" = reread ]; then
    # the same engine and the same key as `dots`, claiming the re-read's queue. Its own role
    # and its own stop file, because the two would otherwise share one card and one stop
    RWORKER="$PY $FLEET/dots_worker.py --pass reread $QUEUE --scratch $OCR/.render \
        --stop-file $OCR/.stop-reread"
    up reread-worker "while true; do $RWORKER >> $LOG/reread-worker.log 2>&1; \
        echo \"\$(date -Is) worker exited \$?\" >> $LOG/reread-worker.log; sleep 60; done"
fi
