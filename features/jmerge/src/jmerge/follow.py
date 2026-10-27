"""After a merge, `jmerge` reinstalls the tool from the main checkout when the merge moved one
of the tool's packages, and runs the install again when the merge changed what it
assembles.

When uv builds an editable install of a checkout, it puts one path on the tool's `sys.path`
for each package root that the checkout's pyproject.toml lists at that moment. A pull does not
make uv build the install again. A merge that moves a package to another root leaves every
command of the tool failing on an import, as #189 did when jsettings went to
`features/jsettings/src`. So after the pull, this module installs the tool again and syncs the
checkout's own environment, when two things hold. The package list
(`[tool.hatch.build.targets.wheel].packages`) has changed, and the uv tool named after the
project is an editable install of this checkout. `jinstall --check` says `stale` of a tool
that this step missed. Nothing runs for a list that did not change, or for a tool installed
from elsewhere.

Each harness's layout links every skill file to its place in the checkout, and a pull does not
assemble it again. A merge that moves or removes a skill leaves its links dangling, as #202
did with pr-review. A merge that adds a skill or a file to one, or edits a file that the
layout writes, leaves the layout short or stale. So after the pull, this module checks each
layout on this machine that `install.sh` assembled from the checkout. When a layout differs
from what the checkout now assembles, `sh install.sh` runs once in the checkout.
`layout.Layout.probe` gives that answer, the same one that `install.sh --check` gives. This
module compares the layouts, not the merge's paths. An edit to a file that a link already
points at needs no install, so nothing runs for it. When a failed install left a layout stale,
this module installs it again after the next merge. Nothing runs where every layout matches
what the checkout makes, or on a machine installed from elsewhere.
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

from jinstall import layout
from jinstall.harnesses import HARNESSES
from jinstall.kinds import State
from jinstall.machine import Machine
from jmerge import lines

Run = Callable[..., subprocess.CompletedProcess[str]]


def _project(run: Run, main: Path, commit: str) -> dict:
    shown = run(main, "git", "show", f"{commit}:pyproject.toml")
    if shown.returncode:
        return {}
    try:
        return tomllib.loads(shown.stdout)
    except ValueError:
        return {}


def packages(project: dict) -> object:
    """The package list that a pyproject.toml sets for hatch's wheel, or None when it sets none."""
    try:
        return project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    except (KeyError, TypeError):
        return None


def follow(run: Run, main: Path, before: str) -> list[str]:
    """The notes for a pull of the main checkout from `before` to its HEAD. First comes the note
    of the tool, `lines.reinstalled` or `lines.not_reinstalled`, then the note of the install,
    `lines.installed` or `lines.not_installed`, and each note appears only when its step was
    due."""
    return [note for note in (_tool(run, main, before), _install(run, main)) if note]


def _tool(run: Run, main: Path, before: str) -> str:
    now = _project(run, main, "HEAD")
    if packages(now) == packages(_project(run, main, before)):
        return ""
    tool = str(now.get("project", {}).get("name", ""))
    source = Machine.here(main).tool_source(tool) if tool else None
    if source is None or source.resolve() != main.resolve():
        return ""
    for command in (
        ("uv", "tool", "install", "--editable", str(main), "--reinstall"),
        ("uv", "sync"),
    ):
        ran = run(main, *command)
        if ran.returncode:
            return lines.not_reinstalled(tool, f"{shlex.join(command)}: {lines.said(ran)}")
    return lines.reinstalled(tool, main)


def _install(run: Run, main: Path) -> str:
    machine = Machine.here(main)
    ours = [
        layout.Layout(harness)
        for harness in HARNESSES
        if (machine.layout(harness.name) / "source").resolve() == main.resolve()
    ]
    if all(one.probe(machine).state is State.OK for one in ours):
        return ""
    ran = run(main, "sh", "install.sh")
    if ran.returncode:
        return lines.not_installed(f"sh install.sh: {_failed(ran)}")
    return lines.installed(main)


def _failed(ran: subprocess.CompletedProcess[str]) -> str:
    """What a failed install said: its note on stderr, or else its first line that is not ok,
    or else its exit code."""
    noted = ran.stderr.strip().splitlines()
    if noted:
        return noted[-1].strip()
    wrong = [line for line in ran.stdout.splitlines() if line and not line.startswith("ok ")]
    return wrong[0] if wrong else f"exit {ran.returncode}"
