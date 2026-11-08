"""Each rule of the repo standard names the file that enforces it.

`features/repo-standard/docs/standard.md` has a part for each area it covers, a `## ` heading, and
a rule is a `### ` heading under a part. A rule holds an `Enforced by:` line that names, in
backticks, at least one file under `scripts/`, `.github/` or `features/` that exists. A rule
whose line is missing, or names no such file, is a rule nobody checks, and the test fails on it.
"""

import re

from testing.paths import REPO

STANDARD = REPO / "features" / "repo-standard" / "docs" / "standard.md"
PARTS = ("Layout", "Feature map", "Docs")
ROOTS = ("scripts/", ".github/", "features/")
CITED = re.compile(r"`([^`\s]+)`")


def rules(text: str) -> dict[str, dict[str, list[str]]]:
    """Each part of the standard, with each of its rules and the lines of that rule."""
    found: dict[str, dict[str, list[str]]] = {}
    part = rule = None
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            part, rule = line[3:].strip(), None
            found[part] = {}
        elif line.startswith("### ") and part is not None:
            rule = line[4:].strip()
            found[part][rule] = []
        elif part is not None and rule is not None:
            found[part][rule].append(line)
    return found


def enforcers(lines: list[str]) -> list[str]:
    """The files a rule's `Enforced by:` line names that are under the roots and exist."""
    named = [
        path for line in lines if line.startswith("Enforced by:") for path in CITED.findall(line)
    ]
    return [path for path in named if path.startswith(ROOTS) and (REPO / path).is_file()]


def uncited(text: str) -> list[str]:
    """Each part of `PARTS` the standard lacks or holds no rule in, and each rule of those parts
    that names no file enforcing it."""
    found = rules(text)
    faults = [f"no rules in part {part}" for part in PARTS if not found.get(part)]
    faults += [
        f"{part} / {rule}: cites no file under {', '.join(ROOTS)}"
        for part in PARTS
        for rule, lines in found.get(part, {}).items()
        if not enforcers(lines)
    ]
    return faults


def test_each_rule_of_the_standard_cites_the_file_that_enforces_it():
    assert uncited(STANDARD.read_text(encoding="utf-8")) == []


def test_a_rule_with_no_enforced_by_line_fails():
    text = STANDARD.read_text(encoding="utf-8")
    first = next(iter(rules(text)["Layout"]))
    head = f"### {first}\n"
    start = text.index(head)
    line = text.index("Enforced by:", start)
    broken = text[:line] + text[text.index("\n", line) + 1 :]
    assert uncited(broken) == [
        f"Layout / {first}: cites no file under scripts/, .github/, features/"
    ]


def test_a_rule_that_cites_a_missing_file_or_one_outside_the_roots_fails():
    text = STANDARD.read_text(encoding="utf-8")
    added = (
        "### A rule nobody checks\n\nIt holds.\n\n"
        "Enforced by: `scripts/no-such-check.py`, `Makefile`\n\n"
    )
    broken = text.replace("## Docs\n", "## Docs\n\n" + added, 1)
    assert uncited(broken) == [
        "Docs / A rule nobody checks: cites no file under scripts/, .github/, features/"
    ]


def test_a_standard_with_a_part_missing_fails():
    text = STANDARD.read_text(encoding="utf-8")
    broken = text.replace("## Feature map\n", "## Feature list\n", 1)
    assert "no rules in part Feature map" in uncited(broken)
