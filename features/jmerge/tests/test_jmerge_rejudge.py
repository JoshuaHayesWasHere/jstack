"""A pull request whose required check failed, and whose base has moved since that check started,
is judged again over today's base: `jmerge` asks GitHub to merge the base into the branch
(`PUT /repos/{owner}/{repo}/pulls/{n}/update-branch`), once for a head and a base tip, and the
pull request goes on by the normal path once GitHub's new check passes. A change broken on its
own fails again at the updated head, as its own. Where the repo has a `fresh-check` file, a green
pull request whose base moved under it takes the same path, and no suite runs on this machine.

The replay is 2026-10-23: main red on two whole-tree tests, pull requests that touched neither
red on them, then main fixed. The tests run the command as `test_jmerge_fresh` does, against a
real origin and a fake `gh`, whose check at an updated head fails where the tree is broken.
What a crew is told is what jbus sends for a line of `jmerge` (`jbus.rebase.asks`)."""

import json

import pytest

import test_home_merge as merge
import test_jmerge_order as order
from jbus import merge as jbus_merge
from jbus import rebase
from jmerge import mainjson, ready
from test_jmerge_fresh import GH, LINES, Kitchen, git, url, write

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
            echo "gh: Server Error (HTTP $(cat "$STUB/down"))" >&2
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

    def crew(self, slug, number, files, check=RED):
        """A crew's pull request, reviewed clean at its head, whose check ran while main was red
        and failed, or ran as `check` says."""
        head = self.kitchen.crew(slug, number, files, checks=(check,))
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

    def github(self, check=None):
        """GitHub after an update of a branch: the new head, whose check ran over today's main
        and ended as `check` says, or by default failed where its tree is broken."""
        for slug, pull in self.kitchen.pulls.items():
            head = git(self.kitchen.origin, "rev-parse", f"refs/heads/{slug}")
            if head == pull["headRefOid"] and not check:
                continue
            listed = git(self.kitchen.origin, "ls-tree", "-r", "--name-only", head).split()
            broken = any(path.startswith("tests/broken-") for path in listed)
            ran = check or (FAILED_AFTER if broken else GREEN)
            pull |= {"headRefOid": head, "statusCheckRollup": merge.rollup([ran])}
        listed = [
            pull
            for slug, pull in self.kitchen.pulls.items()
            if not any(line.startswith(f"merged {pull['number']} ") for line in self.said)
        ]
        (self.kitchen.home.stub / "list.json").write_text(json.dumps(listed))

    def run(self, *flags):
        """One run of `jmerge`. Each line is read as jbus reads it, and what jbus would tell a
        crew is kept."""
        said = self.kitchen.run(*flags)
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
    breaks a test of its own, go red over it, and wait on main's fix. Then main is fixed."""
    heads = [
        replay.crew("one", 333, {"one.txt": "ours\n"}),
        replay.crew("two", 340, {"two.txt": "ours\n"}),
        replay.crew("three", 341, {"a.txt": "ours\n" + LINES}),
        replay.crew("broken", 339, {"tests/broken-its-own": ""}),
    ]
    red = ready.MAIN_RED.format(sha=replay.main_at(WHOLE_TREE, BROKE, "failed")[:12])
    assert replay.run() == [
        f"wait {number} {url(number)}: {red}" for number in (333, 339, 340, 341)
    ]
    fix = replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    return heads, fix


def test_the_replay_every_pull_request_red_only_on_its_base_merges_and_none_runs_here(replay):
    """With a `fresh-check` file, GitHub updates each branch and no suite runs on this machine:
    the change broken on its own fails at its updated head, as its own, and waits."""
    (_, _, _, broken), fix = red_then_fixed(replay)
    replay.passes()
    assert merged(replay.said) == [333, 340, 341]
    carried = [line for line in replay.said if line.startswith("merged ")]
    assert all(", review carried over: range-diff " in line for line in carried), carried
    assert sorted(replay.updated()) == ["333", "339", "340", "341"]
    assert all(len(replay.journal(number)) == 1 for number in (333, 339, 340, 341))
    assert replay.said[-1] == f"wait 339 {url(339)}: check has failed"
    assert replay.told == []
    assert replay.kitchen.at_main("one.txt") == "ours"
    assert not (replay.kitchen.home.state / "fresh.json").exists()


def test_with_no_fresh_check_file_github_s_update_alone_moves_it_on(tmp_path):
    replay = Replay(tmp_path, fresh=False)
    (one, *_), fix = red_then_fixed(replay)
    said = replay.run()
    assert f"wait 333 {url(333)}: {ASKED.format(tip=fix[:12])}" in said
    assert sorted(replay.updated()) == ["333", "339", "340", "341"]
    replay.passes(2)
    assert merged(replay.said) == [333, 340, 341]
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


@pytest.mark.parametrize("status", ["502", "429", "403"])
def test_a_failure_to_ask_github_is_asked_again_on_the_next_run(tmp_path, status):
    """A 5xx or a rate limit is no answer about the branch: it keeps no record, and the next run
    asks again."""
    replay = Replay(tmp_path, fresh=False)
    (replay.kitchen.home.stub / "down").write_text(status)
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


def test_a_red_pull_request_short_of_anything_else_says_so_and_asks_nothing(replay):
    """The change's one safety fact: only a pull request whose single shortfall is its failed
    check is given its base. One whose queue row is held waits on its row, with no update asked
    of GitHub."""
    order.queue_of(replay.kitchen.home, [order.row("one", pr="#333", held=True)])
    replay.crew("one", 333, {"one.txt": "ours\n"})
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    assert replay.run() == [f"wait 333 {url(333)}: {ready.ROW_HELD}"]
    assert replay.updated() == [] and not (replay.kitchen.home.state / "fresh.json").exists()
    order.queue_of(replay.kitchen.home, [order.row("one", pr="#333")])
    fix = git(replay.kitchen.origin, "rev-parse", "refs/heads/main")
    assert replay.run() == [f"wait 333 {url(333)}: {ASKED.format(tip=fix[:12])}"]


def test_a_red_base_is_not_judged_again_until_it_is_green(replay):
    replay.crew("one", 333, {"one.txt": "ours\n"})
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    red = replay.main_at({"b.txt": "theirs\n"}, FIXED, "failed")
    assert replay.run() == [f"wait 333 {url(333)}: {ready.MAIN_RED.format(sha=red[:12])}"]
    assert replay.updated() == [] and not (replay.kitchen.home.state / "fresh.json").exists()


def test_a_failed_check_over_a_base_that_has_not_moved_since_is_the_pull_request_s_own(replay):
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    replay.main_at({"c.txt": "theirs\n"}, "2026-10-23T12:30:00Z", "green")
    replay.crew("one", 333, {"one.txt": "ours\n"})
    assert replay.run() == [f"wait 333 {url(333)}: check has failed"]
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
    reasons = (ready.BASE_MERGE_ASKED, ready.BASE_MERGE_REFUSED, ready.BASE_MERGE_DUE)
    for reason in (*reasons, ready.BASE_MOVED_ASKED, ready.BASE_MOVED_DUE, ready.UNMERGED):
        filled = reason.format(base="main", tip="0123456789ab", why="it said no")
        assert jbus_merge.step(f"wait: {filled}") == "check"
        assert rebase.asks(f"wait 333 {url(333)}: {filled}") is None


PASSED_BEFORE = {**merge.PASSED, "startedAt": STARTED}
PENDING = {**merge.RUNNING, "startedAt": "2099-01-01T00:00:00Z"}
FAILED_AFTER = {**merge.FAILED, "startedAt": "2099-01-01T00:00:00Z"}
REQUIRED = "check\nborders\nmacos\n"
MACOS_RED = {**merge.run("FAILURE", "macos"), "startedAt": STARTED}
MOVED = "GitHub was asked to merge main at {tip} into it: main moved after its check started"


@pytest.fixture
def moved(tmp_path):
    """A repo with a `fresh-check` file whose command takes a stand-in test slot, and a pull
    request that passed its check before main changed its own file under it."""
    replay = Replay(tmp_path, fresh=False)
    slot = replay.kitchen.home.stub / "slot-taken"
    (replay.kitchen.home.state / "fresh-check").write_text(f"touch {slot}\n")
    head = replay.crew("one", 333, {"a.txt": "ours\n" + LINES}, check=PASSED_BEFORE)
    tip = replay.main_at({"a.txt": LINES + "theirs\n"}, FIXED, "green")
    replay.slot = slot
    return replay, head, tip


def test_main_moving_under_a_green_pull_request_asks_github_and_runs_no_local_suite(moved):
    """The base moved after the check passed: `jmerge` asks GitHub to merge it into the branch,
    holds while GitHub's check runs at the updated head, and merges once it passed there. No
    local suite runs, and `fresh.json` gets no run."""
    replay, head, tip = moved
    assert replay.run() == [f"wait 333 {url(333)}: {MOVED.format(tip=tip[:12])}"]
    assert replay.updated() == ["333"]
    replay.github(PENDING)
    assert replay.run() == [f"wait 333 {url(333)}: check has not passed"]
    replay.github(GREEN)
    (line,) = replay.run()
    assert line.startswith("merged 333 "), line
    assert replay.updated() == ["333"]
    assert replay.kitchen.at_main("a.txt") == "ours\n" + LINES + "theirs"
    assert not replay.slot.exists()
    assert not (replay.kitchen.home.state / "fresh.json").exists()


def test_a_failed_check_at_the_updated_head_holds_it(moved):
    replay, head, tip = moved
    replay.run()
    replay.github(FAILED_AFTER)
    for _ in range(2):
        assert replay.run() == [f"wait 333 {url(333)}: check has failed"]
    assert replay.updated() == ["333"]
    assert not replay.slot.exists()


RUNS = """\
    "run list") cat "$STUB/runs-$4-$6.json" ;;
    "run view") cat "$STUB/log-$3.txt" ;;
"""
OURS = "features/x/tests/test_ours.py::test_its_own"
THEIRS = "features/y/tests/test_theirs.py::test_main_broke"


def checked(replay, branch, runs, check="check"):
    """`gh run list` of the runs of a branch's check, newest first, and each failed run's log:
    a run is (its id, its start, the pytest ids it failed)."""
    stub = replay.kitchen.home.stub
    listed = [
        {
            "databaseId": number,
            "status": "completed",
            "conclusion": "failure" if failed else "success",
            "createdAt": at,
        }
        for number, at, failed in reversed(runs)
    ]
    (stub / f"runs-{branch}-{check}.json").write_text(json.dumps(listed))
    for number, at, failed in runs:
        lines = [f"check 1 of 4\tset up\t{at} PASSED is not an id"]
        lines += [
            f"check 2 of 4\tmake check-fast\t{at} FAILED {one} - assert 2 == 1" for one in failed
        ]
        (stub / f"log-{number}.txt").write_text("\n".join(lines) + "\n")


@pytest.mark.parametrize(
    ("second", "mains", "asks"),
    [
        ((OURS,), (THEIRS,), False),
        (("features/x/tests/test_ours.py::test_another",), (THEIRS,), True),
        ((OURS,), (OURS,), True),
    ],
    ids=["same-test-twice", "another-test", "main-failed-it-too"],
)
@pytest.mark.parametrize(
    ("check", "on_main"),
    [("check", True), ("macos", True), ("macos", False)],
    ids=["check", "a-side-check-main-runs", "a-side-check-main-never-runs"],
)
def test_a_pull_request_red_twice_on_the_same_test_of_its_own_is_not_given_main_again(
    tmp_path, second, mains, asks, check, on_main
):
    """2026-10-26, #494: its check failed one test of its own over a main red on another test,
    GitHub merged main into it, and it failed that same test again, nine times. Once its last
    two check runs failed a same pytest id that main's check at neither run's base failed,
    the branch is not updated again: it keeps its red line. A second failure on another test,
    or on a test main also failed, is still given today's main. Each required check is read by
    its own runs: #529's was macos, while its check passed. A check main never runs, as jstack's
    macos runs on pull requests alone, has no run of main to tell its own tests from main's, so it
    is given today's main: a test main broke on macOS alone would otherwise hold it for good."""
    replay = Replay(tmp_path, fresh=False)
    gh = replay.kitchen.home.stub / "gh"
    gh.write_text(gh.read_text().replace("    *) exit 64 ;;\n", RUNS + "    *) exit 64 ;;\n"))
    if check == "check":
        replay.crew("one", 333, {"one.txt": "ours\n"})
    else:
        (replay.kitchen.home.state / "required-checks").write_text(REQUIRED)
        replay.crew("one", 333, {"one.txt": "ours\n"}, check=PASSED_BEFORE)
        pull = replay.kitchen.pulls["one"]
        pull["statusCheckRollup"] = merge.rollup([PASSED_BEFORE, MACOS_RED])
        replay.kitchen.brief("one", pull["headRefOid"])
        checked(replay, "one", [(90, "2026-10-23T12:00:00Z", ()), (91, STARTED, ())])
    if on_main:
        mains = [(70, "2026-10-23T11:30:00Z", mains), (71, "2026-10-23T12:30:00Z", ())]
        checked(replay, "main", mains, check)
    else:
        checked(replay, "main", [], check)
        asks = True
    checked(replay, "one", [(80, "2026-10-23T12:00:00Z", (OURS,)), (81, STARTED, second)], check)
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    fix = replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    said = replay.run()
    if asks:
        assert said == [f"wait 333 {url(333)}: {ASKED.format(tip=fix[:12])}"]
        assert replay.updated() == ["333"]
    else:
        assert said == [f"wait 333 {url(333)}: {check} has failed"]
        assert replay.updated() == []
        assert replay.run() == said and replay.updated() == []


def side(tmp_path):
    """2026-10-27, #529: a pull request reviewed clean at its head, then fixed for a failed check
    by a push of its crew's, whose check and borders then passed and whose required macos check
    failed on a test main was red on, in a repo that requires check, borders and macos."""
    replay = Replay(tmp_path, fresh=False)
    (replay.kitchen.home.state / "required-checks").write_text(REQUIRED)
    reviewed = replay.crew("one", 529, {"one.txt": "ours\n"}, check=PASSED_BEFORE)
    tree = replay.kitchen.tmp / "trees" / "one"
    write(tree, {"one.txt": "ours, fixed\n"})
    git(tree, "commit", "-q", "-am", "fix")
    git(tree, "push", "-q")
    head = git(tree, "rev-parse", "HEAD")
    replay.kitchen.pulls["one"] |= {
        "headRefOid": head,
        "statusCheckRollup": merge.rollup([PASSED_BEFORE, MACOS_RED]),
    }
    replay.kitchen.brief("one", reviewed)
    replay.main_at(WHOLE_TREE, BROKE, "failed")
    fix = replay.main_at({path: None for path in WHOLE_TREE}, FIXED, "green")
    return replay, head, fix


def test_a_pull_request_red_only_on_a_side_check_says_what_else_it_is_short_of(tmp_path):
    """#529 waited ten hours on "macos has not passed" after main moved, and nobody was told
    anything: judged again as if macos had passed, it was short of a scoped review of the push
    after its review, and `jmerge` kept the red line in its place. Its line is what it is short
    of, so jbus asks its crew for that review, and no crew is told to rebase."""
    replay, head, fix = side(tmp_path)
    for _ in range(3):
        (line,) = replay.run()
        assert "macos has not passed" not in line
        assert "changed the content after its review; scoped review of" in line, line
    assert replay.updated() == []
    assert replay.told == [("rereview", 529, head)]
    replay.kitchen.brief("one", head)
    for _ in range(3):
        assert replay.run() == [f"wait 529 {url(529)}: {ASKED.format(tip=fix[:12])}"]
    assert replay.updated() == ["529"]
    assert len(replay.journal(529)) == 1
    assert replay.told == [("rereview", 529, head)]
