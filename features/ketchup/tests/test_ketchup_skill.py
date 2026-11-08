"""The ketchup skill's block prints jbus's list of what waits on the user, and says so where jbus is
not installed. In a home it asks for that home's list alone, of the home's own project; outside one,
for every project's. `features/home/tests/test_home_needs.py` runs it with jbus holding a gate."""

import pytest

from skill_blocks import block, home, outside, repo, run

__all__ = ["home", "outside", "repo"]


NO_LIST = "no list: jbus is not installed or set up here, so what waits on the user is not known"


def test_ketchup_says_so_where_jbus_is_not_installed(repo, home):
    body = block("ketchup", "jbus needs")
    assert run(body, repo, home, before="PATH=/usr/bin:/bin\n") == [NO_LIST]


def test_ketchup_says_so_where_jbus_refuses(repo, home, tmp_path):
    jbus = tmp_path / "jbus"
    jbus.write_text("#!/bin/sh\necho 'refused: no config' >&2\nexit 1\n")
    jbus.chmod(0o755)
    body = block("ketchup", "jbus needs")
    assert run(body, repo, home, before=f"PATH={tmp_path}:/usr/bin:/bin\n") == [NO_LIST]


THREAD = "thread-sc"


@pytest.fixture
def jbus_says(tmp_path):
    """A `jbus` that prints the arguments it was given, one line."""
    made = tmp_path / "bin"
    made.mkdir()
    (made / "jbus").write_text('#!/bin/sh\necho "jbus $*"\n')
    (made / "jbus").chmod(0o755)
    return f"PATH={made}:/usr/bin:/bin\n"


def asked(repo, home, before, thread):
    body = block("ketchup", "jbus needs").replace("<threadId>", thread)
    return run(body, repo, home, before=before)


@pytest.mark.parametrize("scope", ["", "sc"], ids=["the root home", "a scoped home"])
def test_in_a_home_ketchup_asks_for_that_homes_list_of_its_own_project(
    repo, home, jbus_says, scope
):
    state = home / ".local" / "state" / "home" / "demo"
    (state / "sc").mkdir(parents=True)
    (state / "home-id").write_text("thread-root\n")
    (state / "sc" / "home-id").write_text(f"{THREAD}\n")
    mine = state / scope if scope else state
    thread = THREAD if scope else "thread-root"
    assert asked(repo, home, jbus_says, thread) == [f"jbus --project demo needs --home {mine}"]


@pytest.mark.parametrize("thread", ["<threadId>", "", "no-home-of-demo"])
def test_outside_a_home_ketchup_asks_for_every_projects_list(repo, home, jbus_says, thread):
    (home / ".local" / "state" / "home" / "demo").mkdir(parents=True)
    assert asked(repo, home, jbus_says, thread) == ["jbus needs"]
