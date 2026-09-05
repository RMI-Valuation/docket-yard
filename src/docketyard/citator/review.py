"""The review queue: what a human is owed, and what their decision writes.

ADR 0016 gives a reviewer an identity; ADR 0017 D5 says what is left to one, in its order of
yield: the exposed class and every rule-2 repair, then unresolved docket targets whose number
falls inside the held record, then same-docket citations naming a document that did not
resolve, then every reader report. Migration 0015 holds the reviewer and the action.

**A QUEUE IS A QUERY.** Nothing stores queue items. A stored queue is a second source of
truth that has to be kept in step with a registry that MOVES — waves 2-3 are still adding
dockets, so a target that could not resolve last week resolves this week and leaves the
queue on its own. A derived queue notices; a table would hold yesterday's answer and nobody
would know it had.

**A decision writes a `human` assertion, and the projection never learns that a review
happened.** `docs/schema-draft.md` § 7: an acceptance writes a human resolution agreeing with
the model's, a rejection writes a human does-not-resolve, a correction writes the corrected
one. The new row supersedes the live one, every projection keeps reading
`superseded_by IS NULL`, and `review_action` records who and why. `escalated` is the only
decision that produces nothing, and its NULLs say so.
"""

import json

from docketyard.alerts import vault
from docketyard.citator import keys, methods, resolve
from docketyard.ingest import dockets
from docketyard.store.db import utcnow
from docketyard.web import urls

# The queue's own convention version: WHAT EVIDENCE WAS SHOWN and under which rules the
# decision was made. A reviewer who saw less than today's reviewer saw decided a different
# question, so it is stored on every action rather than inferred from its date.
#
# It is `methods.HUMAN_VERSION` and not a second constant: the registry row `declare` writes
# and the assertion row `decide` writes must carry the SAME string, because the projection
# joins them on it — and a mismatch would drop every human answer through an INNER join
# without saying anything.
QUEUE_VERSION = methods.HUMAN_VERSION

_KEY_COLS = ("citing_document", "page", "target_kind", "target_key")


def _cols(alias: str) -> str:
    """The four key columns, EVERY ONE QUALIFIED. `f"{alias}.{_KEY}"` on a bare comma list
    qualifies only the first — the same unqualified-name trap the multi-agent review found
    in `docs/citator-query-2.sql`, where `s.x = x` read as `s.x = s.x` and one veto emptied
    the whole result. Building the list is how it stops being possible to write."""
    return ", ".join(f"{alias}.{c}" for c in _KEY_COLS)


def _on(a: str, b: str) -> str:
    return " AND ".join(f"{a}.{c} = {b}.{c}" for c in _KEY_COLS)


def _unanswered(alias: str, queue: str) -> str:
    """An item is cleared by an answer IN ITS OWN QUEUE, and by nothing else.

    Not "does a live human resolution exist": a key can sit in two queues at once — the
    unresolved and the exposed, say — and answering one question would then clear the other,
    authorising publication on a fusion nobody was ever shown. `review_action.queue` records
    WHICH QUESTION was asked, which is the whole reason that column exists.
    """
    return (
        f"NOT EXISTS (SELECT 1 FROM review_action a WHERE a.queue = '{queue}'"
        # an ESCALATION does not clear the item. It records that somebody looked and could
        # not settle it, which is not the same as settling it — and with no escalation queue
        # built, dropping it here would lose it silently.
        f" AND a.decision <> 'escalated'"
        f" AND a.target_table = 'citation_resolution' AND a.superseded_by IS NULL"
        f" AND a.target_key = {alias}.citing_document || '/' || {alias}.page || '/'"
        f" || {alias}.target_kind || '/' || {alias}.target_key)"
    )


def _decided_better(alias: str) -> str:
    """A key some other live rule already resolves. Live resolutions accumulate per
    (method, version, channel) — ADR 0018 D7 requires it, since rule 1 writes a row WHEN IT
    FAILS and rule 2 writes a separate one — so "a live row with outcome X" is not "the row
    that currently decides". Without this the stale rule-1 `unresolved` row sits in the queue
    claiming the registry cannot resolve an edge that is projecting."""
    return (
        f"NOT EXISTS (SELECT 1 FROM citation_resolution b WHERE {_on('b', alias)}"
        f" AND b.superseded_by IS NULL AND b.outcome IN ('resolved', 'repaired')"
        f" AND b.resolution_id <> {alias}.resolution_id)"
    )


def _base(queue: str, alias: str = "r") -> str:
    return (
        f"SELECT {_cols(alias)}, {alias}.cited_docket_id, g.cited_raw, g.quoted_passage"
        f" FROM citation_resolution {alias}"
        f" JOIN citation c ON {_on('c', alias)} AND c.superseded_by IS NULL"
        f" JOIN citation_reading g ON {_on('g', alias)}"
        f" AND g.reading_channel = {alias}.reading_channel AND g.superseded_by IS NULL"
        f" WHERE {alias}.superseded_by IS NULL AND {_unanswered(alias, queue)}"
    )


# Each queue is one predicate over live rows, minus whatever a human has already answered.
# The order is ADR 0017 D5's order of yield, and the CLI keeps it.
QUEUES = {
    # the exposed class: a docket number a fused footnote marker could explain, which
    # resolved CONFIDENTLY and would otherwise reach a page indistinguishable from a clean
    # edge. ADR 0017 D2 sends it here instead.
    "citation_exposed": (
        _base("citation_exposed")
        + " AND r.outcome IN ('resolved', 'repaired')"
        + f" AND EXISTS (SELECT 1 FROM citation_judgement j WHERE {_on('j', 'r')}"
        " AND j.judgement = 'exposed' AND j.value = 'true' AND j.superseded_by IS NULL)"
    ),
    # every rule-2 repair: the raw failed and a stripped reading resolved, so a human is
    # owed the question even though the edge publishes meanwhile (ADR 0018 D7 ranks it)
    "citation_repaired": (_base("citation_repaired") + " AND r.outcome = 'repaired'"),
    # ADR 0017 D5's second item: unresolved targets whose number falls INSIDE the held
    # record. An ICC-era number is expected to fail and is not queued — queueing it would
    # train a reviewer to skim, which is the argument the exposure test's own narrowing
    # rests on. The range test is `in_the_held_record`, below.
    "citation_unresolved": (
        # and not a key some other live rule already resolves: the stale rule-1 row
        _base("citation_unresolved") + " AND r.outcome = 'unresolved' AND " + _decided_better("r")
    ),
}


def in_the_held_record(con, key: str) -> bool:
    """Is this unresolved target's number inside the range the registry holds for its prefix?

    ADR 0017 D5 queues an unresolved target only when it is — an ICC-era number is EXPECTED
    to fail, and a queue full of expected failures trains a reviewer to skim past the real
    ones. Read in Python rather than SQL because the prefix and sequence live inside the
    normalised key, and parsing it is `keys`' job and nobody else's.
    """
    m = keys.DOCKET.match(key)
    if not m:
        return False
    row = con.execute(
        "SELECT MIN(sequence), MAX(sequence) FROM docket WHERE prefix = ?", (m.group(1),)
    ).fetchone()
    return bool(row and row[0] is not None and row[0] <= int(m.group(2)) <= row[1])


def grant(con, email: str, credit_name: str, note: str, *, counts_public: bool = False) -> int:
    """Give a person the reviewer grant, or re-grant one that was withdrawn.

    THE OPERATOR IS REVIEWER ZERO (ADR 0016), and the pre-table `human` rows — the party
    seed, the joins, the corrections — are NOT re-attributed to that id. 0016 says they are;
    doing it would be an UPDATE on provenance (break A2) and a synthetic review action would
    falsify what happened. `schema-draft.md` § 7's rule stands in its place, recorded as the
    operator's decision of 2026-09-01: a `human` assertion no live review action names is
    the operator's.

    THE OPERATOR DOES THIS BY HAND, and there is no self-service (ADR 0016). The address is
    hashed and sealed with the same vault every other account uses (ADR 0014), so this needs
    the key — while `decide` does not, because a review never touches an address. That split
    is deliberate: reviewing works on a box that cannot read a single email.

    `credit_name` is mandatory. There is no anonymous review: a reviewer chooses how they are
    shown, but is always shown (the operator's amendment on acceptance, 2026-08-28).
    """
    if not credit_name.strip():
        raise ValueError("a credit name is mandatory: there is no anonymous review")
    v = vault.current()
    address = vault.normalise_email(email)
    existing = con.execute(
        "SELECT reviewer_id FROM reviewer WHERE email_hash = ?", (v.hash(address),)
    ).fetchone()
    if existing:
        # a RE-GRANT clears the withdrawal; it does not mint a second id, because provenance
        # points at the id for ever (ADR 0015's discipline, ADR 0016's "past rows stand")
        con.execute(
            "UPDATE reviewer SET revoked_at = NULL, credit_name = ?, granted_note = ?"
            " WHERE reviewer_id = ?",
            (credit_name.strip(), note, existing[0]),
        )
        return existing[0]
    return con.execute(
        "INSERT INTO reviewer (email_hash, email_enc, credit_name, counts_public, granted_at,"
        " granted_note) VALUES (?, ?, ?, ?, ?, ?)",
        (
            v.hash(address),
            v.seal(address),
            credit_name.strip(),
            int(counts_public),
            utcnow(),
            note,
        ),
    ).lastrowid


def revoke(con, reviewer_id: int) -> int:
    """Withdraw the grant, and end every live session with it. Past rows stay attributed.

    `signin.whoami` re-checks `revoked_at` on every request, so the withdrawal bites without
    this — but leaving the rows would leave live tokens naming a reviewer nobody may act as,
    and ADR 0016's "a role that can be withdrawn needs a way to be withdrawn" is better
    served by the token being gone than by every future reader of it remembering to check.
    Returns the number of sessions ended.
    """
    from docketyard.citator import signin

    if (
        con.execute("SELECT 1 FROM reviewer WHERE reviewer_id = ?", (reviewer_id,)).fetchone()
        is None
    ):
        # a mistyped id used to print "revoked; 0 sessions ended" and exit 0 while the real
        # reviewer kept both grant and session
        raise ValueError(f"no reviewer {reviewer_id}")
    con.execute("UPDATE reviewer SET revoked_at = ? WHERE reviewer_id = ?", (utcnow(), reviewer_id))
    return signin.end_all_sessions(con, reviewer_id)


def find_docket(con, printed: str) -> tuple[int, str] | None:
    """A docket a reviewer TYPED, as (id, raw). `AB 124`, `AB-124`, `Docket No. AB 124`,
    `AB 1182-X` and `STB Finance Docket No. 36873` all find the same rows they name: a human
    should not have to know an internal id — or the citation class — to correct one.

    IF THE STRING PARSES AS AN IDENTITY, THAT IDENTITY IS THE ANSWER, held or not. The
    citation grammar gets a look only when it does not parse at all, and that order is the
    whole fix. `keys.normalise` alone was answering three ways that a reviewer could not
    see (verified 2026-09-04):

      * **The site's own printed form of a suffixed parent found the PARENT, silently.**
        `urls.printed_docket` renders `AB_1182_0_X` as `AB 1182-X`; `keys.DOCKET` cannot take
        a hyphen between the digits and the letter, so the suffix fell off the end and
        `AB 1182` — a different held proceeding — came back resolved and confident under the
        reviewer's credit name. Measured against the store 2026-09-04: 2,711 held dockets
        are of that shape and 2,646 of them named a DIFFERENT held docket.
      * **A docket outside the citation class could not be named at all.** `normalise` ships
        ONE class by ADR 0017 D1 and returns None for the other 13 prefixes, so `S5M 1-A` was
        refused as "not a docket this record holds" when the record holds it. 655 dockets can
        never be cited TO; a reviewer correcting a citation that named one wrongly still has
        to be able to name it.
      * **The site's own long citation form was unreadable.** `urls.cite_docket` prints
        `STB Finance Docket No. 36873`, which carries no `FD` token for `keys.DOCKET` to
        match. `urls.lookup` knows the Board's long names; the citation grammar does not.

    Nothing here widens the citation class: this is what a PERSON may type, resolved through
    the record's own identity parser, and no key, `KEY_VERSION` or measured figure moves.

    Returns None when nothing matches, which the caller must refuse: a correction that names
    no docket is worse than no correction, because it publishes under a reviewer's name.
    """
    identity = urls.lookup(printed or "")
    if identity is not None:
        docket_id = dockets.find_docket(con, identity)
    else:
        # not identity-shaped: `AB1296` with no separator is the citation grammar's, not
        # `parse_docket_id`'s, and refusing it here would be a regression for no gain
        key = keys.normalise(printed or "")
        docket_id = None if key is None else keys.registry(con).get(key)
    if docket_id is None:
        return None
    return (docket_id, _raw_docket(con, docket_id))


def _raw_docket(con, docket_id: int) -> str:
    """Both callers' ids come from a SELECT over `docket` and `raw_docket` is NOT NULL, so
    there is no miss to fall back from — an empty string here would be a corrupt store, and
    the caller would rather see it than a label it invented."""
    row = con.execute("SELECT raw_docket FROM docket WHERE docket_id = ?", (docket_id,)).fetchone()
    return row[0] if row else ""


def owed(con, queue: str) -> int:
    """How many items a queue really holds. `len(pending(..., limit=N))` reports N once the
    queue passes N and stays there — and the home page's whole job is saying how much is
    owed, so a number that stops moving is worse than no number."""
    return len(pending(con, queue, limit=None))


def pending(con, queue: str, limit: int | None = 50) -> list[dict]:
    """One queue, oldest key first, with the evidence beside the question (ADR 0016).

    Rendering a queue writes NOTHING. ADR 0011's promise to readers covers reviewers too:
    the surfaces log the decision and nothing else — no page views, no timing beyond the
    action's own timestamp.
    """
    if queue not in QUEUES:
        raise ValueError(f"no such queue: {queue}")
    rows = [
        {
            "target_key_rendered": keys.render(doc, page, kind, key),
            "citing_document": doc,
            "page": page,
            "target_kind": kind,
            "target_key": key,
            "cited_docket_id": docket_id,
            "cited_raw": raw,  # what the page PRINTED, for the human reading below
            "quoted_passage": passage,
        }
        for doc, page, kind, key, docket_id, raw, passage in con.execute(
            QUEUES[queue] + " ORDER BY r.citing_document, r.page, r.target_key"
        )
    ]
    if queue == "citation_unresolved":
        rows = [r for r in rows if in_the_held_record(con, r["target_key"])]
    return rows if limit is None else rows[:limit]


def decide(
    con,
    *,
    reviewer_id: int,
    queue: str,
    item: dict,
    decision: str,
    note: str,
    cited_docket_id: int | None = None,
) -> int:
    """Record one decision: the assertion first, then the action naming it, in ONE
    transaction. Returns the action id.

    The order matters and § 7 fixes it: `produced_key` is written in the same transaction as
    the row it names, and it is THE authoritative link. There is no backward pointer from the
    assertion to the action, because two pointers can disagree and one cannot.
    """
    # `confidence = 1.0` on both human rows is a CHOICE, recorded here rather than left to
    # be read off the number: ADR 0018 D8 says only that a human review HAS a confidence and
    # lacks a benchmark. A reviewer who was unsure should escalate, not stamp a fraction, so
    # the value a decision writes is certainty by construction.
    if decision not in ("accepted", "rejected", "corrected", "escalated"):
        raise ValueError(f"no such decision: {decision}")
    grant = con.execute(
        "SELECT revoked_at FROM reviewer WHERE reviewer_id = ?", (reviewer_id,)
    ).fetchone()
    if grant is None:
        raise ValueError(f"no reviewer {reviewer_id}")
    if grant[0] is not None:
        # a withdrawn grant ends NEW actions; past rows stand and stay attributed (ADR 0016)
        raise ValueError(f"reviewer {reviewer_id} was revoked at {grant[0]}")

    now = utcnow()
    # RE-DERIVED, not taken from the dict: `produced_key` is the authoritative link, and a
    # caller handing over an inconsistent item would make it name a different key than the
    # row this function actually wrote.
    rendered = keys.render(
        item["citing_document"], item["page"], item["target_kind"], item["target_key"]
    )
    produced_table = produced_key = None

    if decision != "escalated":
        # ADR 0018 D4's typed outcome, from the human's answer rather than from a rule:
        # accepted keeps what the machine said, corrected names a different docket, rejected
        # says it resolves to nothing at all and the edge stops projecting.
        # ACCEPTED MEANS "THE STORED ANSWER IS RIGHT", and on the unresolved queue the
        # stored answer is `unresolved` — so accepting there asserts unresolvable, not
        # resolved-to-nothing. Without this the map wrote `resolved` with a NULL docket and
        # tripped migration 0014's outcome CHECK mid-transaction, surfacing as a traceback.
        stored = con.execute(
            "SELECT outcome FROM citation_resolution WHERE citing_document = ? AND page = ?"
            " AND target_kind = ? AND target_key = ? AND superseded_by IS NULL"
            " AND confidence_state <> 'human' ORDER BY resolution_id DESC LIMIT 1",
            (item["citing_document"], item["page"], item["target_kind"], item["target_key"]),
        ).fetchone()
        outcome, docket_id = {
            "accepted": (
                (stored[0] if stored else "unresolved"),
                item["cited_docket_id"],
            ),
            "corrected": ("resolved", cited_docket_id),
            "rejected": ("unresolved", None),
        }[decision]
        if decision == "corrected" and docket_id is None:
            raise ValueError("a corrected decision must name the docket it corrects to")
        if outcome not in ("resolved", "repaired"):
            docket_id = None  # 0014's CHECK: an unresolved row names no docket
        # retire the machine's live answer, then assert the human's over the same key
        # EVERY live resolution on the key, the previous human answer included: ADR 0016's
        # "a later review supersedes" means a review may amend a review, and § 7 refines § 5
        # to say exactly that — a `human` row is never superseded by a MODEL pass, and a
        # review action is what may supersede it.
        live = con.execute(
            "SELECT resolution_id FROM citation_resolution WHERE citing_document = ?"
            " AND page = ? AND target_kind = ? AND target_key = ? AND superseded_by IS NULL",
            (item["citing_document"], item["page"], item["target_kind"], item["target_key"]),
        ).fetchall()
        for (rid,) in live:
            con.execute(
                "UPDATE citation_resolution SET superseded_by = ? WHERE resolution_id = ?",
                (rid, rid),
            )
        # ADR 0007's block, in full: schema-draft.md § 7 promises "the produced row's ADR
        # 0007 block is method='human', its source_location keeps ADR 0007's meaning (WHERE
        # IN THE SOURCE)". The reviewer's id goes in `source_location` because ADR 0016 calls
        # it "method detail the reviewer's id" and there is no column for it — the
        # `review_action` join answers "who" authoritatively, and this makes the row itself
        # legible without one.
        cur = con.execute(
            "INSERT INTO citation_resolution (citing_document, page, target_kind, target_key,"
            " method, method_version, reading_channel, outcome, cited_docket_id,"
            " asserted_from_document, source_location, asserted_at, confidence,"
            " confidence_state)"
            " VALUES (?, ?, ?, ?, 'human', ?, 'human', ?, ?, ?, ?, ?, 1.0, 'human')",
            (
                item["citing_document"],
                item["page"],
                item["target_kind"],
                item["target_key"],
                QUEUE_VERSION,
                outcome,
                docket_id,
                item["citing_document"],
                json.dumps(
                    {"page": item["page"], "reviewer_id": reviewer_id, "queue": queue},
                    sort_keys=True,
                ),
                now,
            ),
        )
        for (rid,) in live:
            con.execute(
                "UPDATE citation_resolution SET superseded_by = ? WHERE resolution_id = ?",
                (cur.lastrowid, rid),
            )
        # the projection's reading join is INNER and channel-matched, so a `human` resolution
        # with no `human` reading projects NOTHING. Migration 0014's header states that as a
        # writer's invariant; this is the writer, so it is met here rather than owed.
        _human_reading(con, item, now, reviewer_id)
        produced_table, produced_key = "citation_resolution", rendered

    # a later review supersedes, never sits beside: one live action per (queue, target)
    prior = con.execute(
        "SELECT action_id FROM review_action WHERE queue = ? AND target_table = ?"
        " AND target_key = ? AND superseded_by IS NULL",
        (queue, "citation_resolution", rendered),
    ).fetchall()
    for (aid,) in prior:
        con.execute("UPDATE review_action SET superseded_by = ? WHERE action_id = ?", (aid, aid))
    action = con.execute(
        "INSERT INTO review_action (reviewer_id, queue, target_table, target_keyed,"
        " target_key, target_key_version, method_version, decision, detail, produced_table,"
        " produced_key, asserted_at)"
        " VALUES (?, ?, 'citation_resolution', 'natural', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            reviewer_id,
            queue,
            rendered,
            keys.KEY_VERSION,
            QUEUE_VERSION,
            decision,
            json.dumps({"note": note, "resolver": resolve.RESOLVER}, sort_keys=True),
            produced_table,
            produced_key,
            now,
        ),
    ).lastrowid
    for (aid,) in prior:
        con.execute("UPDATE review_action SET superseded_by = ? WHERE action_id = ?", (action, aid))
    return action


def _human_reading(con, item: dict, now: str, reviewer_id: int) -> None:
    """A `human` reading carrying the passage the reviewer actually read.

    Not decoration: `project.py`'s reading join is inner and channel-matched, so without this
    row the human's resolution wins the ranking and then projects nothing at all — a review
    that silently changed the answer to "no edge".
    """
    where = (
        "citing_document = ? AND page = ? AND target_kind = ? AND target_key = ?"
        " AND reading_channel = 'human' AND superseded_by IS NULL"
    )
    args = (item["citing_document"], item["page"], item["target_kind"], item["target_key"])
    if con.execute(f"SELECT 1 FROM citation_reading WHERE {where}", args).fetchone():
        return
    con.execute(
        "INSERT INTO citation_reading (citing_document, page, target_kind, target_key,"
        " reading_channel, cited_raw, quoted_passage, asserted_from_document,"
        " source_location, method, method_version, asserted_at, confidence,"
        " confidence_state) VALUES (?, ?, ?, ?, 'human', ?, ?, ?, ?, 'human', ?, ?,"
        " 1.0, 'human')",
        (
            *args,
            # what the page PRINTED, carried across from the reading the reviewer was shown.
            # `target_key` here would display `EP 445` where an unreviewed edge displays
            # `Docket No. EP 445` — 0014 defines the column as "the string as THIS reading
            # printed it", and `project.py` selects it for the reader.
            item["cited_raw"],
            item["quoted_passage"],
            item["citing_document"],
            json.dumps({"page": item["page"], "reviewer_id": reviewer_id}, sort_keys=True),
            QUEUE_VERSION,
            now,
        ),
    )


def credit(con, target_key_rendered: str) -> str | None:
    """ "Who reviewed this?" — § 7's authoritative join, and the only supported one.

    It reads `produced_table` + `produced_key`, never a pointer on the assertion, because two
    pointers can disagree and one cannot. Returns the credit name, which is MANDATORY: there
    is no anonymous review (ADR 0016, the operator's amendment on acceptance).
    """
    # `produced_key` is a rendered KEY, not a row id, so more than one live action can name
    # it — one per queue. The newest wins, and it is ordered rather than left to whichever
    # row SQLite hands back first.
    row = con.execute(
        "SELECT r.credit_name FROM review_action a JOIN reviewer r USING (reviewer_id)"
        " WHERE a.produced_table = 'citation_resolution' AND a.produced_key = ?"
        " AND a.superseded_by IS NULL ORDER BY a.action_id DESC LIMIT 1",
        (target_key_rendered,),
    ).fetchone()
    return row[0] if row else None
