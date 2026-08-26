"""Command-line entry points: capture | ingest | fetch | walk | poll | status | serve."""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from docketyard.alerts import build, mail, vault
from docketyard.capture import backfill, documents, poll, walk
from docketyard.capture.stb import DECISIONS, DOCKETS, FILINGS, PAGE_CLAMP, StbClient
from docketyard.ingest import dockets, observations
from docketyard.parties import resolve
from docketyard.store import db, projections

INGESTERS = {
    DOCKETS: dockets.ingest_capture,
    FILINGS: observations.ingest_capture,
    DECISIONS: observations.ingest_capture,
}


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
        client.get,
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
    summary = backfill.wave(con, client, args.data_dir, start, end, fetch_limit=args.fetch_limit)
    bad = any(
        summary[a]["partial"] or summary[a]["capped"] for a in (FILINGS, DECISIONS)
    ) or summary["documents"].get("failed")
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

    def one_pass():
        return poll.forward_pass(con, client, args.data_dir, days=args.days, alerts=alerts)

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
    uvicorn.run(app, host=args.host, port=args.port)
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
    for name, action in (("dockets", DOCKETS), ("filings", FILINGS), ("decisions", DECISIONS)):
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
    for name, action in (("dockets", DOCKETS), ("filings", FILINGS), ("decisions", DECISIONS)):
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

    bf = sub.add_parser("backfill", help="a wave: both record tables over a range, then files")
    bf.add_argument("--start", required=True, help="first day, YYYY-MM-DD")
    bf.add_argument("--end", help="last day, YYYY-MM-DD (default: the day the watch began)")
    bf.add_argument("--interval", type=float, default=2.0)
    bf.add_argument("--fetch-limit", type=int, help="documents per run (default: all)")
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
