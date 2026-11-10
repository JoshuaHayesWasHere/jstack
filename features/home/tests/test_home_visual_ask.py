"""A visual a home draws restates the ask, is looked at, and is handed over (po-home-visual-ask).

In one week the user corrected 7 of a home's visuals: "I wanted six more in-depth flow diagrams",
"i want this to be top down, not horizontal", "how can i open this in my broswer? give the url".
The fix is three rules where every home reply reads them: in "How a turn ends", which a home
reads at its start. The test takes a home's start as `jbus.telemetry.firstload` counts it, the
files `ROLES` names and the check that `make lint` runs, and asserts that each rule is in that
start and that the start still fits its budget, so a rule moved to a file a home reads later, or
a start grown past its budget, fails here.
"""

import re

import pytest

from jbus.telemetry import firstload
from testing.paths import REPO

RULES = {
    "restates the ask": (
        r"A visual opens with one line of what it shows and its shape, "
        r"in the user's words of the ask"
    ),
    "looks before it shows": (
        r"Before it shows a visual, this home looks at its render, "
        r"the preview's picture, and redraws"
    ),
    "ends with its path": r"A reply with a visual ends with its file's path",
}


def a_homes_start():
    """The text a home reads at its start, file by file, as the first-load check counts it."""
    files = firstload.ROLES["home"][1]
    return "".join((REPO / name).read_text() for name in files)


@pytest.mark.parametrize("rule", RULES)
def test_a_homes_start_holds_the_visual_rule(rule):
    ends = re.search(r"^## How a turn ends\n(.*?)(?=^## )", a_homes_start(), re.M | re.S)
    assert ends, "a home's start lost its 'How a turn ends' section"
    assert re.search(RULES[rule], ends.group(1)), f"'How a turn ends' lost: {rule}"


def test_a_homes_start_with_the_visual_rules_fits_its_budget():
    start = firstload.starts(REPO)["home"]
    assert not start.missing
    assert [
        fault for fault in firstload.faults({"home": start}) if "over its budget" in fault
    ] == []
