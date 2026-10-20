"""The home's launch check names each brief out whose `Where:` meets the task's, and holds
nothing for it: the second pull request to merge rebases. It is the block of the home skill,
run as a home runs it, over `jmerge --claims` against a fake `gh` and a temporary state
directory."""

import pytest

from test_claims import Claims, result
from test_home_merge import Home, block, paths

PULLS = "https://example.test/pull/{}"
SHARED = "`src/jmerge/cli.py`, `docs/jmerge.md`, one test file under `tests/`"


def check(claims, slug="task"):
    script = f"{paths()}\n{block('overlaps ').replace('<slug>', slug)}"
    said = claims.home.sh(script)
    assert claims.home.stderr == ""
    return said


@pytest.fixture
def claims(tmp_path):
    return Claims(Home(tmp_path))


def test_two_briefs_out_on_the_task_s_file_are_each_named_and_hold_nothing(claims):
    claims.write("task", thread=False, where="`src/jmerge/cli.py` and `skills/home/`")
    claims.write("alpha", where=SHARED)
    claims.write("beta", result=result(PULLS.format(82)), where="`src/jmerge/` (the cli)")
    claims.open(82)
    said = check(claims)
    assert claims.home.code == 0
    assert sorted(said[:-1]) == [
        "overlaps alpha (out) on `src/jmerge/cli.py`: the second to merge rebases",
        "overlaps beta (#82) on `src/jmerge/cli.py`: the second to merge rebases",
    ]
    assert said[-1].startswith("go: ")


def test_a_brief_on_other_files_or_not_launched_is_not_named(claims):
    claims.write("task", thread=False, where="`skills/home/SKILL.md`")
    claims.write("alpha", where="`src/jbus/`")
    claims.write("beta", thread=False, where="`skills/home/SKILL.md`")
    claims.write("gamma", where="`skills/home/`, `docs/`")
    said = check(claims)
    assert said == [
        "overlaps gamma (out) on `skills/home/SKILL.md`: the second to merge rebases",
        said[-1],
    ]
    assert said[-1].startswith("go: ")


def test_a_task_with_no_brief_on_disk_waits_and_names_no_go(claims):
    claims.write("alpha", where="`src/jmerge/cli.py`")
    said = check(claims)
    assert said == [
        "wait: jmerge --claims has no line for task: write its brief first, then run this again"
    ]
