"""The loader: one document's reading, page by page, into `document_text` (migration 0018).

Page-grained and multi-method (`docs/ocr-migration.md` item 13). One READING is one pass
over one document by one method at one version under one render profile — the natural key
ADR 0021 D1 fixes — and it arrives as one JSON file. Two shapes are read:

- THE EXTRACTION RECORD `tools/rmi-ai-machine/extract_text.py` writes, which is the text
  layer's reading (ADR 0021 D3): `method` is the TOOL, `render_profile` is `native`, the
  channel is `text-layer`, the role is `primary`, and `page_text[i]` is page i+1.
- A READING DOCUMENT, the general shape an OCR pass will POST back:

      {
        "document_sha256": "<64 hex>",
        "method": "dots.mocr", "method_version": "1.5", "render_profile": "150",
        "reading_channel": "ocr", "reading_role": "primary" | "second",
        "route": {"class": "degraded", "method": "pp-doclayoutv3", "method_version": "3.0"},
        "ran_at": "...", "outcome": "read" | "failed" | "skipped",
        "pages_failed": 0,                 pages attempted and not read (ADR 0021 D5)
        "payload_kind": "dots.mocr.json",  what the engine output under `engine` IS; required,
                                           because block identity is a function of the
                                           payload's SHAPE (0018) and a default is a guess
        "engine": {...},                   the engine's own output, kept whole (ADR 0021 D6)
        "pages": [{"page_no": 1, "text": "...", "engine_confidence": 0.93,
                   "member": "engine/pages/0", "route": {...}?,
                   "agreement": {"distance": 0.04, "method": "...", "method_version": "1",
                                 "against": {"method": "pymupdf", "method_version": "1.24.10",
                                             "render_profile": "native"}}?}]
      }

  An agreement NAMES THE PRIMARY IT WAS MEASURED AGAINST, by key. The loader resolves that
  key to the page's live primary and refuses the reading when they differ: the pointer is
  quoted from the file, never computed from whatever happens to be live when the file lands
  (`CLAUDE.md`, and 0018's reason the second operand must be identified — the primary is
  superseded routinely, and a band attributed to text it was never measured against is a
  false number on a page).

THE FILE IS THE PAYLOAD. Its bytes go to the blob tier content-addressed by their own digest
(`records.save_blob`, the `blobs/<dg[:2]>/<dg>` prefix ADR 0022 D2 names) and are recorded in
`text_payload`; every page row carries that digest and a member path INTO the file — for the
extraction record, `page_text[i]`. That is ADR 0021 D6 for both channels at once. The file is
written to the blob tier AFTER the rows land, so a reading the store refuses leaves no
orphan under `blobs/` for the sync to ship; a batch rolled back by an abort can still leave
its readings' files behind, bounded by one batch and re-derived to the same address next run.

A RESTART COSTS ONE LOOKUP. `ocr_run` is keyed on `ran_at` and written in the same
transaction as the pages, so an existing run row for this reading's key and `ran_at` proves
every page of it already landed; the loader returns `restart` before hashing or parsing the
body. An extraction record's HEADER is what the lookup needs, and it is read from the file's
first 4 KB (`fields.read_head`); the body — 2.5 GB across the record — is read only when a
reading is new. A general reading document is parsed whole.

WHAT SUPERSEDES. Within the natural key, a changed `text_sha256`. ACROSS keys — the idiom
migration 0018 names as new to this project — a `primary` (or a `second`) displaces the
page's live primary (second) of ANOTHER key, because `document_text_one_primary` permits one:
the outgoing row is retired at itself (`store.supersede.retire`, with `at`), the new one
inserted, the old repointed, in one transaction. A live `human` row is never displaced by
this loader; the primary lands beside it and the display view keeps showing the human one.
A key that is live on the page IN ANOTHER ROLE is refused by name rather than left to the
natural-key index's collision: a reading does not change role by re-posting.

THE PAGE INDEX IS KEPT IN STEP by `store.page_index`, whose docstring carries the
obligations and the one thing the loader cannot know.

AN EMPTY PAGE IS A ROW; A FAILED PASS IS A RUN. `text = ''` is a reading (ADR 0021 D5). A
pass with no pages — `outcome` failed or skipped — writes its `ocr_run` row and nothing else,
and is counted `run_only`, apart from `unchanged`, so a wave of failed passes is not reported
as text that was already there.
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from docketyard.capture import records
from docketyard.citator import methods
from docketyard.store import batches, page_index, supersede
from docketyard.store.db import utcnow
from docketyard.text.fields import (
    HEAD,
    Unreadable,
    read_head,
    sha_field,
    text_field,
    text_sha256,
)

ROLES = ("primary", "second")  # what a model pass may write; 'human' is the review layer's
RUN_OUTCOMES = ("read", "failed", "skipped")
ATTACHED = ("loaded", "unchanged", "restart", "run_only")  # a reading met its document
NOUN = "reading"


@dataclass(frozen=True)
class Route:
    route_class: str
    method: str
    method_version: str


class Key(NamedTuple):
    method: str
    method_version: str
    render_profile: str


@dataclass(frozen=True)
class Agreement:
    distance: float
    method: str
    method_version: str
    against: Key


@dataclass(frozen=True)
class Page:
    page_no: int
    text: str
    text_sha256: str
    member: str
    engine_confidence: float | None = None
    route: Route | None = None
    agreement: Agreement | None = None


@dataclass(frozen=True)
class Header:
    """Everything about a reading but its pages: enough to know whether to read them."""

    document_sha256: str
    key: Key
    reading_channel: str
    reading_role: str
    ran_at: str
    outcome: str
    pages_failed: int
    payload_kind: str
    route: Route | None = None


class Reading:
    """A header, and the body — the file's bytes and its pages — read on demand."""

    def __init__(self, header: Header, path: Path | None = None, body=None):
        self.header = header
        self._path = path
        self._body = body

    def body(self) -> tuple[bytes, tuple[Page, ...]]:
        if self._body is None:
            payload = self._path.read_bytes()
            self._body = (payload, pages_of_extraction(json.loads(payload), self.header))
        return self._body


# --- the two shapes ------------------------------------------------------------------------


def _route(d, where: str) -> Route | None:
    if d is None:
        return None
    if not isinstance(d, dict):
        raise Unreadable(f"{where} route is not an object")
    return Route(text_field(d, "class"), text_field(d, "method"), text_field(d, "method_version"))


def _key(d: dict) -> Key:
    return Key(
        text_field(d, "method", allow_slash=False),
        text_field(d, "method_version", allow_slash=False),
        text_field(d, "render_profile", allow_slash=False),
    )


def header_of_reading(doc: dict) -> Header:
    if not isinstance(doc, dict):
        raise Unreadable("not a JSON object")
    channel = text_field(doc, "reading_channel")
    role = text_field(doc, "reading_role")
    if role not in ROLES:
        raise Unreadable(f"reading_role {role!r} is not one of {ROLES}; 'human' is the reviewer's")
    key = _key(doc)
    if channel == "text-layer" and key.render_profile != "native":
        raise Unreadable("a text-layer reading's render_profile is 'native' (ADR 0021 D3)")
    outcome = doc.get("outcome", "read")
    if outcome not in RUN_OUTCOMES:
        raise Unreadable(f"outcome {outcome!r} is not one of {RUN_OUTCOMES}")
    failed = doc.get("pages_failed", 0)
    if isinstance(failed, bool) or not isinstance(failed, int) or failed < 0:
        raise Unreadable(f"pages_failed is {failed!r}")
    return Header(
        sha_field(doc),
        key,
        channel,
        role,
        text_field(doc, "ran_at"),
        outcome,
        failed,
        text_field(doc, "payload_kind"),
        _route(doc.get("route"), "the reading"),
    )


def _page(d, i: int, header: Header) -> Page:
    if not isinstance(d, dict):
        raise Unreadable(f"pages[{i}] is not an object")
    no, text = d.get("page_no"), d.get("text")
    if isinstance(no, bool) or not isinstance(no, int) or no < 1:
        raise Unreadable(f"pages[{i}].page_no is {no!r}, not a page number")
    if not isinstance(text, str):
        raise Unreadable(f"page {no}: text is not a string")  # '' is a reading; None is not
    conf = d.get("engine_confidence")
    if conf is not None and (isinstance(conf, bool) or not isinstance(conf, int | float)):
        raise Unreadable(f"page {no}: engine_confidence is {conf!r}")
    agreement = None
    if (a := d.get("agreement")) is not None:
        if not isinstance(a, dict) or not isinstance(a.get("distance"), int | float):
            raise Unreadable(f"page {no}: agreement is not {{distance, method, ..., against}}")
        if not isinstance(a.get("against"), dict):
            raise Unreadable(f"page {no}: an agreement names the primary it was measured against")
        agreement = Agreement(
            float(a["distance"]),
            text_field(a, "method"),
            text_field(a, "method_version"),
            _key(a["against"]),
        )
    route = _route(d.get("route"), f"page {no}") or header.route
    if header.reading_channel == "ocr" and route is None:
        raise Unreadable(
            f"page {no}: an OCR reading names the class it was routed as (ADR 0021 D4)"
        )
    return Page(no, text, text_sha256(text), text_field(d, "member"), conf, route, agreement)


def pages_of_reading(doc: dict, header: Header) -> tuple[Page, ...]:
    raw = doc.get("pages", [])
    if not isinstance(raw, list):
        raise Unreadable("pages is not a list")
    pages = tuple(_page(p, i, header) for i, p in enumerate(raw))
    if len({p.page_no for p in pages}) != len(pages):
        raise Unreadable("a page is read twice in one reading")
    return pages


def header_of_extraction(record: dict) -> Header:
    """`extract_text.py`'s record as the text layer's reading. `method` is the TOOL, not the
    extraction's name for itself (`text-layer`), which is the channel."""
    if not isinstance(record, dict):
        raise Unreadable("not a JSON object")
    return Header(
        sha_field(record),
        Key(
            text_field(record, "tool", allow_slash=False),
            text_field(record, "tool_version", allow_slash=False),
            "native",
        ),
        "text-layer",
        "primary",
        text_field(record, "extracted_at"),
        "read",
        0,
        "extract_text.json",
    )


def pages_of_extraction(record: dict, header: Header) -> tuple[Page, ...]:
    texts = record.get("page_text") if isinstance(record, dict) else None
    if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
        raise Unreadable("page_text is not a list of strings")
    return tuple(
        Page(i + 1, text, text_sha256(text), f"page_text[{i}]") for i, text in enumerate(texts)
    )


def from_reading(doc: dict, payload: bytes) -> Reading:
    header = header_of_reading(doc)
    return Reading(header, body=(payload, pages_of_reading(doc, header)))


def from_extraction(record: dict, payload: bytes) -> Reading:
    header = header_of_extraction(record)
    return Reading(header, body=(payload, pages_of_extraction(record, header)))


def _is_extraction(path: Path) -> bool:
    """Told from the first 4 KB without parsing: an extraction record's header names its
    `tool` and never a `reading_role`; a reading document names its role, and its engine
    payload may say anything — including the string `"page_text"` — so the marker alone
    cannot decide, and a reading document is never cut at it."""
    with path.open("rb") as f:
        head = f.read(HEAD).decode("utf-8", "replace")
    return '"tool"' in head and '"reading_role"' not in head


def read_file(path: Path) -> Reading:
    """One file. An extraction record yields its header from the first 4 KB and its body
    on demand; a reading document is parsed whole, once. Either must be filed under its
    sha."""
    if _is_extraction(path):
        reading = Reading(header_of_extraction(read_head(path)), path=path)
    else:
        payload = path.read_bytes()
        doc = json.loads(payload)
        if isinstance(doc, dict) and "page_text" in doc:  # a stub, or a record read whole
            reading = from_extraction(doc, payload)
        else:
            reading = from_reading(doc, payload)
    if reading.header.document_sha256 != path.stem:
        raise Unreadable(f"names {reading.header.document_sha256[:12]}, filed as {path.stem[:12]}")
    return reading


# --- the write -----------------------------------------------------------------------------


class Live(NamedTuple):
    text_id: int
    role: str
    key: Key
    text_sha256: str
    agreement: tuple  # (against, distance, method, version), or four Nones


def _live(con, sha: str) -> tuple[dict[tuple[int, str], Live], dict[tuple[int, Key], Live]]:
    """The document's live rows, once: by (page, role) and by (page, natural key)."""
    by_role: dict[tuple[int, str], Live] = {}
    by_key: dict[tuple[int, Key], Live] = {}
    for text_id, no, role, m, v, r, digest, *agreement in con.execute(
        "SELECT text_id, page_no, reading_role, method, method_version, render_profile,"
        " text_sha256, agreement_against, agreement_distance, agreement_method,"
        " agreement_method_version FROM document_text"
        " WHERE document_sha256 = ? AND superseded_by IS NULL",
        (sha,),
    ):
        row = Live(text_id, role, Key(m, v, r), digest, tuple(agreement))
        by_role[(no, role)] = row
        by_key[(no, row.key)] = row
    return by_role, by_key


def _run_recorded(con, h: Header) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM ocr_run WHERE document_sha256 = ? AND method = ?"
            " AND method_version = ? AND reading_channel = ? AND render_profile = ?"
            " AND ran_at = ?",
            (
                h.document_sha256,
                h.key.method,
                h.key.method_version,
                h.reading_channel,
                h.key.render_profile,
                h.ran_at,
            ),
        ).fetchone()
        is not None
    )


def load_reading(con, data_dir, reading: Reading, now: str | None = None, *, machine=None) -> str:
    """One reading into `document_text`, `text_payload`, `ocr_run` and `page_fts`; the
    CALLER holds the transaction. Returns `loaded`, `unchanged` (every page already said
    this), `restart` (this very pass is already recorded), `run_only` (a pass with no
    pages), or `unknown_document`. Raises `Unreadable` for what the store shows to be
    wrong with the reading — `store.batches` counts that as `failed`."""
    now = now or utcnow()
    h = reading.header
    sha = h.document_sha256
    if h.reading_channel not in (machine if machine is not None else methods.machine_channels(con)):
        raise Unreadable(f"reading_channel {h.reading_channel!r} is not a model's")
    if con.execute("SELECT 1 FROM document WHERE document_sha256 = ?", (sha,)).fetchone() is None:
        return "unknown_document"
    if _run_recorded(con, h):
        return "restart"
    payload, pages = reading.body()
    digest = hashlib.sha256(payload).hexdigest()
    con.execute(
        "INSERT OR IGNORE INTO text_payload (payload_digest, payload_kind, size_bytes,"
        " media_type, first_seen_at) VALUES (?, ?, ?, 'application/json', ?)",
        (digest, h.payload_kind, len(payload), now),
    )  # OR IGNORE is right here: the digest IS the identity, and the same bytes are one row
    by_role, by_key = _live(con, sha)
    written = sum(_load_page(con, h, page, digest, now, by_role, by_key) for page in pages)
    con.execute(
        "INSERT INTO ocr_run (document_sha256, method, method_version, reading_channel,"
        " render_profile, outcome, pages_read, pages_failed, ran_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sha,
            h.key.method,
            h.key.method_version,
            h.reading_channel,
            h.key.render_profile,
            h.outcome,
            len(pages),
            h.pages_failed,
            h.ran_at,
        ),
    )
    records.save_blob(data_dir, payload)  # after the rows: a refused reading leaves no file
    if not pages:
        return "run_only"
    return "loaded" if written else "unchanged"


def _load_page(con, h: Header, page: Page, digest: str, now: str, by_role, by_key) -> int:
    sha, no, role = h.document_sha256, page.page_no, h.reading_role
    holder = by_role.get((no, role))  # the page's live row OF THIS ROLE, whatever its key
    same_key = by_key.get((no, h.key))
    if same_key is not None and (holder is None or same_key.text_id != holder.text_id):
        raise Unreadable(
            f"page {no}: {'/'.join(h.key)} is live as {same_key.role!r}; a reading does not"
            f" change role by being posted again as {role!r}"
        )
    against = None
    if page.agreement is not None:
        primary = by_role.get((no, "primary"))
        if primary is None:
            raise Unreadable(f"page {no}: an agreement with no live primary to be against")
        if primary.key != page.agreement.against:
            raise Unreadable(
                f"page {no}: the agreement was measured against"
                f" {'/'.join(page.agreement.against)} but the live primary is"
                f" {'/'.join(primary.key)}"
            )
        against = primary.text_id
    a = page.agreement
    agreement = (against, a.distance, a.method, a.method_version) if a else (None,) * 4
    # "this pass already said this" is the TEXT and the AGREEMENT: a second re-posted with
    # the same text but measured against the page's replacement primary is a new row, or
    # the live row keeps pointing its distance at the retired one (code review, 2026-09-03)
    if (
        holder is not None
        and holder.key == h.key
        and holder.text_sha256 == page.text_sha256
        and holder.agreement == agreement
    ):
        return 0
    visible = role == "primary" and (no, "human") not in by_role
    if holder is not None:
        # CROSS-KEY OR SAME-KEY, the order is the same: retire at itself, insert, repoint —
        # and `superseded_at` in the same statement, or the biconditional refuses it
        supersede.retire(con, "document_text", "text_id", holder.text_id, at=now)
        if visible:
            page_index.leave(con, holder.text_id)
    cur = con.execute(
        "INSERT INTO document_text (document_sha256, page_no, method, method_version,"
        " render_profile, reading_channel, reading_role, route_class, route_method,"
        " route_method_version, text, text_sha256, engine_confidence, agreement_distance,"
        " agreement_against, agreement_method, agreement_method_version, payload_digest,"
        " payload_member, confidence, confidence_state, asserted_from_document, asserted_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'unmeasured',"
        " ?, ?)",
        (
            sha,
            no,
            *h.key,
            h.reading_channel,
            role,
            page.route.route_class if page.route else None,
            page.route.method if page.route else None,
            page.route.method_version if page.route else None,
            page.text,
            page.text_sha256,
            page.engine_confidence,
            page.agreement.distance if page.agreement else None,
            against,
            page.agreement.method if page.agreement else None,
            page.agreement.method_version if page.agreement else None,
            digest,
            page.member,
            sha,
            now,
        ),
    )
    if holder is not None:
        con.execute(
            "UPDATE document_text SET superseded_by = ? WHERE text_id = ?",
            (cur.lastrowid, holder.text_id),
        )
    if visible:
        page_index.enter(con, cur.lastrowid, page.text)
    return 1


def run(
    con, root: Path, data_dir, *, log=print, commit_every: int = batches.COMMIT_EVERY
) -> Counter:
    """The pass over a directory of readings, through `store.batches`."""
    machine = methods.machine_channels(con)
    return batches.run(
        con,
        batches.walk(root, read_file),
        lambda r: load_reading(con, data_dir, r, machine=machine),
        log=log,
        commit_every=commit_every,
    )
