# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""The power of a live A/B on the rows of the span: each KPI's per-row spread in a copy of the
telemetry store, the rows per arm a two-arm A/B needs to see a 20% change at 80% power (two-sided
alpha 0.05), a resampling check of that n, the clustering by merge day, and the rate rows arrive
at. kpi-lab-6's power, moved into the repo.

    uv run --script power.py --store <copy> --fit 2026-10-19..2026-11-01 --week 2026-11-01 \\
        --end 2026-11-03T01:37:48Z --json power.json

The rows are those merged from the fit's first day to the end of `--week`, before `--end`. A
row's arm and threads come from the store's `launch_arms`. The resampling is seeded (SEED).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
from collections import Counter, defaultdict
from datetime import date, timedelta

from span import add_flags, connect, em, from_args, minutes

NORMAL = st.NormalDist()
Z = NORMAL.inv_cdf(0.975) + NORMAL.inv_cdf(0.80)  # 1.96 + 0.8416
CHANGE = 0.20
SEED = 6
ARMS = ("trimmed", "control")
TARGETS = ("lead time, go to merge", "PR open to merge", "first round, the week")
"""The KPIs an A/B targets; the change failure rate and typed messages are guards, too rare
to power."""


def n_mean(sd: float, delta: float) -> float:
    """Rows per arm, two-sample z on a mean: 2 (z_a/2 + z_b)^2 sd^2 / delta^2."""
    return 2 * Z * Z * sd * sd / (delta * delta)


def n_prop(p1: float, p2: float) -> float:
    za, zb = NORMAL.inv_cdf(0.975), NORMAL.inv_cdf(0.80)
    pbar = (p1 + p2) / 2
    top = za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return top * top / (p1 - p2) ** 2


def ceil(x: float | None) -> int | None:
    return None if x is None or math.isinf(x) else math.ceil(x)


def check_logs(rng: random.Random, values: list[float], n: int, reps: int = 2000) -> float:
    """Power by resampling: draw n rows per arm from the real rows, scale arm B by 0.8, and test
    the difference of mean log minutes with a z test."""
    logs = [math.log(max(v, 1.0)) for v in values]
    shift = math.log(1 - CHANGE)
    hits = 0
    for _ in range(reps):
        a = rng.choices(logs, k=n)
        b = [x + shift for x in rng.choices(logs, k=n)]
        se = math.sqrt(st.variance(a) / n + st.variance(b) / n)
        hits += abs((st.mean(a) - st.mean(b)) / se) > 1.96
    return hits / reps


def check_prop(rng: random.Random, p1: float, p2: float, n: int, reps: int = 2000) -> float:
    hits = 0
    for _ in range(reps):
        a = sum(rng.random() < p1 for _ in range(n)) / n
        b = sum(rng.random() < p2 for _ in range(n)) / n
        pbar = (a + b) / 2
        se = math.sqrt(2 * pbar * (1 - pbar) / n) or 1e-9
        hits += abs(a - b) / se > 1.96
    return hits / reps


def icc(groups: dict[str, list[float]]) -> tuple[float | None, float]:
    """One-way ANOVA ICC of the values clustered by `groups`, and the mean cluster size."""
    groups = {k: v for k, v in groups.items() if len(v) >= 2}
    k = len(groups)
    sizes = [len(v) for v in groups.values()]
    total = sum(sizes)
    if k < 2 or total <= k:
        return None, (total / k if k else 0.0)
    grand = sum(sum(v) for v in groups.values()) / total
    ssb = sum(len(v) * (st.mean(v) - grand) ** 2 for v in groups.values())
    ssw = sum(sum((x - st.mean(v)) ** 2 for x in v) for v in groups.values())
    msb, msw = ssb / (k - 1), ssw / (total - k)
    m0 = (total - sum(s * s for s in sizes) / total) / (k - 1)
    den = msb + (m0 - 1) * msw
    return ((msb - msw) / den if den else None), total / k


def measure(db, span) -> dict:
    rng = random.Random(SEED)
    last_day = (date.fromisoformat(span.week) + timedelta(days=7)).isoformat()
    w = {"lo": span.fit_start, "hi": last_day, "end": minutes(db, span.end)}
    inside = f"day >= :lo AND day < :hi AND {em('merged_at')} < :end"

    arm: dict[tuple[str, str], str] = {}
    threads: dict[tuple[str, str], set[str]] = defaultdict(set)
    for project, slug, a, thread in db.execute(
        "SELECT project, slug, arm, thread FROM launch_arms ORDER BY at, key"
    ):
        if a in ARMS:
            arm[(project, slug)] = a
        if thread:
            threads[(project, slug)].add(thread)
    launched = Counter(
        d
        for (d,) in db.execute(
            "SELECT min(day) FROM launch_arms WHERE slug IS NOT NULL GROUP BY project, slug"
        )
    )
    lead = db.execute(
        f"SELECT project, slug, day, minutes FROM lead_times WHERE {inside} ORDER BY day, "
        "project, slug",
        w,
    ).fetchall()
    prs = db.execute(
        "SELECT p.project, m.slug, p.day, p.minutes, p.first_round FROM pr_times p "
        "LEFT JOIN merged m ON m.project = p.project AND m.number = p.pr "
        f"WHERE p.minutes >= 0 AND p.day >= :lo AND p.day < :hi AND {em('p.merged_at')} < :end "
        "ORDER BY p.day, p.project, p.pr",
        w,
    ).fetchall()
    cf = [r[0] for r in db.execute(f"SELECT opened_spell FROM change_failures WHERE {inside}", w)]
    per_thread = dict(
        db.execute(
            "SELECT thread, count(*) FROM messages WHERE role = 'user' AND created_by = 'user' "
            "AND id NOT LIKE 'limit-resume:%' AND kind NOT IN ('dropped', 'resume') GROUP BY thread"
        ).fetchall()
    )

    out: dict = {
        "span": {"days": [span.fit_start, last_day], "end": span.end},
        "seed": SEED,
        "kpis": {},
    }
    k = out["kpis"]
    for name, rows in (("lead time, go to merge", lead), ("PR open to merge", prs)):
        mins = [r[3] for r in rows]
        if len(mins) < 2:
            k[name] = {"rows": len(mins), "n_per_arm": None}
            continue
        sd = st.stdev([math.log(max(m, 1.0)) for m in mins])
        n = ceil(n_mean(sd, abs(math.log(1 - CHANGE))))
        k[name] = {
            "rows": len(mins),
            "median": st.median(mins),
            "spread": sd,
            "spread_of": "sd of ln minutes",
            "cv": st.stdev(mins) / st.mean(mins) if st.mean(mins) else None,
            "n_per_arm": n,
            "power_at_n": check_logs(rng, mins, n) if n else None,
        }
    fr = [r[4] for r in prs if r[4] is not None]
    week_fr = [r[4] for r in prs if r[4] is not None and r[2] >= span.week]
    for name, xs in (("first round, the span", fr), ("first round, the week", week_fr)):
        p = sum(xs) / len(xs) if xs else None
        n = ceil(n_prop(p, p * (1 - CHANGE))) if p else None
        k[name] = {
            "rows": len(xs),
            "share": p,
            "n_per_arm": n,
            "spread_of": "sd of a share",
            "spread": math.sqrt(p * (1 - p)) if p is not None else None,
            "power_at_n": check_prop(rng, p, p * (1 - CHANGE), n) if n else None,
        }
    pc = sum(cf) / len(cf) if cf else None
    k["change failure rate"] = {
        "rows": len(cf),
        "failures": sum(cf),
        "rate": pc,
        "spread_of": "sd of a share",
        "spread": math.sqrt(pc * (1 - pc)) if pc is not None else None,
        "n_per_arm": ceil(n_prop(pc, pc * (1 - CHANGE))) if pc else None,
        "n_per_arm_doubling": ceil(n_prop(pc, min(1.0, 2 * pc))) if pc else None,
    }
    have = [
        sum(per_thread.get(t, 0) for t in threads[(r[0], r[1])])
        for r in lead
        if threads.get((r[0], r[1]))
    ]
    if len(have) >= 2 and st.mean(have):
        mu, sd = st.mean(have), st.stdev(have)
        k["typed messages in a row's threads"] = {
            "rows": len(have),
            "mean": mu,
            "spread": sd,
            "spread_of": "sd of a count",
            "zero_share": sum(c == 0 for c in have) / len(have),
            "n_per_arm": ceil(n_mean(sd, CHANGE * mu)),
        }
    else:
        k["typed messages in a row's threads"] = {"rows": len(have), "n_per_arm": None}

    clusters = {}
    for name, rows, col, f in (
        ("ln lead time", lead, 3, lambda v: math.log(max(v, 1.0))),
        ("ln PR open to merge", prs, 3, lambda v: math.log(max(v, 1.0))),
        ("first round", [r for r in prs if r[4] is not None], 4, float),
    ):
        groups = defaultdict(list)
        for r in rows:
            groups[r[2]].append(f(r[col]))
        rho, m = icc(groups)
        clusters[name] = {
            "days": len(groups),
            "rows_a_day": m,
            "icc": rho,
            "n_factor_stratified": None if rho is None else 1 - rho,
        }
    out["clusters"] = clusters

    full = []
    for view, col in (
        ("weekly_pr_to_merge", "median"),
        ("weekly_lead_time", "median"),
        ("weekly_first_round", "share"),
        ("weekly_change_failure", "100.0 * rate"),
    ):
        vals = [
            v
            for (v,) in db.execute(
                f"SELECT {col} FROM {view} WHERE week >= date(:lo, '-6 days', 'weekday 0') AND "
                "week <= :w "
                f"AND {em("datetime(date(week, '+7 days'), 'utc')")} <= :end ORDER BY week",
                {"lo": span.fit_start, "w": span.week, "end": w["end"]},
            )
            if v is not None
        ]
        cv = st.stdev(vals) / st.mean(vals) if len(vals) >= 2 and st.mean(vals) else None
        full.append(
            {
                "view": view,
                "values": vals,
                "cv": cv,
                "weeks_per_period": ceil(n_mean(cv, CHANGE)) if cv else None,
            }
        )
    out["weekly"] = full

    today = min(
        date.fromisoformat(last_day),
        date.fromisoformat(db.execute("SELECT date(?, 'localtime')", (span.end,)).fetchone()[0]),
    )
    days = [(today - timedelta(days=i)).isoformat() for i in range(1, 8)]
    merged = Counter(r[2] for r in lead)
    out["rate"] = {
        "days": days,
        "launched": [launched[d] for d in days],
        "merged": [merged[d] for d in days],
        "merged_a_day": st.mean(merged[d] for d in days),
    }
    out["arms"] = {
        "rows_with_arm": len(arm),
        "merged": dict(
            sorted(Counter(arm[(r[0], r[1])] for r in lead if (r[0], r[1]) in arm).items())
        ),
    }
    targets = {n: x for n, x in k.items() if n in TARGETS and x.get("n_per_arm")}
    if targets:
        name, x = max(targets.items(), key=lambda kv: (kv[1]["n_per_arm"], kv[0]))
        rate = out["rate"]["merged_a_day"]
        out["limiter"] = {
            "by": "spread",
            "kpi": name,
            "n_per_arm": x["n_per_arm"],
            "days_for_two_arms": (2 * x["n_per_arm"] / rate) if rate else None,
        }
    else:
        out["limiter"] = {"by": "rows", "n_per_arm": None}
    return out


def num(x) -> str:
    return "-" if x is None else f"{x:.3f}" if isinstance(x, float) else str(x)


def show(o: dict) -> None:
    print(
        f"power: rows merged {o['span']['days'][0]} to before {o['span']['days'][1]}, read to "
        f"{o['span']['end']}, "
        f"seed {o['seed']}; rows per arm for a {CHANGE:.0%} change at 80% power"
    )
    for name, x in o["kpis"].items():
        print(
            f"  {name:36} n {x['rows']:5d}  spread {num(x.get('spread')):>7}  rows per arm "
            f"{num(x['n_per_arm']):>7}"
            + (f"  power at n {num(x['power_at_n'])}" if x.get("power_at_n") is not None else "")
        )
    for name, c in o["clusters"].items():
        print(
            f"  clustering, {name}: days {c['days']}, rows a day {c['rows_a_day']:.1f}, ICC "
            f"{num(c['icc'])}"
        )
    for x in o["weekly"]:
        print(
            f"  {x['view']}: full weeks {len(x['values'])}, CV {num(x['cv'])}, weeks per "
            f"period {num(x['weeks_per_period'])}"
        )
    r = o["rate"]
    print(
        f"  rate: rows merged a day over {r['days'][-1]}..{r['days'][0]}: {r['merged']}, mean "
        f"{r['merged_a_day']:.1f}"
    )
    print(
        f"  arms: {o['arms']['rows_with_arm']} rows with an arm, merged in the span "
        f"{o['arms']['merged']}"
    )
    lim = o["limiter"]
    if lim["by"] == "spread":
        days = lim["days_for_two_arms"]
        print(
            f"limiter: spread, of the KPIs an A/B targets {lim['kpi']} needs the most, "
            f"{lim['n_per_arm']} rows per arm, "
            + (
                f"{days:.1f} days of merges for two arms at the span's rate"
                if days
                else "and no rows merged a day to fill them"
            )
        )
    else:
        print("limiter: rows, the span holds too few rows to read a spread")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_flags(ap)
    a = ap.parse_args()
    span = from_args(ap, a)
    out = measure(connect(a.store), span)
    show(out)
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
