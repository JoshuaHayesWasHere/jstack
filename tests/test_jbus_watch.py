"""`jbus.watch` reads what changed since the last pass: a merge, a thread past its time or
ended with no Result, a check on main that failed or was cancelled, a revert, and a
condition jbus cannot judge, each said once. Run as `tests/test_jbus_kitchen.py` runs: the
real pass, against the fakes.
"""

from datetime import timedelta

import pytest

from test_jbus_kitchen import NOW, RESULT, TOKEN


def test_a_merge_is_one_line_with_its_pull_request_and_commit(kitchen):
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "abcdef0123456789" + "0" * 24)])
    kitchen.poll()
    assert kitchen.lines("merged") == ["merged alpha #7 abcdef012345"]
    assert kitchen.events("merged")[0]["text"].startswith("## Result\nStatus: done")


def test_a_merge_first_seen_days_later_is_still_sent_once(kitchen):
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40, ago=timedelta(days=3))])
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines("merged") == ["merged alpha #7 aaaaaaaaaaaa"]


def test_a_first_pass_that_could_not_ask_t3_code_is_not_the_first_whole_pass(kitchen):
    """What was already merged stays unsent until one pass has asked everything."""
    kitchen.brief("alpha", RESULT)
    kitchen.brief("beta", RESULT)
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    stored = kitchen.config_dir / "t3.json"
    good = stored.read_text()
    kitchen.write(stored, good.replace(TOKEN, "a-token-that-ran-out"))
    kitchen.poll()
    kitchen.write(stored, good)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines("merged") == []
    kitchen.set("merged.json", [kitchen.merged("beta", 8, "b" * 40)])
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kitchen.lines("merged") == ["merged beta #8 bbbbbbbbbbbb"]


def test_a_merge_with_no_merge_commit_is_not_reverted_by_every_hyphen(kitchen):
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    merged = {**kitchen.merged("alpha", 7, ""), "mergeCommit": None}
    kitchen.set("merged.json", [merged])
    kitchen.set("commits.json", [kitchen.commit("1" * 40, "fix: a follow-up - with a hyphen")])
    kitchen.poll()
    assert kitchen.lines("retro") == []


def test_what_was_merged_before_the_first_pass_is_not_sent(kitchen):
    kitchen.brief("alpha", RESULT)
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines("merged") == [] and kitchen.lines("result") == []


@pytest.mark.parametrize(
    "timebox, age, line",
    [
        ("TIMEBOX: 2 hours of crew time.\n", timedelta(hours=3, minutes=10), "running 3h"),
        ("TIMEBOX: 6 hours of crew time.\n", timedelta(hours=5), None),
        ("", timedelta(hours=4, minutes=1), "running 4h"),
        ("", timedelta(hours=3, minutes=59), None),
    ],
)
def test_a_thread_running_past_its_timebox_is_stale(kitchen, timebox, age, line):
    kitchen.brief("alpha", timebox)
    kitchen.t3.thread("alpha", "running", age=age)
    kitchen.poll()
    expected = [f"stale alpha: {line}, past its TIMEBOX"] if line else []
    assert kitchen.lines("stale") == expected


def test_a_thread_waiting_on_a_request_for_half_an_hour_is_stale(kitchen):
    kitchen.brief("alpha")
    kitchen.brief("beta")
    kitchen.t3.thread("alpha", "waiting", idle=timedelta(minutes=31))
    kitchen.t3.thread("beta", "waiting", idle=timedelta(minutes=29))
    kitchen.poll()
    assert kitchen.lines("stale") == ["stale alpha: waiting on a request 31 min"]


@pytest.mark.parametrize("status", ["failed", "interrupted", "cancelled", "completed"])
def test_a_thread_that_ended_with_no_result_is_stale(kitchen, status):
    kitchen.brief("alpha")
    kitchen.brief("beta", RESULT)
    kitchen.set("open.json", [kitchen.opened("beta", 9)])
    kitchen.t3.thread("alpha", status)
    kitchen.t3.thread("beta", status)
    kitchen.poll()
    assert kitchen.lines("stale") == [f"stale alpha: thread {status} with no Result"]


def test_a_failed_check_on_main_after_a_merge_names_the_slug_and_the_merges_since_green(kitchen):
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    red, between, green = "d" * 40, "e" * 40, "f" * 40
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, red, ago=timedelta(minutes=30))])
    commits = [
        kitchen.commit(red, ago=timedelta(minutes=30)),
        kitchen.commit(between, ago=timedelta(hours=1)),
        kitchen.commit(green, ago=timedelta(hours=2)),
    ]
    kitchen.set("commits.json", commits)
    done = {"status": "completed"}
    kitchen.set(
        "check-runs.json",
        {
            red: [{**done, "conclusion": "failure"}],
            between: [{**done, "conclusion": "failure"}],
            green: [{**done, "conclusion": "success"}],
        },
    )
    kitchen.poll()
    line = "retro alpha: main check failed at dddddddddddd, 2 merges since the last green"
    assert kitchen.lines("retro") == [line]


@pytest.mark.parametrize("conclusion", ["failure", "timed_out"])
def test_a_check_on_main_that_failed_beside_a_cancelled_one_is_a_failed_check(kitchen, conclusion):
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    red, done = "d" * 40, {"status": "completed"}
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, red)])
    kitchen.set("commits.json", [kitchen.commit(red)])
    runs = [{**done, "conclusion": "cancelled"}, {**done, "conclusion": conclusion}]
    kitchen.set("check-runs.json", {red: runs})
    kitchen.poll()
    line = "retro alpha: main check failed at dddddddddddd, 1 merges since the last green"
    assert kitchen.lines("retro") == [line]
    assert not [call for call in kitchen.log("gh") if call.startswith("run ")]


def cancelled_on_main(kitchen, check_runs):
    """A merge whose commit on main has these check runs, and a push run that ended cancelled."""
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    sha = "d" * 40
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, sha)])
    kitchen.set("commits.json", [kitchen.commit(sha)])
    kitchen.set("check-runs.json", {sha: check_runs})
    stopped = {"id": 501, "status": "completed", "conclusion": "cancelled", "run_attempt": 1}
    kitchen.set("push-runs.json", {sha: [stopped]})
    return sha, stopped


def reruns(kitchen):
    return [call for call in kitchen.log("gh") if call.startswith("run ")]


@pytest.mark.parametrize(
    "check_runs",
    [[{"status": "completed", "conclusion": "cancelled"}], []],
    ids=["its only check run ended cancelled", "displaced with no job and no check run"],
)
def test_a_cancelled_run_on_main_is_no_failed_check_and_is_run_again_once(kitchen, check_runs):
    sha, stopped = cancelled_on_main(kitchen, check_runs)
    kitchen.poll()
    assert kitchen.lines("retro") == []
    assert reruns(kitchen) == ["run rerun 501"]
    kitchen.set("push-runs.json", {sha: [{**stopped, "status": "queued", "conclusion": None}]})
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.set("push-runs.json", {sha: [{**stopped, "conclusion": "success", "run_attempt": 2}]})
    kitchen.set("check-runs.json", {sha: [{"status": "completed", "conclusion": "success"}]})
    kitchen.poll(NOW + timedelta(minutes=9))
    assert kitchen.lines("retro") == []
    assert reruns(kitchen) == ["run rerun 501"]


@pytest.mark.parametrize(
    "check_runs",
    [[{"status": "completed", "conclusion": "cancelled"}], []],
    ids=["its only check run ended cancelled", "displaced with no job and no check run"],
)
def test_a_run_on_main_cancelled_a_second_time_is_said_once_and_not_run_again(kitchen, check_runs):
    sha, stopped = cancelled_on_main(kitchen, check_runs)
    kitchen.poll()
    kitchen.set("push-runs.json", {sha: [{**stopped, "run_attempt": 2}]})
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kitchen.lines("retro") == ["retro alpha: main check cancelled twice at dddddddddddd"]
    assert reruns(kitchen) == ["run rerun 501"]


def test_a_cancelled_run_on_main_that_github_does_not_run_again_is_said_once(kitchen):
    cancelled_on_main(kitchen, [])
    kitchen.set("gh-no-rerun", "")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    line = "retro alpha: main check cancelled at dddddddddddd, and GitHub did not run it again"
    assert kitchen.lines("retro") == [line]
    assert reruns(kitchen) == ["run rerun 501"]


def test_a_revert_on_main_names_the_slug_it_reverts(kitchen):
    kitchen.brief("alpha", RESULT)
    kitchen.brief("beta", RESULT)
    kitchen.quiet()
    merged = [kitchen.merged("alpha", 7, "a" * 40), kitchen.merged("beta", 8, "b" * 40)]
    kitchen.set("merged.json", merged)
    kitchen.set(
        "commits.json",
        [
            kitchen.commit("1" * 40, f"Revert a change\n\nThis reverts commit {'a' * 40}."),
            kitchen.commit("2" * 40, 'Revert "feat: beta (#8)"'),
            kitchen.commit("a" * 40, "feat: alpha (#7)"),
        ],
    )
    kitchen.poll()
    assert kitchen.lines("retro") == [
        "retro alpha: reverted by 111111111111",
        "retro beta: reverted by 222222222222",
    ]


def test_a_second_pass_repeats_no_finding(kitchen):
    kitchen.brief("alpha", RESULT)
    kitchen.brief("beta")
    kitchen.brief("gamma")
    kitchen.quiet()
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.set("commits.json", [kitchen.commit("1" * 40, f"This reverts commit {'a' * 40}.")])
    kitchen.set("check-runs.json", {"1" * 40: [{"status": "completed", "conclusion": "failure"}]})
    kitchen.t3.thread("beta", "running", age=timedelta(hours=5))
    kitchen.t3.thread("gamma", "failed")
    kitchen.poll()
    first = kitchen.lines()
    assert sorted(event["event"] for event in kitchen.events()) == [
        "merged",
        "retro",
        "retro",
        "stale",
        "stale",
    ]
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(hours=1))
    assert kitchen.lines() == first


def test_a_pull_request_with_no_brief_is_a_gate(kitchen):
    kitchen.set("open.json", [kitchen.opened("stray", 12)])
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines() == ["condition stray: pull request #12 has no brief"]


def test_two_threads_for_one_slug_are_a_gate_and_nothing_else_is_said_of_it(kitchen):
    kitchen.brief("alpha")
    kitchen.t3.thread("alpha", "failed")
    kitchen.t3.thread("alpha", "running", age=timedelta(hours=9))
    kitchen.poll()
    assert kitchen.lines() == ["condition alpha: 2 threads for one slug"]


def test_a_thread_state_jbus_does_not_know_is_a_gate(kitchen):
    kitchen.brief("alpha")
    kitchen.t3.thread("alpha", "rolled_back")
    kitchen.poll()
    assert kitchen.lines() == ["condition alpha: thread state rolled_back jbus does not know"]


def test_a_sign_in_that_no_longer_works_is_a_gate_once_a_day(kitchen):
    stored = kitchen.config_dir / "t3.json"
    kitchen.write(stored, stored.read_text().replace(TOKEN, "a-token-that-ran-out"))
    said = kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert any(line.startswith("wait demo: T3 Code could not be asked") for line in said)
    assert kitchen.lines() == ["condition demo: T3 Code could not be asked"]
    assert kitchen.t3.url not in "".join(said) + kitchen.events()[0]["text"]
    assert kitchen.log("jmerge") == ["", ""]
    kitchen.poll(NOW + timedelta(days=1))
    assert len(kitchen.lines()) == 2
