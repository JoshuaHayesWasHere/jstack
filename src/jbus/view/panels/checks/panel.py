"""The repo's checks: its last workflow runs on GitHub, asked by the server, how many
commits of main `checks.json` has as green, and the runner units of this machine.

The runners are what `systemctl --user list-units 'actions-runner-*'` lists, asked by the
server on each request and read-only, each with the state systemd gives it. A runner that is
not active is a fact the card says, not a blind spot: the view knows it is stopped.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from jbus.view.state import Read, Source, iso, kept, text

FIRST = True
GITHUB_FRESH = 180
RUNNERS = "actions-runner-*"
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
    }
}


def runs(read: Read) -> dict[str, Any]:
    """The repo's last workflow runs, as `github.GitHub.runs` gives them."""
    if not read.where:
        return {"runs": [], "at": None, "error": "the repo is not known"}
    return read.runs(read.where)


def _github(read: Read) -> dict[str, Any]:
    """GitHub's answer is renewed each minute, so it is stale only when the server kept an
    answer while a slow `gh` had not come back."""
    asked = read.once(runs)
    return {"at": asked.get("at"), "read": not asked.get("error"), "fresh": GITHUB_FRESH}


def runners(read: Read) -> list[dict[str, str]] | None:
    """Each runner unit systemd lists, loaded or not, active or not, or None where it did
    not answer."""
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


def _units(read: Read) -> dict[str, Any]:
    return {"at": iso(read.now), "read": read.once(runners) is not None}


SOURCES = (
    kept("checks.json", lambda read: read.table("checks.json"), 90),
    Source("GitHub", "server", _github, 150),
    Source("runner units", "server", _units, 160),
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
            "runners": read.once(runners) or [],
            "runners_read": read.once(runners) is not None,
        }
    }
