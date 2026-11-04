"""A pull request whose required check failed, judged again over today's base.

A pull request's check runs on its merge with the base as the base was then, and a rerun runs on
that same merge. So a check that failed while the base was red stays red after the base is
fixed, and no push of the crew's is owed for it. `jmerge` judges such a pull request again once
its base has moved since the check started and is not red: `BaseMerge` asks GitHub to merge the
base into the branch, and GitHub's new check at the new head decides the rest by the normal path.
A green pull request whose base moved under it takes the same path: its check ran over a base
that is gone, so where its head merges cleanly over today's base, GitHub merges the base into it
too (`cli.Repo.over_main`).

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
    ) -> str:
        """Why the pull request waits once its base's merge into it is asked of GitHub: `asked`
        once it is asked, and `due` in a run that asks nothing."""
        was = self.was(one, tip)
        if was is not None and isinstance(was.get("said"), str):
            return was["said"]
        values = {"base": one.base, "tip": tip[:SHA]}
        if not self.run:
            return due.format(**values)
        why, answered = self.ask(one)
        said = ready.BASE_MERGE_REFUSED.format(**values, why=why) if why else asked.format(**values)
        if answered:
            self.keep(one, tip, said=said)
        return said

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
        kept = {number: was for number, was in known.items() if number in numbers}
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
