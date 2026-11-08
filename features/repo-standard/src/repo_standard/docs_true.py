"""The docs name only what the tree has: the core of "the docs say what the tree has", in any repo.

The pages are the tracked files the config's `docs.pages` globs match and its `docs.exclude` globs
do not. On each page:

- a path that starts at a folder of `docs.roots`, as `scripts/check.sh` or `features/a/docs/`,
  is a file or a folder of the tree, or a key of `docs.elsewhere`, whose value says why it is not.
  A path with a placeholder or a glob right after it (`features/<name>/`, `docs/*.md`) is a
  pattern, and a path with a `/` or a word before it (`/tmp/scripts/x`, `a/scripts/x`) starts
  somewhere else, so neither is read.
- a `make` command, a code span or a line of a fenced block that starts with `make`, names
  targets the root `Makefile` defines. The command ends at a `;`, `|`, `&`, `#` or `)`, and a
  `$(...)` in it is no target. Words that set a variable (`TESTS=a`) or pass a flag are not
  targets, and a command with `-C` or `-f` runs another makefile, so it is not read.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_standard.config import Config
from repo_standard.tree import Fault, chosen

FENCE = ("```", "~~~")
SPAN = re.compile(r"`([^`\n]+)`")
PATTERN_NEXT = "<*{$"
SUBSTITUTION = re.compile(r"\$\([^)]*\)|\$\{[^}]*\}")
SHELL_END = re.compile(r"[;|&#)]")
RULE = re.compile(r"^([^\s#:=][^:=]*?)\s*::?(?!=)")
ELSEWHERE_MAKEFILES = ("-C", "-f", "--file", "--directory")


def targets(root: Path) -> set[str] | None:
    """The targets the root Makefile defines, or None when there is none."""
    try:
        text = (root / "Makefile").read_text(encoding="utf-8")
    except OSError:
        return None
    found = set()
    for line in text.splitlines():
        rule = RULE.match(line)
        if rule and "$" not in rule[1]:
            found.update(rule[1].split())
    return found


def _named_targets(command: str) -> list[str]:
    words = SHELL_END.split(SUBSTITUTION.sub("", command))[0].split()
    if words[:1] != ["make"] or set(words) & set(ELSEWHERE_MAKEFILES):
        return []
    return [
        word.rstrip(":,.")
        for word in words[1:]
        if not word.startswith("-") and "=" not in word and not set(word) & set(PATTERN_NEXT)
    ]


def _paths(line: str, found: re.Pattern[str]) -> list[str]:
    return [
        at[1].rstrip(".").rstrip("/")
        for at in found.finditer(line)
        if not line[at.end() : at.end() + 1] or line[at.end()] not in PATTERN_NEXT
    ]


def page(text: str, name: str, root: Path, config: Config, made: set[str] | None) -> list[Fault]:
    """Each path and each make target the page names that the tree lacks."""
    docs = config.part("docs")
    roots = "|".join(re.escape(one.strip("/")) for one in docs.roots)
    found = re.compile(rf"(?<![\w/.~<>*$-])((?:{roots})/[\w.-]+(?:/[\w.-]+)*/?)")
    faults, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(FENCE):
            fenced = not fenced
            continue
        faults += [
            Fault(name, number, f"names {path}, which the tree lacks")
            for path in _paths(line, found)
            if path not in docs.elsewhere and not (root / path).exists()
        ]
        commands = [line.strip()] if fenced else SPAN.findall(line)
        for target in (one for command in commands for one in _named_targets(command)):
            if made is None:
                faults.append(Fault(name, number, f"runs make {target}, with no Makefile"))
            elif target not in made:
                faults.append(Fault(name, number, f"runs make {target}, which the Makefile lacks"))
    return faults


def check(root: Path, config: Config, paths: list[str]) -> list[Fault]:
    docs = config.part("docs")
    made = targets(root)
    faults = []
    for name in chosen(paths, docs.pages, docs.exclude):
        text = (root / name).read_text(encoding="utf-8", errors="replace")
        faults += page(text, name, root, config, made)
    return faults
