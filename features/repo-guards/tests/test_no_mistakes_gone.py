"""jstack calls no-mistakes nowhere, and its code does not name it.

A pull request's review is pstack's (`features/pr-review/SKILL.md`, "The review"), and no
reviewer runs a test step. So the text an agent reads holds none of the three names of the
old path. The code, the project file and the tests hold the first name nowhere but in this
file, which has to spell it to look for it: `jgauge run` and the sweep of a `no-mistakes`
remote are removed.
"""

import subprocess
from pathlib import Path

from testing.paths import REPO

READ = ("skills", "templates", "playbooks", "docs", "README.md")
GONE = ("no-mistakes", "review+test", "full run: reviewer")

CODE = ("src", "tests", "pyproject.toml")


def named(repo=REPO):
    found = []
    for top in READ:
        for path in sorted([repo / top, *(repo / top).rglob("*")]):
            if not path.is_file():
                continue
            for line in path.read_text(errors="ignore").splitlines():
                if any(name in line.lower() for name in GONE):
                    found.append((str(path.relative_to(repo)), line.strip()))
    return found


def test_the_text_an_agent_reads_names_the_old_path_nowhere_else():
    assert [f"{file}: {line[:90]}" for file, line in named()] == []


def test_the_code_the_project_file_and_the_tests_do_not_name_it():
    """Only what the repo tracks is read: a compiled file holds its checkout's own path."""
    here = str(Path(__file__).relative_to(REPO))
    listed = subprocess.run(
        ["git", "ls-files", "--", *CODE], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert here in listed
    found = [
        f"{file}: {line[:90]}"
        for file in listed
        if file != here and (REPO / file).is_file()
        for line in (REPO / file).read_text(errors="ignore").splitlines()
        if GONE[0] in line.lower()
    ]
    assert found == []


def test_the_search_finds_a_name_in_each_place_it_reads_and_in_no_other(tmp_path):
    planted = {
        "skills/deep/down/SKILL.md": "  Start a No-Mistakes run.",
        "templates/brief.md": "Review: review | none | review+test",
        "playbooks/plan.md": "its notes say `Full run: reviewer`",
        "docs/flow.html": "<b>One no-mistakes run</b>",
        "README.md": "runs one no-mistakes run",
        "src/jgauge/cli.py": "what a no-mistakes run cost",
    }
    for name, line in planted.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(f"a line with none of the names\n{line}\n")
    read = [name for name in planted if name.split("/")[0] in READ]
    assert sorted(named(tmp_path)) == sorted((name, planted[name].strip()) for name in read)
    assert len(read) == len(READ) == 5
