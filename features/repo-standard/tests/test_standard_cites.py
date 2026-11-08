"""Each rule of the repo standard names the file that enforces it.

`features/repo-standard/docs/standard.md` has a part for each area it covers, a `## ` heading, and
a rule is a `### ` heading under a part. A rule holds an `Enforced by:` line that names, in
backticks, at least one file under `scripts/`, `.github/`, `features/` or `testing/` that exists.
A rule whose line is missing, or names no such file, is a rule nobody checks, and the test fails on
it. The part `Versions` holds no such line, since no check of the tag exists before the tag does,
but it defines the tag and a breaking change.

The `Makefile`'s opening comment and the standard's CI part say what CI runs on a pull request, so
each names in backticks the `make` targets that the pull-request jobs of `check.yml` run, and no
other.
"""

import re

from testing.paths import REPO

STANDARD = REPO / "features" / "repo-standard" / "docs" / "standard.md"
MAKEFILE = REPO / "Makefile"
WORKFLOW = REPO / ".github" / "workflows" / "check.yml"
PARTS = ("Layout", "Feature map", "Docs", "Scripts", "Guards", "Testing", "CI", "Deploy")
VERSIONS = ("The standard is versioned by a tag", "A breaking change takes a new version")
ROOTS = ("scripts/", ".github/", "features/", "testing/")
CITED = re.compile(r"`([^`\s]+)`")
MAKE = re.compile(r"\bmake ([a-z][\w-]*)")
NAMED = re.compile(r"`make ([a-z][\w-]*)")


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
    versions = found.get("Versions", {})
    faults += [f"no rule {rule} in part Versions" for rule in VERSIONS if rule not in versions]
    defined = "\n".join(line for lines in versions.values() for line in lines)
    faults += [] if "`repo-standard-vN`" in defined else ["Versions does not name repo-standard-vN"]
    return faults


def pull_request_targets(workflow: str) -> set[str]:
    """The `make` targets that the jobs of the workflow which run only on a pull request run."""
    targets: set[str] = set()
    on_pull_request = False
    for line in workflow.split("\njobs:\n", 1)[1].splitlines():
        if re.match(r"  [\w-]+:$", line):
            on_pull_request = False
        elif re.match(r"    if: .*github\.event_name == 'pull_request'", line):
            on_pull_request = True
        elif on_pull_request and line.lstrip().startswith(("run:", "- run:")):
            targets |= set(MAKE.findall(line))
    return targets


def makefile_says(makefile: str) -> set[str]:
    """The targets the sentence on a pull request of the `Makefile`'s opening comment names."""
    head = " ".join(
        line.removeprefix("#").strip() for line in makefile.split("\n\n", 1)[0].splitlines()
    )
    said = [one for one in re.split(r"(?<=\.) ", head) if "pull request" in one]
    return {target for one in said for target in NAMED.findall(one)}


def ci_part_says(text: str) -> set[str]:
    """The targets the CI part's rule on a pull request names."""
    lines = rules(text)["CI"]["A pull request runs the selection, the lint and the selected tests"]
    return set(NAMED.findall("\n".join(lines)))


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
        f"Layout / {first}: cites no file under scripts/, .github/, features/, testing/"
    ]


def test_a_rule_that_cites_a_missing_file_or_one_outside_the_roots_fails():
    text = STANDARD.read_text(encoding="utf-8")
    added = (
        "### A rule nobody checks\n\nIt holds.\n\n"
        "Enforced by: `scripts/no-such-check.py`, `Makefile`\n\n"
    )
    broken = text.replace("## Docs\n", "## Docs\n\n" + added, 1)
    assert uncited(broken) == [
        "Docs / A rule nobody checks: cites no file under scripts/, .github/, features/, testing/"
    ]


def test_a_standard_with_a_part_missing_fails():
    text = STANDARD.read_text(encoding="utf-8")
    broken = text.replace("## Feature map\n", "## Feature list\n", 1)
    assert "no rules in part Feature map" in uncited(broken)


def test_a_standard_with_no_version_tag_fails():
    text = STANDARD.read_text(encoding="utf-8")
    broken = text.replace("`repo-standard-vN`", "`v1`")
    assert uncited(broken) == ["Versions does not name repo-standard-vN"]
    dropped = text.replace("### A breaking change takes a new version", "### Changes")
    assert uncited(dropped) == ["no rule A breaking change takes a new version in part Versions"]


def test_the_makefile_and_the_ci_part_name_what_a_pull_request_runs():
    targets = pull_request_targets(WORKFLOW.read_text(encoding="utf-8"))
    assert targets == {"lint", "test"}
    assert makefile_says(MAKEFILE.read_text(encoding="utf-8")) == targets
    assert ci_part_says(STANDARD.read_text(encoding="utf-8")) == targets


def test_a_makefile_that_says_check_fast_runs_on_a_pull_request_fails():
    wrong = "# The check. CI runs it on main, and `make check-fast` on a pull request.\n\nall:\n"
    assert makefile_says(wrong) == {"check-fast"}
