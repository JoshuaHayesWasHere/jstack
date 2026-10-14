"""jroles: the model each role's thread is launched on, read from the role map.

This module is the model: the map's lines, read into one answer for one role. The map is
`${XDG_CONFIG_HOME:-~/.config}/jstack/roles`, one line a role, `#` for a comment:

    crew: <provider> <model> [<instanceId>]
    review: inherit

A role with no line, or with `inherit`, is launched on the model of the thread that launches it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ROLES = ("crew", "scout", "review", "home", "expert", "exec")
PROVIDERS = {"claudeAgent": "Claude", "codex": "Codex", "grok": "Grok"}
INHERIT = "inherit"
_LINE = re.compile(rf"({'|'.join(ROLES)}):[ \t]+(\S+)(?:[ \t]+(\S+))?(?:[ \t]+(\S+))?")


class Refused(Exception):
    """The map gives the role no model selection. The message is the one line to print."""


@dataclass(frozen=True)
class Selection:
    """What `t3_thread_launch` takes as `modelSelection`."""

    provider: str
    model: str
    instance_id: str | None = None

    def as_json(self) -> dict[str, str]:
        given = {"provider": self.provider, "model": self.model}
        return given if self.instance_id is None else {**given, "instanceId": self.instance_id}


def read_map(text: str, role: str) -> Selection | None:
    """The selection the map gives `role`, or None for no line or `inherit`.

    A line that is not the map's refuses the whole map, whichever role it is for: a map that
    is half read would launch a thread on a model nobody chose."""
    lines: dict[str, tuple[str, ...]] = {}
    bad = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        entry = _LINE.fullmatch(line.strip())
        words = tuple(filter(None, entry.groups()[1:])) if entry else ()
        whole = words == (INHERIT,) or (len(words) >= 2 and words[0] != INHERIT)
        if entry and whole and entry[1] not in lines:
            lines[entry[1]] = words
        else:
            bad.append(f"bad line {number}: {line}")
    if bad:
        raise Refused("\n".join(bad))
    words = lines.get(role, (INHERIT,))
    if words == (INHERIT,):
        return None
    if words[0] not in PROVIDERS:
        raise Refused(f"refused {role}: {words[0]} is not {_names()}")
    return Selection(*words)


def _names() -> str:
    *first, last = PROVIDERS.values()
    return f"{', '.join(first)} or {last}"
