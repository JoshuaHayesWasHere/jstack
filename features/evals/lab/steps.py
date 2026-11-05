# /// script
# requires-python = ">=3.12"
# dependencies = ["scipy>=1.14", "numpy>=2"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""Per-step samples of the jstack pipeline from a copy of the telemetry store, by week, with
shift tests: kpi-lab-2's steps, moved into the repo.

    uv run --script steps.py --store <copy> --fit 2026-10-19..2026-11-01 --week 2026-11-01 \\
        --end 2026-11-03T01:37:48Z --json steps.json

It reads the weeks from the fit's first week to `--week`. Each step prints, per week: n, median,
p90, max, and a shape note; then a Kruskal-Wallis test across the weeks with n >= 5, and
Mann-Whitney U and Kolmogorov-Smirnov between each pair of consecutive weeks. A shift is "proved"
at p < 0.01 after a Bonferroni factor of the pair count. A value counts when its step's own time
(a merge, a launch, a review) is before `--end`. The dependencies resolve as they stood on
`exclude-newer`, so the same copy gives the same numbers after a release of scipy.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np
from scipy import stats
from span import add_flags, connect, from_args

PROJECT = "jstack"
WEEK = "date({d}, '-6 days', 'weekday 0')"
RED = "('failure', 'timed_out', 'startup_failure', 'action_required')"
CREW_FIX = (
    "('no-fixed', 'fix-unreviewed', 'content-changed', 'dropped', 'scoped-unruled', "
    "'unruled-drops', 'declines-unruled')"
)
CLASH = (
    "('conflicts', 'base-moved-asked', 'base-merge-asked', 'fresh-conflict', 'base-merge-refused')"
)
REVIEW_EVENTS_FROM = "2026-10-20"
"""The first day the store holds a `review` event for every reviewed row."""
WAIT_LABELS_FROM = "2026-10-29"
"""The first day of merges whose `merge.log` waits all carry a label (labels from 10-28)."""
MIN_N = 5


def before(x: str) -> str:
    """A step's own time, before `--end`."""
    return f"julianday({x}) < julianday(:end)"


def checks(p: str, red: bool) -> str:
    """Each merged PR's pull_request check runs, or red ones, counted once per PR and joined."""
    runs = f"CASE WHEN conclusion IN {RED} THEN run END" if red else "run"
    return (
        f"WITH c AS (SELECT pr, count(DISTINCT {runs}) AS n FROM ci_jobs WHERE project='{p}' "
        "AND event='pull_request' GROUP BY pr) "
        "SELECT t.week, coalesce(c.n, 0) FROM pr_times t LEFT JOIN c ON c.pr = t.pr "
        f"WHERE t.project='{p}' AND {before('t.merged_at')}"
    )


def waits(p: str, labels: str) -> str:
    """Each merged PR's wait spells on `labels`: a wait so labelled after a line that was not."""
    return (
        f"WITH w AS (SELECT number, at, verb='wait' AND label IN {labels} AS hit, "
        f"lag(verb='wait' AND label IN {labels}, 1, 0) OVER (PARTITION BY number "
        f"ORDER BY at, key) AS before FROM merges WHERE project='{p}' AND verb IN "
        "('wait','merged')) "
        "SELECT t.week, (SELECT count(*) FROM w WHERE w.number=t.pr AND hit AND NOT before) "
        f"FROM pr_times t WHERE t.project='{p}' AND t.day >= '{WAIT_LABELS_FROM}' "
        f"AND {before('t.merged_at')}"
    )


def steps(p: str) -> dict[str, tuple[str, str]]:
    """Each step: (unit, SQL giving rows of (week, value)), cut at `:end` on the step's time."""
    return {
        "arrivals: rows proposed per local day": (
            "rows/day",
            f"SELECT {WEEK.format(d='day')}, count(*) FROM items WHERE project='{p}' "
            f"AND verb='proposed' AND {before('at')} GROUP BY day",
        ),
        "arrivals: minutes between proposals": (
            "min",
            f"SELECT {WEEK.format(d='day')}, "
            "(julianday(at) - julianday(lag(at) OVER (ORDER BY at, key))) * 1440 "
            f"FROM items WHERE project='{p}' AND verb='proposed' AND {before('at')}",
        ),
        "go to launch (row_goes.approved -> first launched)": (
            "min",
            f"SELECT {WEEK.format(d='l.day')}, (julianday(l.at)-julianday(g.approved))*1440 "
            "FROM row_goes g JOIN row_moves l ON l.project=g.project AND l.slug=g.slug "
            f"AND l.to_status='launched' WHERE g.project='{p}' AND l.at >= g.approved "
            f"AND {before('l.at')}",
        ),
        "crew run (first launched -> first pr)": (
            "min",
            f"SELECT {WEEK.format(d='r.day')}, (julianday(r.at)-julianday(l.at))*1440 "
            "FROM row_moves l JOIN row_moves r ON r.project=l.project AND r.slug=l.slug "
            f"AND r.to_status='pr' WHERE l.project='{p}' AND l.to_status='launched' "
            f"AND r.at>=l.at AND {before('r.at')}",
        ),
        "checks: pull_request runs per merged PR": ("runs", checks(p, red=False)),
        "checks: red pull_request runs per merged PR": ("runs", checks(p, red=True)),
        "review: 'review' events (distinct ## Review texts) per merged row": (
            "events",
            f"SELECT {WEEK.format(d='m.day')}, (SELECT count(*) FROM events e "
            "WHERE e.project=m.project AND e.slug=m.slug AND e.event='review' "
            f"AND {before('e.at')}) FROM row_moves m WHERE m.project='{p}' "
            f"AND m.to_status='merged' AND m.day >= '{REVIEW_EVENTS_FROM}' AND {before('m.at')}",
        ),
        "review: first pr -> first 'review' event": (
            "min",
            f"SELECT {WEEK.format(d='r.day')}, (julianday(min(e.at))-julianday(r.at))*1440 "
            "FROM row_moves r JOIN events e ON e.project=r.project AND e.slug=r.slug "
            f"AND e.event='review' AND e.at>=r.at AND {before('e.at')} WHERE r.project='{p}' "
            f"AND r.to_status='pr' AND r.day >= '{REVIEW_EVENTS_FROM}' GROUP BY r.slug",
        ),
        "fix rounds: CREW_FIX wait spells per merged PR": ("spells", waits(p, CREW_FIX)),
        "clashes: conflict/base-moved wait spells per merged PR": ("spells", waits(p, CLASH)),
        "merge wait: PR open -> merge (pr_times)": (
            "min",
            f"SELECT week, minutes FROM pr_times WHERE project='{p}' AND minutes >= 0 "
            f"AND {before('merged_at')}",
        ),
        "merge wait: first 'readied' wait -> merged line": (
            "min",
            "SELECT " + WEEK.format(d="m.day") + ", (julianday(m.at)-julianday(min(w.at)))*1440 "
            "FROM merges m JOIN merges w ON w.project=m.project AND w.number=m.number "
            f"AND w.label='readied' AND w.at<=m.at WHERE m.project='{p}' AND m.verb='merged' "
            f"AND {before('m.at')} GROUP BY m.number",
        ),
        "lead time (lead_times, go -> merge)": (
            "min",
            f"SELECT week, minutes FROM lead_times WHERE project='{p}' AND {before('merged_at')}",
        ),
        "main: red spells, minutes to green (main_spells)": (
            "min",
            f"SELECT week, minutes_to_green FROM main_spells WHERE project='{p}' "
            f"AND minutes_to_green IS NOT NULL AND {before('green_at')}",
        ),
    }


def shape(v: np.ndarray) -> str:
    if len(v) < MIN_N:
        return "-"
    if np.all(v == np.round(v)) and v.max() <= 10:
        zero = np.mean(v == 0)
        dispersion = v.var() / max(v.mean(), 1e-9)
        return f"count; zero {zero:.0%}, mean {v.mean():.2f}, var/mean {dispersion:.2f}"
    pos = v[v > 0]
    skew = stats.skew(v)
    if len(pos) >= MIN_N:
        lg = np.log(pos)
        _, pl = stats.shapiro(lg) if len(lg) <= 5000 else (0, float("nan"))
        return f"skew {skew:.1f}; log-normal Shapiro p {pl:.3f}"
    return f"skew {skew:.1f}"


def measure(db, first: str, last: str, end: str) -> dict:
    out = {}
    for name, (unit, sql) in steps(PROJECT).items():
        by: dict[str, list[float]] = defaultdict(list)
        for week, value in db.execute(sql, {"end": end}):
            if week and first <= week <= last and value is not None:
                by[week].append(float(value))
        weeks = {}
        for w in sorted(by):
            v = np.array(sorted(by[w]))
            weeks[w] = {
                "n": len(v),
                "median": float(np.median(v)),
                "p90": float(np.percentile(v, 90)),
                "max": float(v.max()),
                "shape": shape(v),
            }
        big = [w for w in sorted(by) if len(by[w]) >= MIN_N]
        step = {"unit": unit, "weeks": weeks, "kruskal": None, "pairs": []}
        if len(big) >= 2:
            h, p = stats.kruskal(*(sorted(by[w]) for w in big))
            step["kruskal"] = {"weeks": big, "h": float(h), "p": float(p)}
            pairs = list(zip(big, big[1:], strict=False))
            for x, y in pairs:
                u = stats.mannwhitneyu(sorted(by[x]), sorted(by[y]))
                k = stats.ks_2samp(sorted(by[x]), sorted(by[y]))
                shift = min(u.pvalue, k.pvalue) * len(pairs) < 0.01
                step["pairs"].append(
                    {
                        "from": x,
                        "to": y,
                        "mann_whitney_p": float(u.pvalue),
                        "ks_d": float(k.statistic),
                        "ks_p": float(k.pvalue),
                        "verdict": "SHIFT" if shift else "same",
                    }
                )
        out[name] = step
    return out


def show(out: dict, first: str, last: str) -> dict:
    tested = [
        (s["weeks"][w]["n"], name, w)
        for name, s in out.items()
        if s["kruskal"]
        for w in s["kruskal"]["weeks"]
    ]
    shifts = sum(p["verdict"] == "SHIFT" for s in out.values() for p in s["pairs"])
    pairs = sum(len(s["pairs"]) for s in out.values())
    print(
        f"steps: weeks {first} to {last}, {len(out)} steps, {shifts} of {pairs} week-to-week "
        "pairs SHIFT"
    )
    for name, s in out.items():
        print(f"\n## {name} [{s['unit']}]")
        for w, x in s["weeks"].items():
            print(
                f"  {w}  n {x['n']:4d}  median {x['median']:9.1f}  p90 {x['p90']:9.1f}  max "
                f"{x['max']:9.1f}  {x['shape']}"
            )
        if s["kruskal"]:
            k = s["kruskal"]
            print(f"  Kruskal-Wallis over {','.join(k['weeks'])}: H {k['h']:.1f}, p {k['p']:.2g}")
        for p in s["pairs"]:
            print(
                f"    {p['from']} vs {p['to']}: Mann-Whitney p {p['mann_whitney_p']:.2g}, "
                f"KS D {p['ks_d']:.2f} p {p['ks_p']:.2g} -> {p['verdict']}"
            )
    if tested:
        n, name, w = min(tested)
        limiter = {"by": "n", "n": n, "step": name, "week": w}
        print(
            f"\nlimiter: n, the smallest tested week holds {n} values ({name}, {w}): at p < "
            "0.01 over "
            f"{pairs} pairs, a shift smaller than its spread is not seen"
        )
    else:
        limiter = {"by": "weeks", "n": 0}
        print(
            f"\nlimiter: weeks, no step has two weeks of {MIN_N} or more values, so no shift "
            "can be tested"
        )
    return limiter


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_flags(ap)
    a = ap.parse_args()
    span = from_args(ap, a)
    db = connect(a.store)
    first = db.execute("SELECT " + WEEK.format(d="?"), (span.fit_start,)).fetchone()[0]
    out = measure(db, first, span.week, span.end)
    limiter = show(out, first, span.week)
    if a.json:
        doc = {
            "span": {"weeks": [first, span.week], "end": span.end},
            "steps": out,
            "limiter": limiter,
        }
        a.json.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
