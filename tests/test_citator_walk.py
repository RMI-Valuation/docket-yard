"""`citator.walk` — the finder over the record's own text (the `find` verb).

The half that was missing while the store held no text. Migration A put it there on
2026-09-04, so the walk is a store read; what it emits is `load.load_document`'s shape, and
these tests are about the three judgements it makes on the way — which pages are the
document's, what the document's OWN dockets are, and which channel the run is stamped with.
"""

import argparse
import json

import pytest

from docketyard import cli
from docketyard.citator import find, keys, walk
from docketyard.store import db
from tests.test_citator_pipeline import SHA, STAMP, _store


def _page(
    con,
    sha,
    page_no,
    text,
    *,
    role="primary",
    channel="text-layer",
    method="pdf-text",
    route_class=None,
):
    con.execute(
        "INSERT INTO document_text (document_sha256, page_no, reading_channel, reading_role,"
        " method, method_version, render_profile, route_class, route_method,"
        " route_method_version, text, text_sha256, confidence, confidence_state, asserted_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            sha,
            page_no,
            channel,
            role,
            method if role != "human" else "human",
            "unversioned" if role == "human" else "1",
            "human" if role == "human" else "native",
            route_class or ("clean" if channel == "ocr" else None),
            "pp-doclayoutv3+regions" if channel == "ocr" else None,
            "provisional-1" if channel == "ocr" else None,
            text,
            f"{abs(hash((sha, page_no, text, role))) & 0xFFFFFFFF:064d}",
            1.0 if role == "human" else 0.0,
            "human" if role == "human" else "unmeasured",
            STAMP,
        ),
    )


def test_the_walk_emits_what_load_consumes_with_the_pages_the_reader_sees(tmp_path):
    """One document, three pages, and a page number that has to survive: `source_location`
    points at the page a reader would be shown, so the finding's page is the store's page
    number and not its position in a list."""
    con = _store(tmp_path)
    _page(con, SHA, 1, "This decision concerns FD 36873.")
    _page(con, SHA, 4, "See Docket No. EP 445 for the Board's earlier view.")
    _page(con, SHA, 7, "")  # a blank page is read and carries nothing
    con.commit()

    docs = list(walk.documents(con))
    assert len(docs) == 1
    doc = docs[0]
    # the shape `citator load` requires of every findings document
    for required in ("document_sha256", "method", "method_version", "reading_channel"):
        assert doc[required], required
    assert doc["document_sha256"] == SHA
    assert doc["method"] == "regex-docket-cite" and doc["method_version"] == find.FINDER_VERSION
    assert doc["pages_read"] == 3

    pages = {f["page"] for f in doc["findings"]}
    assert 4 in pages, "the citation on page 4 must key at page 4, not at position 2"
    found = {(f["page"], keys.normalise(f["target"]), f["kind"]) for f in doc["findings"]}
    # its OWN proceeding is a caption; the unrelated docket is a citation (ADR 0017 D1)
    assert (1, "FD 36873", "caption") in found
    assert (4, "EP 445", "citation") in found
    con.close()


def test_the_documents_own_dockets_are_the_union_of_its_carriers(tmp_path):
    """A document carried by a decision in a docket AND its sub-docket (ADR 0005), or by two
    decisions, has both as its own. Reading one of them as a citation because a second
    carrier exists would mint an edge out of the record's own filing arrangement."""
    con = _store(tmp_path)
    con.execute(
        "INSERT INTO decision_record (decision_pk, docket_id, stb_decision_id, service_date,"
        " observed_in_event) VALUES (2, 2, '52527', '2021-03-12', 1)"
    )
    con.execute(
        "INSERT INTO decision_attachment (decision_pk, source_url, document_sha256)"
        " VALUES (2, 'u2', ?)",
        (SHA,),
    )
    con.commit()
    assert walk.own_by_document(con)[SHA] == {"FD 36873", "FD 36873 (1)"}

    _page(con, SHA, 1, "In FD 36873 (Sub-No. 1), and see EP 445.")
    con.commit()
    doc = next(iter(walk.documents(con)))
    kinds = {(keys.normalise(f["target"]), f["kind"]) for f in doc["findings"]}
    assert ("FD 36873 (1)", "caption") in kinds, "the sub-docket is this document's own"
    assert ("EP 445", "citation") in kinds
    con.close()


def test_a_superseded_reading_is_not_read(tmp_path):
    """`document_text` is append-only and a correction supersedes rather than updates (ADR
    0021 D1). The finder reads what is live, so a withdrawn reading cannot mint an edge."""
    con = _store(tmp_path)
    _page(con, SHA, 1, "The live page names EP 445.")
    _page(con, SHA, 2, "Superseded text naming EP 111.")
    con.execute(
        "UPDATE document_text SET superseded_by = text_id, superseded_at = ? WHERE page_no = 2",
        (STAMP,),
    )
    con.commit()
    doc = next(iter(walk.documents(con)))
    found = {keys.normalise(f["target"]) for f in doc["findings"]}
    assert found == {"EP 445"} and doc["pages_read"] == 1
    con.close()


def test_a_document_with_no_readable_text_is_skipped_not_emitted(tmp_path):
    """The 610 decisions whose files are image-only, until the OCR wave's readings land.
    Emitting them would record an extraction run over a document the finder never read, and
    `pages_read` of zero is a claim to have looked."""
    con = _store(tmp_path)
    assert list(walk.documents(con)) == [], "a document with no text row is not a reading"
    _page(con, SHA, 1, "")
    _page(con, SHA, 2, "   ")
    con.commit()
    assert list(walk.documents(con)) == [], "every page blank is not a reading either"
    con.close()


def test_a_document_read_on_two_channels_is_two_readings_not_one(tmp_path):
    """THE GRAIN. `load` stamps a batch with one (method, version, reading_channel) and the
    CLI refuses a mixed one, because the confidence written on a row is the measurement of
    THAT pass on THAT channel (ADR 0017 D3, ADR 0018 D8). An earlier draft of this walk took
    the majority channel of a mixed document; its output was unloadable, and the OCR pages
    would have carried the text-layer measurement — the borrowed precision
    `load.WrongChannel` exists to refuse (code review, 2026-09-04)."""
    con = _store(tmp_path)
    _page(con, SHA, 1, "The text layer names EP 445.", channel="text-layer")
    _page(con, SHA, 2, "The scan was read as EP 446.", channel="ocr", method="ppocr")
    _page(con, SHA, 3, "And EP 447 too.", channel="ocr", method="ppocr")
    con.commit()

    docs = sorted(walk.documents(con), key=lambda d: d["reading_channel"])
    assert [d["reading_channel"] for d in docs] == ["ocr", "text-layer"]
    assert [d["document_sha256"] for d in docs] == [SHA, SHA], "one document, two readings"
    assert [d["pages_read"] for d in docs] == [2, 1]
    ocr, layer = docs
    assert {keys.normalise(f["target"]) for f in ocr["findings"]} == {"EP 446", "EP 447"}
    assert {keys.normalise(f["target"]) for f in layer["findings"]} == {"EP 445"}
    # two passes, so two batches: `cli._citator` refuses a directory holding both
    assert len({(d["method"], d["method_version"], d["reading_channel"]) for d in docs}) == 2
    assert list(walk.documents(con, "ocr")) == [ocr], "a channel can be walked alone"
    con.close()


def test_a_human_page_is_read_by_no_machine_pass(tmp_path):
    """`'human'` is legal in `reading_vocab` and is never what a model pass read from, so
    `load` refuses it outright. A citation a person found on a corrected page is the review
    layer's to assert, not this finder's — and the page does not fall back to the primary it
    shadows, because reading text no reader is shown would put a `source_location` where
    nobody can check it."""
    con = _store(tmp_path)
    _page(con, SHA, 1, "The machine misread this as EP 999.")
    _page(con, SHA, 1, "A person read: see EP 445.", role="human", channel="human")
    _page(con, SHA, 2, "The layer names EP 446.")
    con.commit()

    docs = list(walk.documents(con))
    assert [d["reading_channel"] for d in docs] == ["text-layer"]
    assert docs[0]["pages_read"] == 1, "the human page belongs to no machine reading"
    found = {keys.normalise(f["target"]) for f in docs[0]["findings"]}
    assert found == {"EP 446"}
    assert "EP 445" not in found, "a human reading was emitted as a machine pass"
    assert "EP 999" not in found, "the primary a human row shadows was read anyway"
    con.close()


def test_the_find_verb_writes_a_directory_and_asserts_nothing(tmp_path):
    con = _store(tmp_path)
    _page(con, SHA, 1, "See EP 445.")
    con.commit()
    con.close()
    out = tmp_path / "findings"
    args = argparse.Namespace(
        db=str(tmp_path / "s.sqlite"), what="find", out=str(out), channel=None
    )
    assert cli._citator(args) == 0
    written = list(out.glob("*/*.json"))
    assert [p.stem for p in written] == [SHA]
    assert written[0].parent.name == "text-layer", "one subdirectory per channel: one batch"
    doc = json.loads(written[0].read_text(encoding="utf-8"))
    assert doc["document_sha256"] == SHA and doc["findings"]

    # it asserted nothing: the citator's own tables are untouched
    con = db.connect(tmp_path / "s.sqlite")
    for table in ("citation", "citation_reading", "extraction_run"):
        assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    con.close()


def test_a_document_with_no_own_dockets_is_a_refusal_not_a_default(tmp_path):
    """`find.findings_document` raises rather than treating an empty `own` as "no captions",
    which would read every caption as a citation. The walk must not paper over it."""
    con = _store(tmp_path)
    _page(con, SHA, 1, "FD 36873.")
    con.commit()
    with pytest.raises(ValueError, match="no `own` dockets"):
        find.findings_document([(1, "FD 36873.")], document_sha256=SHA, own=set())
    con.close()


def test_a_findings_directory_is_written_once_and_never_reused(tmp_path):
    """`load` reads every *.json under the path it is given. A stale document from an earlier
    walk — of text the store no longer holds, or on a channel this walk no longer emits —
    would poison the batch's one-pass check or be loaded as a reading that never happened."""
    con = _store(tmp_path)
    _page(con, SHA, 1, "See EP 445.")
    con.commit()
    con.close()
    out = tmp_path / "findings"
    args = argparse.Namespace(
        db=str(tmp_path / "s.sqlite"), what="find", out=str(out), channel=None
    )
    assert cli._citator(args) == 0
    assert cli._citator(args) == 1, "a second walk into the same directory was allowed"
