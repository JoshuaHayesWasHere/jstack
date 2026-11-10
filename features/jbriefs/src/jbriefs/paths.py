"""The paths and globs a line of a brief names, and whether a changed file is one of them or
under one. `jbriefs.parse` reads them from a brief's head lines, such as `Where:`."""

from __future__ import annotations

import re

_PAREN = re.compile(r"\([^()]*\)")
_WORD = re.compile(r"`[^`]+`|\S+")
_LINES = re.compile(r":\d+(?:-\d+)?$")
_PATHLIKE = re.compile(r"[\w.@+~*?\[\]{}/-]+")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_BRACES = re.compile(r"\{([^{}]*)\}")


def _path(word: str, ticked: bool) -> str:
    """The path or glob under the repo that a word names, or an empty string when it names none.

    A word in backticks names one if it is a single token that is not an option, a URL or a
    path that leaves the repo. A word between commas needs more to tell it from prose: a
    `/`, a glob, or a file extension.
    """
    if word.strip() in (".", "./"):
        return "."
    word = _LINES.sub("", word.strip().rstrip(".,;:")).removeprefix("./")
    if not word or word[0] in "-/~" or ".." in word.split("/") or "://" in word:
        return ""
    if not _PATHLIKE.fullmatch(word):
        return ""
    if not ticked and not ("/" in word or "*" in word or _EXTENSION.search(word)):
        return ""
    return word.rstrip("/")


def _items(line: str) -> list[str]:
    """The line cut at each comma that is not inside a brace set."""
    items, depth, start = [], 0, 0
    for at, char in enumerate(line):
        if char == "{":
            depth += 1
        elif char == "}" and depth:
            depth -= 1
        elif char == "," and not depth:
            items.append(line[start:at])
            start = at + 1
    return [*items, line[start:]]


def _expanded(word: str) -> tuple[str, ...]:
    """A word with its brace sets spelled out, the innermost first: `a{b,c}.py` gives two."""
    found = _BRACES.search(word)
    if found is None:
        return (word,)
    head, tail = word[: found.start()], word[found.end() :]
    return tuple(
        whole for part in found.group(1).split(",") for whole in _expanded(head + part + tail)
    )


def named(line: str) -> tuple[str, ...]:
    """The paths and globs that a line names, in its order, each once.

    An item is a span in backticks or a span between commas, and the function keeps each
    item that names a path under the repo. A `path:line` or `path:a-b` keeps its path, and a
    directory loses its closing `/`. The function drops prose in parentheses, with the commas
    in it. It spells out a brace set, so `src/{a,b}.py` gives two paths, and the commas of a
    brace set do not end an item. It reads a bare word when the word is the first of its item
    (`docs/ pages tied to`) or has a `/` (`plus templates/x.service`). A line that names no
    path gives an empty tuple.
    """
    while (bare := _PAREN.sub("", line)) != line:
        line = bare
    found: dict[str, None] = {}
    for item in _items(line):
        for at, word in enumerate(_WORD.findall(item)):
            ticked = word.startswith("`") and word.endswith("`") and len(word) > 1
            if ticked or at == 0 or "/" in word:
                named = (
                    _path(one, ticked) for one in _expanded(word.strip("`") if ticked else word)
                )
                found.update(dict.fromkeys(filter(None, named)))
    return tuple(found)


def _glob(pattern: str) -> re.Pattern[str]:
    """A glob as a regex over a whole path. A `*` matches within one name, and `**` crosses `/`."""
    out, at = "", 0
    while at < len(pattern):
        if pattern.startswith("**/", at):
            out, at = out + "(?:.*/)?", at + 3
        elif pattern.startswith("**", at):
            out, at = out + ".*", at + 2
        elif pattern[at] == "*":
            out, at = out + "[^/]*", at + 1
        elif pattern[at] == "?":
            out, at = out + "[^/]", at + 1
        else:
            out, at = out + re.escape(pattern[at]), at + 1
    return re.compile(out)


def covers(patterns: tuple[str, ...], path: str) -> bool:
    """Whether a changed file is one of the paths and globs that `where` gave, or is under one.
    `.` is the whole repo."""
    if "." in patterns:
        return True
    parts = path.split("/")
    parents = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    return any(_glob(pattern).fullmatch(parent) for pattern in patterns for parent in parents)


_SOURCE = re.compile(r"^features/(?P<feature>[^/]+)/src(?:/|$)")
_LANDS = re.compile(r"\(in (?P<named>none|`[^()]*)\)\W*$")


def reach(inside: tuple[str, ...], kept: tuple[str, ...]) -> tuple[str, ...]:
    """The paths of `inside`, a brief's `Where:`, and the `docs/` of each feature whose source
    under `features/<f>/src/` they name, where `kept`, its `Do not touch:`, does not cover it. A
    doc line a change makes wrong is fixed in the same pull request, not queued as a row."""
    docs = (f"features/{hit['feature']}/docs" for path in inside if (hit := _SOURCE.match(path)))
    return tuple(dict.fromkeys((*inside, *(doc for doc in docs if not covers(kept, doc)))))


def lands_in(item: str) -> tuple[str, ...] | None:
    """The files a `Done when:` item says it lands in, from the `(in `<path>`, ...)` or
    `(in none)` that ends it, or None when it ends with no such marker."""
    marker = _LANDS.search(item)
    return None if marker is None else named(marker["named"])
