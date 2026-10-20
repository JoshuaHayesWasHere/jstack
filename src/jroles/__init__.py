"""jroles: the model each role's thread is launched on, read from the role map.

This module is the model: the map's lines, read into the answer for one role. The map is
`${XDG_CONFIG_HOME:-~/.config}/jstack/roles`, one line a role, `#` for a comment:

    crew: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<level>] [fast=<on|off>]
    review: <provider> <model> [<instanceId>[,...]] [effort=<level>] [fast=<on|off>]
    review: <provider> <model> [<instanceId>[,...]] [effort=<level>] [fast=<on|off>]

A role with no line, or with `inherit`, is launched on the model of the thread that launches it.
The instances are a line's pool, in order: a launch goes to the first of them with headroom in
the ledger (`jroles.pool`). A line that names none has the provider's built-in instance as its
pool of one.
`review` alone may have several lines: each is one reviewer, in the order they are written,
and every pull request gets a review from each.

Each provider names its effort with its own option id, and takes only the levels T3 Code
lists for it (`PROVIDERS`). A Claude selection always carries its effort, `medium` where the
line names none. T3 Code launches a model with no effort option at that model's own default,
which is `high` for some (Claude Sonnet 5.5, Claude Opus 5), and the user's rule is that no
Claude thread runs above medium unless told: so the map may lower a Claude role to `low` and
nothing raises one. The other providers launch at their own default where the line names no
effort. `fast=` is Cursor's alone, whose default is on.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

ROLES = ("crew", "scout", "review", "home", "expert")
LISTED = "review"
INHERIT = "inherit"
_LINE = re.compile(rf"({'|'.join(ROLES)}):[ \t]+(\S+(?:[ \t]+\S+)*)")
_OPTION = re.compile(r"(effort|fast)=(\S*)")
_FAST = {"on": True, "off": False}


@dataclass(frozen=True)
class Provider:
    """What T3 Code calls a provider's options, and the levels it lists for its effort."""

    name: str
    effort: str | None = None
    levels: tuple[str, ...] = ()
    default: str | None = None
    fast: str | None = None


PROVIDERS = {
    "claudeAgent": Provider("Claude", "effort", ("low", "medium"), default="medium"),
    "codex": Provider(
        "Codex", "reasoningEffort", ("low", "medium", "high", "xhigh", "max", "ultra")
    ),
    "cursor": Provider(
        "Cursor", "reasoning_effort", ("low", "medium", "high", "xhigh"), fast="fastMode"
    ),
    "grok": Provider("Grok"),
}


class Refused(Exception):
    """The map gives the role no model selection. The message is the one line to print."""


@dataclass(frozen=True)
class Selection:
    """What `t3_thread_launch` takes as `modelSelection`: one line of the map."""

    provider: str
    model: str
    pool: tuple[str, ...] = ()
    effort: str | None = None
    fast: bool | None = None

    @property
    def instances(self) -> tuple[str, ...]:
        """The pool, or the provider's built-in instance where the line names none."""
        return self.pool or (self.provider,)

    def as_json(self, instance: str | None = None) -> dict[str, object]:
        """The selection on `instance`, the first of the pool where none is given. A line that
        names no instance launches on the provider's own, and names none either. Each option
        goes by the id the provider gives it."""
        given: dict[str, object] = {"provider": self.provider, "model": self.model}
        if self.pool:
            given["instanceId"] = instance or self.pool[0]
        known = PROVIDERS[self.provider]
        options = [
            {"id": option, "value": value}
            for option, value in ((known.effort, self.effort), (known.fast, self.fast))
            if option is not None and value is not None
        ]
        if options:
            given["options"] = options
        return given


def read_map(text: str, role: str) -> tuple[Selection, ...]:
    """The selections the map gives `role`, in order, or none for no line or `inherit`.

    A line that is not the map's refuses the whole map, whichever role it is for: a map that
    is half read would launch a thread on a model nobody chose. For the same reason one line
    of a role that is refused refuses every line of that role."""
    lines: dict[str, list[tuple[str, ...]]] = {}
    bad = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        entry = _LINE.fullmatch(line.strip())
        words = tuple(entry[2].split()) if entry else ()
        if entry and _whole(words) and _fits(lines.get(entry[1], []), entry[1], words):
            lines.setdefault(entry[1], []).append(words)
        else:
            bad.append(f"bad line {number}: {line}")
    if bad:
        raise Refused("\n".join(bad))
    given = lines.get(role, [(INHERIT,)])
    if given == [(INHERIT,)]:
        return ()
    return tuple(_selection(role, words) for words in given)


def _whole(words: tuple[str, ...]) -> bool:
    """`inherit` alone, or two or three plain words and then each option once."""
    if words == (INHERIT,):
        return True
    plain = len(words) - len(_options(words))
    named = [_OPTION.fullmatch(word)[1] for word in words[plain:]]
    return (
        2 <= plain <= 3
        and words[0] != INHERIT
        and not any("=" in word for word in words[:plain])
        and len(named) == len(set(named))
    )


def _options(words: tuple[str, ...]) -> tuple[str, ...]:
    """The words at the end of a line that are options, `effort=` or `fast=`."""
    at = len(words)
    while at and _OPTION.fullmatch(words[at - 1]):
        at -= 1
    return words[at:]


def _fits(before: list[tuple[str, ...]], role: str, words: tuple[str, ...]) -> bool:
    """Whether a line can join the lines of its role before it: only `review` takes more than
    one, and `inherit` is never one of several."""
    if not before:
        return True
    return role == LISTED and (INHERIT,) not in (*before, words)


def _selection(role: str, words: tuple[str, ...]) -> Selection:
    if words[0] not in PROVIDERS:
        raise Refused(f"refused {role}: {words[0]} is not {_names(PROVIDERS)}")
    known = PROVIDERS[words[0]]
    named = _options(words)
    options = dict(_OPTION.fullmatch(word).groups() for word in named)
    plain = words[: len(words) - len(named)]
    effort = options.get("effort")
    if effort is not None and known.effort is None:
        raise Refused(f"refused {role}: a {known.name} line names no effort")
    if effort is not None and effort not in known.levels:
        raise Refused(f"refused {role}: effort={effort} is not {_names(known.levels)}")
    fast = options.get("fast")
    if fast is not None and known.fast is None:
        fast_ones = [name for name, one in PROVIDERS.items() if one.fast]
        raise Refused(f"refused {role}: only a {_names(fast_ones)} line names fast")
    if fast is not None and fast not in _FAST:
        raise Refused(f"refused {role}: fast={fast} is not on or off")
    provider, model, *listed = plain
    pool = tuple(listed[0].split(",")) if listed else ()
    if not all(pool) or len(set(pool)) != len(pool):
        raise Refused(f"refused {role}: the pool {listed[0]} names an instance twice or none")
    return Selection(
        provider,
        model,
        pool,
        effort=effort or known.default,
        fast=None if fast is None else _FAST[fast],
    )


def _names(names: Iterable[str]) -> str:
    """Each provider by its name and each level as it is, as one list: `a, b or c`."""
    *first, last = [PROVIDERS[name].name if name in PROVIDERS else name for name in names]
    return f"{', '.join(first)} or {last}" if first else last
