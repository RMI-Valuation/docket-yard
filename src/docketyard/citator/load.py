"""Findings from one document become rows in four families, or an honest count of why not.

The interchange the enrichment box POSTs back (`docs/architecture.md`) is one JSON object
per document:

    {
      "document_sha256": "<64 hex>",       the CITING DOCUMENT: bytes, never a record row
      "method": "regex-docket-cite",       who found these
      "method_version": "2026-08-30",
      "reading_channel": "text-layer",     FK reading_vocab
      "reading_method": null,              the OCR engine, and its version, when the channel
      "reading_method_version": null,      is 'ocr' — payload, never key (ADR 0018 D3)
      "pages_read": 33,                    so "read and found nothing" is not "not yet read"
      "findings": [
        {"page": 4, "target": "EP 328", "quoted": "... the line the target sat on ..."}
      ]
    }

Anchoring on `document_sha256` and not on a decision id is ADR 0018 D2 and
`schema-draft.md`'s "citations come from the attachment, never from the cell": a citation is
a fact about bytes. One document may belong to two works, and the fold at projection is
where that becomes two citing works — correctly, not as a doubling.

WHAT THIS DOES NOT DO, because ADR 0017 D2 moved it: it does not filter on the registry.
Every docket-shaped finding is stored, resolved or not. An unresolved target is a real edge
bound for a human, and a finder that could not emit one would empty that queue by
construction.
"""

from dataclasses import dataclass, field

from docketyard.citator import judge, keys, methods, resolve
from docketyard.store.db import dump_json, utcnow


class NotTheOwner(RuntimeError):
    """A findings document whose method does not own the class it is writing into. Two
    extractors emitting the same target on the same page would collide on a key with no
    method in it, so one row would be dropped or the edge counted twice (ADR 0018 D1)."""


@dataclass
class Loaded:
    """What one document's pass did, in the terms `extraction_run` records."""

    document_sha256: str = ""
    emitted: int = 0
    out_of_class: int = 0
    resolved: int = 0
    repaired: int = 0
    unresolved: int = 0
    exposed: int = 0
    unchanged: int = 0  # this exact pass had already asserted the key: a restart, not a
    human_held: int = 0  # second edge. And a `human` row a model pass may never supersede.
    review: list[str] = field(default_factory=list)  # rendered keys, for ADR 0017 D5's queues


def _live_citation(con, sha: str, page: int, key: str):
    """The live extraction assertion on this key, if any."""
    return con.execute(
        "SELECT citation_id, method, method_version, confidence_state FROM citation"
        " WHERE citing_document = ? AND page = ? AND target_kind = 'stb' AND target_key = ?"
        " AND superseded_by IS NULL",
        (sha, page, key),
    ).fetchone()


def _retire(con, table: str, id_col: str, row_id: int) -> None:
    """0006_parties.sql's order, forced by the partial live index: retire the old row by
    pointing it at ITSELF so the replacement can take the key, then repoint it once the new
    id exists. Inserting first fails, because for that instant two rows on one key would be
    live. The caller holds the transaction — a crash between the two steps leaves a
    self-pointer that cannot be told apart from a deliberate retirement."""
    con.execute(f"UPDATE {table} SET superseded_by = ? WHERE {id_col} = ?", (row_id, row_id))


def _supersede_if_changed(
    con,
    *,
    table: str,
    id_col: str,
    where: str,
    where_args: tuple,
    compare: str,
    values: tuple,
    insert: str,
    insert_args: tuple,
) -> bool:
    """Write an assertion only if it says something the live row does not. Returns True when
    a row was written.

    The alternative — `INSERT OR IGNORE` on the live key — keeps the FIRST answer for ever,
    and for a target the registry did not yet hold the first answer is `unresolved`. Waves
    2-3 are still adding dockets, so that would quietly cap what the citator can ever show.
    """
    live = con.execute(
        f"SELECT {id_col}, {compare} FROM {table} WHERE {where} AND superseded_by IS NULL",
        where_args,
    ).fetchone()
    if live is not None and tuple(live[1:]) == tuple(values):
        return False  # the same answer, already asserted at this method and version
    if live is not None:
        _retire(con, table, id_col, live[0])
    cur = con.execute(insert, insert_args)
    if live is not None:
        con.execute(
            f"UPDATE {table} SET superseded_by = ? WHERE {id_col} = ?", (cur.lastrowid, live[0])
        )
    return True


def load_document(con, doc: dict, held: dict[str, int], stamps: dict) -> Loaded:
    """One findings document, through citation_key and the four live families.

    `stamps` is `methods.stamp(con)`: {stage: (measurement_id, precision)}. THE CONFIDENCE
    AND THE POINTER COME FROM THE SAME ROW, so no figure is written here or anywhere else
    in this package — a constant would be a second home for a number `class_measurement`
    already holds, and the two would drift. Every assertion carries the measurement for ITS
    OWN stage; the schema will not accept another's.

    Returns the counts rather than printing them: ADR 0018 D1 promises that a finding
    outside its method's class is an auditable number, and `extraction_run` below is where
    that promise is kept.
    """
    sha = doc["document_sha256"]
    channel = doc.get("reading_channel", methods.CHANNEL_TEXT)
    method, version = doc["method"], doc["method_version"]
    now = utcnow()
    out = Loaded(document_sha256=sha)

    # ADR 0018 D1's one-owner rule, enforced where migration 0014 says it must be: "the
    # extractor looks up its own class, finds no owner row and must refuse to insert." The
    # index constrains DECLARATIONS; only this lookup constrains ROWS, and without it a
    # findings file naming any method at all writes into the class regex owns.
    declared = methods.owner(con, "stb", "docket")
    if declared is None or tuple(declared) != (method, version):
        raise NotTheOwner(
            f"{method}@{version} does not own (stb, docket); "
            f"{'nothing does' if declared is None else f'{declared[0]}@{declared[1]} does'}"
        )

    # A target printed several times on one page is ONE key, so the passages are collected
    # before any row is written and the quoted text is joined. The shipping finder emits at
    # most one finding per (page, key) today, so this joins nothing — it is here because the
    # key permits multiplicity and the span test must see all of it if it ever arrives.
    passages: dict[tuple[int, str], list[str]] = {}
    printed: dict[tuple[int, str], str] = {}
    for finding in doc.get("findings", []):
        key = keys.normalise(finding.get("target", ""))
        if key is None or not keys.DOCKET_KEY.match(key):
            out.out_of_class += 1  # counted, never silently dropped (ADR 0018 D1)
            continue
        at = (int(finding["page"]), key)
        passages.setdefault(at, []).append(finding.get("quoted", ""))
        printed.setdefault(at, finding.get("target", ""))

    for (page, key), quotes in sorted(passages.items()):
        passage = " | ".join(q for q in quotes if q)
        out.emitted += 1
        con.execute(
            "INSERT OR IGNORE INTO citation_key (citing_document, page, target_kind,"
            " target_key, key_version, first_seen_at) VALUES (?, ?, 'stb', ?, ?, ?)",
            (sha, page, key, keys.KEY_VERSION, now),
        )
        # A BACKFILL IS RESTARTABLE, so a pass must run twice over one document without
        # minting a second assertion or a second edge. `unchanged` does NOT skip the rest of
        # the loop: the families below are keyed by reading channel, and an OCR pass over a
        # document already read from its text layer must still write its own rows (ADR 0018
        # D3 designs `citation_reading` around exactly that second row).
        live = _live_citation(con, sha, page, key)
        unchanged = live is not None and (live[1], live[2]) == (method, version)
        if unchanged:
            out.unchanged += 1
        elif live is not None and live[3] == "human":
            # ADR 0017 D5: a review writes a `human` row and A MODEL PASS MAY NEVER
            # SUPERSEDE ONE. Migration 0014's trigger would refuse it; refusing here makes
            # it a counted outcome rather than an exception mid-batch.
            out.human_held += 1
            continue
        else:
            if live is not None:
                _retire(con, "citation", "citation_id", live[0])
            cur = con.execute(
                "INSERT INTO citation (citing_document, page, target_kind, target_key,"
                " asserted_from_document, method, method_version, asserted_at, confidence,"
                " confidence_state, measured_target, score_row_id)"
                " VALUES (?, ?, 'stb', ?, ?, ?, ?, ?, ?, 'measured', 'citation', ?)",
                (
                    sha,
                    page,
                    key,
                    sha,
                    method,
                    version,
                    now,
                    stamps["citation"][1],
                    stamps["citation"][0],
                ),
            )
            if live is not None:  # step three: the retired row points at its replacement
                con.execute(
                    "UPDATE citation SET superseded_by = ? WHERE citation_id = ?",
                    (cur.lastrowid, live[0]),
                )
        # the reading's key is the CHANNEL, so a re-read at a better engine matches and
        # supersedes rather than doubling the live readings (ADR 0018 D3)
        old_reading = con.execute(
            "SELECT reading_id FROM citation_reading WHERE citing_document = ? AND page = ?"
            " AND target_kind = 'stb' AND target_key = ? AND reading_channel = ?"
            " AND superseded_by IS NULL",
            (sha, page, key, channel),
        ).fetchone()
        if old_reading:
            _retire(con, "citation_reading", "reading_id", old_reading[0])
        new_reading = con.execute(
            "INSERT INTO citation_reading (citing_document, page, target_kind, target_key,"
            " reading_channel, reading_method, reading_method_version, cited_raw,"
            " quoted_passage, source_location, asserted_from_document, method,"
            " method_version, asserted_at, confidence, confidence_state, measured_target,"
            " score_row_id)"
            " VALUES (?, ?, 'stb', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'measured',"
            " 'citation', ?)",
            (
                sha,
                page,
                key,
                channel,
                doc.get("reading_method"),
                doc.get("reading_method_version"),
                printed[(page, key)],
                passage,
                dump_json({"page": page}),
                sha,
                method,
                version,
                now,
                stamps["citation"][1],
                stamps["citation"][0],
            ),
        )
        if old_reading:
            con.execute(
                "UPDATE citation_reading SET superseded_by = ? WHERE reading_id = ?",
                (new_reading.lastrowid, old_reading[0]),
            )

        # THE REGISTRY GROWS. `citation_resolution`'s key carries the resolver's method and
        # version and NOT the run's, so an `INSERT OR IGNORE` here would silently keep the
        # first answer for ever — and the first answer for a target the registry did not yet
        # hold is `unresolved`. Waves 2-3 are still adding dockets, so ADR 0017 D2's "store
        # it unresolved, resolve it later" would have had no later. Instead the live row is
        # compared and superseded when the ANSWER changed.
        r = resolve.resolve(key, held)
        _supersede_if_changed(
            con,
            table="citation_resolution",
            id_col="resolution_id",
            where=(
                "citing_document = ? AND page = ? AND target_kind = 'stb' AND target_key = ?"
                " AND method = ? AND method_version = ? AND reading_channel = ?"
            ),
            where_args=(sha, page, key, resolve.RESOLVER, r.method, channel),
            compare="outcome, cited_docket_id, cited_decision_id",
            values=(r.outcome, r.docket_id, r.decision_id),
            insert=(
                "INSERT INTO citation_resolution (citing_document, page, target_kind,"
                " target_key, method, method_version, reading_channel, outcome,"
                " cited_docket_id, cited_decision_id, asserted_from_document, asserted_at,"
                " confidence, confidence_state, measured_target, score_row_id)"
                " VALUES (?, ?, 'stb', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'measured',"
                " 'citation_resolution', ?)"
            ),
            insert_args=(
                sha,
                page,
                key,
                resolve.RESOLVER,
                r.method,
                channel,
                r.outcome,
                r.docket_id,
                r.decision_id,
                sha,
                now,
                stamps["citation_resolution"][1],
                stamps["citation_resolution"][0],
            ),
        )
        # The span judgement is a STORED ASSERTION (ADR 0017 D4) — it decides what every
        # published edge IS, so it carries its own method, version and confidence and is
        # never a predicate computed inside a view.
        #
        # A `false` judgement is written UNMEASURED, and that is migration 0014's own limit
        # made real: the projection precision speaks for what the pair SHOWS, so it stands
        # behind a `true`. Stamping a suppression with it would quote the pair for a decision
        # the pair does not make — and `class_vocab` holds ('citation_judgement',
        # 'span_names_document') empty precisely because that figure does not exist yet. The
        # outcome is identical either way: an unmeasured judgement is filtered out of the
        # projection's candidate set, `sp.value` is NULL, and the default suppresses.
        names = judge.names_document(passage)
        _supersede_if_changed(
            con,
            table="citation_judgement",
            id_col="judgement_id",
            where=(
                "citing_document = ? AND page = ? AND target_kind = 'stb' AND target_key = ?"
                " AND judgement = 'span_names_document' AND method = ? AND method_version = ?"
                " AND reading_channel = ?"
            ),
            where_args=(sha, page, key, methods.SPAN_METHOD, judge.SPAN_VERSION, channel),
            compare="value",
            values=("true" if names else "false",),
            insert=(
                "INSERT INTO citation_judgement (citing_document, page, target_kind,"
                " target_key, judgement, value_domain, value, method, method_version,"
                " reading_channel, asserted_from_document, asserted_at, confidence,"
                " confidence_state, measured_target, score_row_id)"
                " VALUES (?, ?, 'stb', ?, 'span_names_document', 'boolean', ?, ?, ?, ?, ?, ?,"
                " ?, ?, ?, ?)"
            ),
            insert_args=(
                sha,
                page,
                key,
                "true" if names else "false",
                methods.SPAN_METHOD,
                judge.SPAN_VERSION,
                channel,
                sha,
                now,
                *(
                    (stamps["projection"][1], "measured", "projection", stamps["projection"][0])
                    if names
                    else (0, "unmeasured", None, None)
                ),
            ),
        )

        # THE EXPOSURE TEST IS STORED, not recomputed at read time (migration 0015). It
        # decides whether a published edge reaches a page unreviewed, so it is an assertion
        # with its own method and provenance, exactly as the span test is.
        #
        # It carries its OWN method and version, not the resolver's: the exposure test is a
        # distinct rule whose membership ADR 0017 reconsidered between 3, 5 and 14 before
        # settling on 3, and `registry-match@rule-1` on an exposure judgement is simply false
        # provenance — that method did not make that judgement, and redefining the class
        # would have rewritten every row in place with nothing visible to say so.
        #
        # `unmeasured`, not `measured` and not `not-applicable`: ADR 0017 measures how OFTEN
        # this fires (3 of 225, 3 of 249 emitted), which is a rate and not a precision, so
        # `class_measurement` has nothing for it to point at — but a precision IS measurable,
        # and the review queue this feeds is the instrument that would produce it. So the
        # honest state is "nobody has scored it yet", which is the state the span test's
        # `false` rows already carry. The projection reads this row WITHOUT the confidence
        # predicate in any case: it suppresses, and a suppressor filtered out of the
        # candidate set is silently inert (ADR 0018 D7, on the on-page veto).
        _supersede_if_changed(
            con,
            table="citation_judgement",
            id_col="judgement_id",
            where=(
                "citing_document = ? AND page = ? AND target_kind = 'stb' AND target_key = ?"
                " AND judgement = 'exposed' AND method = ? AND method_version = ?"
                " AND reading_channel = ?"
            ),
            where_args=(
                sha,
                page,
                key,
                resolve.EXPOSURE_METHOD,
                resolve.EXPOSURE_VERSION,
                channel,
            ),
            compare="value",
            values=("true" if r.exposed else "false",),
            insert=(
                "INSERT INTO citation_judgement (citing_document, page, target_kind,"
                " target_key, judgement, value_domain, value, method, method_version,"
                " reading_channel, asserted_from_document, source_location, asserted_at,"
                " confidence, confidence_state) VALUES (?, ?, 'stb', ?, 'exposed', 'boolean',"
                " ?, ?, ?, ?, ?, ?, ?, 0, 'unmeasured')"
            ),
            insert_args=(
                sha,
                page,
                key,
                "true" if r.exposed else "false",
                resolve.EXPOSURE_METHOD,
                resolve.EXPOSURE_VERSION,
                channel,
                sha,
                dump_json({"page": page}),
                now,
            ),
        )

        if r.outcome == "resolved":
            out.resolved += 1
        elif r.outcome == "repaired":
            out.repaired += 1
        else:
            out.unresolved += 1
        if r.exposed:
            out.exposed += 1
        # ADR 0017 D5, in its order of yield: the exposed class, then every rule-2 repair.
        # These are the keys `citator review list` renders; the queue itself is a QUERY over
        # the store, so this list is a convenience for the operator running the load and
        # never the queue's source of truth.
        if r.exposed or r.outcome == "repaired":
            out.review.append(keys.render(sha, page, "stb", key))

    # ADR 0018 D10. Absence is not a measurement: this row is what separates READ AND FOUND
    # NOTHING from NOT YET READ, and it carries the out-of-class count that makes "not kept"
    # auditable. A re-run at the same version replaces it — it records a pass, not a claim.
    con.execute(
        "INSERT INTO extraction_run (document_sha256, method, method_version, reading_channel,"
        " outcome, pages_read, targets_emitted, targets_out_of_class, ran_at)"
        " VALUES (?, ?, ?, ?, 'read', ?, ?, ?, ?)"
        " ON CONFLICT (document_sha256, method, method_version, reading_channel) DO UPDATE SET"
        " outcome = excluded.outcome, pages_read = excluded.pages_read,"
        " targets_emitted = excluded.targets_emitted,"
        " targets_out_of_class = excluded.targets_out_of_class, ran_at = excluded.ran_at",
        (
            sha,
            method,
            version,
            channel,
            int(doc.get("pages_read") or 0),
            out.emitted,
            out.out_of_class,
            now,
        ),
    )
    return out
