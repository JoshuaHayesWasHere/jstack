"""No skill, playbook or doc under `features/` states how many gate cases there are.

The cases are the table of `features/home/templates/gates.md`, and `jbus.party.DOORS` is the same
table in code. A line that counts them ("four things only are never done on a default", "one of
the six cases") goes stale the day a case is added: dc-unslop-scout (2026-11-05) found "four
things" in five skill and playbook files while the table had six. So a line about the gate cases
names `gates.md`, or lists the cases, and gives no number.

A line is about the gate cases when it is in a `gates.md`, or names one, `party.DOORS`, a gate
that holds, what is "never done on a default", or one of the cases word for word, or when a case's
own words from `party.DOORS` match it. It states a count when a number, in words or digits, comes before `things`, `cases`, `doors`
or `gates`, or ends "these <number>". The tests and the recorded evals under
`features/evals/evals/` are data about the past and are not read.
"""

import re
import subprocess

from jbus import party
from testing.paths import REPO

NUMBER = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
COUNT = re.compile(
    rf"\b{NUMBER}\s+(?:gate\s+)?(?:things|cases|doors|gates)\b|\bthese\s+{NUMBER}\b(?!\s+\w)",
    re.I,
)
ABOUT = (
    re.compile(
        r"gates\.md|(?-i:\bDOORS\b)|\bgates? that holds?\b|\bnever (?:done|does) on a default\b",
        re.I,
    ),
    *(re.compile(re.escape(case), re.I) for case in party.CASES),
    *(re.compile(one.named, re.I) for one in party.DOORS if one.named),
)


def counting(repo=REPO):
    """`<file>:<line>` for each Markdown line under `features/` that counts the gate cases, but
    for tests and recorded evals."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "features/*.md"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    found = []
    for file in listed:
        if not file or "/tests/" in file or file.startswith("features/evals/evals/"):
            continue
        path = repo / file
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            about = file.endswith("/gates.md") or any(one.search(line) for one in ABOUT)
            if about and COUNT.search(line):
                found.append(f"{file}:{number}")
    return found


def test_no_line_under_features_counts_the_gate_cases():
    assert counting() == []


def test_the_search_finds_a_planted_count_and_passes_a_named_table(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    planted = {
        "features/crew/SKILL.md": (
            "Four things only are never done on a default: a force-push to a shared branch.\n"
            "One of the cases of `$T/gates.md` holds as above.\n"
        ),
        "features/home/skills/home/SKILL.md": "Pause before four things only: deleting data.\n",
        "features/jbus/docs/jbus/the-queue.md": "A gate that holds is one of the six cases.\n",
        "features/home/templates/gates.md": "The case is one of these six, word for word:\n",
        "features/scout/SKILL.md": "A scout writes three kinds of file and no others.\n",
        "features/jbus/docs/jbus/the-relay.md": "The relay pages in two cases.\n",
        "features/principles/SKILL.md": "It enters through three doors only: raw data.\n",
        "features/crew/tests/fixture.md": "Four things only are never done on a default.\n",
        "features/evals/evals/run/answer.md": "Four things only are never done on a default.\n",
    }
    for name, text in planted.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert counting(tmp_path) == [
        "features/crew/SKILL.md:1",
        "features/home/skills/home/SKILL.md:1",
        "features/home/templates/gates.md:1",
        "features/jbus/docs/jbus/the-queue.md:1",
    ]
