"""crew-router-pilot: a trimmed scout row's `/scout <slug>` expands the SKILL.md the layout holds,
and a control row's first line names the control copy of today's priming in the jstack source."""

import re
from pathlib import Path

from jbus import priming, queue
from testing.layouts import assembled
from testing.paths import REPO


def test_a_trimmed_scout_is_told_the_slash_command_that_expands_the_trimmed_skill():
    assert priming.first_line(queue.SCOUT, "alpha", priming.TRIMMED) == "/scout alpha"
    loaded = assembled() / "skills" / "scout" / "SKILL.md"
    assert loaded.read_bytes() == (REPO / "features" / "scout" / "SKILL.md").read_bytes()


def test_a_control_scout_reads_todays_priming():
    line = priming.first_line(queue.SCOUT, "alpha", priming.CONTROL)
    (named,) = re.findall(r"Read `([^`]+)`", line)
    text = Path(named).read_text()
    assert text == (REPO / "features" / "scout" / "control" / "scout.md").read_text()
    assert "## Report" in text and "Read `$T/scout-report.md` now." in text
