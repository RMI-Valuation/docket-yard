"""schema.org JSON-LD, at the site level only (docs/machine-surface.md, decided 2026-09-10).

Three blocks and no more: `WebSite` with its `SearchAction` on the home page, `Dataset` on
`/data` for the CC0 snapshot (what Dataset Search indexes), and `BreadcrumbList` on a docket
sheet. Each is built by its route from the same objects the route hands the template, so a
block cannot say something its page does not.

No record-level and no party-level type, by decision: schema.org has no type for an agency
proceeding, a filing or a decision, and `Organization`/`Person` on a party page would publish
the classification the party-types sheet has not yet measured (`docs/party-types.md`).
Widening is a later decision, not an edit here.

`base.html` renders a block through Jinja's `tojson`, which escapes `<`, `>`, `&` and `'`:
a manifest's prose and a docket's printed form reach a `<script>` element, and `</script>`
inside one would end it.
"""

from docketyard.ingest.dockets import ParsedDocket
from docketyard.store import dump
from docketyard.web import urls

CONTEXT = "https://schema.org"
BOARD_SEARCH = "https://www.stb.gov/proceedings-actions/search-stb-records/"


def website(site_name: str, site_host: str) -> dict:
    """The home page's block: the site and the one search box it has."""
    root = f"https://{site_host}/"
    return {
        "@context": CONTEXT,
        "@type": "WebSite",
        "name": site_name,
        "url": root,
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{root}search?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def dataset(manifest: dump.Manifest, site_name: str, site_host: str) -> dict:
    """`/data`'s block, from the manifest the page itself prints — the counts are measured
    from the snapshot file, and the held layer is named in the manifest's own words, so the
    block and the page cannot disagree about what the file holds."""
    root = f"https://{site_host}"
    c, latest = manifest.counts, manifest.latest
    return {
        "@context": CONTEXT,
        "@type": "Dataset",
        "name": f"{site_name}: the raw index of Surface Transportation Board proceedings",
        "description": (
            f"Every docket, filing, decision, date and document hash {site_name} holds about"
            " proceedings before the U.S. Surface Transportation Board, with its provenance,"
            f" as one SQLite file cut nightly: {c['dockets']:,} dockets, {c['filings']:,}"
            f" filings, {c['decisions']:,} decisions and {c['events']:,} ledger events."
            " The Board's own file remains the authority for every record."
            f" {manifest.held_reason}"
        ),
        "url": f"{root}/data",
        "license": manifest.licence_url,
        "isAccessibleForFree": True,
        "isBasedOn": BOARD_SEARCH,
        "dateModified": manifest.built_at,
        "distribution": [
            {
                "@type": "DataDownload",
                "name": latest.name,
                "contentUrl": f"{root}/data/files/{latest.name}",
                "encodingFormat": "application/gzip",
                "contentSize": f"{latest.bytes / 1e6:.1f} MB",
                "sha256": latest.sha256,
            }
        ],
    }


def sheet_trail(
    identity: ParsedDocket, *, in_series: bool, prefix_listed: bool
) -> list[tuple[str, str]]:
    """The way up from a docket sheet, as (name, path), to the sheet itself.

    Every level is a page that answers: the prefix's list only when the registry lists that
    prefix (a sheet can exist for a docket the dockets table never showed), and the number
    above only where the sheet itself links it — the same `series`-and-`parent()` test
    `sheet.html` uses, so the trail is never a way up the page does not offer."""
    trail = [("Dockets", "/dockets")]
    if prefix_listed:
        trail.append((identity.prefix, f"/dockets/{identity.prefix}"))
    parent = identity.parent() if in_series else None
    if parent is not None:
        trail.append((urls.printed_docket(parent), urls.docket_path(parent)))
    trail.append((urls.printed_docket(identity), urls.docket_path(identity)))
    return trail


def breadcrumbs(site_host: str, trail: list[tuple[str, str]]) -> dict:
    return {
        "@context": CONTEXT,
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": f"https://{site_host}{path}"}
            for i, (name, path) in enumerate(trail, 1)
        ],
    }
