"""A pull request whose required check failed, judged again over today's base.

A pull request's check runs on its merge with the base as the base was then, and a rerun runs on
that same merge. So a check that failed while the base was red stays red after the base is
fixed, and no push of the crew's is owed for it. `jmerge` judges such a pull request again once
its base has moved since the check started and is not red: `BaseMerge` asks GitHub to merge the
base into the branch, and GitHub's new check at the new head decides the rest by the normal path.
A green pull request whose base moved under it takes the same path: its check ran over a base
that is gone, so where its head merges cleanly over today's base, GitHub merges the base into it
too (`cli.Repo.over_main`), one pull request at a time: the one at the head of the line
(`BaseMerge.holder`), which every other one whose base moved, green, red or with a check
that has no run, waits behind.

GitHub's endpoint merges the base into the branch and rewrites no history:
https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request-branch. `expected_head_sha`
makes it refuse a branch that moved since `jmerge` judged it. A review stands across that merge
when the patch is unchanged, as across a rebase: its range-diff shows no content
(`rangediff.verdict`), which leaves out the merge commit.

A pull request whose last two check runs failed a same pytest id, which main's check at neither
run's base failed, is broken on its own, and a merge of the base would only fail it again
(#494, 2026-10-26: nine merges of main, each red on the same test). `Repeated` finds those ids
in the `FAILED <id>` lines of `gh run view <id> --log-failed`. Its answer is kept for the head,
the base tip and the check, "not repeated" as well, so no run log is read twice for one head and
tip: each run of `jmerge` read the logs of every red pull request again (2026-11-03).

Every call to GitHub here goes through `backoff`: after a refusal for the rate limit, none is made
until GitHub said it may be.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

from jmerge import backoff, ready
from jsettings import store

NAME = "base-merges.json"
SHA = 12
REFUSED = re.compile(r"\(HTTP (409|422)\)")
FAILED = re.compile(r"\sFAILED (\S+::\S+)")
RUNS = 20


class BaseMerge:
    """The branch updates `jmerge` asked GitHub for, one record for a pull request, kept in
    `base-merges.json` in the project's state: the head, the base tip, and what GitHub said. A
    record of the same head and tip is said again and not asked again. A failure to ask, such as
    a `gh` that did not run, a 5xx, a 403 or 429 rate limit, keeps no record, so a later run asks
    again, after the wait a rate limit sets (`backoff`): only GitHub's answer about the branch, a
    merge or a 409 or 422 refusal, is kept. The record keeps too whether each failed check was
    `repeated`. A record goes once its pull request is no longer open (`open_only`). A run that
    asks nothing, `--check`, keeps what it learns for itself alone."""

    def __init__(self, main: Path, state: Path, about: list[str], run: bool) -> None:
        self.main = main
        self.path = state / NAME
        self.about = about
        self.run = run
        self.records: dict | None = None
        self.repeated = Repeated(main, about)

    def known(self) -> dict:
        if self.records is None:
            self.records = store.read_dict(self.path)
        return self.records

    def of(
        self,
        one: ready.PullRequest,
        tip: str,
        asked: str = ready.BASE_MERGE_ASKED,
        due: str = ready.BASE_MERGE_DUE,
        *,
        line: bool = False,
    ) -> str:
        """Why the pull request waits once its base's merge into it is asked of GitHub: `asked`
        once it is asked, and `due` in a run that asks nothing. With `line`, a merge GitHub took
        puts the pull request at the head of the line (`holder`), in a run that asks nothing
        for that run alone."""
        was = self.was(one, tip)
        if was is not None and isinstance(was.get("said"), str):
            return was["said"]
        values = {"base": one.base, "tip": tip[:SHA]}
        if not self.run:
            if line:
                self.keep(one, tip, line=True)
            return due.format(**values)
        why, answered = self.ask(one)
        said = ready.BASE_MERGE_REFUSED.format(**values, why=why) if why else asked.format(**values)
        if answered:
            self.keep(one, tip, said=said, line=line and not why)
        return said

    def holder(self, numbers: Collection[int]) -> int | None:
        """The pull request at the head of the line, of the open ones in `numbers`: the one
        GitHub last took a merge of the base into because its base moved after its check
        (`cli.Repo.over_main`), until `release`. GitHub merges the base into no other green
        pull request while it holds the line, so each merge costs one rerun."""
        known = self.known()
        held = (n for n in numbers if (known.get(str(n)) or {}).get("line") is True)
        return next(held, None)

    def release(self, one: ready.PullRequest) -> None:
        """Take the pull request from the head of the line."""
        was = self.known().get(str(one.number))
        if isinstance(was, dict) and was.get("line"):
            self.records = {**self.known(), str(one.number): {**was, "line": False}}
            if self.run:
                store.write_json(self.path, self.records)

    def stuck(self, one: ready.PullRequest) -> dict:
        """What `jmerge` did about a run GitHub kept queued at the pull request's head
        (`cli.Repo.unstuck`): `since`, when GitHub had queued the run it restarted, `reopen`
        while the reopen of that restart is still owed, and `gave_up` once it gave up the line.
        Nothing for another head."""
        was = self.known().get(str(one.number))
        kept = was.get("stuck") if isinstance(was, dict) else None
        return kept if isinstance(kept, dict) and kept.get("head") == one.head else {}

    def keep_stuck(self, one: ready.PullRequest, **kept: object) -> None:
        """Keep `kept` in what `stuck` says of the pull request's head, over what it said."""
        was = self.known().get(str(one.number))
        record = was if isinstance(was, dict) else {}
        stuck = {**self.stuck(one), "head": one.head, **kept}
        self.records = {**self.known(), str(one.number): {**record, "stuck": stuck}}
        if self.run:
            store.write_json(self.path, self.records)

    def restart(self, one: ready.PullRequest, since: datetime) -> str:
        """Close and reopen the pull request, so GitHub starts a new run of each of its
        workflows in their concurrency groups, which cancels the queued one: GitHub refuses to
        rerun a run it has not ended, and a cancel can leave it queued (#1028, 2026-11-04). The
        restart is kept before the close, with the reopen owed, so a run that stops between the
        two leaves a record that the next run reopens by (`reopen`), and none restarts twice.
        Return nothing, or why the close or the reopen failed."""
        self.keep_stuck(one, since=since.isoformat(), reopen=True)
        closed = self.gh("pr", "close", str(one.number))
        if closed.returncode:
            self.keep_stuck(one, reopen=False)
            return _said(closed)
        why = self.reopened(one.number)
        if not why:
            self.keep_stuck(one, reopen=False)
        return why

    def reopen(self, numbers: Collection[str]) -> None:
        """Reopen each pull request whose restart's reopen is owed, and that is not open, in
        `numbers`: a run of `jmerge` stopped between the close and the reopen, or GitHub refused
        the reopen. One that is open again owes none. A reopened one holds the line no more, for
        another took it while it was closed."""
        for number in [number for number in self.known() if _owed(self.known()[number])]:
            if number in numbers or not self.reopened(number):
                was = self.known()[number]
                kept = {**was, "stuck": {**was["stuck"], "reopen": False}}
                if number not in numbers:
                    kept["line"] = False
                self.records = {**self.known(), number: kept}
                if self.run:
                    store.write_json(self.path, self.records)

    def reopened(self, number: int | str) -> str:
        """Reopen the pull request, and return nothing, or why it was not."""
        said = self.gh("pr", "reopen", str(number))
        return _said(said) if said.returncode else ""

    def gh(self, *args: str) -> subprocess.CompletedProcess[str]:
        return backoff.run(
            "gh",
            *args,
            cwd=self.main,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )

    def repeats(self, one: ready.PullRequest, tip: str, check: str) -> bool:
        """Whether the pull request failed a same test of its own in its last two runs of
        `check` (`Repeated`), so that its base is not merged into it. The answer is kept for the
        head, the base tip and the check, so GitHub's logs are read again only once the head or
        the tip moves. An answer GitHub left unsettled, a call it did not answer or a run of the
        base still going, is not kept."""
        was = self.was(one, tip) or {}
        kept = was.get("repeated")
        if isinstance(kept, dict) and isinstance(kept.get(check), list):
            return bool(kept[check])
        ids, settled = self.repeated.of(one, check)
        if settled:
            known = kept if isinstance(kept, dict) else {}
            self.keep(one, tip, repeated={**known, check: sorted(ids)})
        return bool(ids)

    def was(self, one: ready.PullRequest, tip: str) -> dict | None:
        was = self.known().get(str(one.number))
        if isinstance(was, dict) and (was.get("head"), was.get("tip")) == (one.head, tip):
            return was
        return None

    def keep(self, one: ready.PullRequest, tip: str, **kept: object) -> None:
        """Keep `kept` in the record of the head and tip, over what it held."""
        now = datetime.now().astimezone()
        was = self.was(one, tip) or {}
        record = {**was, "head": one.head, "tip": tip, **kept, "at": f"{now:%Y-%m-%dT%H:%M:%S%z}"}
        self.records = {**self.known(), str(one.number): record}
        if self.run:
            store.write_json(self.path, self.records)

    def open_only(self, numbers: Collection[str]) -> None:
        """Drop the record of each pull request whose number is not in `numbers`, the open ones:
        a merged or closed pull request is never judged again, and its record would only grow the
        file."""
        known = self.known()
        kept = {number: was for number, was in known.items() if number in numbers or _owed(was)}
        if kept != known:
            self.records = kept
            if self.run:
                store.write_json(self.path, kept)

    def ask(self, one: ready.PullRequest) -> tuple[str, bool]:
        """Ask GitHub to merge the base into the branch. Return nothing, or why it did not, and
        whether GitHub answered: `gh api` ends its error line with `(HTTP <status>)`. It asks
        with `--include`, so that a refusal for the rate limit waits as long as GitHub's
        `retry-after` says (`backoff`)."""
        path = f"repos/{{owner}}/{{repo}}/pulls/{one.number}/update-branch"
        ran = backoff.run(
            *("gh", "api", "-X", "PUT", path, "-f", f"expected_head_sha={one.head}", "--include"),
            cwd=self.main,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        if not ran.returncode:
            return "", True
        if backoff.is_wait(ran.stderr or ""):
            return ran.stderr.strip(), False
        try:
            message = json.loads(backoff.body(ran.stdout)).get("message")
        except (ValueError, AttributeError):
            message = None
        lines = (ran.stderr or ran.stdout).strip().splitlines()
        why = str(message or (lines[-1] if lines else f"gh exited {ran.returncode}"))
        return why, bool(REFUSED.search(ran.stderr))


def _owed(was: object) -> bool:
    """Whether a record owes the reopen of a restart (`BaseMerge.restart`)."""
    stuck = was.get("stuck") if isinstance(was, dict) else None
    return isinstance(stuck, dict) and stuck.get("reopen") is True


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    """The last line `gh` wrote of why it failed."""
    lines = (ran.stderr or ran.stdout or "").strip().splitlines()
    return lines[-1] if lines else f"gh exited {ran.returncode}"


class Repeated:
    """The pytest ids a pull request failed in each of its last two check runs, less those that
    main's check at either run's base failed: main's latest run of the check started by the time
    the pull request's run started. A run's ids are the `FAILED <id>` lines of its log. Where
    GitHub does not answer, or a run of main is not known, it finds none, and the base is merged
    as before. A run of `jmerge` reads each list of runs and each log once."""

    def __init__(self, main: Path, about: list[str]) -> None:
        self.main = main
        self.about = about
        self.listed: dict[tuple[str, str, str], list[dict] | None] = {}
        self.logs: dict[str, frozenset[str] | None] = {}

    def of(self, one: ready.PullRequest, check: str) -> tuple[frozenset[str], bool]:
        """The ids, of the runs of the workflow named `check`, and whether the answer is
        settled for the head and the base's tip: GitHub answered each call, and no run it
        reads from was still going."""
        listed = self.runs(one.branch, check, "pull_request")
        if listed is None:
            return frozenset(), False
        settled = all(run.get("status") == "completed" for run in listed)
        last = [run for run in listed if run.get("status") == "completed"][-2:]
        if len(last) < 2 or any(run.get("conclusion") != "failure" for run in last):
            return frozenset(), settled
        logs = [self.failing(run) for run in last]
        if any(log is None for log in logs):
            return frozenset(), False
        shared = (logs[0] or frozenset()) & (logs[1] or frozenset())
        if not shared:
            return frozenset(), settled
        base = self.runs(one.base, check, "push")
        if base is None:
            return frozenset(), False
        if any(run.get("status") != "completed" and run["at"] <= last[-1]["at"] for run in base):
            settled = False
        mains = [run for run in base if run.get("conclusion") in ("success", "failure")]
        for run in last:
            before = [main for main in mains if main["at"] <= run["at"]]
            if not before:
                return frozenset(), settled
            if before[-1].get("conclusion") == "failure":
                failed = self.failing(before[-1])
                if failed is None:
                    return frozenset(), False
                shared -= failed
        return shared, settled

    def runs(self, branch: str, check: str, event: str) -> list[dict] | None:
        """The runs of the check's workflow on the branch, oldest first, the ended ones with
        none cancelled and those still going, or None where GitHub gave no list."""
        key = (branch, check, event)
        if key not in self.listed:
            self.listed[key] = self.list(*key)
        return self.listed[key]

    def list(self, branch: str, check: str, event: str) -> list[dict] | None:
        said = self.gh(
            "run",
            "list",
            "--branch",
            branch,
            "--workflow",
            check,
            "--event",
            event,
            "--limit",
            str(RUNS),
            "--json",
            "databaseId,status,conclusion,createdAt",
        )
        try:
            listed = json.loads(said or "")
        except ValueError:
            return None
        if not isinstance(listed, list):
            return None
        kept = []
        for run in listed:
            if not isinstance(run, dict) or run.get("conclusion") == "cancelled":
                continue
            try:
                at = datetime.fromisoformat(str(run.get("createdAt")))
            except ValueError:
                continue
            kept.append({**run, "at": at})
        return sorted(kept, key=lambda run: run["at"])

    def failing(self, run: dict) -> frozenset[str] | None:
        """The pytest ids the run failed, or `None` where GitHub gave no log."""
        number = str(run.get("databaseId"))
        if number not in self.logs:
            log = self.gh("run", "view", number, "--log-failed")
            self.logs[number] = None if log is None else frozenset(FAILED.findall(log))
        return self.logs[number]

    def gh(self, *args: str) -> str | None:
        ran = backoff.run(
            "gh",
            *args,
            cwd=self.main,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        return None if ran.returncode else ran.stdout
