"""The operator's seed: names, marks and successions the record cannot learn from "Filed
For" cells alone. Every row loads with method 'human' and this file's version as the
method version, so a later model pass can never supersede it and its git history is the
audit trail. Effective dates are set only where a Board decision is cited; otherwise the
relationship is asserted without a date and the note says what would supply one.

Reviewed by the operator before shipping (docs/party-module.md). Facts here are corporate
structure as generally known in the industry; anything doubtful is left out rather than
guessed, and a wrong row is corrected by a `correction` and a superseding row, never an
edit in place.
"""

SEED_VERSION = "seed-2026-08-26.1"

# (legal name, [other names as (kind, name)], note)
PARTIES: list[tuple[str, list[tuple[str, str]], str]] = [
    # --- Class I carriers and their holding companies -------------------------------
    (
        "BNSF Railway Company",
        [("mark", "BNSF"), ("display", "BNSF Railway"), ("colloquial", "BNSF Railway")],
        "Class I",
    ),
    ("Burlington Northern Santa Fe, LLC", [], "holding company of BNSF Railway Company"),
    (
        "Union Pacific Railroad Company",
        [("mark", "UP"), ("display", "Union Pacific"), ("colloquial", "Union Pacific Railroad")],
        "Class I",
    ),
    ("Union Pacific Corporation", [], "holding company of Union Pacific Railroad Company"),
    (
        "CSX Transportation, Inc.",
        [("mark", "CSXT"), ("display", "CSX Transportation"), ("colloquial", "CSXT")],
        "Class I",
    ),
    ("CSX Corporation", [("mark", "CSX")], "holding company of CSX Transportation, Inc."),
    (
        "Norfolk Southern Railway Company",
        [
            ("mark", "NS"),
            ("display", "Norfolk Southern"),
            ("colloquial", "Norfolk Southern Railway"),
        ],
        "Class I",
    ),
    ("Norfolk Southern Corporation", [], "holding company of Norfolk Southern Railway Company"),
    (
        "Canadian Pacific Kansas City Limited",
        [("mark", "CPKC"), ("colloquial", "CPKC"), ("display", "CPKC")],
        "Class I; formerly Canadian Pacific Railway Limited",
    ),
    ("Canadian Pacific Railway Company", [("mark", "CP")], "the CP operating company"),
    ("Kansas City Southern", [("mark", "KCS")], "holding company; merged into CPKC (FD 36500)"),
    (
        "The Kansas City Southern Railway Company",
        [("mark", "KCSR"), ("display", "Kansas City Southern Railway")],
        "KCS US operating company",
    ),
    ("Soo Line Railroad Company", [("mark", "SOO")], "CP's US operating subsidiary"),
    ("Canadian National Railway Company", [("mark", "CN"), ("display", "CN")], "Class I"),
    ("Grand Trunk Corporation", [], "CN's US holding company"),
    ("Illinois Central Railroad Company", [("mark", "IC")], "CN US subsidiary"),
    ("Grand Trunk Western Railroad Company", [("mark", "GTW")], "CN US subsidiary"),
    ("Wisconsin Central Ltd.", [("mark", "WC")], "CN US subsidiary"),
    # --- passenger ------------------------------------------------------------------
    (
        "National Railroad Passenger Corporation",
        [("mark", "AMTK"), ("colloquial", "Amtrak"), ("display", "Amtrak")],
        "intercity passenger",
    ),
    (
        "Northeast Illinois Regional Commuter Railroad Corporation",
        [("colloquial", "Metra"), ("display", "Metra")],
        "commuter, Chicago",
    ),
    ("New Jersey Transit Corporation", [("colloquial", "NJ Transit")], "commuter"),
    (
        "Southeastern Pennsylvania Transportation Authority",
        [("mark", "SEPTA"), ("display", "SEPTA")],
        "commuter",
    ),
    (
        "Massachusetts Bay Transportation Authority",
        [("mark", "MBTA"), ("display", "MBTA")],
        "commuter",
    ),
    ("Metro-North Commuter Railroad Company", [("colloquial", "Metro-North")], "commuter"),
    ("The Long Island Rail Road Company", [("mark", "LIRR"), ("display", "LIRR")], "commuter"),
    (
        "Southern California Regional Rail Authority",
        [("colloquial", "Metrolink"), ("mark", "SCRRA")],
        "commuter",
    ),
    ("Peninsula Corridor Joint Powers Board", [("colloquial", "Caltrain")], "commuter"),
    (
        "Virginia Railway Express",
        [("mark", "VRE")],
        "commuter; a joint powers commission",
    ),
    ("Maryland Transit Administration", [("mark", "MTA"), ("colloquial", "MARC")], "commuter"),
    ("Utah Transit Authority", [("mark", "UTA"), ("colloquial", "FrontRunner")], "commuter"),
    (
        "Central Puget Sound Regional Transit Authority",
        [("colloquial", "Sound Transit")],
        "commuter",
    ),
    # --- short-line and regional holding companies ------------------------------------
    ("Genesee & Wyoming Inc.", [("mark", "GWI"), ("display", "Genesee & Wyoming")], "holding"),
    ("Watco Companies, L.L.C.", [("display", "Watco")], "holding"),
    ("OmniTRAX, Inc.", [("display", "OmniTRAX")], "holding"),
    ("Patriot Rail Company LLC", [("display", "Patriot Rail")], "holding"),
    ("Anacostia Rail Holdings Company", [("display", "Anacostia Rail Holdings")], "holding"),
    ("Railroad Development Corporation", [("mark", "RDC")], "holding"),
    ("Iowa Interstate Railroad, Ltd.", [("mark", "IAIS")], "RDC subsidiary"),
    ("R.J. Corman Railroad Group, LLC", [("display", "R.J. Corman")], "holding"),
    ("Pinsly Railroad Company", [], "holding"),
    ("Progressive Rail Incorporated", [("display", "Progressive Rail")], "holding"),
    ("Jaguar Transport Holdings, LLC", [("display", "Jaguar Transport")], "holding"),
    ("Gulf & Ohio Railways, Inc.", [("display", "Gulf & Ohio Railways")], "holding"),
    ("Regional Rail, LLC", [("display", "Regional Rail")], "holding"),
    ("Carload Express, Inc.", [("display", "Carload Express")], "holding"),
    ("Rio Grande Pacific Corporation", [("display", "Rio Grande Pacific")], "holding"),
    # --- names with 'and' in them that the split rules cannot vouch for alone -----------
    ("Norfolk and Portsmouth Belt Line Railroad Company", [("mark", "NPBL")], "switching"),
    ("Brotherhood of Locomotive Engineers and Trainmen", [("mark", "BLET")], "union"),
    ("The National Grain and Feed Association", [("mark", "NGFA")], "association"),
    # --- the agency and the associations that file often -------------------------------
    ("Surface Transportation Board", [("mark", "STB"), ("display", "the Board")], "agency"),
    ("Association of American Railroads", [("mark", "AAR")], "association"),
    (
        "American Short Line and Regional Railroad Association",
        [("mark", "ASLRRA")],
        "association",
    ),
]

# (from legal name, rel_type, to legal name, effective_date or None, note)
RELATIONSHIPS: list[tuple[str, str, str, str | None, str]] = [
    ("Burlington Northern Santa Fe, LLC", "parent_of", "BNSF Railway Company", None, ""),
    ("Union Pacific Corporation", "parent_of", "Union Pacific Railroad Company", None, ""),
    ("CSX Corporation", "parent_of", "CSX Transportation, Inc.", None, ""),
    ("Norfolk Southern Corporation", "parent_of", "Norfolk Southern Railway Company", None, ""),
    (
        "Canadian Pacific Kansas City Limited",
        "parent_of",
        "Canadian Pacific Railway Company",
        None,
        "",
    ),
    (
        "Kansas City Southern",
        "merged_into",
        "Canadian Pacific Kansas City Limited",
        None,
        "STB FD 36500 (control decision); date to be quoted from that decision",
    ),
    (
        "Canadian Pacific Kansas City Limited",
        "parent_of",
        "The Kansas City Southern Railway Company",
        None,
        "",
    ),
    ("Canadian Pacific Railway Company", "parent_of", "Soo Line Railroad Company", None, ""),
    ("Canadian National Railway Company", "parent_of", "Grand Trunk Corporation", None, ""),
    ("Grand Trunk Corporation", "parent_of", "Illinois Central Railroad Company", None, ""),
    ("Grand Trunk Corporation", "parent_of", "Grand Trunk Western Railroad Company", None, ""),
    ("Grand Trunk Corporation", "parent_of", "Wisconsin Central Ltd.", None, ""),
    ("Railroad Development Corporation", "parent_of", "Iowa Interstate Railroad, Ltd.", None, ""),
]

AGENCY = "Surface Transportation Board"  # shown in Parties blocks with the 'agency' label
