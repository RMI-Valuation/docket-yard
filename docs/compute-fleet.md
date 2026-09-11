# The compute fleet — derivation on the operator's LAN

**Status: running since 2026-09-09 — the queue, monitor and one worker on RMI-AI-MACHINE,
six workers on the operator's workstation while it is idle, Alloy writing from the node; the
Grafana rules, the Mac and the Jetson are owed.** The decision this rests on is ADR 0025,
Accepted 2026-09-10. This document is the mechanics: what the machines are, what a pass is,
how a page is leased, what the monitor shows, and what a second node must do to join.

The mistake it prevents: **a derivation run that dies and is not noticed.** On 2026-09-06 the
`dots` OCR server died of CUDA out-of-memory on a 20 × 15 inch plan sheet, 28 hours into a run
projected at 132. The driver treated the refused connection like a bad page, walked the
remaining 32,849 pages against a closed port at network speed, wrote every one of 9,915
documents as `failed`, printed progress lines throughout, and exited 0. Nothing alerted,
because nothing was watching the fleet — production's alerting (ADR 0019) watches the record.
Three days passed before an ssh login found the GPU idle.

## The machines

Named, never addressed — the repository is public. Addresses live outside it.

| Machine | GPU memory | OS | Role |
| --- | --- | --- | --- |
| RMI-AI-MACHINE | RTX 4070, 12 GB | Linux | A worker. Always on. Paddle, dots.mocr through vLLM. Held the queue and the monitor until 2026-09-10 |
| rmi-nuc, an Intel NUC | none | Ubuntu Server | **The coordinator** since 2026-09-10: the queue, the monitor, the collector, the blob mirror, Alloy, the token. No GPU; it reads nothing. What it gives is that the GPU boxes are stateless workers a reboot does not cost |
| The operator's workstation | RTX 5080, 16 GB | Windows 11 | Opportunistic: a worker that runs only while the operator is away from it, under `workstation-gate.ps1`; vLLM in a container |
| rmi-mac, a Mac mini | M4 Pro, 24 GB unified | macOS | Ready since 2026-09-10 as an Ollama host on Metal (`mac-up.sh`: Alloy and Ollama as user launch agents, no administrator needed), nothing assigned: the largest GPU-addressable memory on the LAN; cannot run vLLM, so any engine there is another pass |
| rmi-jetson-orin, a Jetson Orin Nano | 8 GB shared | JetPack 7.2.1 | A container host since 2026-09-10 (CUDA 13.2 under the NVIDIA runtime): small always-on services (layout, classification, embeddings) as a pass of its own; not a vision-language model. **Headless since 2026-09-11** (the operator's decision): its desktop was measured at about 0.9 GB across 68 processes, so `multi-user.target` and a 16 GB swap file took it from ~0.4 GB free to 6.7 GB available — enough to hold an 8B model, which had failed to load beside the desktop |

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
- **A failure nobody named is nobody's we named.** A missing blob, an import that fails, a
  4xx: the worker releases every leased page unspent and exits 4 with the traceback. Twenty-
  five page-owned failures in a row with no page read is a cause nobody has named yet: exit
  5. A worker whose default branch were "the page failed" would reproduce 2026-09-06 for
  every such cause, only faster — no server round-trip to slow it.
- **Collect** writes a reading document once every page of a document is terminal, in the
  loader's shape, through the same `dots_page` the driver uses, under the same path. `ran_at`
  is the moment of collection, written once. The root's `_manifest.json` names every
  producer that read for it. A document with every page failed is written `failed` with its
  `pages_failed`, as before — but *a `failed` on disk is no longer a reason to skip*. At the
  next `seed` the queue decides: a collected document whose every failure is the page's own
  is **whole**; one holding a failure that was not the page's is **re-read** — its file is
  set aside as `.superseded`, so is its second reading (measured against text that is no
  longer this key's), and every page of it is queued anew. The loader takes a document whole
  under one `ran_at`, so a page cannot be added later. A file the queue does not know is the
  old driver's, which kept no reasons: whole only if it says `read` with no page failed.

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
swapped (`tools/fleet/config.alloy`, run as a container with the node's `/proc`, `/sys` and
`/` mounted so it reports the node and not itself); endpoint, username and token are the
operator's, in an env file on the node, and enter no repository. **The three rules exist in Grafana Cloud since 2026-09-10**, provisioned from
`infra/grafana/provision.py` beside production's; the alertmanager's route to mail was proved
with a temporary rule the same day.

## Running it

Two roles, tmux sessions for each, started idempotently by `tools/fleet/fleet-up.sh <role>`
(`DY_FLEET_DATA` is the data root; `DY_FLEET_PY` the interpreter):

| Role | Session | Runs | Log |
| --- | --- | --- | --- |
| coordinator | `fleet-queue` | `queue_server.py` on port 8131: the lease calls and the blobs | `ocr/logs/queue-server.log` |
| coordinator | `fleet-monitor` | `monitor.py` on port 8130 | `ocr/logs/monitor.log` |
| coordinator | `dots-collect` | `pagequeue.py collect` every ten minutes | `ocr/logs/dots-collect.log` |
| worker | `dots-vllm` | `dots-serve.sh`: vLLM, restarted a minute after it dies | `ocr/logs/vllm.log` |
| worker | `dots-worker` | `dots_worker.py`, restarted a minute after it exits (0: queue empty; 2: server gone 30 min; 3: server dies on consecutive pages; 4: not the page's fault; 5: too many page failures in a row) | `ocr/logs/dots-worker.log` |

The coordinator is rmi-nuc (data under the operator's home; `DY_FLEET_PY=python3`, since it
needs no engine). A worker names the coordinator in `<data>/fleet-node` and, if it holds a
mirror of the blobs (RMI-AI-MACHINE does), reads them from its own disk. The workstation's
gate is the Windows form of the worker role. Alloy runs on the coordinator with
`config.alloy` (the fleet's series and the box's vitals) and on each worker with
`config-host.alloy` (vitals only), the box's name in `FLEET_HOST` beside the credentials.

```
bash ~/docket-yard/tools/fleet/fleet-up.sh coordinator     # on rmi-nuc
bash ~/docket-yard/tools/fleet/fleet-up.sh worker          # on a GPU box
python3 tools/fleet/pagequeue.py --db Q status             # the queue, as JSON
python3 tools/fleet/pagequeue.py --db Q seed --pass dots --out /data/docketyard/ocr --dry-run
python3 tools/fleet/pagequeue.py --db Q fail --job N --error 'why'   # an operator's decision
```

A worker that exits 4 every minute is stopped by one page it names in its log — a blob that
is missing or will not open — and claims in document order, so that page is first every
time. The queue is STALLED until the operator decides: `fail --job N --error 'why'` records
the decision as `operator: why` (not the page's own, so the document is re-read at a later
seed) and the worker moves on at its next start.

When the queue empties: `collect` has written every document; `second` and `graphic` follow
as `ocr_wave.py` documents; rsync and `text load` each root in that order on the instance.

## Joining a node

A second node needs three things and no redesign:

1. **A transport — built 2026-09-09.** `queue_server.py` on the node puts the six calls a
   worker makes (register, claim, extend, release, done, fail) and the documents' bytes
   (`/blob/<sha>`) on port 8131, behind a bearer token that is one line in a file on the
   node and on each joining machine and in no repository. `pagequeue.RemoteQueue` is the
   client, with the same six methods, so `dots_worker.py --queue http://<node>:8131
   --token-file …` holds either and does not know which. A remote worker fetches a
   document once per document (a claim is one document's pages in order); measured from the
   workstation, 4.3 MB in 0.08 s. SQLite over a network share is not a transport.
2. **A producer it can declare truthfully.** The same engine and version, or a new pass.
3. **Its own stop rule.** The workstation's is *the operator is using it*, and it is built:
   `workstation-gate.ps1` reads the time since the last keyboard or mouse input every 30 s,
   and after ten idle minutes starts the vLLM container (the node's image and version, the
   node's flags, the model on a named volume) and a worker against the node's queue; at the
   first input it writes the worker's stop file, stops the container, and the worker is gone
   within seconds with its pages released. Two switch files override the idle rule either
   way. The lease makes a hard stop cost nothing. The Mac's and the Jetson's rules are
   whatever they are for. **Since 2026-09-11 it starts only when the node has work**: it asks
   `GET /pending` first and holds otherwise, re-asking every five minutes, and when every
   worker exits "queue empty" it stops the container rather than relaunching them. With the
   `dots` queue dry from 05:51 that morning it had kept the model resident and relaunched six
   workers a minute — 222 launches in 37 minutes on a machine the operator came back to.

   **Measured 2026-09-09, the workstation's first hour.** vLLM 0.28.0 in a container under
   WSL2 with `VLLM_USE_V2_MODEL_RUNNER=0` — the V2 runner needs unified virtual addressing,
   which WSL2 lacks — reads the node's pages to the same text: twelve pages re-read, eleven
   identical, one a character apart; the raw answers differ more often because bounding-box
   coordinates wobble between cards, which the key tolerates. One request at a time it is
   no faster than the 4070 (11.2 s a page; both cards generate ~125 tokens/s, so a 3B model
   at batch one is bound by per-step overhead, not bandwidth). The card's advantage is room:
   its KV cache holds ten 16k requests against the node's two or three, and six workers at
   once read a page every 3.3 s effective. The gate runs six. The node could run two, and
   has not been measured for the vision encoder's activation peak at two — the OOM lesson.

**NVIDIA's Personal AI Router (PAIR)** was evaluated 2026-09-09 for this role and is not it:
it routes single requests to Ollama or LM Studio nodes by GPU utilisation, without regard to
memory or model fit (its README says so), with no batch, no lease, and no way to say which
node answered — the fact the reading key must record. It fits a later *online* layer, if the
project ever calls a model from a page; batch derivation is the queue.

## What is owed

- A pass for the Mac and one for the Jetson, when a workload is chosen; two workers on the
  node, measured for the activation peak first; `second` and `graphic` on the coordinator
- `second` and `graphic` run through the queue rather than `ocr_wave.py`, so that every pass
  has the same lease and the same monitor (they read a cache and cannot die the same way, so
  this is tidiness, not safety)
- tmux is where the operator looks; `systemd --user` units would survive a reboot, which tmux
  does not. Owed when a reboot happens before the queue empties
