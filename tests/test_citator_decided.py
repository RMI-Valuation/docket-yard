"""The decided-date extraction pass (ADR 0023 addendum of 2026-09-16; migration 0034).

What it asserts is a QUOTATION of a `Decided:` line, with the page, the line, the text it read
and the rule that read it; never a decision's date. These tests hold it to the addendum's
decisions in the order the addendum gives them.
"""

import json

from docketyard.citator import decided
from tests.test_citator_pipeline import SHA, STAMP, _store

LATER = "2026-10-05T00:00:00+00:00"


def _page(con, page_no, text, *, channel="text-layer", role="primary", at=STAMP, **over):
    """A displayed reading of one page. A text-layer page by default; `role="human"` is a
    person's correction, which the display prefers."""
    ocr = channel == "ocr"
    human = role == "human"
    row = {
        "document_sha256": SHA,
        "page_no": page_no,
        "method": "human" if human else ("dots.mocr" if ocr else "pymupdf"),
        "method_version": "unversioned" if human else ("1.5" if ocr else "1.28"),
        "render_profile": "human" if human else ("200" if ocr else "native"),
        "reading_channel": channel,
        "reading_role": role,
        "route_class": "degraded" if ocr else None,
        "route_method": "pp-doclayoutv3" if ocr else None,
        "route_method_version": "3.0" if ocr else None,
        "text": text,
        "text_sha256": "a" * 64,
        "confidence": 1.0 if human else 0,
        "confidence_state": "human" if human else "unmeasured",
        "asserted_at": at,
    }
    row.update(over)
    cols = ", ".join(row)
    con.execute(
        f"INSERT INTO document_text ({cols}) VALUES ({', '.join('?' * len(row))})",
        list(row.values()),
    )
    return con.execute("SELECT last_insert_rowid()").fetchone()[0]


def _live(con):
    return con.execute(
        "SELECT page_no, ordinal, printed_text, decided_date, reading_channel, text_id"
        " FROM decision_decided_date WHERE superseded_by IS NULL ORDER BY page_no, ordinal"
    ).fetchall()


def test_a_line_is_quoted_as_printed_and_read_never_corrected():
    """Decision 7, and CLAUDE.md: dates are quoted, never computed. The schedule's own
    misprint stays a misprint."""
    text = "SERVICE DATE\nDecided:  October 15, 2016\nBy the Board"
    (line,) = decided.lines(text)
    assert line.printed_text == "Decided:  October 15, 2016"
    assert line.decided_date == "2016-10-15"
    start, end, raw = line.spans[0]
    assert " ".join(text[start:end].split()) == raw == "Decided: October 15, 2016"
    assert decided.parse("Decided: Sept. 30, 2026") == "2026-09-30"
    assert decided.parse("Decided: February 30, 2026") is None  # shaped right, not a day
    assert decided.parse("Decided: illegible") is None
    # the spacing the record prints (the 2026-09-17 copy's unparsed lines)
    for printed, iso in (
        ("Decided:  March 20,1997", "1997-03-20"),
        ("Decided:  June 23 , 1998", "1998-06-23"),
        ("Decided:  September1, 2026.", "2026-09-01"),
        ("Decided: January, 22, 2004.", "2004-01-22"),
    ):
        assert decided.parse(printed) == iso, printed
    assert decided.parse("Decided:  April 21, 20004") is None  # not a year
    assert decided.parse("Decided: 18, 1997") is None  # no month printed
    assert decided.parse("Decided: January 77. 1998") is None  # not a day
    assert decided.parse("Decided: No 12 2004, October 5, 2017") == "2017-10-05"


def test_an_empty_label_takes_the_next_line_unless_that_line_is_a_label():
    text = "Decided:\n\n  October 1, 2026\n"
    (line,) = decided.lines(text)
    assert line.printed_text == "Decided: October 1, 2026"
    assert line.decided_date == "2026-10-01"
    assert [raw for *_, raw in line.spans] == ["Decided:", "October 1, 2026"]
    for start, end, raw in line.spans:
        assert " ".join(text[start:end].split()) == raw
    (bare,) = decided.lines("Decided:\nVice Chairman Primus: concurring\n")
    assert bare.printed_text == "Decided:" and bare.decided_date is None
    # a date line with a label after it is the date, not a label (code review)
    (dated,) = decided.lines("Decided:\nSeptember 30 2016 Served: October 3 2016\n")
    assert dated.decided_date == "2016-09-30"


def test_the_pass_quotes_every_line_of_every_page_with_its_page_and_text(tmp_path):
    """Decisions 1, 2 and 4: the page in the key, the ordinal within one page's reading, and
    the text it read named."""
    con = _store(tmp_path)
    p1 = _page(con, 1, "Decided: March 10, 2021\n")
    p9 = _page(con, 9, "Decided: March 10, 2021\nand\nDecided: March 11, 2021\n")
    out = decided.run(con)
    assert (out.documents, out.pages, out.lines) == (1, 2, 3)
    assert _live(con) == [
        (1, 0, "Decided: March 10, 2021", "2021-03-10", "text-layer", p1),
        (9, 0, "Decided: March 10, 2021", "2021-03-10", "text-layer", p9),
        (9, 1, "Decided: March 11, 2021", "2021-03-11", "text-layer", p9),
    ]
    loc = json.loads(
        con.execute(
            "SELECT source_location FROM decision_decided_date WHERE page_no = 9 AND ordinal = 1"
        ).fetchone()[0]
    )
    assert loc["page"] == 9 and loc["spans"][0][2] == "Decided: March 11, 2021"
    run = con.execute(
        "SELECT outcome, pages_read, targets_emitted FROM extraction_run WHERE method = ?",
        (decided.METHOD,),
    ).fetchone()
    assert run == ("read", 2, 3)


def test_a_document_read_and_found_empty_says_so(tmp_path):
    """ADR 0018 D10: absence is recorded as a read, not left as no row."""
    con = _store(tmp_path)
    _page(con, 1, "No decided line on this page.\n")
    decided.run(con)
    assert _live(con) == []
    assert con.execute(
        "SELECT pages_read, targets_emitted FROM extraction_run WHERE method = ?",
        (decided.METHOD,),
    ).fetchone() == (1, 0)


def test_an_unchanged_page_is_not_rewritten(tmp_path):
    """Decision 8: a page whose live quotations already quote its displayed text, at this
    version, line for line, is left as it is."""
    con = _store(tmp_path)
    _page(con, 1, "Decided: March 10, 2021\n")
    decided.run(con)
    (before,) = con.execute("SELECT decided_id FROM decision_decided_date").fetchone()
    again = decided.run(con)
    assert (again.unchanged, again.retired) == (1, 0)
    assert con.execute("SELECT decided_id FROM decision_decided_date").fetchall() == [(before,)]


def test_a_text_stamped_before_the_last_run_is_still_quoted(tmp_path):
    """The clock rule this replaced: the text loader stamps `asserted_at` when a batch starts
    and commits later, so a text the display shows only after a run can carry an EARLIER stamp
    than that run, and was skipped for ever (code review and the schema critic, 2026-10-03)."""
    con = _store(tmp_path)
    first = _page(con, 1, "Decided: March 10, 2O21\n")
    decided.run(con)
    con.execute(
        "UPDATE document_text SET superseded_by = text_id, superseded_at = ? WHERE text_id = ?",
        (LATER, first),
    )
    newer = _page(con, 1, "Decided: March 10, 2021\n", at="2000-01-01T00:00:00+00:00")
    decided.run(con)
    assert _live(con) == [(1, 0, "Decided: March 10, 2021", "2021-03-10", "text-layer", newer)]


def test_a_page_shown_again_after_a_correction_is_withdrawn_is_quoted_again(tmp_path):
    """The second way the clock rule lost a page: the machine reading comes back to the display
    with its old stamp after a person's correction is retired."""
    con = _store(tmp_path)
    machine = _page(con, 1, "Decided: March 10, 2021\n")
    decided.run(con)
    person = _page(con, 1, "Decided: March 10, 2021\n", channel="human", role="human", at=LATER)
    decided.run(con)
    assert _live(con) == []  # the person's page is not quoted, and the machine row went stale
    con.execute(
        "UPDATE document_text SET superseded_by = text_id, superseded_at = ? WHERE text_id = ?",
        (LATER, person),
    )
    decided.run(con)
    assert [r[5] for r in _live(con)] == [machine]


def test_every_live_row_on_a_re_read_page_is_retired(tmp_path):
    """Decision 5, every live machine row of the method on the page: two live rows sharing a
    line — two readings' quotations, which `one_per_line` allows because their texts differ —
    are both retired on a re-read, where a map keyed by line kept one of them (code review)."""
    con = _store(tmp_path)
    layer = _page(con, 1, "Decided: March 10, 2021\n")
    decided.run(con)
    ocr = _page(con, 1, "Decided: March 10, 2021\n", channel="ocr", role="second")
    con.execute(  # a second reading's quotation of the same line, as a later pass might write
        "INSERT INTO decision_decided_date (document_sha256, date_kind, page_no, ordinal,"
        " reading_channel, method, method_version, render_profile, reading_method,"
        " reading_method_version, printed_text, decided_date, text_id, asserted_at,"
        " confidence, confidence_state) VALUES (?, 'decided', 1, 0, 'ocr', ?, ?, '200',"
        " 'dots.mocr', '1.5', 'Decided: March 10, 2021', '2021-03-10', ?, ?, 0, 'unmeasured')",
        (SHA, decided.METHOD, decided.VERSION, ocr, STAMP),
    )
    assert len(_live(con)) == 2
    con.execute(
        "UPDATE document_text SET superseded_by = text_id, superseded_at = ? WHERE text_id = ?",
        (LATER, layer),
    )
    newest = _page(con, 1, "Decided: March 11, 2021\n", at=LATER)
    out = decided.run(con)
    assert out.retired == 2
    assert _live(con) == [(1, 0, "Decided: March 11, 2021", "2021-03-11", "text-layer", newest)]


def test_a_limited_run_sweeps_only_what_it_read(tmp_path):
    """A document a limited run never reached keeps its rows live, for the run that reads it
    to replace and point at (decision 6)."""
    con = _store(tmp_path)
    first = _page(con, 1, "Decided: March 10, 2021\n")
    decided.run(con)
    con.execute(
        "UPDATE document_text SET superseded_by = text_id, superseded_at = ? WHERE text_id = ?",
        (LATER, first),
    )
    _page(con, 1, "Decided: March 10, 2021\n", at=LATER)
    assert decided.run(con, limit=0).stale == 0  # read nothing, so swept nothing
    full = decided.run(con)
    assert full.stale == 0 and full.retired == 1  # replaced on the re-read, not swept


def test_a_person_s_reading_is_not_quoted_and_the_machine_s_quotation_goes_stale(tmp_path):
    """Decisions 3 and 6: the display shows the person's correction, so the page is skipped,
    and the machine quotation of the text it no longer shows is retired, at itself."""
    con = _store(tmp_path)
    _page(con, 1, "Decided: March 10, 2021\n")
    decided.run(con)
    _page(con, 1, "Decided: March 10, 2021\n", channel="human", role="human", at=LATER)
    out = decided.run(con)
    assert out.human_pages == 1 and out.stale == 1
    assert _live(con) == []
    (sup, at, me) = con.execute(
        "SELECT superseded_by, superseded_at, decided_id FROM decision_decided_date"
    ).fetchone()
    assert sup == me and at is not None


def test_a_re_read_page_replaces_its_lines_and_points_each_at_its_replacement(tmp_path):
    """Decisions 5 and 6: a newer reading of the page retires every live row of the method on
    it first, and a retired row points at the new row on the same (page, ordinal) — or at
    itself where the newer reading found no line there."""
    con = _store(tmp_path)
    first = _page(con, 1, "Decided: March 10, 2O21\nDecided: March 11, 2021\n")
    decided.run(con)
    old = dict(
        con.execute(
            "SELECT ordinal, decided_id FROM decision_decided_date WHERE superseded_by IS NULL"
        ).fetchall()
    )
    # the page is read again: the old reading retired, a new one displayed in its place
    con.execute(
        "UPDATE document_text SET superseded_by = text_id, superseded_at = ? WHERE text_id = ?",
        (LATER, first),
    )
    newer = _page(con, 1, "Decided: March 10, 2021\n", at=LATER)
    out = decided.run(con)
    assert out.retired == 2 and out.lines == 1
    assert _live(con) == [(1, 0, "Decided: March 10, 2021", "2021-03-10", "text-layer", newer)]
    (new_id,) = con.execute(
        "SELECT decided_id FROM decision_decided_date WHERE superseded_by IS NULL"
    ).fetchone()
    pointers = dict(
        con.execute(
            "SELECT decided_id, superseded_by FROM decision_decided_date"
            " WHERE superseded_by IS NOT NULL"
        ).fetchall()
    )
    assert pointers[old[0]] == new_id  # replaced on the same line
    assert pointers[old[1]] == old[1]  # the line the newer reading no longer finds


def test_an_ocr_quotation_names_the_engine_that_read_it(tmp_path):
    con = _store(tmp_path)
    _page(con, 1, "Decided: March 10, 2021\n", channel="ocr")
    decided.run(con)
    row = con.execute(
        "SELECT reading_channel, render_profile, reading_method, reading_method_version"
        " FROM decision_decided_date"
    ).fetchone()
    assert row == ("ocr", "200", "dots.mocr", "1.5")


def test_a_document_no_decision_carries_is_not_read(tmp_path):
    con = _store(tmp_path)
    con.execute("DELETE FROM decision_attachment")
    _page(con, 1, "Decided: March 10, 2021\n")
    assert decided.run(con).documents == 0
