You are drafting ground-truth labels for Docket Yard's OCR citation benchmark. A person
(the operator) will check every row you write against the same page images, so accuracy and
completeness matter more than speed. You are NOT reviewing or improving anything else.

## What you are given

Batch {batch}: read `E:\DevProjects\docket-yard\data\ocr-citation\batches.json`, entry with
`"batch": {batch}`. For each document it lists `document_sha256`, `labelled_pages` and
`decisions` (each with `docket` — the proceeding the decision is filed in — and
`stb_decision_id`, `service_date`, `decision_type`).

Every labelled page is an image at
`E:\DevProjects\docket-yard\data\ocr-citation\pages\<first 12 hex of document_sha256>_p<page>.png`.
Open each one with the Read tool and read the WHOLE page — body, footnotes, headers, stamps,
tables, margins.

Label ONLY from the image. Do not read any other file under `data/ocr-citation/` except
`batches.json` and the page images; in particular never open `ocr-text.json` or anything
under `blobs/`. The benchmark measures what a machine reading of these scans gets wrong, so a
label taken from a machine reading measures nothing.

Only the pages listed are in scope. A long document was sampled; do not look for or label
other pages.

## What to label (the benchmark's conventions, citations and captions only)

One row per distinct (page, target) — a docket mentioned three times on a page is one row.

- **citation, `stb`**: a reference to a Board or ICC proceeding or decision OTHER than this
  document's own proceeding named as itself — another docket, a prior decision (even in the
  same docket) given by `Decision No.`, `slip op.`, `served <date>`, `decision of <date>`,
  an Ex Parte rulemaking relied on, a short form. Docket-shaped: `FD 36500`,
  `Finance Docket No. 32760 (Sub-No. 46)`, `AB-55 (Sub-No. 595X)`, `Ex Parte No. 711`,
  `NOR 42144`, `MC-F-21000`, `WCC-101`, `ICC Docket No. …`.
- **citation, `court`**: a court case. **citation, `record`**: a filing in this proceeding
  given as party, document and date (the docket number in it is an address).
- **caption, `self`**: this document's own proceeding named as ITSELF, naming no document —
  the caption, a heading, a running header, a bare `Docket No. X`, "All pleadings referring to
  Docket No. X". The own proceedings are the `docket` values in `decisions`, AND their parent
  docket and sub-dockets (e.g. a decision filed in `AB 55 (595X)` has `AB 55` as family). THE
  TEST IS DOCUMENT VERSUS PROCEEDING: `Docket No. EP 787` is a caption; `NPRM, EP 787, slip op.
  at 4` is a citation, because it points at a specific decision, even in the own docket.

Statutes, CFR sections, U.S.C., Federal Register cites, and deadlines are NOT labelled.

## Columns (CSV, header row exactly as below, UTF-8, comma-separated, RFC-4180 quoting)

`document_sha256,page,kind,target_kind,quoted,target,note`

- `page`: the page number from the image's file name.
- `kind`: `citation` or `caption`.
- `target_kind`: `stb`, `court`, `record` (citation) or `self` (caption).
- `quoted`: the reference EXACTLY as printed on the page, character for character — spacing,
  punctuation, `Sub-No.` spelling, capitals. Never corrected or expanded.
- `target`: for `stb` and `self`, the proceeding a citator would resolve, in the form
  `PREFIX SEQUENCE` or `PREFIX SEQUENCE (SUB)` — `FD 32760 (46)`, `AB 55 (595X)`, `EP 711`,
  `NOR 42144`. For a consolidated list, one row per proceeding. For `court`/`record`, the case
  or filing name as printed.
- `note`: anything a checker needs — where on the page it sits, a digit you cannot read with
  certainty (write `uncertain digit` and give your best reading in `target`, never guess
  silently), a reference that starts on this page and completes on an unlabelled one, why a
  nearby string was passed over. A page with nothing to label gets ONE row with `kind` and
  `target_kind` empty and `note` = `nothing to label`, so an empty page is a reading, not an
  absence.

A digit you genuinely cannot read: `[illegible]` in `quoted` at that position, and say so in
`note`. Never invent a docket number.

## Output

Write `E:\DevProjects\docket-yard\data\ocr-citation\drafts\batch-{batch:02d}.csv` with the Write
tool (create the directory if needed). Every labelled page of every document in the batch must
appear at least once. When done, reply with ONLY: the file path, rows written, pages covered,
and a list of any pages you could not read or any row you are unsure of (page and why).
