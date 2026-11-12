"""Why a failed head's red is not the row's own: the main its check ran on (`tested`), a flake
shared with two other branches (`shared`), a step that failed to fetch what the check needs
(`infra`, `FETCH`, `failed_step`), and a merge of main into the head before it (`merge_of_main`)
that failed something new (`failures`). `stall.twice` reads these before it counts a head, and
keeps the failed tests a counted head's logs name (`named`)."""

from __future__ import annotations

import re
from typing import Any

from jbus import rebase, reverts
from jbus.ci import collect
from jbus.passes import Pass
from jbus.watch import World, _api, job_log, ran
from jmerge.joblog import failed_in, plain


def tested(run: Pass, head: str, red: rebase.Red) -> str | None:
    """Return the main that the head's failed check ran on: the commit that GitHub merged the head
    into, as the first failed job's log that names the merge says, or nothing where no log names
    one. None where a log GitHub did not give might have named it, so the head is judged again on
    a later pass."""
    named = re.compile(rf"Merge {re.escape(head)} into ([0-9a-f]{{40}})")
    unread = False
    for repo, job in red.jobs:
        log = job_log(run, repo, job)
        found = named.search(log) if log is not None else None
        if found:
            return found.group(1)
        unread = unread or log is None
    return None if unread else ""


def shared(run: Pass, pull: dict[str, Any], red: rebase.Red) -> list[str]:
    """Return the tests that failed at the pull request's head where each is a flake by `jbus ci`'s
    rule, failed on two branches besides the pull request's own (`reverts.flaky`), or nothing where
    one is not, or a failed job's log was not given, names no test, or counts a failure or an error
    it names no test of, as a collection error is: that red is the row's own."""
    tests: set[str] = set()
    for repo, job in red.jobs:
        log = job_log(run, repo, job)
        failed = failed_in(log) if log is not None else None
        if failed is None or not failed.tests or failed.count > len(failed.tests):
            return []
        tests.update(failed.tests)
    if not tests or not tests <= reverts.flaky(run, str(pull.get("headRefName") or "")):
        return []
    return sorted(tests)


FETCH = re.compile(
    r"(?im)curl: \(\d+\)|Could not resolve host|Temporary failure in name resolution"
    r"|\b(?:HTTP(?:/[\d.]+)?|returned error:|status(?: code)?:?) ?5\d\d\b"
    r"|\b5\d\d (?:Service Unavailable|Bad Gateway|Gateway Time-?out|Internal Server Error)"
    r"|(?-i:Connection (?:reset by peer|refused|timed out))|Operation timed out"
    r"|ECONNRESET|ETIMEDOUT|EAI_AGAIN"
    r"|(?:Failed|Unable) to download|artifact[^\n]{0,60}download[^\n]{0,40}fail"
)
"""The sign of a download or network failure in a job's log, beside `collect.SIGNS`: a `curl`
error, an HTTP 5xx, a host that did not resolve, a connection reset or timed out, or an artifact
download that failed. The connection's words are matched as the system prints them, so a lint
line that quotes them in prose is no sign."""

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


def infra(run: Pass, world: World, red: rebase.Red) -> list[str]:
    """Return the step each failed job failed at, where every one failed at a step whose log names
    no failed test (`failed_in`) and no make target (`collect.TARGET`), and shows a download or
    network failure (`FETCH`): a step that failed to fetch what the check needs, such as a
    package. Each sign is searched in the failed step's own part of the log (`failed_step`), so a
    passed step's retried download is no sign. Return nothing where a failed check gives no job,
    or a job's failed step or log is not given, or the step's part names a failed test or a make
    target or shows no fetch failure, as a lint step's does: that red is the row's own. The step
    comes from `watch.ran`, which keeps it with the job."""
    if len(red.jobs) < len(red.names):
        return []
    steps: list[str] = []
    for repo, job in red.jobs:
        step = str(ran(run, world, repo, job).get("failed_step") or "")
        log = job_log(run, repo, job)
        own = failed_step(log) if log is not None else ""
        if not step or log is None or failed_in(own).count or not FETCH.search(own):
            return []
        if any(collect.TARGET.match(line) for line in collect.evidence(own)):
            return []
        steps.append(step)
    return steps


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


def named(run: Pass, red: rebase.Red) -> list[str]:
    """Return the failed tests that the failed jobs' logs name (`failed_in`), or nothing where no
    log GitHub gave names one."""
    tests: dict[str, None] = {}
    for repo, job in red.jobs:
        log = job_log(run, repo, job)
        tests.update(dict.fromkeys(failed_in(log).tests if log is not None else ()))
    return list(tests)


def merge_of_main(run: Pass, head: str, before: str, main: str) -> bool:
    """Say whether `head` is a merge of main into `before`, the head seen before it, as a crew's
    `git merge main` and GitHub's update-branch make one: a merge commit whose first parent is
    `before` and whose second is on `main`, the main its check ran on."""
    said = _api(run, f"repos/{{owner}}/{{repo}}/commits/{head}")
    given = said.get("parents") if isinstance(said, dict) else None
    parents = [str(one.get("sha")) for one in given or [] if isinstance(one, dict)]
    if len(parents) != 2 or not before or parents[0] != before:
        return False
    compared = _api(run, f"repos/{{owner}}/{{repo}}/compare/{parents[1]}...{main}")
    status = compared.get("status") if isinstance(compared, dict) else None
    return status in ("ahead", "identical")
