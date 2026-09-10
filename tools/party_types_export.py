"""Party types: export the live party names, read-only, for a draw made off the instance.

The first sample read a store copy; a copy goes stale, and a held-out draw must come from
the population as it stands. This runs ON the instance against the live store opened
read-only and writes JSON to stdout — nothing is copied to the box and nothing written:

    ssh <instance> 'timeout 120 sudo nice -n 15 python3 -' \\
        < tools/party_types_export.py > data/party-pop.json

The population query is `party_types_sample.py`'s own; the docket lookup is the same join,
run once for every party instead of once per sampled party.
"""

import json
import sqlite3
import sys

STORE = "file:/srv/docketyard/data/docketyard.sqlite?mode=ro"


def main() -> int:
    con = sqlite3.connect(STORE, uri=True)
    names = con.execute(
        "SELECT party_id, raw_name FROM party_name"
        " WHERE superseded_by IS NULL AND name_kind = 'as_filed' ORDER BY party_id"
    ).fetchall()
    marks = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT party_id FROM party_name"
            " WHERE superseded_by IS NULL AND name_kind = 'mark'"
        )
    ]
    dockets: dict[int, list[str]] = {}
    for pid, dk in con.execute(
        """
        SELECT DISTINCT l.party_id, d.prefix || ' ' || d.sequence
          FROM filing_party_link l
          JOIN filing_party_span s ON s.span_id = l.span_id
               AND s.superseded_by IS NULL AND s.role = 'filed_for'
          JOIN filing f ON f.filing_pk = s.filing_pk AND f.filed_for_raw = s.raw_text
          JOIN docket d ON d.docket_id = f.docket_id
         WHERE l.superseded_by IS NULL
        """
    ):
        got = dockets.setdefault(pid, [])
        if len(got) < 4:
            got.append(dk)
    json.dump(
        {
            "schema": con.execute("PRAGMA user_version").fetchone()[0],
            "exported_at": con.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now')").fetchone()[0],
            "names": names,
            "marks": marks,
            "dockets": {str(k): v for k, v in dockets.items()},
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
