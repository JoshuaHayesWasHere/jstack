"""Main's live ruleset against the two files that say what it should be, once a day.

GitHub holds main to ruleset `ID`. Two files say what it holds: `KEPT`, the ruleset's body in the
project's checkout, which the repo guards test, and the home's `required-checks`, the checks jmerge
waits for. No test reads the live ruleset, so a hand edit of it on GitHub passes them all. `check`
reads it with one `gh api` call (`ASK`) and tells the project's home, through a line raised once
(`jbus.alert.deliver`), when its `rules` differ from `KEPT`'s, or its required status checks from
`required-checks`. `jbus ci --day` runs it, once a day, after the day's report: no pull request's
check reads GitHub for it.

A project whose checkout has no `KEPT` is not checked, and costs no call. A ruleset `gh` does not
give is said on the day's output and tells no one: that is GitHub's answer, not drift.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import jbus
from jbus import alert, passes
from jmerge import ready

ID = 25665226
KEPT = Path("features/repo-guards/main-ruleset.json")
REQUIRED = "required-checks"
ASK = ["gh", "api", "repos/{repo}/rulesets/{id}"]
CHECKS = "required_status_checks"


def contexts(rules: list[dict[str, Any]]) -> tuple[str, ...]:
    """The contexts the rules' required status checks name, in their order."""
    return tuple(
        str(one.get("context"))
        for rule in rules
        if rule.get("type") == CHECKS
        for one in (rule.get("parameters") or {}).get(CHECKS) or ()
    )


def drift(live: list[dict], kept: list[dict], required: tuple[str, ...]) -> list[str]:
    """What differs between the live rules and the kept rules and `required-checks`, one line
    each, or nothing where they agree."""
    found = []
    if live != kept:
        types = sorted(
            {str(rule.get("type")) for rule in live if rule not in kept}
            | {str(rule.get("type")) for rule in kept if rule not in live}
        )
        found.append(f"its rules differ from {KEPT} in {', '.join(types)}")
    have = contexts(live)
    lacks = [name for name in required if name not in have]
    extra = [name for name in have if name not in required]
    if lacks:
        found.append(f"it lacks {', '.join(lacks)} of {REQUIRED}")
    if extra:
        found.append(f"it requires {', '.join(extra)}, which {REQUIRED} does not name")
    return found


def check(
    config: jbus.Config,
    project: jbus.Project,
    now: datetime,
    repo: str | None,
    ask: Callable[[list[str]], Any],
) -> None:
    """Read the live ruleset of the project's repo, compare it, and tell the home of any drift."""
    try:
        kept = json.loads((project.checkout / KEPT).read_text())["rules"]
    except FileNotFoundError:
        return
    if repo is None:
        print(f"ci: ruleset {ID} not read: the checkout has no GitHub origin")
        return
    try:
        text = (config.home(project) / REQUIRED).read_text(errors="replace")
    except OSError:
        text = ""
    done = ask([part.format(repo=repo, id=ID) for part in ASK])
    if done.returncode:
        why = " ".join(str(done.stderr).split())[:200] or f"gh exit {done.returncode}"
        print(f"ci: ruleset {ID} not read: {why}")
        return
    try:
        live = json.loads(done.stdout)["rules"]
    except (ValueError, KeyError, TypeError):
        print(f"ci: ruleset {ID} not read: gh gave no rules")
        return
    found = drift(live, kept, ready.required_of(text))
    if not found:
        print(f"ci: ruleset {ID} on {repo} matches {KEPT} and {REQUIRED}, no drift")
        return
    line = f"main's live ruleset {ID} on {repo} drifted: {'; '.join(found)}"
    alert.deliver(passes.Pass(config, project, now, print), line)
