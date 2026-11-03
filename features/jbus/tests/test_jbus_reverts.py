"""A red main holds no pull request, and jbus reverts its one clear culprit (`jbus.reverts`, Josh's
pick of 2026-11-02, "Yes, guess-free reverts").

A red tip that is a briefed merge's commit, red after its one rerun (#672) with a green commit
under it, gets a revert pull request from `gh pr revert`, which `jmerge` merges with no review
(`features/jmerge/tests/test_jmerge_red_main.py`). Where the culprit is not clear, or the revert
would be wrong, nothing is reverted and the red gets the fix row it got before.

Like `test_jbus_watch.py`, the tests run the real pass against the fakes, on a real commit of
origin's main, which `mainmoved.tell` reads for the tests that failed there."""

import json
from datetime import timedelta

import pytest

import jbus.queue
from jbus import reverts
from jbus.watch import World
from jmerge import mainjson
from jmerge import reverts as kept
from test_jbus_chains import queue_add
from test_jbus_kitchen import NOW, iso
from test_jbus_main_moved import move, tip
from test_jbus_queue import go as queue_go
from test_jbus_watch import main_red

TEST = "features/a/tests/test_a.py::test_x"
OTHER = "features/a/tests/test_a.py::test_y"
LOG = f"FAILED {TEST} - assert 1\n= 1 failed, 9 passed in 2.0s =\n"
DONE = {"status": "completed"}


def brief(kitchen, slug, number):
    result = f"\n## Result\nStatus: done\nBranch: {slug}   Pull request: {url(number)}\n"
    kitchen.brief(slug, f"Thread: mcp:{slug}-crew\nHome: root\n{result}")


def url(number):
    return f"https://example.test/pull/{number}"


def red_merges(kitchen, *merges):
    """Land one red merge on origin's main for each `(slug, number, title)` of `merges`, oldest
    first, on a green commit, each red again after its one rerun with `TEST` failed in its log.
    Return the red tips, oldest first."""
    kitchen.quiet()
    green = tip(kitchen)
    reds, merged, runs, pushed = [], [], {green: [{**DONE, "conclusion": "success"}]}, {}
    for n, (slug, number, title) in enumerate(merges):
        brief(kitchen, slug, number)
        red = move(kitchen, "failure")
        reds.append(red)
        ago = timedelta(minutes=20 - n)
        merged.append(kitchen.merged(slug, number, red, ago=ago, title=title))
        runs[red] = [{**DONE, "conclusion": "failure", "name": "check", "id": 91 + n}]
        pushed[red] = [{**DONE, "id": 501 + n, "conclusion": "failure", "run_attempt": 2}]
    kitchen.set("merged.json", merged)
    commits = [
        kitchen.commit(
            red, f"{one[2] or 'feat: ' + one[0]} (#{one[1]})", ago=timedelta(minutes=20 - n)
        )
        for n, (red, one) in enumerate(zip(reds, merges, strict=True))
    ]
    kitchen.set(
        "commits.json", [*reversed(commits), kitchen.commit(green, "older", ago=timedelta(hours=2))]
    )
    kitchen.set("check-runs.json", runs)
    kitchen.set("push-runs.json", pushed)
    kitchen.set("logs.json", {str(91 + n): LOG for n in range(len(merges))})
    return reds


def passes(kitchen, count=3):
    for minutes in range(count):
        kitchen.poll(NOW + timedelta(minutes=3 * minutes))


def asked(kitchen, command):
    log = kitchen.stub / "gh.log"
    return [line for line in log.read_text().splitlines() if line.startswith(command)]


def test_one_clear_culprit_red_after_its_one_rerun_is_reverted_and_its_crew_and_home_told(kitchen):
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    before = tip(kitchen)
    passes(kitchen)
    (revert,) = asked(kitchen, "pr revert")
    assert revert.startswith(f"pr revert {url(7)} --body ")
    made = kept.read(kitchen.state)
    assert made == {red: kept.Revert(red, "alpha", "revert-7-alpha", "e" * 40, made[red].pull)}
    text = (kitchen.home / "tasks" / "revert-7-alpha.md").read_text()
    assert f"Branch: revert-7-alpha   Pull request: {made[red].pull}" in text
    assert "Home: root" in text
    assert main_red(kitchen) == []
    assert [line for line in kitchen.lines("revert") if line.startswith("revert alpha: ")]
    sent = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]
    told = [given for given in sent if given["threadId"] == "mcp:alpha-crew"]
    assert len(told) == 1 and made[red].pull in told[0]["message"]
    assert tip(kitchen) == before, "a revert is a new pull request, never a push to main"
    assert not [line for line in asked(kitchen, "api") if "git/refs" in line]


def test_the_revert_of_a_red_tip_is_opened_once(kitchen):
    red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen, 6)
    assert len(asked(kitchen, "pr revert")) == 1
    assert main_red(kitchen) == []


def test_two_overlapping_reds_revert_nothing_and_file_one_row_naming_both_tips(kitchen):
    """beta landed on alpha's red and failed a test alpha's red did not: a second break, so
    neither merge is the one clear culprit."""
    first, second = red_merges(kitchen, ("alpha", 7, None), ("beta", 8, None))
    kitchen.set("logs.json", {"91": LOG, "92": f"FAILED {TEST}\nFAILED {OTHER}\n= 2 failed =\n"})
    passes(kitchen)
    assert asked(kitchen, "pr revert") == []
    (row,) = main_red(kitchen)
    assert row["slug"] == f"{mainjson.FIX}{second[:12]}"
    text = (kitchen.home / "tasks" / f"{row['slug']}.md").read_text()
    task = next(line for line in text.splitlines() if line.startswith("Task:"))
    assert reverts.Keep.OVERLAP in task
    assert first[:12] in task and second[:12] in task


def test_a_red_two_merges_made_together_reverts_nothing_and_files_its_row(kitchen):
    """#864 merged a minute before #866 and renamed a helper #866's new tests still used: main
    was green at #864, and #866's own check passed over a main that lacked it. Neither merge is
    the one clear culprit, so the red gets its fix row and no revert."""
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    under = json.loads((kitchen.stub / "commits.json").read_text())[-1]["sha"]
    kitchen.set("compare.json", {f"{under}...{'d' * 40}": {"status": "diverged"}})
    passes(kitchen)
    assert asked(kitchen, "pr revert") == []
    assert kept.read(kitchen.state) == {}
    (row,) = main_red(kitchen)
    assert row["slug"] == f"{mainjson.FIX}{red[:12]}"
    text = (kitchen.home / "tasks" / f"{row['slug']}.md").read_text()
    assert reverts.Keep.SKEW in text


def fixed_first(kitchen):
    """Main red at alpha's merge with its revert open, then a fix row's merge on top whose
    check passes. Return the red tip, the revert on record and the green fix."""
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen)
    made = kept.read(kitchen.state)[red]
    fixed = move(kitchen, "success")
    commits = json.loads((kitchen.stub / "commits.json").read_text())
    kitchen.set(
        "commits.json", [kitchen.commit(fixed, "fix: main (#878)", ago=timedelta(0))] + commits
    )
    pushed = json.loads((kitchen.stub / "push-runs.json").read_text())
    kitchen.set("push-runs.json", {**pushed, fixed: [{**DONE, "id": 601, "conclusion": "success"}]})
    return red, made, fixed


def test_a_revert_jbus_opened_is_closed_once_main_is_green_without_it(kitchen):
    """A fix row lands first and main's check passes at it: the revert jbus opened would only
    sit in conflict with main, so jbus closes it, with a comment that names the green commit.
    While it is open, its record stays."""
    red, made, fixed = fixed_first(kitchen)
    assert list(kept.read(kitchen.state)) == [red], "an open revert keeps its record"
    kitchen.poll(NOW + timedelta(minutes=30))
    (closed,) = asked(kitchen, "pr close")
    assert closed.startswith(f"pr close {made.pull} --comment ")
    assert fixed[:12] in closed
    opened = json.loads((kitchen.stub / "open.json").read_text())
    assert made.pull not in [pull["url"] for pull in opened]
    assert list(kept.read(kitchen.state)) == [red], "the pass that closes it keeps its record"


def test_a_closed_revert_whose_culprit_is_over_is_dropped_on_the_next_pass(kitchen):
    """alpha merged, has no pull request open, no thread unsettled and no row: it merges nothing
    more, so the record of its closed revert holds nothing and goes, and a later red that alpha's
    slug names is not held as `TWICE`."""
    red, _, _ = fixed_first(kitchen)
    kitchen.poll(NOW + timedelta(minutes=30))
    kitchen.poll(NOW + timedelta(minutes=33))
    assert kept.read(kitchen.state) == {}


def test_a_closed_revert_whose_culprit_still_has_a_thread_keeps_its_record(kitchen):
    """alpha's crew is still at work, told to bring its change back: alpha can merge again, so
    the record stays, and the row is still never reverted twice."""
    red, _, _ = fixed_first(kitchen)
    kitchen.t3.thread("alpha")
    for minutes in (30, 33, 36):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert list(kept.read(kitchen.state)) == [red]


def test_over_needs_no_open_pull_request_no_live_thread_and_a_final_row():
    world = World(open={}, threads={})
    assert reverts.over("alpha", world, [])
    assert reverts.over("alpha", world, [{"slug": "alpha", "status": "merged"}])
    assert not reverts.over("alpha", world, [{"slug": "alpha", "status": "queued"}])
    assert not reverts.over("alpha", World(open={"alpha": {}}), [])
    assert not reverts.over("alpha", World(threads={"alpha": [{}]}), [])


def test_a_revert_that_goes_red_is_not_reverted(kitchen):
    (red,) = red_merges(kitchen, ("revert-7-alpha", 9, 'Revert "feat: alpha"'))
    passes(kitchen)
    assert asked(kitchen, "pr revert") == []
    assert [row["slug"] for row in main_red(kitchen)] == [f"{mainjson.FIX}{red[:12]}"]


def flaky_elsewhere(kitchen, beside=("gamma", [TEST])):
    """`jbus ci`'s ledger: `TEST` failed this week on beta, and `beside` names the other branch's
    red and its tests, by default `TEST` on gamma: two other branches, with no runner fault."""
    at = iso(NOW - timedelta(days=1))
    job = {
        "event": "pull_request",
        "kind": "local",
        "conclusion": "failure",
        "steps": 3,
        "created": at,
        "started": at,
        "completed": at,
        "sha": "a" * 40,
        "tests": [TEST],
        "signs": [],
        "attempt": 1,
        "name": "check",
    }
    jobs = [
        {**job, "run": 1, "job": 11, "branch": "beta", "tests": [TEST, OTHER]},
        {**job, "run": 2, "job": 12, "branch": beside[0], "tests": beside[1]},
    ]
    kitchen.state.mkdir(parents=True, exist_ok=True)
    (kitchen.state / "ci.jsonl").write_text("".join(json.dumps(one) + "\n" for one in jobs))


def test_a_tip_whose_failed_tests_are_flakes_by_jbus_ci_s_rule_is_not_reverted(kitchen):
    flaky_elsewhere(kitchen)
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen)
    assert asked(kitchen, "pr revert") == []
    assert [row["slug"] for row in main_red(kitchen)] == [f"{mainjson.FIX}{red[:12]}"]


@pytest.mark.parametrize(
    "beside", [("gamma", [OTHER]), ("alpha", [TEST])], ids=["one-branch", "own-branch"]
)
def test_a_tip_whose_failed_test_failed_on_one_other_branch_alone_is_reverted(kitchen, beside):
    """`TEST` shares beta's red with `OTHER`, a flake of two branches, or its second branch is
    alpha's own: it failed on one branch besides the culprit's, so it is no flake."""
    flaky_elsewhere(kitchen, beside)
    red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen)
    assert len(asked(kitchen, "pr revert")) == 1
    assert main_red(kitchen) == []


def test_a_row_is_never_reverted_twice(kitchen):
    made = kept.Revert("0" * 40, "alpha", "revert-6-alpha", "e" * 40, url(6))
    kitchen.state.mkdir(parents=True, exist_ok=True)
    (kitchen.state / kept.NAME).write_text(json.dumps({made.red: kept.record(made)}))
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen)
    assert asked(kitchen, "pr revert") == []
    assert [row["slug"] for row in main_red(kitchen)] == [f"{mainjson.FIX}{red[:12]}"]


def test_a_revert_github_does_not_open_files_the_row(kitchen):
    (kitchen.stub / "gh-no-revert").write_text("GraphQL: not allowed\n")
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen)
    assert kept.read(kitchen.state) == {}
    assert [row["slug"] for row in main_red(kitchen)] == [f"{mainjson.FIX}{red[:12]}"]
    assert [line for line in kitchen.lines("condition") if "its revert was not opened" in line]


def test_a_crew_the_message_could_not_reach_is_told_by_a_later_pass(kitchen):
    red_merges(kitchen, ("alpha", 7, None))
    kitchen.t3.down.add("demo")
    passes(kitchen)
    assert kept.read(kitchen.state)
    kitchen.t3.down.discard("demo")
    kitchen.poll(NOW + timedelta(minutes=30))
    kitchen.poll(NOW + timedelta(minutes=33))
    sent = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]
    told = [given for given in sent if given["threadId"] == "mcp:alpha-crew"]
    assert len(told) == 1 and "revert" in told[0]["message"]


def test_a_crew_told_of_a_revert_that_merged_is_not_told_again_once_its_mark_is_pruned(kitchen):
    """red-main-no-hold F20: the daily prune forgets the told mark of a finished row, while the
    revert's record stays, so a merged revert must not be told again."""
    from jbus.wake import _prunable

    (red,) = red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen)
    made = kept.read(kitchen.state)[red]
    pulls = json.loads((kitchen.stub / "open.json").read_text())
    kitchen.set("open.json", [one for one in pulls if one["url"] != made.pull])
    merged = json.loads((kitchen.stub / "merged.json").read_text())
    landed = [dict(one, mergedAt=iso(NOW)) for one in pulls if one["url"] == made.pull]
    kitchen.set("merged.json", [*merged, *landed])
    sent = json.loads((kitchen.state / "sent.json").read_text())
    (kitchen.state / "sent.json").write_text(
        json.dumps([key for key in sent if not _prunable(key, {"alpha"})])
    )
    kitchen.poll(NOW + timedelta(minutes=30))
    kitchen.poll(NOW + timedelta(minutes=33))
    sent = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]
    told = [given for given in sent if given["threadId"] == "mcp:alpha-crew"]
    assert len(told) == 1 and made.pull in told[0]["message"]


def test_a_revert_github_opened_but_did_not_describe_is_taken_up_and_not_opened_again(kitchen):
    """`gh pr view` gives no answer once the revert opened: the next pass finds it by its branch
    (`gh pr list --head`), keeps it, and opens no second one."""
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    (kitchen.stub / "gh-view-down").write_text("no answer\n")
    passes(kitchen, 4)
    assert len(asked(kitchen, "pr revert")) == 1
    assert list(kept.read(kitchen.state)) == [red]
    assert [line for line in kitchen.lines("condition") if "does not say its branch yet" in line]
    assert main_red(kitchen) == []


def test_a_red_whose_tests_stay_unread_gets_its_row_once_the_wait_is_over(kitchen):
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    kitchen.set("logs.json", {"91": None})
    passes(kitchen)
    assert main_red(kitchen) == []
    kitchen.poll(NOW + reverts.READ_WAIT)
    (row,) = main_red(kitchen)
    assert row["slug"] == f"{mainjson.FIX}{red[:12]}"
    text = (kitchen.home / "tasks" / f"{row['slug']}.md").read_text()
    assert reverts.Keep.NOT_READ in text
    assert asked(kitchen, "pr revert") == []


def test_a_revert_that_goes_red_gets_the_fix_row(kitchen):
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen)
    assert main_red(kitchen) == []
    made = kept.read(kitchen.state)[red]
    pulls = json.loads((kitchen.stub / "open.json").read_text())
    failed = [{"status": "COMPLETED", "conclusion": "FAILURE", "name": "check"}]
    for pull in pulls:
        if pull["url"] == made.pull:
            pull["statusCheckRollup"] = failed
    kitchen.set("open.json", pulls)
    kitchen.poll(NOW + timedelta(minutes=30))
    (row,) = main_red(kitchen)
    text = (kitchen.home / "tasks" / f"{row['slug']}.md").read_text()
    assert f"its revert {made.pull} has a failed check" in text
    assert len(asked(kitchen, "pr revert")) == 1


def test_a_revert_goes_to_the_home_s_digest(kitchen):
    import jbus
    from jbus import digest

    red_merges(kitchen, ("alpha", 7, None))
    passes(kitchen)
    said = digest.build(jbus.load(), since=NOW - timedelta(hours=1), now=NOW + timedelta(hours=1))
    (routine,) = [one for one in said["projects"]["demo"]["routine"] if one["event"] == "revert"]
    assert routine["slug"] == "alpha" and routine["line"].startswith("revert alpha: main red at ")


def test_a_plain_launch_waits_on_a_red_main(kitchen):
    """While main is red, `jbus.dispatch` launches only a row that fixes main or launches
    stacked (`test_jbus_red_main.py`): a plain row waits for green."""
    kitchen.quiet()
    red = move(kitchen, "failure")
    record = mainjson.record(main=red, at=iso(NOW), check="failed", broken=red, failed=[TEST])
    (kitchen.state / mainjson.NAME).write_text(json.dumps(record))
    assert queue_add(kitchen, "beta")[0] == 0
    assert queue_go(kitchen, "beta")[0] == 0
    kitchen.poll(NOW + timedelta(minutes=1))
    assert kitchen.t3.launches == []
    (beta,) = [row for row in jbus.queue.load(kitchen.state) if row["slug"] == "beta"]
    assert beta["why"] == "main is red: waits for green"


def test_the_rule_names_one_reason_for_each_red_it_does_not_revert():
    pull = {"number": 7, "title": "feat: alpha", "url": url(7)}
    one = reverts.Red("r" * 40, ["r" * 40], pull, "alpha", [TEST])
    made = {"o" * 40: kept.Revert("o" * 40, "beta", "revert-5-beta", "e" * 40, url(5))}
    assert reverts.culprit(one, {}, ()) == reverts.Culprit("r" * 40, "alpha", pull)
    cases = {
        reverts.Keep.OPENED: (one, {one.tip: made["o" * 40]}, ()),
        reverts.Keep.OVERLAP: (
            reverts.Red(one.tip, ["r" * 40, "q" * 40], pull, "alpha", [TEST]),
            {},
            (),
        ),
        reverts.Keep.UNBRIEFED: (reverts.Red(one.tip, [one.tip], None, "", [TEST]), {}, ()),
        reverts.Keep.OF_A_REVERT: (
            reverts.Red(one.tip, [one.tip], pull, "revert-5-beta", [TEST]),
            made,
            (),
        ),
        reverts.Keep.TWICE: (reverts.Red(one.tip, [one.tip], pull, "beta", [TEST]), made, ()),
        reverts.Keep.UNREAD: (reverts.Red(one.tip, [one.tip], pull, "alpha", None), {}, ()),
        reverts.Keep.FLAKES: (one, {}, (TEST,)),
    }
    for why, (red, kept_reverts, flakes) in cases.items():
        assert reverts.culprit(red, kept_reverts, flakes) == why, why
    assert reverts.culprit(reverts.Red(one.tip, [one.tip], pull, "alpha", []), {}, (TEST,)) == (
        reverts.Culprit(one.tip, "alpha", pull)
    )
