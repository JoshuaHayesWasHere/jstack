"""No file under `features/` sends a thread to a home's `notes.md`.

The user's word (2026-10-28): "We need to just diverge from notes.md and this pattern of adding
things here rather than fixing them outright." A line in that file was a shortcut: written instead
of a fix, then forgotten. Each fact it held lives where code reads it: the check command in
`$H/fresh-check`, the generated files in jbus's `[[project]]` key `generated`, a scope's slug
prefix in `$H/<scope>/prefix`, and a rule in a queued row that codes it.

So no skill, playbook, doc or source file under `features/` names `notes.md`. The tests and the
recorded evals under `features/evals/evals/` are data about the past and are not read.
"""

import subprocess

from testing.paths import REPO

READ_SET = ("features/",)
NAME = "notes.md"


def naming(repo=REPO):
    """Each tracked file under `features/` that names the file, but for tests and recorded evals."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "features"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    return [
        file
        for file in listed
        if file
        and "/tests/" not in file
        and not file.startswith("features/evals/evals/")
        and (repo / file).is_file()
        and NAME in (repo / file).read_text(errors="ignore")
    ]


def test_no_file_under_features_names_the_notes():
    assert naming() == []


def test_the_search_finds_a_planted_name_and_skips_tests_and_evals(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    planted = {
        "features/crew/SKILL.md": "Read `$H/notes.md`.",
        "features/crew/tests/test_x.py": "notes.md",
        "features/evals/evals/run/answers.json": "notes.md",
        "features/crew/a-conflict.md": "no such name here",
    }
    for name, text in planted.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(f"{text}\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert naming(tmp_path) == ["features/crew/SKILL.md"]
