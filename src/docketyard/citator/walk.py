"""The finder over the record's own text: `document_text` in, findings documents out.

THIS IS THE HALF THE CLI SAID WAS MISSING, and the reason it was missing stopped being true
on 2026-09-04. `cli._citator`'s docstring said "there is no `find` verb, and that is the
missing half rather than an omission: text extraction runs on the enrichment box and comes
back over the internal API" — which was so while the store held no text. Migration A loaded
1,104,935 pages, of which 161,801 non-empty pages are a decision's, covering 19,229 of the
record's 19,839 decisions. The text the finder wants is now IN the store, so the walk is a
store read and not an API round trip.

It writes, and asserts, nothing. Output is findings documents in the shape `citator load`
consumes, keyed on `document_sha256` because ADR 0018 D2 anchors an edge on the bytes that
carry it and not on a record row — **one per (document, machine channel)**, which is the
grain `load` stamps and the CLI refuses to mix. Whether to load them is a separate verb and
a separate decision.

THE STORED TEXT, NOT THE DISPLAYED TEXT. `document_text_display` masks email addresses and
telephone numbers for a reader (migration 0020); this reads `document_text.text`, the
document's own words, because a citation is an assertion about what the document SAYS. The
masking would not hide a docket number, so this is about which text the record means rather
than about a difference in the answer — but `source_location` points into the text that was
read, and pointing into a text nobody stored would be a provenance that cannot be checked.

The ROW RULE is the display view's, minus the masking: live rows, `primary` or `human`, and
a primary is skipped where a live human row holds that page. One reading per page, the best
one held — the same precedence a reader sees, so a finding's page number means the page the
reader would be shown.
"""

from collections.abc import Iterator
from sqlite3 import Connection

from docketyard.citator import find, keys, methods

# The pages of one document, best reading per page, in page order. `reading_channel` comes
# from the row rather than a default: `load.load_document` refuses a document that does not
# say which channel read it, and inventing one here would launder that refusal.
_PAGES = """
SELECT t.page_no, t.text, t.reading_channel
  FROM document_text t
 WHERE t.document_sha256 = ?
   AND t.superseded_by IS NULL
   AND t.reading_role IN ('primary', 'human')
   AND NOT (t.reading_role = 'primary'
            AND EXISTS (SELECT 1 FROM document_text h
                         WHERE h.document_sha256 = t.document_sha256
                           AND h.page_no = t.page_no
                           AND h.reading_role = 'human'
                           AND h.superseded_by IS NULL))
 ORDER BY t.page_no
"""

# Every document a DECISION carries, with the dockets its decisions sit in. The join is the
# whole of what makes a document citable: a filing's attachment has text too, and ADR 0017
# is about what one decision says of another.
_DOCUMENTS = """
SELECT a.document_sha256, d.prefix, d.sequence, d.sub_sequence, d.suffix
  FROM decision_attachment a
  JOIN decision_record r ON r.decision_pk = a.decision_pk
  JOIN docket d ON d.docket_id = r.docket_id
 WHERE a.document_sha256 IS NOT NULL
 ORDER BY a.document_sha256
"""


def own_by_document(con: Connection) -> dict[str, set[str]]:
    """document -> the registry keys of every docket a decision carrying it sits in.

    ADR 0017 D1 keeps the caption/citation judgement with the extractor because the record
    already knows which proceeding a decision belongs to, and `find` refuses an empty set
    rather than defaulting — a document with no `own` would read every caption as a citation.

    THE UNION IS DELIBERATE where one document is carried by more than one decision, or by a
    decision entered in a docket and its sub-docket (ADR 0005): a number that is the own
    proceeding of ANY decision carrying these bytes is a caption in these bytes. Reading it
    as a citation because a second carrier exists would invent an edge out of the record's
    own filing arrangement.
    """
    out: dict[str, set[str]] = {}
    for sha, prefix, seq, sub, suffix in con.execute(_DOCUMENTS):
        out.setdefault(sha, set()).add(keys.registry_key(prefix, seq, sub, suffix))
    return out


def documents(con: Connection, channel: str | None = None) -> Iterator[dict]:
    """One findings document per (document, MACHINE CHANNEL), in `load`'s shape.

    ONE PER CHANNEL, NOT ONE PER DOCUMENT, and that is the whole of what the interchange is
    keyed on. `load` stamps a batch with one `(method, method_version, reading_channel)` and
    `cli._citator` refuses a batch that mixes them, because the confidence written on a row
    is the measurement of THAT pass on THAT channel (ADR 0017 D3, ADR 0018 D8). A document
    read partly from its text layer and partly by OCR is two readings of one document, and
    collapsing them — stamping the OCR pages with the text-layer channel — is the borrowed
    precision `load.WrongChannel` exists to refuse. It would also erase the per-channel
    `citation_reading` row ADR 0018 D3 designs (code review, 2026-09-04, which is how this
    was caught: an earlier draft took the majority channel and its output was unloadable).

    A PAGE WHOSE LIVE READING IS HUMAN IS NOT READ HERE. `'human'` is legal in
    `reading_vocab` and is never what a model pass read from, so `load` refuses it outright;
    a citation a person found on a corrected page is the review layer's to assert (Migration
    B), not this finder's. The page is absent from every channel's `pages_read` rather than
    falling back to the primary it shadows — reading text no reader is shown would put a
    `source_location` where nobody can check it.

    `channel` narrows to one; the default walks every machine channel the store holds.
    """
    own = own_by_document(con)
    machine = methods.machine_channels(con)
    wanted = machine if channel is None else ({channel} & machine)
    for sha in own:
        by_channel: dict[str, list[tuple[int, str]]] = {}
        for page_no, text, page_channel in con.execute(_PAGES, (sha,)):
            if page_channel in wanted:
                by_channel.setdefault(page_channel, []).append((page_no, text or ""))
        for page_channel, pages in sorted(by_channel.items()):
            # A reading of nothing is not a reading: `pages_read` of zero would record that
            # the finder had looked at a document it never read, and an `extraction_run` row
            # would claim a pass over blank pages. The image-only decisions are this case
            # until the OCR wave's readings land.
            if not any(text.strip() for _, text in pages):
                continue
            yield find.findings_document(
                pages, document_sha256=sha, own=own[sha], reading_channel=page_channel
            )
