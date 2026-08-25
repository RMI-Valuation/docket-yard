"""HTTP client for the STB record-search AJAX endpoint.

Everything here follows docs/stb-data-source.md. The traps this module answers:
- criteria MUST be sent as search-criteria[i][name]/[value] pairs (plain fields are
  silently ignored and return the full unfiltered set with a 200);
- the nonce rotates and is scraped per run;
- the endpoint 403s User-Agents without a Mozilla/5.0 prefix (measured 2026-08-25), so the
  UA is the compatible-bot form — WAF-acceptable and still honestly identified.
"""

import re
import time
import urllib.error
import urllib.parse
import urllib.request

from docketyard import __version__

SEARCH_PAGE = "https://www.stb.gov/proceedings-actions/search-stb-records/"
AJAX = "https://www.stb.gov/wp-admin/admin-ajax.php"
USER_AGENT = f"Mozilla/5.0 (compatible; DocketYard/{__version__}; +https://docketyard.org)"

DOCKETS = "stb_hook_table_dockets"
FILINGS = "stb_hook_table_filings"
DECISIONS = "stb_hook_table_decisions"

# 10,000 in `total` is a display cap, not a count (docs/stb-data-source.md). The single
# definition — ingest imports it rather than re-declaring the number.
DISPLAY_CAP = 10_000

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
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    raise RuntimeError(
                        "STB endpoint returned 403 — the WAF likely changed its User-Agent"
                        " rules; see docs/stb-data-source.md"
                    ) from e
                if e.code in (429, 500, 502, 503, 504):
                    last_error = e
                    time.sleep(self.min_interval * (2**attempt))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as e:
                # transient transport failures (DNS, reset, read timeout) retry like 5xx
                last_error = e
                time.sleep(self.min_interval * (2**attempt))
                continue
        raise RuntimeError(f"STB endpoint failed after retries: {last_error}") from last_error

    def get_nonces(self) -> dict[str, str]:
        if not self._nonces:
            _, body = self._request(SEARCH_PAGE)
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
