"""A red main changes the order of the queue:

- jbus queues the fix it files for the red main ahead of every row of its project, and the fix is
  the next launch there.
- `main.json`, the record of `mainmoved`, keeps the last tip of main that was green, and the tip
  that is red.
- `jmerge` reads that file (`features/jmerge/tests/test_jmerge_order.py`).
- A launched brief names the green sha on a `Green main:` line.

Like `test_jbus_watch.py`, the tests run the real pass against the fakes.
"""

import json
from datetime import timedelta

import jbus.queue
import jbus.wake
import test_jbus_main_moved
from jbus import questions
from jmerge import mainjson
from jmerge import rows as jmerge_rows
from test_jbus_kitchen import NOW, RESULT, approved, complete, go, iso, queued
from test_jbus_main_moved import checks, move, pull, tip
from test_jbus_watch import main_of, main_red


def kept(kitchen):
    return mainjson.read(kitchen.state)


def launched(kitchen):
    return [given["title"] for given in kitchen.t3.launches]


def test_the_fix_of_a_red_main_is_queued_ahead_of_every_row_and_launches_next(kitchen):
    for slug, priority in (("beta", 0), ("gamma", -5)):
        text = complete(slug)
        assert kitchen.main("queue", "add", slug, "--priority", str(priority), stdin=text)[0] == 0
    shas = main_of(kitchen, "failure")
    kitchen.poll()
    name = f"main-red-{shas[-1][:12]}"
    rows = jbus.queue.load(kitchen.state)
    assert [row["slug"] for row in sorted(rows, key=jbus.queue.order)] == [name, "gamma", "beta"]
    (fix,) = main_red(kitchen)
    assert fix["priority"] < -5 and fix["approved"] == ""
    for slug in ("gamma", "beta", name):
        assert go(kitchen, slug)[0] == 0
    said = kitchen.poll(NOW + timedelta(minutes=3))
    assert launched(kitchen) == [f"crew: {name}"], said


def test_a_second_red_tip_is_queued_ahead_of_the_fix_that_is_still_waiting(kitchen):
    first = main_of(kitchen, "failure")
    kitchen.poll()
    second = main_of(kitchen, "failure", "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    rows = sorted(jbus.queue.load(kitchen.state), key=jbus.queue.order)
    assert [row["slug"] for row in rows] == [
        f"main-red-{second[-1][:12]}",
        f"main-red-{first[0][:12]}",
    ]


def test_a_green_tip_is_the_last_green_main(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    assert kept(kitchen) == mainjson.Main(green=green)


def test_a_red_tip_keeps_the_green_tip_before_it(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    red = move(kitchen, "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kept(kitchen) == mainjson.Main(green=green, red=red)


def test_a_red_main_with_no_merge_in_a_day_is_still_kept_as_red(kitchen):
    kitchen.quiet()
    red = tip(kitchen)
    checks(kitchen, red, "failure")
    kitchen.poll()
    assert kept(kitchen) == mainjson.Main(red=red)
    assert main_red(kitchen) == []


def test_a_later_green_tip_clears_the_red_and_becomes_the_green(kitchen):
    checks(kitchen, tip(kitchen), "failure")
    kitchen.poll()
    green = move(kitchen, "success")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kept(kitchen) == mainjson.Main(green=green)


def test_a_tip_whose_check_has_not_ended_changes_nothing(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    red = move(kitchen, "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    move(kitchen, "")
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kept(kitchen) == mainjson.Main(green=green, red=red)


def test_main_json_is_the_one_record_of_the_red_tip_and_both_readers_agree(kitchen):
    """`mainmoved` keeps the red tip as `broken`, and `jmerge` reads the same sha from the same
    file. `checks.json` holds the sha too, as the answer GitHub gave for that commit, but that is
    no record of which tip is red. No other file of the project's state names a red main."""
    checks(kitchen, tip(kitchen), "success")
    kitchen.poll()
    red = move(kitchen, "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    record = json.loads((kitchen.state / "main.json").read_text())
    assert record["broken"] == red == jmerge_rows.main(kitchen.checkout).red
    assert jmerge_rows.red(jmerge_rows.main(kitchen.checkout), "beta").endswith(
        f"{red[:12]}, its fix merges first"
    )
    named = {path.name for path in kitchen.state.rglob("*.json") if red in path.read_text()}
    assert named == {"main.json", "checks.json"}
    assert json.loads((kitchen.state / "checks.json").read_text())[red] == "failed"
    move(kitchen, "success")
    kitchen.poll(NOW + timedelta(minutes=6))
    assert jmerge_rows.main(kitchen.checkout).red == ""


crews = test_jbus_main_moved.launched


def test_a_main_that_turns_green_while_a_message_is_owed_is_green_at_once(crews):
    """jbus still owes its message to a red crew whose head GitHub has not judged yet, so `tell`
    keeps the old commit to look at again. Even so, on that pass `jmerge` no longer reads main as
    red."""
    red = tip(crews)
    crews.set("open.json", [pull(crews, "alpha", 7, "FAILURE", mergeable="UNKNOWN")])
    crews.box = jbus.wake.Box(crews.state, jbus.load().projects[0])
    crews.box.mark("rebase|alpha|cccccccccccc")
    green = move(crews)
    crews.poll()
    record = json.loads((crews.state / "main.json").read_text())
    assert (record["main"], record["broken"], record["fixed"]) == (red, red, green)
    assert kept(crews) == mainjson.Main(green=green)
    assert jmerge_rows.main(crews.checkout).red == ""


def test_a_record_from_before_broken_was_kept_names_its_failed_tip_as_red():
    record = {"main": "d" * 40, "check": "failed"}
    assert mainjson.of(record) == mainjson.Main(red="d" * 40)


def test_a_launched_brief_names_the_last_green_main_on_a_green_main_line(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    approved(kitchen, "beta")
    before = (kitchen.state / "briefs" / "beta.md").read_text()
    kitchen.poll(NOW + timedelta(minutes=3))
    (given,) = kitchen.t3.launches
    line = f"Green main: {green}"
    assert given["message"].splitlines().count(line) == 1
    assert line in given["message"].split("## ")[0]
    assert (kitchen.home / "tasks" / "beta.md").read_text().splitlines().count(line) == 1
    assert (kitchen.state / "briefs" / "beta.md").read_text() == before


def test_a_launched_brief_after_a_red_main_names_the_green_before_the_red(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    red = move(kitchen, "failure")
    kitchen.poll(NOW + timedelta(minutes=3))
    approved(kitchen, "beta")
    kitchen.poll(NOW + timedelta(minutes=6))
    (given,) = kitchen.t3.launches
    assert f"Green main: {green}" in given["message"]
    assert red not in given["message"]


def test_a_brief_that_names_a_green_main_itself_is_sent_with_jbus_own_line(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    text = "".join(
        "\n".join(
            [
                "# beta: a task",
                'Task: "do beta"',
                "Green main: " + "9" * 40,
                "Done when:",
                "- it is done",
                "",
            ]
        )
        + "Proves it: `make check`\nSize: S\nWhere: `src/beta/`\nDesign: none, a test\n"
        "Pull request: open one when done\nReview: review\nPlaybook: feature\n"
    )
    queued(kitchen, "beta", text)
    kitchen.poll(NOW + timedelta(minutes=3))
    (given,) = kitchen.t3.launches
    assert [x for x in given["message"].splitlines() if x.startswith("Green main:")] == [
        f"Green main: {green}"
    ]


def test_a_brief_already_in_the_home_gets_the_green_main_line_it_is_launched_with(kitchen):
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.poll()
    approved(kitchen, "beta")
    target = kitchen.home / "tasks" / "beta.md"
    target.write_text(
        complete("beta").replace("\n", "\nHome: root\nGreen main: " + "9" * 40 + "\n", 1)
    )
    kitchen.poll(NOW + timedelta(minutes=3))
    (given,) = kitchen.t3.launches
    line = f"Green main: {green}"
    assert line in given["message"]
    lines = target.read_text().splitlines()
    assert [x for x in lines if x.startswith("Green main:")] == [line]
    assert "Home: root" in lines


def test_a_launch_with_no_green_main_known_sends_the_brief_as_approved(kitchen):
    approved(kitchen, "beta")
    kitchen.poll()
    (given,) = kitchen.t3.launches
    assert "Green main" not in given["message"]


def no_job(kitchen, sha, n):
    """Give a commit on main the check run GitHub gives when it starts no job, a spent Actions
    limit or a failed payment: it failed 3 s after it started, and its job ran no step on no
    runner."""
    began = NOW + timedelta(minutes=3 * n)
    run = {
        "id": 5000 + n,
        "name": "make check",
        "status": "completed",
        "conclusion": "failure",
        "started_at": iso(began),
        "completed_at": iso(began + timedelta(seconds=3)),
    }
    job = {"id": run["id"], "conclusion": "failure", "steps": [], "runner_id": 0, "runner_name": ""}
    for name, key, value in (("check-runs.json", sha, [run]), ("jobs.json", str(run["id"]), job)):
        kept = kitchen.stub / name
        kitchen.set(name, {**(json.loads(kept.read_text()) if kept.exists() else {}), key: value})


def landed(kitchen, n, conclusion=""):
    """Land a merge on main, list it first among main's commits, and return its sha."""
    sha = move(kitchen, conclusion)
    kept = json.loads((kitchen.stub / "commits.json").read_text())
    kitchen.set("commits.json", [kitchen.commit(sha, ago=-timedelta(minutes=3 * n)), *kept])
    return sha


def replay_no_job_runs(kitchen, runs=20):
    """Merge alpha at a green main, then land `runs` merges whose check starts no job, each
    seen by a pass of its own 3 minutes after the one before."""
    kitchen.brief("alpha", RESULT)
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.set("commits.json", [kitchen.commit(green, ago=timedelta(hours=1))])
    kitchen.quiet()
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, green, ago=timedelta(minutes=30))])
    for n in range(1, runs + 1):
        no_job(kitchen, landed(kitchen, n), n)
        kitchen.poll(NOW + timedelta(minutes=3 * n))
    return green, runs


def asked(kitchen):
    return questions.load(kitchen.state)


def test_twenty_runs_that_start_no_job_are_one_account_decision_and_no_red_main(kitchen):
    green, runs = replay_no_job_runs(kitchen)
    assert main_red(kitchen) == []
    assert not [line for line in kitchen.lines("retro") if "failed" in line]
    assert kept(kitchen) == mainjson.Main(green=green)
    (decision,) = asked(kitchen)
    assert decision.answer is None
    assert len(kitchen.lines("gate")) == 1
    passed = landed(kitchen, runs + 1, "success")
    kitchen.poll(NOW + timedelta(minutes=3 * (runs + 1)))
    (decision,) = asked(kitchen)
    assert decision.answer is not None
    assert decision.answer.closed_by != questions.SILENCE
    assert kept(kitchen) == mainjson.Main(green=passed)
    red = landed(kitchen, runs + 2, "failure")
    kitchen.poll(NOW + timedelta(minutes=3 * (runs + 2)))
    assert [row["slug"] for row in main_red(kitchen)] == [f"main-red-{red[:12]}"]
    assert len(asked(kitchen)) == 1


def test_a_run_that_starts_no_job_after_the_account_was_put_right_is_a_new_decision(kitchen):
    _, runs = replay_no_job_runs(kitchen, runs=2)
    landed(kitchen, runs + 1, "success")
    kitchen.poll(NOW + timedelta(minutes=3 * (runs + 1)))
    no_job(kitchen, landed(kitchen, runs + 2), runs + 2)
    kitchen.poll(NOW + timedelta(minutes=3 * (runs + 2)))
    first, second = asked(kitchen)
    assert first.answer is not None and second.answer is None
    assert main_red(kitchen) == []


def test_a_rerun_on_the_same_tip_whose_jobs_pass_closes_the_decision(kitchen):
    _, runs = replay_no_job_runs(kitchen, runs=1)
    at = tip(kitchen)
    checks(kitchen, at, "success")
    kitchen.poll(NOW + timedelta(minutes=3 * (runs + 1)))
    (decision,) = asked(kitchen)
    assert decision.answer is not None
    assert kept(kitchen) == mainjson.Main(green=at)
