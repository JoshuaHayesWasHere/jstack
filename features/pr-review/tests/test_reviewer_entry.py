"""A reviewer starts as `/pr-review run <slug> <n>`, and Claude Code expands the whole of SKILL.md
into its first message. So SKILL.md is the reviewer's entry, and the launcher's text sits in
`launching.md`, the file a launcher is told to read, by SKILL.md and by the crew skill's launch."""

import re
import subprocess
import textwrap

from test_home_merge import FENCED
from testing.paths import REPO

SKILL = REPO / "features" / "pr-review" / "SKILL.md"
LAUNCHING = SKILL.parent / "launching.md"
CREW = REPO / "features" / "crew" / "the-review.md"


def expanded():
    """What `/pr-review run` loads: the skill's body, with no front matter."""
    return SKILL.read_text().split("\n---\n", 1)[1]


def lines(text):
    return {line.strip() for line in text.splitlines() if len(line.strip()) > 30}


def test_the_reviewer_s_first_load_holds_none_of_the_launcher_s_text():
    first = expanded()
    assert lines(first) & lines(LAUNCHING.read_text()) == set()
    for heading in (
        "Which part this thread plays",
        "The brief's `Review:` line",
        "What a review covers",
    ):
        assert f"## {heading}\n" not in first
    assert "\n## The reviewer\n" in first
    assert '"/pr-review run <slug> scoped "*)' in first


def test_the_crew_s_launch_reads_the_launcher_s_text_in_the_file_it_names():
    (said,) = [
        line
        for line in CREW.read_text().splitlines()
        if "what a reviewer does with its number" in line
    ]
    (name,) = re.findall(r"`\$T/\.\./skills/pr-review/([^`]+)`", said)
    text = (SKILL.parent / name).read_text()
    assert "## Which part this thread plays\n" in text
    assert "the message `/pr-review run <slug> <n>`" in text
    (read,) = [b for b in FENCED.findall(text) if b.strip().startswith("awk '/^Review:/")]
    brief = "# a-task\nTask: `Review: review` inside the task counts for nothing\nReview: none\n"
    said = subprocess.run(
        ["sh", "-c", textwrap.dedent(read).replace('"$H/tasks/<slug>.md"', "/dev/stdin")],
        input=brief,
        capture_output=True,
        text=True,
        check=True,
    )
    assert said.stdout == "none\n"
