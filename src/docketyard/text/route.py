"""The route pass: the OCR wave's router verdicts into `page_route` (migration 0032, ADR 0021
addendum 2026-09-15).

THE INPUT IS WHAT THE WAVE WROTE (`tools/rmi-ai-machine/ocr_wave.py`, `run-paddle`):
`<root>/<xx>/<sha>.json`, one file per document —
`{document_sha256, method, method_version, layout_model, region_cut, dpi, routed_at,
pages: {"<n>": {class, regions, labels[, error]}}}`. `routed_at` is the row's `asserted_at`:
when the router said it, not when the store heard it.

WHAT EACH PAGE BECOMES, against the page's live row:

- none: inserted (`loaded`);
- the same class, router and version: nothing written (`unchanged`) — a note or region count
  that differs is not a new verdict;
- a person's row: left alone (`human_held`), as `paginate` leaves a corrected count;
- a different class, router or version: retire at itself, insert, repoint, with
  `superseded_at` set in the retiring statement (`superseded`);
- UNLESS the file is OLDER than the live row and names a different router or version: a stale
  file is refused and the document writes nothing (`stale`), so re-running an old root cannot
  undo a newer router's verdicts.

WHOLE DOCUMENT OR NOTHING. Every page is judged before any is written, and a document the store
cannot take is raised out of `route_document`, which `store.batches` rolls back to the document's
savepoint and counts as `failed`: a page number above the document's live `page_count` (a route
for bytes that are not the bytes paginated), or a document with no paginated count at all — the
check the first refusal needs is not there to make.

A PAGE THE ROUTER ERRORED ON loads as the class the wave recorded for it (`unrouted`, whose
vocabulary note already says the page went to the default reader), with the error in `note`.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from docketyard.store import batches, supersede
from docketyard.store.db import load_json, utcnow
from docketyard.text.fields import Unreadable, sha_field, text_field

ATTACHED = ("loaded", "superseded", "unchanged", "human_held", "stale")  # met its document
NOUN = "route file"


@dataclass(frozen=True)
class PageVerdict:
    page_no: int
    route_class: str
    region_count: int | None
    note: str | None


@dataclass(frozen=True)
class Route:
    """One route file, validated."""

    document_sha256: str
    method: str
    method_version: str
    routed_at: str
    pages: tuple[PageVerdict, ...]


def classes(con) -> frozenset[str]:
    """`route_class_vocab`, read from the store: a class is widened by an INSERT (0018)."""
    return frozenset(r[0] for r in con.execute("SELECT route_class FROM route_class_vocab"))


def from_record(record: dict, allowed: frozenset[str] | set[str]) -> Route:
    """A `Route` from a route file's JSON, or `Unreadable` — never a guess."""
    if not isinstance(record, dict):
        raise Unreadable("not a JSON object")
    sha = sha_field(record)
    method, version = text_field(record, "method"), text_field(record, "method_version")
    routed_at = text_field(record, "routed_at")
    pages = record.get("pages")
    if not isinstance(pages, dict):
        raise Unreadable(f"pages is {type(pages).__name__}, not an object")
    out = []
    for key, page in pages.items():
        if not (isinstance(key, str) and key.isdigit() and int(key) >= 1):
            raise Unreadable(f"page key {key!r} is not a page number")
        if not isinstance(page, dict):
            raise Unreadable(f"page {key} is not an object")
        cls = page.get("class")
        if cls not in allowed:
            raise Unreadable(f"page {key} class {cls!r} is not one of {sorted(allowed)}")
        regions = page.get("regions")
        if regions is not None and (
            isinstance(regions, bool) or not isinstance(regions, int) or regions < 0
        ):
            raise Unreadable(f"page {key} regions is {regions!r}, not a whole number")
        error = page.get("error")
        if error is not None and not isinstance(error, str):
            raise Unreadable(f"page {key} error is {error!r}, not a string")
        out.append(PageVerdict(int(key), cls, regions, error or None))
    return Route(sha, method, version, routed_at, tuple(sorted(out, key=lambda p: p.page_no)))


def read_file(path: Path, allowed: frozenset[str]) -> Route:
    route = from_record(load_json(path.read_text(encoding="utf-8")), allowed)
    if route.document_sha256 != path.stem:
        raise Unreadable(f"names {route.document_sha256[:12]}, filed as {path.stem[:12]}")
    return route


# the order a document's word is chosen in when its pages differ: the most consequential wins
_PRECEDENCE = ("superseded", "loaded", "human_held", "unchanged")


def route_document(con, route: Route, now: str | None = None) -> str:
    """One document's verdicts into `page_route`; the CALLER holds the transaction. Returns
    the word `store.batches.run` counts: loaded, superseded, unchanged, human_held, stale, or
    unknown_document. Raises `Unreadable` for a document the store must refuse whole."""
    now = now or utcnow()
    sha = route.document_sha256
    if con.execute("SELECT 1 FROM document WHERE document_sha256 = ?", (sha,)).fetchone() is None:
        return "unknown_document"
    count = con.execute(
        "SELECT page_count FROM document_pagination"
        " WHERE document_sha256 = ? AND superseded_by IS NULL",
        (sha,),
    ).fetchone()
    if count is None or count[0] is None:
        raise Unreadable("the document has no live paginated page count to check pages against")
    above = [p.page_no for p in route.pages if p.page_no > count[0]]
    if above:
        raise Unreadable(f"page {above[0]} is above the document's live page count {count[0]}")
    live = {
        r[0]: r[1:]
        for r in con.execute(
            "SELECT page_no, route_id, route_class, method, method_version, asserted_at,"
            " confidence_state FROM page_route WHERE document_sha256 = ? AND superseded_by IS NULL",
            (sha,),
        )
    }
    plan: list[tuple[PageVerdict, str, int | None]] = []
    for page in route.pages:
        row = live.get(page.page_no)
        if row is None:
            plan.append((page, "loaded", None))
            continue
        route_id, cls, method, version, asserted_at, state = row
        if state == "human":
            plan.append((page, "human_held", None))
        elif (cls, method, version) == (page.route_class, route.method, route.method_version):
            plan.append((page, "unchanged", None))
        elif (method, version) != (route.method, route.method_version) and (
            route.routed_at < asserted_at
        ):
            return "stale"  # nothing of this document is written
        else:
            plan.append((page, "superseded", route_id))
    for page, outcome, old_id in plan:
        if outcome not in ("loaded", "superseded"):
            continue
        if old_id is not None:
            supersede.retire(con, "page_route", "route_id", old_id, at=now)
        cur = con.execute(
            "INSERT INTO page_route (document_sha256, page_no, route_class, method,"
            " method_version, region_count, note, confidence, confidence_state, asserted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'unmeasured', ?)",
            (
                sha,
                page.page_no,
                page.route_class,
                route.method,
                route.method_version,
                page.region_count,
                page.note,
                route.routed_at,
            ),
        )
        if old_id is not None:
            repoint = "UPDATE page_route SET superseded_by = ? WHERE route_id = ?"
            con.execute(repoint, (cur.lastrowid, old_id))
    seen = {outcome for _, outcome, _ in plan}
    return next((word for word in _PRECEDENCE if word in seen), "unchanged")


def run(con, root: Path, *, log=print, commit_every: int = batches.COMMIT_EVERY) -> Counter:
    """The pass over a route root, through `store.batches`: one key per `route_document`
    outcome, plus `unreadable`, `failed` and `aborted`."""
    allowed = classes(con)
    return batches.run(
        con,
        batches.walk(root, lambda path: read_file(path, allowed)),
        lambda route: route_document(con, route),
        log=log,
        commit_every=commit_every,
    )
