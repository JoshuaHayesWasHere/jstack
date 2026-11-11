"""Every place jbus once fell back to the root home for a row with no home of its own falls back to
the catch-all, `uncategorized`, instead: the root home owns no row. One table runs each default in
a repo's state with one live scope, `flow`, and reads the home it gives through
`jbriefs.home.home_of`, the one rule every thread and jbus ask."""

import argparse
from datetime import UTC, date, datetime

import pytest

import jsettings
from jbriefs import home as homes
from jbus import blockers, children, daywarnings, homestatus, needs, queue, reverts, watch
from jbus import home as jhome
from jbus.ci import wrongcloses
from jbus.view import homes as viewed


@pytest.fixture
def state(tmp_path):
    """A repo's state: the root home, with its `home-id`, and one live scope, `flow`."""
    root = tmp_path / "demo"
    (root / "flow").mkdir(parents=True)
    (root / "flow" / "home-id").write_text("mcp:flow\n")
    (root / "flow" / "plan.md").write_text("# demo, flow: plan\n")
    (root / "home-id").write_text("mcp:root\n")
    return root


def _queued_from_no_home(root):
    """`jbus queue add --from ""`: the row is the catch-all's, so its brief is too."""
    text = "# alpha\nHome: uncategorized\n"
    assert queue.owned(root, "demo", "alpha", text, "", None) == ""
    with pytest.raises(queue.Refused, match="the uncategorized home adds it"):
        queue.owned(root, "demo", "alpha", "# alpha\nHome: flow\n", "", None)
    return homes.home_of(root, text)


def _needs_of_a_slug_with_no_brief(root):
    return needs.home_of(root, root, "a-slug-of-no-brief")


def _watch_fix_brief(root):
    text = watch.fix_brief("# x", "fix it", "it is red", ["- it is green"], "it runs", "a run", [])
    return homes.home_of(root, text)


def _day_warnings(root):
    kept = daywarnings.Kept("alpha", "1", "`a.py`:1", "say it", "https://x/pull/1", "2026-11-08")
    return homes.home_of(root, daywarnings.brief("2026-11-08", [kept]))


def _wrong_closes(root):
    start = datetime(2026, 11, 2, tzinfo=UTC)
    text = wrongcloses.request(date(2026, 11, 2), start, start, [], jsettings.DEFAULTS)
    return homes.home_of(root, text)


def _revert_of_a_row_with_no_home(root):
    return homes.home_of(root, f"# revert\nHome: {reverts.home_of_revert('# alpha')}\n")


def _children_watch_key(root):
    (first, *_) = children.watched(root)
    return first


DEFAULTS = {
    "queue add --from empty": _queued_from_no_home,
    "needs.home_of": _needs_of_a_slug_with_no_brief,
    "watch.fix_brief": _watch_fix_brief,
    "daywarnings.brief": _day_warnings,
    "ci/wrongcloses.request": _wrong_closes,
    "reverts.home_of_revert": _revert_of_a_row_with_no_home,
    "children.watch's first key": _children_watch_key,
}


@pytest.mark.parametrize("default", DEFAULTS)
def test_each_default_home_is_the_catch_all_and_never_the_root(state, default):
    assert DEFAULTS[default](state) == homes.catchall(state) != state


def test_the_root_is_watched_under_no_key_of_its_own(state):
    """`stalls.json` once kept the root under `/`: the catch-all is watched in its stead, made or
    not, and each other scope beside it."""
    assert [one.name for one in children.watched(state)] == [homes.UNCATEGORIZED, "flow"]


def test_while_the_root_stands_in_its_clear_and_its_start_read_the_catch_all_s_rows(state):
    """`jbus clear` (`blockers.Directory`) and the home's start (`homestatus.Home`) read a row
    of the catch-all's as the root's while the root stands in for it, a slug of no brief too, and
    as the catch-all's alone once that home has its own `home-id`. The catch-all's own slug,
    which `/handoff` queues an archived scope's gates under, reads the same, though its directory
    is there already for its retry ledger."""
    (state / "tasks").mkdir()
    (state / "tasks" / "alpha.md").write_text("# alpha\nHome: root\n")
    catchall = homes.catchall(state)
    catchall.mkdir()
    (catchall / "blockers.json").write_text("{}\n")

    def views(mine):
        clear = blockers.Directory(state, mine)
        start = homestatus.Home(mine, state, "demo")
        slugs = ("alpha", "no-brief", "home-uncategorized")
        return (*(clear.has(slug) for slug in slugs), start.keeps("tasks", "alpha"))

    assert views(state) == (True, True, True, True)
    assert views(state / "flow") == (False, False, False, False)
    (catchall / "home-id").write_text("mcp:the-catch-all\n")
    assert views(state) == (False, False, False, False)
    assert views(catchall) == (True, True, True, True)


def test_jbus_home_directory_names_the_root_while_it_stands_in_and_the_catch_all_after(
    state, capsys
):
    """`jbus home --directory` of a brief no scope claims prints the directory of the home that
    works it (`jbus.home`): the root's while it stands in, and the catch-all's once that home has
    a thread of its own."""
    (state / "tasks").mkdir()
    brief = state / "tasks" / "alpha.md"
    brief.write_text("# alpha\nHome: root\n")
    catchall = homes.catchall(state)
    (verb,) = jhome.VERBS
    parser = argparse.ArgumentParser()
    verb.arguments(parser)

    def directory():
        assert verb.run(parser.parse_args(["--directory", str(brief)]), None) == 0
        return capsys.readouterr().out.strip()

    assert directory() == str(state)
    catchall.mkdir()
    (catchall / "home-id").write_text("mcp:the-catch-all\n")
    assert directory() == str(catchall)


def test_the_view_reads_the_catch_all_as_a_home_and_the_root_s_line_while_it_stands_in(state):
    """`jbus.view.homes`: a brief that names a retired scope is the catch-all's and says the
    name, a row of no brief is the catch-all's, the root works the catch-all's rows while it
    stands in, a gate of the catch-all's directory is its, and the summary draws the root, then
    the catch-all, then each other scope, with the catch-all's health `none` while the root
    stands in for it."""
    found = viewed.Homes(state, state)
    assert found.owner("# x\nHome: old-shelf\n") == viewed.Owner(viewed.CATCHALL, "old-shelf")
    assert found.of_key("no-brief", {}, {"no-brief"}) == viewed.CATCHALL
    assert found.works(viewed.ROOT) == {viewed.ROOT, viewed.CATCHALL}
    assert found.of_gate(viewed.CATCHALL) == viewed.CATCHALL
    assert found.of_gate("gone") == viewed.ROOT
    assert list(found.colours) == [viewed.ROOT, viewed.CATCHALL, "flow"]
    group = found.group([], [])
    assert [(one["name"], one["health"]) for one in group] == [
        (viewed.ROOT, "unknown"),
        (viewed.CATCHALL, "none"),
        ("flow", "unknown"),
    ]
