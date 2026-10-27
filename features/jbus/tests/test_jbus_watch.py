"""`jbus.watch` reads what changed since the last pass, and reports each change once: a merge, a
thread past its time or ended with no Result, a check on main that failed or was cancelled, a
revert, and a condition jbus cannot judge. Like `test_jbus_kitchen.py`, the tests run the real pass
against the fakes.
"""

import json
from datetime import timedelta

import pytest

import jbus.queue
from jbus import cli
from test_jbus_kitchen import NOW, RESULT, TOKEN, iso


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
    """jbus sends nothing of what was already merged until one pass has asked everything."""
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


FULL_JOB = "https://example.test/o/r/actions/runs/77/job/901"


def main_after_alpha(kitchen, conclusion):
    """Merge alpha at a commit on main whose `full` job ended `conclusion`, on top of a green
    commit. The log of that job has two failed tests in pytest's summary."""
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    red, green, done = "d" * 40, "f" * 40, {"status": "completed"}
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, red, ago=timedelta(minutes=30))])
    kitchen.set(
        "commits.json",
        [
            kitchen.commit(red, "feat: alpha (#7)", ago=timedelta(minutes=30)),
            kitchen.commit(green, "feat: older (#6)", ago=timedelta(hours=2)),
        ],
    )
    full = {**done, "conclusion": conclusion, "name": "full", "id": 901, "html_url": FULL_JOB}
    kitchen.set(
        "check-runs.json",
        {
            red: [{**done, "conclusion": "success", "name": "check", "id": 900}, full],
            green: [{**done, "conclusion": "success", "name": "full", "id": 800}],
        },
    )
    summary = (
        "2026-10-16T15:01:02.0000000Z FAILED tests/test_a.py::test_one - AssertionError\n"
        "2026-10-16T15:01:02.0000000Z FAILED tests/test_b.py::test_two[x] - KeyError: 'k'\n"
        "2026-10-16T15:01:03.0000000Z ===== 2 failed, 3000 passed in 120.00s =====\n"
    )
    kitchen.set("logs.json", {"901": summary})
    kitchen.set("commit-files.json", {red: ["src/alpha/a.py"], green: ["src/older.py"]})


def main_red(kitchen):
    return [row for row in jbus.queue.load(kitchen.state) if row["slug"].startswith("main-red-")]


def test_a_failed_full_run_on_main_files_one_unapproved_brief_for_its_fix(kitchen):
    main_after_alpha(kitchen, "failure")
    kitchen.poll()
    brief = kitchen.home / "tasks" / "main-red-dddddddddddd.md"
    text = brief.read_text()
    for said in (
        FULL_JOB,
        "tests/test_a.py::test_one",
        "tests/test_b.py::test_two[x]",
        "dddddddddddd feat: alpha (#7)",
        "\nWhere: `src/alpha/a.py`, `tests/test_a.py`, `tests/test_b.py`\n",
        "\nPlaybook: bug-fix\n",
        "\nSize: S\n",
    ):
        assert said in text
    assert "feat: older (#6)" not in text
    assert jbus.queue.brief_sha(text) == jbus.queue.brief_sha(
        (kitchen.state / "briefs" / "main-red-dddddddddddd.md").read_text()
    )
    assert [(row["slug"], row["approved"]) for row in main_red(kitchen)] == [
        ("main-red-dddddddddddd", "")
    ]
    brief.write_text(text + "Noticed: the home edited it\n")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert brief.read_text().endswith("Noticed: the home edited it\n")
    assert len(main_red(kitchen)) == 1
    line = "retro alpha: main check failed at dddddddddddd, 1 merges since the last green"
    assert kitchen.lines("retro") == [line]


def test_the_brief_for_a_red_main_names_the_push_runs_jobs_and_not_a_dispatched_runs(kitchen):
    main_after_alpha(kitchen, "failure")
    red, browser = "d" * 40, "https://example.test/o/r/actions/runs/78/job/902"
    runs = json.loads((kitchen.stub / "check-runs.json").read_text())
    done = {"status": "completed", "conclusion": "failure"}
    runs[red].append(
        {**done, "name": "browser", "id": 902, "html_url": browser, "check_suite": {"id": 12}}
    )
    kitchen.set("check-runs.json", runs)
    dispatched = {**done, "event": "workflow_dispatch", "check_suite_id": 12}
    kitchen.set("push-runs.json", {red: [dispatched]})
    kitchen.poll()
    text = (kitchen.home / "tasks" / "main-red-dddddddddddd.md").read_text()
    assert FULL_JOB in text and browser not in text


def test_a_pass_that_stopped_before_the_row_was_added_files_it_on_the_next(kitchen):
    main_after_alpha(kitchen, "failure")
    tasks = kitchen.home / "tasks"
    tasks.chmod(0o500)
    kitchen.t3.write(NOW)
    said = []
    try:
        assert cli.poll(jbus.load(), NOW, said.append) == 1
    finally:
        tasks.chmod(0o700)
    assert "pass failed demo: PermissionError" in said[0]
    assert main_red(kitchen) == []
    kitchen.poll(NOW + timedelta(minutes=3))
    assert (tasks / "main-red-dddddddddddd.md").exists()
    assert [row["slug"] for row in main_red(kitchen)] == ["main-red-dddddddddddd"]
    line = "retro alpha: main check failed at dddddddddddd, 1 merges since the last green"
    assert kitchen.lines("retro") == [line]


def test_a_removed_row_is_not_filed_again(kitchen):
    main_after_alpha(kitchen, "failure")
    kitchen.poll()
    removed = ["queue", "remove", "main-red-dddddddddddd", "--by", "user"]
    assert kitchen.main(*removed, "--at", "2026-10-12 11:00 ET")[0] == 0
    (kitchen.home / "tasks" / "main-red-dddddddddddd.md").unlink()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert not (kitchen.home / "tasks" / "main-red-dddddddddddd.md").exists()
    assert main_red(kitchen) == []


def test_a_first_pass_over_a_red_main_files_no_brief(kitchen):
    main_after_alpha(kitchen, "failure")
    (kitchen.state / "wake.json").unlink()
    kitchen.poll()
    assert list((kitchen.home / "tasks").glob("main-red-*")) == []
    assert main_red(kitchen) == []
    assert kitchen.lines("retro") == []


def test_a_green_main_files_no_brief(kitchen):
    main_after_alpha(kitchen, "success")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert list((kitchen.home / "tasks").glob("main-red-*")) == []
    assert main_red(kitchen) == []


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


def beside_a_dispatched_browser_run(sha, check):
    """Return the check runs and the workflow runs of a commit on main whose push run's `full`
    job ended `check`, beside browser.yml runs at the same commit that failed: one dispatched by
    hand, one on a schedule and one for a tag."""
    done = {"status": "completed"}
    check_runs = [{**done, "conclusion": check, "name": "full", "check_suite": {"id": 11}}]
    workflow_runs = [{**done, "conclusion": check, "event": "push", "check_suite_id": 11}]
    for suite, event, branch in (
        (12, "workflow_dispatch", "main"),
        (13, "schedule", "main"),
        (14, "push", "v1.2.0"),
    ):
        check_runs.append(
            {**done, "conclusion": "failure", "name": "browser", "check_suite": {"id": suite}}
        )
        workflow_runs.append(
            {
                **done,
                "conclusion": "failure",
                "event": event,
                "head_branch": branch,
                "check_suite_id": suite,
            }
        )
    return {sha: check_runs}, {sha: workflow_runs}


@pytest.mark.parametrize("check, line", [("success", None), ("failure", "failed")])
def test_main_is_judged_by_its_push_run_and_not_by_a_browser_run_beside_it(kitchen, check, line):
    """jstack's main at d1e3bd5: its push run passed, and three browser runs dispatched at the
    same commit failed. Main was green, and jbus held every pull request as red."""
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    sha = "d" * 40
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, sha)])
    kitchen.set("commits.json", [kitchen.commit(sha)])
    check_runs, workflow_runs = beside_a_dispatched_browser_run(sha, check)
    kitchen.set("check-runs.json", check_runs)
    kitchen.set("push-runs.json", workflow_runs)
    kitchen.poll()
    said = f"retro alpha: main check {line} at dddddddddddd, 1 merges since the last green"
    assert kitchen.lines("retro") == ([said] if line else [])
    assert json.loads((kitchen.state / "checks.json").read_text()) == {sha: line or "green"}


def cancelled_on_main(kitchen, check_runs):
    """Make a merge whose commit on main has these check runs, and a push run that ended
    cancelled."""
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
    kitchen.poll(NOW + timedelta(minutes=3))
    first = kitchen.lines()
    assert sorted(event["event"] for event in kitchen.events()) == [
        "decision",
        "merged",
        "retro",
        "retro",
        "stale",
        "stale",
        "waiting",
    ]
    assert "(approve main-red-111111111111)" in kitchen.lines("waiting")[0]
    (decided,) = kitchen.lines("decision")
    assert decided.startswith("decision main-red-111111111111: approve main-red-111111111111: ")
    kitchen.poll(NOW + timedelta(minutes=6))
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


def main_of(kitchen, *checks):
    """Make one commit for each of `checks` on top of a green base, oldest first, a minute apart
    and newer than the merge, and merge alpha at the oldest one. Each check is `failure` or
    `success` for the `full` job. The commits' shas are `1` * 40, `2` * 40, and so on."""
    kitchen.brief("alpha", RESULT)
    kitchen.quiet()
    shas = [str(n) * 40 for n in range(1, len(checks) + 1)]
    done, base = {"status": "completed"}, "f" * 40
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, shas[0], ago=timedelta(minutes=30))])
    kitchen.set(
        "commits.json",
        [
            *(
                kitchen.commit(sha, f"feat: {sha[:3]}", ago=timedelta(minutes=30 - n))
                for n, sha in reversed(list(enumerate(shas)))
            ),
            kitchen.commit(base, "feat: older (#6)", ago=timedelta(hours=2)),
        ],
    )
    runs = {
        sha: [{**done, "conclusion": c, "name": "full"}]
        for sha, c in zip(shas, checks, strict=True)
    }
    kitchen.set("check-runs.json", {**runs, base: [{**done, "conclusion": "success"}]})
    return shas


def test_red_commits_a_later_green_one_superseded_file_nothing(kitchen):
    main_of(kitchen, "failure", "failure", "success")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert list((kitchen.home / "tasks").glob("main-red-*")) == []
    assert main_red(kitchen) == []


def test_a_red_tip_files_one_brief_for_the_tip_alone(kitchen):
    shas = main_of(kitchen, "failure", "failure")
    kitchen.poll()
    name = f"main-red-{shas[-1][:12]}"
    assert [path.name for path in (kitchen.home / "tasks").glob("main-red-*")] == [f"{name}.md"]
    assert [row["slug"] for row in main_red(kitchen)] == [name]


def test_a_red_tip_filed_is_not_filed_again_on_the_next_pass(kitchen):
    shas = main_of(kitchen, "failure")
    kitchen.poll()
    brief = kitchen.home / "tasks" / f"main-red-{shas[-1][:12]}.md"
    brief.write_text(brief.read_text() + "Noticed: the home edited it\n")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert brief.read_text().endswith("Noticed: the home edited it\n")
    assert [row["slug"] for row in main_red(kitchen)] == [f"main-red-{shas[-1][:12]}"]


def test_a_red_tip_that_turns_green_at_a_later_commit_withdraws_its_row_and_says_so_once(kitchen):
    main_of(kitchen, "failure")
    kitchen.poll()
    shas = main_of(kitchen, "failure", "success")
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    name = f"main-red-{shas[0][:12]}"
    assert main_red(kitchen) == []
    green = f"retro {name}: main is green again at {shas[1][:12]}, and its row is withdrawn"
    assert [line for line in kitchen.lines("retro") if "green again" in line] == [green]


BROWSER_JOB = "https://example.test/o/r/actions/runs/88/job/911"
BROWSER_LOG = (
    "2026-10-18T07:09:02.0000000Z FAILED tests/test_jbus_view_page.py::test_one - AssertionError\n"
    "2026-10-18T07:09:02.0000000Z FAILED tests/test_jbus_view_page.py::test_two[desk] - KeyError\n"
    "2026-10-18T07:09:03.0000000Z ===== 2 failed, 92 passed in 400.00s =====\n"
)


def browser_run(number=88, conclusion="failure", ago=timedelta(minutes=40), **more):
    """Return a run of browser.yml that ended `ago` before the pass, by default the nightly one."""
    return {
        "id": number,
        "status": "completed",
        "conclusion": conclusion,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": "c" * 40,
        "html_url": f"https://example.test/o/r/actions/runs/{number}",
        "created_at": iso(NOW - ago - timedelta(minutes=8)),
        "updated_at": iso(NOW - ago),
    } | more


def browser_runs(kitchen, *runs):
    """Set the workflow's runs, newest first as GitHub lists them, and a failed job and its log
    for the run 88."""
    kitchen.quiet()
    kitchen.set("browser-runs.json", list(runs))
    job = {"id": 911, "name": "browser", "status": "completed", "html_url": BROWSER_JOB}
    kitchen.set("run-jobs.json", {"88": [job | {"conclusion": "failure"}]})
    kitchen.set("logs.json", {"911": BROWSER_LOG})


def browser_red(kitchen):
    return [row for row in jbus.queue.load(kitchen.state) if row["slug"].startswith("browser-red-")]


def test_a_red_browser_run_files_one_brief_approved_by_rule_naming_its_failed_tests(kitchen):
    browser_runs(kitchen, browser_run())
    kitchen.poll()
    brief = kitchen.home / "tasks" / "browser-red-2026-10-12.md"
    text = brief.read_text()
    for said in (
        BROWSER_JOB,
        "tests/test_jbus_view_page.py::test_one",
        "tests/test_jbus_view_page.py::test_two[desk]",
        "\nWhere: `tests/test_jbus_view_page.py`\n",
        "\nPlaybook: bug-fix\n",
        "\nSize: S\n",
        "https://example.test/o/r/actions/runs/88",
    ):
        assert said in text
    assert [row["slug"] for row in browser_red(kitchen)] == ["browser-red-2026-10-12"]
    run = 'the red run "the browser run 88 failed on 2026-10-12, 2 tests named"'
    assert run in browser_red(kitchen)[0]["approved"]
    assert jbus.queue.brief_sha(text) == jbus.queue.brief_sha(
        (kitchen.state / "briefs" / "browser-red-2026-10-12.md").read_text()
    )
    line = "retro browser-red-2026-10-12: the browser run 88 failed on 2026-10-12, 2 tests named"
    assert kitchen.lines("retro") == [line]


def test_a_red_browser_run_filed_is_not_filed_again_and_an_edited_brief_stays(kitchen):
    browser_runs(kitchen, browser_run())
    kitchen.poll()
    brief = kitchen.home / "tasks" / "browser-red-2026-10-12.md"
    brief.write_text(brief.read_text() + "Noticed: the home edited it\n")
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert brief.read_text().endswith("Noticed: the home edited it\n")
    assert [row["slug"] for row in browser_red(kitchen)] == ["browser-red-2026-10-12"]
    assert len(kitchen.lines("retro")) == 1


def test_a_removed_browser_red_row_is_not_filed_again(kitchen):
    browser_runs(kitchen, browser_run())
    kitchen.poll()
    removed = ["queue", "remove", "browser-red-2026-10-12", "--by", "user"]
    assert kitchen.main(*removed, "--at", "2026-10-12 11:00 ET")[0] == 0
    (kitchen.home / "tasks" / "browser-red-2026-10-12.md").unlink()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert not (kitchen.home / "tasks" / "browser-red-2026-10-12.md").exists()
    assert browser_red(kitchen) == []


def test_two_red_browser_runs_of_one_day_are_two_briefs_with_two_names(kitchen):
    nightly = browser_run(88, ago=timedelta(hours=2))
    release = browser_run(89, ago=timedelta(minutes=30), event="push", head_branch="v1.0.0")
    browser_runs(kitchen, release, nightly)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert sorted(row["slug"] for row in browser_red(kitchen)) == [
        "browser-red-2026-10-12",
        "browser-red-2026-10-12-2",
    ]
    tasks = kitchen.home / "tasks"
    assert "the browser run 88 failed" in (tasks / "browser-red-2026-10-12.md").read_text()
    assert "the browser run 89 failed" in (tasks / "browser-red-2026-10-12-2.md").read_text()


@pytest.mark.parametrize("conclusion", ["success", "cancelled", "skipped"])
def test_a_browser_run_that_passed_or_was_cancelled_files_nothing(kitchen, conclusion):
    browser_runs(kitchen, browser_run(conclusion=conclusion))
    kitchen.poll()
    assert list((kitchen.home / "tasks").glob("browser-red-*")) == []
    assert browser_red(kitchen) == []
    assert kitchen.lines("retro") == []


def test_a_browser_run_that_timed_out_is_red_with_no_test_named(kitchen):
    browser_runs(kitchen, browser_run(conclusion="timed_out"))
    kitchen.set("logs.json", {"911": "Error: The operation was canceled.\n"})
    kitchen.poll()
    text = (kitchen.home / "tasks" / "browser-red-2026-10-12.md").read_text()
    assert "its log names no failed test, read it" in text
    assert "\nWhere: the tests marked `browser`\n" in text


def test_a_first_pass_over_a_red_browser_run_files_no_brief_then_or_later(kitchen):
    browser_runs(kitchen, browser_run())
    (kitchen.state / "wake.json").unlink()
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert list((kitchen.home / "tasks").glob("browser-red-*")) == []
    assert browser_red(kitchen) == []


def test_a_red_browser_run_older_than_three_days_files_nothing(kitchen):
    browser_runs(kitchen, browser_run(ago=timedelta(days=4)))
    kitchen.poll()
    assert browser_red(kitchen) == []


def test_a_manual_run_on_a_branch_files_nothing_and_one_on_the_default_branch_does(kitchen):
    manual = {"event": "workflow_dispatch", "head_branch": "some-fix"}
    browser_runs(kitchen, browser_run(87, **manual))
    kitchen.poll()
    assert browser_red(kitchen) == []
    browser_runs(
        kitchen, browser_run(88, **manual | {"head_branch": "main"}), browser_run(87, **manual)
    )
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [row["slug"] for row in browser_red(kitchen)] == ["browser-red-2026-10-12"]


def test_a_red_pull_request_run_files_nothing_on_any_push_and_is_marked_seen(kitchen):
    """A pull request's browser run is that pull request's check, not a red on main."""
    pull = {"event": "pull_request", "head_branch": "some-fix"}
    browser_runs(kitchen, browser_run(88, **pull))
    kitchen.poll()
    browser_runs(kitchen, browser_run(89, **pull), browser_run(88, **pull))
    kitchen.poll(NOW + timedelta(minutes=3))
    assert list((kitchen.home / "tasks").glob("browser-red-*")) == []
    assert browser_red(kitchen) == []
    assert kitchen.lines("retro") == []
    assert json.loads((kitchen.state / "browser-runs.json").read_text()) == {"88": "", "89": ""}


def test_a_red_pull_request_run_from_a_branch_named_main_files_nothing(kitchen):
    browser_runs(kitchen, browser_run(88, event="pull_request"))
    kitchen.poll()
    assert browser_red(kitchen) == []


def test_a_red_push_run_on_main_files_one_row(kitchen):
    browser_runs(kitchen, browser_run(88, event="push"))
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [row["slug"] for row in browser_red(kitchen)] == ["browser-red-2026-10-12"]


def test_a_red_run_of_a_published_release_on_its_tag_files_one_row(kitchen):
    browser_runs(kitchen, browser_run(88, event="release", head_branch="v1.0.0"))
    kitchen.poll()
    assert [row["slug"] for row in browser_red(kitchen)] == ["browser-red-2026-10-12"]


def test_a_red_macos_nightly_from_a_pull_request_files_nothing(kitchen):
    pull = {"event": "pull_request", "head_branch": "mac-room-fix"}
    macos_runs(kitchen, macos_run(**pull), macos_green())
    kitchen.poll()
    assert red_rows(kitchen, "macos-red-") == []


def test_a_github_that_does_not_answer_files_nothing_and_the_run_is_filed_when_it_does(kitchen):
    browser_runs(kitchen, browser_run())
    (kitchen.stub / "gh-down").write_text("")
    kitchen.poll()
    assert browser_red(kitchen) == []
    (kitchen.stub / "gh-down").unlink()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [row["slug"] for row in browser_red(kitchen)] == ["browser-red-2026-10-12"]


def test_a_run_whose_log_or_jobs_github_would_not_give_is_filed_on_a_later_pass_with_its_names(
    kitchen,
):
    browser_runs(kitchen, browser_run())
    kitchen.set("logs.json", {})
    kitchen.poll()
    assert browser_red(kitchen) == []
    kitchen.set("logs.json", {"911": BROWSER_LOG})
    kitchen.poll(NOW + timedelta(minutes=3))
    text = (kitchen.home / "tasks" / "browser-red-2026-10-12.md").read_text()
    assert "tests/test_jbus_view_page.py::test_one" in text


def test_a_run_whose_log_stays_unreadable_for_an_hour_is_filed_without_names(kitchen):
    browser_runs(kitchen, browser_run())
    kitchen.set("logs.json", {})
    kitchen.poll(NOW + timedelta(hours=2))
    text = (kitchen.home / "tasks" / "browser-red-2026-10-12.md").read_text()
    assert "its log names no failed test, read it" in text


def test_a_run_whose_jobs_github_would_not_give_waits_an_hour_and_is_then_filed_without_names(
    kitchen,
):
    browser_runs(kitchen, browser_run())
    kitchen.set("run-jobs.json", {"88": None})
    kitchen.poll()
    assert browser_red(kitchen) == []
    kitchen.poll(NOW + timedelta(hours=2))
    text = (kitchen.home / "tasks" / "browser-red-2026-10-12.md").read_text()
    assert "\nWhere: the tests marked `browser`\n" in text


MACOS_JOB = "https://example.test/o/r/actions/runs/77/job/712"
MACOS_LOG = (
    "2026-10-12T09:01:02.0000000Z FAILED features/jgauge/tests/test_room.py::test_load[idle]\n"
    "2026-10-12T09:01:02.0000000Z FAILED features/crew/tests/test_check.py::TestSetsid::test_starts"
    "\n"
    "2026-10-12T09:01:03.0000000Z ::warning::macOS: 2 tests failed, the suite step ended failure\n"
)


def macos_run(conclusion="failure", ref="main", **more):
    """Return a run of macos-nightly.yml, whose title names the ref it checked out."""
    return browser_run(77, conclusion, display_title=f"macos-nightly on {ref}", **more)


def macos_green(ref="main"):
    """Return a run of macos-nightly.yml on `ref` that passed the night before the run 77."""
    return macos_run("success", ref, id=76, ago=timedelta(days=1))


def macos_runs(kitchen, *runs, log=MACOS_LOG):
    """Set the runs of macos-nightly.yml, newest first, and a failed job and its log for the run
    77. A nightly's runs are on main, whatever branch its `ref` checked out."""
    kitchen.quiet()
    kitchen.set("workflow-runs.json", {"macos-nightly.yml": list(runs)})
    job = {"id": 712, "name": "macos", "status": "completed", "html_url": MACOS_JOB}
    kitchen.set("run-jobs.json", {"77": [job | {"conclusion": "failure"}]})
    kitchen.set("logs.json", {"712": log})


def red_rows(kitchen, prefix):
    return [row for row in jbus.queue.load(kitchen.state) if row["slug"].startswith(prefix)]


def test_a_red_macos_nightly_files_one_brief_approved_by_rule_for_the_macos_home(
    kitchen,
):
    macos_runs(kitchen, macos_run(), macos_green())
    kitchen.poll()
    brief = kitchen.home / "tasks" / "macos-red-2026-10-12.md"
    text = brief.read_text()
    for said in (
        MACOS_JOB,
        "`features/jgauge/tests/test_room.py::test_load[idle]`",
        "`features/crew/tests/test_check.py::TestSetsid::test_starts`",
        "\nWhere: `features/jgauge/tests/test_room.py`, `features/crew/tests/test_check.py`\n",
        "\nHome: macos\n",
        "\nPull request: open one when done\n",
        "\nPlaybook: bug-fix\n",
        "https://example.test/o/r/actions/runs/77",
    ):
        assert said in text
    assert "macos-nightly.yml" in text.split("\nProves it: ")[1].splitlines()[0]
    assert [row["slug"] for row in red_rows(kitchen, "macos-red-")] == ["macos-red-2026-10-12"]
    run = 'the red run "the macOS nightly run 77 failed on 2026-10-12, 2 tests named"'
    assert run in red_rows(kitchen, "macos-red-")[0]["approved"]
    line = (
        "retro macos-red-2026-10-12: the macOS nightly run 77 failed on 2026-10-12, 2 tests named"
    )
    assert kitchen.lines("retro") == [line]


def test_a_red_browser_run_and_a_red_macos_nightly_of_one_night_file_a_brief_each(kitchen):
    browser_runs(kitchen, browser_run())
    kitchen.set("workflow-runs.json", {"macos-nightly.yml": [macos_run(), macos_green()]})
    macos = {"id": 712, "name": "macos", "status": "completed", "html_url": MACOS_JOB}
    browser = {"id": 911, "name": "browser", "status": "completed", "html_url": BROWSER_JOB}
    kitchen.set(
        "run-jobs.json",
        {"77": [macos | {"conclusion": "failure"}], "88": [browser | {"conclusion": "failure"}]},
    )
    kitchen.set("logs.json", {"712": MACOS_LOG, "911": BROWSER_LOG})
    kitchen.poll()
    tasks = kitchen.home / "tasks"
    assert "Home:" not in (tasks / "browser-red-2026-10-12.md").read_text()
    assert (
        "tests/test_jbus_view_page.py::test_one"
        in (tasks / "browser-red-2026-10-12.md").read_text()
    )
    assert "test_room.py::test_load[idle]" in (tasks / "macos-red-2026-10-12.md").read_text()
    assert sorted(kitchen.lines("retro")) == [
        "retro browser-red-2026-10-12: the browser run 88 failed on 2026-10-12, 2 tests named",
        "retro macos-red-2026-10-12: the macOS nightly run 77 failed on 2026-10-12, 2 tests named",
    ]


def test_a_macos_nightly_that_timed_out_is_red_with_no_test_named_and_is_filed_once(kitchen):
    macos_runs(kitchen, macos_run("timed_out"), macos_green(), log="The job was cancelled.\n")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    text = (kitchen.home / "tasks" / "macos-red-2026-10-12.md").read_text()
    assert "its log names no failed test, read it" in text
    assert (
        "\nWhere: the tests the macOS nightly runs on main, under `features/` and `testing/`\n"
        in text
    )
    assert [row["slug"] for row in red_rows(kitchen, "macos-red-")] == ["macos-red-2026-10-12"]


@pytest.mark.parametrize("conclusion", ["success", "cancelled"])
def test_a_macos_nightly_that_passed_or_was_cancelled_files_nothing(kitchen, conclusion):
    macos_runs(kitchen, macos_run(conclusion))
    kitchen.poll()
    assert red_rows(kitchen, "macos-red-") == []
    assert kitchen.lines("retro") == []


def test_a_red_manual_macos_run_on_a_fixs_ref_files_nothing_and_one_on_main_does(kitchen):
    """Every run of macos-nightly.yml is on main, so its title is what names the ref it ran."""
    manual = {"event": "workflow_dispatch", "head_branch": "main"}
    macos_runs(kitchen, macos_run(ref="mac-room-fix", **manual), macos_green())
    kitchen.poll()
    assert red_rows(kitchen, "macos-red-") == []
    macos_runs(kitchen, macos_run(**manual), macos_green())
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [row["slug"] for row in red_rows(kitchen, "macos-red-")] == ["macos-red-2026-10-12"]


NEVER_GREEN = (
    "retro macos-nightly: the macOS nightly run {} failed on {}, and no run of it on main "
    "has passed yet, so no row is filed"
)


def test_a_red_macos_nightly_on_a_main_that_never_passed_files_no_row_and_pages_nobody(kitchen):
    """main's macOS nightly has not been green yet while its fixes are open: its red nights are its
    home's known work, so each is one quiet line in the log, and no row asks the user anything."""
    macos_runs(kitchen, macos_run(), macos_green(ref="mac-room-fix"))
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert list((kitchen.home / "tasks").glob("macos-red-*")) == []
    assert red_rows(kitchen, "macos-red-") == []
    assert kitchen.lines("retro") == [NEVER_GREEN.format(77, "2026-10-12")]
    assert kitchen.webhook.posts == []


def test_once_main_passed_a_red_night_after_it_files_one_row_and_one_before_it_none(kitchen):
    before = macos_run(id=75, ago=timedelta(days=2))
    macos_runs(kitchen, macos_run(), macos_green(), before)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [row["slug"] for row in red_rows(kitchen, "macos-red-")] == ["macos-red-2026-10-12"]
    assert (
        "the macOS nightly run 77 failed"
        in (kitchen.home / "tasks" / "macos-red-2026-10-12.md").read_text()
    )
    assert kitchen.lines("retro") == [
        NEVER_GREEN.format(75, "2026-10-10"),
        "retro macos-red-2026-10-12: the macOS nightly run 77 failed on 2026-10-12, 2 tests named",
    ]


def test_a_nightly_pass_is_kept_after_github_lists_it_no_more(kitchen):
    """GitHub lists the last 20 runs, so a night that passed slides out of the list."""
    macos_runs(kitchen, macos_green())
    kitchen.poll()
    kitchen.set("workflow-runs.json", {"macos-nightly.yml": [macos_run()]})
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [row["slug"] for row in red_rows(kitchen, "macos-red-")] == ["macos-red-2026-10-12"]


def macos_check_log():
    """Return a log in the shape of a macos-nightly job whose suite failed: pytest's summary,
    whose ids cut a parameter with spaces short and leave out an error at teardown, its last line,
    then the step that prints every failed test, whose script GitHub echoes in colour."""
    at = "2026-10-12T09:{}.0000000Z "
    lines = [
        '##[group]Run make check JUNIT="$RUNNER_TEMP/junit.xml"',
        "FAILED features/jlog/tests/test_log.py::test_one - AssertionError: assert [] == ['x']",
        "FAILED features/jlog/tests/test_log.py::test_two[a note under a heading] - KeyError",
        "ERROR features/jlog/tests/test_tail.py::test_three - OSError: [Errno 24]",
        "= 2 failed, 40 passed, 3 skipped, 1 xfailed, 2 errors in 31.07s (0:00:31) =",
        "##[error]Process completed with exit code 2.",
        "##[group]Run python3 - << 'EOF'",
        '\x1b[36;1m    line = f"macOS: {len(failed)} tests failed, the suite step ended"\x1b[0m',
        '\x1b[36;1m    print(f"FAILED {test}")\x1b[0m',
        "##[endgroup]",
        "##[warning]macOS: 4 tests failed, the suite step ended failure",
        "FAILED features/jlog/tests/test_log.py::test_one",
        "FAILED features/jlog/tests/test_log.py::test_two[a note under a heading]",
        "FAILED features/jlog/tests/test_tail.py::test_three",
        "FAILED features/jlog/tests/test_tail.py::test_four",
        "Post job cleanup.",
    ]
    return "".join(f"{at.format(f'{n:02}:00')}{line}\n" for n, line in enumerate(lines))


def test_a_red_night_names_every_test_the_failed_tests_step_prints(kitchen):
    """GitHub's log of the job has escape sequences, which `gh api` gives only when asked to."""
    macos_runs(kitchen, macos_run(), macos_green(), log=macos_check_log())
    kitchen.poll()
    text = (kitchen.home / "tasks" / "macos-red-2026-10-12.md").read_text()
    read = text.split("\nRead:\n")[1].splitlines()[0]
    assert read == f"- the job `macos`, {MACOS_JOB}: " + ", ".join(
        f"`features/jlog/tests/{test}`"
        for test in (
            "test_log.py::test_one",
            "test_log.py::test_two[a note under a heading]",
            "test_tail.py::test_three",
            "test_tail.py::test_four",
        )
    )
    assert (
        "\nWhere: `features/jlog/tests/test_log.py`, `features/jlog/tests/test_tail.py`\n" in text
    )
    assert "run 77 failed on 2026-10-12, 4 tests named" in text
    assert kitchen.lines("retro") == [
        "retro macos-red-2026-10-12: the macOS nightly run 77 failed on 2026-10-12, 4 tests named"
    ]


def test_a_red_night_whose_log_counts_failures_it_does_not_name_says_how_many(kitchen):
    log = "2026-10-12T09:01:00.0000000Z = 3 failed, 9 passed, 1 error in 2.50s =\n"
    macos_runs(kitchen, macos_run(), macos_green(), log=log)
    kitchen.poll()
    said = "the macOS nightly run 77 failed on 2026-10-12, 4 tests failed, none named"
    assert said in (kitchen.home / "tasks" / "macos-red-2026-10-12.md").read_text()
    assert kitchen.lines("retro") == [f"retro macos-red-2026-10-12: {said}"]
