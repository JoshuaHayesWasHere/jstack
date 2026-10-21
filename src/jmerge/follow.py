"""The tool installed from the main checkout follows a merge that moves one of its packages,
and the install made from it follows a merge that changes what it assembles.

uv's editable install of a checkout puts one path on the tool's `sys.path` for each package
root its pyproject.toml listed when it was built, and a pull does not build it again. A merge
that moves a package to another root leaves every command of the tool failing on an import,
as #189 did when jsettings went to `features/jsettings/src`. So after the pull, where the
package list (`[tool.hatch.build.targets.wheel].packages`) is not what it was, and uv's tool
of the project's name is an editable install of this checkout, the tool is installed again
and the checkout's own environment synced. `jinstall --check` says `stale` of a tool this
missed. Nothing runs for a list that did not change, or a tool installed from elsewhere.

Each harness's layout links every skill file to its place in the checkout, and a pull does not
assemble it again. A merge that moves or removes a skill leaves its links dangling, as #202 did
with pr-review, and one that adds a skill or a file to one, or edits a file the layout writes,
leaves the layout short or stale. So after the pull, where the merge changed what the assembly
reads (`skills.json`, `plugin.json`, a file the catalog lists, a file in a skill's folder) and a
layout on this machine was assembled from this checkout, `sh install.sh` runs in it once.
`install.sh --check` says `stale` of a layout this missed. Nothing runs for a merge that
changed none of it, or a machine installed from elsewhere.
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath

from jinstall import layout
from jinstall.harnesses import HARNESSES
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


def follow(run: Run, main: Path, before: str) -> list[str]:
    """After the main checkout was pulled from `before` to its HEAD: the note of the tool,
    `lines.reinstalled` or `lines.not_reinstalled`, then the note of the install,
    `lines.installed` or `lines.not_installed`, each only where it was due."""
    return [note for note in (_tool(run, main, before), _install(run, main, before)) if note]


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
            return lines.not_reinstalled(tool, f"{shlex.join(command)}: {_said(ran)}")
    return lines.reinstalled(tool, main)


def assembles(main: Path, changed: Iterable[str]) -> bool:
    """Whether a change to the paths `changed` changes what the install assembles from the
    checkout `main`: its catalog, its `plugin.json`, a file the catalog lists, or a file in the
    folder of a skill, but for the parts of a feature that are not the skill."""
    changed = set(changed)
    if changed & {layout.CATALOG, layout.PLUGIN}:
        return True
    try:
        items, hooks = layout.catalog(main), layout.hooks(main)
    except layout.UNREADABLE:
        return False
    listed = {item["path"] for item in items} | {hook["path"] for hook in hooks}
    folders = [
        PurePosixPath(item["path"]).parent
        for item in items
        if item["kind"] in ("skill", "principle") and item["path"].endswith("/SKILL.md")
    ]
    for path in map(PurePosixPath, changed - listed):
        for folder in folders:
            if not path.is_relative_to(folder):
                continue
            parts = path.relative_to(folder).parts
            if parts[0] not in layout.NOT_THE_SKILL and not any(
                part.startswith(".") or part == "__pycache__" for part in parts
            ):
                return True
    return bool(changed & listed)


def _install(run: Run, main: Path, before: str) -> str:
    machine = Machine.here(main)
    if not any(
        (machine.layout(harness.name) / "source").resolve() == main.resolve()
        for harness in HARNESSES
    ):
        return ""
    diff = run(main, "git", "diff", "--name-only", "--no-renames", "-z", before, "HEAD")
    if diff.returncode:
        return lines.not_installed(f"git diff {before} HEAD: {_said(diff)}")
    if not assembles(main, filter(None, diff.stdout.split("\0"))):
        return ""
    ran = run(main, "sh", "install.sh")
    if ran.returncode:
        return lines.not_installed(f"sh install.sh: {_failed(ran)}")
    return lines.installed(main)


def _failed(ran: subprocess.CompletedProcess[str]) -> str:
    """What an install that failed said: its note on stderr, else its first line that is not
    ok, else its exit code."""
    noted = ran.stderr.strip().splitlines()
    if noted:
        return noted[-1].strip()
    wrong = [line for line in ran.stdout.splitlines() if line and not line.startswith("ok ")]
    return wrong[0] if wrong else f"exit {ran.returncode}"
