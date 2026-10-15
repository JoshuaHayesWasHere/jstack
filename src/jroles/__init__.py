"""jroles: the model each role's thread is launched on, read from the role map.

This module is the model: the map's lines, read into one answer for one role. The map is
`${XDG_CONFIG_HOME:-~/.config}/jstack/roles`, one line a role, `#` for a comment:

    crew: <provider> <model> [<instanceId>] [effort=<low|medium>]
    review: inherit

A role with no line, or with `inherit`, is launched on the model of the thread that launches it.

A Claude selection always carries its effort, `medium` where the line names none. T3 Code
launches a model with no effort option at that model's own default, which is `high` for some
(Claude Sonnet 5.5, Claude Opus 5), and the user's rule is that no thread runs above medium.
So the map may lower a role to `low` and nothing raises one: any other level refuses that
role, whose launch then inherits.
That holds for Claude lines only. The other providers name their effort option otherwise,
and a line for one takes none: it launches at that provider's own default, which is not read
here, as T3 Code lists no models for them on this machine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ROLES = ("crew", "scout", "review", "home", "expert", "exec")
PROVIDERS = {"claudeAgent": "Claude", "codex": "Codex", "grok": "Grok"}
INHERIT = "inherit"
EFFORTS = ("low", "medium")
EFFORT = "medium"
_LINE = re.compile(
    rf"({'|'.join(ROLES)}):[ \t]+(\S+)(?:[ \t]+(\S+))?(?:[ \t]+(\S+))?(?:[ \t]+(\S+))?"
)
_EFFORT = re.compile(r"effort=(\S*)")


class Refused(Exception):
    """The map gives the role no model selection. The message is the one line to print."""


@dataclass(frozen=True)
class Selection:
    """What `t3_thread_launch` takes as `modelSelection`."""

    provider: str
    model: str
    instance_id: str | None = None
    effort: str | None = None

    def as_json(self) -> dict[str, object]:
        given: dict[str, object] = {"provider": self.provider, "model": self.model}
        if self.instance_id is not None:
            given["instanceId"] = self.instance_id
        if self.effort is not None:
            given["options"] = [{"id": "effort", "value": self.effort}]
        return given


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
        plain = words[:-1] if words and _EFFORT.fullmatch(words[-1]) else words
        alone = not any(_EFFORT.fullmatch(word) for word in plain)
        whole = alone and (words == (INHERIT,) or (2 <= len(plain) <= 3 and plain[0] != INHERIT))
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
    named = _EFFORT.fullmatch(words[-1])
    plain, effort = (words[:-1], named[1]) if named else (words, None)
    if words[0] != "claudeAgent":
        if effort is not None:
            raise Refused(f"refused {role}: only a Claude line names an effort")
        return Selection(*plain)
    if effort is not None and effort not in EFFORTS:
        raise Refused(f"refused {role}: effort={effort} is not low or medium")
    return Selection(*plain, effort=effort or EFFORT)


def _names() -> str:
    *first, last = PROVIDERS.values()
    return f"{', '.join(first)} or {last}"
