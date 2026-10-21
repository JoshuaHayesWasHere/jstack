"""The tool installed from the main checkout follows a merge that moves one of its packages.

uv's editable install of a checkout puts one path on the tool's `sys.path` for each package
root its pyproject.toml listed when it was built, and a pull does not build it again. A merge
that moves a package to another root leaves every command of the tool failing on an import,
as #189 did when jsettings went to `features/jsettings/src`. So after the pull, where the
package list (`[tool.hatch.build.targets.wheel].packages`) is not what it was, and uv's tool
of the project's name is an editable install of this checkout, the tool is installed again
and the checkout's own environment synced. `jinstall --check` says `stale` of a tool this
missed. Nothing runs for a list that did not change, or a tool installed from elsewhere.
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

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
    """The package list a pyproject.toml gives hatch's wheel, or None where it gives none."""
    try:
        return project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    except (KeyError, TypeError):
        return None


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    said = (ran.stderr or ran.stdout).strip().splitlines()
    return said[-1].strip() if said else f"exit {ran.returncode}"


def follow(run: Run, main: Path, before: str) -> str:
    """After the main checkout was pulled from `before` to its HEAD: the note of the merged
    line, `lines.reinstalled` or `lines.not_reinstalled`, or nothing where nothing was due."""
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
            return lines.not_reinstalled(tool, f"{shlex.join(command)}: {_said(ran)}")
    return lines.reinstalled(tool, main)
