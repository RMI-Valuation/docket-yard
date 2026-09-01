"""`docketyard.citator.find` — the finder, and the two things it must not do.

It must not filter on the registry (ADR 0017 D2), and it must not drop a caption (the
operator's decision, 2026-09-01). Both are ways of discarding a row, and both were how the
measured tool behaved.
"""

from docketyard.citator import find, keys

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


def test_a_document_with_no_page_markers_is_one_page():
    doc = find.findings_document("EP 445, slip op. at 3.", document_sha256="d" * 64, own=OWN)
    assert doc["pages_read"] == 1 and doc["findings"][0]["page"] == 1
