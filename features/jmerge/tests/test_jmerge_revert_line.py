"""A revert jbus opened for a red main (`jmerge.reverts`) is the first pull request in `jmerge`'s
line, whatever its number. It branches from main's tip, the newest pull request there is, so by
number it lined up last: on a red main other pull requests keep merging (#862), each moved main
past the revert's check, and the revert waited a turn behind every one of them. Now it takes the
line from the pull request that holds it, which waits behind the revert and keeps its record of
the update GitHub was asked for. Every other pull request lines up as before, migrations in their
declared order."""

import json

import pytest

from jmerge import rejudge, reverts
from test_jmerge_fresh import AFTER, LINES, Kitchen, asked, url
from test_jmerge_in_line import behind
from test_jmerge_order import BETA_URL, DIRECTORY, GAMMA_URL, pulls, queue_of, starts, three_in_line


def named(state, *opened):
    """`reverts.json` in jbus's `state`, naming each `(branch, url)` as a revert jbus opened."""
    kept = {}
    for n, (branch, pull) in enumerate(opened):
        made = reverts.Revert(f"{n}" * 40, f"culprit-{n}", branch, "f" * 40, pull)
        kept[made.red] = reverts.record(made)
    (state / reverts.NAME).write_text(json.dumps(kept))


@pytest.fixture
def lined(merged):
    return three_in_line(merged)


@pytest.fixture
def kitchen(tmp_path):
    files = {"a.txt": LINES, "b.txt": LINES, "c.txt": LINES, "d.txt": LINES}
    kitchen = Kitchen(tmp_path, {**files, "Makefile": "check:\n"})
    kitchen.jbus = queue_of(kitchen.home, []).parent
    return kitchen


def test_a_revert_main_moved_past_is_updated_first_and_the_others_wait_behind_it(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    kitchen.crew("revert-it", 9, {"a.txt": "ours\n" + LINES})
    named(kitchen.jbus, ("revert-it", url(9)))
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(9, tip), behind(7, 9), behind(8, 9)]
    assert kitchen.updates() == ["9"]

    kitchen.updated("revert-it", AFTER)
    first, second, third = kitchen.run()
    assert first.startswith("merged 9 revert-it ")
    assert (second, third) == (asked(7, kitchen.tip()), behind(8, 7))


def test_a_revert_takes_the_line_from_the_one_that_holds_it_which_keeps_its_record(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    held = json.loads((kitchen.home.state / rejudge.NAME).read_text())["7"]
    assert held["line"] is True

    kitchen.crew("revert-it", 9, {"a.txt": "ours\n" + LINES})
    named(kitchen.jbus, ("revert-it", url(9)))
    kitchen.on_main({"d.txt": "theirs again\n"})
    tip = kitchen.tip()
    assert kitchen.run() == [asked(9, tip), behind(7, 9), behind(8, 9)]
    assert kitchen.updates() == ["7", "9"]
    kept = json.loads((kitchen.home.state / rejudge.NAME).read_text())
    assert kept["7"] == {**held, "line": False}
    assert kept["9"]["line"] is True


def test_a_pull_request_reverts_json_does_not_name_lines_up_by_number_as_before(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    named(kitchen.jbus, ("revert-gone", url(5)))
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]


def test_a_revert_comes_before_the_migrations_which_keep_their_declared_order(lined):
    state = queue_of(lined.home, [], DIRECTORY).parent
    pulls(lined.home)
    assert starts(lined.run("--check")) == ["ready 7", "wait 8", "ready 9"]
    named(state, ("gamma", GAMMA_URL))
    said = lined.run("--check")
    assert starts(said) == ["ready 9", "ready 7", "wait 8"]


def test_two_reverts_line_up_by_number_ahead_of_the_rest(lined):
    state = queue_of(lined.home, [], DIRECTORY).parent
    pulls(lined.home)
    named(state, ("gamma", GAMMA_URL), ("beta", BETA_URL))
    assert starts(lined.run("--check")) == ["ready 8", "ready 9", "ready 7"]
