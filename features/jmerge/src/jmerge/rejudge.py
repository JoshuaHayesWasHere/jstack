"""A pull request whose required check failed, judged again over today's base.

A pull request's check runs on its merge with the base as the base was then, and a rerun runs on
that same merge. So a check that failed while the base was red stays red after the base is
fixed, and no push of the crew's is owed for it. `jmerge` judges such a pull request again once
its base has moved since the check started and is not red. Where the repo has a `fresh-check`
file, the command runs on the head merged over today's base first (`cli.Fresh`), once for a head
and a base tip. On a pass, or with no such file, `BaseMerge` asks GitHub to merge the base into
the branch, and GitHub's new check at the new head decides the rest by the normal path. On a fail
the line is `ready.FRESH_FAILS`, on which jbus tells the crew once.

GitHub's endpoint merges the base into the branch and rewrites no history:
https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request-branch. `expected_head_sha`
makes it refuse a branch that moved since `jmerge` judged it. A review stands across that merge
when the patch is unchanged, as across a rebase: its range-diff shows no content
(`rangediff.verdict`), which leaves out the merge commit.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from jmerge import ready

NAME = "base-merges.json"
SHA = 12


class BaseMerge:
    """The branch updates `jmerge` asked GitHub for, one record for a pull request, kept in
    `base-merges.json` in the project's state: the head, the base tip, and what GitHub said. A
    record of the same head and tip is said again and not asked again."""

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

    def of(self, one: ready.PullRequest, tip: str) -> str:
        """Why the pull request waits once its base's merge into it is asked of GitHub."""
        was = self.known().get(str(one.number))
        if isinstance(was, dict) and (was.get("head"), was.get("tip")) == (one.head, tip):
            return str(was.get("said") or "")
        values = {"base": one.base, "tip": tip[:SHA]}
        if not self.run:
            return ready.BASE_MERGE_DUE.format(**values)
        why = self.ask(one)
        said = (
            ready.BASE_MERGE_REFUSED.format(**values, why=why)
            if why
            else ready.BASE_MERGE_ASKED.format(**values)
        )
        now = datetime.now().astimezone()
        record = {"head": one.head, "tip": tip, "said": said, "at": f"{now:%Y-%m-%dT%H:%M:%S%z}"}
        known = {**self.known(), str(one.number): record}
        self.path.write_text(json.dumps(known, indent=2) + "\n")
        return said

    def ask(self, one: ready.PullRequest) -> str:
        """Ask GitHub to merge the base into the branch, and return nothing, or why it did not."""
        path = f"repos/{{owner}}/{{repo}}/pulls/{one.number}/update-branch"
        ran = subprocess.run(
            ["gh", "api", "-X", "PUT", path, "-f", f"expected_head_sha={one.head}"],
            cwd=self.main,
            capture_output=True,
            text=True,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        if not ran.returncode:
            return ""
        try:
            message = json.loads(ran.stdout).get("message")
        except (ValueError, AttributeError):
            message = None
        lines = (ran.stderr or ran.stdout).strip().splitlines()
        return str(message or (lines[-1] if lines else f"gh exited {ran.returncode}"))
