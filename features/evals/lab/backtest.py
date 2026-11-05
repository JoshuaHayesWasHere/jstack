# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""The backtest: the smallest discrete-event model of the pipeline, fit on the days `--fit` names
in a copy of the telemetry store and run over the week `--week` names, against that week's real
KPIs. kpi-lab-3's paired model, moved into the repo.

    uv run --script backtest.py --store <copy> --fit 2026-10-19..2026-11-01 --week 2026-11-01 \\
        --end 2026-11-03T01:37:48Z --runs 200 --json backtest.json

One run is one simulated span: a warm-up of WARMUP_DAYS before the week, then the week up to
`--end`. Rows arrive each local day, the count bootstrapped from the fit's days and each go's
minute of the day drawn from the fit's goes. A jstack row takes its crew stage (go to pull request
open) and its pull-request stage (open to merge) together from one row of the fit; a row of
another project takes its whole lead time from the fit's. A ready row merges at the next jbus pass
(PASS_MIN apart), except that a jstack merge waits while main is red. A jstack merge has a kept
push check with probability `p_kept`, and a kept one opens a red spell of main with probability
`p_spell`, which lasts a restore time drawn from the fit's finished spells (a spell the store
dates green before red is left out).

The KPIs are taken over the rows merged in the week, as the store's views define them: PR open to
merge and lead time are medians over the week's merges, merges counts them as `weekly_merges`
does, and the change failure rate is spells over jstack merges with a kept push check, as
`change_failures` counts it since #911. The real side reads those views' rows, cut at `--end`.

Nothing at or after the cutoff enters the fit. Seeds are 0..runs-1, so a run repeats exactly.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import statistics
from dataclasses import dataclass, field

from span import Span, add_flags, bounds, connect, em, from_args, local_midnight, minutes

PROJECT = "jstack"
PASS_MIN = 1.0
"""Minutes between jbus passes, each of which runs jmerge: the passes table (2026-11-02, the
only day it held when kpi-lab-3 ran) has 199 gaps from 60.0 s to 66.0 s."""
WARMUP_DAYS = 3
THIN = {"arrival days": 7, "finished spells": 10}
"""Fewer of these in the fit than this and the backtest warns: the arrivals bootstrap from that many
days, and a run's restore times and change failures draw from that many spells."""
RED = "('failure', 'timed_out', 'startup_failure', 'action_required')"
KPIS = {
    "pr_median": "PR open to merge, median min",
    "lead_median": "lead time, median min",
    "cfr_pct": "change failure rate, %",
    "merges": "merges",
}


@dataclass
class Fit:
    start: str
    cutoff: str
    day_counts: list[int] = field(default_factory=list)
    tod: list[float] = field(default_factory=list)
    share_jstack: float = 0.0
    other_lead: list[float] = field(default_factory=list)
    pairs: list[tuple[float, float]] = field(default_factory=list)
    p_kept: float = 0.0
    p_spell: float = 0.0
    restore: list[float] = field(default_factory=list)
    notes: dict = field(default_factory=dict)


def rows_between(db: sqlite3.Connection, lo: float, hi: float) -> list[sqlite3.Row]:
    """Rows merged in the span, with their go, pull-request open and merge, in minutes."""
    return db.execute(
        f"""WITH r AS (SELECT l.project, l.slug, l.pr, {em("l.go")} AS go_m,
               {em("l.merged_at")} AS merged_m,
               (julianday(l.go, 'localtime') - julianday(date(l.go, 'localtime'))) * 1440.0 AS tod,
               date(l.go, 'localtime') AS go_day,
               CASE WHEN l.project = :p THEN {em("c.created")} END AS open_m,
               c.number IS NOT NULL AS has_pr
             FROM lead_times l
             LEFT JOIN ci_prs c ON l.project = :p AND c.project = :p
               AND c.number = l.pr AND c.merged IS NOT NULL)
           SELECT * FROM r WHERE merged_m >= :lo AND merged_m < :hi
           ORDER BY merged_m, project, slug""",
        {"p": PROJECT, "lo": lo, "hi": hi},
    ).fetchall()


def fit(
    db: sqlite3.Connection, start: str, cutoff: str, hi: float | None = None, censor: bool = True
) -> Fit:
    """The model's inputs from the rows merged from `start` to `cutoff` (or `hi`, in minutes)."""
    f = Fit(start, cutoff)
    lo = local_midnight(db, start)
    hi = local_midnight(db, cutoff) if hi is None else hi
    rows = rows_between(db, lo, hi)
    # Arrivals: goes per local day, of the fit's merged rows, leaving out the last day before the
    # cutoff, whose late goes have not merged yet (right censoring).
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["go_day"]] = counts.get(r["go_day"], 0) + 1
    last = db.execute("SELECT date(?, '-1 day')", (cutoff,)).fetchone()[0] if censor else cutoff
    days = sorted(d for d in counts if start <= d < last)
    f.day_counts = [counts[d] for d in days]
    f.tod = [r["tod"] for r in rows]
    js = [r for r in rows if r["project"] == PROJECT and r["has_pr"]]
    f.share_jstack = len(js) / len(rows) if rows else 0.0
    f.pairs = [(max(0.0, r["open_m"] - r["go_m"]), r["merged_m"] - r["open_m"]) for r in js]
    f.other_lead = [
        r["merged_m"] - r["go_m"] for r in rows if not (r["project"] == PROJECT and r["has_pr"])
    ]
    # Change failures as the store counts them: of the jstack merges, those with a kept push check,
    # and of those, the ones whose pull request opened a red spell of main.
    span = f"project = :p AND {em('merged_at')} >= :lo AND {em('merged_at')} < :hi"
    args = {"p": PROJECT, "lo": lo, "hi": hi}
    merged, kept = db.execute(
        f"SELECT count(*), coalesce(sum(kept), 0) FROM ci_rows WHERE {span}", args
    ).fetchone()
    failures = db.execute(
        f"SELECT coalesce(sum(opened_spell), 0) FROM change_failures WHERE {span}", args
    ).fetchone()[0]
    f.p_kept = kept / merged if merged else 0.0
    f.p_spell = failures / kept if kept else 0.0
    f.restore = [
        s[0]
        for s in db.execute(
            "SELECT minutes_to_green FROM main_spells WHERE project = :p AND "
            f"{em('first_fail_at')} >= :lo "
            f"AND {em('first_fail_at')} < :hi AND green_at IS NOT NULL "
            "AND minutes_to_green >= 0 ORDER BY first_fail_at",
            args,
        )
    ]
    f.notes = {
        "rows": len(rows),
        "jstack_rows": len(js),
        "arrival_days": days,
        "ci_merges": merged,
        "kept": kept,
        "failures": failures,
        "finished_spells": len(f.restore),
    }
    return f


@dataclass(frozen=True)
class Week:
    lo: float
    hi: float
    days: list[float]


def sim_week(db: sqlite3.Connection, span: Span) -> Week:
    lo, hi = bounds(db, span)
    d = db.execute("SELECT date(?, ?)", (span.week, f"-{WARMUP_DAYS} days")).fetchone()[0]
    days = []
    while (m := local_midnight(db, d)) < hi:
        days.append(m)
        d = db.execute("SELECT date(?, '+1 day')", (d,)).fetchone()[0]
    return Week(lo, hi, days)


def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def run(f: Fit, w: Week, seed: int, override: dict | None = None) -> dict:
    """One seeded run: the KPIs of the rows merged in the week."""
    o = {**f.__dict__, **(override or {})}
    rng = random.Random(seed)
    ready = []  # (ready minute, is jstack, go, pr open)
    for day in w.days:
        for _ in range(rng.choice(o["day_counts"])):
            go = day + rng.choice(o["tod"])
            if rng.random() < o["share_jstack"]:
                crew, pr = rng.choice(o["pairs"])
                ready.append((go + crew + pr, True, go, go + crew))
            else:
                ready.append((go + rng.choice(o["other_lead"]), False, go, None))
    ready.sort()
    red_until, merged, kept, spells = -math.inf, [], 0, 0
    for t, js, go, opened in ready:
        if t >= w.hi:
            break
        at = math.ceil(t / PASS_MIN) * PASS_MIN
        if js:
            at = max(at, red_until)
            if at >= w.hi:
                continue
            # One draw: a kept check (u < p_kept), and of those a spell (u < p_kept * p_spell).
            u = rng.random()
            if u < o["p_kept"] * o["p_spell"]:
                red_until = at + rng.choice(o["restore"])
                spells += at >= w.lo
            kept += at >= w.lo and u < o["p_kept"]
        if at >= w.lo:
            merged.append((at, js, go, opened))
    return {
        "pr_median": median([at - op for at, js, _, op in merged if js]),
        "lead_median": median([at - go for at, _, go, _ in merged]),
        "cfr_pct": 100.0 * spells / kept if kept else None,
        "merges": len(merged),
    }


def real(db: sqlite3.Connection, span: Span, week: str) -> dict:
    """The week's KPIs from the rows of the store's views, merged before `--end`: for a week
    `--end` does not cut, the numbers `weekly_pr_to_merge`, `weekly_lead_time`,
    `weekly_change_failure` and `weekly_merges` give."""
    cut = {"w": week, "end": minutes(db, span.end)}
    before = f"{em('merged_at')} < :end"
    pr = [
        r[0]
        for r in db.execute(
            f"SELECT minutes FROM pr_times WHERE week = :w AND minutes >= 0 AND {before}", cut
        )
    ]
    lead = [
        r[0]
        for r in db.execute(
            f"SELECT minutes FROM lead_times WHERE week = :w AND minutes >= 0 AND {before}", cut
        )
    ]
    merges = db.execute(
        f"SELECT count(*) FROM lead_times WHERE week = :w AND {before}", cut
    ).fetchone()[0]
    failures, kept = db.execute(
        "SELECT coalesce(sum(opened_spell), 0), count(*) FROM change_failures WHERE week = :w "
        f"AND {before}",
        cut,
    ).fetchone()
    return {
        "pr_median": median(pr),
        "pr_n": len(pr),
        "lead_median": median(lead),
        "lead_n": len(lead),
        "cfr_pct": 100.0 * failures / kept if kept else None,
        "failures": failures,
        "kept": kept,
        "merges": merges,
    }


def oracle(db: sqlite3.Connection, span: Span, w: Week) -> tuple[dict[str, dict], Fit]:
    """Each input as the predicted week itself has it, for the blame swap."""
    g = fit(db, span.week, span.week_end, hi=w.hi, censor=False)
    return {
        "arrivals": {
            "day_counts": [round(sum(g.day_counts) / len(g.day_counts))] if g.day_counts else None
        },
        "other_lead": {"other_lead": g.other_lead},
        "pairs": {"pairs": g.pairs},
        "share_jstack": {"share_jstack": g.share_jstack},
        "main_spells": {"p_kept": g.p_kept, "p_spell": g.p_spell, "restore": g.restore},
    }, g


def thin(f: Fit) -> list[str]:
    """What the fit has too little of to trust the bands it gives."""
    days = f.notes["arrival_days"]
    has = {"arrival days": len(days), "finished spells": f.notes["finished_spells"]}
    seen = {"arrival days": f" ({days[0]}..{days[-1]})" if days else ""}
    return [
        f"the fit has {has[k]} {k}{seen.get(k, '')}, fewer than {least}: the bands rest on too "
        "few draws"
        for k, least in THIN.items()
        if has[k] < least
    ]


def band(xs: list[float | None]) -> dict:
    ys = sorted(x for x in xs if x is not None)
    if not ys:
        return {"p05": None, "median": None, "p95": None, "runs": 0}
    q = lambda p: ys[min(len(ys) - 1, int(p * len(ys)))]  # noqa: E731
    return {"p05": q(0.05), "median": statistics.median(ys), "p95": q(0.95), "runs": len(ys)}


def usable(override: dict) -> bool:
    """A swap the model can run: every list it draws from holds a value."""
    return all(v is not None and (not isinstance(v, list) or v) for v in override.values())


def blame(pred: dict, x: float | None, swaps: dict[str, dict], k: str) -> dict | None:
    """The swap whose median moves the KPI furthest toward the real value."""
    if x is None or pred["median"] is None:
        return None
    gap = abs(pred["median"] - x)
    moves = [
        (gap - abs(s[k] - x), label, s[k]) for label, s in swaps.items() if s.get(k) is not None
    ]
    if not moves:
        return None
    closed, label, to = max(moves, key=lambda m: (m[0], m[1]))
    return (
        {"swap": label, "median": to, "closes": closed}
        if closed > 0
        else {"swap": None, "closes": 0.0}
    )


def backtest(db: sqlite3.Connection, span: Span, runs: int) -> dict:
    f = fit(db, span.fit_start, span.cutoff)
    w = sim_week(db, span)
    results = [run(f, w, seed) for seed in range(runs)]
    pred = {k: band([r[k] for r in results]) for k in KPIS}
    now, naive = real(db, span, span.week), real(db, span, span.last_week)
    swaps, g = oracle(db, span, w)
    out_swaps = {}
    for label, over in swaps.items():
        if not usable(over):
            continue
        rs = [run(f, w, seed, over) for seed in range(runs)]
        out_swaps[label] = {k: band([x[k] for x in rs])["median"] for k in KPIS}
    kpis = []
    for k, name in KPIS.items():
        b, x = pred[k], now[k]
        hit = x is not None and b["p05"] is not None and b["p05"] <= x <= b["p95"]
        kpis.append(
            {
                "key": k,
                "name": name,
                "predicted": b,
                "real": x,
                "verdict": "hit" if hit else "miss",
                "naive": naive[k],
                "blame": None if hit else blame(b, x, out_swaps, k),
            }
        )
    summary = lambda v: {"n": len(v), "median": median(v)}  # noqa: E731
    return {
        "span": {"fit": f"{span.fit_start}..{span.cutoff}", "week": span.week, "end": span.end},
        "runs": runs,
        "seeds": [0, runs - 1],
        "fit": {
            "day_counts": f.day_counts,
            "share_jstack": f.share_jstack,
            "pairs": len(f.pairs),
            "crew": summary([c for c, _ in f.pairs]),
            "pr": summary([p for _, p in f.pairs]),
            "other_lead": summary(f.other_lead),
            "p_kept": f.p_kept,
            "p_spell": f.p_spell,
            "restore": f.restore,
            "notes": f.notes,
        },
        "kpis": kpis,
        "real": now,
        "last_week": naive,
        "oracle_inputs": {
            "day_counts": g.day_counts,
            "share_jstack": g.share_jstack,
            "pairs": len(g.pairs),
            "crew": summary([c for c, _ in g.pairs]),
            "pr": summary([p for _, p in g.pairs]),
            "other_lead": summary(g.other_lead),
            "p_kept": g.p_kept,
            "p_spell": g.p_spell,
            "notes": g.notes,
        },
        "swaps": out_swaps,
        "warnings": thin(f),
    }


def num(x: float | None) -> str:
    return "-" if x is None else f"{x:.1f}" if isinstance(x, float) else str(x)


def show(o: dict) -> None:
    s, f = o["span"], o["fit"]
    print(
        f"backtest: fit {s['fit']} (cutoff held out), week {s['week']} read to {s['end']}, "
        f"{o['runs']} runs, seeds {o['seeds'][0]}..{o['seeds'][1]}"
    )
    print(
        f"  fit: rows {f['notes']['rows']}, jstack pairs {f['pairs']}, goes a day "
        f"{f['day_counts']}, "
        f"jstack share {f['share_jstack']:.2f}, crew median {num(f['crew']['median'])}, "
        f"pr median {num(f['pr']['median'])}, p_kept {f['p_kept']:.3f}, p_spell "
        f"{f['p_spell']:.4f}, "
        f"finished spells {len(f['restore'])}"
    )
    print(
        f"  {'KPI':30} {'predicted median [p05, p95]':>30} {'real':>8} {'verdict':>7} {'naive':>8}"
    )
    for k in o["kpis"]:
        b = k["predicted"]
        band_ = f"{num(b['median'])} [{num(b['p05'])}, {num(b['p95'])}]"
        print(
            f"  {k['name']:30} {band_:>30} {num(k['real']):>8} {k['verdict']:>7} "
            f"{num(k['naive']):>8}"
        )
    r = o["real"]
    print(
        f"  real n: PR {r['pr_n']}, lead {r['lead_n']}, merges {r['merges']}, "
        f"change failures {r['failures']} of {r['kept']} kept"
    )
    print("  swap one input for the week's own (median of runs):")
    for label, sw in o["swaps"].items():
        print(f"    {label:13} " + "  ".join(f"{k} {num(sw[k])}" for k in KPIS))
    limiter = min(
        ("fit pairs", f["pairs"]), ("finished spells", len(f["restore"])), key=lambda t: t[1]
    )
    print(
        f"  limiter: {limiter[0]}, {limiter[1]}: each run draws from these, so a band is no "
        "wider than they vary"
    )
    for w in o["warnings"]:
        print(f"  warning: {w}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_flags(ap)
    ap.add_argument("--runs", type=int, default=200)
    a = ap.parse_args()
    span = from_args(ap, a)
    db = connect(a.store)
    out = backtest(db, span, a.runs)
    show(out)
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
