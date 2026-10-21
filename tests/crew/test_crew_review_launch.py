"""The crew skill finds what it launches by, and says whether to launch a reviewer."""

import os
import re
import subprocess
from pathlib import Path

import pytest

from crew.helpers import BRIEF, SKILL, said, with_field
from test_home_thread import as_read
from testing.layouts import assembled


def test_the_skill_it_launches_by_is_found_from_any_repo(tmp_path):
    text = as_read(SKILL)
    (setting,) = [line for line in text.splitlines() if line.startswith("T=")]
    ((path, heading),) = re.findall(r'`(\$T/\S+/SKILL\.md)` "([^"]+)"', text)

    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "crew").symlink_to(assembled() / "skills" / "crew")
    elsewhere = tmp_path / "another-repo"
    elsewhere.mkdir()
    found = subprocess.run(
        ["sh", "-c", f'{setting}\nprintf %s "{path}"'],
        capture_output=True,
        env={**os.environ, "HOME": str(user)},
        cwd=elsewhere,
        check=True,
    )
    assert f"## {heading}" in Path(found.stdout.decode()).read_text().splitlines()


@pytest.mark.parametrize(
    ("brief", "mode", "launches"),
    [
        (BRIEF, "review", True),
        (with_field("Review: review"), "review", True),
        pytest.param(
            with_field("Review: review+test"),
            "review",
            True,
            id="a word from before the review ran no test step is read as a review",
        ),
        (with_field("Review: none"), "none", False),
        (with_field("Review: something else"), "review", True),
        pytest.param(
            with_field("Review: review") + "Review: none\n",
            "review",
            True,
            id="only the first Review line is the brief's",
        ),
        (with_field("Review: none") + "Review: review\n", "none", False),
        (BRIEF + "Reviewer: mcp:1111-aaaa\n", "review", False),
        (BRIEF + "Reviewer: none, no launch tool in this session\n", "review", False),
        (BRIEF + "\n## Review\nVerdict: clean\n", "review", False),
        (with_field("Review: review+test") + "Reviewer: mcp:1111-aaaa\n", "review", False),
        (
            with_field("Review: none") + "Reviewer: none, the brief says Review: none\n",
            "none",
            False,
        ),
    ],
)
def test_the_check_before_a_launch_prints_the_mode_and_whether_to_launch(
    brief, mode, launches, tmp_path
):
    (line,) = said(tmp_path, "The review", "launch a reviewer", brief)
    printed, what = line.split(": ", 1)
    assert printed == mode
    assert (what == "launch a reviewer") == launches
    assert launches or what.startswith("launch no reviewer, ")
