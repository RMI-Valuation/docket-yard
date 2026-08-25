"""Command-line entry points: capture | ingest | fetch | status."""

import argparse
import sys

from docketyard.capture import documents, records
from docketyard.capture.stb import AJAX, DECISIONS, DOCKETS, FILINGS, PAGE_CLAMP, StbClient
from docketyard.ingest import dockets, observations
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
    spec = observations.SPECS.get(action)  # None for the dockets table
    criteria = _criteria_from(args, spec)
    page, seen, total, exit_code = 1, 0, None, 0
    while page <= args.pages:
        status, body, fields = client.query_table(
            action, criteria, page=page, per_page=args.per_page
        )
        # capture-first: the raw is durable (and quarantined) before anything parses it
        capture_id = records.save_capture(
            con,
            args.data_dir,
            source_system=dockets.SOURCE_SYSTEM,
            endpoint=AJAX,
            table_action=action,
            request_params=fields,
            body=body,
            http_status=status,
            ingest_mode=args.mode,
        )
        try:
            if spec is None:
                parsed = dockets.parse_response(body)
                asserted = dockets.assert_filter(criteria, parsed)
            else:
                parsed = observations.parse_response(spec, body)
                asserted = observations.assert_filter(spec, criteria, parsed)
        except ValueError as e:
            if page > 1 and dockets.is_no_results_envelope(body):
                # end of results after a page that passed assertion; the identical
                # envelope on page 1 is the wrong-criteria trap and quarantines below
                records.set_verdict(
                    con, capture_id, filter_asserted=True, row_count=0, reported_total=total or 0
                )
                records.mark_processed(con, capture_id)
                print(f"capture {capture_id}: page {page}, end of results")
                break
            print(f"capture {capture_id}: QUARANTINED, unparseable response ({e})")
            return 1
        records.set_verdict(
            con,
            capture_id,
            filter_asserted=asserted,
            row_count=len(parsed.rows),
            reported_total=parsed.total,
        )
        seen += len(parsed.rows)
        total = parsed.total
        print(f"capture {capture_id}: page {page}, {len(parsed.rows)} rows, total={total}")
        if not asserted:
            print("  QUARANTINED: filter assertion failed — will not be ingested")
            return 1
        if dockets.hit_display_cap(total):
            print(f"  WARNING: total={total} is the display cap; this slice is INCOMPLETE")
            exit_code = 1
        # the server clamps per-page (measured: 50) and `total` may count records rather
        # than rows, so the last page is the first SHORT page — never `seen >= total`. A
        # slice that fills its last page exactly ends on the no-results envelope above.
        if not parsed.rows or len(parsed.rows) < min(args.per_page, PAGE_CLAMP):
            break
        page += 1
    else:
        print(f"  WARNING: stopped at --pages {args.pages} with {seen} rows; more may remain")
        exit_code = 1
    return exit_code


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

    cap = sub.add_parser("capture", help="fetch from the STB endpoint into captures")
    cap_sub = cap.add_subparsers(dest="table", required=True)
    for name, action in (("dockets", DOCKETS), ("filings", FILINGS), ("decisions", DECISIONS)):
        p = cap_sub.add_parser(name)
        p.add_argument("--prefix", help="docketNum_one criterion, e.g. FD")
        p.add_argument("--sequence", type=int, help="docketNum_two criterion")
        if action != DOCKETS:
            p.add_argument("--start", help="date-range start, MM/DD/YYYY")
            p.add_argument("--end", help="date-range end, MM/DD/YYYY")
        p.add_argument("--pages", type=int, default=10)
        p.add_argument("--per-page", type=int, default=50, help="server clamps to 50")
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

    st = sub.add_parser("status", help="counts for captures, records, documents, events")
    st.set_defaults(func=_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
