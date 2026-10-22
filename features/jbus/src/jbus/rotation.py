"""jbus keeps whose turn is first, the project the free slots start at, from one pass to the
next.

Each pass is a new process, so jbus keeps the place in a file, `rotation.json` in the state
directory: `{"next": "<project name>"}`. Only a pass that launched something writes it, and
it names the project after the last one that launched. If the file is missing or does not
read, or names a project the config no longer has, the turns start at the config's first.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from jbus import Config, dispatch, read_json, write_json

if TYPE_CHECKING:
    from jbus.cli import Half


def path(config: Config) -> Path:
    return config.state_dir / "rotation.json"


def start(config: Config) -> int:
    kept = read_json(path(config), {})
    name = kept.get("next") if isinstance(kept, dict) else None
    names = [project.name for project in config.projects]
    return names.index(name) if name in names else 0


def keep(config: Config, last: str) -> None:
    names = [project.name for project in config.projects]
    write_json(path(config), {"next": names[(names.index(last) + 1) % len(names)]})


def share(config: Config, halves: list[Half], say: Callable[[str], None]) -> None:
    """Launch across the projects, with one count of the crews out and the free slots given
    in turns.

    The turns start at the project the rotation file names. If the crews out of any project
    are not known, the count is not known, and `share` launches nothing anywhere.
    """
    first = start(config)
    turns = [half.turns for half in halves[first:] + halves[:first] if half.turns]
    out = [half.seen.out for half in halves]
    known = [count for count in out if count is not None]
    for half in halves:
        if half.seen.out is None:
            say(f"wait: crews out not known ({half.run.project.name}: {half.seen.why})")
    slots = config.max_running - sum(known) if len(known) == len(out) else None
    made = dispatch.dispatch(turns, slots)
    if made:
        keep(config, made[-1])
