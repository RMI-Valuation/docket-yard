"""The party module: splitting rules on the measured cell shapes, exact resolution with
minting and ambiguity, supersession on a changed cell, and the same_as component."""

from docketyard.parties import names, resolve, seed
from docketyard.store import db


def spans(cell, known=frozenset()):
    return [(s.text, s.role, s.confidence) for s in names.split_cell(cell, set(known))]


def test_single_names_are_one_span():
    assert spans("CSX Transportation, Inc.") == [("CSX Transportation, Inc.", "filed_for", 1.0)]
    assert spans("Kansas & Oklahoma Railroad, LLC") == [
        ("Kansas & Oklahoma Railroad, LLC", "filed_for", 1.0)
    ]
    assert spans("James Riffin") == [("James Riffin", "filed_for", 1.0)]


def test_parent_and_subsidiary_cut_on_and():
    assert spans("Norfolk Southern Corporation and Norfolk Southern Railway Company") == [
        ("Norfolk Southern Corporation", "filed_for", 1.0),
        ("Norfolk Southern Railway Company", "filed_for", 1.0),
    ]


def test_two_pairs_joined_by_a_comma():
    cell = (
        "Union Pacific Corporation and Union Pacific Railroad Company,"
        " Norfolk Southern Corporation and Norfolk Southern Railway Company"
    )
    assert [s[0] for s in spans(cell)] == [
        "Union Pacific Corporation",
        "Union Pacific Railroad Company",
        "Norfolk Southern Corporation",
        "Norfolk Southern Railway Company",
    ]


def test_on_behalf_of_is_a_relationship_not_a_second_filer():
    out = spans(
        "Grand Trunk Corporation, on behalf of itself and its U.S. rail operating subsidiaries"
    )
    assert out[0] == ("Grand Trunk Corporation", "filed_for", 1.0)
    assert out[1][1] == "on_behalf_of" and "subsidiaries" in out[1][0]


def test_repeat_is_folded_and_uncuttable_stays_whole_with_doubt():
    assert spans("Ohio Rail Development Commission, Ohio Rail Development Commission") == [
        ("Ohio Rail Development Commission", "filed_for", 1.0)
    ]
    out = spans("Smith and Jones")  # no suffixes, unknown names: one doubtful span
    assert len(out) == 1 and out[0][2] < 1.0
    out = spans("Alpha Grain, Beta Feed")  # a comma the rules cannot vouch for
    assert len(out) == 1 and out[0][2] < 1.0


def test_known_names_let_a_cut_happen_without_suffixes():
    known = {names.normalise("CPKC"), names.normalise("Weskan Grain LLC")}
    assert [s[0] for s in spans("CPKC and Weskan Grain LLC", known)] == ["CPKC", "Weskan Grain LLC"]


def test_normalise_and_trade_name():
    assert names.normalise("CSX Transportation, Inc.") == names.normalise("csx transportation inc")
    assert names.normalise("BNSF Railway Company") == "bnsf ry co"
    assert names.trade_name("Ethanol Products, LLC d/b/a POET Biofuels") == (
        "Ethanol Products, LLC",
        "POET Biofuels",
    )


def _store():
    con = db.connect(":memory:")
    con.execute("INSERT INTO docket (raw_docket, prefix, sequence) VALUES ('FD_1', 'FD', 1)")
    con.execute(
        "INSERT INTO capture (source_system, endpoint, request_params, response_sha256,"
        " http_status, filter_asserted, ingest_mode, captured_at, table_action)"
        " VALUES ('s', 'e', '[]', 'x', 200, 1, 'forward', 't', 'a')"
    )
    return con


def _filing(con, fid, cell):
    ev = con.execute(
        "INSERT INTO event (event_type, docket_id, recorded_at, capture_id, source_key,"
        " payload, payload_version) VALUES ('filing_observed', 1, 't', 1, ?, '{}', 1)",
        (f"FD_1|{fid}",),
    ).lastrowid
    return con.execute(
        "INSERT INTO filing (docket_id, stb_filing_id, filed_for_raw, observed_in_event)"
        " VALUES (1, ?, ?, ?)",
        (fid, cell, ev),
    ).lastrowid


def test_split_resolve_mint_and_ambiguity():
    con = _store()
    _filing(con, "1", "CSX Transportation, Inc.")
    _filing(con, "2", "CSX Transportation")  # normalises differently: a second party for now
    _filing(con, "3", "Norfolk Southern Corporation and Norfolk Southern Railway Company")
    _filing(con, "4", "Smith and Jones")  # doubtful: never minted
    _filing(con, "5", "Ethanol Products, LLC d/b/a POET Biofuels")
    out = resolve.run(con, log=lambda _: 0)
    seeded = out["seed"]["parties"]
    assert out["split"]["filings"] == 5 and out["split"]["spans"] == 6
    # CSX, NS Corp and NS Railway are seeded; 'CSX Transportation' (no Inc.) is the seed's
    # display name -> matched; Ethanol Products is minted; Smith and Jones is left
    assert out["resolve"]["minted"] == 1 and out["resolve"]["left"] == 1
    assert out["resolve"]["linked"] == 5
    assert con.execute("SELECT COUNT(*) FROM party").fetchone()[0] == seeded + 1
    trade = con.execute("SELECT raw_name FROM party_name WHERE name_kind = 'trade'").fetchone()
    assert trade == ("POET Biofuels",)
    # re-running is a no-op: every live span already has a live link
    again = resolve.run(con, log=lambda _: 0)
    assert again["split"]["filings"] == 0 and again["resolve"]["linked"] == 0
    # a same_as edge joins two parties without any UPDATE; the display name comes from the
    # whole component, whichever id is the representative
    a = con.execute(
        "SELECT party_id FROM party WHERE founding_key = ?",
        (names.normalise("CSX Transportation, Inc."),),
    ).fetchone()[0]
    b = con.execute(
        "SELECT party_id FROM party WHERE founding_key = ?",
        (names.normalise("Ethanol Products, LLC"),),
    ).fetchone()[0]
    con.execute(
        "INSERT INTO party_relationship (from_party, to_party, rel_type, method, method_version,"
        " asserted_at, confidence) VALUES (?, ?, 'same_as', 'human', 'test', 't', 1.0)",
        (b, a),
    )
    assert resolve.component_of(con, a) == resolve.component_of(con, b) == min(a, b)
    assert resolve.display_name(con, b) == "CSX Transportation"  # the seed's display name
    # a name shared by two components is ambiguous: no link, no mint
    con.execute("INSERT INTO party (founding_key, created_at) VALUES ('other', 't')")
    other = con.execute("SELECT MAX(party_id) FROM party").fetchone()[0]
    resolve.add_name(con, other, "Norfolk Southern Corporation", "as_filed", None, None, "t")
    _filing(con, "6", "Norfolk Southern Corporation")
    out = resolve.run(con, log=lambda _: 0)
    assert out["resolve"]["ambiguous"] == 1 and out["resolve"]["linked"] == 0


def test_a_mark_minted_before_the_seed_is_joined_not_duplicated():
    con = _store()
    _filing(con, "1", "BNSF")
    resolve.split_pending(con, log=lambda _: 0)
    resolve.resolve_pending(con, log=lambda _: 0)  # minted 'BNSF' as its own party
    out = resolve.load_seed(con, log=lambda _: 0)
    assert out["joined"] >= 1
    _filing(con, "2", "BNSF")
    out = resolve.run(con, log=lambda _: 0)
    assert out["resolve"]["ambiguous"] == 0 and out["resolve"]["linked"] == 1
    assert len({p["name"] for p in resolve.parties_in(con, [1])}) == 1
    assert resolve.parties_in(con, [1])[0]["name"] == "BNSF Railway"


def test_a_doubtful_cut_is_retried_when_its_names_become_known():
    con = _store()
    _filing(con, "1", "Weskan Grain LLC and Delta Southern")
    resolve.run(con, log=lambda _: 0)
    assert con.execute("SELECT COUNT(*) FROM filing_party_link").fetchone()[0] == 0
    _filing(con, "2", "Delta Southern")  # now on record: the earlier cell can be cut
    out = resolve.run(con, log=lambda _: 0)
    assert out["split"]["superseded"] == 1 and out["split"]["spans"] >= 2


def test_a_changed_cell_supersedes_its_spans():
    con = _store()
    pk = _filing(con, "1", "Weskan Grain LLC")
    resolve.run(con, log=lambda _: 0)
    con.execute(
        "UPDATE filing SET filed_for_raw = 'Weskan Grain LLC and Delta Southern Railroad, Inc.'"
        " WHERE filing_pk = ?",
        (pk,),
    )
    con.commit()
    out = resolve.run(con, log=lambda _: 0)
    assert out["split"]["superseded"] == 1 and out["split"]["spans"] == 2
    live = con.execute(
        "SELECT span_text FROM filing_party_span WHERE superseded_by IS NULL ORDER BY ordinal"
    ).fetchall()
    assert live == [("Weskan Grain LLC",), ("Delta Southern Railroad, Inc.",)]
    assert con.execute("SELECT COUNT(*) FROM filing_party_span").fetchone()[0] == 3  # history kept


def test_rules_measured_on_the_record():
    # a name with 'and' inside it is doubt until it is on record (the seed carries these);
    # a person plus a carrier must never be minted as one party
    assert spans("Norfolk and Portsmouth Belt Line Railroad Company")[0][2] < 1.0
    known = {names.normalise("Norfolk and Portsmouth Belt Line Railroad Company")}
    assert spans("Norfolk and Portsmouth Belt Line Railroad Company", known)[0][2] == 1.0
    assert spans("John Doe and Norfolk Southern Railway Company")[0][2] < 1.0
    # Oxford commas and semicolons are list separators
    assert [
        s[0] for s in spans("Evergy, Inc., Evergy Metro, Inc., and Evergy Kansas Central, Inc.")
    ] == [
        "Evergy, Inc.",
        "Evergy Metro, Inc.",
        "Evergy Kansas Central, Inc.",
    ]
    assert [
        s[0]
        for s in spans(
            "Sills Road Realty LLC; Brookhaven Terminal Operations, LLC;"
            " and Spectrum RR Holdings LLC"
        )
    ] == [
        "Sills Road Realty LLC",
        "Brookhaven Terminal Operations, LLC",
        "Spectrum RR Holdings LLC",
    ]
    # a person's name in a list is still doubt: we do not cut what we cannot vouch for
    assert len(spans("Colby Nitterhouse, NPJ Rail, LLC, PNGT Rail, LLC, and WCN Rail, LLC")) == 1


def test_seed_loads_idempotently_and_marks_are_matchable():
    con = _store()
    first = resolve.load_seed(con, log=lambda _: 0)
    assert first["parties"] > 40 and first["relationships"] >= 12
    again = resolve.load_seed(con, log=lambda _: 0)
    assert again == {"parties": 0, "names": 0, "relationships": 0, "joined": 0}
    # a bare mark in a cell resolves to the seeded carrier, with the seed's provenance
    _filing(con, "1", "BNSF")
    _filing(con, "2", "Surface Transportation Board")
    resolve.run(con, log=lambda _: 0)
    assert (
        resolve.display_name(
            con,
            con.execute(
                "SELECT party_id FROM party WHERE founding_key = ?",
                (names.normalise("BNSF Railway Company"),),
            ).fetchone()[0],
        )
        == "BNSF Railway"
    )
    block = resolve.parties_in(con, [1])
    assert {p["name"] for p in block} == {"BNSF Railway", "the Board"}
    assert next(p for p in block if p["name"] == "the Board")["agency"]
    assert con.execute(
        "SELECT method, method_version FROM party_name WHERE raw_name = 'BNSF'"
    ).fetchone() == ("human", seed.SEED_VERSION)


def test_sheet_and_parties_view(tmp_path):
    from fastapi.testclient import TestClient

    from docketyard.web.app import create_app
    from tests.test_web import build_store

    path = build_store(tmp_path)
    con = db.connect(path)
    resolve.run(con, log=lambda _: 0)
    con.close()
    client = TestClient(create_app(path))
    r = client.get("/d/FD-36873")
    assert "Parties on record" in r.text and 'data-party="' in r.text
    assert "NRDC" in r.text and 'data-parties="' in r.text
    r = client.get("/parties", params={"name": "nrdc"})
    assert r.status_code == 200 and "FD 36873" in r.text and "resolve-exact 1" in r.text
    assert "never a citation" in r.text
    assert "No party on record" in client.get("/parties", params={"name": "%_%"}).text
    assert "No party on record" in client.get("/parties", params={"name": "zzz"}).text
