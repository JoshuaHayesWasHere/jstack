"""A row that builds on an open pull request launches stacked on its branch (`test_jbus_chains`).
While the base is open, its crew is told nothing, however the base's head moves. Once:

- When the base merged, jbus bases the link's pull request on the branch the base merged into
  (main, or another branch), or on the one its brief opens it against, tells its crew to move
  its own commits onto that branch, and writes where it sits now on the brief's `Stacked on:` line.
- A link that still sits on its base gets no message to rebase onto main: its branch holds its
  base's commits, which only "A link that moved" leaves out.
- A link with no pull request yet, its crew waiting on the review jbus launches, has its
  `Stacked on:` lines moved onto the branch its base merged into by `jbus.stack.before_pull`, in
  the brief's head and in its Result, before that review is launched.

The tests run the real pass against the kitchen's fakes of T3 Code and GitHub."""

import json
from datetime import timedelta

import pytest

import jbus
from crew_branches import pushed
from jbriefs import stacked as stacks
from jbus import queue
from jmerge import mainjson
from test_jbus_chains import queue_add
from test_jbus_kitchen import NOW, Kitchen, asks, sends_in_once
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
    pushed(kitchen, "one")
    kitchen.set("open.json", [kitchen.opened("one", 10)])
    kitchen.poll(NOW - timedelta(minutes=27))
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: one", "crew: two"]
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    yield kitchen
    kitchen.close()


def pulls(
    kitchen, base=BASE, link=LINK, on="one", merged=False, mergeable="MERGEABLE", into="main"
):
    """Set what GitHub lists: `two` at `link` based on the branch `on`, and `one` at `base`,
    open, or merged into the branch `into` as `MERGE` with its last head `LAST`."""
    two = {**kitchen.opened("two", 11), "headRefOid": link, "baseRefName": on}
    two["mergeable"] = mergeable
    if merged:
        kitchen.set("open.json", [two])
        done = {**kitchen.merged("one", 10, MERGE), "headRefOid": LAST, "baseRefName": into}
        kitchen.set("merged.json", [done])
    else:
        kitchen.set("open.json", [{**kitchen.opened("one", 10), "headRefOid": base}, two])


def passes(kitchen, *minutes):
    for minute in minutes:
        kitchen.poll(NOW + timedelta(minutes=minute))


def head_line(kitchen):
    text = (kitchen.home / "tasks" / "two.md").read_text()
    return stacks.of(text)


def keys(kitchen):
    """The request id of each message a pass sent a thread, but for the one list's wakes."""
    return [given["clientRequestId"] for given in asks(kitchen)]


def edits(kitchen):
    return [line for line in kitchen.log("gh") if line.startswith("pr edit")]


def test_a_link_whose_base_is_open_is_told_nothing_however_the_base_moves(stacked):
    """The base's head moves under its link (review fixes, a rebase), and the link's own head
    moves too: none of it is the crew's to hear while the base is open. Once the base merged,
    the crew hears of it once."""
    for minute, (base, link) in enumerate([(BASE, LINK), ("e" * 40, LINK), ("f" * 40, "9" * 40)]):
        pulls(stacked, base=base, link=link)
        passes(stacked, 3 * minute)
    assert asks(stacked) == [] and keys(stacked) == []
    assert not [line for line in stacked.log("gh") if "/compare/" in line]
    assert head_line(stacked) == stacks.Stacked("one", "one")

    pulls(stacked, merged=True)
    passes(stacked, 9, 12)
    assert keys(stacked) == [f"restack|two|{LINK[:12]}|{MERGE[:12]}"]
    assert head_line(stacked) == stacks.Stacked("one", "main", MERGE)


@pytest.mark.parametrize("on", ["one", "main"])
def test_a_base_that_merged_moves_its_link_onto_main_once(stacked, on):
    """GitHub bases the link on main by itself when the base's branch is deleted on its merge.
    Where it has not, jbus does. Either way the crew is told once, with the base's last head as
    the commit its own commits start above, and the brief says where the link sits now."""
    pulls(stacked, merged=True, on=on)
    passes(stacked, 0, 3)
    assert edits(stacked) == (["pr edit 11 --base main"] if on == "one" else [])
    assert keys(stacked) == [f"restack|two|{LINK[:12]}|{MERGE[:12]}"]
    (said,) = [given["message"] for given in asks(stacked)]
    assert "one merged as aaaaaaaaaaaa" in said and "now based on main" in said
    assert f"run its block with {LAST} as `was`" in said and "again with one" in said
    assert head_line(stacked) == stacks.Stacked("one", "main", MERGE)


@pytest.mark.parametrize("on", ["one", "release/x"])
def test_a_base_that_merged_into_a_branch_moves_its_link_onto_the_branch(stacked, on):
    """A base that merged into another branch than the default leaves its link on that
    branch: a rebase onto main would carry the branch's commits to main. A link GitHub already
    based on the branch is not edited."""
    pulls(stacked, merged=True, on=on, into="release/x")
    passes(stacked, 0, 3)
    assert edits(stacked) == (["pr edit 11 --base release/x"] if on == "one" else [])
    (said,) = [given["message"] for given in asks(stacked)]
    assert "one merged as aaaaaaaaaaaa" in said and "now based on release/x" in said
    assert "origin/release/x" in said and "main" not in said
    assert head_line(stacked) == stacks.Stacked("one", "release/x", MERGE)


def test_a_link_whose_brief_names_its_base_is_moved_onto_that_base(stacked):
    """A brief whose `Pull request:` line names the branch to open it against keeps its link on
    that branch once its base merged, wherever the base merged."""
    path = stacked.home / "tasks" / "two.md"
    text = path.read_text().replace(
        "Pull request: open one when done", "Pull request: open one against release/y when done"
    )
    path.write_text(text)
    pulls(stacked, merged=True)
    passes(stacked, 0, 3)
    assert edits(stacked) == ["pr edit 11 --base release/y"]
    assert head_line(stacked) == stacks.Stacked("one", "release/y", MERGE)


def test_a_link_is_not_moved_while_github_does_not_say_where_its_base_merged(stacked):
    """With no answer from GitHub on the branch the base merged into, the link is not moved
    onto the default branch for want of it: it waits for a later pass."""
    pulls(stacked, merged=True, into="release/x")
    (stacked.stub / "gh-view-down").write_text("")
    said = stacked.poll(NOW)
    assert "wait two: GitHub did not say what one merged into" in said
    assert edits(stacked) == [] and asks(stacked) == []
    assert head_line(stacked) == stacks.Stacked("one", "one")
    (stacked.stub / "gh-view-down").unlink()
    passes(stacked, 3)
    assert edits(stacked) == ["pr edit 11 --base release/x"]


def test_a_link_whose_thread_is_at_work_is_moved_on_a_later_pass(stacked):
    pulls(stacked, merged=True)
    for thread in stacked.t3.threads:
        thread["status"] = "running"
    passes(stacked, 0)
    assert asks(stacked) == []
    assert head_line(stacked) == stacks.Stacked("one", "one")
    for thread in stacked.t3.threads:
        thread["status"] = "completed"
    passes(stacked, 3, 6)
    assert keys(stacked) == [f"restack|two|{LINK[:12]}|{MERGE[:12]}"]
    assert head_line(stacked) == stacks.Stacked("one", "main", MERGE)


def test_a_link_that_sits_on_its_base_is_not_told_to_rebase_onto_main_for_a_conflict(stacked):
    pulls(stacked, mergeable="CONFLICTING")
    passes(stacked, 0, 3)
    assert asks(stacked) == []


def test_a_link_github_will_not_rebase_is_told_nothing_and_its_line_stays(stacked):
    pulls(stacked, merged=True)
    (stacked.stub / "gh-edit-refused").write_text("")
    said = stacked.poll(NOW)
    assert "wait two: #11 could not be based on main: gh exited 1" in said
    assert asks(stacked) == []
    assert head_line(stacked) == stacks.Stacked("one", "one")


def test_a_refused_or_lost_move_keeps_no_key_and_the_link_where_it_sits(stacked):
    """Only a message that went writes the restack key and moves the brief's `Stacked on:` line,
    so the next pass tells it under the same key."""
    key = f"restack|two|{LINK[:12]}|{MERGE[:12]}"
    pulls(stacked, merged=True)
    stacked.t3.refuse_send = True
    passes(stacked, 0)
    stacked.t3.refuse_send = False
    stacked.t3.lose_send = True
    passes(stacked, 3)
    stacked.t3.lose_send = False
    assert key not in jbus.read_json(stacked.state / "sent.json", [])
    assert head_line(stacked) == stacks.Stacked("one", "one")
    assert stacked.lines("restack") == []

    passes(stacked, 6, 9)
    assert keys(stacked) == [key] * 3
    assert jbus.read_json(stacked.state / "sent.json", []).count(key) == 1
    assert stacked.lines("restack") == [f"restack two: told the crew one merged (#11, {LINK[:12]})"]
    assert head_line(stacked) == stacks.Stacked("one", "main", MERGE)


def test_the_restack_message_goes_out_inside_once(stacked, monkeypatch):
    spied = sends_in_once(monkeypatch)
    pulls(stacked, merged=True)
    passes(stacked, 0)
    assert spied == [(f"restack|two|{LINK[:12]}|{MERGE[:12]}", True)]


def before_pull(kitchen, merged=True, into="main"):
    """`two` has no pull request yet: its crew wrote its Result with `Pull request: after the
    review`, its own `Stacked on:` line naming `one`'s pull request, and `one` is open, or merged
    into the branch `into` as `MERGE`."""
    path = kitchen.home / "tasks" / "two.md"
    path.write_text(
        path.read_text() + "\n## Result\nStatus: done\nBranch: two   Pull request: after the "
        "review\nStacked on: one one https://example.test/pull/10\nLeft: none\n"
    )
    if merged:
        kitchen.set("open.json", [])
        done = {**kitchen.merged("one", 10, MERGE), "headRefOid": LAST, "baseRefName": into}
        kitchen.set("merged.json", [done])
    else:
        kitchen.set("open.json", [{**kitchen.opened("one", 10), "headRefOid": BASE}])
    return path


def result_line(path):
    return [
        line for line in path.read_text().split("\n## ", 1)[1].splitlines() if "Stacked" in line
    ]


def test_a_restack_before_the_pull_request_moves_both_lines_once_its_base_merged(stacked):
    path = before_pull(stacked)
    said = stacked.poll(NOW)
    assert head_line(stacked) == stacks.Stacked("one", "main", MERGE)
    assert result_line(path) == [f"Stacked on: one main at {MERGE} https://example.test/pull/10"]
    assert "restack two: moved its Stacked on: line onto main, one merged" in said
    restacks = [one for one in asks(stacked) if not one["clientRequestId"].startswith("prereview-")]
    assert edits(stacked) == [] and restacks == []


def test_a_restack_before_the_pull_request_waits_while_its_base_is_open(stacked):
    path = before_pull(stacked, merged=False)
    stacked.poll(NOW)
    assert head_line(stacked) == stacks.Stacked("one", "one")
    assert result_line(path) == ["Stacked on: one one https://example.test/pull/10"]


def test_a_restack_before_the_pull_request_waits_while_github_does_not_say_where(stacked):
    path = before_pull(stacked, into="release/x")
    (stacked.stub / "gh-view-down").write_text("")
    said = stacked.poll(NOW)
    assert "wait two: GitHub did not say what one merged into" in said
    assert head_line(stacked) == stacks.Stacked("one", "one")
    (stacked.stub / "gh-view-down").unlink()
    passes(stacked, 3)
    assert head_line(stacked) == stacks.Stacked("one", "release/x", MERGE)
    assert result_line(path)[0].startswith(f"Stacked on: one release/x at {MERGE} ")


def test_a_restack_before_the_pull_request_whose_brief_cannot_be_written_says_so(stacked):
    path = before_pull(stacked)
    path.chmod(0o444)
    try:
        said = stacked.poll(NOW)
    finally:
        path.chmod(0o644)
    wait = "wait two: its Stacked on: line could not be written ("
    assert [line for line in said if line.startswith(wait)] != []
    assert [line for line in said if line.startswith("restack two: moved")] == []
    assert head_line(stacked) == stacks.Stacked("one", "one")


@pytest.mark.parametrize("left", ["landed", "not moved", "stopped", "unreadable"])
def test_a_crew_killed_after_its_rebase_landed_leaves_a_record_that_holds_no_link(
    stacked, monkeypatch, left
):
    """The crew's push block pushed its rebased head and the crew was killed before
    `jbus forget`, so `crew-before-rebase` is left in its worktree's git dir. Origin's branch is at
    that rebased head, so the rebase is done: jbus forgets the record and moves the link. A record
    whose rebase has not moved the head yet, at the head it names as before the rebase, a rebase
    git has stopped in, and a record that cannot be read, are a rebase not finished, and hold the
    link."""
    from test_jbus_stack_move import Stack, git, signed

    signed(monkeypatch)
    stack = Stack(stacked)
    tree = stacked.root / "two-tree"
    git(stacked.checkout, "worktree", "add", "-q", str(tree), stack.head, "-b", "two")
    gitdir = stacked.root / git(tree, "rev-parse", "--absolute-git-dir")
    record = gitdir / "crew-before-rebase"
    before = stack.head if left == "not moved" else git(tree, "rev-parse", f"{stack.head}^")
    if left == "unreadable":
        record.mkdir()
    else:
        record.write_text(f"{before} one {before}\n")
    if left == "stopped":
        (gitdir / "rebase-merge").mkdir()
    said = stacked.poll(NOW)
    if left == "landed":
        moved = stack.origin("two")
        assert git(stacked.origin, "rev-parse", f"{moved}^") == stack.merge
        assert git(tree, "rev-parse", "HEAD") == moved
        assert not record.exists() and asks(stacked) == []
    else:
        assert stack.origin("two") == stack.head and record.exists()
        assert any("has a rebase of its own not finished" in line for line in said), said


BASE_ROW, HELD_ROW = "st-code-conforms", "st-hand-over-line"


class Held:
    """st-hand-over-line, replayed: `st-code-conforms` (#10) is open on its branch, and
    `st-hand-over-line`, filed from it with no depends, launched on main. Its crew found the code
    it needs only on the base's branch, built two commits on its head in its own worktree, pushed
    nothing, and paused with `Waits on: st-code-conforms`. Each thread's turn has ended."""

    def __init__(self, kitchen, monkeypatch, waits=BASE_ROW, against=""):
        from test_jbus_stack_move import commit, crewtree_of, git, signed

        signed(monkeypatch)
        self.kitchen, self.git = kitchen, git
        kitchen.word()
        kitchen.config(max_running=8)
        assert queue_add(kitchen, BASE_ROW)[0] == 0 and go(kitchen, BASE_ROW)[0] == 0
        text = brief(HELD_ROW)
        if against:
            text = text.replace("open one when done", f"open one against {against} when done")
        assert queue_add(kitchen, HELD_ROW, text=text)[0] == 0 and go(kitchen, HELD_ROW)[0] == 0
        assert queue_add(kitchen, "other")[0] == 0
        if against:
            pushed(kitchen, against)
        green = git(kitchen.checkout, "rev-parse", "main")
        kept = mainjson.record(main=green, at=NOW.isoformat(), check="green", green=green)
        (kitchen.state / mainjson.NAME).write_text(json.dumps(kept))
        passes(kitchen, -30, -27)
        titles = [one["title"] for one in kitchen.t3.launches]
        assert titles == [f"crew: {BASE_ROW}", f"crew: {HELD_ROW}"]
        base, row = crewtree_of(kitchen, BASE_ROW), crewtree_of(kitchen, HELD_ROW)
        self.base_head = commit(base, "conforms.txt", "conforms\n")
        git(base, "push", "-q", "origin", BASE_ROW)
        git(row, "fetch", "-q", "origin", BASE_ROW)
        git(row, "reset", "-q", "--hard", self.base_head)
        commit(row, "hand.txt", "hand over\n")
        self.head = commit(row, "line.txt", "the line\n")
        self.tree = row
        self.path = kitchen.home / "tasks" / f"{HELD_ROW}.md"
        self.path.write_text(
            self.path.read_text() + "\n## Result\nStatus: paused\nDone when: all hold\n"
            f"Branch: {HELD_ROW}   Pull request: none\nWaits on: {waits}\n"
            f"Left: the commits are local, nothing is pushed, by design, until {BASE_ROW} "
            "merges\n"
        )
        self.opened(self.base_head)
        for thread in kitchen.t3.threads:
            thread["status"] = "completed"

    def opened(self, head):
        self.kitchen.set("open.json", [{**self.kitchen.opened(BASE_ROW, 10), "headRefOid": head}])

    def head_line(self):
        return stacks.of(self.path.read_text())

    def green(self):
        head = self.path.read_text().split("\n## ", 1)[0]
        return [line for line in head.splitlines() if line.startswith("Green main:")]

    def depends(self):
        (row,) = [one for one in queue.load(self.kitchen.state) if one["slug"] == HELD_ROW]
        return row.get("depends", [])

    def told(self):
        return [one for one in asks(self.kitchen) if one["clientRequestId"].startswith("stacked|")]


@pytest.fixture
def held(tmp_path, monkeypatch):
    kitchen = Kitchen(tmp_path, monkeypatch)
    yield Held(kitchen, monkeypatch)
    kitchen.close()


def test_a_paused_row_built_on_an_open_rows_branch_is_stacked_on_its_pull_request(held):
    """One pass stacks it: the depends, the `Stacked on:` line in place of `Green main:`, and one
    message telling its crew to check on that base, push, and end for the review. A second pass
    sends nothing. Once the base merges, the row's pushed commits are moved onto main as for a
    link jbus launched stacked."""
    kitchen = held.kitchen
    assert held.green() != [] and held.head_line() is None
    said = kitchen.poll(NOW)
    assert held.head_line() == stacks.Stacked(BASE_ROW, BASE_ROW)
    assert held.green() == []
    assert held.depends() == [BASE_ROW]
    (told,) = held.told()
    assert told["clientRequestId"] == f"stacked|{HELD_ROW}|{BASE_ROW}|{held.base_head[:12]}"
    assert "push" in told["message"] and f"Stacked on: {BASE_ROW} {BASE_ROW}" in told["message"]
    assert any(line.startswith(f"stack {HELD_ROW}: stacked on {BASE_ROW}") for line in said), said

    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(held.told()) == 1

    git = held.git
    git(held.tree, "push", "-q", "origin", HELD_ROW)
    held.path.write_text(
        held.path.read_text() + "\n## Result, follow-up (2026-11-12, stacked)\nStatus: done\n"
        f"Branch: {HELD_ROW}   Pull request: after the review\nLeft: none\n"
    )
    tree = kitchen.checkout
    git(tree, "fetch", "-q", "origin", "main")
    git(tree, "switch", "-q", "--detach", "origin/main")
    git(tree, "checkout", "-q", held.base_head, "--", "conforms.txt")
    git(tree, "commit", "-q", "-m", f"{BASE_ROW} (#10)")
    merge = git(tree, "rev-parse", "HEAD")
    git(tree, "push", "-q", "origin", f"{merge}:refs/heads/main")
    git(tree, "switch", "-q", "main")
    kitchen.set("open.json", [])
    done = {**kitchen.merged(BASE_ROW, 10, merge), "headRefOid": held.base_head}
    kitchen.set("merged.json", [{**done, "baseRefName": "main"}])
    kitchen.poll(NOW + timedelta(minutes=6))
    moved = git(kitchen.origin, "rev-parse", HELD_ROW)
    assert git(kitchen.origin, "rev-parse", f"{moved}~2") == merge
    assert git(kitchen.origin, "diff", "--name-only", merge, moved).split() == [
        "hand.txt",
        "line.txt",
    ]
    assert held.head_line() == stacks.Stacked(BASE_ROW, "main", merge)
    assert len(held.told()) == 1


@pytest.mark.parametrize("left", ["no pull request", "two slugs", "not held", "other branch"])
def test_a_paused_row_with_nothing_pushed_to_stack_on_is_left_as_it_is(tmp_path, monkeypatch, left):
    """A base with no open pull request (its branch never pushed), a wait on two rows, a branch
    that does not hold the base's head, or a row that goes on another branch than its base: the
    row stays paused on main, its depends as they were, and its crew is told nothing."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    try:
        waits = f"{BASE_ROW} other" if left == "two slugs" else BASE_ROW
        held = Held(kitchen, monkeypatch, waits, "release/x" if left == "other branch" else "")
        if left == "no pull request":
            kitchen.set("open.json", [])
        if left == "not held":
            held.opened("e" * 40)
        kitchen.poll(NOW)
        assert held.head_line() is None and held.green() != []
        assert held.depends() == [] and held.told() == []
    finally:
        kitchen.close()


def test_a_stack_whose_message_is_refused_or_held_tells_its_crew_once_on_a_later_pass(held):
    """T3 Code refuses the message, then the crew's turn runs, and the outbox holds it: the stack
    stays written, and the crew hears of it once, on the first pass that can tell it."""
    kitchen = held.kitchen
    key = f"stacked|{HELD_ROW}|{BASE_ROW}|{held.base_head[:12]}"
    kitchen.t3.refuse_send = True
    said = kitchen.poll(NOW)
    kitchen.t3.refuse_send = False
    assert any(line.startswith(f"wait {HELD_ROW}: its crew could not be told") for line in said)
    assert held.head_line() == stacks.Stacked(BASE_ROW, BASE_ROW)
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == f"crew: {HELD_ROW}"]
    crew.update(status="running")
    kitchen.t3.at_work.add(crew["threadId"])
    passes(kitchen, 3)
    assert key not in jbus.read_json(kitchen.state / "sent.json", [])
    crew.update(status="completed")
    kitchen.t3.at_work.discard(crew["threadId"])
    passes(kitchen, 6, 9)
    assert jbus.read_json(kitchen.state / "sent.json", []).count(key) == 1
    assert [one["clientRequestId"] for one in held.told()].count(key) == 2


def test_a_stack_whose_brief_cannot_be_written_is_made_on_a_later_pass(held):
    held.path.chmod(0o444)
    try:
        said = held.kitchen.poll(NOW)
    finally:
        held.path.chmod(0o644)
    assert any("its Stacked on: line could not be written" in line for line in said), said
    assert held.head_line() is None and held.told() == []
    passes(held.kitchen, 3)
    assert held.head_line() == stacks.Stacked(BASE_ROW, BASE_ROW) and len(held.told()) == 1
