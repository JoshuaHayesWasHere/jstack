"""Read a Result's `Proved:` line: the crew skill's proof that a pull request's changed tests fail
over its merge-base's code and pass at its head, or that it changes no test and is of a kind
that needs none. `jmerge` judges the line against the files the pull request changes
(`ready.short_on_proved`)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_RESULT = re.compile(r"^## Result\b", re.MULTILINE)
EXEMPT = {
    "docs": ("*.md", "*.txt", "*.rst", "docs/*"),
    "config": (
        "*.toml",
        "*.json",
        "*.yml",
        "*.yaml",
        "*.cfg",
        "*.ini",
        "*.lock",
        ".*",
        ".github/*",
    ),
}
"""The kinds of change a pull request that changes no test names on its `Proved: none, <kind>`
line, each with the paths it covers: `docs`, prose and the docs directories, and `config`,
settings, workflows, lockfiles and dotfiles. A pattern with a `/` matches from any directory
of the path on, one without it matches the file's name."""
_PROVED_RUN = re.compile(
    r"Proved: (?P<tests>\S.*?) base exit (?P<base_exit>\d+) at (?P<base>[0-9a-f]{40}), "
    r"head exit (?P<head_exit>\d+) at (?P<head>[0-9a-f]{40})"
)
_PROVED_NONE = re.compile(r"Proved: none, (?P<kinds>.+)")
_KIND_SEPARATOR = re.compile(r"\s*,\s*|\s+and\s+")


@dataclass(frozen=True)
class Proved:
    """A Result's `Proved:` line, which the crew skill's proof block prints.

    For a pull request that changes tests it names them, then their run with the head's tests
    over the merge-base's code (`base_exit`, 1 where they fail there) and at the head
    (`head_exit`, 0 where they pass): `Proved: <tests> base exit 1 at <base>, head exit 0 at
    <head>`. For one that changes no test, `kinds` names the kinds of change it is, from
    `EXEMPT`: `Proved: none, docs and config`. `fault` says why the line has neither shape."""

    tests: tuple[str, ...] = ()
    base_exit: int = -1
    base: str = ""
    head_exit: int = -1
    head: str = ""
    kinds: tuple[str, ...] = ()
    fault: str = ""


def proved(text: str) -> Proved | None:
    """The last `Proved:` line under a brief's first `## Result`, read, or None where there is
    none. A later line is a later run of the proof block, so it is the one that counts."""
    start = _RESULT.search(text)
    lines = text[start.start() :].splitlines() if start else []
    said = next((line.strip() for line in reversed(lines) if line.startswith("Proved:")), None)
    if said is None:
        return None
    run = _PROVED_RUN.fullmatch(said)
    if run:
        return Proved(
            tests=tuple(run["tests"].replace(",", " ").split()),
            base_exit=int(run["base_exit"]),
            base=run["base"],
            head_exit=int(run["head_exit"]),
            head=run["head"],
        )
    exempt = _PROVED_NONE.fullmatch(said)
    kinds = tuple(_KIND_SEPARATOR.split(exempt["kinds"].strip())) if exempt else ()
    unknown = [kind for kind in kinds if kind not in EXEMPT]
    if exempt and kinds and not unknown:
        return Proved(kinds=kinds)
    if unknown:
        return Proved(fault=f"names {', '.join(unknown)}, which is no kind of {', '.join(EXEMPT)}")
    return Proved(fault="is not <tests> base exit <n> at <base>, head exit <n> at <head>")
