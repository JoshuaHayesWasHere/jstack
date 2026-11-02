"""The ketchup skill's block prints jbus's list of what waits on the user, and says so where jbus is
not installed. `features/home/tests/test_home_needs.py` runs it with jbus holding a gate."""

from skill_blocks import block, home, outside, repo, run

__all__ = ["home", "outside", "repo"]


def test_ketchup_says_so_where_jbus_is_not_installed(repo, home):
    body = block("ketchup", "jbus needs")
    said = run(body, repo, home, before="PATH=/usr/bin:/bin\n")
    assert said == ["no list: jbus is not installed here, so what waits on the user is not known"]
