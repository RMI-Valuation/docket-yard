"""Command-line entry points: capture | ingest | status."""

import argparse
import sys

from docketyard.capture import records
from docketyard.capture.stb import AJAX, DOCKETS, StbClient
from docketyard.ingest import dockets
from docketyard.store import db, projections


def _capture_dockets(args: argparse.Namespace) -> int:
    con = db.connect(args.db)
    client = StbClient(min_interval=args.interval)
    criteria: list[tuple[str, str]] = []
    if args.prefix:
        criteria.append(("docketNum_one", args.prefix))
    if args.sequence is not None:  # `is not None`: --sequence 0 must not silently unfilter
        criteria.append(("docketNum_two", str(args.sequence)))
    page, seen, total, exit_code = 1, 0, None, 0
    while page <= args.pages:
        status, body, fields = client.query_table(
            DOCKETS, criteria, page=page, per_page=args.per_page
        )
        # capture-first: the raw is durable (and quarantined) before anything parses it
        capture_id = records.save_capture(
            con,
            args.data_dir,
            source_system=dockets.SOURCE_SYSTEM,
            endpoint=AJAX,
            request_params=fields,
            body=body,
            http_status=status,
            ingest_mode=args.mode,
        )
        try:
            parsed = dockets.parse_response(body)
        except ValueError as e:
            print(f"capture {capture_id}: QUARANTINED, unparseable response ({e})")
            return 1
        asserted = dockets.assert_filter(criteria, parsed)
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
        if not parsed.rows or seen >= total:
            break
        page += 1
    if total is not None and seen < total and not dockets.hit_display_cap(total):
        print(f"  WARNING: stopped at --pages {args.pages} with {seen}/{total} rows fetched")
        exit_code = 1
    return exit_code


def _ingest_dockets(args: argparse.Namespace) -> int:
    con = db.connect(args.db)
    pending = [args.capture] if args.capture else projections.pending_capture_ids(con)
    if not pending:
        print("nothing to ingest")
        return 0
    exit_code = 0
    for capture_id in pending:
        try:
            stats = dockets.ingest_capture(con, args.data_dir, capture_id)
        except Exception as e:  # noqa: BLE001 — one bad capture must not strand the batch
            print(f"capture {capture_id}: FAILED ({type(e).__name__}: {e})")
            exit_code = 1
            continue
        print(f"capture {capture_id}: {stats}")
        if stats.get("unparsed") or stats.get("markup_skipped"):
            print("  WARNING: rows dropped during parse; raw is retained in the capture")
            exit_code = 1
    return exit_code


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
    cap_dockets = cap_sub.add_parser("dockets")
    cap_dockets.add_argument("--prefix", help="docketNum_one criterion, e.g. FD")
    cap_dockets.add_argument("--sequence", type=int, help="docketNum_two criterion")
    cap_dockets.add_argument("--pages", type=int, default=1)
    cap_dockets.add_argument("--per-page", type=int, default=100)
    cap_dockets.add_argument("--interval", type=float, default=2.0)
    cap_dockets.add_argument("--mode", choices=("forward", "backfill"), default="forward")
    cap_dockets.set_defaults(func=_capture_dockets)

    ing = sub.add_parser("ingest", help="consume asserted captures into the ledger")
    ing_sub = ing.add_subparsers(dest="table", required=True)
    ing_dockets = ing_sub.add_parser("dockets")
    ing_dockets.add_argument("--capture", type=int, help="one capture id (default: all pending)")
    ing_dockets.set_defaults(func=_ingest_dockets)

    st = sub.add_parser("status", help="counts for captures, dockets, events")
    st.set_defaults(func=_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
