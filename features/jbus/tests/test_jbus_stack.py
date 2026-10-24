"""A row that builds on an open pull request launches stacked on its branch (`test_jbus_chains`).
Each pass after that keeps the link on its base, and tells its crew to move it, once for each
move:

- When the base's head moves (review fixes, a rebase), the link is told to rebase onto the base's
  branch, once for that head, unless its head already holds the base's.
- When the base merged, jbus bases the link's pull request on main, tells its crew to move its
  own commits onto main, and writes where it sits now on the brief's `Stacked on:` line.
- A link that still sits on its base gets no message to rebase onto main: its branch holds its
  base's commits, which only "A link that moved" leaves out.

The tests run the real pass against the kitchen's fakes of T3 Code and GitHub."""

from datetime import timedelta

import pytest

from jmerge import stacked as stacks
from test_jbus_chains import queue_add
from test_jbus_github import keys, sends
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import brief, go

BASE, LINK, MERGE, LAST = "c" * 40, "b" * 40, "a" * 40, "d" * 40


@pytest.fixture
def stacked(tmp_path, monkeypatch):
    """`one` (#10) is open on its branch `one`, and `two` (#11) builds on it: a pass launched it
    stacked on `one`, and it opened its pull request on that branch. Each thread's turn has
    ended, since jbus tells nothing to a thread that is at work."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    kitchen.word()
    kitchen.config(max_running=8)
    assert queue_add(kitchen, "one")[0] == 0
    assert go(kitchen, "one")[0] == 0
    built = brief("two", "Builds on: one: the table one adds\n")
    assert queue_add(kitchen, "two", "--depends", "one", text=built)[0] == 0
    assert go(kitchen, "two")[0] == 0
    kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.set("open.json", [kitchen.opened("one", 10)])
    kitchen.poll(NOW - timedelta(minutes=27))
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: one", "crew: two"]
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    yield kitchen
    kitchen.close()


def pulls(kitchen, base=BASE, link=LINK, on="one", merged=False, mergeable="MERGEABLE"):
    """Set what GitHub lists: `two` at `link` based on the branch `on`, and `one` at `base`,
    open, or merged as `MERGE` with its last head `LAST`."""
    two = {**kitchen.opened("two", 11), "headRefOid": link, "baseRefName": on}
    two["mergeable"] = mergeable
    if merged:
        kitchen.set("open.json", [two])
        done = {**kitchen.merged("one", 10, MERGE), "headRefOid": LAST}
        kitchen.set("merged.json", [done])
    else:
        kitchen.set("open.json", [{**kitchen.opened("one", 10), "headRefOid": base}, two])


def holds(kitchen, *pairs):
    """Say that the link's head holds the base's head, for each (base head, link head)."""
    kitchen.set("compare.json", {f"{base}...{link}": "ahead" for base, link in pairs})


def passes(kitchen, *minutes):
    for minute in minutes:
        kitchen.poll(NOW + timedelta(minutes=minute))


def head_line(kitchen):
    text = (kitchen.home / "tasks" / "two.md").read_text()
    return stacks.of(text)


def edits(kitchen):
    return [line for line in kitchen.log("gh") if line.startswith("pr edit")]


def test_a_link_whose_head_holds_its_bases_head_is_told_nothing(stacked):
    pulls(stacked)
    holds(stacked, (BASE, LINK))
    passes(stacked, 0, 3)
    assert sends(stacked) == []


def test_a_base_whose_head_moved_tells_its_link_once_for_that_head(stacked):
    moved = "e" * 40
    pulls(stacked, base=moved)
    passes(stacked, 0, 3, 6)
    assert keys(stacked) == [f"restack|two|{LINK[:12]}|{moved[:12]}"]
    (said,) = [given["message"] for given in sends(stacked)]
    assert "moved to eeeeeeeeeeee" in said and "#11" in said
    assert '"A link that moved"' in said and "with one as the branch it sat on" in said

    again = "f" * 40
    pulls(stacked, base=again)
    passes(stacked, 9, 12)
    assert keys(stacked)[1:] == [f"restack|two|{LINK[:12]}|{again[:12]}"]

    rebased = "9" * 40
    pulls(stacked, base=again, link=rebased)
    holds(stacked, (again, rebased))
    passes(stacked, 15, 18)
    assert len(sends(stacked)) == 2
    assert head_line(stacked) == stacks.Stacked("one", "one")


@pytest.mark.parametrize("on", ["one", "main"])
def test_a_base_that_merged_moves_its_link_onto_main_once(stacked, on):
    """GitHub bases the link on main by itself when the base's branch is deleted on its merge.
    Where it has not, jbus does. Either way the crew is told once, with the base's last head as
    the commit its own commits start above, and the brief says where the link sits now."""
    pulls(stacked, merged=True, on=on)
    passes(stacked, 0, 3)
    assert edits(stacked) == (["pr edit 11 --base main"] if on == "one" else [])
    assert keys(stacked) == [f"restack|two|{LINK[:12]}|{MERGE[:12]}"]
    (said,) = [given["message"] for given in sends(stacked)]
    assert "one merged as aaaaaaaaaaaa" in said and "now based on main" in said
    assert f"with {LAST} as the branch it sat on" in said and "again with one" in said
    assert head_line(stacked) == stacks.Stacked("one", "main", MERGE)


def test_a_link_whose_thread_is_at_work_is_moved_on_a_later_pass(stacked):
    pulls(stacked, merged=True)
    for thread in stacked.t3.threads:
        thread["status"] = "running"
    passes(stacked, 0)
    assert sends(stacked) == []
    assert head_line(stacked) == stacks.Stacked("one", "one")
    for thread in stacked.t3.threads:
        thread["status"] = "completed"
    passes(stacked, 3, 6)
    assert keys(stacked) == [f"restack|two|{LINK[:12]}|{MERGE[:12]}"]
    assert head_line(stacked) == stacks.Stacked("one", "main", MERGE)


def test_a_link_that_sits_on_its_base_is_not_told_to_rebase_onto_main_for_a_conflict(stacked):
    pulls(stacked, mergeable="CONFLICTING")
    holds(stacked, (BASE, LINK))
    passes(stacked, 0, 3)
    assert sends(stacked) == []


def test_a_link_github_will_not_rebase_is_told_nothing_and_its_line_stays(stacked):
    pulls(stacked, merged=True)
    (stacked.stub / "gh-edit-refused").write_text("")
    said = stacked.poll(NOW)
    assert "wait two: #11 could not be based on main: gh exited 1" in said
    assert sends(stacked) == []
    assert head_line(stacked) == stacks.Stacked("one", "one")
