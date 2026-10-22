"""What the server asks GitHub. It asks two things, read-only, through `gh api`, and keeps
each answer a while.

`runs` asks for the repo's last `RUNS` workflow runs, for the Checks card, and keeps them
`RUNS_KEPT` seconds. `pull` asks for one pull request and the check runs of its head when its
task's drawer opens, and keeps them `PULL_KEPT` seconds. Every call is `gh api <path>` with a
path under `repos/<owner>/<name>/` and nothing more: no method, no field and no body, so a
call cannot write. The token stays inside `gh`. The server takes only named fields from an
answer, never a title, a body, a diff or a log.

The server keeps a missing answer as long as one that came, so it does not ask GitHub on
every request while GitHub is down.

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
from datetime import datetime
from typing import Any

from jbus.view.state import iso, text, when

RUNS, RUNS_KEPT, PULL_KEPT = 40, 60, 30
TIMEOUT = 10
PATIENCE = 2.0
DOWN = "GitHub did not answer"
WAITING = "GitHub has not answered yet"
UNKNOWN = "the repo is not known"
_SHA = re.compile(r"[0-9a-f]{40}")


def _ask(path: str) -> Any:
    """What `gh api <path>` printed, as JSON, or None where it did not answer."""
    try:
        asked = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=TIMEOUT)
        return json.loads(asked.stdout) if asked.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _state(one: dict[str, Any]) -> str:
    """A run's state in one word: what it concluded, or its status while it has not
    concluded."""
    return text(one.get("conclusion") or one.get("status"), 30)


class GitHub:
    """The two questions, and the answer to each for the time this class keeps it."""

    def __init__(self, clock: Callable[[], datetime]) -> None:
        self.clock = clock
        self.patience = PATIENCE
        self._lock = threading.Lock()
        self._kept: dict[tuple[str, str, int], tuple[datetime, dict[str, Any]]] = {}
        self._asking: dict[tuple[str, str, int], threading.Event] = {}

    def _held(
        self,
        key: tuple[str, str, int],
        seconds: int,
        ask: Callable[[], dict[str, Any]],
        none: dict[str, Any],
    ) -> dict[str, Any]:
        """The kept answer, or a new one once the old one is `seconds` old. The method holds
        the lock only to read and write the kept answers, never while `gh` runs."""

        def fetch(done: threading.Event) -> None:
            try:
                answer = ask()
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
            said = _ask(f"repos/{repo}/actions/runs?per_page={RUNS}")
            found = said.get("workflow_runs") if isinstance(said, dict) else None
            if not isinstance(found, list):
                return {"runs": [], "at": iso(self.clock()), "error": DOWN}
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
            return {"runs": runs[-RUNS:], "at": iso(self.clock()), "error": ""}

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
            said = _ask(f"repos/{repo}/pulls/{number}")
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
            ran = _ask(f"repos/{repo}/commits/{sha}/check-runs") if pull["head"] else None
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
