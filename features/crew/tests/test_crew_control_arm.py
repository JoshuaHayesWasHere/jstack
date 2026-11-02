"""crew-router-pilot: the first line jbus launches a crew with loads its arm's priming. A trimmed
row's `/crew <slug>` expands the SKILL.md the layout holds, and a control row's line names the
control copy of today's priming, whose every side file is in the layout."""

import re
from pathlib import Path

from jbus import priming, queue
from testing.layouts import assembled
from testing.paths import REPO


def placed(line):
    """The layout file a control row's first line tells the thread to read."""
    (named,) = re.findall(r"`(~/\.claude/skills/[^`]+)`", line)
    return assembled() / named.removeprefix("~/.claude/")


def test_a_trimmed_crew_is_told_the_slash_command_that_expands_the_trimmed_skill():
    assert priming.first_line(queue.CREW, "alpha", priming.TRIMMED) == "/crew alpha"
    loaded = assembled() / "skills" / "crew" / "SKILL.md"
    assert loaded.read_bytes() == (REPO / "features" / "crew" / "SKILL.md").read_bytes()


def test_a_control_crew_reads_todays_priming_and_each_side_file_it_names():
    line = priming.first_line(queue.CREW, "alpha", priming.CONTROL)
    copy = placed(line)
    text = copy.read_text()
    assert text == (REPO / "features" / "crew" / "control" / "crew.md").read_text()
    assert "## Telling the home" in text and "## Stay on the pull request" in text
    named = re.findall(r"`\$T/\.\./(skills/crew/[^`]+\.md)`", text)
    assert "skills/crew/control/do-the-task.md" in named
    assert "skills/crew/do-the-task.md" not in named
    for path in named:
        assert Path(assembled() / path).is_file(), path
    assert "`$T/a-fault-outside.md`" in (assembled() / named[0]).read_text()
