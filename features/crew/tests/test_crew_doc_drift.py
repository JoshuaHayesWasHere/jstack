"""Rules of the crew skill that name what jbus's code does, checked against that code."""

import re

from jbriefs import below
from jbus import party
from testing.paths import REPO

READ_SET = ("features/crew/*.md",)
CREW = REPO / "features" / "crew"
SKILL = REPO / "features" / "crew" / "SKILL.md"


def test_the_skill_names_each_case_jbus_holds_and_counts_them_right():
    """The cases never done on a default are the ones jbus parks as holding gates
    (`jbus.party.CASES`), no fewer and no other."""
    (line,) = [one for one in SKILL.read_text().splitlines() if "never done on a default" in one]
    named = re.findall(r"\(`([^`]+)`\)", line)
    assert sorted(named) == sorted(party.CASES)
    words = {4: "Four", 5: "Five", 6: "Six", 7: "Seven"}
    assert line.startswith(f"{words[len(party.CASES)]} things only")


def test_each_scoped_reviewer_line_the_skill_asks_for_names_its_head():
    """`jbriefs.below.reviewers` counts a scoped reviewer only for the head its line names after
    `of`, so a line the crew is told to write with no head would count for no head at all."""
    asked = []
    for page in sorted(CREW.glob("*.md")):
        asked += re.findall(r"`Scoped reviewer: <threadId>[^`]*`", page.read_text())
    assert asked
    for line in asked:
        filled = re.sub(r"<[^>]*>", "x", line.strip("`")).replace("of x", f"of {'c' * 40}")
        brief = f"\n## Result\nStatus: done\n{filled}\n"
        assert below.reviewers(brief, "Scoped reviewer", "c" * 40), line
