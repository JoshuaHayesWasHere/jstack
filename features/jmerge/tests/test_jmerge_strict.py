"""Main's ruleset is strict (`strict_required_status_checks_policy`, 2026-11-04): GitHub merges
no pull request whose head lacks main's tip, whenever its check started. So a head is behind
whenever main's tip is not its ancestor, and it goes through the one-at-a-time update-branch line
rather than to `gh pr merge`, which would refuse it and leave it on `the merge failed` until main
moved again. A head that has main's tip merges with no update."""

import pytest

from jmerge import ready
from test_jmerge_fresh import AFTER, GH, LINES, Kitchen, asked, url

STRICT = GH.replace(
    '        [ "$4 $5" = "--squash --match-head-commit" ] || exit 64\n',
    '        [ "$4 $5" = "--squash --match-head-commit" ] || exit 64\n'
    '        if ! git -C "$ORIGIN" merge-base --is-ancestor refs/heads/main "$6"; then\n'
    '            echo "gh: Head branch is not up to date with the base branch" >&2\n'
    "            exit 1\n"
    "        fi\n",
)
assert STRICT != GH


@pytest.fixture
def kitchen(tmp_path):
    kitchen = Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES, "Makefile": "check:\n"})
    (kitchen.home.stub / "gh").write_text(STRICT)
    return kitchen


def test_strict_a_head_that_lacks_main_s_tip_is_updated_in_line_whenever_its_check_started(
    kitchen,
):
    kitchen.crew("two", 7, {"a.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"b.txt": LINES + "ours\n"})
    tip = kitchen.on_main({"c.txt": "theirs\n"})
    kitchen.checked("two", AFTER)
    kitchen.checked("three", AFTER)
    behind = ready.IN_LINE.format(number=7, base="main")
    assert kitchen.run() == [asked(7, tip), f"wait 8 {url(8)}: {behind}"]
    assert kitchen.updates() == ["7"]
    assert kitchen.calls() == []

    kitchen.updated("two", AFTER)
    first, second = kitchen.run()
    assert first.startswith("merged 7 two ")
    assert second == asked(8, kitchen.tip())
    kitchen.updated("three", AFTER)
    (said,) = kitchen.run()
    assert said.startswith("merged 8 three ")
    assert kitchen.updates() == ["7", "8"]
    assert not any(ready.MERGE_FAILED in line for line in (first, second, said))


def test_strict_a_head_git_cannot_read_waits_and_is_neither_updated_nor_merged(kitchen):
    kitchen.crew("two", 7, {"a.txt": "ours\n" + LINES}, checks=(AFTER,))
    kitchen.pulls["two"]["headRefOid"] = "f" * 40
    kitchen.brief("two", "f" * 40)
    (said,) = kitchen.run()
    assert said.startswith(f"wait 7 {url(7)}: its head could not be merged over today's base (")
    assert (kitchen.updates(), kitchen.calls()) == ([], [])


def test_strict_a_head_that_has_main_s_tip_merges_with_no_update(kitchen):
    kitchen.on_main({"c.txt": "theirs\n"})
    kitchen.crew("two", 7, {"a.txt": "ours\n" + LINES}, checks=(AFTER,))
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ")
    assert kitchen.updates() == []
