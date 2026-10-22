"""What the page cannot say: each source that could not be read, what each panel cannot say now,
and last what the view never can.

Each line opens the panel that says it. The line of a source that could not be read opens the panel
that names the source, when the page asks the server for that panel on its own. Otherwise the
line opens the list of every source, which the pulse panel draws.
"""

from __future__ import annotations

from typing import Any

from jbus.view.state import Read, Spot

FIRST = True
UNREAD = ("missing", "unreadable")
SOURCES_AT = "pulse"
SHAPE = {"blind": [{"line": None, "open": None}]}


def _unread(read: Read) -> list[dict[str, str]]:
    """Each source that could not be read, except a source that a session writes, since having no
    session is no fault. Each line opens the one panel that names its source, where that panel is
    not on the first screen."""
    names: dict[str, list[str]] = {}
    for panel in read.panels:
        for source in panel.sources:
            names.setdefault(source.name, []).append("" if panel.first else panel.name)
    return [
        {
            "line": f"{one['name']} could not be read",
            "open": (names[one["name"]][0] if len(names[one["name"]]) == 1 else "") or SOURCES_AT,
        }
        for one in read.listed
        if one["state"] in UNREAD and one["by"] != "session"
    ]


def _spots(read: Read, kept: bool) -> list[dict[str, str]]:
    """What each panel cannot say now, or what it never can, in the order of the ranks."""
    found: list[tuple[Spot, str]] = []
    for panel in read.panels:
        say = getattr(panel.data, "blind", None)
        spots = panel.not_kept if kept else say(read) if say else []
        found += [(spot, panel.name) for spot in spots]
    found.sort(key=lambda one: one[0].rank)
    return [{"line": spot.line, "open": name} for spot, name in found]


def build(read: Read) -> dict[str, Any]:
    return {"blind": _unread(read) + _spots(read, kept=False) + _spots(read, kept=True)}
