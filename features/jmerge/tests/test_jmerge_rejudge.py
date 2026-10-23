"""A pull request whose required check failed, and whose base has moved since that check started,
is judged again over today's base. Where the repo has a `fresh-check` file, `jmerge` runs it on
the head merged over today's base, once for a head and a base tip. On a pass, or with no such
file, it asks GitHub to merge the base into the branch
(`PUT /repos/{owner}/{repo}/pulls/{n}/update-branch`), and the pull request goes on by the
normal path once GitHub's new check passes. On a fail, its crew is told once that the command
fails over today's base.

The replay is 2026-10-23: main red on two whole-tree tests, pull requests that touched neither
red on them, then main fixed. The tests run the command as `test_jmerge_fresh` does, against a
real origin and a fake `gh`. What a crew is told is what jbus sends for a line of `jmerge`
(`jbus.rebase.asks`)."""

import json

import pytest

import test_home_merge as merge
import test_jmerge_order as order
from jbus import merge as jbus_merge
from jbus import rebase
from jmerge import mainjson, ready
from test_jmerge_fresh import GH, LINES, Kitchen, git, known, settled, url, write

BROKE = "2026-10-23T12:00:00Z"
STARTED = "2026-10-23T13:00:00Z"
FIXED = "2026-10-23T15:00:00Z"
RED = {**merge.FAILED, "startedAt": STARTED}
GREEN = {**merge.PASSED, "startedAt": "2099-01-01T00:00:00Z"}
UPDATE = """\
    "api -X")
        number=${4#*/pulls/}
        number=${number%/update-branch}
        echo "$number" >> "$STUB/updated"
        branch=$(cat "$STUB/branch-$number")
        head=$(git -C "$ORIGIN" rev-parse "refs/heads/$branch")
        if [ "$6" != "expected_head_sha=$head" ]; then
            echo '{"message":"expected head sha did not match current head ref."}'
            exit 1
        fi
        if [ -e "$STUB/refuse" ]; then
            echo '{"message":"merge conflict between base and head"}'
            echo "gh: merge conflict between base and head (HTTP 422)" >&2
            exit 1
        fi
        if [ -e "$STUB/down" ]; then
            echo '{"message":"Server Error"}'
            echo "gh: Server Error (HTTP 502)" >&2
            exit 1
        fi
        tree=$(git -C "$ORIGIN" merge-tree --write-tree refs/heads/main "$head") || exit 1
        commit=$(git -C "$ORIGIN" commit-tree "$tree" -p "$head" -p refs/heads/main -m update)
        git -C "$ORIGIN" update-ref "refs/heads/$branch" "$commit"
        echo '{"message":"Updating pull request branch."}' ;;
"""
CHECK = "! ls tests/broken-* > /dev/null 2>&1"
WHOLE_TREE = {"tests/broken-module-size": "", "tests/broken-view-sources": ""}
ASKED = "GitHub was asked to merge main at {tip} into it: its check failed before main moved"


class Replay:
    """A kitchen whose fake `gh` can update a branch, and whose home has a jbus config, so that
    `jmerge` reads jbus's `main.json`."""

    def __init__(self, tmp_path, fresh=True):
        self.kitchen = kitchen = Kitchen(tmp_path, {"a.txt": LINES, "Makefile": "check:\n"})
        gh = kitchen.home.stub / "gh"
        gh.write_text(GH.replace("    *) exit 64 ;;\n", UPDATE + "    *) exit 64 ;;\n"))
        self.state = order.queue_of(kitchen.home, []).parent
        if fresh:
            (kitchen.home.state / "fresh-check").write_text(f"{CHECK}\n")
        self.told = []
        self.said = []

    def crew(self, slug, number, files):
        """A crew's pull request, reviewed clean at its head, whose check ran while main was red
        and failed."""
        head = self.kitchen.crew(slug, number, files, checks=(RED,))
        (self.kitchen.home.stub / f"branch-{number}").write_text(slug)
        return head

    def main_at(self, files, at, check):
        """A commit on main at the time `at`, and what jbus's `main.json` says of it."""
        main = self.kitchen.home.main
        git(main, "pull", "-q", "--ff-only")
        write(main, files)
        git(main, "commit", "-q", "-m", "main", at=at)
        git(main, "push", "-q")
        tip = git(main, "rev-parse", "HEAD")
        broken = {"broken": tip} if check == "failed" else {}
        record = mainjson.record(main=tip, at=at, check=check, **broken)
        (self.state / mainjson.NAME).write_text(json.dumps(record))
        return tip

    def github(self):
        """GitHub after an update of a branch: the new head, whose check ran over today's main
        and passed."""
        for slug, pull in self.kitchen.pulls.items():
            head = git(self.kitchen.origin, "rev-parse", f"refs/heads/{slug}")
            if head != pull["headRefOid"]:
                pull |= {"headRefOid": head, "statusCheckRollup": merge.rollup([GREEN])}
        listed = [
            pull
            for slug, pull in self.kitchen.pulls.items()
            if not any(line.startswith(f"merged {pull['number']} ") for line in self.said)
        ]
        (self.kitchen.home.stub / "list.json").write_text(json.dumps(listed))

    def run(self, *flags):
        """One run of `jmerge`, after any fresh check the run started has ended. Each line is
        read as jbus reads it, and what jbus would tell a crew is kept."""
        before = known(self.kitchen)
        said = self.kitchen.run(*flags)
        if any(line.endswith(ready.FRESH_QUEUED) for line in said):
            settled(self.kitchen, before)
        for line in said:
            asked = rebase.asks(line)
            if asked:
                number, _, ask = asked
                if (ask.kind, number, ask.head) not in self.told:
                    self.told.append((ask.kind, number, ask.head))
        self.said += said
        return said

    def passes(self, count=10):
        """`count` passes of jbus, each with GitHub's check of each branch it updated."""
        for _ in range(count):
            self.github()
            self.run()

    def updated(self):
        path = self.kitchen.home.stub / "updated"
        return path.read_text().split() if path.exists() else []

    def journal(self, number):
        log = (self.kitchen.home.state / "merge.log").read_text().splitlines()
        return [line for line in log if f" {number} " in line and "GitHub was asked" in line]


def merged(said):
    return sorted(int(line.split()[1]) for line in said if line.startswith("merged "))


@pytest.fixture
def replay(tmp_path):
    return Replay(tmp_path)


def red_then_fixed(replay):
    """Main breaks on two whole-tree tests. Three pull requests that touch neither, and one that
    breaks a test of its own, go red over it. Then main is fixed."""
    heads = [
        replay.crew("one", 333, {"one.txt": "ours\n"}),
        replay.crew("two", 340, {"two.txt": "ours\n"}),
        replay.crew("three", 341, {"a.txt": "ours\n" + LINES}),
        replay.crew("broken", 339, {"tests/broken-its-own": ""}),
    ]
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    assert replay.run() == [
        f"wait {number} {url(number)}: check has not passed" for number in (333, 339, 340, 341)
    ]
    fix = replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    return heads, fix


def test_the_replay_every_pull_request_red_only_on_its_base_merges_and_one_crew_is_told(replay):
    (_, _, _, broken), fix = red_then_fixed(replay)
    replay.passes()
    assert merged(replay.said) == [333, 340, 341]
    carried = [line for line in replay.said if line.startswith("merged ")]
    assert all(", review carried over: range-diff " in line for line in carried), carried
    assert sorted(replay.updated()) == ["333", "340", "341"]
    assert all(len(replay.journal(number)) == 1 for number in (333, 340, 341))
    failing = f"{CHECK} fails on {broken[:12]} over today's main"
    assert replay.said[-1].startswith(f"wait 339 {url(339)}: {failing} ")
    assert replay.told == [("rebase", 339, broken[:12])]
    assert replay.kitchen.at_main("one.txt") == "ours"


def test_with_no_fresh_check_file_github_s_update_alone_moves_it_on(tmp_path):
    replay = Replay(tmp_path, fresh=False)
    (one, *_), fix = red_then_fixed(replay)
    said = replay.run()
    assert f"wait 333 {url(333)}: {ASKED.format(tip=fix[:12])}" in said
    assert sorted(replay.updated()) == ["333", "339", "340", "341"]
    replay.passes(2)
    assert merged(replay.said) == [333, 339, 340, 341]
    assert replay.told == []


def test_the_branch_is_updated_once_for_a_head_and_a_base_tip(tmp_path):
    replay = Replay(tmp_path, fresh=False)
    (replay.kitchen.home.stub / "refuse").write_text("")
    replay.crew("one", 333, {"one.txt": "ours\n"})
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    fix = replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    refused = "GitHub did not merge main at {tip} into it: merge conflict between base and head"
    for _ in range(3):
        assert replay.run()[-1] == f"wait 333 {url(333)}: {refused.format(tip=fix[:12])}"
    assert replay.updated() == ["333"]
    later = replay.main_at({"b.txt": "theirs\n"}, "2026-10-23T16:00:00Z", "green")
    replay.run()
    assert replay.run()[-1] == f"wait 333 {url(333)}: {refused.format(tip=later[:12])}"
    assert replay.updated() == ["333", "333"]


def test_a_failure_to_ask_github_is_asked_again_on_the_next_run(tmp_path):
    """A 5xx is no answer of GitHub's own: it keeps no record, and the next run asks again."""
    replay = Replay(tmp_path, fresh=False)
    (replay.kitchen.home.stub / "down").write_text("")
    replay.crew("one", 333, {"one.txt": "ours\n"})
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    fix = replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    down = f"GitHub did not merge main at {fix[:12]} into it: Server Error"
    assert replay.run() == [f"wait 333 {url(333)}: {down}"]
    assert replay.run() == [f"wait 333 {url(333)}: {down}"]
    (replay.kitchen.home.stub / "down").unlink()
    assert replay.run() == [f"wait 333 {url(333)}: {ASKED.format(tip=fix[:12])}"]
    assert replay.updated() == ["333", "333", "333"]
    replay.passes(1)
    assert merged(replay.said) == [333]


def test_a_red_pull_request_short_of_anything_else_keeps_its_line_and_asks_nothing(replay):
    """The change's one safety fact: only a pull request whose single shortfall is its failed
    check is judged again. One whose queue row is held waits as before, with no fresh check and
    no update asked of GitHub."""
    order.queue_of(replay.kitchen.home, [order.row("one", pr="#333", held=True)])
    replay.crew("one", 333, {"one.txt": "ours\n"})
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    assert replay.run() == [f"wait 333 {url(333)}: check has not passed"]
    assert replay.updated() == [] and not (replay.kitchen.home.state / "fresh.json").exists()
    order.queue_of(replay.kitchen.home, [order.row("one", pr="#333")])
    assert replay.run() == [f"wait 333 {url(333)}: {ready.FRESH_QUEUED}"]


def test_a_red_base_is_not_judged_again_until_it_is_green(replay):
    replay.crew("one", 333, {"one.txt": "ours\n"})
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    replay.main_at({"b.txt": "theirs\n"}, FIXED, "failed")
    assert replay.run() == [f"wait 333 {url(333)}: check has not passed"]
    assert replay.updated() == [] and not (replay.kitchen.home.state / "fresh.json").exists()


def test_a_failed_check_over_a_base_that_has_not_moved_since_is_the_pull_request_s_own(replay):
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    replay.main_at({"c.txt": "theirs\n"}, "2026-10-23T12:30:00Z", "green")
    replay.crew("one", 333, {"one.txt": "ours\n"})
    assert replay.run() == [f"wait 333 {url(333)}: check has not passed"]
    assert replay.updated() == [] and not (replay.kitchen.home.state / "fresh.json").exists()


def test_a_check_run_asks_github_for_nothing(tmp_path):
    replay = Replay(tmp_path, fresh=False)
    replay.crew("one", 333, {"one.txt": "ours\n"})
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    fix = replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    due = "its check failed before main moved: GitHub is to merge main at {tip} into it"
    assert replay.run("--check") == [f"wait 333 {url(333)}: {due.format(tip=fix[:12])}"]
    assert replay.updated() == []


def test_each_line_of_a_judgement_again_is_on_the_check_step_and_tells_no_crew():
    for reason in (ready.BASE_MERGE_ASKED, ready.BASE_MERGE_REFUSED, ready.BASE_MERGE_DUE):
        filled = reason.format(base="main", tip="0123456789ab", why="it said no")
        assert jbus_merge.step(f"wait: {filled}") == "check"
        assert rebase.asks(f"wait 333 {url(333)}: {filled}") is None
