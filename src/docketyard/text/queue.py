"""Which documents the instance owes a text-layer reading, and in what order.

ADR 0024 D1, D3 and D4 in SQL, and nothing else: this module decides *what to hand over*. It
opens no PDF, invokes no container and writes no row — the dispatcher does those, and keeping
the queue separable is what lets its size be MEASURED against production before anything is
handed to a parser (ADR 0024 § Owed 4, which asks for exactly that and warns that the forward
record count is a different and smaller number).

THE FOUR TERMS, each with the failure it exists to prevent:

D1, SCOPE. A document is the instance's if any capture that ever observed it ran in `forward`
mode and positively asserted its filter, joined through `document_source.capture_id`, whose
rows accumulate and are never repointed. Not `observed_in_event`, which is current state and
moves. Not a record filter, which would leave the erratum re-check ownerless: that re-check
walks every held URL, so a replaced file mints a NEW document under a forward capture that no
record filter reaches and no finished wave claims. The filter term excludes nothing on this
join today and stands against a future widening — the endpoint's first trap, applied where it
always is.

D4, READ. A document is owed extraction when it has no `ocr_run` row at the text-layer
reading key whose outcome is `read`, AT ANY METHOD VERSION. The outcome is part of the test
rather than the row's existence: `run_outcome_vocab` holds `failed`, `skipped` and
`not-paginable` beside `read`, so under "no row at that key" a single failure would silence
this queue for that document for ever, at every version, and the release that fixes those
bytes would change nothing. And the version is absent on purpose (D6): under "no run at the
PINNED version" a point release would re-read 74,295 documents and rewrite about 1.1M rows.

D4, ATTEMPTS. Fewer than `EXTRACT_ATTEMPTS` dispatches AT THE PIN NOW IN FORCE, and no
dispatch at all inside `EXTRACT_RETRY_HOURS`. The count is per pin so a version bump is the
reset — otherwise a document that burned its attempts on one `pymupdf` release is out for
ever and the fix changes nothing. The interval is per DOCUMENT, not per pin, or a pin that
flaps (two pollers, a rollback) re-dispatches with no interval at all. The counter cannot be
`ocr_run`, which exists only because the loader read a spool file: a container that is down,
OOM-killed or stuck records nothing, so no attempt would ever count and the same documents
would be selected every pass while every newer one went unread, silently.

D3, THE BOUND. `EXTRACT_LIMIT` documents ordered by `document.first_seen_at` DESCENDING, an
`EXTRACT_MAX_BYTES` above which a document is not dispatched, and a media type that is a
PDF's. **The size and media-type limits are terms of the QUEUE, not only of the loader**,
because D2 hands the container an explicit list and this is therefore the only filter that
exists: without them the queue dispatches the 1.07 GB application that OOM-killed the wave
twice, and every `.xlsx`, `.zip`, `.jpg` and `.docx` the record holds. The container dies or
raises, the attempt burns, and the document is exhausted — never read and never refused with
a reason, which is D3 and D5 both defeated by the queue.

Newest first is a promise: a decision served this morning is read this pass, and the archive
documents D1 admits drain from the recent end backwards. A look-back window was refused
outright — it is the one shape that can strand a document for ever when a pass dies.
"""

from sqlite3 import Connection

# ADR 0024 D3. `EXTRACT_MAX_BYTES` matches `observations.RECHECK_MAX_BYTES` deliberately: the
# same 64 MB that bounds what the watch re-fetches bounds what a parser is handed, so one
# number governs the two places a large file can hurt this box.
EXTRACT_MAX_BYTES = 64 << 20
EXTRACT_ATTEMPTS = 3
EXTRACT_RETRY_HOURS = 6
# SIZED AGAINST THE QUEUE MEASURED WITH D1'S OWN JOIN (§ Owed 4), which is the point of that
# owed item: the forward RECORD count is a different and much larger number. Measured on
# production 2026-09-10 with this module's own SQL, against 104,230 documents in the store:
#
#     375  in D1's forward scope at all      0  media_type NULL
#     218  eligible — fetched, never read    4  media_type other than pdf
#     124  fetched in the last seven days    4  oversize or no size recorded
#
# So the standing backlog is 218 and material arrives at about 18 a day — roughly 0.4 per
# 30-minute pass. 25 clears the backlog in nine passes and is sixty times the steady arrival
# rate, so the limit governs the drain and never the promise: newest-first is what makes "a
# decision served this morning is read this pass" true, at any limit above zero.
EXTRACT_LIMIT = 25
# The idiom `RECHECK_BUDGET_SECONDS` already uses (ADR 0024 D3): after this the stage stops
# STARTING work, so a slow document cannot hold the next forward pass. Lower than the
# re-check's 300 because this runs last and the pass is 30 minutes long.
EXTRACT_BUDGET_SECONDS = 180

# The reading key this queue asks about. `render_profile` is the text layer's own: a file with
# a text layer is read as it stands, never rendered.
CHANNEL = "text-layer"
RENDER = "native"
# What `document.media_type` must be — the column is nullable and `size_bytes` is not, so
# this is the one of the two that needs a term for absence. NULL is NOT admitted, and the
# exclusion is COUNTED rather than silent (§ Owed 6): a NULL media type means nothing sniffed
# the bytes, and handing those to a parser is what the media term exists to stop.
MEDIA = "pdf"

# D1 and D4's read test, shared by the count and the walk so a measured queue and a dispatched
# one can never be two different populations.
_ELIGIBLE = """
  FROM document d
 WHERE d.media_type = :media
   AND d.size_bytes <= :max_bytes
   AND EXISTS (SELECT 1 FROM document_source ds
                JOIN capture c ON c.capture_id = ds.capture_id
               WHERE ds.document_sha256 = d.document_sha256
                 AND c.ingest_mode = 'forward' AND c.filter_asserted = 1)
   AND NOT EXISTS (SELECT 1 FROM ocr_run r
                    WHERE r.document_sha256 = d.document_sha256
                      AND r.reading_channel = :channel AND r.render_profile = :render
                      AND r.outcome = 'read')
"""
# The attempt terms, which need the pin and the clock and so are separate: `census` reports
# the population without them, and the walk applies them.
_UNSPENT = """
   AND (SELECT COUNT(*) FROM extraction_dispatch x
         WHERE x.document_sha256 = d.document_sha256
           AND x.pinned_method = :method AND x.pinned_method_version = :version
       ) < :attempts
   AND NOT EXISTS (SELECT 1 FROM extraction_dispatch x
                    WHERE x.document_sha256 = d.document_sha256
                      AND x.dispatched_at > :since)
"""


def _terms(method: str, version: str, since: str, *, attempts: int) -> dict:
    return {
        "media": MEDIA,
        "max_bytes": EXTRACT_MAX_BYTES,
        "channel": CHANNEL,
        "render": RENDER,
        "method": method,
        "version": version,
        "since": since,
        "attempts": attempts,
    }


def due(
    con: Connection,
    *,
    method: str,
    version: str,
    since: str,
    limit: int = EXTRACT_LIMIT,
    attempts: int = EXTRACT_ATTEMPTS,
) -> list[str]:
    """The next `limit` documents to hand over, newest bytes first.

    `since` is the retry cutoff as an ISO timestamp — a document dispatched after it is not
    asked for again this pass, whatever the pass rate. The caller computes it from the clock
    it is committing against, so a test can drive the interval without waiting six hours.
    """
    return [
        row[0]
        for row in con.execute(
            "SELECT d.document_sha256"
            + _ELIGIBLE
            + _UNSPENT
            + " ORDER BY d.first_seen_at DESC, d.document_sha256 LIMIT :limit",
            _terms(method, version, since, attempts=attempts) | {"limit": limit},
        )
    ]


def census(con: Connection, *, method: str, version: str, since: str) -> dict[str, int]:
    """What the queue holds, and what it is excluding — the numbers § Owed 4 asks for and
    § Owed 6 asks to be published rather than left silent.

    `eligible` is D1's scope less the read test: everything this stage could ever owe.
    `due` is what a pass would hand over now. The rest are the exclusions, each counted
    apart, because "handed over and nothing came back" and "never eligible" are the two
    things the published table exists to separate, and a third — never attempted because the
    queue refused it — is representable nowhere else.
    """
    terms = _terms(method, version, since, attempts=EXTRACT_ATTEMPTS)
    one = con.execute
    out = {
        "eligible": one("SELECT COUNT(*)" + _ELIGIBLE, terms).fetchone()[0],
        "due": one("SELECT COUNT(*)" + _ELIGIBLE + _UNSPENT, terms).fetchone()[0],
    }
    # the exclusions, each measured on the same forward scope so they add up against a
    # denominator a reader can see
    forward = (
        " FROM document d"
        " WHERE EXISTS (SELECT 1 FROM document_source ds"
        "                JOIN capture c ON c.capture_id = ds.capture_id"
        "               WHERE ds.document_sha256 = d.document_sha256"
        "                 AND c.ingest_mode = 'forward' AND c.filter_asserted = 1)"
    )
    out["forward"] = one("SELECT COUNT(*)" + forward, terms).fetchone()[0]
    out["media_null"] = one(
        "SELECT COUNT(*)" + forward + " AND d.media_type IS NULL", terms
    ).fetchone()[0]
    out["media_other"] = one(
        "SELECT COUNT(*)" + forward + " AND d.media_type IS NOT NULL AND d.media_type <> :media",
        terms,
    ).fetchone()[0]
    # `document.size_bytes` is NOT NULL, so there is no third case here and none is guarded
    # for: a document with no recorded size cannot exist.
    out["oversize"] = one(
        "SELECT COUNT(*)" + forward + " AND d.media_type = :media AND d.size_bytes > :max_bytes",
        terms,
    ).fetchone()[0]
    out["already_read"] = (
        out["forward"] - out["eligible"] - out["media_null"] - out["media_other"] - out["oversize"]
    )
    out["exhausted_or_resting"] = out["eligible"] - out["due"]
    return out
