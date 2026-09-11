"""`docketyard.citator.find` — the finder, and the two things it must not do.

It must not filter on the registry (ADR 0017 D2), and it must not drop a caption (the
operator's decision, 2026-09-01). Both are ways of discarding a row, and both were how the
measured tool behaved.
"""

from docketyard.citator import find, keys, resolve

OWN = {"FD 36873"}


def test_it_does_not_filter_on_the_registry():
    """ADR 0017 D2. A finder that can only emit dockets the registry holds cannot emit an
    unresolvable one — which empties the review queue by construction and makes
    "cites `EP 445` (not in the record)" a display that can never be produced."""
    found = find.find("See NOR 99999, slip op. at 3, which nobody holds.", OWN)
    assert [f["target"] for f in found] == ["NOR 99999"]


def test_a_caption_is_emitted_and_labelled_rather_than_dropped():
    """The measured tool kept only what it called a citation — 401 captions dropped against
    356 citations on the sixty decisions. A row is never discarded.

    The document-word window is ±160 characters, so the filler below is not padding: a
    running caption near a citation reads as a citation, which is the measured behaviour of
    the rule that scored 95.1% recall at 88.1% precision. Widening or narrowing it is a new
    FINDER_VERSION and a re-measurement, not a tidy-up.
    """
    page = (
        "SURFACE TRANSPORTATION BOARD\nDocket No. FD 36873\n"
        + "The parties are directed to confer and report. " * 5
        + "\nThe Board in EP 445, slip op. at 3, held otherwise."
    )
    kinds = {f["target"]: f["kind"] for f in find.find(page, OWN)}
    assert kinds == {"FD 36873": "caption", "EP 445": "citation"}


def test_its_own_proceeding_becomes_a_citation_when_a_document_word_is_near():
    """The own-docket rule of ADR 0017 D1: a caption ONLY when the number is the citing
    decision's own proceeding AND no document word is near. A prior decision in the same
    proceeding is the reconsideration edge query 2 exists to find."""
    page = "Decision No. 5, FD 36873, slip op. at 6, decided the same question."
    assert find.find(page, OWN)[0]["kind"] == "citation"


def test_the_raw_is_what_the_page_printed():
    """`citation_reading.cited_raw` is "the string as THIS reading printed it". Rebuilding it
    from the match groups drops the parenthetical, because `keys.DOCKET` has no group for
    one — so a page saying `EP 542 (Sub-No. 32)` would be recorded as `EP 542`."""
    found = find.find("In Docket No. EP 542 (Sub-No. 32) the Board said so.", OWN)
    assert found[0]["target"] == "EP 542 (Sub-No. 32)"
    assert keys.normalise(found[0]["target"]) == "EP 542 (32)"


def test_a_target_read_twice_on_a_page_is_one_finding():
    """One finding per (page, key): the quoted text is joined at load, never doubled here."""
    page = "EP 445 first, and EP 445 again on the same line, slip op. at 3."
    assert len(find.find(page, OWN)) == 1


def test_the_deadline_sentence_trap_is_not_a_docket():
    """`IS` and `SO` are English words, which is why `keys.DOCKET` matches its prefix
    case-sensitively: "the exemption is 30 days after" must not key as `IS 30`."""
    assert find.find("the exemption is 30 days after service of this decision", OWN) == []


def test_pages_are_split_the_way_the_box_writes_them():
    text = "===== page 1 =====\nEP 445, slip op.\n===== page 7 =====\nNOR 42150, slip op."
    assert [p for p, _ in find.pages(text)] == [1, 7]
    doc = find.findings_document(text, document_sha256="d" * 64, own=OWN)
    assert doc["pages_read"] == 2
    assert [f["page"] for f in doc["findings"]] == [1, 7]
    assert doc["method"] == "regex-docket-cite"


def test_a_sub_docket_the_line_break_pushed_down_is_read():
    """628 citations in the first load (2026-09-11) keyed as the parent because `keys.SUBNO`
    will not cross a newline; with the words `Sub-No.` it may, and the target's second line is
    quoted, so the served date printed on it reaches the resolver too."""
    page = (
        "Southern Pacific—Aban. Exemption, Docket No. AB-12 \n"
        "(Sub-No. 162X) (STB served May 29, 1996). \n"
    )
    f = find.find(page, OWN)[0]
    assert f["target"] == "AB-12 (Sub-No. 162X)"
    assert keys.normalise(f["target"]) == "AB 12 (162X)"
    assert resolve.served_date(resolve._anchored(f["quoted"], f["target"])) == "1996-05-29"


def test_a_bare_parenthesis_on_the_next_line_is_still_a_list_marker():
    """The guard `keys.SUBNO` exists for: only the words cross a line break. Both bare cases in
    the first load were list items."""
    page = "STB Docket No. AB-88 (Sub-No. 10X)\n(3) Retain its interest in an\n"
    f = find.find(page, OWN)[0]
    assert f["target"] == "AB-88 (Sub-No. 10X)"
    assert f["quoted"] == "STB Docket No. AB-88 (Sub-No. 10X)"  # the list item is not quoted
    assert [f["target"] for f in find.find("the carrier in EP 445\n(a) shall file", OWN)] == [
        "EP 445"
    ]


def test_a_served_date_the_line_break_pushed_down_is_quoted():
    """3,438 citations in the first load printed their served date only on the next line. The
    two shapes that continue a citation: its own parenthesis left open, and `, et al.` before
    a served parenthetical on the next line."""
    for page, served in (
        (
            "Discon., Docket No. AB-379X (ICC\nserved Nov. 4, 1992) (Cheatham County); Fore",
            "1992-11-04",
        ),
        (
            "Line in Okla. County, Okla., AB 6 (Sub-No. 430X), et al. \n"
            "(STB served June 5, 2008). \n",
            "2008-06-05",
        ),
    ):
        f = find.find(page, OWN)[0]
        assert resolve.served_date(resolve._anchored(f["quoted"], f["target"])) == served


def test_a_line_that_is_not_the_citations_is_not_quoted():
    """The continuation feeds the span test as well as the resolver, so a caption followed by
    prose — even prose that says `served` — is quoted alone, exactly as before."""
    page = "Docket No. FD 36873\nThe Board served notice on the parties.\n"
    assert find.find(page, OWN)[0]["quoted"] == "Docket No. FD 36873"
    one = "In Docket No. EP 542 (Sub-No. 32) the Board said so.  \n"
    assert (
        find.find(one, OWN)[0]["quoted"] == "In Docket No. EP 542 (Sub-No. 32) the Board said so."
    )


def test_a_later_citations_parenthesis_does_not_continue_an_earlier_one():
    """A parenthesis opened after a later target on the line is that target's (ingest
    specialist, 2026-09-11): EP 445 must not gain FD 36873's date line."""
    page = "See EP 445 and FD 36873 (STB\nserved Mar. 12, 2021).\n"
    quotes = {f["target"]: f["quoted"] for f in find.find(page, OWN)}
    assert quotes["EP 445"] == "See EP 445 and FD 36873 (STB"
    assert quotes["FD 36873"] == "See EP 445 and FD 36873 (STB served Mar. 12, 2021)"


def test_a_parenthesis_closed_after_a_later_docket_is_closed():
    """Opened before a later target and closed after it on the same line: nothing is left open,
    so the next line of prose is not quoted (code review, 2026-09-11 — it put `slip op.` into
    the span test's hands and flipped an in-family edge)."""
    page = "EP 711 (Sub-No. 1) (citing FD 36873), the Board held\nthat Decision No. 5, slip op."
    quotes = {f["target"]: f["quoted"] for f in find.find(page, OWN)}
    assert quotes["EP 711 (Sub-No. 1)"] == "EP 711 (Sub-No. 1) (citing FD 36873), the Board held"


def test_parentheses_are_matched_in_order():
    """Counting opens and closes apart could not see either of these (code review, 2026-09-11):
    a later target's own sub-docket pair inside this target's open parenthesis, and a stray
    close before the parenthesis this target opens."""
    nested = "EP 445 (see FD 1 (Sub-No. 2)\nserved Mar. 12, 2021) and a paragraph.\n"
    quotes = {f["target"]: f["quoted"] for f in find.find(nested, OWN)}
    assert quotes["EP 445"] == "EP 445 (see FD 1 (Sub-No. 2) served Mar. 12, 2021)"
    stray = "EP 445 (Sub-No. 3)) (STB\nserved June 5, 2008). And a paragraph.\n"
    assert find.find(stray, OWN)[0]["quoted"] == ("EP 445 (Sub-No. 3)) (STB served June 5, 2008)")


def test_the_continuation_stops_at_the_parenthesis_it_closes():
    """Everything quoted reaches the span test, so a paragraph printed on one line after the
    date is not handed to it."""
    page = (
        "Discon., Docket No. AB-379X (ICC\n"
        "served Nov. 4, 1992) (Cheatham County); and a paragraph the text layer ran on.\n"
    )
    assert find.find(page, OWN)[0]["quoted"] == (
        "Discon., Docket No. AB-379X (ICC served Nov. 4, 1992)"
    )


def test_crlf_text_reads_as_lf():
    page = "Docket No. AB-12 \r\n(Sub-No. 162X) (STB served May 29, 1996). \r\n"
    f = find.find(page, OWN)[0]
    assert keys.normalise(f["target"]) == "AB 12 (162X)"
    assert resolve.served_date(resolve._anchored(f["quoted"], f["target"])) == "1996-05-29"


def test_a_document_with_no_page_markers_is_one_page():
    doc = find.findings_document("EP 445, slip op. at 3.", document_sha256="d" * 64, own=OWN)
    assert doc["pages_read"] == 1 and doc["findings"][0]["page"] == 1
