"""The repo's checks: its last workflow runs on GitHub, the count of main's commits that
`checks.json` records as green, and the runner units of this machine. The server asks GitHub
for the runs.

The runners are the units that `systemctl --user list-units 'actions-runner-*'` lists. The server
asks for them on each request, read-only, and each has the state systemd gives it. The card says
when a runner is not active, and that is not a blind spot: the view knows the runner is stopped.
On macOS a runner is the launchd agent its `svc.sh install` loads, `actions.runner.<repo>.<name>`,
which `launchctl list` lists: active while it has a process, inactive while it has none.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from jbus import launchd
from jbus.view.state import Read, Source, iso, kept, text

FIRST = True
GITHUB_FRESH = 180
RUNNERS = "actions-runner-*"
AGENTS = "actions.runner."
_RUN = {key: None for key in ("branch", "name", "state", "created", "started", "updated", "url")}
_UNIT = {"unit": None, "active": None, "sub": None}
SHAPE = {
    "checks": {
        "runs": [_RUN],
        "at": None,
        "error": None,
        "commits": None,
        "green": None,
        "runners": [_UNIT],
        "runners_read": None,
        "manager": None,
        "ended": None,
        "now": {"running": [None], "waiting": [None], "failed": [None]},
    }
}
QUEUED = ("queued", "requested")
FAILED = ("failure", "timed_out", "startup_failure")


def runs(read: Read) -> dict[str, Any]:
    """The repo's last workflow runs, as `github.GitHub.runs` gives them."""
    if not read.where:
        return {"runs": [], "at": None, "error": "the repo is not known"}
    return read.runs(read.where)


def _github(read: Read) -> dict[str, Any]:
    """The server renews GitHub's answer each minute, so the answer is stale only when the server
    kept an old answer while a slow `gh` had not returned."""
    asked = read.once(runs)
    return {"at": asked.get("at"), "read": not asked.get("error"), "fresh": GITHUB_FRESH}


def runners(read: Read) -> list[dict[str, str]] | None:
    """Each runner unit that systemd lists, loaded or not and active or not, or None where
    systemd did not answer. On macOS, each runner agent that launchd lists."""
    if launchd.manager() == "launchd":
        return agents(read)
    try:
        asked = subprocess.run(
            ["systemctl", "--user", "list-units", RUNNERS, "--all", "--output=json", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        listed = json.loads(asked.stdout) if not asked.returncode else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(listed, list):
        return None
    return [
        {
            "unit": text(one.get("unit"), 80),
            "active": text(one.get("active"), 40),
            "sub": text(one.get("sub"), 40),
        }
        for one in listed
        if isinstance(one, dict)
    ]


def agents(read: Read) -> list[dict[str, str]] | None:
    """Each runner agent that `launchctl list` lists, or None where launchd did not answer. Its
    rows are `<pid or -> <last exit> <label>`."""
    try:
        asked = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if asked.returncode:
        return None
    found = []
    for line in asked.stdout.splitlines()[1:]:
        pid, _, label = (line.split("\t") + ["", ""])[:3]
        if label.startswith(AGENTS):
            running = pid.strip().isdigit()
            found.append(
                {
                    "unit": text(label, 80),
                    "active": "active" if running else "inactive",
                    "sub": "running" if running else "dead",
                }
            )
    return found


def tally(runs: list[dict[str, Any]]) -> dict[str, list[int]]:
    """Which runs run now, which wait for a runner, and which failed, each by its place in
    `runs`. A branch is in the failed list once, as long as the newest run of any of its
    workflows failed. Its place there is the place of the oldest of those failed runs. The runs
    are oldest first, as `github.GitHub.runs` gives them. This is the one rule: the card and its
    drawer draw these lists, and the overview counts them."""
    newest = {(one.get("branch"), one.get("name")): at for at, one in enumerate(runs)}
    failed: dict[Any, int] = {}
    for at in sorted(newest.values()):
        if runs[at].get("state") in FAILED:
            failed.setdefault(runs[at].get("branch"), at)
    return {
        "running": [at for at, one in enumerate(runs) if one.get("state") == "in_progress"],
        "waiting": [at for at, one in enumerate(runs) if one.get("state") in QUEUED],
        "failed": sorted(failed.values()),
    }


def _units(read: Read) -> dict[str, Any]:
    return {"at": iso(read.now), "read": read.machine(runners) is not None}


SOURCES = (
    kept("checks.json", lambda read: read.table("checks.json"), 90),
    Source("GitHub", "server", _github, 150),
    Source("runner units", "server", _units, 160, machine=True),
)


def build(read: Read) -> dict[str, Any]:
    asked, kept = read.once(runs), read.table("checks.json") or {}
    return {
        "checks": {
            "runs": asked.get("runs", []),
            "at": asked.get("at"),
            "error": text(asked.get("error")),
            "commits": len(kept),
            "green": sum(1 for word in kept.values() if word == "green"),
            "runners": read.machine(runners) or [],
            "runners_read": read.machine(runners) is not None,
            "manager": launchd.manager(),
            "ended": sum(1 for one in asked.get("runs", []) if one.get("state") in FAILED),
            "now": tally(asked.get("runs", [])),
        }
    }
