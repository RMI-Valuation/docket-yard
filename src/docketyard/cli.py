"""Command-line entry points: capture | ingest | fetch | walk | poll | status | serve."""

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from docketyard.alerts import build, mail, vault
from docketyard.capture import backfill, documents, poll, walk
from docketyard.capture.stb import (
    DECISIONS,
    DOCKETS,
    ENVIRO_COMMENTS,
    FILINGS,
    PAGE_CLAMP,
    StbClient,
)
from docketyard.ingest import dockets, observations
from docketyard.parties import resolve
from docketyard.store import db, gaps, projections, search, traffic

INGESTERS = {
    DOCKETS: dockets.ingest_capture,
    FILINGS: observations.ingest_capture,
    DECISIONS: observations.ingest_capture,
    ENVIRO_COMMENTS: observations.ingest_capture,
}
# the subcommand name per table, in one place: `capture` and `ingest` offer the same set
TABLE_COMMANDS = (
    ("dockets", DOCKETS),
    ("filings", FILINGS),
    ("decisions", DECISIONS),
    ("comments", ENVIRO_COMMENTS),
)


def _criteria_from(args: argparse.Namespace, spec) -> list[tuple[str, str]]:
    criteria: list[tuple[str, str]] = []
    if args.prefix:
        criteria.append(("docketNum_one", args.prefix))
    if args.sequence is not None:  # `is not None`: --sequence 0 must not silently unfilter
        criteria.append(("docketNum_two", str(args.sequence)))
    if spec is not None:
        if getattr(args, "start", None):
            criteria.append((spec.date_criteria[0], args.start))
        if getattr(args, "end", None):
            criteria.append((spec.date_criteria[1], args.end))
    return criteria


def _run_capture(args: argparse.Namespace, action: str) -> int:
    con = db.connect(args.db)
    client = StbClient(min_interval=args.interval)
    criteria = _criteria_from(args, observations.SPECS.get(action))
    result = walk.capture_slice(
        con,
        client,
        action,
        criteria,
        data_dir=args.data_dir,
        per_page=args.per_page,
        pages=args.pages,
        mode=args.mode,
    )
    return 0 if result.status == "done" else 1


def _run_ingest(args: argparse.Namespace, table_action: str) -> int:
    con = db.connect(args.db)
    ingest = INGESTERS[table_action]
    pending = [args.capture] if args.capture else projections.pending_capture_ids(con, table_action)
    if not pending:
        print("nothing to ingest")
        return 0
    exit_code = 0
    for capture_id in pending:
        try:
            stats = ingest(con, args.data_dir, capture_id)
        except Exception as e:  # noqa: BLE001 — one bad capture must not strand the batch
            con.rollback()  # its partial writes must not ride the next capture's commit
            print(f"capture {capture_id}: FAILED ({type(e).__name__}: {e})")
            exit_code = 1
            continue
        print(f"capture {capture_id}: {stats}")
        if stats.get("unparsed") or stats.get("markup_skipped"):
            print("  WARNING: rows dropped during parse; raw is retained in the capture")
            exit_code = 1
    return exit_code


def _fetch_attachments(args: argparse.Namespace) -> int:
    con = db.connect(args.db)
    client = StbClient(min_interval=args.interval)
    stats = documents.fetch_attachments(
        con,
        args.data_dir,
        client.fetcher(args.data_dir),
        limit=args.limit,
        refresh=args.refresh,
        ingest_mode=args.mode,
    )
    print(stats)
    return 1 if stats["failed"] else 0


def _walk_dockets(args: argparse.Namespace) -> int:
    con = db.connect(args.db)
    client = StbClient(min_interval=args.interval)
    summary = walk.walk_dockets(con, client, data_dir=args.data_dir, redo=args.redo)
    print(summary)
    # a walk that captured nothing is never a success, whatever the per-slice statuses say
    return (
        1
        if summary["partial"] or summary["capped"] or not (summary["done"] + summary["skipped"])
        else 0
    )


def _backfill(args: argparse.Namespace) -> int:
    con = db.connect(args.db)
    client = StbClient(min_interval=args.interval)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else None
    by_name = {name: action for name, action in TABLE_COMMANDS}
    tables = tuple(by_name[n] for n in args.tables) if args.tables else None
    summary = backfill.wave(
        con,
        client,
        args.data_dir,
        start,
        end,
        fetch_limit=args.fetch_limit,
        **({"tables": tables} if tables else {}),
    )
    # judged over the tables THIS wave walked, not a fixed pair: `--tables comments` walks
    # one, and reading the other two would fail the run with a KeyError
    walked = tables or (FILINGS, DECISIONS, ENVIRO_COMMENTS)
    bad = any(summary[a]["partial"] or summary[a]["capped"] for a in walked) or summary[
        "documents"
    ].get("failed")
    return 1 if bad else 0


def _poll(args: argparse.Namespace) -> int:
    if args.days < poll.MIN_WINDOW_DAYS:
        args.parser.error(f"--days must be at least {poll.MIN_WINDOW_DAYS}")
    con = db.connect(args.db)
    client = StbClient(min_interval=args.interval)
    sender = _sender()
    site = os.environ.get("DY_HOST", "docketyard.org")
    if sender is None:
        print("mail not configured (AWS_* / DY_SES_REGION): email alerts wait; webhooks go")

    def alerts():
        return build.run_after_pass(con, sender, site)

    operator = os.environ.get("DY_OPERATOR_EMAIL") or None
    if operator is None:
        print("DY_OPERATOR_EMAIL not set: no weekly traffic digest")

    def one_pass():
        summary = poll.forward_pass(con, client, args.data_dir, days=args.days, alerts=alerts)
        try:  # the operator's weekly digest (docs/traffic.md); never costs the pass
            traffic.send_digest(
                Path(args.db).parent / "traffic.sqlite", sender, operator, datetime.now(UTC)
            )
        except Exception as e:  # noqa: BLE001
            print(f"traffic digest failed ({type(e).__name__}: {e})")
        return summary

    if args.every is not None:
        poll.run_forever(one_pass, args.every)
        return 0
    return 1 if one_pass()["problems"] else 0


def _sender():
    vault.configure(vault.Vault.from_env())
    if not vault.is_open():
        print("DY_EMAIL_KEY not set: the address vault is closed; subscriptions are off")
    try:
        return mail.Sender.from_env()
    except KeyError:
        return None


def _parties(args: argparse.Namespace) -> int:
    con = db.connect(args.db)
    if args.what == "seed":
        print(resolve.load_seed(con))
    elif args.what in ("join", "unjoin"):
        try:
            if args.what == "join":
                edge, still = resolve.join(con, args.a, args.b, args.note, cite=args.cite), []
            else:
                edge, still = resolve.unjoin(con, args.a, args.b, args.note)
        except ValueError as e:
            print(f"refused: {e}")
            return 1
        print(
            f"{args.what}: edge {edge}; {args.a} now resolves to"
            f" /p/{resolve.component_of(con, args.a)}, {args.b} to"
            f" /p/{resolve.component_of(con, args.b)}"
        )
        if still:  # a triangle of joins splits one edge at a time
            print(
                "still one component through "
                + ", ".join(f"{x}-{y}" for x, y in still)
                + " — retire those too"
            )
    else:
        print(resolve.run(con))
    print(f"search index: {search.rebuild(con)}")  # names or edges moved; the index follows
    return 0


def _gap(args: argparse.Namespace) -> int:
    """The operator's record of an outage (docs/alerts.md § gaps): the coverage page and
    the late-delivery citation are generated from these rows."""
    con = db.connect(args.db)
    try:
        if args.what == "open":
            gap_id = gaps.open_gap(con, args.failure, since=args.since, note=args.note)
            print(f"gap {gap_id} open: {args.failure} since {gaps.get(con, gap_id).started_at}")
        elif args.what == "close":
            row = gaps.close_gap(con, args.gap_id, at=args.at)
            print(f"gap {row.gap_id} closed: {row.failure} {row.started_at} → {row.ended_at}")
    except ValueError as e:
        print(f"refused: {e}")
        return 1
    rows = gaps.list_gaps(con)
    if not rows:
        print("no gap recorded")
    for g in rows:
        print(
            f"{g.gap_id:4d} {g.failure:10s} {g.started_at} → {g.ended_at or 'open'} {g.note or ''}"
        )
    return 0


def _traffic(args: argparse.Namespace) -> int:
    """The operator's view of the hourly counts; published nowhere."""
    path = Path(args.db).parent / "traffic.sqlite"
    if not path.exists():
        print(f"no counts yet ({path})")
        return 0
    print(f"{'route':10s} {'readers':>8s} {'crawlers':>9s} {'MB':>8s} {'5xx':>5s} {'<500ms':>7s}")
    for route, readers, crawlers, size, errors, fast in traffic.report(path, days=args.days):
        print(f"{route:10s} {readers:8d} {crawlers:9d} {size / 1e6:8.1f} {errors:5d} {fast:6.0f}%")
    return 0


def _citator(args: argparse.Namespace) -> int:
    """The citator's two operator verbs: load a batch of findings, and read an edge list.

    There is no `find` verb, and that is the missing half rather than an omission: text
    extraction runs on the enrichment box and comes back over the internal API, and the
    finder itself waits on a vocabulary for the `kind` judgement (docketyard/citator).
    """
    from docketyard.citator import keys, load, methods, project, review

    con = db.connect(args.db)
    if args.what in ("grant", "revoke"):
        # The grant needs the vault key; a REVIEW does not, because a decision never touches
        # an address. That split is why a reviewer can work on a box that cannot read one.
        if args.what == "revoke":
            ended = review.revoke(con, args.reviewer)
            con.commit()
            print(
                f"reviewer {args.reviewer} revoked; {ended} session(s) ended."
                " Past rows stand and stay attributed."
            )
            return 0
        v = vault.Vault.from_env()
        if v is None:
            print("refused: no DY_EMAIL_KEY — a grant seals an address (ADR 0014)")
            return 1
        vault.configure(v)
        try:
            who = review.grant(con, args.email, args.credit_name, args.note)
        except ValueError as e:
            print(f"refused: {e}")
            return 1
        con.commit()
        print(f"reviewer {who}: {args.credit_name}")
        return 0

    if args.what == "review":
        # Rendering a queue WRITES NOTHING (ADR 0011's promise covers reviewers too): the
        # surfaces log the decision and nothing else — no page views, no timing beyond the
        # action's own timestamp.
        items = review.pending(con, args.queue, limit=args.limit)
        for item in items:
            print(f"{item['target_key_rendered']}  -> docket {item['cited_docket_id']}")
            print(f"    {item['quoted_passage'][:110]}")
        print(f"{len(items)} owed a human on the {args.queue} queue")
        return 0

    if args.what == "decide":
        item = next(
            (
                q
                for q in review.pending(con, args.queue, limit=10_000)
                if q["target_key_rendered"] == args.key
            ),
            None,
        )
        if item is None:
            print(f"refused: {args.key} is not on the {args.queue} queue")
            return 1
        try:
            action = review.decide(
                con,
                reviewer_id=args.reviewer,
                queue=args.queue,
                item=item,
                decision=args.decision,
                note=args.note,
                cited_docket_id=args.docket,
            )
        except ValueError as e:
            con.rollback()
            print(f"refused: {e}")
            return 1
        con.commit()  # the assertion and the action land together, or neither does
        print(
            f"action {action}: {args.decision} by {review.credit(con, args.key) or args.reviewer}"
        )
        return 0

    if args.what == "cited-by":
        rows = (
            project.cited_by(con, work_id=args.work)
            if args.work
            else project.cited_by(con, docket_id=args.docket)
        )
        # ADR 0017 D6: per edge, the citing passage, its page, the method and version, and
        # the class's measured confidence. NO COUNT IS PUBLISHED WITHOUT ITS CLASS.
        for r in rows:
            work, _kind, key, _dk, _wk, conf, state, _score, method, version, channel = r[:11]
            raw, passage, page = r[11], r[12], r[13]
            print(f"{work}  p{page}  {key}  <- {raw!r}")
            print(f"    {passage[:110]}")
            print(f"    {method}@{version} / {channel}, confidence {conf} ({state})")
        # ADR 0018 D9: "cited by" and every count are distinct (citing work, target) PAIRS.
        # The rows are per page — short-form density must not inflate a count a reader sees.
        print(f"{len({(r[0], r[2]) for r in rows})} edges over {len(rows)} passages")
        return 0

    batch = sorted(Path(args.findings).glob("*.json"))
    if not batch:
        print(f"no findings documents in {args.findings}")
        return 1
    docs, unreadable = [], 0
    for path in batch:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            for required in ("document_sha256", "method", "method_version"):
                if not doc[required]:
                    raise KeyError(required)
        except (ValueError, KeyError, TypeError, OSError) as e:
            print(f"  skipped {path.name}: {type(e).__name__} {e}")
            unreadable += 1
            continue
        docs.append((path, doc))
    if not docs:
        print("refused: no readable findings document in the batch")
        return 1
    # A MIXED BATCH IS REFUSED rather than half-declared. `declare` records one owner per
    # class per rank_version, so loading two extractor versions in one wave would leave the
    # second writing rows the registry says it does not own (ADR 0018 D1).
    passes = {(d["method"], d["method_version"]) for _, d in docs}
    if len(passes) > 1:
        print(f"refused: the batch mixes {sorted(passes)} — one pass per load")
        return 1
    method, version = passes.pop()

    try:
        # The measurement must exist before an edge may point at it: a class nobody has
        # scored is unmeasured and PROJECTS NOTHING (ADR 0017 D3). `stamp` also refuses a
        # measurement that carries no precision, which is what a row is stamped with.
        stamps = methods.stamp(con)
        methods.declare(con, version, extractor=method)
        con.commit()
    except (methods.Unscored, methods.Conflict) as e:
        print(f"refused: {e}")
        return 1

    held = keys.registry(con)
    totals = dict.fromkeys(
        ("documents", "emitted", "out_of_class", "unresolved", "unchanged", "human_held"), 0
    )
    review: list[str] = []
    failed = 0
    for path, doc in docs:
        try:
            result = load.load_document(con, doc, held, stamps)
            con.commit()  # PER DOCUMENT: a wave killed at document 40,000 keeps 40,000, and
        except Exception as e:  # noqa: BLE001 — one bad document must not take the wave
            con.rollback()  # the 30-minute poller is not locked out for the whole run
            print(f"  failed {path.name}: {type(e).__name__} {e}")
            failed += 1
            continue
        totals["documents"] += 1
        for field in ("emitted", "out_of_class", "unresolved", "unchanged", "human_held"):
            totals[field] += getattr(result, field)
        review.extend(result.review)
    print(totals | {"unreadable": unreadable, "failed": failed})
    # ADR 0017 D5's queues do not exist yet, so these keys are PRINTED and not stored. Until
    # `review_action` is in a migration, the exposed class reaches a page unreviewed — which
    # is the one thing the exposure test was defined to prevent. See docketyard/citator.
    if review:
        print(f"\n{len(review)} keys owed a human review (ADR 0017 D5) — NOT YET QUEUED:")
        for rendered in review:
            print(f"  {rendered}")
    return 0


def _search_rebuild(args: argparse.Namespace) -> int:
    print(search.rebuild(db.connect(args.db)))
    return 0


def _vault_new_key(args: argparse.Namespace) -> int:
    print(vault.Vault.new_key())
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from docketyard.web.app import create_app

    sender = _sender()
    if sender is None:
        print("mail not configured (AWS_* / DY_SES_REGION): the subscribe form answers 503")
    app = create_app(
        args.db,
        site_host=os.environ.get("DY_HOST", "docketyard.org"),
        sender=sender,
        feedback_topic=os.environ.get("DY_SES_FEEDBACK_TOPIC") or None,
    )
    # Caddy keeps the access log, filtered (ADR 0011); uvicorn's would write every request
    # line, query string and all, to the container's stdout, and Docker keeps that on disk
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
    return 0


def _suppress(args: argparse.Namespace) -> int:
    """Stop delivering to one recipient — an address, or a webhook URL — for good."""
    from docketyard.alerts import subscriptions, vault

    vault.configure(vault.Vault.from_env())
    if not vault.is_open():
        print("DY_EMAIL_KEY is not set")
        return 2
    con = db.connect(args.db)
    try:
        channel = "webhook" if args.recipient.startswith("https://") else "email"
        subscriptions.suppress(con, args.recipient, "manual", channel=channel)
        print(f"suppressed one {channel} recipient")
    finally:
        con.close()
    return 0


def _dump(args: argparse.Namespace) -> int:
    """Cut the nightly public snapshot (M9): the store minus every reader table."""
    from docketyard.store import dump

    out = Path(args.out) if args.out else Path(args.db).parent / "public"
    m = dump.dump(Path(args.db), out)
    print(
        f"{m.latest.name}: {m.latest.bytes:,} bytes, {m.counts['filings']:,} filings,"
        f" {len(m.dated)} dated archive(s); schema v{m.schema_version}; {m.licence}"
    )
    return 0


def _status(args: argparse.Namespace) -> int:
    con = db.connect(args.db)
    for key, value in projections.status(con).items():
        print(f"{key:24} {value}")
    print("\nregistry sample:")
    for raw, title in projections.docket_titles(con, limit=5):
        print(f"  {raw:16} {(title or '(never directly observed)')[:70]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docketyard")
    parser.add_argument("--db", default="data/docketyard.sqlite")
    parser.add_argument("--data-dir", default="data")
    sub = parser.add_subparsers(dest="command", required=True)
    sup = sub.add_parser("suppress", help="never deliver to an address or webhook URL again")
    sup.add_argument("recipient")
    sup.set_defaults(func=_suppress)

    cap = sub.add_parser("capture", help="fetch one slice from the STB endpoint into captures")
    cap_sub = cap.add_subparsers(dest="table", required=True)
    for name, action in TABLE_COMMANDS:
        p = cap_sub.add_parser(name)
        p.add_argument("--prefix", help="docketNum_one criterion, e.g. FD")
        p.add_argument("--sequence", type=int, help="docketNum_two criterion")
        if action != DOCKETS:
            p.add_argument("--start", help="date-range start, MM/DD/YYYY")
            p.add_argument("--end", help="date-range end, MM/DD/YYYY")
        p.add_argument("--pages", type=int, default=10)
        p.add_argument("--per-page", type=int, default=PAGE_CLAMP, help="server clamps to 50")
        p.add_argument("--interval", type=float, default=2.0)
        p.add_argument("--mode", choices=("forward", "backfill"), default="forward")
        p.set_defaults(func=lambda a, act=action: _run_capture(a, act))

    ing = sub.add_parser("ingest", help="consume asserted captures into the ledger")
    ing_sub = ing.add_subparsers(dest="table", required=True)
    for name, action in TABLE_COMMANDS:
        p = ing_sub.add_parser(name)
        p.add_argument("--capture", type=int, help="one capture id (default: all pending)")
        p.set_defaults(func=lambda a, act=action: _run_ingest(a, act))

    fetch = sub.add_parser("fetch", help="download attachment bytes into the blob store")
    fetch_sub = fetch.add_subparsers(dest="what", required=True)
    fa = fetch_sub.add_parser("attachments")
    fa.add_argument("--limit", type=int)
    fa.add_argument("--interval", type=float, default=1.0)
    fa.add_argument("--refresh", action="store_true", help="refetch known documents (errata check)")
    fa.add_argument("--mode", choices=("forward", "backfill"), default="forward")
    fa.set_defaults(func=_fetch_attachments)

    wk = sub.add_parser("walk", help="backfill campaign: every slice of a table, resumably")
    wk_sub = wk.add_subparsers(dest="table", required=True)
    wd = wk_sub.add_parser("dockets", help="the full registry, one prefix per slice")
    wd.add_argument("--interval", type=float, default=2.0)
    wd.add_argument("--redo", action="store_true", help="re-walk prefixes already done")
    wd.set_defaults(func=_walk_dockets)

    bf = sub.add_parser("backfill", help="a wave: the record tables over a range, then files")
    bf.add_argument("--start", required=True, help="first day, YYYY-MM-DD")
    bf.add_argument("--end", help="last day, YYYY-MM-DD (default: the day the watch began)")
    bf.add_argument("--interval", type=float, default=2.0)
    bf.add_argument("--fetch-limit", type=int, help="documents per run (default: all)")
    bf.add_argument(
        "--tables",
        nargs="+",
        choices=[name for name, action in TABLE_COMMANDS if action != DOCKETS],
        help="which record tables this wave walks (default: all of them)",
    )
    bf.set_defaults(func=_backfill)

    pl = sub.add_parser("poll", help="forward pass: capture, ingest and fetch the recent window")
    pl.add_argument(
        "--days",
        type=int,
        default=poll.WINDOW_DAYS,
        help=f"trailing window, at least {poll.MIN_WINDOW_DAYS}: shorter alarms on quiet days",
    )
    pl.add_argument("--interval", type=float, default=2.0)
    pl.add_argument("--every", type=float, help="seconds between passes; omit for one pass")
    pl.set_defaults(func=_poll, parser=pl)

    pt = sub.add_parser("parties", help="the party module: split and resolve, or load the seed")
    pt_sub = pt.add_subparsers(dest="what", required=True)
    pt_sub.add_parser("resolve", help="split new cells and link spans to parties").set_defaults(
        func=_parties
    )
    pt_sub.add_parser("seed", help="load parties/seed.py (method human)").set_defaults(
        func=_parties
    )
    for what, blurb in (
        ("join", "hold two party ids to be one entity (a same_as edge, method human)"),
        ("unjoin", "retire a join found wrong; the ids keep their addresses"),
    ):
        pj = pt_sub.add_parser(what, help=blurb)
        pj.add_argument("a", type=int, help="a party id (the number in /p/<id>)")
        pj.add_argument("b", type=int, help="the other party id")
        pj.add_argument("--note", required=True, help="why — recorded as the provenance")
        if what == "join":
            pj.add_argument("--cite", default=None, help="a filing or decision id, or a URL")
        pj.set_defaults(func=_parties)

    ct = sub.add_parser("citator", help="citation edges (docs/adr/0017, 0018; migration 0014)")
    ct_sub = ct.add_subparsers(dest="what", required=True)
    cl = ct_sub.add_parser("load", help="one batch of findings documents into the families")
    cl.add_argument("findings", help="a directory of findings JSON, one per document")
    cl.set_defaults(func=_citator)
    cb = ct_sub.add_parser("cited-by", help="what cites this proceeding, or this work")
    cb_group = cb.add_mutually_exclusive_group(required=True)
    cb_group.add_argument("--docket", type=int, help="a docket_id — THE NORMAL GRAIN")
    cb_group.add_argument("--work", help="an stb_decision_id; thin, see project.cited_by")
    cb.set_defaults(func=_citator)
    gr = ct_sub.add_parser("grant", help="give the reviewer grant by hand (ADR 0016)")
    gr.add_argument("email")
    gr.add_argument("--credit-name", required=True, help="how they are shown — mandatory")
    gr.add_argument("--note", required=True, help="the operator's reason, in words")
    gr.set_defaults(func=_citator)
    rk = ct_sub.add_parser("revoke", help="withdraw a grant; past rows stand")
    rk.add_argument("reviewer", type=int)
    rk.set_defaults(func=_citator)
    rv = ct_sub.add_parser("review", help="what a human is owed (ADR 0017 D5, in its order)")
    rv.add_argument(
        "queue", choices=sorted(("citation_exposed", "citation_repaired", "citation_unresolved"))
    )
    rv.add_argument("--limit", type=int, default=50)
    rv.set_defaults(func=_citator)
    dc = ct_sub.add_parser("decide", help="record one review decision (ADR 0016)")
    dc.add_argument(
        "queue", choices=sorted(("citation_exposed", "citation_repaired", "citation_unresolved"))
    )
    dc.add_argument("key", help="the rendered key, as `citator review` prints it")
    dc.add_argument("--reviewer", type=int, required=True, help="a reviewer_id")
    dc.add_argument(
        "--decision", required=True, choices=("accepted", "rejected", "corrected", "escalated")
    )
    dc.add_argument("--note", required=True, help="why — recorded as the provenance")
    dc.add_argument("--docket", type=int, help="for `corrected`: the docket it corrects to")
    dc.set_defaults(func=_citator)

    se = sub.add_parser("search", help="the search index (docs/search.md)")
    se_sub = se.add_subparsers(dest="what", required=True)
    se_sub.add_parser("rebuild", help="rebuild the index from the store").set_defaults(
        func=_search_rebuild
    )

    gp = sub.add_parser("gap", help="record an outage window for /coverage (docs/alerts.md)")
    gp_sub = gp.add_subparsers(dest="what", required=True)
    go = gp_sub.add_parser("open", help="a gap began (now, or --since)")
    go.add_argument("failure", choices=gaps.FAILURES)
    go.add_argument("--since", help="ISO-8601 instant; naive means UTC")
    go.add_argument("--note", help="published on /coverage — never an address")
    go.set_defaults(func=_gap)
    gc = gp_sub.add_parser("close", help="a gap ended (now, or --at)")
    gc.add_argument("gap_id", type=int)
    gc.add_argument("--at", help="ISO-8601 instant; naive means UTC")
    gc.set_defaults(func=_gap)
    gp_sub.add_parser("list", help="every recorded gap").set_defaults(func=_gap)
    tr = sub.add_parser("traffic", help="hourly request counts, no identifier (docs/traffic.md)")
    tr.add_argument("--days", type=int, default=1)
    tr.set_defaults(func=_traffic)

    vk = sub.add_parser("vault", help="the address-encryption key")
    vk_sub = vk.add_subparsers(dest="what", required=True)
    vk_sub.add_parser(
        "new-key", help="print a fresh DY_EMAIL_KEY; keep it in .env and a password manager"
    ).set_defaults(func=_vault_new_key)

    dp = sub.add_parser("dump", help="cut the public snapshot (data/public by default)")
    dp.add_argument("--out", default=None)
    dp.set_defaults(func=_dump)
    st = sub.add_parser("status", help="counts for captures, records, documents, events")
    st.set_defaults(func=_status)

    sv = sub.add_parser("serve", help="serve the site over the store (read-only)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(func=_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
