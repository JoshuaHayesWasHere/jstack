"""The home skill says which paths `jmerge` guards on one line, `Guarded today: ...`, and that
line is `src/jmerge/guarded.txt`. The list was emptied on 2026-10-12 and the skill went on
naming five paths, so a home told a user their change to `skills/` was held to a stricter
gate that no longer runs."""

import re
from pathlib import Path

from jmerge import ready

REPO = Path(__file__).parent.parent
SKILL = REPO / "skills" / "home" / "SKILL.md"
GUARDED = REPO / "src" / "jmerge" / "guarded.txt"
SAID = re.compile(r"^Guarded today: (.*)\.$", re.MULTILINE)


def said_by_the_skill():
    """The patterns on the skill's `Guarded today:` line: its backticked words, or none."""
    lines = SAID.findall(SKILL.read_text())
    assert len(lines) == 1, f"the home skill has {len(lines)} `Guarded today:` lines, not one"
    if lines[0] == "none":
        return set()
    patterns = re.findall(r"`([^`]+)`", lines[0])
    assert patterns, f"`Guarded today:` is neither `none` nor a list of patterns: {lines[0]}"
    return set(patterns)


def test_the_guarded_list_the_home_skill_gives_is_the_one_jmerge_reads():
    shipped = set(ready.patterns_of(GUARDED.read_text()))
    assert said_by_the_skill() == shipped
