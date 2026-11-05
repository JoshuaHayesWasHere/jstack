"""The A/B verdict: a paired interval over tasks, an exact test for a pass/fail family, and the
rule of `README.md`, "The rule". Pure: no file, no process, no clock."""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Literal

Kind = Literal["graded", "pass/fail"]
KINDS: tuple[Kind, ...] = ("graded", "pass/fail")
# The smallest difference a family calls, when its task file names none: 0.03 on a graded score,
# one failed trial in nine on a pass/fail one.
MDE: dict[Kind, float] = {"graded": 0.03, "pass/fail": 1 / 9}
RESAMPLES = 10_000
ALPHA = 0.05
# A mean of differences that are all 0 can come out as 1e-17: below this it is 0.
EPS = 1e-12

Word = Literal["B better", "B worse", "no measurable difference", "inconclusive: A/A not clean"]


@dataclass(frozen=True)
class Interval:
    mean: float
    low: float
    high: float

    @property
    def excludes_zero(self) -> bool:
        return self.low > EPS or self.high < -EPS


@dataclass(frozen=True)
class Exact:
    """Failed trials over all trials, in each of two arms, and the two-sided Fisher p."""

    failed: tuple[int, int]
    total: tuple[int, int]
    p: float


@dataclass(frozen=True)
class Verdict:
    word: Word
    diff: Interval
    aa: Interval
    mde: float
    # Pass/fail families only: B against A, and A-again against A.
    exact: Exact | None = None
    exact_aa: Exact | None = None

    @property
    def aa_excludes_below_mde(self) -> bool:
        """The A/A interval excludes 0 by less than the mde: what a 95% interval does about one
        time in twenty, and not a reason to distrust the run."""
        return self.word != "inconclusive: A/A not clean" and self.aa.excludes_zero


def paired_interval(diffs: list[float], seed: str) -> Interval:
    """The mean of the per-task differences and its 95% bootstrap interval: the tasks resampled
    with replacement `RESAMPLES` times from `random.Random(seed)`, the 2.5th and 97.5th
    percentiles of the resampled means."""
    n = len(diffs)
    rng = random.Random(seed)
    means = sorted(math.fsum(rng.choices(diffs, k=n)) / n for _ in range(RESAMPLES))
    at = lambda q: means[round(q * (RESAMPLES - 1))]  # noqa: E731
    return Interval(math.fsum(diffs) / n, at(0.025), at(0.975))


def fisher(failed_a: int, total_a: int, failed_b: int, total_b: int) -> float:
    """The two-sided p of Fisher's exact test on failed against passed in two arms: the sum of
    the probabilities of every table with these margins that is no likelier than this one."""
    failed, total = failed_a + failed_b, total_a + total_b
    lo, hi = max(0, failed - total_b), min(failed, total_a)
    whole = math.comb(total, total_a)
    prob = {
        x: math.comb(failed, x) * math.comb(total - failed, total_a - x) / whole
        for x in range(lo, hi + 1)
    }
    seen = prob[failed_a]
    return min(1.0, math.fsum(p for p in prob.values() if p <= seen * (1 + 1e-7)))


def _exact(a: dict[str, list[float]], other: dict[str, list[float]]) -> Exact:
    failed = tuple(sum(v < 1 for vs in arm.values() for v in vs) for arm in (a, other))
    total = tuple(sum(len(vs) for vs in arm.values()) for arm in (a, other))
    return Exact(failed, total, fisher(failed[0], total[0], failed[1], total[1]))


def verdict(
    kind: Kind,
    mde: float,
    a: dict[str, list[float]],
    again: dict[str, list[float]],
    b: dict[str, list[float]],
    seed: str,
) -> Verdict:
    """The rule for one family. Each arm maps a task to its trials' scores; a task's score is
    the mean of its trials, and the arms are paired by task.

    - `inconclusive: A/A not clean` when A-again against A would itself be called: its test
      shows a difference (the interval excludes 0, or for a pass/fail family Fisher p < 0.05)
      and its mean is at least the mde.
    - `B better` or `B worse` when B against A shows a difference by the same test and its mean
      is at least the mde.
    - Else `no measurable difference`.
    """
    tasks = sorted(a)
    if sorted(again) != tasks or sorted(b) != tasks:
        raise ValueError("the three arms do not hold the same tasks")
    mean = {
        t: (statistics.fmean(a[t]), statistics.fmean(again[t]), statistics.fmean(b[t]))
        for t in tasks
    }
    diff = paired_interval([mean[t][2] - mean[t][0] for t in tasks], f"{seed}:B")
    aa = paired_interval([mean[t][1] - mean[t][0] for t in tasks], f"{seed}:A-again")
    exact = exact_aa = None
    if kind == "pass/fail":
        exact, exact_aa = _exact(a, b), _exact(a, again)
        shows, shows_aa = exact.p < ALPHA, exact_aa.p < ALPHA
    else:
        shows, shows_aa = diff.excludes_zero, aa.excludes_zero
    big = lambda i: abs(i.mean) >= mde - EPS  # noqa: E731
    if shows_aa and big(aa):
        word: Word = "inconclusive: A/A not clean"
    elif shows and big(diff):
        word = "B better" if diff.mean > 0 else "B worse"
    else:
        word = "no measurable difference"
    return Verdict(word, diff, aa, mde, exact, exact_aa)
