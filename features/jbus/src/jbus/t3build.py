"""The T3 Code build jbus asks the user to install: an `install` item of what waits on the user
(`jbus.waiting`) while T3 Code runs a jstack build of other patches than the tree jbus runs from.

A merged change to jstack's T3 Code patches reaches the sidebar only once the user runs
`jinstall --setup`, which needs sudo, and opens T3 Code again, so the item is the user's alone.
The series on each side are the doctor's (`jinstall.kinds.T3JstackBuild`), read with its own
helpers: the running build's from what `t3 --version` answers, and the tree's from its patches
(`patch_series`).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbus import green
from jsettings import proc

if TYPE_CHECKING:
    from jbus.passes import Pass

PACKAGING = Path("features/t3code-jstack/packaging")
"""Where a checkout of jstack keeps the patches and the PKGBUILD of its T3 Code build."""


def behind(run: Pass) -> list[dict[str, Any]]:
    """Return the one `install` item where T3 Code runs a jstack build of other patches than the
    tree jbus runs from: the green copy of the project's checkout, else the checkout. A project
    whose tree has no such patches, and a machine whose `t3` answers no jstack build, list
    nothing."""
    from jinstall.kinds import T3_JSTACK, patch_series, t3_command
    from jinstall.machine import Machine

    copy = green.path()
    made_from = green.of(copy)
    ours = made_from is not None and made_from.resolve() == run.project.checkout.resolve()
    tree = copy if ours else run.project.checkout
    if not any((tree / PACKAGING).glob("*.patch")):
        return []
    machine = Machine.here(run.project.checkout)
    command = t3_command(machine)
    ran = machine.run([str(command), "--version"]) if command is not None else None
    built = None if ran is None or ran.code != 0 else T3_JSTACK.search(ran.out)
    want = patch_series(tree / PACKAGING)
    if built is None or built[2] == want:
        return []
    have = built[2]
    lacks = _lacks(run.project.checkout, green.at(tree), have)
    line = (
        f"install t3code-jstack: T3 Code runs the jstack build of series {have}, and the patches "
        f"jbus runs from are series {want}: {lacks}; run jinstall --setup, then quit T3 Code "
        "and open it again"
    )
    return [{"kind": "install", "key": "install:t3code-jstack", "line": line}]


def _lacks(checkout: Path, tip: str, have: str) -> str:
    """Say how many changes to the patches merged after the commit that gave the PKGBUILD the
    series `have`, up to `tip`, from the checkout's history."""

    def git(*args: str) -> str:
        said = proc.run("git", "-C", str(checkout), *args, timeout=60)
        return said.stdout.strip() if said.returncode == 0 else ""

    if tip:
        pkgbuild = str(PACKAGING / "PKGBUILD")
        named = git("log", "--reverse", "--format=%H", f"-S{have}", tip, "--", pkgbuild)
        first = named.split("\n", 1)[0]
        count = git("rev-list", "--count", f"{first}..{tip}", "--", str(PACKAGING)) if first else ""
        if count.isdigit():
            return f"the build lacks {count} merged change{'s' * (count != '1')} to them"
    return "main's history does not hold the build's series, so it lacks some of them"
