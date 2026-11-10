"""A visual a home draws restates the ask, is looked at, and is handed over (po-home-visual-ask).

In one week the user corrected 7 of a home's visuals: "I wanted six more in-depth flow diagrams",
"i want this to be top down, not horizontal", "how can i open this in my broswer? give the url".
The home skill's "How a turn ends", which every home reply reads, now holds three rules for a
visual: it opens with the ask in the user's words and its shape, the home looks at its own render
before it shows it, and the reply ends with the file's path. The test reads that section as an
agent reads it and fails when any of the three is gone.
"""

import re

import pytest

from test_home_thread import as_read
from testing.paths import skills

SKILL = skills()["home"] / "SKILL.md"
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


def how_a_turn_ends():
    ends = re.search(r"^## How a turn ends\n(.*?)(?=^## )", as_read(SKILL), re.M | re.S)
    assert ends, "the home skill lost its 'How a turn ends' section"
    return ends.group(1)


@pytest.mark.parametrize("rule", RULES)
def test_how_a_turn_ends_holds_the_visual_rule(rule):
    assert re.search(RULES[rule], how_a_turn_ends()), f"'How a turn ends' lost: {rule}"
