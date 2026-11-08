"""A skill's SKILL.md stays within its cap, a `size` rule of `.repo-standard.yml` that
`test_module_size.py` runs. A long section moves to a file beside the SKILL.md, and one trigger
line in the SKILL.md says to read that file now. That is jstack's extension, and this file holds
it. The nesting is one level deep: a side file holds no trigger line of its own."""

import pytest

from test_home_thread import NAMED, named
from testing.paths import skills

SKILLS = [folder / "SKILL.md" for folder in skills().values()]
SIDES = sorted(
    side
    for skill in SKILLS
    for side in skill.parent.glob("*.md")
    if side != skill and side.name != "verify.md"
)


def ids(path):
    return f"{path.parent.name}/{path.name}"


@pytest.mark.parametrize("side", SIDES, ids=ids)
def test_a_side_file_is_named_by_one_trigger_line(side):
    assert named(side.parent / "SKILL.md").count(side) == 1


@pytest.mark.parametrize("side", SIDES, ids=ids)
def test_a_side_file_holds_no_trigger_line(side):
    assert [line for line in side.read_text().splitlines() if NAMED.search(line)] == []
