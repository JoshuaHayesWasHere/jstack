"""Whose turn is first: the project the free slots start at, kept from one pass to the next.

Each pass is a new process, so the place is a file, `rotation.json` in the state directory:
`{"next": "<project name>"}`. It is written only by a pass that launched something, and
names the project after the last one that launched. A file that is missing or does not
read, or that names a project the config no longer has, starts at the config's first.
"""

from __future__ import annotations

from pathlib import Path

from jbus import Config, read_json, write_json


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
