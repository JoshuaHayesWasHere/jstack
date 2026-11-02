"""The ketchup skill's block prints jbus's list of what waits on the user, and says so where jbus is
not installed. `features/home/tests/test_home_needs.py` runs it with jbus holding a gate."""

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
