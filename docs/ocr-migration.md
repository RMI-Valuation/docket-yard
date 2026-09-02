# What the OCR migration owes

The checklist for the migration that creates `document_text` and its neighbours, held here
rather than in [ADR 0021](adr/0021-the-ocr-text-grain.md) so that accepting the record means
accepting thirteen decisions and not sixty lines of mechanics. **It becomes the migration's
header comment when the migration is written**, which is where this project keeps this kind
of detail (migrations 0014 and 0015 both carry theirs).

Nothing here is optional and nothing here is a decision. Each item is work the accepted
records already imply, written down so it is not rediscovered at three in the morning.

## The rebuilds SQLite forces

1. **`assertion_method`.** Its `target_table` is a hard `CHECK` over five citation tables and
   SQLite cannot alter a CHECK, so the table is rebuilt: three partial indexes reproduced
   (`assertion_method_one_owner`, `_identity`, `_rank`), the five-branch `CASE` given an
   explicit `WHEN 'document_text'` branch rather than letting it fall to the `ELSE`,
   `route_class` added with its own vocabulary, and the rank index re-formed as
   `UNIQUE (rank_version, target_table, COALESCE(route_class, ''), precedence_rank)`. The
   COALESCE is not decoration: SQLite treats NULLs as distinct, so without it the five
   citation tables lose the rank uniqueness migration 0014 built that index to guarantee.
   `citator.methods.declare` writes a fixed column list into this table and must move in the
   same commit.

2. **`correction`.** Its CHECK lists the seven natural-keyed tables that must carry a
   slash-rendered key; `document_text` is not among them, so a correction naming it could
   carry a bare integer — the exact defect that rebuild existed to stop. Extended in the same
   transaction, with its key rendering written beside the others migration 0014 lists.

Both run inside the migration's single transaction, as every migration before them has.

## The vocabularies and their rows

3. **`review_queue_vocab`** gains `ocr_page`, the name `schema-draft.md` § 7 already uses.
4. **`review_target_vocab`** gains `document_text`, natural-keyed. The five-segment key form
   `<sha256>/<page_no>/<method>/<method_version>/<render_profile>` and the page-grained queue
   exclusion of ADR 0021 D12 are both pinned by tests, or they are conventions nobody
   enforces.
5. **`measured_target_vocab`** gains `document_text` **with an empty `class_vocab`**, so ADR
   0021 D8's "nothing published until measured" is enforced by the schema rather than by
   convention. The classes it will eventually hold are the benchmark's own — CER, WER, docket
   numbers, dates, at three tiers — and each must be scoped to this stage, or migration
   0014's lesson repeats and one stage's figure is displayed beside another's.
6. **`route_class_vocab`**, with `unrouted` as a member rather than a null, because ADR 0021
   D9 requires an undetected page to be routed to a reader rather than skipped.

## The tables that have no home yet

7. **`text_agreement`** — the table ADR 0021 D7's confidence rule needs and nothing owns.
   `citation_judgement` is citation-family and cannot hold it. Keyed on the page, naming both
   readings, carrying its rule, its rule version and an ADR 0007 block. **Without it the
   review queue cannot find a flagged page at all.**
8. **`reader_report`**, if the "report a misreading" path ships with the queue.
   `schema-draft.md` § 7 names it as the `/contribute` landing that has no table.
9. **The payload table**, with `document`'s discipline — digest, size, first seen — so a
   pruned payload is a visible fact and not a dangling hash.

## The passes

10. **A pagination pass over every held PDF** to populate `document_page`. ADR 0021 D4 makes
    an unread page countable only if a row exists for a document nobody has read, and that is
    a pass, not a number. `had_text_layer` is a derived assertion — extractors disagree on a
    page carrying three junk characters — so it carries a method, a version and a timestamp,
    or it breaks ADR 0007 on arrival.
11. **An OCR class measurement before any OCR-channel edge projects.** ADR 0017 D3,
    unchanged. `citator.methods.measure` hardcodes `reading_channel = 'text-layer'`, so
    today's guard is accidental; it is made explicit here.

## The infrastructure that breaks on deploy day

12. **`dump.py`'s allowlist and its shadow handling.** Every new table is classified per ADR
    0022 D5 or the nightly snapshot raises `Unsafe`. The shadow logic is hardcoded to names
    beginning `search_fts_`, so a second FTS index is a code change and not an allowlist
    entry — and only `HELD` (dropped) is safe for it, because a `DERIVED` classification
    leaves `%_data`/`%_idx` shadows holding a positional index of withheld text.
    `HELD_REASON` is one string for the whole list and would say something untrue about the
    text-layer channel; it needs to be per-table or the publication filtered.
13. **The blob prefix, named.** `prune_blobs.py` lists only `blobs/`, the sync unit copies
    only `data/blobs`, and the web tier's IAM grant is `s3:GetObject` on `blobs/*` and
    nothing else. Anything under another prefix is unsynced, unpruned and unreadable by the
    process that serves readers. Payload objects are content-addressed by their own digest,
    two levels deep, one per document per pass (ADR 0022 D9).
14. **The loader.** A new page-grained, multi-method interchange: it commits per document as
    the citator's does, streams rather than parsing the whole directory, and shares none of
    `methods.stamp` (which raises when a class has no measurement), `methods.declare` (whose
    row list is citation-family) or `methods.owner` (which hardcodes
    `target_table = 'citation'`).
15. **`docs/search.md`** says document text is not indexed. It is a published-page source, so
    it moves with the code or the drift rule is broken.

## The review

16. **schema-critic before the tables exist.** Grain, identity and provenance at once, which
    `CLAUDE.md` requires of anything schema-touching.
