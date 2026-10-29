"""jbus records which project's turn is first, the project where the free slots start, and
keeps it from one pass to the next.

Each pass is a new process, so jbus keeps the place in a file, `rotation.json` in the state
directory: `{"next": "<project name>"}`. Only a pass that launched something writes the file, and
the file names the project that comes after the last project that launched. If the file is missing,
cannot be read, or names a project that the config no longer has, the turns start at the config's
first project.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from jbus import Config, dispatch, read_json, write_json

if TYPE_CHECKING:
    from jbus.poll import Half


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
    """Launch across all the projects. `share` counts the crews out once for all of them,
    and gives out the free slots of `max_running` in turns. Each project's `Turns` keeps its
    own caps, by home and for the project (`dispatch.Caps`).

    The turns start at the project that the rotation file names. If jbus does not know how
    many crews any one project has out, it does not know the total, and `share` launches
    nothing anywhere.
    """
    first = start(config)
    turns = [half.turns for half in halves[first:] + halves[:first] if half.turns]
    out = [half.seen.out for half in halves]
    known = [count for count in out if count is not None]
    for half in halves:
        if half.seen.out is None:
            say(f"wait: crews out not known ({half.run.project.name}: {half.seen.why})")
    slots = config.max_running - sum(map(len, known)) if len(known) == len(out) else None
    made = dispatch.dispatch(turns, slots)
    if made:
        keep(config, made[-1])
