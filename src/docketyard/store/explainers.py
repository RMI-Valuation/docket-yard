"""Measurements for the docket-type explainers (docs/explainers.md; capability P2).

Every number an explainer page prints comes from here, on request, so the pages cannot go
stale and no figure is hand-typed. Everything is a count over the registry and the record
tables; nothing is inferred about any proceeding's merits.
"""

# ruff: noqa: E501 — the prose rows below are the reviewed draft's sentences, kept whole

from dataclasses import dataclass, field
from sqlite3 import Connection

PAGES = ("FD", "AB", "NOR", "EP", "MCF")  # the prefixes with a page of their own
LIVE = {"WB", "RR", "SO", "CU", "SDM", "DOP"}  # still receive entries; the rest are inherited
# the search form's prefixes (scraped 2026-08-26) that the record holds nothing for
EMPTY_PREFIXES = ("ARB", "ASC", "DSO", "RER", "S5A", "SUS")


# the prefixes without a page of their own: (prefix, what it is — HTML, grades). The prose is
# the reviewed draft's (docs/explainers.md); a `?` grade is a reading of the captions the
# Board's records staff have not confirmed, published so the gap is public.
OTHERS = (
    (
        "WB",
        "<strong>Waybill data requests.</strong> “The Carload Waybill Sample is a stratified sample of carload waybills for U.S. rail traffic”. WB 26 is the current series; each sub-number is one request, answered by a decision under 49 CFR 1244.9, with objections from the railroads whose data it is. Every caption reads “Request for / Release of Waybill Data”.",
        "BC",
    ),
    (
        "RR",
        "<strong>Released rates</strong> — a carrier’s request to limit its liability for loss or damage in exchange for a lower rate (49 U.S.C. §14706 for motor carriers, §10502 exemptions for rail). Household-goods movers’ released-rates orders live here; the Board “oversees tariff requirements for interstate moving companies” and refers moving disputes to FMCSA.",
        "BC",
    ),
    (
        "SO",
        "<strong>Service orders</strong> — emergency orders directing service when a carrier cannot or will not provide it (49 U.S.C. §11123): “Petition for Emergency Service Order”.",
        "CR",
    ),
    (
        "PTO",
        "<strong>Passenger train operation orders</strong> — numbered orders concerning a freight carrier’s handling of passenger trains (the captions name the Indiana Harbor Belt). Statutory basis unconfirmed (49 U.S.C. §24308 governs Amtrak’s use of freight facilities).",
        "C?",
    ),
    (
        "DOP",
        "<strong>Designated operator</strong> certificates — a carrier designated to operate a line another carrier is abandoning, under 49 CFR Part 1150 Subpart B.",
        "RC",
    ),
    (
        "SDM",
        "<strong>System diagram maps</strong> — each carrier’s mandated map of its lines by category (Category 1 = anticipated abandonment within three years), 49 CFR §1152.10–.13. One docket per carrier.",
        "RC",
    ),
    (
        "CU",
        "<strong>Paperwork Reduction Act notices</strong> — the Board’s 60- and 30-day notices seeking OMB clearance for its information collections. Not proceedings between parties.",
        "C",
    ),
    (
        "SUB",
        "<strong>Depreciation rates</strong> — “In the matter of prescribing depreciation rates for use in computing depreciation charges” for a named carrier (49 U.S.C. §11143). Suffix letters distinguish successive prescriptions.",
        "C",
    ),
    (
        "AM",
        "<strong>Administrative matters</strong> of the agency itself: “Senior Executive Service Performance Review Board”, “Implementation of the Regulatory Flexibility Act”.",
        "C",
    ),
    (
        "STA",
        "<strong>Special tariff authority</strong> for non-contiguous domestic water carriers — permission to change a tariff on short notice. The Board keeps “rate regulation of non-contiguous domestic water transportation”. The expansion of the letters is unconfirmed.",
        "BC?",
    ),
    (
        "WCC",
        "<strong>Water carrier complaints</strong> in the non-contiguous domestic trade (Hawaii, Alaska, Puerto Rico, Guam): “DHX, Inc. v. Matson Navigation Company”.",
        "BC",
    ),
    (
        "WC",
        "<strong>Water carrier</strong> authority, ICC-era: “Champion’s Auto Ferry, Inc. — Algonac, MI”.",
        "C",
    ),
    (
        "EPM",
        "<strong>Ex Parte, motor</strong> — ICC rulemakings for the trucking industry: “Review of Motor Tariff Regulations — 1993”. Closed series.",
        "C",
    ),
    (
        "MC",
        "<strong>Motor carrier operating authority</strong> — the ICC’s certificates and permits by carrier docket number (a fraction of the ICC’s ~247,000); the sub-number is the application. Live motor authority is FMCSA’s since 1996.",
        "CB",
    ),
    (
        "MCC",
        "<strong>Motor carrier complaints and declaratory orders</strong>: “AAA Cooper Transportation v. Ross Neely Express”. The Board retains a narrow motor-carrier jurisdiction (49 U.S.C. subtitle IV part B).",
        "C",
    ),
    (
        "NOM",
        "<strong>Motor carrier rate and practice petitions</strong> — overwhelmingly shippers’ <em>petitions for declaratory order</em> on “certain rates and practices” of a trucking company (the 1990s undercharge cases). Closed series.",
        "C",
    ),
    (
        "ISM",
        "<strong>Investigation and suspension, motor</strong> — ICC proceedings suspending and investigating a proposed motor tariff. Closed.",
        "CN",
    ),
    (
        "IS",
        "<strong>Investigation and suspension, rail</strong> — the same for rail tariffs: “Surcharge on Furniture, Conrail, October 1979”, “Cancellation of Reciprocal Switching”. Closed.",
        "CN",
    ),
    (
        "FSA",
        "<strong>Fourth Section applications</strong> — carriers seeking permission to charge more for a shorter haul than a longer one over the same line (the Interstate Commerce Act’s “long-and-short-haul” clause). Closed.",
        "NC",
    ),
    (
        "S5M",
        "<strong>Section 5a agreements, motor</strong> — ICC approval of rate-bureau agreements among motor carriers under §5a of the Interstate Commerce Act (antitrust immunity for collective ratemaking). Closed. The expansion of the letters is unconfirmed.",
        "C?",
    ),
    (
        "SAI",
        "<strong>Shipper agreements</strong> — approval of agreements among shippers’ associations: “American Petroleum Institute Agreement”. Statutory basis unconfirmed (49 U.S.C. §10706).",
        "C?",
    ),
    (
        "MXC",
        "<strong>Mexican carrier certificates</strong> — ICC-era operating authority for Mexico-domiciled motor carriers. Captions are personal names. Unconfirmed.",
        "C?",
    ),
    ("CNO", "Captioned “Classification” — a single ICC-era docket; meaning unconfirmed.", "?"),
)


@dataclass
class PrefixFacts:
    prefix: str
    dockets: int = 0
    subs: int = 0  # dockets that are sub-numbers
    seq_min: int = 0  # 0 when the record holds none of the prefix
    seq_max: int = 0
    filings: int = 0
    decisions: dict[str, int] = field(default_factory=dict)  # decision type -> count
    filing_types: dict[str, int] = field(default_factory=dict)  # filing type -> count

    @property
    def top_filing_types(self) -> list[tuple[str, int]]:
        return sorted(self.filing_types.items(), key=lambda kv: (-kv[1], kv[0]))[:5]

    def decision_count(self, kind: str) -> int:
        return sum(n for t, n in self.decisions.items() if t.lower() == kind.lower())

    def filings_like(self, needle: str) -> int:
        needle = needle.lower()
        return sum(n for t, n in self.filing_types.items() if needle in t.lower())


@dataclass
class Facts:
    total_dockets: int
    prefixes: dict[str, PrefixFacts]
    suffixes: list[tuple[str, str, int]]  # (suffix, prefix, dockets), most common first
    decision_types: list[tuple[str, int]]  # across the record, most common first

    def prefix(self, p: str) -> PrefixFacts:
        return self.prefixes.get(p) or PrefixFacts(p)

    def suffix_count(self, suffix: str, prefix: str | None = None) -> int:
        return sum(
            n for s, p, n in self.suffixes if s == suffix and (prefix is None or p == prefix)
        )

    def dockets_in(self, prefixes) -> int:
        return sum(self.prefix(p).dockets for p in prefixes)


def measure(con: Connection) -> Facts:
    q = con.execute
    prefixes: dict[str, PrefixFacts] = {}
    for prefix, n, subs, lo, hi in q(
        "SELECT prefix, COUNT(*), SUM(sub_sequence IS NOT NULL), MIN(sequence), MAX(sequence)"
        " FROM docket GROUP BY prefix"
    ):
        prefixes[prefix] = PrefixFacts(prefix, n, subs or 0, lo or 0, hi or 0)
    for prefix, ftype, n in q(
        "SELECT d.prefix, COALESCE(f.filing_type, ''), COUNT(DISTINCT f.stb_filing_id)"
        " FROM filing f JOIN docket d ON d.docket_id = f.docket_id GROUP BY 1, 2"
    ):
        pf = prefixes.setdefault(prefix, PrefixFacts(prefix))
        pf.filing_types[ftype] = n
        pf.filings += n
    for prefix, dtype, n in q(
        "SELECT d.prefix, COALESCE(r.decision_type, ''), COUNT(DISTINCT r.stb_decision_id)"
        " FROM decision_record r JOIN docket d ON d.docket_id = r.docket_id GROUP BY 1, 2"
    ):
        prefixes.setdefault(prefix, PrefixFacts(prefix)).decisions[dtype] = n
    suffixes = [
        (s, p, n)
        for s, p, n in q(
            "SELECT suffix, prefix, COUNT(*) FROM docket WHERE suffix IS NOT NULL"
            " GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2"
        )
    ]
    decision_types = [
        (t, n)
        for t, n in q(
            "SELECT COALESCE(decision_type, ''), COUNT(DISTINCT stb_decision_id)"
            " FROM decision_record GROUP BY 1 ORDER BY 2 DESC, 1"
        )
    ]
    return Facts(
        total_dockets=q("SELECT COUNT(*) FROM docket").fetchone()[0],
        prefixes=prefixes,
        suffixes=suffixes,
        decision_types=decision_types,
    )
