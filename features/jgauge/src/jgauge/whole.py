"""Whether a slot command runs a repo's whole suite where the repo's check selects its tests.

A repo whose pull request check selects its tests has `scripts/select_tests.py`: CI's check runs
the tests the change selects on every pull request, and the whole suite runs nightly and before a
release. A thread's desk then runs the touched check, a step to a short slot
(features/crew/do-the-task.md), and a whole suite there only repeats CI, on the cores every other
thread's tests share: on 2026-11-09 crews' whole-suite runs held the full lane for 3.27 h of a
6 h push, and load was over the 24 cores in 46.8% of its samples.

A whole suite is `make check`, `make check-fast` with no `PART=`, `make test` with no `TESTS=`,
and `pytest` with no path, as the command's own words give them. A command inside `sh -c` is not
read: its words are only known when it runs.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

SELECTS = Path("scripts") / "select_tests.py"
TOUCHED = "make check-fast BASE=<base> PART=touched"


def selecting_repo(here: Path) -> Path | None:
    """The top of the repo `here` is in, where that repo's check selects its tests: the nearest
    directory up from `here` with `scripts/select_tests.py`, stopping at the repo's top."""
    for at in (here, *here.parents):
        if (at / SELECTS).is_file():
            return at
        if (at / ".git").exists():
            break
    return None


def _make(args: Sequence[str], env: Mapping[str, str]) -> bool:
    given = dict(arg.split("=", 1) for arg in args if "=" in arg and not arg.startswith("-"))
    targets = {arg for arg in args if "=" not in arg and not arg.startswith("-")}

    def set_(name: str) -> bool:
        return bool(given.get(name, env.get(name, "")).strip())

    return (
        "check" in targets
        or ("check-fast" in targets and not set_("PART"))
        or ("test" in targets and not set_("TESTS"))
    )


_VALUED = frozenset(
    "-k -m -n -p -c -o -W -r --dist --maxfail --durations --tb --junitxml --deselect --ignore"
    " --ignore-glob --rootdir --basetemp --confcutdir --log-level --timeout".split()
)


def _pytest(args: Sequence[str], here: Path) -> bool:
    """Whether no word of `args` names a path in `here`. The word after an option that takes a
    value, as `-k tests`, is that value and not a path."""
    paths, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg in _VALUED:
            skip = True
        elif not arg.startswith("-"):
            paths.append(arg)
    return not any((here / arg.split("::", 1)[0]).exists() for arg in paths)


def whole_suite(command: Sequence[str], here: Path, env: Mapping[str, str]) -> bool:
    """Whether `command`, run in `here`, runs the whole suite."""
    for n, word in enumerate(command):
        name = os.path.basename(word)
        if name in ("make", "gmake"):
            return _make(command[n + 1 :], env)
        if name in ("pytest", "py.test"):
            return _pytest(command[n + 1 :], here)
        if word == "-m" and command[n + 1 : n + 2] == ["pytest"]:
            return _pytest(command[n + 2 :], here)
    return False


def refusal(command: Sequence[str], here: Path, env: Mapping[str, str]) -> str:
    """Why a thread may not run `command` in `here`, or nothing where it may."""
    top = selecting_repo(here)
    if top is None or not whole_suite(command, here, env):
        return ""
    return (
        f"test-slot: `{' '.join(command)}` runs the whole suite, and {top.name}'s check selects"
        f" its tests ({SELECTS}): CI's check runs the selection on the pull request, so nothing"
        f" ran. Run the touched check, `{TOUCHED}`, a step to a short slot, with the check block"
        " of the crew's Do the task, or one test file at a time:"
        " `jgauge test-slot --short --thread <id> -- make test TESTS=<file>`."
    )
