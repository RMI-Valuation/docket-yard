"""Build the re-read queue from the store, read-only: the flagged text-layer pages, prose first.

Run it where the store is (production, `sudo nice -n 15`, `?mode=ro`), with `text_quality.py`
and the lexicon beside it. Measured 2026-09-17 over 1,085,316 live text-layer primaries in
24 minutes: 31,798 flagged, of which 6,170 are prose-shaped, in 4,896 documents.

Flagged = a live text-layer primary with >= 15 letter-bearing tokens whose score is under the
cut, the score being `lexicon_hits / lettered_tokens` — NOT `shares()["lex"]`, which divides by
word-shaped tokens and is a diagnostic (the two-denominator confusion the research README
records). Ordered by the operator's rule of 2026-09-17 — prose first, maps and drawings
last — using the screen in `text_quality.looks_like_prose`, which orders a queue and asserts
nothing. Writes queue.csv.gz beside itself; nothing is written to the store."""

import csv
import gzip
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from text_quality import features, layout, looks_like_prose  # noqa: E402

CUT = 0.5
FLOOR = 15
YEAR = re.compile(r"(19|20)\d\d")
t0 = time.time()
con = sqlite3.connect("file:/srv/docketyard/data/docketyard.sqlite?mode=ro", uri=True)
lexicon = set(open("/tmp/tq/lexicon.txt").read().split())

year = {}
for q in (
    "select fa.document_sha256, f.filed_date from filing f"
    " join filing_attachment fa using (filing_pk)",
    "select da.document_sha256, d.service_date from decision_record d"
    " join decision_attachment da using (decision_pk)",
    "select ca.document_sha256, c.date_received_or_sent from enviro_comment c"
    " join enviro_comment_attachment ca using (comment_pk)",
):
    for sha, date in con.execute(q):
        if sha and (m := YEAR.search(date or "")):
            y = int(m.group(0))
            if sha not in year or y < year[sha]:
                year[sha] = y

rows, seen = [], 0
for tid, sha, page, text in con.execute(
    "select text_id, document_sha256, page_no, text from document_text"
    " where superseded_by is null and reading_channel = 'text-layer' and reading_role = 'primary'"
):
    seen += 1
    f = features(text, lexicon)
    if f["lettered"] < FLOOR:
        continue
    score = f["hits"] / f["lettered"]
    if score >= CUT:
        continue
    lay = layout(text)
    rows.append(
        (
            tid,
            sha,
            page,
            round(score, 3),
            int(looks_like_prose(lay)),
            year.get(sha, ""),
            lay["lines"],
            lay["median_line"],
            round(lay["tokens_per_line"], 2),
            round(lay["numeric_share"], 3),
        )
    )
print(
    f"{seen} live text-layer primaries read, {len(rows)} flagged, {time.time() - t0:.0f}s",
    flush=True,
)

# prose first, then by score: the worst pages of each kind are read before the merely poor
rows.sort(key=lambda r: (-r[4], r[3]))
with gzip.open("/tmp/tq/queue.csv.gz", "wt", newline="") as out:
    w = csv.writer(out)
    w.writerow(
        [
            "text_id",
            "sha",
            "page",
            "score",
            "prose",
            "year",
            "lines",
            "median_line",
            "tokens_per_line",
            "numeric_share",
        ]
    )
    w.writerows(rows)

prose = sum(r[4] for r in rows)
docs = len({r[1] for r in rows})
print(f"prose-shaped {prose}, other {len(rows) - prose}; {docs} documents")
for lo, hi in ((0, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5)):
    n = sum(1 for r in rows if lo <= r[3] < hi)
    p = sum(1 for r in rows if lo <= r[3] < hi and r[4])
    print(f"  score {lo}-{hi}: {n:6} pages, {p:6} prose-shaped")
