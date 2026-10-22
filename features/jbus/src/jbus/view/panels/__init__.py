"""The panels of the view: each folder of this directory is one whole panel.

A panel's folder holds two files, and the folder's name is the panel's name. `panel.py` is its
data:

- `build(read)`, one function from the sources (`state.Read`) to a dict;
- `SHAPE`, the shape that `clean.keep` cuts that dict to before the server sends it;
- `SOURCES`, each source it reads, with who writes it (`state.Source`);
- `FIRST`, True where the first screen needs the dict: then its keys are keys of `/state.json`.
  The page asks for any other panel when its drawer opens, at `/panel/<name>.json`;
- `blind(read)`, the lines it cannot say now, and `NOT_KEPT`, the ones it never can
  (`state.Spot`). Each line opens the panel.

`panel.js` draws the panel, with one call of `panel` that passes whichever of these it has:

- `drawer(arg, data)`, the HTML of the drawer that `data-open="<name>:<arg>"` opens. `data` is
  the dict of a panel that is not on the first screen;
- `card()`, its card on the first screen. Only a panel that has one adds to that screen;
- `adds`, what it adds to another panel's drawer: `adds.task(task)` is one line of the task's
  drawer, and `adds.you()` is one count of the wait band;
- `wide`, for a drawer of the full width;
- `title`, for a panel the page asks for: the heading its drawer shows while the page waits for
  the answer;
- `gloss`, what its cards mean, by name, as `[name, text]`: the glossary at `#/help` lists it;
- `reads`, how fresh its drawer is, which the drawer's head says once: `"server"` for what the
  server reads itself on each request, `"mixed"` for both, and none for what a pass wrote.

Nothing else names a panel. The server lists this directory when it starts (`found`). The keys of
`/state.json`, the shapes, the list of sources, the routes and the page's drawers all come from
what it finds. The page is `page.html` with each `panel.js` in it. The server reads those files
on every request. A folder that is added or removed after the start counts as newer code on disk
(`names`), and the server starts again for it.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).parent
DATA, SCRIPT = "panel.py", "panel.js"
NAME = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class Panel:
    """One folder: its name, its data as the loaded module, and the path of its script."""

    name: str
    data: ModuleType
    script: Path

    @property
    def first(self) -> bool:
        return getattr(self.data, "FIRST", False) is True

    @property
    def shape(self) -> dict[str, Any]:
        return self.data.SHAPE

    @property
    def sources(self) -> tuple[Any, ...]:
        return tuple(getattr(self.data, "SOURCES", ()))

    @property
    def not_kept(self) -> tuple[Any, ...]:
        return tuple(getattr(self.data, "NOT_KEPT", ()))


def names(here: Path = HERE) -> tuple[str, ...]:
    """The name of each panel under `here` now, in order: every folder that holds the two files.
    Where the directory cannot be listed, there are no names."""
    try:
        return tuple(
            sorted(
                one.name
                for one in here.iterdir()
                if NAME.fullmatch(one.name) and (one / DATA).is_file() and (one / SCRIPT).is_file()
            )
        )
    except OSError:
        return ()


def found() -> tuple[Panel, ...]:
    """Each panel, in the order of the names."""
    return tuple(
        Panel(name, importlib.import_module(f"{__name__}.{name}.panel"), HERE / name / SCRIPT)
        for name in names()
    )
