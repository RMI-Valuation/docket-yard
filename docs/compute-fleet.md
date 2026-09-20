# The compute fleet — derivation on the operator's LAN

**Status: running since 2026-09-09.** `dots` is complete and loaded. `tabular` has read
17,275 of its 26,294 pages and is **stopped part-way by the operator's decision**, with
nothing leased and nothing from it loaded — so the record shows no reading from that pass
yet, and the pages it has not reached are not covered by it. `reread` is built and unrun.
Since 2026-09-18 a broker places readers on cards; an addendum to ADR 0025 is owed for that.

The decision this rests on is ADR 0025, Accepted 2026-09-10. This document is the mechanics:
what a pass is, how a page is leased, what the monitor shows, and what a new reader must do
to join. **It describes roles, not machines** — the fleet's inventory, addresses and
operational posture are the operator's and live outside this repository.

The mistake it prevents: **a derivation run that dies and is not noticed.** On 2026-09-06 the
`dots` OCR server died of CUDA out-of-memory on a 20 × 15 inch plan sheet, 28 hours into a run
projected at 132. The driver treated the refused connection like a bad page, walked the
remaining 32,849 pages against a closed port at network speed, wrote every one of 9,915
documents as `failed`, printed progress lines throughout, and exited 0. Nothing alerted,
because nothing was watching the fleet — production's alerting (ADR 0019) watches the record.
Three days passed before an ssh login found the GPU idle.

## The roles

**Named by role, never by machine — the repository is public.** Which box fills a role, what
card is in it, how it is reached and what it holds are the operator's, recorded outside this
repository. What belongs here is what each role owes the record, because that is what lets a
reader judge a reading.

| Role | What it owes |
| --- | --- |
| **The coordinator** | Holds the queue, the route roots, the collected readings, the collector and the monitor. It reads nothing itself, which is what makes every reader replaceable. Everything it holds can be produced again, but only by spending the machine time that produced it — about 43 hours of reading for the pages already read — so it is the one role that is backed up. All of it is 464 MB |
| **A reader** | Claims pages under a lease, declares a producer the queue can check, renders at the pass's own DPI and posts an answer or a named failure. Disposable by design: everything it holds is a lease, and a lease that expires returns the page |
| **An opportunistic reader** | A reader whose stop rule is someone else's claim on the machine — the operator sitting down at it, or the broker preempting it for another project. The lease is what makes a hard stop cost nothing |
| **The broker** | Since 2026-09-18 it places readers on cards and may stop them. **It never learns what a pass is:** the submit line pins the pass, and nothing on the broker side resolves a version. An addendum to ADR 0025 is owed for this and is the operator's to accept |

A role is not a machine. One box may hold two roles, and the same pass may be read by
several boxes at once — that is the point of the producer check below, not an exception to
it. What a reader must *not* be is the coordinator: a reader can be rebuilt from a spec in an
afternoon, and the coordinator holds the machine time the fleet has already spent.

**Production never joins the fleet.** The instance holds the store and the keys; the fleet
holds neither. Reading documents reach the store the way they always have — `rsync` of the
pass's root and `docketyard text load` on the instance, in the order `ocr_wave.py` fixes —
and the fleet's only output is files under `/data/docketyard/ocr/<root>/`.

## What a pass is

**A pass is a reading key.** `dots` means dots.mocr 1.5 at 200 DPI, the key ADR 0023 fixes
and migration 0024's producer declaration names. A worker claiming pages for `dots` declares
its producer — the key, its host, the engine and the engine's version as the server reports
them — and the queue refuses a worker whose key is not the pass's (`pagequeue.Queue.register`,
tested). This is the rule that lets machines differ: a model served by MLX on the Mac, or
Ollama on the Jetson, is **another pass under another key**, never a quiet substitute inside
this one. The pick rule (ADR 0023 addendum) compares readings by key; a key that meant two
engines would be a false number on a page.

The passes today, all in `tools/fleet/pagequeue.py § PASSES`:

| Pass | Key | Reads | Output root |
| --- | --- | --- | --- |
| `dots` | dots.mocr 1.5, 200 DPI | pages routed `degraded` | `ocr/dots` |
| `tabular` | hunyuan-ocr 1.5, 150 DPI — HunyuanOCR-1.5 in-process through transformers (`hunyuan_worker.py`); built 2026-09-15, **part-read and stopped** 2026-09-18 at 17,275 of 26,294 pages, nothing loaded | pages routed `tabular` (26,294) | `ocr/hunyuan-tabular` |
| `reread` | dots.mocr 1.5, 200 DPI — **dots' own key**; role `second`; built 2026-09-18, not yet run | flagged text-layer pages, from a page list, routed first | `ocr/dots-reread` |

Each pass names its own page builder (`PASSES[...]["page"]`): the worker posts the engine's
raw answer and `collect` turns it into the engine page and its text — `ocr_wave.dots_page`
for `dots`, `ocr_wave.hunyuan_page` for `tabular` (the answer kept whole; each `<table>`
flattened to `[table]` blocks by the benchmark's own `_markdown_tables`).

## The lease

One SQLite file, `/data/docketyard/ocr/queue.sqlite`, holds a row per page a pass owes.

```
pending  --claim-->  leased  --done-->  done
                       |  \--fail, the page's own-->  failed  (`page: ...`; final)
                       \--lease expires / server dies-->  pending (attempt spent)
                                              ... or failed, if that was the last attempt
```

- **Claim** is atomic (`BEGIN IMMEDIATE`): two workers never hold one page. A claim takes
  the next few pending pages in document order and leases them for 45 minutes; the worker
  extends the lease after every page.
- **A lease that expires returns the page** — every claim reaps first, so a dead worker's
  pages go back without an operator. Three attempts are allowed; the third expiry fails the
  page with `lease expired on attempt 3`.
- **An answer to an expired lease is dropped.** Another worker may hold the page.
- **A failure's reason says whose it is, and the default is not the page's.** Only a named
  cause is the page's own and final, prefixed `page:` — a cut answer (`finish_reason` other
  than `stop`), a sheet over the pass's bound, a page pymupdf opened but would not
  rasterise, a timeout with the server healthy. The queue refuses a final failure with any
  other prefix.
- **The server dying is not a page failing.** A refused connection, a reset, a body cut off,
  a 5xx or a timeout with the server unhealthy puts the page in flight back as `server: …`
  with its attempt spent (it may be the cause — the 12-megapixel sheet was), puts every other
  leased page back unspent, and makes the worker *wait* for the server rather than claim, so
  the read-age grows. A server that dies on two different pages in a row is the server's
  fault: the worker exits 3 and the restart loop throttles it.
- **A missing blob is three different things** (ADR 0025 addendum 5-6, Accepted 2026-09-19).
  Absent from the mirror AND from the store is the DOCUMENT's: `blob: ...`, attempt spent,
  not final, re-read at a later seed. A store the coordinator cannot reach — no credential,
  an expired one, a refusal, a reset — is the ENVIRONMENT's: every leased page goes back
  unspent and the worker exits 4, because every page would fail identically. Bytes that do
  not hash to the sha asked for are the STORE's: `BLOB CORRUPT IN THE STORE` on the
  coordinator, 502 to the worker, and the page is not final either. None of the three
  arrives as a traceback any more, which two of them used to.
- **A failure nobody named is nobody's we named.** An import that fails, a
  4xx: the worker releases every leased page unspent and exits 4 with the traceback. Twenty-
  five page-owned failures in a row with no page read is a cause nobody has named yet: exit
  5. A worker whose default branch were "the page failed" would reproduce 2026-09-06 for
  every such cause, only faster — no server round-trip to slow it.
- **A reader is told to stop in two ways, and they mean the same thing** (`tools/fleet/
  stopping.py`): the **stop file**, which an operator or a gate writes, and a **signal**, which
  is how a broker preempts. Either way the reader yields *before the next page*, releasing what
  is unspent with its attempt refunded, and exits 0 — a stop is nobody's fault and must cost the
  page nothing. **The stop file is a latch and the signal is not:** a person clears the file,
  while a signal sets a flag inside the process that dies with it, so the next placement reads
  normally. A preempt implemented as a stop file would hold the whole pass down until someone
  noticed. Every branch that can be interrupted mid-page yields too, including the ones that
  would otherwise record the interruption as the page's own fault — a server torn down under an
  in-flight request answers `finish_reason: abort`, which read as a cut page would fail it
  **finally** and count its document whole for ever. `JOBD_CHECKPOINT_GRACE_S` is the budget
  before the signal becomes a kill; it is logged at startup, because a page that outruns it
  never reaches the yield. A clean yield prints `jobd-checkpoint-complete`.
- **A brokered placement and the restart loop must not both manage one reader.** `fleet-up.sh`
  restarts a worker a minute after any exit, which would put it back on the card a minute after
  a broker took it away — overriding the placement silently. A reader is run by one or the
  other, never both.
- **Collect** writes a reading document once every page of a document is terminal, in the
  loader's shape, through the same `dots_page` the driver uses, under the same path. `ran_at`
  is the moment of collection, written once. The root's `_manifest.json` names every
  producer that read for it. A document with every page failed is written `failed` with its
  `pages_failed`, as before — but *a `failed` on disk is no longer a reason to skip*. At the
  next `seed` the queue decides: a collected document whose every failure is the page's own
  **and whose reading document is still on disk** is **whole**; one holding a failure that was
  not the page's is **re-read** — its file is set aside as `.superseded`, so is its second
  reading (measured against text that is no longer this key's), and every page of it is queued
  anew. **A document the queue calls whole with no reading document on disk is read again, not
  skipped**, and counted apart in the seed's report: that is a coordinator restored from a queue
  newer than its file tree, and counting it whole would silence it for ever, since nothing else
  queues it and nothing ever collects it. The loader takes a document whole
  under one `ran_at`, so a page cannot be added later. A file the queue does not know is the
  old driver's, which kept no reasons: whole only if it says `read` with no page failed.
- **A failed page carries its reason into the store** (migration 0031, ADR 0024 § Owed 2
  addendum 2026-09-15, Proposed). Collect writes `page_failures: [{page_no, reason, detail?}]`
  beside `pages_failed`, with the classifier that named them, mapping each `job.error` to a
  reason through `ocr_wave.failure_reason`: `page:` is page-owned (`cut-answer`, `oversize`,
  `render`, `timeout`, `operator-page`), and `server:`, `blob:`, a lease expiry, `operator:`
  and anything unnamed are not. A detail is kept only when it is its reason's closed shape
  (`ocr_wave.DETAIL_SHAPES`: `oversize: 8.4 MP at 200 DPI`, `finish_reason length`, ...), because
  it is PUBLISHED with `ocr_run`; an exception's text or an operator's words never are. A
  document holding a `page:` error with no known reason is skipped and left uncollected — every
  other document in the batch is still written, and a later run collects it once the classifier
  names the word. The loader writes a row per failed page in the run's own transaction, in
  `ocr_page_failure`. **Owed:** the 134 page failures
  collected before this shipped carry no list, and are loaded once, directly, as a sidecar
  (`docs/deferred.md` § From the schema critic on migration 0031).

The promises are tested in `tests/test_fleet.py`, through the real loader, in CI.

## The oversize guard

Measured 2026-09-09 over all 41,688 degraded pages: the median is a letter page at 3.74 MP
when rendered at 200 DPI; 840 pages exceed 4 MP (legal, 4.8 MP, which the run had read
without incident); **five exceed 5 MP**, four of them the plan sheets of the document that
killed the server. The bound is the pass's (`PASSES["dots"]["max_megapixels"]`, 6 MP),
declared in every worker's producer, so `oversize` means one thing on every node; the worker
fails such a page before it reaches the server. It does not render the page smaller: the
render is the reading's key (ADR 0023), and a quiet 100 DPI reading filed under `200` is the
kind of lie the key exists to prevent. Those five pages wait for a pass under another
profile, if one is ever worth running.

The server itself runs at `--gpu-memory-utilization 0.90` (was 0.95; the worker is serial,
so the 0.5 GB given back is headroom for the vision encoder rather than KV cache it never
used) with `expandable_segments` on, and under a loop that restarts it a minute after it
dies. Each is a bound, not a proof.

## The monitor, and what detection means

`tools/fleet/monitor.py` serves, on the node, LAN only:

| Path | What |
| --- | --- |
| `/` | The status page: each pass's counts, last read, last-hour rate and ETA; each worker's producer, pages and last sign of life; collected documents; failures by reason; a **STALLED** or **FAILING** banner |
| `/status.json` | The same, as the queue reports it |
| `/metrics` | Prometheus text exposition in ADR 0019's grammar: `docket_yard_fleet_jobs{pass,state}`, `docket_yard_fleet_last_read_known{pass}` paired with `docket_yard_fleet_last_read_age_seconds{pass}` (the age is absent until a page has been read — never a sentinel, the shape `docket_yard_freshness_*` chose), `docket_yard_fleet_pages_last_hour{pass,outcome}`, `docket_yard_fleet_stalled{pass}`, `docket_yard_fleet_failing{pass}`, `docket_yard_fleet_worker_last_seen_age_seconds{worker,pass,host}`, `docket_yard_fleet_worker_pages_done{…}` |
| `/health` | 200 while reading is under way or nothing is owed; 503 when STALLED or FAILING |

The queue is opened read-only; a path with no queue file is a 503, never an empty queue
reporting that nothing is owed.

**STALLED** is: pages owed, and no page *read* in 30 minutes. Read, not finished — a fleet
failing every page finishes pages briskly, and that was the 2026-09-06 shape. The run reads
a page every 11–13 s, so 30 minutes is a server that has not come back, a worker loop that
has stopped, or a box that is off. **FAILING** is the other half: pages owed and, in the last
hour, more failed than read, with at least ten failed so a tail of five oversize sheets does
not trip it.

**A local banner is not detection.** A dead box cannot report its own death (ADR 0012, 0019).
The fleet's detection is the same shape as production's: **Grafana Alloy on the node scrapes
`/metrics` and remote-writes to the same Grafana Cloud stack**, where three rules fire —
`docket_yard_fleet_stalled == 1` for ten minutes, `docket_yard_fleet_failing == 1` for ten
minutes, and *absence* of `docket_yard_fleet_last_read_known` for ten minutes (the box, the
monitor or Alloy is gone). The scrape block is production's `config.alloy` with the target
swapped (`tools/fleet/config.alloy`, reading the node's own `/proc`, `/sys` and `/` — mounted
into a container, or the paths themselves when it runs as a binary on the box — so it reports
the node and not itself); endpoint, username and token are the
operator's, in an env file on the node, and enter no repository. **The three rules exist in Grafana Cloud since 2026-09-10**, provisioned from
`infra/grafana/provision.py` beside production's; the alertmanager's route to mail was proved
with a temporary rule the same day.

## Running it

Four roles — `coordinator`, `worker`, `tabular`, `reread` — with tmux sessions for each,
started idempotently by `tools/fleet/fleet-up.sh <role>` (`DY_FLEET_DATA` is the data root;
`DY_FLEET_PY` the interpreter). `all` is the coordinator and `worker` on one machine:

| Role | Session | Runs | Log |
| --- | --- | --- | --- |

### Putting the store within the coordinator's reach (ADR 0025 addendum 5-6)

`<data>/store.env`, mode 600, in no repository, read by `fleet-up.sh` and sourced into the
environment before the queue server starts — never passed in argv, because `ps` is readable by
every user on the box:

```
DY_S3_BUCKET=docketyard-prod
AWS_REGION=us-east-2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

**Use `docketyard-blobs-reader`, not `docketyard-reader`.** The older key grants `GetObject` on
`docketyard-prod/*`, and that bucket holds `litestream/` as well as `blobs/` — so it can read a
2.3 GB replica of the whole production store. Measured 2026-09-19, which is why a narrower user
exists: `s3:GetObject` on `docketyard-prod/blobs/*` and `s3:ListBucket` on the bucket, nothing
else. **`ListBucket` is unconditioned deliberately**: S3 answers 404 rather than 403 for a
missing key only when the caller holds it, and a GetObject request carries no `s3:prefix` for a
condition to match — so scoping it by prefix would collapse the two answers the queue's failure
grammar depends on. The cost is that the key can see `litestream/` key NAMES; it cannot read one.

Prove it after placing it, against the running coordinator — all three, not just the happy one:

```
T=$(cat <data>/fleet.token)
curl -s -o /tmp/b -w '%{http_code} %{size_download}
' -H "Authorization: Bearer $T"     http://127.0.0.1:8131/blob/<a sha the mirror holds>     # 200, served from disk
curl -s -o /tmp/b -w '%{http_code} %{size_download}
' -H "Authorization: Bearer $T"     http://127.0.0.1:8131/blob/<a sha only the store holds> # 200, and the mirror is now filled
curl -s -o /tmp/b -w '%{http_code}
' -H "Authorization: Bearer $T"     http://127.0.0.1:8131/blob/$(printf '0%.0s' {1..64})    # 404 — NOT 503
```

The third is the one that matters: a 503 there means the credential lacks `ListBucket` and every
absent document is about to be blamed on the environment. Verified on rmi-nuc 2026-09-19.

| coordinator | `fleet-queue` | `queue_server.py` on port 8131: the lease calls and the blobs, refetching from the store on a mirror miss when `<data>/store.env` is present | `ocr/logs/queue-server.log` |
| coordinator | `fleet-monitor` | `monitor.py` on port 8130 | `ocr/logs/monitor.log` |
| coordinator | `dots-collect` | `pagequeue.py collect` every ten minutes | `ocr/logs/dots-collect.log` |
| worker | `dots-vllm` | `dots-serve.sh`: vLLM, restarted a minute after it dies | `ocr/logs/vllm.log` |
| worker | `dots-worker` | `dots_worker.py`, restarted a minute after it exits (0: queue empty; 2: server gone 30 min; 3: server dies on consecutive pages; 4: not the page's fault; 5: too many page failures in a row) | `ocr/logs/dots-worker.log` |
| coordinator | `tabular-collect` | `pagequeue.py collect --pass tabular` every ten minutes; writes nothing until the pass is seeded | `ocr/logs/tabular-collect.log` |
| tabular | `tabular-worker` | `hunyuan_worker.py` under `DY_FLEET_HUNYUAN_PY`, restarted a minute after it exits (0: queue empty, model not loaded; 3: out of GPU memory on two different pages in a row; 4: the model did not load, the card is short of free memory, the engine raised on a page, or not the page's fault; 5: too many page failures in a row). Its own role, never part of `worker` or `all` | `ocr/logs/tabular-worker.log` |

The coordinator needs no engine (`DY_FLEET_PY=python3`). A reader names the coordinator in
`<data>/fleet-node` and, if it holds a mirror of the blobs, reads them from its own disk
instead of over the transport. An opportunistic reader's gate is the Windows form of the
same role. Alloy runs on the coordinator with
`config.alloy` (the fleet's series and the box's vitals) and on each worker with
`config-host.alloy` (vitals only), the box's name in `FLEET_HOST` beside the credentials.

```
bash ~/docket-yard/tools/fleet/fleet-up.sh coordinator     # on the coordinator
bash ~/docket-yard/tools/fleet/fleet-up.sh worker          # on a reader
python3 tools/fleet/pagequeue.py --db Q status             # the queue, as JSON
python3 tools/fleet/pagequeue.py --db Q seed --pass dots --out /data/docketyard/ocr --dry-run
python3 tools/fleet/pagequeue.py --db Q fail --job N --error 'why'   # an operator's decision
```

A worker that exits 4 every minute is now most often stopped by the COORDINATOR rather than
by a page: a store it cannot reach is the environment's and exits 4 charging nothing, so read
the coordinator's own log first (`no $DATA/store.env`, a 403, a timeout) before hunting a bad
page. When it IS a page, the worker names it in its log — a blob that will not open — and
claims in document order, so that page is first every time. The queue is STALLED until the operator decides: `fail --job N --error 'why'` records
the decision as `operator: why` (not the page's own, so the document is re-read at a later
seed) and the worker moves on at its next start.

When the queue empties: `collect` has written every document; `second` and `graphic` follow
as `ocr_wave.py` documents; rsync and `text load` each root in that order on the instance.

### Running a reader through the broker

Since 2026-09-18 a broker places readers on cards (ADR 0025 addendum, proposals 1–4 Accepted
2026-09-19). A pass is submitted rather than started, and **the submit line pins the pass** —
nothing on the broker side resolves an engine, a version or a render.

```bash
# on the coordinator, when a pass owes pages and nothing is reading them
python3 tools/fleet/resubmit.py --db "$DB" --pass tabular \
    --jobd-url http://<broker>:8765 --jobd-token-file ~/.config/jobd/submit.token \
    --cwd /home/<user>/docket-yard -- \
    <hunyuan venv>/bin/python tools/fleet/hunyuan_worker.py \
        --queue http://<coordinator>:8131 --token-file "$DATA/fleet.token" \
        --scratch "$OCR/.render" --stop-file "$OCR/.stop-tabular"
```

**A reader is run by the broker OR by `fleet-up.sh`, never by both.** The restart loop starts a
worker a minute after any exit, so a reader the broker has just preempted would be back on the
card a minute later, silently overriding the placement. `resubmit.py` refuses when the queue
shows any worker of the pass seen recently — whoever started it — so the collision is reported
rather than silent, but the rule is the operator's to keep.

**Why a resubmitter exists at all:** a preempted job is terminal in jobd and is never requeued.
Nothing is lost, because the reader yields its pages back before exiting, but nothing picks
them up either. Resubmission is this project's, never the broker's, because choosing to read
again is choosing to spend the record's money. It asks two questions and needs both: **are
pages owed** (the coordinator's queue is the only thing that knows) and **is anything reading**
(the broker for jobs it started, and the queue for readers it did not). It keys off the
broker's state, never an exit code — exit 0 now means the queue drained, or the stop file, or a
preempt, and only the last prints `jobd-checkpoint-complete`.

The broker's token is **as powerful as ssh to every worker**; it is the operator's to place, it
lives in a file mode 600 on the coordinator, and it enters no repository.

### The tabular pass

ocr-plan.md decision 6, built on the operator's decision of 2026-09-15 (`docs/deferred.md`
§ that date). **Running it waits for a parity probe on the GPU** — the worker's reading of a
handful of benchmark pages against `ocr_run.py --engine hunyuan-ocr`'s — **and loading
`ocr/hunyuan-tabular` into production waits for the operator's go.** Neither is implied by
the pass existing.

The worker is `tools/fleet/hunyuan_worker.py`: `dots_worker.py`'s lease loop, stop file,
breaker and taxonomy, minus the server. HunyuanOCR-1.5 runs in its own process through
`ocr_run.run_hunyuan_ocr` — the benchmark's call, transformers, bfloat16, greedy, 4,096 new
tokens — because vLLM 0.28's HunYuanVL fails on start and the benchmark's numbers are the
transformers path's. The producer names `transformers` and its version, `tencent/HunyuanOCR`
and the snapshot revision it loaded (the config's commit hash, else the cache's `refs/main`;
a worker that cannot name it does not claim). What is the page's own, finally: `oversize`
over 6 MP at 150 DPI (29 of the 26,294 pages, measured 2026-09-15), a render that fails, and
`finish_reason length` (every new token spent and no EOS). **Out of GPU memory is not the
page's**: the likeliest cause is another process on the card, and a final failure would count
the document whole with no text. The worker refuses to load with under 4 GiB free
(`MIN_FREE_TO_LOAD`: the 2 GB model plus 2 GiB headroom, a bound the parity probe owes a
measurement for) and to claim with under 2 GiB usable (`MIN_HEADROOM`), exiting 4 with nothing
claimed. An OOM that survives one retry with the cache emptied puts the page back as
`gpu: oom`, attempt spent, and claims again; OOM on two different pages in a row exits 3. The
engine raising anything else on a page puts that page back as `engine: <Exception>`, attempt
spent — it is first in claim order, so a refund would loop it for ever — and exits 4. Neither
is `page:`, so after three attempts the document is re-read at a later seed, never whole.
**An empty answer is not a blank page**: a tabular page has a table on it, so `''` is the model
failing (a template or processor drift, an immediate EOS). It goes back as
`engine: empty answer`, attempt spent, never posted as done, and consecutive ones trip the
breaker (exit 5). `--model` must be `tencent/HunyuanOCR`, the model the key names; anything
else exits 4 before claiming.
**The card must be the worker's**: with a vLLM server holding 90% of the card, the floor
refuses every start. So:

```bash
tmux kill-session -t dots-vllm; tmux kill-session -t dots-worker          # on a shared card
python3 tools/fleet/pagequeue.py --db Q seed --pass tabular --out /data/docketyard/ocr --dry-run
python3 tools/fleet/pagequeue.py --db Q seed --pass tabular --out /data/docketyard/ocr
DY_FLEET_HUNYUAN_PY=<venv>/bin/python bash ~/docket-yard/tools/fleet/fleet-up.sh tabular
touch /data/docketyard/ocr/.stop-tabular                                   # stop it
python3 tools/fleet/pagequeue.py --db Q collect --pass tabular --out /data/docketyard/ocr
```

**Seed only when a worker is about to read.** The monitor's alarms are per pass: a seeded
pass that owes pages and has never read one is STALLED from the first scrape, which is
correct and will page the operator. `tabular-collect` on the coordinator writes
`ocr/hunyuan-tabular/<xx>/<sha>.json` as documents finish; nothing rsyncs or loads it.

The workstation's gate (`workstation-gate.ps1`) is still the `dots` pass's: its container,
worker script and names are dots-specific, and `-Pass` only changes what it asks `/pending`.

### The text-layer re-read

`docs/research/text-quality/` measured ~110,500 faulty pages among the 931,392 the site shows
as the publisher's own text layer, and the operator's order is prose first. Two steps, because
**the pages must be routed before they can be read**:

```bash
# 1. route them — layout only, no text, into the re-read's OWN route root
python3 tools/rmi-ai-machine/ocr_wave.py route-list --from queue.csv.gz --column prose \
    --blobs /data/docketyard/blobs --out /data/docketyard/ocr
# 2. seed and read
python3 tools/fleet/pagequeue.py --db Q seed --pass reread --out /data/docketyard/ocr \
    --from queue.csv.gz --column prose --dry-run     # 6,170 pages in 1,501 documents
python3 tools/fleet/dots_worker.py --pass reread --queue http://<node>:8131 ...
python3 tools/fleet/pagequeue.py --db Q collect --pass reread --out /data/docketyard/ocr
```

**Why routing is not optional.** `text/load.py` refuses an `ocr` reading whose page names no
routed class — *"an OCR reading names the class it was routed as (ADR 0021 D4)"* — and
`document_text`'s own `CHECK (reading_channel <> 'ocr' OR route_class IS NOT NULL)` refuses the
row behind it. The first design gave these pages no route, on the reasoning that the router had
never seen them and calling them `unrouted` would stamp ROUTER's method on a page that method
never touched. True, and beside the point: the readings would have been written and thrown away.
The class is also what makes them scorable later (`class_measurement` is keyed on class) and
what lets the operator promote one class and not another. `seed_from_list` refuses a pass with
no route root (`Unloadable`) and skips a document or page that has not been routed, reporting
both, so a page waits rather than being read for nothing.

**`route-list` runs the LAYOUT model only.** `classify` reads regions, not text, so the
recognition half of `run-paddle` would be spent for nothing — and worse than nothing, since
`run-paddle` writes a PP-OCR *primary* for the clean pages and every page here already has a
live primary from the publisher's text layer. It is resumable, a document at a time, and a page
that will not render is written `unrouted` with its error, which is a real class and loads.

**The routes live apart, under `ocr/route-reread`.** `seed_pass` globs every route document
under `route/` for every routed pass, so writing these text-layer documents there would have
quietly enlarged the `dots` pass with any page of them that classified `degraded`.

**The pass has no class of its own**, because the list chooses the pages and they are of every
class; each page carries its own class from its route document, quoting that document's method
version rather than the module's constant, so a page routed by an earlier router says so.
Whether a pass is seeded from the route root or a list is `seeded_from` on its spec, separate
from whether its pages are routed; each seed refuses the other's pass. **Only the listed pages
are queued** — but what this pass owes a document is not fixed the way a route document fixes
it, because the score's lexicon grows with the record and the operator can move the cut, so a
wider list **tops up** a document the queue already calls whole: its file is set aside and it is
read again whole, since the loader takes a reading under one `ran_at`.

**The key is `dots`' own**, unchanged — same engine, same version, same render, so it is the
same reading, and one worker serves both passes (`dots_worker.py --pass`, which offers every
pass whose key is dots.mocr's and no other). `document_text_live` does **not** carry the role,
so it does not keep the two passes apart; it makes it impossible for one page to hold both, and
the loader then refuses the whole document. What keeps them apart is that no document is both
image-only and text-layer — unasserted in the store, but now partly guarded, since the two
passes read different route roots.

**The role is `second`, and the promotion question is deferred** (the operator, 2026-09-18).
`document_text_one_primary` is UNIQUE on (document, page) for live primaries and every one of
these pages already holds a text-layer primary, so a `primary` here could not load without
superseding the publisher's own text layer — a publishing decision under ADR 0023's pick rule,
not a reading one. What that costs while it stands: the better text is not displayed, not in
`page_fts` and not walked by the citator, so a garbled page stays garbled until he chooses.

**Two things are owed before a reading from this pass is loaded**, both in `docs/deferred.md`
§ 2026-09-18:

- **The agreement distance, and what `band()` says without it.** The wave's `second` readings
  carry a distance because `ocr_wave.py second` measures them against the dots primary on disk;
  here the reading to measure against is the text layer in the store. `collect` writes no
  agreement, and `store/pages.py:band` LEFT JOINs the live `second` row whatever its channel —
  so loading these would replace *"Read once; no second reading to compare it with, so no
  band."* with *"A second reading exists (dots.mocr 1.5); its distance from this one has not
  been computed, so no band."* on every re-read page, on `/text`, in search hits and through
  MCP. That is published text moving on a load rather than a dated rule.
- **Computing the distance is itself a publishing decision**, not a computation: it would print
  a band on those pages from a cross-channel instrument that has been measured at nothing.

**`second` also spends the page's one `second` slot** (`document_text_one_second` is unique per
live page), which is where a cheap second reading to catch invention would have gone — and
dots.mocr is itself a VL model, so a re-read that invents is indistinguishable from one that
repairs. The critic's suggestion, worth weighing before the other ~25,600 pages: run the 6,170
prose pages, take the promotion decision with them in hand, and leave the rest.

## Joining a node

A second node needs three things and no redesign:

1. **A transport — built 2026-09-09.** `queue_server.py` on the node puts the six calls a
   worker makes (register, claim, extend, release, done, fail) and the documents' bytes
   (`/blob/<sha>`) on port 8131, behind a bearer token that is one line in a file on the
   node and on each joining machine and in no repository. `pagequeue.RemoteQueue` is the
   client, with the same six methods, so `dots_worker.py --queue http://<node>:8131
   --token-file …` holds either and does not know which. A remote worker fetches a
   document once per document (a claim is one document's pages in order); measured from a
   second machine, 4.3 MB in 0.08 s. SQLite over a network share is not a transport.
2. **A producer it can declare truthfully.** The same engine and version, or a new pass.
3. **Its own stop rule.** A reader must be able to stop on someone else's terms and cost
   nothing — the lease is what makes a hard stop free. An opportunistic reader's rule is
   *someone else wants this machine*: idle time watched, the engine started after a set idle
   period, the stop file written at the first input, pages released within seconds, with
   switch files to override the rule either way. **Since 2026-09-11 such a reader also asks
   whether there is work before it starts anything** (`GET /pending`), and stops its engine
   when the queue reports empty instead of relaunching readers against a dry queue — without
   that it relaunches a worker a minute for as long as the queue stays empty. Which machine
   uses which rule, and how each is implemented, is recorded outside this repository.

   **Two machines read a page to the same text — measured 2026-09-09.** Twelve pages re-read
   on a second machine came back eleven identical and one a character apart. The raw answers
   differ more often, because bounding-box coordinates wobble between cards, and the key
   tolerates that. This is the evidence behind one pass being read by several machines at
   once: **the key names the engine and the render, not the card.** What a given machine needs
   in order to serve that engine — and what it cost to find out — is the operator's, and is
   recorded outside this repository.

   **A reader needs no S3 key.** The token streams from the coordinator and the coordinator
   serves the documents' bytes, so joining adds no credential to the machine that reads.

**NVIDIA's Personal AI Router (PAIR)** was evaluated 2026-09-09 for this role and is not it:
it routes single requests to Ollama or LM Studio nodes by GPU utilisation, without regard to
memory or model fit (its README says so), with no batch, no lease, and no way to say which
node answered — the fact the reading key must record. It fits a later *online* layer, if the
project ever calls a model from a page; batch derivation is the queue.

## What is owed

- A pass for each runtime the fleet gains, when a workload is chosen — a different runtime is
  a different key, so it is a new pass, never a substitution inside an existing one; more than
  one reader per card, measured for the vision encoder's activation peak first; `second` and
  `graphic` on the coordinator
- `second` and `graphic` run through the queue rather than `ocr_wave.py`, so that every pass
  has the same lease and the same monitor (they read a cache and cannot die the same way, so
  this is tidiness, not safety)
- **A backup of the coordinator, which holds the machine time the fleet has spent** — each
  pass's collected root first, since re-reading is the dear part, then the route roots, then the
  queue. Not because any of it is irreplaceable, but because all of it together is 464 MB and
  reproducing it means spending those GPU hours again. First taken
  2026-09-19: snapshot through SQLite's backup API, `PRAGMA integrity_check` and table counts
  on the copy, and a hash matching snapshot to copy, which proves the **transfer** and not
  fidelity to a database that moved while it was read. Making it routine is owed, and so is a
  target that is not another fleet box. The restore order — **the files before the queue** — is
  now a matter of cost, not of silence: since 2026-09-19 a queue newer than its file tree makes
  the seed read those documents again rather than skip them, which is correct and can be a whole
  wave of GPU time. The cheaper verdict, weighed and not taken, is in `docs/deferred.md`
- The fleet's operational posture — how each role is supervised, what survives a reboot, what
  the monitor cannot yet distinguish, and which gaps are open — is **deliberately not in this
  public repository**. It is the operator's and is recorded with the fleet's inventory. What
  belongs here is only what a reader needs to judge a reading
