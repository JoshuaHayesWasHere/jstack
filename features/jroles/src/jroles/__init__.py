"""jroles: the model that each role's thread launches on, which jroles reads from the role map.

This module reads the map's lines into the answer for one role. The map is
`${XDG_CONFIG_HOME:-~/.config}/jstack/roles`, with one line for each role, and `#` starts a
comment:

    crew: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<level>] [fast=<on|off>]
    review: <provider> <model> [<instanceId>[,...]] [effort=<level>] [fast=<on|off>]
    review: <provider> <model> [<instanceId>[,...]] [effort=<level>] [fast=<on|off>]

A role with no line, or with `inherit`, runs on the model of the thread that launches it.
The instances that a line names are its pool, in order. A launch goes to the first of them
with headroom in the ledger (`jroles.pool`). A line that names no instance has a pool of one,
the provider's built-in instance.
Only `review` may have several lines. Each line is one reviewer, in the order the lines are
written, and every pull request gets a review from each reviewer.

Each provider names its effort with its own option id. It accepts only the levels that T3
Code lists for it (`PROVIDERS`), up to the ceiling that the user's rule gives the role
(`Provider.allowed`). A Claude selection always carries its effort, which is `medium` when the
line names none. T3 Code launches a model that has no effort option at that model's own
default, and that default is `high` for some models (Claude Sonnet 5.5, Claude Opus 5). The
user's rule is that no Claude thread runs above medium unless the user says so. So the map may
lower a Claude role to `low`, and it raises only `review`, to `high`, as the user said on
2026-10-20. The other providers launch at their own default when the line names no effort.
Only Cursor takes `fast=`, and its default is on.
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
    """The ids that T3 Code gives a provider's options, and the levels it lists for the
    provider's effort, lowest first. `ceiling` is the user's rule, the highest level a role may
    name. `raised` holds the roles that the user lifted above it. A level that T3 Code lists is
    not allowed for that reason alone."""

    name: str
    effort: str | None = None
    levels: tuple[str, ...] = ()
    default: str | None = None
    fast: str | None = None
    ceiling: str | None = None
    raised: tuple[tuple[str, str], ...] = ()

    def allowed(self, role: str) -> tuple[str, ...]:
        """The levels that a line of `role` may name: the listed ones, up to the role's
        ceiling."""
        top = dict(self.raised).get(role, self.ceiling)
        return self.levels if top is None else self.levels[: self.levels.index(top) + 1]


PROVIDERS = {
    "claudeAgent": Provider(
        "Claude",
        "effort",
        ("low", "medium", "high", "xhigh", "max"),
        default="medium",
        ceiling="medium",
        raised=(("review", "high"),),
    ),
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
    """What `t3_thread_launch` takes as `modelSelection`, built from one line of the map."""

    provider: str
    model: str
    pool: tuple[str, ...] = ()
    effort: str | None = None
    fast: bool | None = None

    @property
    def instances(self) -> tuple[str, ...]:
        """The pool, or the provider's built-in instance when the line names no instance."""
        return self.pool or (self.provider,)

    def as_json(self, instance: str | None = None) -> dict[str, object]:
        """The selection on `instance`, or on the first instance of the pool when the caller
        gives none. When the line names no instance, the thread launches on the provider's
        own instance, and the selection names no instance either. Each option carries the id
        that the provider gives it."""
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
    """The selections that the map gives `role`, in order, or none when the role has no line
    or has `inherit`.

    The function refuses the whole map when one line does not fit the map's format, whichever
    role the line is for, because a half-read map would launch a thread on a model that nobody
    chose. For the same reason, when it refuses one line of a role, it refuses every line of
    that role."""
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
    """Whether the words make a whole line: `inherit` alone, or two or three plain words
    followed by options, each named at most once."""
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
    """The words at the end of a line that are options, which are `effort=` or `fast=`."""
    at = len(words)
    while at and _OPTION.fullmatch(words[at - 1]):
        at -= 1
    return words[at:]


def _fits(before: list[tuple[str, ...]], role: str, words: tuple[str, ...]) -> bool:
    """Whether a line can join the earlier lines of its role. Only `review` takes more than
    one line, and `inherit` is never one of several."""
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
    if effort is not None and effort not in known.allowed(role):
        raise Refused(f"refused {role}: effort={effort} is not {_names(known.allowed(role))}")
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
    """One list, `a, b or c`, that gives each provider by its name and each level as it
    is."""
    *first, last = [PROVIDERS[name].name if name in PROVIDERS else name for name in names]
    return f"{', '.join(first)} or {last}" if first else last
