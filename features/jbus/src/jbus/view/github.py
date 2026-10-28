"""What the server asks GitHub. It asks four things, read-only, through `gh`, and keeps
each answer a while.

`runs` asks for the repo's last `RUNS` workflow runs, for the Checks card, and keeps them
`RUNS_KEPT` seconds. `pull` asks for one pull request and the check runs of its head when its
task's drawer opens, and keeps them `PULL_KEPT` seconds. Each of those calls is `gh api <path>`
with a path under `repos/<owner>/<name>/` and nothing more: no method, no field and no body, so
a call cannot write. `merged` asks `gh pr list` for the pull requests merged since a day, with
their numbers and merge times, when the Throughput drawer opens, and keeps them `MERGED_KEPT`
seconds: `pr list` only lists. `landed` asks, for each integration branch of a project, for the
pull requests whose head is that branch, when the Milestones drawer opens, and keeps the answer
`LANDED_KEPT` seconds: a branch has landed once one of them merged into the repo's default branch
and none is still open. The token stays inside `gh`. Of an answer the server takes only
named fields, never a title, a body, a diff or a log.

When GitHub does not answer, the server keeps that failure for as long as it would keep an
answer that did come. So it does not ask GitHub on every request while GitHub is down. A call
GitHub refused for its rate limit is kept as the line that names the window and when it starts
again (`jmerge.budget`), in place of `DOWN`.

No request waits on GitHub for more than `PATIENCE` seconds. The server runs `gh` in a
thread of its own, one at a time for each question. A request still waiting after that time
takes the answer there was before, or `WAITING` where there was none, and the next request
gets the new answer.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from jbus.view.state import iso, text, when
from jmerge import budget as allowance

RUNS, RUNS_KEPT, PULL_KEPT, MERGED_KEPT, LANDED_KEPT = 40, 60, 30, 300, 300
MERGED_MOST, FROM_MOST = 1000, 100
TIMEOUT = 10
PATIENCE = 2.0
DOWN = "GitHub did not answer"
WAITING = "GitHub has not answered yet"
UNKNOWN = "the repo is not known"
_SHA = re.compile(r"[0-9a-f]{40}")


class Limited(Exception):
    """GitHub refused a call for its rate limit. The message is the line that says so."""


def _run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT)


def _ask(*said: str) -> Any:
    """What `gh <said>` printed, as JSON, or None where it did not answer. Raise `Limited` where
    GitHub refused it for its rate limit."""
    try:
        asked = _run("gh", *said)
        if asked.returncode and allowance.refused(asked.stderr):
            raise Limited(allowance.named(_run(*allowance.ASK)))
        return json.loads(asked.stdout) if asked.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _state(one: dict[str, Any]) -> str:
    """A run's state in one word: what it concluded, or its status while it has not
    concluded."""
    return text(one.get("conclusion") or one.get("status"), 30)


def shaped(said: Any, now: datetime) -> dict[str, Any]:
    """`{"runs", "at", "error"}` of GitHub's answer to the list of a repo's workflow runs, or of
    None where GitHub did not answer: the last `RUNS` runs, oldest first."""
    found = said.get("workflow_runs") if isinstance(said, dict) else None
    if not isinstance(found, list):
        return {"runs": [], "at": iso(now), "error": DOWN}
    runs = [
        {
            "branch": text(one.get("head_branch"), 120),
            "name": text(one.get("name"), 60),
            "state": _state(one),
            "created": when(one.get("created_at")),
            "started": when(one.get("run_started_at")),
            "updated": when(one.get("updated_at")),
            "url": text(one.get("html_url")),
        }
        for one in found
        if isinstance(one, dict) and when(one.get("created_at"))
    ]
    runs.sort(key=lambda run: run["created"])
    return {"runs": runs[-RUNS:], "at": iso(now), "error": ""}


class GitHub:
    """The four questions, and the answer to each for the time this class keeps it."""

    def __init__(self, clock: Callable[[], datetime]) -> None:
        self.clock = clock
        self.patience = PATIENCE
        self._lock = threading.Lock()
        self._kept: dict[tuple[Any, ...], tuple[datetime, dict[str, Any]]] = {}
        self._asking: dict[tuple[Any, ...], threading.Event] = {}

    def _held(
        self,
        key: tuple[Any, ...],
        seconds: int,
        ask: Callable[[], dict[str, Any]],
        none: dict[str, Any],
    ) -> dict[str, Any]:
        """The kept answer, or a new one once the old one is `seconds` old. The method holds
        the lock only to read and write the kept answers, never while `gh` runs."""

        def fetch(done: threading.Event) -> None:
            try:
                answer = ask()
            except Limited as limited:
                answer = none | {"error": str(limited)}
            except Exception:
                answer = none | {"error": DOWN}
            with self._lock:
                self._kept[key] = (self.clock(), answer)
                self._asking.pop(key, None)
            done.set()

        with self._lock:
            kept = self._kept.get(key)
            if kept is not None and abs((self.clock() - kept[0]).total_seconds()) <= seconds:
                return kept[1]
            done = self._asking.get(key)
            if done is None:
                done = self._asking[key] = threading.Event()
                threading.Thread(target=fetch, args=(done,), daemon=True).start()
        done.wait(self.patience)
        with self._lock:
            now = self._kept.get(key)
        if done.is_set() and now is not None:
            return now[1]
        return kept[1] if kept is not None else none | {"error": WAITING}

    def runs(self, repo: str) -> dict[str, Any]:
        """`{"runs", "at", "error"}`: the last workflow runs, oldest first."""

        def ask() -> dict[str, Any]:
            return shaped(_ask("api", f"repos/{repo}/actions/runs?per_page={RUNS}"), self.clock())

        return self._held(("runs", repo, 0), RUNS_KEPT, ask, {"runs": [], "at": None})

    def pull(self, repo: str, slug: str, number: int | None) -> dict[str, Any]:
        """`{"slug", "pull", "checks"}` of a task: the pull request's state and the check runs
        of its head. It has `at` and `error` too where the server asked GitHub."""
        if number is None:
            return {"slug": slug, "pull": None, "checks": []}
        if not repo:
            return {"slug": slug, "pull": None, "checks": [], "error": UNKNOWN}

        def ask() -> dict[str, Any]:
            at = iso(self.clock())
            said = _ask("api", f"repos/{repo}/pulls/{number}")
            if not isinstance(said, dict):
                return {"slug": slug, "pull": None, "checks": [], "at": at, "error": DOWN}
            head = said.get("head") if isinstance(said.get("head"), dict) else {}
            sha = text(head.get("sha"), 40)
            pull = {
                "number": number,
                "state": text(said.get("state"), 20),
                "merged": said.get("merged") is True,
                "mergeable": said.get("mergeable")
                if isinstance(said.get("mergeable"), bool)
                else None,
                "mergeable_state": text(said.get("mergeable_state"), 60),
                "head": sha if _SHA.fullmatch(sha) else "",
                "updated": when(said.get("updated_at")),
                "url": text(said.get("html_url")),
            }
            ran = _ask("api", f"repos/{repo}/commits/{sha}/check-runs") if pull["head"] else None
            found = ran.get("check_runs") if isinstance(ran, dict) else None
            checks = [
                {
                    "name": text(one.get("name"), 60),
                    "state": _state(one),
                    "started": when(one.get("started_at")),
                    "completed": when(one.get("completed_at")),
                    "url": text(one.get("html_url")),
                }
                for one in (found if isinstance(found, list) else [])
                if isinstance(one, dict)
            ]
            error = "" if isinstance(found, list) else DOWN
            return {"slug": slug, "pull": pull, "checks": checks, "at": at, "error": error}

        none = {"slug": slug, "pull": None, "checks": []}
        return self._held(("pull", repo, number), PULL_KEPT, ask, none)

    def merged(self, repo: str, since: date) -> dict[str, Any]:
        """`{"merged", "at", "error"}`: each pull request merged on `since` or after, as its
        number and its merge time, oldest first. GitHub's search reads `since` as a day in
        UTC, so a caller asks from a day early and counts the times itself."""

        def ask() -> dict[str, Any]:
            said = _ask(
                *("pr", "list", "--repo", repo, "--state", "merged"),
                *("--search", f"merged:>={since.isoformat()}"),
                *("--json", "number,mergedAt", "--limit", str(MERGED_MOST)),
            )
            if not isinstance(said, list):
                return {"merged": [], "at": iso(self.clock()), "error": DOWN}
            merged = [
                {"number": one["number"], "at": when(one.get("mergedAt"))}
                for one in said
                if isinstance(one, dict) and isinstance(one.get("number"), int)
            ]
            merged = sorted((one for one in merged if one["at"]), key=lambda one: one["at"])
            return {"merged": merged, "at": iso(self.clock()), "error": ""}

        key = ("merged", repo, since.toordinal())
        return self._held(key, MERGED_KEPT, ask, {"merged": [], "at": None})

    def landed(self, repo: str, branches: tuple[str, ...]) -> dict[str, Any]:
        """`{"landed", "at", "error"}`: the branches of `branches` that have landed on the
        repo's default branch. One thread asks for every branch, so the panel waits on GitHub
        once, not once for each branch. A branch GitHub did not answer for is not landed, and
        `error` says so."""

        def ask() -> dict[str, Any]:
            owner = repo.partition("/")[0]
            landed, missed = [], []
            for branch in branches:
                head = quote(f"{owner}:{branch}", safe="")
                path = f"repos/{repo}/pulls?state=all&head={head}&per_page={FROM_MOST}"
                said = _ask("api", path)
                if not isinstance(said, list):
                    missed.append(branch)
                    continue
                pulls = [one for one in said if isinstance(one, dict)]
                if _merged_home(pulls) and not any(one.get("state") == "open" for one in pulls):
                    landed.append(branch)
            return {"landed": landed, "at": iso(self.clock()), "error": DOWN if missed else ""}

        key = ("landed", repo, branches)
        return self._held(key, LANDED_KEPT, ask, {"landed": [], "at": None})


def _merged_home(pulls: list[dict[str, Any]]) -> bool:
    """Whether one of `pulls`, as GitHub lists pull requests, merged into its repo's default
    branch."""
    for one in pulls:
        base = one.get("base") if isinstance(one.get("base"), dict) else {}
        home = base.get("repo") if isinstance(base.get("repo"), dict) else {}
        if one.get("merged_at") and base.get("ref") and base["ref"] == home.get("default_branch"):
            return True
    return False
