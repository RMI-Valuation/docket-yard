"""The route pass: the OCR wave's router verdicts into `page_route` (migration 0032, ADR 0021
addendum 2026-09-15).

THE INPUT IS WHAT THE WAVE WROTE (`tools/rmi-ai-machine/ocr_wave.py`, `run-paddle`):
`<root>/<xx>/<sha>.json`, one file per document —
`{document_sha256, method, method_version, layout_model, region_cut, dpi, routed_at,
pages: {"<n>": {class, regions, labels[, error]}}}`.

TWO CLOCKS. A row's `asserted_at` is the store's — when the pass wrote it, as `document_text`'s
is — and `superseded_at` is the same clock, so the pair replays what a page showed on a date.
The file's `routed_at` is kept beside them as the router's own clock, and is what staleness
compares — parsed, REQUIRED to carry a timezone, and stored in UTC as
`2026-09-05T13:22:13+00:00`, so that comparing two of them as strings compares instants; any
other shape is `Unreadable`. `dpi` becomes `render_profile` (e.g. '150').

WHAT EACH PAGE BECOMES, against the page's live row:

- none: inserted (`loaded`);
- the same verdict — class, router, version and render: nothing written (`unchanged`); a note or
  region count that differs is not a new verdict;
- a person's row: left alone (`human_held`), as `paginate` leaves a corrected count;
- a different verdict: retire at itself, insert, repoint, with `superseded_at` set in the
  retiring statement (`superseded`);
- UNLESS the file was routed NO LATER than the live row was: a differing verdict from an older
  file, or from one routed at the same instant (the first of two loaded wins), is refused and the
  document writes nothing (`stale`), whatever its version, so re-running an old root cannot undo
  a newer verdict. The live row's `routed_at` is that of the verdict AS FIRST LOADED: an
  `unchanged` load writes nothing, so a later file agreeing with it does not move the date.

WHOLE DOCUMENT OR NOTHING. Every page is judged before any is written, and a document the store
cannot take is raised out of `route_document`, which `store.batches` rolls back to the document's
savepoint and counts as `failed`: a page number above the document's live `page_count` (a route
for bytes that are not the bytes paginated), or a document with no paginated count at all — the
check the first refusal needs is not there to make.

A PAGE THE ROUTER FAILED ON (its entry carries `error`) IS NOT A VERDICT: the wave recorded it
as `unrouted` so its reader could run, but nothing classified it. No row is written; the pass
counts such pages under `route_error_pages`.

WHAT A FILE DOES NOT SAY IS REPORTED, NOT ASSUMED (Copilot and code review, PR #36). A file
carrying no verdict at all — no pages, or every page errored — is `no_verdicts`, which is not
attached, so the exit status refuses a root of them instead of calling a pass that wrote nothing
a success. A file that names only SOME of a document's live pages still loads what it names, and
returns `omits_live_pages`: the rows it did not mention stay live, and this pass will not retire
a verdict on the strength of a file's silence — but the count says a file did it.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from docketyard.store import batches, supersede
from docketyard.store.db import load_json, utcnow
from docketyard.text.fields import Unreadable, sha_field, text_field

# met its document. `no_verdicts` is NOT here: a file that classified nothing attached nothing,
# and a cron told it succeeded would never learn that a root of such files landed no row.
ATTACHED = ("loaded", "superseded", "unchanged", "human_held", "stale", "omits_live_pages")
NOUN = "route file"


@dataclass(frozen=True)
class PageVerdict:
    page_no: int
    route_class: str
    region_count: int | None


@dataclass(frozen=True)
class Route:
    """One route file, validated. `errored` is the pages the router failed on: no verdict."""

    document_sha256: str
    method: str
    method_version: str
    render_profile: str
    routed_at: str
    pages: tuple[PageVerdict, ...]
    errored: tuple[int, ...] = ()


def classes(con) -> frozenset[str]:
    """`route_class_vocab`, read from the store: a class is widened by an INSERT (0018)."""
    return frozenset(r[0] for r in con.execute("SELECT route_class FROM route_class_vocab"))


def _routed_at(record: dict) -> str:
    """The router's clock as one UTC shape, or `Unreadable`: a time with no zone is not an
    instant, and staleness compares these as strings."""
    raw = text_field(record, "routed_at")
    try:
        at = datetime.fromisoformat(raw)
    except ValueError:
        raise Unreadable(f"routed_at {raw!r} is not an ISO 8601 time") from None
    if at.tzinfo is None or at.utcoffset() is None:
        raise Unreadable(f"routed_at {raw!r} carries no timezone")
    try:  # a time at the edge of the calendar parses, then leaves it in UTC
        return at.astimezone(UTC).isoformat(timespec="seconds")
    except OverflowError:
        raise Unreadable(f"routed_at {raw!r} is out of range in UTC") from None


def _render(record: dict) -> str:
    dpi = record.get("dpi")
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi <= 0:
        raise Unreadable(f"dpi is {dpi!r}, not a positive whole number")
    return str(dpi)


def from_record(record: dict, allowed: frozenset[str] | set[str]) -> Route:
    """A `Route` from a route file's JSON, or `Unreadable` — never a guess."""
    if not isinstance(record, dict):
        raise Unreadable("not a JSON object")
    sha = sha_field(record)
    method, version = text_field(record, "method"), text_field(record, "method_version")
    if method == "human":  # a file is a machine's; the store's CHECK would refuse it as `failed`
        raise Unreadable("method 'human' is a person's correction, never a route file")
    routed_at = _routed_at(record)
    render = _render(record)
    pages = record.get("pages")
    if not isinstance(pages, dict):
        raise Unreadable(f"pages is {type(pages).__name__}, not an object")
    out, errored = [], []
    for key, page in pages.items():
        if not (isinstance(key, str) and key.isdigit() and int(key) >= 1):
            raise Unreadable(f"page key {key!r} is not a page number")
        if not isinstance(page, dict):
            raise Unreadable(f"page {key} is not an object")
        if page.get("error") is not None:
            errored.append(int(key))
            continue
        cls = page.get("class")
        if cls not in allowed:
            raise Unreadable(f"page {key} class {cls!r} is not one of {sorted(allowed)}")
        regions = page.get("regions")
        if regions is not None and (
            isinstance(regions, bool) or not isinstance(regions, int) or regions < 0
        ):
            raise Unreadable(f"page {key} regions is {regions!r}, not a whole number")
        out.append(PageVerdict(int(key), cls, regions))
    return Route(
        sha,
        method,
        version,
        render,
        routed_at,
        tuple(sorted(out, key=lambda p: p.page_no)),
        tuple(sorted(errored)),
    )


def read_file(path: Path, allowed: frozenset[str]) -> Route:
    route = from_record(load_json(path.read_text(encoding="utf-8")), allowed)
    if route.document_sha256 != path.stem:
        raise Unreadable(f"names {route.document_sha256[:12]}, filed as {path.stem[:12]}")
    return route


# the order a document's word is chosen in when its pages differ: the most consequential wins
_PRECEDENCE = ("superseded", "loaded", "human_held", "unchanged")


def route_document(con, route: Route, now: str | None = None) -> str:
    """One document's verdicts into `page_route`; the CALLER holds the transaction. Returns
    the word `store.batches.run` counts: loaded, superseded, unchanged, human_held, stale,
    omits_live_pages, no_verdicts, or unknown_document. Raises `Unreadable` for a document the
    store must refuse whole."""
    now = now or utcnow()
    sha = route.document_sha256
    if con.execute("SELECT 1 FROM document WHERE document_sha256 = ?", (sha,)).fetchone() is None:
        return "unknown_document"
    if not route.pages:
        # nothing to write and nothing to check a page count against: said, not passed over
        return "no_verdicts"
    count = con.execute(
        "SELECT page_count FROM document_pagination"
        " WHERE document_sha256 = ? AND superseded_by IS NULL",
        (sha,),
    ).fetchone()
    if count is None or count[0] is None:
        raise Unreadable("the document has no live paginated page count to check pages against")
    # EVERY page the file names, errored ones included (Copilot, PR #36): a page above the live
    # count is a route for bytes that are not the bytes paginated whether the router read it or
    # not, and an errored page writes no row to catch it later.
    named = [p.page_no for p in route.pages] + list(route.errored)
    above = sorted(no for no in named if no > count[0])
    if above:
        raise Unreadable(f"page {above[0]} is above the document's live page count {count[0]}")
    live = {
        r[0]: r[1:]
        for r in con.execute(
            "SELECT page_no, route_id, route_class, method, method_version, render_profile,"
            " routed_at, confidence_state FROM page_route"
            " WHERE document_sha256 = ? AND superseded_by IS NULL",
            (sha,),
        )
    }
    verdict = (route.method, route.method_version, route.render_profile)
    plan: list[tuple[PageVerdict, str, int | None]] = []
    for page in route.pages:
        row = live.get(page.page_no)
        if row is None:
            plan.append((page, "loaded", None))
            continue
        route_id, cls, method, version, render, routed_at, state = row
        if state == "human":
            plan.append((page, "human_held", None))
        elif (cls, method, version, render) == (page.route_class, *verdict):
            plan.append((page, "unchanged", None))
        elif route.routed_at <= routed_at:
            return "stale"  # an older file's differing verdict: nothing of it is written
        else:
            plan.append((page, "superseded", route_id))
    for page, outcome, old_id in plan:
        if outcome not in ("loaded", "superseded"):
            continue
        if old_id is not None:
            supersede.retire(con, "page_route", "route_id", old_id, at=now)
        cur = con.execute(
            "INSERT INTO page_route (document_sha256, page_no, route_class, method,"
            " method_version, render_profile, region_count, confidence, confidence_state,"
            " routed_at, asserted_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'unmeasured', ?, ?)",
            (
                sha,
                page.page_no,
                page.route_class,
                *verdict,
                page.region_count,
                route.routed_at,
                now,
            ),
        )
        if old_id is not None:
            repoint = "UPDATE page_route SET superseded_by = ? WHERE route_id = ?"
            con.execute(repoint, (cur.lastrowid, old_id))
    # A file's SILENCE about a live page retires nothing — the verdict stands until another
    # names it — but it is counted, so a partial root is visible in the pass's own totals.
    if set(live) - {p.page_no for p in route.pages}:
        return "omits_live_pages"
    seen = {outcome for _, outcome, _ in plan}
    return next((word for word in _PRECEDENCE if word in seen), "unchanged")


def run(con, root: Path, *, log=print, commit_every: int = batches.COMMIT_EVERY) -> Counter:
    """The pass over a route root, through `store.batches`: one key per `route_document`
    outcome, plus `unreadable`, `failed` and `aborted`, and `route_error_pages` — pages the
    router failed on, in the files read. Counted at READ, which happens once per file: a batch
    replayed after a lock re-applies the items it holds and does not re-read them."""
    allowed = classes(con)
    errors = Counter()

    def read(path: Path) -> Route:
        got = read_file(path, allowed)
        errors["route_error_pages"] += len(got.errored)
        return got

    totals = batches.run(
        con,
        batches.walk(root, read),
        lambda route: route_document(con, route),
        log=log,
        commit_every=commit_every,
    )
    if errors["route_error_pages"]:
        totals["route_error_pages"] = errors["route_error_pages"]
    return totals
