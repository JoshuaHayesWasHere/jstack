"""Whose turn is first: the project the free slots start at, kept from one pass to the next.

Each pass is a new process, so the place is a file, `rotation.json` in the state directory:
`{"next": "<project name>"}`. It is written only by a pass that launched something, and
names the project after the last one that launched. A file that is missing or does not
read, or that names a project the config no longer has, starts at the config's first.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from jbus import Config, alert, dispatch, health, read_json, write_json

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
    """Launch across the projects: one count of the crews out, and the free slots in turns.

    The turns start at the project the rotation file names. With the crews out of any
    project not known, the count is not known, and nothing is launched anywhere.

    The machine is looked at first, once a pass (`health`): an instance capped since the last
    pass is paged before a launch skips it, and one whose window reset says launches on it
    resume before the launch that goes there. A look that raises is said, and the launch
    goes on.
    """
    if halves:
        now = halves[0].run.now
        try:
            health.watch(config, now, say)
        except Exception as error:
            say(f"health failed: {alert.why(error, *config.hooks())}")
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
