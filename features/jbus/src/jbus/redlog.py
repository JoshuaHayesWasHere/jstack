"""What a red head's failed jobs' logs name, read by `jbus.stall.twice`: the failed step's own part
of a job's log (`failed_step`), the failed tests (`named`), and every failed test and lint rule with
its path (`failures`)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from jbus.watch import job_log
from jmerge.joblog import failed_in, plain

if TYPE_CHECKING:
    from jbus import rebase
    from jbus.passes import Pass

RUN = re.compile(r"(?m)^(?:\S+ )?##\[group\]Run ")
EXITED = re.compile(r"(?m)^(?:\S+ )?##\[error\]Process completed with exit code .*$")


def failed_step(log: str) -> str:
    """Return the own part of a job's log of the step that failed the job: from the last
    `##[group]Run` line before the last `##[error]Process completed with exit code` line, to that
    line. An earlier error line is a step's that ran with `continue-on-error: true`, failed, and
    let the job go on. Where no such error line is given, the part runs to the log's end, and where
    no `Run` line comes before it, from the log's start."""
    exits = list(EXITED.finditer(log))
    end = exits[-1].end() if exits else len(log)
    starts = [run.start() for run in RUN.finditer(log, 0, end)]
    return log[starts[-1] if starts else 0 : end]


def named(run: Pass, red: rebase.Red) -> list[str]:
    """Return the failed tests that the failed jobs' logs name (`failed_in`), or nothing where no
    log GitHub gave names one."""
    tests: dict[str, None] = {}
    for repo, job in red.jobs:
        log = job_log(run, repo, job)
        tests.update(dict.fromkeys(failed_in(log).tests if log is not None else ()))
    return list(tests)


LINT = re.compile(r"(?m)\berror ([a-z0-9][a-z0-9-]*): ([^\s:]+)")
"""`repo-standard conform`'s line for an error of a rule: the rule's id and the path it names."""


def failures(run: Pass, red: rebase.Red) -> set[str]:
    """Return what failed at a head: each failed test's id and each lint rule with its path that
    the failed jobs' logs name, or the failed checks' names where the logs name neither."""
    found: set[str] = set()
    for repo, job in red.jobs:
        log = plain(job_log(run, repo, job) or "")
        found.update(failed_in(log).tests)
        found.update(f"{rule} {path}" for rule, path in LINT.findall(log))
    return found or {f"check {name}" for name in red.names}
