"""The crew, pr-review and scout skills read a brief's Result lines through `jbriefs line`: the
pull request on a `Branch:` line, the review seats, `Reviewer:`, `Stacked on:`, `Checked:` and
`Status:`. No awk or sed program in their files reads one of those lines with a field or a
pattern of its own, so a block gives the answer jbriefs, jmerge and jbus give (the st-implicit-pkgs
scout, finding 1).

The tests read the files as they are written and run two blocks as an agent runs them, over
copies of real briefs (`features/jbriefs/tests/fixtures/result_lines`)."""

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

from crew_helpers import block
from jbriefs import cli
from test_home_thread import blocks
from testing.paths import REPO

SKILLS = ("crew", "pr-review", "scout")
LINES = re.compile(r"Branch:|Pull request|Stacked on|Checked:|Status:|Reviewer|reviewer:|By:")
PROGRAM = re.compile(r"\b(?:awk|sed)\b[^'\n]*'(.*?)'", re.S)
OTHER = {
    ("crew/a-second-pass.md", "reviewer:"): "the head a `Scoped reviewer:` line names, not a seat",
    ("crew/the-review.md", "Reviewer"): "whether the crew wrote its own `Reviewer: none` line once",
    ("pr-review/SKILL.md", "By:"): "a reviewer finding its own section by the `By:` it printed",
    ("pr-review/the-review.md", "Pull request"): "the head, `Task:` to `Pull request:`",
}
"""The programs left that name one of the labels, each for another question than what the line
says of the Result: none of them is a reader of the pull request, a seat, a reviewer launched,
the stack, the check or the status."""
CALLERS = {
    "crew/SKILL.md": "jbriefs line status,pr",
    "crew/no-pr-end.md": "jbriefs line status,pr",
    "crew/stay-on-the-pr.md": "jbriefs line status",
    "crew/a-conflict.md": "jbriefs line stacked",
    "crew/a-link-that-moved.md": "jbriefs line reviewing",
    "crew/the-review.md": "jbriefs line reviewed",
    "crew/do-the-task.md": "jbriefs line base",
    "crew/templates/proved.sh": "jbriefs line base",
    "pr-review/launching.md": "jbriefs line status,pr,reviewed",
    "pr-review/SKILL.md": "jbriefs line base",
    "scout/SKILL.md": "jbriefs line status",
}
BRIEFS = REPO / "features" / "jbriefs" / "tests" / "fixtures" / "result_lines"


def files():
    for skill in SKILLS:
        root = REPO / "features" / skill
        for path in sorted(root.rglob("*")):
            if path.is_file() and "tests" not in path.parts and path.suffix in (".md", ".sh"):
                yield path.relative_to(REPO / "features").as_posix(), path.read_text()


def test_no_awk_or_sed_program_reads_a_result_line_of_its_own():
    found = {
        (name, label)
        for name, text in files()
        for program in PROGRAM.findall(text)
        for label in LINES.findall(program)
    }
    assert found == set(OTHER)


CALL = re.compile(r"jbriefs line ([a-z,]+)")


@pytest.mark.parametrize(("name", "call"), CALLERS.items())
def test_each_block_the_scout_listed_calls_jbriefs_line_with_lines_it_reads(name, call, capsys):
    text = (REPO / "features" / name).read_text()
    assert call in text
    for what in CALL.findall(text):
        assert cli.main(["line", what, str(BRIEFS / "po-scout-model-doc.md")]) == 0, what
        (said,) = capsys.readouterr().out.splitlines()
        assert all(said.split("\t")), (what, said)


def settle(tmp_path, status):
    (found,) = [one for one in blocks("scout") if "jbriefs line status" in one]
    (tmp_path / "scouts").mkdir(exist_ok=True)
    (tmp_path / "scouts" / "alpha.md").write_text(
        f"# alpha: a question\n\n## Report\nStatus: {status}\nAnswers: one\n"
    )
    ran = subprocess.run(
        ["sh", "-c", found],
        capture_output=True,
        text=True,
        env={**os.environ, "H": str(tmp_path), "S": "alpha"},
        check=True,
    )
    return ran.stdout.strip()


@pytest.mark.parametrize(
    ("status", "said"),
    [
        ("done", "settle"),
        ("done.", "settle"),
        ("done (both ran the same cases)", "settle"),
        ("done, mostly", "stay: the Report does not say Status: done"),
        ("not done", "stay: the Report does not say Status: done"),
    ],
)
def test_the_scout_settles_on_the_status_jbriefs_reads(tmp_path, status, said):
    assert settle(tmp_path, status) == said


def test_a_crew_that_ended_finds_the_pull_request_a_merged_note_follows(tmp_path):
    """statechart-tmp-cleanup's last Result names #679 with `(merged)` after it: the End
    block's `$(NF)` read the note, found no pull request, and told the home the task ended
    with none."""
    (tmp_path / "tasks").mkdir()
    brief = (BRIEFS / "statechart-tmp-cleanup.md").read_text()
    (tmp_path / "tasks" / "alpha.md").write_text(brief)
    code = textwrap.dedent(block("End", "write the Result first")).replace("<slug>", "alpha")
    ran = subprocess.run(
        ["sh", "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "H": str(tmp_path)},
        check=True,
    )
    assert ran.stdout.startswith(
        "send nothing: https://github.com/JoshuaHayesWasHere/jstack/pull/679 is open"
    )


def test_the_report_names_every_block_it_listed():
    """The report's list, by file: each is a caller above, so none was left out."""
    listed = {
        "crew/SKILL.md",
        "crew/no-pr-end.md",
        "pr-review/launching.md",
        "crew/a-conflict.md",
        "crew/the-review.md",
        "crew/do-the-task.md",
        "crew/templates/proved.sh",
        "scout/SKILL.md",
    }
    assert listed <= set(CALLERS)
    assert all(Path(REPO / "features" / name).is_file() for name in CALLERS)
