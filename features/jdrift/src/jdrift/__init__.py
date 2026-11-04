"""jdrift: what changed upstream in pstack since the pin, for the files this repo took from it.

This module reads the pstack section of `THIRD_PARTY.md` into five parts: the pin, the upstream
paths with the local files that came from each one, the commit each upstream path was last taken
at where that is not the pin, the upstream skills that the repo left out on purpose, and
jstack's own files. jstack's own files are in the same folders as the files this repo took
from pstack, but they have no upstream to compare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FILE = "THIRD_PARTY.md"
_PIN = re.compile(r"^- Commit: ([0-9a-f]{7,40})$", re.MULTILINE)
_NOT_TAKEN = re.compile(r"^Not taken: (.+)$", re.MULTILINE)
_OWN = re.compile(r"^jstack's own: (.+)$", re.MULTILINE)
_BLOCK = re.compile(r"^Upstream map:\n+```\n(.*?)^```$", re.MULTILINE | re.DOTALL)
_LINE = re.compile(r"(\S+) <- (pstack/\S+(?:, pstack/\S+)*)")
_AT = re.compile(r"(pstack/[^@\s]+)(?:@([0-9a-f]{7,40}))?")


class Refused(Exception):
    """jdrift cannot compare this repo with the upstream. The message is the one line to
    print."""


@dataclass(frozen=True)
class Pinned:
    pin: str
    sources: dict[str, tuple[str, ...]]
    not_taken: frozenset[str]
    own: tuple[str, ...] = ()
    pins: dict[str, str] = field(default_factory=dict)

    def at(self, upstream: str) -> str:
        """The commit `upstream` was last taken at: its own pin, or the `Commit:` line's."""
        return self.pins.get(upstream, self.pin)


def read_section(text: str) -> Pinned:
    """The pstack section of `THIRD_PARTY.md`. It has its `Commit:` line, and its
    `Upstream map:` block with one `<local path> <- <upstream path>[, <upstream path>...]` on
    each line. An upstream path taken at another commit than the `Commit:` line's carries it,
    as `pstack/<path>@<commit>`, on every line that names it. It also has a `Not taken:` line,
    and a `jstack's own:` line, which lists in backticks the local paths that come from no
    upstream path."""
    found = re.search(r"^## pstack\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not found:
        raise Refused(f"{FILE}: no pstack section")
    section = found.group(1)
    pin = _PIN.search(section)
    if not pin:
        raise Refused(f"{FILE}: the pstack section has no Commit: line")
    block = _BLOCK.search(section)
    if not block:
        raise Refused(f"{FILE}: the pstack section has no Upstream map: block")
    fed: dict[str, list[str]] = {}
    pins: dict[str, str | None] = {}
    seen: set[str] = set()
    for line in filter(None, block.group(1).splitlines()):
        entry = _LINE.fullmatch(line)
        if not entry:
            raise Refused(f"{FILE}: the Upstream map: block does not parse at: {line}")
        local = entry.group(1)
        if local in seen:
            raise Refused(f"{FILE}: the Upstream map: block names twice: {local}")
        seen.add(local)
        for named in entry.group(2).split(", "):
            path = _AT.fullmatch(named)
            if not path:
                raise Refused(f"{FILE}: the Upstream map: block does not parse at: {line}")
            upstream, at = path.groups()
            if pins.setdefault(upstream, at) != at:
                raise Refused(f"{FILE}: the Upstream map: block names {upstream} at two commits")
            fed.setdefault(upstream, []).append(local)
    if not fed:
        raise Refused(f"{FILE}: the Upstream map: block has no line")
    left_out = _NOT_TAKEN.search(section)
    not_taken = re.findall(r"pstack/[^\s`,]+", left_out.group(1)) if left_out else []
    ours = _OWN.search(section)
    own = re.findall(r"`([^`]+)`", ours.group(1)) if ours else []
    for local in own:
        if local in seen:
            raise Refused(
                f"{FILE}: {local} is in the Upstream map: block and on the jstack's own: line"
            )
    return Pinned(
        pin=pin.group(1),
        sources={upstream: tuple(fed[upstream]) for upstream in sorted(fed)},
        not_taken=frozenset(not_taken),
        own=tuple(own),
        pins={upstream: at for upstream, at in sorted(pins.items()) if at},
    )
