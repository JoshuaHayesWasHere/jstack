"""A skill keeps a spine: its SKILL.md stays within `CAP` lines, and a long section moves to a
file beside it that one trigger line in the SKILL.md says to read now. One level deep: a side
file holds no trigger line of its own."""

import pytest

from test_home_thread import NAMED, named
from testing.paths import REPO, skills

CAP = 400
ROLES = REPO / "skills"
OVER = {ROLES / "handoff"}
SKILLS = [folder / "SKILL.md" for folder in skills().values()]
SIDES = sorted(side for skill in SKILLS for side in skill.parent.glob("*.md") if side != skill)


def ids(path):
    return f"{path.parent.name}/{path.name}"


@pytest.mark.parametrize("skill", SKILLS, ids=ids)
def test_a_skill_md_stays_within_the_cap_or_is_on_the_allowlist(skill):
    lines = len(skill.read_text().splitlines())
    if skill.parent in OVER:
        assert lines > CAP, f"{ids(skill)} is within {CAP} lines now: take it off OVER"
    else:
        assert lines <= CAP, f"{ids(skill)} has {lines} lines: move a long section beside it"


def test_every_skill_on_the_allowlist_is_there():
    assert sorted(OVER - {skill.parent for skill in SKILLS}) == []


@pytest.mark.parametrize("side", SIDES, ids=ids)
def test_a_side_file_is_named_by_one_trigger_line(side):
    assert named(side.parent / "SKILL.md").count(side) == 1


@pytest.mark.parametrize("side", SIDES, ids=ids)
def test_a_side_file_holds_no_trigger_line(side):
    assert [line for line in side.read_text().splitlines() if NAMED.search(line)] == []
