"""`docketyard text load` — one reading per document into `document_text` (migration 0018).

Every test pins an obligation migration 0018's header states for the loader: the natural key,
the cross-key supersession of a primary, the page index kept in step, the payload in the
blob tier, the run row that appends — and what the review of 2026-09-03 found.
"""

import argparse
import hashlib
import json

import pytest

from docketyard import cli
from docketyard.capture import records
from docketyard.store import db
from docketyard.text import load

STAMP = "2026-09-03T00:00:00+00:00"
RAN = "2026-09-02T10:00:00+00:00"
LATER = "2026-09-03T10:00:00+00:00"
SHA_A = "a" * 64
SHA_B = "b" * 64
PRIMARY = {"method": "pymupdf", "method_version": "1.24.10", "render_profile": "native"}


def _store(tmp_path, *shas):
    con = db.connect(tmp_path / "s.sqlite")
    for sha in shas or (SHA_A, SHA_B):
        con.execute(
            "INSERT INTO document (document_sha256, size_bytes, media_type, first_seen_at)"
            " VALUES (?, 1, 'pdf', ?)",
            (sha, STAMP),
        )
    con.commit()
    return con


def _extraction(sha, pages=("abandonment in Perry County", "", "Docket No. AB 1242"), **over):
    rec = {
        "document_sha256": sha,
        "size_bytes": 1234,
        "method": "text-layer",
        "method_version": "1",
        "tool": "pymupdf",
        "tool_version": "1.24.10",
        "extracted_at": RAN,
        "pages": len(pages),
        "chars": sum(len(p) for p in pages),
        "image_only": False,
        "text_sha256": "c" * 64,
        "page_text": list(pages),
    }
    rec.update(over)
    return rec


def _ocr(sha, texts=("abandonment in Perry County",), role="primary", **over):
    doc = {
        "document_sha256": sha,
        "method": "dots.mocr",
        "method_version": "1.5",
        "render_profile": "150",
        "reading_channel": "ocr",
        "reading_role": role,
        "route": {"class": "degraded", "method": "pp-doclayoutv3", "method_version": "3.0"},
        "ran_at": RAN,
        "outcome": "read",
        "pages_failed": 0,
        "payload_kind": "dots.mocr.json",
        "engine": {"pages": [{"blocks": [t]} for t in texts]},
        "pages": [
            {"page_no": i + 1, "text": t, "member": f"engine/pages/{i}", "engine_confidence": 0.9}
            for i, t in enumerate(texts)
        ],
    }
    doc.update(over)
    return doc


def _reading(doc):
    payload = json.dumps(doc).encode()
    return (load.from_extraction if "page_text" in doc else load.from_reading)(doc, payload)


def _write(root, doc, name=None, *, tail=None):
    sha = name or doc["document_sha256"]
    shard = root / sha[:2]
    shard.mkdir(parents=True, exist_ok=True)
    body = json.dumps(doc)
    if tail is not None:
        body = body[: body.index('"page_text"')] + '"page_text": ' + tail
    (shard / f"{sha}.json").write_text(body, encoding="utf-8")
    return shard / f"{sha}.json"


def _live(con, sha):
    return con.execute(
        "SELECT page_no, method, method_version, render_profile, reading_channel,"
        " reading_role, text, payload_member FROM document_text"
        " WHERE document_sha256 = ? AND superseded_by IS NULL ORDER BY page_no, reading_role",
        (sha,),
    ).fetchall()


def _hits(con, word):
    return [r[0] for r in con.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH ?", (word,))]


def _ns(tmp_path, root):
    return argparse.Namespace(
        db=str(tmp_path / "s.sqlite"), data_dir=str(tmp_path), what="load", root=str(root)
    )


# --- the two shapes -------------------------------------------------------------------------


def test_the_extraction_record_is_the_text_layers_reading():
    """ADR 0021 D3: the text layer is a reading at channel text-layer, render native; the
    method is the TOOL. `page_text[i]` is page i+1 and the member path says so."""
    r = _reading(_extraction(SHA_A))
    h = r.header
    assert h.key == ("pymupdf", "1.24.10", "native")
    assert (h.reading_channel, h.reading_role, h.ran_at) == ("text-layer", "primary", RAN)
    assert h.payload_kind == "extract_text.json"
    payload, pages = r.body()
    assert payload and [(p.page_no, p.text, p.member) for p in pages] == [
        (1, "abandonment in Perry County", "page_text[0]"),
        (2, "", "page_text[1]"),
        (3, "Docket No. AB 1242", "page_text[2]"),
    ]
    assert pages[0].text_sha256 == hashlib.sha256(b"abandonment in Perry County").hexdigest()


def test_a_reading_is_validated_and_never_guessed():
    second = _ocr(SHA_A, role="second")
    second["pages"][0]["agreement"] = {"distance": 0.1, "method": "d", "method_version": "1"}
    for broken in (
        _ocr(SHA_A) | {"reading_role": "human"},  # the reviewer's, never a model pass's
        _ocr(SHA_A) | {"route": None},  # OCR without the class it was routed as
        _ocr(SHA_A) | {"method": "hf/dots.mocr"},  # '/' cannot be parsed back from a review key
        _ocr(SHA_A) | {"reading_channel": "text-layer"},  # text-layer at render 150
        _ocr(SHA_A, texts=("a", "b")) | {"pages": [{"page_no": 1, "text": "a", "member": "m"}] * 2},
        _ocr(SHA_A) | {"pages": [{"page_no": 0, "text": "a", "member": "m"}]},
        _ocr(SHA_A) | {"pages": [{"page_no": 1, "text": None, "member": "m"}]},
        _ocr(SHA_A) | {"pages": [{"page_no": 1, "text": "a"}]},  # no member path
        _ocr(SHA_A, texts=("\ud83d",)),  # a lone surrogate: JSON permits it, UTF-8 cannot hold it
        _ocr(SHA_A) | {"outcome": "ok"},
        _ocr(SHA_A) | {"pages_failed": -1},
        {k: v for k, v in _ocr(SHA_A).items() if k != "payload_kind"},  # the shape is not a guess
        second,  # an agreement that does not name what it was measured against
        _extraction(SHA_A) | {"page_text": "not a list"},
        _extraction("short"),
    ):
        with pytest.raises(load.Unreadable):
            _reading(broken)
    # a page's own route wins over the reading's, and a text-layer page carries none
    page = {
        "page_no": 1,
        "text": "a",
        "member": "m",
        "route": {"class": "clean", "method": "x", "method_version": "1"},
    }
    r = _reading(_ocr(SHA_A) | {"pages": [page]})
    assert r.body()[1][0].route.route_class == "clean"
    assert _reading(_extraction(SHA_A)).body()[1][0].route is None


def test_an_extraction_records_body_is_read_only_when_it_is_needed(tmp_path):
    """The restart check needs the header, which sits in the first 4 KB; the body is 2.5 GB
    across the record and is read only for a reading that is new. Here the body is not
    even JSON and the restart is still recognised."""
    con = _store(tmp_path)
    root = tmp_path / "text"
    path = _write(root, _extraction(SHA_A), tail="[" + "x" * 100_000)
    reading = load.read_file(path)
    assert reading.header.document_sha256 == SHA_A
    con.execute(
        "INSERT INTO ocr_run (document_sha256, method, method_version, reading_channel,"
        " render_profile, outcome, pages_read, ran_at)"
        " VALUES (?, 'pymupdf', '1.24.10', 'text-layer', 'native', 'read', 3, ?)",
        (SHA_A, RAN),
    )
    assert load.load_reading(con, tmp_path, reading) == "restart"
    with pytest.raises(ValueError):
        reading.body()  # and a NEW reading with that body would be counted, not raised


# --- what one reading writes ------------------------------------------------------------------


def test_a_reading_writes_one_row_per_page_the_payload_and_the_run(tmp_path):
    con = _store(tmp_path)
    r = _reading(_extraction(SHA_A))
    assert load.load_reading(con, tmp_path, r) == "loaded"
    assert _live(con, SHA_A) == [
        (
            1,
            "pymupdf",
            "1.24.10",
            "native",
            "text-layer",
            "primary",
            "abandonment in Perry County",
            "page_text[0]",
        ),
        (2, "pymupdf", "1.24.10", "native", "text-layer", "primary", "", "page_text[1]"),
        (
            3,
            "pymupdf",
            "1.24.10",
            "native",
            "text-layer",
            "primary",
            "Docket No. AB 1242",
            "page_text[2]",
        ),
    ]
    # provenance, the digest of the text, and the unmeasured state (ADR 0021 D7's gate)
    row = con.execute(
        "SELECT text_sha256, confidence, confidence_state, asserted_from_document,"
        " payload_digest FROM document_text WHERE page_no = 1"
    ).fetchone()
    assert row[0] == hashlib.sha256(b"abandonment in Perry County").hexdigest()
    assert row[1:4] == (0, "unmeasured", SHA_A)
    # THE FILE IS THE PAYLOAD: content-addressed under blobs/, recorded in text_payload
    payload = r.body()[0]
    digest = hashlib.sha256(payload).hexdigest()
    assert row[4] == digest
    assert records.blob_path(tmp_path, digest).read_bytes() == payload
    assert con.execute("SELECT payload_kind, size_bytes FROM text_payload").fetchall() == [
        ("extract_text.json", len(payload))
    ]
    # the pass is recorded, keyed on when it ran
    assert con.execute(
        "SELECT method, reading_channel, render_profile, outcome, pages_read, pages_failed,"
        " ran_at FROM ocr_run"
    ).fetchall() == [("pymupdf", "text-layer", "native", "read", 3, 0, RAN)]
    # and every visible page is in the index
    assert _hits(con, "Perry") == [1] and _hits(con, "AB") == [3]


def test_a_blank_page_is_a_row_and_a_failed_pass_is_a_run_and_nothing_else(tmp_path):
    con = _store(tmp_path)
    load.load_reading(con, tmp_path, _reading(_extraction(SHA_A, pages=("",))))
    assert _live(con, SHA_A)[0][6] == ""
    failed = _reading(_ocr(SHA_B, texts=()) | {"outcome": "failed", "pages_failed": 4})
    assert load.load_reading(con, tmp_path, failed) == "run_only"  # not `unchanged`
    assert con.execute(
        "SELECT outcome, pages_read, pages_failed FROM ocr_run WHERE document_sha256 = ?", (SHA_B,)
    ).fetchall() == [("failed", 0, 4)]
    assert _live(con, SHA_B) == []


def test_a_restart_is_one_lookup_and_a_later_agreeing_pass_is_unchanged(tmp_path):
    con = _store(tmp_path)
    r = _reading(_extraction(SHA_A))
    load.load_reading(con, tmp_path, r)
    assert load.load_reading(con, tmp_path, r) == "restart"  # the run row proves it landed
    assert con.execute("SELECT COUNT(*) FROM document_text").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM ocr_run").fetchone()[0] == 1
    later = _reading(_extraction(SHA_A, extracted_at=LATER))
    assert load.load_reading(con, tmp_path, later) == "unchanged"  # no rows, but its run
    assert con.execute("SELECT COUNT(*) FROM ocr_run").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM document_text").fetchone()[0] == 3


def test_a_re_read_at_a_new_version_supersedes_across_keys_and_the_index_follows(tmp_path):
    """The idiom migration 0018 names as new: the incoming primary has a DIFFERENT natural
    key from the row it displaces, so nothing in the index reminds the writer. Retire at
    itself with `superseded_at`, insert, repoint — and `page_fts` loses the old text and
    gains the new."""
    con = _store(tmp_path)
    load.load_reading(con, tmp_path, _reading(_extraction(SHA_A)))
    newer = _reading(
        _extraction(
            SHA_A,
            pages=("abandonment in Ferry County", "", "Docket No. AB 1242"),
            tool_version="1.26.0",
            extracted_at=LATER,
        )
    )
    assert load.load_reading(con, tmp_path, newer, now=STAMP) == "loaded"
    rows = con.execute(
        "SELECT text_id, page_no, method_version, superseded_by, superseded_at"
        " FROM document_text ORDER BY text_id"
    ).fetchall()
    # page 1 changed and page 3 has a new key: both superseded; page 2 is ALSO superseded,
    # because a primary of another key now holds the page and one live primary is the rule
    assert rows == [
        (1, 1, "1.24.10", 4, STAMP),
        (2, 2, "1.24.10", 5, STAMP),
        (3, 3, "1.24.10", 6, STAMP),
        (4, 1, "1.26.0", None, None),
        (5, 2, "1.26.0", None, None),
        (6, 3, "1.26.0", None, None),
    ]
    assert _hits(con, "Perry") == [] and _hits(con, "Ferry") == [4]
    assert _hits(con, "AB") == [6]
    assert [r[0] for r in con.execute("SELECT text_id FROM document_text_display ORDER BY 1")] == [
        4,
        5,
        6,
    ]


def test_a_human_reading_is_never_displaced_and_keeps_the_primary_out_of_the_index(tmp_path):
    con = _store(tmp_path)
    load.load_reading(con, tmp_path, _reading(_extraction(SHA_A)))
    con.execute(
        "INSERT INTO document_text (document_sha256, page_no, method, method_version,"
        " render_profile, reading_channel, reading_role, text, text_sha256, confidence,"
        " confidence_state, asserted_at) VALUES (?, 1, 'human', 'unversioned', 'human',"
        " 'human', 'human', 'abandonment in Berry County', ?, 1, 'human', ?)",
        (SHA_A, "d" * 64, STAMP),
    )
    # the human writer's half of the index obligation, by hand until Migration B
    con.execute(
        "INSERT INTO page_fts (page_fts, rowid, text) VALUES ('delete', 1, ?)",
        ("abandonment in Perry County",),
    )
    con.execute("INSERT INTO page_fts (rowid, text) VALUES (4, 'abandonment in Berry County')")
    newer = _reading(
        _extraction(
            SHA_A,
            pages=("abandonment in Ferry County", "", "x"),
            tool_version="1.26.0",
            extracted_at=LATER,
        )
    )
    assert load.load_reading(con, tmp_path, newer) == "loaded"
    display = con.execute(
        "SELECT page_no, reading_role, text FROM document_text_display ORDER BY page_no"
    ).fetchall()
    assert display[0] == (1, "human", "abandonment in Berry County")
    assert _hits(con, "Ferry") == [] and _hits(con, "Berry") == [4]  # the primary stays out
    assert _hits(con, "x") == [con.execute("SELECT MAX(text_id) FROM document_text").fetchone()[0]]


def test_an_ocr_reading_carries_its_route_and_a_second_names_its_primary(tmp_path):
    con = _store(tmp_path)
    load.load_reading(con, tmp_path, _reading(_ocr(SHA_A)))
    row = con.execute(
        "SELECT route_class, route_method, route_method_version, engine_confidence,"
        " reading_channel FROM document_text"
    ).fetchone()
    assert row == ("degraded", "pp-doclayoutv3", "3.0", 0.9, "ocr")
    second = _ocr(
        SHA_A,
        texts=("abandonment in Perry Country",),
        role="second",
        method="ppocrv6",
        method_version="6",
    )
    against = {"method": "dots.mocr", "method_version": "1.5", "render_profile": "150"}
    second["pages"][0]["agreement"] = {
        "distance": 0.04,
        "method": "normalised-edit-distance",
        "method_version": "1",
        "against": against,
    }
    assert load.load_reading(con, tmp_path, _reading(second)) == "loaded"
    band = con.execute(
        "SELECT agreement_distance, agreement_against, agreement_method FROM document_text"
        " WHERE reading_role = 'second'"
    ).fetchone()
    assert band == (0.04, 1, "normalised-edit-distance")
    assert _hits(con, "Country") == []  # a second reading never reaches the display or the index
    assert _hits(con, "Perry") == [1]
    # the same second re-read at a new version supersedes the old second, not the primary
    second["method_version"] = "7"
    load.load_reading(con, tmp_path, _reading(second), now=STAMP)
    assert con.execute(
        "SELECT reading_role, superseded_at IS NOT NULL FROM document_text ORDER BY text_id"
    ).fetchall() == [("primary", 0), ("second", 1), ("second", 0)]


def test_an_agreement_is_against_the_primary_it_names_or_it_is_refused(tmp_path):
    """The pointer is quoted from the file, never computed from whatever is live when the
    file lands: the primary is superseded routinely, and a band attributed to text it was
    never measured against is a false number on a page."""
    con = _store(tmp_path)
    second = _ocr(SHA_A, role="second")
    second["pages"][0]["agreement"] = {
        "distance": 0.1,
        "method": "d",
        "method_version": "1",
        "against": PRIMARY,
    }
    with pytest.raises(load.Unreadable, match="no live primary"):
        load.load_reading(con, tmp_path, _reading(second))
    load.load_reading(con, tmp_path, _reading(_extraction(SHA_A, pages=("p",))))
    load.load_reading(
        con,
        tmp_path,
        _reading(_extraction(SHA_A, pages=("q",), tool_version="1.26.0", extracted_at=LATER)),
    )
    with pytest.raises(
        load.Unreadable,
        match="measured against pymupdf/1.24.10/native but the live primary is pymupdf/1.26.0",
    ):
        load.load_reading(con, tmp_path, _reading(second))
    assert (
        con.execute("SELECT COUNT(*) FROM document_text WHERE reading_role = 'second'").fetchone()[
            0
        ]
        == 0
    )


def test_a_key_live_in_another_role_is_refused_by_name(tmp_path):
    """The natural key carries no role; without this the INSERT collides with the reading's
    own live `second` and the operator sees an IntegrityError naming nothing."""
    con = _store(tmp_path)
    load.load_reading(con, tmp_path, _reading(_extraction(SHA_A, pages=("p",))))
    load.load_reading(con, tmp_path, _reading(_ocr(SHA_A, texts=("p",), role="second")))
    with pytest.raises(load.Unreadable, match="live as 'second'"):
        load.load_reading(con, tmp_path, _reading(_ocr(SHA_A, texts=("p2",), ran_at=LATER)))


def test_a_reading_for_bytes_the_store_does_not_hold_writes_nothing(tmp_path):
    con = _store(tmp_path, SHA_A)
    assert load.load_reading(con, tmp_path, _reading(_extraction(SHA_B))) == "unknown_document"
    assert con.execute("SELECT COUNT(*) FROM text_payload").fetchone()[0] == 0
    assert not (tmp_path / "blobs").exists()


# --- the pass over a directory, and the verb ----------------------------------------------------


def test_a_refused_reading_is_rolled_back_alone_and_leaves_no_blob(tmp_path):
    """`store.batches`: a document the store refuses (here an engine confidence on a
    text-layer row, which the CHECK rejects) or that the loader refuses on what it finds in
    the store (an agreement with no primary) is undone inside its savepoint, the neighbours
    land, and NO payload file is left under blobs/ for the sync to ship."""
    con = _store(tmp_path, SHA_A, SHA_B, "c" * 64)
    root = tmp_path / "text"
    _write(root, _extraction(SHA_A))
    bad = _ocr(SHA_B) | {"render_profile": "native", "reading_channel": "text-layer", "route": None}
    bad["pages"] = [{"page_no": 1, "text": "t", "member": "m", "engine_confidence": 0.5}]
    _write(root, bad)
    orphan = _ocr("c" * 64, role="second")
    orphan["pages"][0]["agreement"] = {
        "distance": 0.1,
        "method": "d",
        "method_version": "1",
        "against": PRIMARY,
    }
    _write(root, orphan)
    lines = []
    totals = load.run(con, root, tmp_path, log=lines.append)
    assert totals == {"loaded": 1, "failed": 2}
    assert sum("failed" in line for line in lines) == 2
    assert con.execute("SELECT COUNT(*) FROM document_text").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM ocr_run").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM text_payload").fetchone()[0] == 1
    blobs = [p for p in (tmp_path / "blobs").glob("*/*") if p.is_file()]
    assert len(blobs) == 1


def test_the_pass_walks_the_directory_and_the_verb_reports(tmp_path, capsys):
    con = _store(tmp_path)
    con.close()
    root = tmp_path / "text"
    _write(root, _extraction(SHA_A))
    _write(root, _ocr(SHA_B))
    _write(root, _extraction("e" * 64))  # not held
    _write(root, _extraction("f" * 64), name="9" * 64)  # misfiled
    (root / "cd").mkdir()
    (root / "cd" / ("c" * 64 + ".json")).write_text("{not json", encoding="utf-8")
    ns = _ns(tmp_path, root)
    assert cli._text(ns) == 0
    out = capsys.readouterr().out
    assert "'loaded': 2" in out and "'unknown_document': 1" in out and "'unreadable': 2" in out
    con = db.connect(tmp_path / "s.sqlite")
    assert con.execute("SELECT COUNT(*) FROM document_text").fetchone()[0] == 4
    assert _hits(con, "Perry") == [1, 4]
    con.close()
    assert cli._text(ns) == 0  # a restart: one lookup each, exit 0
    assert "'restart': 2" in capsys.readouterr().out
    ns.root = str(tmp_path / "nowhere")
    assert cli._text(ns) == 1
    assert "directory of readings" in capsys.readouterr().out


def test_a_second_re_posted_against_the_replacement_primary_is_a_new_row(tmp_path):
    """Same text, new agreement: the short-circuit that compared text alone kept the live
    second pointing its distance at the retired primary — the false number on a page the
    loader's docstring says it refuses."""
    con = _store(tmp_path)
    load.load_reading(con, tmp_path, _reading(_ocr(SHA_A)))
    against = {"method": "dots.mocr", "method_version": "1.5", "render_profile": "150"}
    second = _ocr(
        SHA_A,
        texts=("abandonment in Perry Country",),
        role="second",
        method="ppocrv6",
        method_version="6",
    )
    second["pages"][0]["agreement"] = {
        "distance": 0.04,
        "method": "d",
        "method_version": "1",
        "against": against,
    }
    load.load_reading(con, tmp_path, _reading(second))
    newer = _ocr(SHA_A, texts=("abandonment in Perry County.",), method_version="1.6", ran_at=LATER)
    load.load_reading(con, tmp_path, _reading(newer))
    second["pages"][0]["agreement"] = {
        "distance": 0.05,
        "method": "d",
        "method_version": "1",
        "against": dict(against, method_version="1.6"),
    }
    second["ran_at"] = "2026-09-04T00:00:00+00:00"
    assert load.load_reading(con, tmp_path, _reading(second)) == "loaded"
    new_primary = con.execute(
        "SELECT text_id FROM document_text WHERE method_version = '1.6'"
    ).fetchone()[0]
    rows = con.execute(
        "SELECT agreement_against, agreement_distance, superseded_by IS NULL FROM document_text"
        " WHERE reading_role = 'second' ORDER BY text_id"
    ).fetchall()
    assert rows == [(1, 0.04, 0), (new_primary, 0.05, 1)]
    # and the very same second again is unchanged
    second["ran_at"] = "2026-09-05T00:00:00+00:00"
    assert load.load_reading(con, tmp_path, _reading(second)) == "unchanged"


def test_a_reading_document_is_parsed_once_and_never_cut_at_a_page_text_string(tmp_path):
    """The extraction shape is told from the head without parsing; a reading document
    whose engine payload happens to contain the string "page_text" is not cut there."""
    root = tmp_path / "text"
    doc = _ocr(SHA_A) | {"engine": {"note": 'here "page_text" is the engine word for it'}}
    path = _write(root, doc)
    assert path.read_text(encoding="utf-8").index("page_text") < 4096
    reading = load.read_file(path)
    assert reading.header.key.method == "dots.mocr" and reading.body()[1][0].text
    # a stub whose FIRST member is page_text is parsed whole, not cut to an empty header
    rest = {k: v for k, v in _extraction(SHA_B).items() if k != "page_text"}
    path = _write(root, {"page_text": ["p"], **rest})
    assert load.read_file(path).header.key.method == "pymupdf"
