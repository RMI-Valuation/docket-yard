#!/usr/bin/env python3
"""Score the prose screen on the population it actually sorts (docs/research/text-quality).

    python3 kinds_flagged_score.py [--sample <json>] [--checked <json>] [--boot 20000]

THE QUESTION, unchanged from the draw: of the pages the screen ORDERS — the flagged set, a live
primary text-layer reading scoring under 0.5 over the 15-token floor — how often is a page the
screen calls prose actually prose (precision), and how much of the flagged set's prose does it
find (recall)? The earlier figures rested on five prose pages (`docs/deferred.md`, 2026-09-18).

THE WEIGHTS ARE WHY 40 LABELS ANSWER BOTH. `kinds_flagged_sample.py` drew a pool of 400 at
random from the eligible flagged pages, then took 20 from each side of the screen's own verdict.
Precision reads straight off the first stratum — every page in it carries the same weight, so
weighting cannot change a ratio computed inside it. Recall cannot: a page the screen rejected
stands for 15.9 pool pages against the accepted page's 4.1, so the false negatives must be
weighted up before they are counted, or recall comes out roughly four times too flattering.

`mixed` IS REPORTED BOTH WAYS AND NEITHER IS PRIMARY. A page of argument with a table under it
is partly what the re-read wants and partly not, and nothing in the record decides it. The two
readings bracket the answer; the spread between them is the cost of the question being open, and
it is stated rather than resolved here.

THE INTERVALS. Precision is a binomial proportion within one stratum: Wilson, which is what a
count of 20 admits. Recall and prevalence are ratios of weighted sums across two strata, where
no closed form is honest, so they are bootstrapped — the strata resampled independently, which
is how they were drawn. A seed is fixed so two runs agree.

Nothing here is published from a model's labels: `kinds-flagged-checked.json` is the operator's
own, typed against the page on a sheet that showed him no score and no screen verdict.
"""

import argparse
import json
import random
from math import sqrt
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[2] / "docs" / "research" / "text-quality"
SEED_BOOT = 20260919
PROSE = "prose"
MIXED = "mixed"


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def counts(rows: list[dict], is_prose) -> dict:
    """Per stratum: how many were drawn, and how many of them are prose under this reading."""
    out = {}
    for r in rows:
        cell = out.setdefault(r["screen_prose"], {"n": 0, "prose": 0, "weight": r["weight"]})
        cell["n"] += 1
        cell["prose"] += 1 if is_prose(r["kind"]) else 0
        if cell["weight"] != r["weight"]:
            raise ValueError("one stratum, two weights — the draw and the scoring disagree")
    return out


def figures(rows: list[dict], is_prose, pool: int) -> dict:
    c = counts(rows, is_prose)
    yes, no = c[True], c[False]
    tp_w = yes["prose"] * yes["weight"]
    fn_w = no["prose"] * no["weight"]
    return {
        "precision": yes["prose"] / yes["n"],
        "precision_hits": (yes["prose"], yes["n"]),
        "recall": tp_w / (tp_w + fn_w) if (tp_w + fn_w) else float("nan"),
        "found_raw": (yes["prose"], no["prose"]),
        # the flagged set's prose rate, as a share of the pool the 40 were drawn from
        "prevalence": (tp_w + fn_w) / pool,
    }


def composition(rows: list[dict], pool: int) -> dict[str, float]:
    """What the flagged set IS, by weighted share. The raw tally is not this: it is 20 and 20
    by construction, and the second twenty each stand for nearly four times what the first do."""
    out: dict[str, float] = {}
    for r in rows:
        out[r["kind"]] = out.get(r["kind"], 0.0) + r["weight"]
    return {k: w / pool for k, w in out.items()}


def boot(rows: list[dict], is_prose, pool: int, n: int, seed: int) -> dict:
    """Resample each stratum with replacement, as it was drawn, and keep the percentiles."""
    rng = random.Random(seed)
    strata = {
        True: [r for r in rows if r["screen_prose"]],
        False: [r for r in rows if not r["screen_prose"]],
    }
    recalls, prevs = [], []
    for _ in range(n):
        draw = [rng.choice(s) for s in strata.values() for _ in s]
        f = figures(draw, is_prose, pool)
        if f["recall"] == f["recall"]:  # not NaN: no prose at all in this resample
            recalls.append(f["recall"])
        prevs.append(f["prevalence"])
    pick = lambda xs, q: sorted(xs)[int(q * (len(xs) - 1))] if xs else float("nan")  # noqa: E731
    return {
        "recall_ci": (pick(recalls, 0.025), pick(recalls, 0.975)),
        "prevalence_ci": (pick(prevs, 0.025), pick(prevs, 0.975)),
    }


def boot_composition(rows: list[dict], pool: int, n: int, seed: int) -> dict[str, tuple]:
    rng = random.Random(seed)
    strata = [
        [r for r in rows if r["screen_prose"]],
        [r for r in rows if not r["screen_prose"]],
    ]
    kinds = sorted({r["kind"] for r in rows})
    runs: dict[str, list[float]] = {k: [] for k in kinds}
    for _ in range(n):
        draw = [rng.choice(s) for s in strata for _ in s]
        share = composition(draw, pool)
        for k in kinds:
            runs[k].append(share.get(k, 0.0))
    pick = lambda xs, q: sorted(xs)[int(q * (len(xs) - 1))]  # noqa: E731
    return {k: (pick(v, 0.025), pick(v, 0.975)) for k, v in runs.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=Path, default=RESEARCH / "kinds-flagged-sample.json")
    ap.add_argument("--checked", type=Path, default=RESEARCH / "kinds-flagged-checked.json")
    ap.add_argument("--boot", type=int, default=20000)
    args = ap.parse_args()

    drawn = json.loads(args.sample.read_text(encoding="utf-8"))
    checked = json.loads(args.checked.read_text(encoding="utf-8"))
    weights = {True: drawn["weight_prose_stratum"], False: drawn["weight_not_stratum"]}
    rows = []
    for p in drawn["pages"]:
        lid = p["label_id"]
        if lid not in checked:
            raise KeyError(f"{lid} was drawn and is not labelled — the sample is not complete")
        kind = checked[lid]["kind"]
        if kind is None:
            raise ValueError(f"{lid} carries a note and no kind")
        rows.append(
            {
                "id": lid,
                "kind": kind,
                "screen_prose": p["screen_prose"],
                "weight": weights[p["screen_prose"]],
            }
        )
    if len(rows) != len(checked):
        raise ValueError(f"{len(checked)} labels against {len(rows)} drawn pages")

    pool, pop = drawn["pool"], drawn["eligible"]
    print(f"{len(rows)} pages, pool {pool} of {pop} eligible ({drawn['population']} flagged)")
    tally: dict[str, list[int]] = {}
    for r in rows:
        cell = tally.setdefault(r["kind"], [0, 0])
        cell[0 if r["screen_prose"] else 1] += 1
    share = composition(rows, pool)
    ci = boot_composition(rows, pool, args.boot, SEED_BOOT)
    print("\nWHAT THE FLAGGED SET IS — the drawn counts are 20 and 20 by construction, so the")
    print("share is the weighted one, and it is what estimates the record.\n")
    print("kind        drawn: screen prose / not     share of the flagged set        pages")
    for kind in sorted(share, key=lambda k: -share[k]):
        yes, no = tally[kind]
        lo, hi = ci[kind]
        print(
            f"  {kind:<9} {yes:>10} / {no:<4}    {share[kind]:>6.1%}  ({lo:.1%}-{hi:.1%})"
            f"   {share[kind] * pop:>7,.0f}"
        )

    for label, is_prose in (
        ("prose only", lambda k: k == PROSE),
        ("prose or mixed", lambda k: k in (PROSE, MIXED)),
    ):
        f = figures(rows, is_prose, pool)
        b = boot(rows, is_prose, pool, args.boot, SEED_BOOT)
        plo, phi = wilson(*f["precision_hits"])
        rlo, rhi = b["recall_ci"]
        vlo, vhi = b["prevalence_ci"]
        hits, n = f["precision_hits"]
        print(f"\n--- {label} ---")
        print(f"  precision  {f['precision']:.2f}  ({hits}/{n}, Wilson {plo:.2f}-{phi:.2f})")
        print(f"  recall     {f['recall']:.2f}  (bootstrap {rlo:.2f}-{rhi:.2f})")
        print(
            f"  prevalence {f['prevalence']:.3f} ({vlo:.3f}-{vhi:.3f})"
            f"  =  {f['prevalence'] * pop:,.0f} pages ({vlo * pop:,.0f}-{vhi * pop:,.0f})"
        )
        found, missed = f["found_raw"]
        print(f"  found {found} of the screen's 20, missed {missed} of the other 20")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
