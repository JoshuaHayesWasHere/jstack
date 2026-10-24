"""`jbus.sidered` gives a workflow that is red on main, and that no other rule of jbus's reads,
one fix row: a run that ran no job, a scheduled run, or a push run at a commit that is no longer
main's tip. The gate's own rule, main's check runs at its tip, is the one it was. The runs here
are small made-up fixtures in the shape GitHub lists them. Like `test_jbus_watch.py`, the tests
run the real pass against the fakes.
"""

import subprocess
from datetime import timedelta

import pytest

import jbus.queue
from test_jbus_kitchen import NOW, iso

RELEASE, CHECK, DRIFT, BROWSER, MACOS = 11, 12, 13, 14, 16
WORKFLOWS = [
    {"id": RELEASE, "path": ".github/workflows/release.yml", "state": "active"},
    {"id": CHECK, "path": ".github/workflows/check.yml", "state": "active"},
    {"id": DRIFT, "path": ".github/workflows/pstack-drift.yml", "state": "active"},
    {"id": BROWSER, "path": ".github/workflows/browser.yml", "state": "active"},
    {"id": MACOS, "path": ".github/workflows/macos-nightly.yml", "state": "active"},
    {"id": 15, "path": "dynamic/dependabot/dependabot-updates", "state": "active"},
]
DRIFT_LOG = (
    "2026-10-12T13:09:02.0000000Z FAILED tests/test_drift.py::test_pinned - AssertionError\n"
)


def run(
    number, sha, conclusion="success", ago=timedelta(hours=1), took=timedelta(minutes=4), **more
):
    """Return a completed run on main that ended `ago` before the pass and took `took`. A run
    that took no time is one GitHub started no job for."""
    return {
        "id": number,
        "name": more.pop("name", "check"),
        "status": "completed",
        "conclusion": conclusion,
        "event": "push",
        "head_branch": "main",
        "head_sha": sha * 40 if len(sha) == 1 else sha,
        "html_url": f"https://example.test/o/r/actions/runs/{number}",
        "created_at": iso(NOW - ago - took),
        "run_started_at": iso(NOW - ago - took),
        "updated_at": iso(NOW - ago),
    } | more


def no_job(number, sha, ago):
    """Return a push run GitHub failed at once and named after its file, as it does for a file it
    cannot read."""
    return run(number, sha, "failure", ago, timedelta(0), name=".github/workflows/release.yml")


def eight_runs_with_no_job():
    """Return eight push runs of release.yml with no job, newest first, each beside a run of
    check.yml at the same commit that ran its jobs and passed."""
    shas = "abcdefgh"
    release = [no_job(100 + n, sha, timedelta(hours=8 - n)) for n, sha in enumerate(shas)]
    check = [run(200 + n, sha, ago=timedelta(hours=8 - n)) for n, sha in enumerate(shas)]
    return release[::-1], check[::-1]


def side(kitchen, runs, push=True):
    """Set the repo's workflows and the runs of each one by its id, push a new tip of main
    unless `push` is false, and return main's tip."""
    kitchen.set("workflows.json", WORKFLOWS)
    kitchen.set("workflow-runs.json", {str(flow): each for flow, each in runs.items()})
    if push:
        kitchen.git("commit", "--allow-empty", "-q", "-m", "a change")
        kitchen.git("push", "-q", "origin", "HEAD:refs/heads/main")
    asked = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=kitchen.checkout, capture_output=True, text=True
    )
    return asked.stdout.strip()


def rows(kitchen):
    return [
        row for row in jbus.queue.load(kitchen.state) if row["slug"].startswith("workflow-red-")
    ]


def asked_for_workflows(kitchen):
    return [line for line in kitchen.log("gh") if line.split("?")[0].endswith("/actions/workflows")]


def test_eight_push_runs_of_a_side_workflow_with_no_job_file_one_owned_row(kitchen):
    """The replay of NoRedWithoutOwner (S14): release.yml ran no job in 8 of 8 push runs."""
    kitchen.quiet()
    release, check = eight_runs_with_no_job()
    side(kitchen, {RELEASE: release, CHECK: check})
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=20))
    first = "a" * 12
    assert [(row["slug"], row["approved"]) for row in rows(kitchen)] == [
        (f"workflow-red-release-{first}", "")
    ]
    brief = (kitchen.home / "tasks" / f"workflow-red-release-{first}.md").read_text()
    assert "Where: `.github/workflows/release.yml`" in brief
    assert "GitHub started no job" in brief and "a candidate for removal" in brief
    assert "https://example.test/o/r/actions/runs/100" in brief
    assert "https://example.test/o/r/actions/runs/107" in brief
    assert kitchen.lines("retro") == [
        f"retro workflow-red-release-{first}: release.yml ran no job on main in 8 runs since "
        "2026-10-12: GitHub could not run it, so fix its file or remove it"
    ]


def test_a_scheduled_workflow_that_fails_files_one_row_naming_its_failed_tests(kitchen):
    kitchen.quiet()
    red = run(300, "c", "failure", event="schedule", name="pstack-drift")
    side(
        kitchen,
        {
            DRIFT: [red, run(299, "b", ago=timedelta(days=1), event="schedule")],
            CHECK: [run(201, "h")],
        },
    )
    job = {"id": 931, "name": "drift", "status": "completed", "conclusion": "failure"}
    kitchen.set("run-jobs.json", {"300": [job | {"html_url": "https://example.test/job/931"}]})
    kitchen.set("logs.json", {"931": DRIFT_LOG})
    kitchen.poll()
    name = f"workflow-red-pstack-drift-{'c' * 12}"
    assert [row["slug"] for row in rows(kitchen)] == [name]
    brief = (kitchen.home / "tasks" / f"{name}.md").read_text()
    assert "Where: `.github/workflows/pstack-drift.yml`, `tests/test_drift.py`" in brief
    assert (
        "the job `drift`, https://example.test/job/931: `tests/test_drift.py::test_pinned`" in brief
    )
    assert kitchen.lines("retro") == [
        f"retro {name}: pstack-drift.yml failed on main in 1 run since 2026-10-12, 1 test named"
    ]


def test_a_red_run_of_the_gate_at_mains_tip_is_left_to_the_main_red_rule(kitchen):
    """main's check runs at its tip carry a push run that ran a job: `watch._retro` owns it, as
    before, and this rule files nothing beside it."""
    kitchen.quiet()
    head = side(kitchen, {})
    side(
        kitchen,
        {CHECK: [run(201, head, "failure"), run(200, "g", ago=timedelta(hours=2))]},
        push=False,
    )
    kitchen.poll()
    assert rows(kitchen) == []


def test_a_red_of_the_gate_below_a_tip_whose_run_is_still_going_files_nothing(kitchen):
    """The gate's run at a new tip has not ended: its red at the commit before is still the
    main-red rule's, and the answer at the tip is the one that counts."""
    kitchen.quiet()
    head = side(kitchen, {})
    going = run(202, head, None, ago=timedelta(0), status="in_progress")
    side(kitchen, {CHECK: [going, run(201, "g", "failure")]}, push=False)
    kitchen.poll()
    assert rows(kitchen) == []


def test_a_red_of_the_gate_below_a_tip_whose_push_run_was_cancelled_files_nothing(kitchen):
    """The gate's push run at main's tip was cancelled: the main-red rule holds that tip pending
    and runs it again, so the red at the commit before is still its, not a side red."""
    kitchen.quiet()
    head = side(kitchen, {})
    stopped = run(202, head, "cancelled", ago=timedelta(minutes=5))
    side(kitchen, {CHECK: [stopped, run(201, "g", "failure")]}, push=False)
    kitchen.poll()
    assert rows(kitchen) == []


def test_a_red_push_run_below_mains_tip_is_a_side_red(kitchen):
    """A workflow with path filters that failed at a commit and did not run at the tip leaves no
    check run there, so no rule but this one sees it."""
    kitchen.quiet()
    side(kitchen, {DRIFT: [run(301, "d", "failure", name="pstack-drift")], CHECK: [run(201, "h")]})
    kitchen.poll()
    assert [row["slug"] for row in rows(kitchen)] == [f"workflow-red-pstack-drift-{'d' * 12}"]


def test_runs_that_ran_no_job_in_every_workflow_are_the_accounts_and_file_nothing(kitchen):
    """CI that ran no job anywhere is the account's (S9), not a workflow's to fix."""
    kitchen.quiet()
    release, _ = eight_runs_with_no_job()
    check = [run(200 + n, "x", "failure", timedelta(hours=8 - n), timedelta(0)) for n in range(8)]
    stopped = run(250, "y", "cancelled", timedelta(minutes=5), timedelta(0))
    side(kitchen, {RELEASE: release, CHECK: [stopped, *check[::-1]]})
    kitchen.poll()
    assert rows(kitchen) == []


@pytest.mark.parametrize(
    "runs",
    [
        [
            run(301, "d", event="schedule"),
            run(300, "c", "failure", timedelta(hours=2), event="schedule"),
        ],
        [run(300, "c", "failure", ago=timedelta(days=4), event="schedule")],
        [run(301, "d", "cancelled", event="schedule"), run(300, "c", event="schedule")],
    ],
    ids=["green-again", "older-than-the-window", "cancelled-after-green"],
)
def test_a_workflow_green_on_main_or_red_long_ago_files_nothing(kitchen, runs):
    kitchen.quiet()
    side(kitchen, {DRIFT: runs, CHECK: [run(201, "h")]})
    kitchen.poll()
    assert rows(kitchen) == []


def test_each_nightly_keeps_its_own_rule_and_a_dynamic_workflow_is_not_judged(kitchen):
    kitchen.quiet()
    red = {BROWSER: [run(400, "e", "failure")], MACOS: [run(402, "e", "failure")]}
    side(kitchen, red | {15: [run(401, "e", "failure")]})
    kitchen.poll()
    assert rows(kitchen) == []


def test_a_side_red_is_filed_once_and_a_removed_row_is_not_filed_again(kitchen):
    kitchen.quiet()
    release, check = eight_runs_with_no_job()
    side(kitchen, {RELEASE: release, CHECK: check})
    kitchen.poll()
    name = f"workflow-red-release-{'a' * 12}"
    code, said = kitchen.main(
        "queue", "remove", name, "--by", "user", "--at", "2026-10-12 11:00 ET"
    )
    assert code == 0, said
    (kitchen.home / "tasks" / f"{name}.md").unlink()
    later = no_job(108, "i", timedelta(0))
    side(kitchen, {RELEASE: [later, *release], CHECK: check})
    kitchen.poll(NOW + timedelta(minutes=20))
    assert rows(kitchen) == []
    assert not (kitchen.home / "tasks" / f"{name}.md").exists()


def test_a_new_red_after_a_green_run_is_a_new_row(kitchen):
    kitchen.quiet()
    side(kitchen, {DRIFT: [run(300, "c", "failure", event="schedule")], CHECK: [run(201, "h")]})
    kitchen.poll()
    again = [
        run(302, "e", "failure", ago=timedelta(0), event="schedule"),
        run(301, "d", ago=timedelta(minutes=30), event="schedule"),
        run(300, "c", "failure", event="schedule"),
    ]
    side(kitchen, {DRIFT: again, CHECK: [run(201, "h")]})
    kitchen.poll(NOW + timedelta(minutes=20))
    assert sorted(row["slug"] for row in rows(kitchen)) == [
        f"workflow-red-pstack-drift-{'c' * 12}",
        f"workflow-red-pstack-drift-{'e' * 12}",
    ]


def test_a_projects_first_pass_records_a_side_red_and_files_nothing(kitchen):
    release, check = eight_runs_with_no_job()
    side(kitchen, {RELEASE: release, CHECK: check})
    kitchen.poll(NOW - timedelta(hours=1))
    kitchen.poll()
    assert rows(kitchen) == []


def test_the_workflows_are_asked_at_most_once_in_fifteen_minutes(kitchen):
    kitchen.quiet()
    side(kitchen, {CHECK: [run(201, "h")]})
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=5))
    kitchen.poll(NOW + timedelta(minutes=14))
    assert len(asked_for_workflows(kitchen)) == 2
    kitchen.poll(NOW + timedelta(minutes=16))
    assert len(asked_for_workflows(kitchen)) == 3


def test_a_red_whose_file_changed_on_main_since_waits_for_a_run_and_files_nothing(kitchen):
    """release.yml's fix made it run on a pushed tag alone: no run on main ends its red, and the
    commit to its file since its newest red run is the fix."""
    kitchen.quiet()
    release, check = eight_runs_with_no_job()
    side(kitchen, {RELEASE: release, CHECK: check})
    kitchen.set("commits.json", [kitchen.commit("f" * 40, "fix: release.yml runs on a tag")])
    kitchen.poll()
    assert rows(kitchen) == []
    kitchen.set("commits.json", [kitchen.commit("f" * 40, "feat: release", ago=timedelta(days=1))])
    kitchen.poll(NOW + timedelta(minutes=20))
    assert [row["slug"] for row in rows(kitchen)] == [f"workflow-red-release-{'a' * 12}"]


def test_a_red_longer_than_the_runs_github_lists_is_one_row(kitchen):
    """GitHub lists the newest 20 runs: as the red goes on, its oldest run slides out of the list,
    and the red is still the one row it got."""
    kitchen.quiet()
    check = [run(200, "h", ago=timedelta(minutes=10))]
    many = [no_job(100 + n, f"{n:02x}" * 20, timedelta(minutes=50 - n)) for n in range(25)]
    side(kitchen, {RELEASE: many[:20][::-1], CHECK: check})
    kitchen.poll()
    side(kitchen, {RELEASE: many[5:][::-1], CHECK: check}, push=False)
    kitchen.poll(NOW + timedelta(minutes=20))
    assert [row["slug"] for row in rows(kitchen)] == [f"workflow-red-release-{'0' * 12}"]
