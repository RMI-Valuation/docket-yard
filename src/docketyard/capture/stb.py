"""HTTP client for the STB record-search AJAX endpoint.

Everything here follows docs/stb-data-source.md. The traps this module answers:
- criteria MUST be sent as search-criteria[i][name]/[value] pairs (plain fields are
  silently ignored and return the full unfiltered set with a 200);
- the nonce rotates and is scraped per run;
- the endpoint 403s User-Agents without a Mozilla/5.0 prefix (measured 2026-08-25), so the
  UA is the compatible-bot form — WAF-acceptable and still honestly identified.
"""

import http.client
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from docketyard import __version__
from docketyard.capture import records

SEARCH_PAGE = "https://www.stb.gov/proceedings-actions/search-stb-records/"
AJAX = "https://www.stb.gov/wp-admin/admin-ajax.php"
USER_AGENT = f"Mozilla/5.0 (compatible; DocketYard/{__version__}; +https://docketyard.org)"

DOCKETS = "stb_hook_table_dockets"
FILINGS = "stb_hook_table_filings"
DECISIONS = "stb_hook_table_decisions"
ENVIRO_COMMENTS = "stb_hook_table_environmental_comments"

# 10,000 in `total` is a display cap, not a count (docs/stb-data-source.md). The single
# definition — ingest imports it rather than re-declaring the number.
DISPLAY_CAP = 10_000
# per-page is clamped server-side (measured 2026-08-25): a page shorter than this is the last
PAGE_CLAMP = 50
CHUNK = records.CHUNK  # bytes per read when a document is streamed to disk

# What `_wire_url` leaves alone: the printable ASCII bytes EXCEPT the space. `%` is in the
# range, so escapes already in a stored URL are not doubled. The space is deliberately out:
# http.client rejects one in the request line as a control character (InvalidURL), which is
# the same never-fetchable failure the function exists to close.
_WIRE_SAFE = "".join(map(chr, range(0x21, 0x7F)))

# The stable sort per table. The default order is NOT repeatable (measured), so every
# multi-page walk pins one of these. Dockets ascend so a walk is resumable by inspection;
# filings/decisions descend so forward polling sees the newest first.
#
# ENVIRO_COMMENTS is the exception, and its empty string is a MEASURED VALUE, not a default
# left unset (2026-08-31). That table accepts no sort at all: every candidate key tried —
# date, receivedDate, dateReceived, receivedOrSentDate, commentDate, receivedSentDate,
# dateReceivedOrSent, commentNum — answers the empty "There are no environmental comments
# available" envelope with a 200, the same silent-failure shape as the criteria format and
# the two wrong date pairs. `sort_order` is echoed back ("…Asc.") and then ignored: asc and
# desc return identical rows, newest first. Paging it is safe anyway, which was measured
# rather than assumed — 151 rows over four pages carried 151 distinct data-stb-ids, no
# overlap and no omission. Do not "fix" this by supplying a sort key: that silently
# empties the walk.
TABLE_SORT = {
    DOCKETS: ("docketNum", "asc"),
    FILINGS: ("officialFilingDate", "desc"),
    DECISIONS: ("serviceDate", "desc"),
    ENVIRO_COMMENTS: ("", "desc"),
}

# The 34 prefixes the search form offers (census 2026-08-25; none reaches the display cap).
DOCKET_PREFIXES = (
    "AB AM ARB ASC CNO CU DOP DSO EP EPM FD FSA IS ISM MC MCC MCF MXC NOM NOR PTO RER RR"
    " S5A S5M SAI SDM SO STA SUB SUS WB WC WCC"
).split()
# The census found these empty. A no-results envelope on any OTHER prefix is the trap (wrong
# criteria, expired nonce, renamed sort key), never a benign empty slice.
EXPECTED_EMPTY_PREFIXES = frozenset("ARB ASC DSO RER S5A SUS".split())

# Attributes are matched per-tag and independently, so attribute order, spacing, and
# unrelated attributes between them cannot break the scrape.
_STB_TAG_RE = re.compile(r"<[^>]*data-stb-action=[^>]*>")
_ACTION_ATTR_RE = re.compile(r'data-stb-action="(stb_hook_table_\w+)"')
_NONCE_ATTR_RE = re.compile(r'data-stb-nonce="([0-9a-fA-F]+)"')

Criteria = list[tuple[str, str]]


def parse_nonces(page_html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in _STB_TAG_RE.findall(page_html):
        action = _ACTION_ATTR_RE.search(tag)
        nonce = _NONCE_ATTR_RE.search(tag)
        if action and nonce:
            out[action.group(1)] = nonce.group(1)
    return out


def build_fields(
    action: str,
    nonce: str,
    criteria: Criteria,
    *,
    page: int,
    per_page: int,
    sort_by: str = "",
    sort_order: str = "desc",
) -> list[tuple[str, str]]:
    fields = [
        ("_ajax_nonce", nonce),
        ("action", action),
        ("page", str(page)),
        ("per-page", str(per_page)),
        ("sort_by", sort_by),
        ("sort_order", sort_order),
    ]
    for i, (name, value) in enumerate(criteria):
        fields.append((f"search-criteria[{i}][name]", name))
        fields.append((f"search-criteria[{i}][value]", value))
    return fields


def _wire_url(url: str) -> str:
    """The request-line form of a stored URL.

    The Board's tables hand back the document URL as it was typed, and three comment
    attachments carry a raw en dash (U+2013) in the file name — the only non-ASCII
    characters in the production store's 110,110 attachment rows, counted there
    2026-09-02T01:40Z. urllib puts the request line on the wire as ASCII, so such a URL
    raises UnicodeEncodeError before a byte is sent; a raw space, the likelier as-typed
    defect, raises InvalidURL a moment later. Either way the fetch fails locally, forever,
    and no capture is recorded to rest it — which is why the drain could not reach zero.
    Percent-encoding those bytes (as UTF-8, which is what the bucket's keys are) fetches
    them: verified 200 and PDF bytes on all three, 2026-09-02.

    Only the wire form is rewritten. The stored URL stays verbatim, so it remains the key
    that groups attachment rows and finds errata; identity is untouched.

    The netloc is quoted along with the path, which is a no-op on every host that exists
    (measured 2026-09-02: 110,107 rows on dcms-external.s3.amazonaws.com and 3 on
    dcms-external.s3.us-east-1.amazonaws.com, both ASCII). A non-ASCII host would need
    IDNA, and percent-encoding it would give an unresolvable name — so do not reuse this
    on a host that arrives from data without splitting the parts first.
    """
    return urllib.parse.quote(url, safe=_WIRE_SAFE)


class StbClient:
    """Rate-limited client. One instance per run; nonces are cached per instance only."""

    def __init__(self, min_interval: float = 2.0, timeout: float = 90.0):
        self.min_interval = min_interval
        self.timeout = timeout
        self._nonces: dict[str, str] = {}
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def _request(self, url: str, data: bytes | None = None) -> tuple[int, bytes]:
        """A table query or a small page: the whole body, in memory."""
        return self._attempt(url, data, lambda resp: (resp.status, resp.read()))

    def download(self, url: str, into: str | Path) -> tuple[int, Path]:
        """A document: streamed in CHUNK-sized reads to a temporary file under `into`
        (the blob store's own filesystem, so the caller renames it into place). Nothing
        larger than one chunk is ever held in memory — the record holds a 1.07 GB filing
        (FD 36500's application, 303143.pdf), and `resp.read()` of it took the process
        past a 2 GB box's memory (measured 2026-08-26). The file is the caller's to
        consume or delete; a failed attempt leaves nothing behind, and what a killed
        process leaves is swept by `records.sweep_staging` at the start of a fetch run."""
        tmp_dir = records.staging_dir(into)

        def consume(resp) -> tuple[int, Path]:
            fd, name = tempfile.mkstemp(dir=tmp_dir, prefix="dl-")
            try:
                with os.fdopen(fd, "wb") as out:
                    shutil.copyfileobj(resp, out, CHUNK)
            except BaseException:
                Path(name).unlink(missing_ok=True)
                raise
            return resp.status, Path(name)

        return self._attempt(url, None, consume, keep_refusals=True)

    def fetcher(self, data_dir: str | Path):
        """The document fetcher `documents.fetch_attachments` takes: `download` bound to
        the blob store's directory, so every caller streams and none reads whole."""
        return lambda url: self.download(url, data_dir)

    def _attempt(self, url: str, data: bytes | None, consume, *, keep_refusals: bool = False):
        """Run `consume(resp)` against a fresh response under the one retry policy: 403 is
        a hard stop with a diagnosis; 429/5xx, transport failures and a failure mid-read
        (timeout, reset, a body cut short of its Content-Length) retry with backoff,
        three attempts in all. A local failure (disk full, permissions) is not retried."""
        headers = {"User-Agent": USER_AGENT}
        if data is not None:
            headers |= {
                "Referer": SEARCH_PAGE,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
        last_error: Exception | None = None
        for attempt in range(3):
            self._throttle()
            self._last_request = time.monotonic()
            try:
                req = urllib.request.Request(_wire_url(url), data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return consume(resp)
            except urllib.error.HTTPError as e:
                host = urllib.parse.urlsplit(url).netloc
                if (
                    keep_refusals
                    and not host.endswith("stb.gov")
                    and e.code < 500
                    and e.code != 429
                ):
                    # a document host refusing one object (403 on a legacy /MPD/ path,
                    # measured 2026-08-27; a 404): the answer is the record of the attempt
                    return consume(e)
                if e.code == 403:
                    body = e.read(200).decode("utf-8", "replace").strip()
                    if body == "-1":
                        why = "body `-1`: WordPress rejected the nonce (stale cached search page?)"
                    elif host.endswith("stb.gov"):
                        why = "the WAF likely changed its User-Agent rules"
                    else:
                        # a document host (the Board's S3 bucket): one object it will not
                        # serve — a legacy /MPD/ path, measured 2026-08-27 — not a rule change
                        why = "that object is not served; other fetches are unaffected"
                    raise RuntimeError(
                        f"{host} returned 403 — {why}; see docs/stb-data-source.md"
                    ) from e
                if e.code in (429, 500, 502, 503, 504):
                    last_error = e
                    time.sleep(self.min_interval * (2**attempt))
                    continue
                raise
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                http.client.HTTPException,  # IncompleteRead, RemoteDisconnected mid-body
            ) as e:
                # transient transport failures (DNS, reset, read timeout) retry like 5xx
                last_error = e
                time.sleep(self.min_interval * (2**attempt))
                continue
        raise RuntimeError(f"STB endpoint failed after retries: {last_error}") from last_error

    def get(self, url: str) -> tuple[int, bytes]:
        """Rate-limited GET of a small page, whole, in memory. Never a document: the record
        holds gigabyte filings; those go through `download` (or `fetcher`)."""
        return self._request(url)

    def refresh_nonces(self) -> dict[str, str]:
        """Re-scrape mid-run — the nonce rotates on a clock a long walk can straddle."""
        self._nonces = {}
        return self.get_nonces()

    def get_nonces(self) -> dict[str, str]:
        if not self._nonces:
            # cache-busted: stb.gov's page cache serves a stale copy of the search page whose
            # nonce no longer validates (403 with body `-1`, measured 2026-08-26 from AWS);
            # a query string the cache has not seen forces a fresh render
            _, body = self._request(f"{SEARCH_PAGE}?dy={int(time.time())}")
            self._nonces = parse_nonces(body.decode("utf-8", "replace"))
            if not self._nonces:
                raise RuntimeError("no nonces found on the search page — markup changed?")
        return self._nonces

    def query_table(
        self,
        action: str,
        criteria: Criteria,
        *,
        page: int = 1,
        per_page: int = 100,
        sort_by: str = "",
        sort_order: str = "desc",
    ) -> tuple[int, bytes, list[tuple[str, str]]]:
        """POST one page query. Returns (http_status, raw_body, fields_as_sent)."""
        nonce = self.get_nonces()[action]
        fields = build_fields(
            action, nonce, criteria,
            page=page, per_page=per_page, sort_by=sort_by, sort_order=sort_order,
        )  # fmt: skip
        body = urllib.parse.urlencode(fields).encode()
        status, raw = self._request(AJAX, data=body)
        return status, raw, fields
