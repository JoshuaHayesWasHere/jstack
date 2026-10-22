"""The home's launch check names each brief out whose `Where:` overlaps the task's, and holds no
launch back for it: of the two pull requests, the one that merges second rebases. The test runs the
home skill's block as a home runs it, over `jmerge --claims` against a fake `gh` and a temporary
state directory."""

import os

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
    claims.write("alpha", where="`features/jbus/src/jbus/`")
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


def test_a_durable_scout_with_no_brief_goes(claims):
    (claims.home.state / "scouts").mkdir()
    (claims.home.state / "scouts" / "task.md").write_text("# task: a scout\n")
    claims.write("alpha", where="`src/jmerge/cli.py`")
    said = check(claims)
    assert len(said) == 1 and said[0].startswith("go: ")


def test_a_claims_run_that_fails_part_way_waits_and_shows_no_line(claims, tmp_path):
    claims.write("task", thread=False, where="`src/jmerge/cli.py`")
    stub = tmp_path / "failing"
    stub.mkdir()
    (stub / "uv").write_text(
        "#!/bin/sh\necho 'task not launched root Where: `src/jmerge/cli.py`'\nexit 1\n"
    )
    (stub / "uv").chmod(0o755)
    path = f"{stub}:{claims.home.stub}:{os.environ['PATH']}"
    script = f"{paths()}\n{block('overlaps ').replace('<slug>', 'task')}"
    said = claims.home.sh(script, path=path)
    assert said == ["wait: jmerge --claims did not finish, no overlap was read"]
