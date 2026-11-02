"""A stacked link whose own change has no need of its base's code comes off the stack while the
base is still open: its own commits merge cleanly onto main without the base's, and its added
lines use no name the base introduced. jbus moves those commits onto main, bases its pull request
there and drops its brief's `Stacked on:` line, so `jmerge` no longer waits for the base. A link
that conflicts without its base, or uses a name the base introduced, stays stacked.

The tests run the real pass against the kitchen's fakes of T3 Code and GitHub, over a real git
origin: `one` (#10) is open on its branch, and `two` (#11) is one commit on it."""

from datetime import timedelta

import pytest

from jmerge import ready
from jmerge import stacked as stacks
from test_jbus_kitchen import NOW, asks
from test_jbus_stack import edits, head_line, stacked
from test_jbus_stack_move import commit, git, signed, unmoved

__all__ = ["stacked"]


class OpenStack:
    """`one` changes `one_file` to `one_text` on its branch, and `two`, stacked on it, changes
    `two_file` to `two_text`. Main took a commit of its own after `one` left it."""

    def __init__(self, kitchen, one_file, one_text, two_file, two_text):
        self.kitchen, tree = kitchen, kitchen.checkout
        commit(tree, "shared.txt", "main's line\n")
        git(tree, "switch", "-q", "-c", "one")
        self.last = commit(tree, one_file, one_text)
        git(tree, "switch", "-q", "-c", "two")
        self.head = commit(tree, two_file, two_text)
        git(tree, "switch", "-q", "main")
        self.main = commit(tree, "later.txt", "main moved on\n")
        git(tree, "push", "-q", "origin", "main", "one", "two")
        git(tree, "branch", "-q", "-D", "one", "two")
        one = {**kitchen.opened("one", 10), "headRefOid": self.last, "baseRefName": "main"}
        two = {**kitchen.opened("two", 11), "headRefOid": self.head, "baseRefName": "one"}
        kitchen.set("open.json", [one, two])

    def origin(self, ref):
        return git(self.kitchen.origin, "rev-parse", ref)


@pytest.fixture
def signed_stack(stacked, monkeypatch):
    """The stack, with `two`'s brief left with no `Builds on:` line, as a row queued before
    `jbus queue add` asked a depends for one, so only `need` says whether it needs `one`."""
    signed(monkeypatch)
    builds_on(stacked, "")
    return stacked


def builds_on(kitchen, line):
    """Put `line` in place of any `Builds on:` line of `two`'s brief, or leave it none."""
    path = kitchen.home / "tasks" / "two.md"
    lines = path.read_text().splitlines(keepends=True)
    kept = [one for one in lines if not one.startswith("Builds on:")]
    at = next(n for n, one in enumerate(kept) if one.startswith("Where:")) + 1
    path.write_text("".join([*kept[:at], *([line] if line else []), *kept[at:]]))


def stays(stack):
    """The link is left on its base's branch, as it was, and `jmerge` waits for the base."""
    kitchen = stack.kitchen
    assert edits(kitchen) == []
    assert stack.origin("two") == stack.head
    assert head_line(kitchen) == stacks.Stacked("one", "one")
    said = ready.STACKED_ON.format(branch="one", slug="one", default="main")
    assert unmoved(kitchen, stack.head, base="one") == said
    assert asks(kitchen) == []


def test_a_link_with_no_need_of_its_open_base_moves_onto_main_and_merges_without_it(
    signed_stack,
):
    stack = OpenStack(signed_stack, "one.py", "def table_of(rows):\n", "two.txt", "two\n")
    kitchen = stack.kitchen
    said = ready.STACKED_ON.format(branch="one", slug="one", default="main")
    assert unmoved(kitchen, stack.head, base="one") == said
    kitchen.poll(NOW)
    moved = stack.origin("two")
    assert edits(kitchen) == ["pr edit 11 --base main"]
    assert git(kitchen.origin, "rev-parse", f"{moved}^") == stack.main
    assert git(kitchen.origin, "show", f"{moved}:two.txt") == "two"
    assert head_line(kitchen) is None
    assert unmoved(kitchen, moved) == ""
    assert asks(kitchen) == []
    assert [line.split(":")[0] for line in kitchen.lines("unstack")] == ["unstack two"]

    done = {**kitchen.merged("one", 10, "a" * 40), "headRefOid": stack.last}
    kitchen.set("open.json", [{**kitchen.opened("two", 11), "headRefOid": moved}])
    kitchen.set("merged.json", [{**done, "baseRefName": "main"}])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert stack.origin("two") == moved and edits(kitchen) == ["pr edit 11 --base main"]
    assert asks(kitchen) == []


def test_a_link_whose_brief_builds_on_its_open_base_stays_stacked_though_need_finds_nothing(
    signed_stack,
):
    """`two` needs `one` through a string, which `need` does not see: its brief's `Builds on:`
    line names `one`, so it stays stacked. The same link with no such line moves (above)."""
    builds_on(signed_stack, "Builds on: one: the tool name one adds to the table\n")
    stack = OpenStack(signed_stack, "one.py", "def table_of(rows):\n", "two.txt", "two\n")
    said = stack.kitchen.poll(NOW) + stack.kitchen.poll(NOW + timedelta(minutes=3))
    stays(stack)
    assert [line for line in said if line.startswith("unstack two")] == [
        "unstack two: stays stacked on one, since its brief's Builds on: line names it"
    ]


def test_a_link_whose_brief_builds_on_another_row_still_moves(signed_stack):
    builds_on(signed_stack, "Builds on: three: the table three adds\n")
    stack = OpenStack(signed_stack, "one.py", "def table_of(rows):\n", "two.txt", "two\n")
    stack.kitchen.poll(NOW)
    assert edits(stack.kitchen) == ["pr edit 11 --base main"]
    assert head_line(stack.kitchen) is None


def test_a_link_that_conflicts_without_its_base_stays_stacked(signed_stack):
    stack = OpenStack(signed_stack, "shared.txt", "one's line\n", "shared.txt", "two's line\n")
    stack.kitchen.poll(NOW)
    stays(stack)


def test_a_link_that_uses_a_name_its_base_introduced_stays_stacked(signed_stack):
    stack = OpenStack(
        signed_stack, "one.py", "def table_of(rows):\n", "two.py", "print(table_of([]))\n"
    )
    stack.kitchen.poll(NOW)
    stays(stack)


def test_a_link_whose_commits_conflict_one_by_one_is_left_once_for_its_heads(signed_stack):
    """Its own change as a whole merges cleanly, but its first commit, replayed onto main, does
    not: jbus leaves it stacked and tries it again only once a head moves."""
    kitchen, tree = signed_stack, signed_stack.checkout
    commit(tree, "shared.txt", "main's line\n")
    git(tree, "switch", "-q", "-c", "one")
    last = commit(tree, "one.py", "def table_of(rows):\n")
    git(tree, "switch", "-q", "-c", "two")
    commit(tree, "shared.txt", "for a while\n")
    head = commit(tree, "shared.txt", "main's line\n", "back")
    git(tree, "switch", "-q", "main")
    commit(tree, "shared.txt", "main's later line\n")
    git(tree, "push", "-q", "origin", "main", "one", "two")
    git(tree, "branch", "-q", "-D", "one", "two")
    one = {**kitchen.opened("one", 10), "headRefOid": last, "baseRefName": "main"}
    two = {**kitchen.opened("two", 11), "headRefOid": head, "baseRefName": "one"}
    kitchen.set("open.json", [one, two])
    said = kitchen.poll(NOW) + kitchen.poll(NOW + timedelta(minutes=3))
    assert [line for line in said if line.startswith("unstack two")] == [
        "unstack two: jbus left its branch as it was (its commits conflict with origin/main), "
        "so it stays stacked for now"
    ]
    assert edits(kitchen) == [] and head_line(kitchen) == stacks.Stacked("one", "one")
