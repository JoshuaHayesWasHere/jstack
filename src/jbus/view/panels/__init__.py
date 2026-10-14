"""The panels of the view: each folder of this directory is one, whole.

A panel's folder holds two files, and its name is the panel's. `panel.py` is its data:

- `build(read)`, one function from the sources (`state.Read`) to a dict;
- `SHAPE`, the shape that dict is cut to (`clean.keep`) before it leaves;
- `SOURCES`, each source it reads, with who writes it (`state.Source`);
- `FIRST`, True where the first screen needs the dict: then its keys are keys of
  `/state.json`. Any other panel is asked for when its drawer opens, at
  `/panel/<name>.json`;
- `blind(read)`, the lines it cannot say now, and `NOT_KEPT`, the ones it never can
  (`state.Spot`). Each opens the panel.

`panel.js` is its drawing, one call of `panel` with what it has of these:

- `drawer(arg, data)`, the drawer `data-open="<name>:<arg>"` opens, as HTML. `data` is the
  dict of a panel that is not on the first screen;
- `card()`, its card on the first screen. Only a panel that has one adds to that screen;
- `adds`, what it adds to another panel's drawer: `adds.task(task)` is one line of the
  task's drawer, and `adds.you()` one count of the wait band;
- `wide`, for a drawer of the full width, and `title`, the heading of the drawer of a panel
  that is asked for, while its answer is on its way.

Nothing else names a panel. The server lists this directory when it starts (`found`), and
the keys of `/state.json`, the shapes, the list of sources, the routes and the page's
drawers are what it finds: the page is `page.html` with each `panel.js` in it, read on
every request. A folder that comes or goes after the start is code on disk that is newer
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
    """One folder: its name, its data as the module loaded, and where its script is."""

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
    """The name of each panel there is under `here` now: every folder that holds the two
    files, in order, and no name where the directory cannot be listed."""
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
