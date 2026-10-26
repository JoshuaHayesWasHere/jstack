"""A pull request whose required check failed, judged again over today's base.

A pull request's check runs on its merge with the base as the base was then, and a rerun runs on
that same merge. So a check that failed while the base was red stays red after the base is
fixed, and no push of the crew's is owed for it. `jmerge` judges such a pull request again once
its base has moved since the check started and is not red: `BaseMerge` asks GitHub to merge the
base into the branch, and GitHub's new check at the new head decides the rest by the normal path.
A green pull request whose base moved under it takes the same path where the repo has a
`fresh-check` file (`cli.Merged`), so no suite runs on this machine for a merge.

GitHub's endpoint merges the base into the branch and rewrites no history:
https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request-branch. `expected_head_sha`
makes it refuse a branch that moved since `jmerge` judged it. A review stands across that merge
when the patch is unchanged, as across a rebase: its range-diff shows no content
(`rangediff.verdict`), which leaves out the merge commit.

A pull request whose last two check runs failed a same pytest id, which main's check at neither
run's base failed, is broken on its own, and a merge of the base would only fail it again
(#494, 2026-10-26: nine merges of main, each red on the same test). `Repeated` finds those ids
in the `FAILED <id>` lines of `gh run view <id> --log-failed`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from jmerge import ready

NAME = "base-merges.json"
SHA = 12
REFUSED = re.compile(r"\(HTTP (409|422)\)")
FAILED = re.compile(r"\sFAILED (\S+::\S+)")
RUNS = 20


class BaseMerge:
    """The branch updates `jmerge` asked GitHub for, one record for a pull request, kept in
    `base-merges.json` in the project's state: the head, the base tip, and what GitHub said. A
    record of the same head and tip is said again and not asked again. A failure to ask, such as
    a `gh` that did not run, a 5xx, a 403 or 429 rate limit, keeps no record, so the next run asks
    again: only GitHub's answer about the branch, a merge or a 409 or 422 refusal, is kept."""

    def __init__(self, main: Path, state: Path, about: list[str], run: bool) -> None:
        self.main = main
        self.path = state / NAME
        self.about = about
        self.run = run

    def known(self) -> dict:
        try:
            known = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return known if isinstance(known, dict) else {}

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
        if was is not None and not was.get("repeated"):
            return str(was.get("said") or "")
        values = {"base": one.base, "tip": tip[:SHA]}
        if not self.run:
            return due.format(**values)
        why, answered = self.ask(one)
        said = ready.BASE_MERGE_REFUSED.format(**values, why=why) if why else asked.format(**values)
        if answered:
            self.keep(one, tip, said=said)
        return said

    def repeats(self, one: ready.PullRequest, tip: str, check: str) -> bool:
        """Whether the pull request failed a same test of its own in its last two check runs
        (`Repeated`), so that its base is not merged into it. It is kept for a head and a base
        tip, so GitHub's logs are read again only once either moves."""
        was = self.was(one, tip)
        if was is not None:
            return bool(was.get("repeated"))
        ids = Repeated(self.main, self.about).of(one, check)
        if ids and self.run:
            self.keep(one, tip, repeated=sorted(ids))
        return bool(ids)

    def was(self, one: ready.PullRequest, tip: str) -> dict | None:
        was = self.known().get(str(one.number))
        if isinstance(was, dict) and (was.get("head"), was.get("tip")) == (one.head, tip):
            return was
        return None

    def keep(self, one: ready.PullRequest, tip: str, **kept: object) -> None:
        now = datetime.now().astimezone()
        record = {"head": one.head, "tip": tip, **kept, "at": f"{now:%Y-%m-%dT%H:%M:%S%z}"}
        known = {**self.known(), str(one.number): record}
        self.path.write_text(json.dumps(known, indent=2) + "\n")

    def ask(self, one: ready.PullRequest) -> tuple[str, bool]:
        """Ask GitHub to merge the base into the branch. Return nothing, or why it did not, and
        whether GitHub answered: `gh api` ends its error line with `(HTTP <status>)`."""
        path = f"repos/{{owner}}/{{repo}}/pulls/{one.number}/update-branch"
        ran = subprocess.run(
            ["gh", "api", "-X", "PUT", path, "-f", f"expected_head_sha={one.head}"],
            cwd=self.main,
            capture_output=True,
            text=True,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        if not ran.returncode:
            return "", True
        try:
            message = json.loads(ran.stdout).get("message")
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
    as before."""

    def __init__(self, main: Path, about: list[str]) -> None:
        self.main = main
        self.about = about

    def of(self, one: ready.PullRequest, check: str) -> frozenset[str]:
        """The ids, of the runs of the workflow named `check`."""
        last = self.runs(one.branch, check, "pull_request")[-2:]
        if len(last) < 2 or any(run.get("conclusion") != "failure" for run in last):
            return frozenset()
        shared = (self.failing(last[0]) or frozenset()) & (self.failing(last[1]) or frozenset())
        if not shared:
            return frozenset()
        mains = [
            run
            for run in self.runs(one.base, check, "push")
            if run.get("conclusion") in ("success", "failure")
        ]
        for run in last:
            before = [main for main in mains if main["at"] <= run["at"]]
            if not before:
                return frozenset()
            if before[-1].get("conclusion") == "failure":
                failed = self.failing(before[-1])
                if failed is None:
                    return frozenset()
                shared -= failed
        return shared

    def runs(self, branch: str, check: str, event: str) -> list[dict]:
        """The ended runs of the check's workflow on the branch, oldest first, with none
        cancelled."""
        said = self.gh(
            "run", "list", "--branch", branch, "--workflow", check, "--event", event,
            "--limit", str(RUNS), "--json", "databaseId,status,conclusion,createdAt",
        )  # fmt: skip
        try:
            listed = json.loads(said or "")
        except ValueError:
            return []
        if not isinstance(listed, list):
            return []
        ended = []
        for run in listed:
            if not isinstance(run, dict) or run.get("status") != "completed":
                continue
            try:
                at = datetime.fromisoformat(str(run.get("createdAt")))
            except ValueError:
                continue
            if run.get("conclusion") != "cancelled":
                ended.append({**run, "at": at})
        return sorted(ended, key=lambda run: run["at"])

    def failing(self, run: dict) -> frozenset[str] | None:
        """The pytest ids the run failed, or `None` where GitHub gave no log."""
        log = self.gh("run", "view", str(run.get("databaseId")), "--log-failed")
        return None if log is None else frozenset(FAILED.findall(log))

    def gh(self, *args: str) -> str | None:
        ran = subprocess.run(
            ["gh", *args],
            cwd=self.main,
            capture_output=True,
            text=True,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        return None if ran.returncode else ran.stdout
