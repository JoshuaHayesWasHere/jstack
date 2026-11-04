"""`mainmoved` judges main's tips and keeps the verdict in `main.json`, and sends no crew a
message. A pull request into main that went red while main was red is judged again by `jmerge`
once `main.json` reads green: `jmerge.cli.Repo.again` asks GitHub to merge main into it
(`features/jmerge/tests/test_jmerge_rejudge.py`). So these tests check what `main.json` reads
at each move of main, and that no main-moved message goes out. Like `test_jbus_unlock.py`, the
tests run the real pass against the fakes, with the kitchen's own origin as the remote whose
main moves."""

import json
import subprocess
from datetime import timedelta

import pytest

import jbus
from jmerge import mainjson, rows
from test_jbus_kitchen import NOW, PROJECT, iso
from test_jbus_queue import add, gates, go
from test_jbus_watch import beside_a_dispatched_browser_run

HEAD = "c" * 40


@pytest.fixture
def launched(kitchen, request):
    """Alpha and beta are rows that a first pass launched while main's check still ran: a red
    main launches no plain row. Main's check then ends red unless the test asks for `success`,
    and a second pass records where main is. Each thread's turn has ended, since jbus tells
    nothing to a thread that is at work."""
    kitchen.config(max_running=2)
    add(kitchen, "alpha")
    add(kitchen, "beta", priority=2)
    checks(kitchen, tip(kitchen), "")
    said = kitchen.poll(NOW - timedelta(minutes=30))
    assert "launched alpha: mcp:thread-1" in said and "launched beta: mcp:thread-2" in said
    checks(kitchen, tip(kitchen), getattr(request, "param", "failure"))
    kitchen.poll(NOW - timedelta(minutes=29))
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    return kitchen


def tip(kitchen):
    asked = ["git", "rev-parse", "refs/heads/main"]
    return subprocess.run(
        asked, cwd=kitchen.origin, capture_output=True, text=True, check=True
    ).stdout.strip()


def red_since(kitchen, sha, at):
    """Write `main.json` as a pass at `at` leaves it once main's check at `sha` failed: the red a
    row launched before it now sits on."""
    kept = mainjson.record(main=sha, at=iso(at), check="failed", broken=sha)
    (kitchen.state / mainjson.NAME).write_text(json.dumps(kept))


def checks(kitchen, sha, conclusion):
    """Set the conclusion of main's one check run at a commit, with `""` for a check run that is
    still running."""
    kept = kitchen.stub / "check-runs.json"
    runs = json.loads(kept.read_text()) if kept.exists() else {}
    runs[sha] = [{"status": "completed" if conclusion else "in_progress", "conclusion": conclusion}]
    kitchen.set("check-runs.json", runs)


def move(kitchen, conclusion="success"):
    """Land a merge on origin's main from another clone, which the checkout never fetches. Its
    check ends as `conclusion` says."""
    other = kitchen.root / "other"
    if not other.exists():
        kitchen.git("clone", "-q", str(kitchen.origin), str(other), cwd=kitchen.root)
    kitchen.git("pull", "-q", "--ff-only", cwd=other)
    kitchen.git("commit", "-q", "--allow-empty", "-m", "a merge", cwd=other)
    kitchen.git("push", "-q", "origin", "main", cwd=other)
    checks(kitchen, tip(kitchen), conclusion)
    return tip(kitchen)


def pull(kitchen, slug, number, state="SUCCESS", mergeable="MERGEABLE"):
    return {**kitchen.opened(slug, number, state), "mergeable": mergeable}


def pending(kitchen, slug, number):
    running = [{"status": "IN_PROGRESS", "conclusion": ""}]
    return {**pull(kitchen, slug, number), "statusCheckRollup": running}


def sends(kitchen):
    """Return the main-moved messages that went out, which should be none. `rebase.github` still
    tells the crew of a red head of its failed check, once per head, under a key of its own."""
    every = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]
    return [given for given in every if given["clientRequestId"].startswith("mainmoved|")]


def test_a_main_that_turns_green_while_t3_code_is_down_is_green_at_once(launched):
    """A pass with no T3 Code still judges main: the red ends at the green tip, so `jmerge` no
    longer holds a red pull request's merge of main (`jmerge.cli.Repo.again` reads the record as
    `rows.main`). No message is owed, so the first pass with T3 Code sends none."""
    red = tip(launched)
    assert rows.main(launched.checkout) == mainjson.Main(red=red)
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    launched.t3.down.add(PROJECT)
    main = move(launched)
    launched.poll()
    assert rows.main(launched.checkout) == mainjson.Main(green=main)
    launched.t3.down.clear()
    launched.poll(NOW + timedelta(minutes=3))
    assert sends(launched) == []
    assert rows.main(launched.checkout) == mainjson.Main(green=main)


def test_main_going_red_to_green_writes_green_and_tells_neither_a_red_nor_a_conflicting_one(
    launched,
):
    red = pull(launched, "alpha", 7, "FAILURE")
    conflicting = pull(launched, "beta", 8, mergeable="CONFLICTING")
    launched.set("open.json", [red, conflicting])
    main = move(launched)
    launched.poll()
    assert sends(launched) == [] and launched.lines("mainmoved") == []
    assert json.loads((launched.state / "main.json").read_text()) == {
        "main": main,
        "at": NOW.isoformat(),
        "check": "green",
        "green": main,
    }


def test_a_kept_red_at_a_tip_whose_push_run_passed_beside_a_failed_browser_run_clears(launched):
    """jstack's main.json at d1e3bd5: `checks.json` kept `failed` from three browser runs
    dispatched at main's tip, and main's push run there had passed. The next pass reads main
    green, and jmerge holds nothing."""
    main = tip(launched)
    kept = json.loads((launched.state / "main.json").read_text())
    assert (kept["check"], jbus.read_json(launched.state / "checks.json", {})) == (
        "failed",
        {main: "failed"},
    )
    check_runs, workflow_runs = beside_a_dispatched_browser_run(main, "success")
    launched.set("check-runs.json", check_runs)
    launched.set("push-runs.json", workflow_runs)
    launched.poll()
    record = json.loads((launched.state / "main.json").read_text())
    assert {k: v for k, v in record.items() if k != "at"} == {
        "main": main,
        "check": "green",
        "green": main,
    }
    assert mainjson.read(launched.state).red == ""


def test_a_green_pull_request_is_told_nothing_up_to_date_or_behind_main(launched):
    launched.set("open.json", [pull(launched, "alpha", 7), pull(launched, "beta", 8)])
    for minutes in (0, 3):
        main = move(launched, "failure" if minutes else "success")
        launched.poll(NOW + timedelta(minutes=minutes))
    assert sends(launched) == [] and launched.lines("mainmoved") == [] and gates(launched) == []
    assert jbus.read_json(launched.state / "main.json", {})["main"] == main


def test_a_pending_pull_request_is_told_nothing(launched):
    launched.set("open.json", [pending(launched, "alpha", 7)])
    move(launched)
    launched.poll()
    assert sends(launched) == [] and launched.lines("mainmoved") == []


def test_the_first_pass_with_no_main_json_records_the_commit_and_tells_nobody(launched):
    (launched.state / "main.json").unlink()
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    main = move(launched)
    launched.poll()
    assert sends(launched) == [] and launched.lines("mainmoved") == []
    assert jbus.read_json(launched.state / "main.json", {})["main"] == main


@pytest.mark.parametrize("launched", ["success"], indirect=True)
def test_main_going_green_to_green_tells_a_red_pull_request_nothing(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    for minutes in (0, 3):
        main = move(launched)
        launched.poll(NOW + timedelta(minutes=minutes))
    assert sends(launched) == [] and launched.lines("mainmoved") == []
    assert jbus.read_json(launched.state / "main.json", {})["main"] == main


def test_main_going_red_to_red_reads_red_at_the_newest_and_the_green_after_it_ends_it(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    red = move(launched, "failure")
    launched.poll()
    assert rows.main(launched.checkout).red == red
    fixed = move(launched)
    launched.poll(NOW + timedelta(minutes=3))
    assert rows.main(launched.checkout) == mainjson.Main(green=fixed)
    assert sends(launched) == []


def test_a_main_whose_check_has_not_ended_stays_red_until_it_is_green(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    red = tip(launched)
    main = move(launched, "")
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert rows.main(launched.checkout).red == red
    checks(launched, main, "success")
    for minutes in (6, 9):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert rows.main(launched.checkout) == mainjson.Main(green=main)
    assert sends(launched) == []


def test_a_main_whose_check_failed_after_it_landed_is_red_and_the_next_green_ends_it(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    first = move(launched, "")
    launched.poll()
    checks(launched, first, "failure")
    launched.poll(NOW + timedelta(minutes=3))
    assert rows.main(launched.checkout).red == first
    fixed = move(launched)
    launched.poll(NOW + timedelta(minutes=6))
    assert rows.main(launched.checkout) == mainjson.Main(green=fixed)
    assert sends(launched) == []


def test_a_failed_tip_whose_check_is_rerun_and_passes_is_green_with_no_new_commit(launched):
    """A flake: main's check fails at its tip, and a rerun of that check passes while the tip
    stays where it is. jbus filed a fix row for the flake, and the row is not approved. jbus
    reports the row as green again and leaves it as it is. The next test covers an approved row."""
    red = tip(launched)
    launched.set("commits.json", [launched.commit(red)])
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    add(launched, f"main-red-{red[:12]}", priority=0, approve=False)
    launched.poll()
    assert mainjson.read(launched.state).red == red
    checks(launched, red, "success")
    for minutes in (3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert mainjson.read(launched.state) == mainjson.Main(green=red)
    record = jbus.read_json(launched.state / "main.json", {})
    assert (record["check"], record["green"], "broken" in record) == ("green", red, False)
    assert sends(launched) == []
    row = f"main-red-{red[:12]}"
    green = f"retro {row}: main is green again at {red[:12]}, and its row is left as it is"
    assert [line for line in launched.lines("retro") if "green again" in line] == [green]
    assert [r.get("thread") for r in jbus.queue.load(launched.state) if r["slug"] == row] == [""]


def test_a_fix_row_approved_after_its_main_is_green_again_is_never_launched(launched):
    """As with main-red-b66eaae4c2ca: its tip's check failed, a rerun passed, and the row got its
    approval after that. A main that is green needs no fix, so jbus does not launch the row."""
    red = tip(launched)
    launched.set("commits.json", [launched.commit(red)])
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    row = f"main-red-{red[:12]}"
    add(launched, row, priority=0, approve=False)
    launched.poll()
    checks(launched, red, "success")
    for minutes in (3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert [line for line in launched.lines("retro") if "green again" in line] != []
    assert go(launched, row)[0] == 0
    for minutes in (9, 12):
        launched.poll(NOW + timedelta(minutes=minutes))
    (left,) = [r for r in jbus.queue.load(launched.state) if r["slug"] == row]
    assert (left.get("thread"), left.get("status")) == ("", "queued")
    assert left.get("why") == (
        f"main is green again at {red[:12]}, its own commit, so it has no red to fix"
    )


def test_a_green_tip_ends_the_red_though_the_next_tip_is_pending(launched):
    red = tip(launched)
    fixed = move(launched)
    launched.poll()
    assert mainjson.read(launched.state) == mainjson.Main(green=fixed)
    move(launched, "")
    launched.poll(NOW + timedelta(minutes=3))
    assert mainjson.read(launched.state).red == "", f"main reads red at {red[:12]}"


@pytest.mark.parametrize("launched", ["success"], indirect=True)
def test_a_tip_that_failed_under_one_no_pass_saw_is_red_while_the_newest_is_pending(launched):
    first = tip(launched)
    red = move(launched, "failure")
    newest = move(launched, "")
    parents = ((newest, red), (red, first))
    commits = [{**launched.commit(sha), "parents": [{"sha": parent}]} for sha, parent in parents]
    launched.set("commits.json", commits)
    launched.poll()
    assert mainjson.read(launched.state).red == red


def test_the_rebase_message_writes_its_key_and_the_main_moved_key_of_the_tip(launched):
    launched.set("jmerge.txt", "wait 7 https://example.test/pull/7: it conflicts with its base\n")
    launched.set("open.json", [pull(launched, "alpha", 7, mergeable="CONFLICTING")])
    launched.poll()
    sent = jbus.read_json(launched.state / "sent.json", [])
    assert {"rebase|alpha|cccccccccccc", f"mainmoved|alpha|#7|{tip(launched)[:12]}"} <= set(sent)
    assert launched.lines("rebase") == ["rebase alpha: told the crew (#7, cccccccccccc)"]


def test_494_a_red_pull_request_gets_no_main_moved_message_as_main_goes_red_to_green(launched):
    """#494 (`skills-no-outside-instructions`): red into main while main went red to green three
    times, it got a main-moved message each time, and each time jmerge asked GitHub to merge main
    in within minutes (`jmerge.cli.Repo.again`), so the crew's turn bought nothing. Each green now
    reads green to jmerge, whose base merge wakes the pull request, and jbus sends no message of
    its own."""
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    for minutes in (0, 6, 12):
        if minutes:
            red = move(launched, "failure")
            launched.poll(NOW + timedelta(minutes=minutes))
            assert rows.main(launched.checkout).red == red
        fixed = move(launched)
        launched.poll(NOW + timedelta(minutes=minutes + 3))
        assert rows.main(launched.checkout) == mainjson.Main(green=fixed)
    assert sends(launched) == [] and launched.lines("mainmoved") == []
    sent = jbus.read_json(launched.state / "sent.json", [])
    assert [key for key in sent if key.startswith(("mainmoved|", "moved|"))] == []
