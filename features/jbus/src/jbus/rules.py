"""A standing rule lives in code, a brief or the queue, and never in a file a thread reads at its
start.

The user, 2026-11-02 (the D2 pick of the scorecard-probes-current scout, on word 819ce35a98):
"standing rules in .md files like this are not" allowed, "briefs are fine, a queue is fine". A
file that holds one goes stale, and nothing runs it. So a rule file is any of:

- a `standing.md` of a project's home, or of one of its scoped homes, with any text in it. One
  in a home directory no project has is the machine's, so it is the infra project's;
- a file with any text in it in an agent's auto-memory directory,
  `<agent home>/projects/<name>/memory/`, for each agent home T3 Code runs
  (`jroles.inventory.agent_homes`). `<name>` is the checkout's path with each character that is
  not a letter or a digit made `-`, as the agent names it. A directory no project's checkout
  names is the machine's, so it is the infra project's (`jbus.Config.owner`).

Two agent homes can hold the same file, as one mounted on the other does: it is listed once.

`found` lists a project's rule files. Each is an item of the one list (`jbus.wakes`), the
catch-all's, `uncategorized`, keyed `rulefile:<path>`, told once while the file stays, which asks
for its rules to move to code, a skill's text or a queued row and for the file to go. `jbus
rules` prints every project's and exits 1 when there is one.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import jbus
from jbus import verbs
from jroles import inventory

KEY = "rulefile"
TEXT = (
    "{path} holds a standing rule, and no file a thread reads at its start may hold one ({user}, "
    "2026-11-02). Give each rule in it a home: code (a check, a lint, a jbus behaviour), the text "
    "of the skill step that needs it, or a queued row, or drop it where code already holds it. "
    "Then delete the file. A rule of another repo is queued to that repo's home."
)
_NOT_NAME = re.compile(r"[^A-Za-z0-9]")


def agent_homes() -> list[Path]:
    """Each agent home T3 Code runs (`jroles.inventory.agent_homes`)."""
    return inventory.agent_homes()


def memory_name(checkout: Path) -> str:
    """The name the agent gives the project directory of a checkout."""
    return _NOT_NAME.sub("-", str(checkout))


def _held(path: Path) -> bool:
    """Whether the file has any text in it. One that cannot be read is counted, so it is seen."""
    try:
        return bool(path.read_text(errors="replace").strip())
    except OSError:
        return True


def _memories(config: jbus.Config, project: jbus.Project) -> list[Path]:
    names = {memory_name(one.checkout): one.name for one in config.projects}
    files, seen = [], set()
    for agent in agent_homes():
        for directory in sorted((agent / "projects").glob("*/memory")):
            owner = names.get(directory.parent.name)
            if owner != project.name and (owner or not _machines(config, project)):
                continue
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or not _held(path):
                    continue
                stat = path.stat()
                if (stat.st_dev, stat.st_ino) not in seen:
                    seen.add((stat.st_dev, stat.st_ino))
                    files.append(path)
    return files


def _machines(config: jbus.Config, project: jbus.Project) -> bool:
    machine = config.owner("")
    return machine is not None and machine.name == project.name


def found(config: jbus.Config, project: jbus.Project) -> list[Path]:
    """Each rule file of the project: its homes' `standing.md`, then its auto-memory files."""
    home = config.home(project)
    standing = {home / "standing.md", *home.glob("*/standing.md")}
    if _machines(config, project):
        homes = {one.state for one in config.projects}
        standing |= {
            path for path in config.home_dir.glob("*/standing.md") if path.parent.name not in homes
        }
    held = [path for path in sorted(standing) if path.is_file() and _held(path)]
    return held + _memories(config, project)


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        default=argparse.SUPPRESS,
        help="the project's name in the config, to list its files alone",
    )


def _rules(args: argparse.Namespace, config: jbus.Config) -> int:
    named = getattr(args, "project", None)
    projects = [config.project(named)] if named else list(config.projects)
    count = 0
    for project in projects:
        for path in found(config, project):
            print(f"{project.name}: {path}")
            count += 1
    print(f"rules: {count} rule files")
    return 1 if count else 0


VERBS = (
    verbs.Verb(
        "rules",
        "list the files that hold a standing rule: a standing.md, an auto-memory file",
        _arguments,
        _rules,
    ),
)
