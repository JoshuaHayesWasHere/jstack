"""The sharpen skill walks the open choices in a question form, as a section of grilling says.
This test holds that each section it cites by name is a heading of that skill."""

import re

from testing.paths import REPO

FEATURES = REPO / "features"
SKILL = FEATURES / "sharpen" / "SKILL.md"


def headings(path):
    return {line[3:].strip() for line in path.read_text().splitlines() if line.startswith("## ")}


def test_each_section_sharpen_cites_is_a_heading_of_that_skill():
    cited = re.findall(r'(\w[\w-]*)\'s "([^"]+)"', SKILL.read_text())
    assert ("grilling", "Asking a round") in cited
    for skill, section in cited:
        assert section in headings(FEATURES / skill / "SKILL.md"), (skill, section)
