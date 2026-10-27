"""When the default branch goes from red to green, jbus tells the crew of each open red pull
request once to rebase and carry on. So a pull request that main broke does not sit idle after
main is fixed. When main moves from green to green, jbus tells nobody. `rebase.github` tells a
crew of a conflict once per head, and this module does not (`test_jbus_github.py`). Like
`test_jbus_unlock.py`, the tests run the real pass against the fakes, with the kitchen's own
origin as the remote whose main moves."""

import json
import subprocess
from datetime import timedelta

import pytest

import jbus
from jmerge import mainjson
from test_jbus_kitchen import NOW
from test_jbus_queue import add, gates, go
from test_jbus_watch import beside_a_dispatched_browser_run

HEAD = "c" * 40
RED = "red: checks failed"


@pytest.fixture
def launched(kitchen, request):
    """Alpha and beta are rows that a first pass launched. That pass also records where main is,
    red unless the test asks for `success`. Each thread's turn has ended, since jbus tells
    nothing to a thread that is at work."""
    kitchen.config(max_running=2)
    add(kitchen, "alpha")
    add(kitchen, "beta", priority=2)
    checks(kitchen, tip(kitchen), getattr(request, "param", "failure"))
    said = kitchen.poll(NOW - timedelta(minutes=30))
    assert "launched alpha: mcp:thread-1" in said and "launched beta: mcp:thread-2" in said
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    return kitchen


def tip(kitchen):
    asked = ["git", "rev-parse", "refs/heads/main"]
    return subprocess.run(
        asked, cwd=kitchen.origin, capture_output=True, text=True, check=True
    ).stdout.strip()


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
    """Return the main-moved messages that went out. Where this module did not first tell the
    crew of a red head, `rebase.github` also tells that crew of its failed check once."""
    every = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]
    return [given for given in every if given["clientRequestId"].startswith("mainmoved|")]


def keys(kitchen):
    return [given["clientRequestId"] for given in sends(kitchen)]


def mine(gates):
    return [line for line in gates if "failed check" not in line]


def message(slug, number, main, why):
    return (
        f"jbus: main is green again at {main[:12]} while your pull request #{number} is {why}. "
        "If main was what broke it, it may be fixed now. In your own worktree: run `git update-ref "
        f'refs/jstack/pre-rebase/{slug}/cccccccccccc {HEAD}`, rebase onto origin/main as "A '
        'conflict" says, rerun the tests your change touches plus the ones that failed, and '
        f"push with `git push --force-with-lease=refs/heads/{slug}:{HEAD} origin "
        f"HEAD:refs/heads/{slug}`. Then carry on your flow: launch its reviewer on that push "
        'if it has none, without waiting for green ("The review"), and handle the rest as '
        '"Stay on the pull request" says.'
    )


def test_main_moves_and_a_red_pull_request_is_told_once_and_a_conflicting_one_is_not(launched):
    red = pull(launched, "alpha", 7, "FAILURE")
    conflicting = pull(launched, "beta", 8, mergeable="CONFLICTING")
    launched.set("open.json", [red, conflicting])
    main = move(launched)
    said = launched.poll()
    assert sends(launched) == [
        {
            "threadId": "mcp:thread-1",
            "message": message("alpha", 7, main, RED),
            "mode": "queue",
            "clientRequestId": f"mainmoved|alpha|#7|{main[:12]}",
        },
    ]
    every = [
        given["clientRequestId"] for tool, given in launched.t3.calls if tool == "t3_thread_send"
    ]
    assert every == [f"mainmoved|alpha|#7|{main[:12]}", "conflict|beta|cccccccccccc"]
    line = f"mainmoved alpha: told the crew (#7, main {main[:12]})"
    assert launched.lines("mainmoved") == [line] and line in said
    sent = jbus.read_json(launched.state / "sent.json", [])
    assert {f"mainmoved|alpha|#7|{main[:12]}", "failed|alpha|cccccccccccc"} <= set(sent)
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


def test_the_same_main_commit_tells_nobody_again_and_a_new_one_tells_once_more(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    first = move(launched)
    for minutes in (0, 3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert keys(launched) == [f"mainmoved|alpha|#7|{first[:12]}"]
    move(launched, "failure")
    launched.poll(NOW + timedelta(minutes=8))
    second = move(launched)
    for minutes in (9, 12):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert keys(launched) == [
        f"mainmoved|alpha|#7|{first[:12]}",
        f"mainmoved|alpha|#7|{second[:12]}",
    ]
    assert launched.lines("mainmoved") == [
        f"mainmoved alpha: told the crew (#7, main {first[:12]})",
        f"mainmoved alpha: told the crew (#7, main {second[:12]})",
    ]


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


def test_a_red_pull_request_with_no_launch_record_is_told_nothing(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n")
    kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.set("open.json", [pull(kitchen, "alpha", 7, "FAILURE")])
    move(kitchen)
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("mainmoved") == [] and gates(kitchen) == []


def test_a_red_pull_request_with_no_thread_line_is_a_gate_once_per_main_commit(launched):
    (launched.home / "tasks/alpha.md").unlink()
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    move(launched)
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    gate = "condition alpha: red pull request with no thread to tell"
    assert sends(launched) == []
    assert [line for line in mine(gates(launched)) if "thread to tell" in line] == [gate]
    move(launched, "failure")
    launched.poll(NOW + timedelta(minutes=4))
    move(launched)
    launched.poll(NOW + timedelta(minutes=6))
    assert [line for line in mine(gates(launched)) if "thread to tell" in line] == [gate, gate]


def test_a_message_t3_code_refuses_is_a_gate_once_per_main_commit(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    move(launched)
    launched.t3.refuse_send = True
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert mine(gates(launched)) == ["condition alpha: T3 Code refused the main-moved message"]
    assert len(sends(launched)) == 1 and launched.lines("mainmoved") == []


def test_a_message_with_no_answer_waits_and_the_next_pass_sends_it_with_the_same_key(launched):
    red = pull(launched, "alpha", 7, "FAILURE")
    launched.set("open.json", [red, pull(launched, "beta", 8, "FAILURE")])
    before = tip(launched)
    main = move(launched)
    launched.t3.lose_send = True
    said = launched.poll()
    waits = [line for line in said if "could not be told that main moved" in line]
    assert [line.split(":")[0] for line in waits] == ["wait alpha", "wait beta"]
    assert launched.lines("mainmoved") == [] and mine(gates(launched)) == []
    assert jbus.read_json(launched.state / "main.json", {})["main"] == before
    launched.t3.lose_send = False
    launched.poll(NOW + timedelta(minutes=3))
    launched.poll(NOW + timedelta(minutes=6))
    alpha, beta = f"mainmoved|alpha|#7|{main[:12]}", f"mainmoved|beta|#8|{main[:12]}"
    assert keys(launched) == [alpha, beta, alpha, beta]
    assert sorted(launched.t3.messages) == [alpha, beta]
    assert jbus.read_json(launched.state / "main.json", {})["main"] == main


def test_a_pull_request_github_has_not_judged_yet_holds_up_no_main_commit(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, mergeable="UNKNOWN")])
    main = move(launched)
    launched.poll()
    assert sends(launched) == []
    assert jbus.read_json(launched.state / "main.json", {})["main"] == main


def test_a_head_the_rebase_message_went_to_is_not_told_again(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, mergeable="CONFLICTING")])
    launched.set("jmerge.txt", "wait 7 https://example.test/pull/7: it conflicts with its base\n")
    move(launched)
    launched.poll()
    every = [
        given["clientRequestId"] for tool, given in launched.t3.calls if tool == "t3_thread_send"
    ]
    assert every == ["rebase|alpha|cccccccccccc"]
    assert launched.lines("mainmoved") == []


def test_a_red_head_the_rebase_message_went_to_earlier_is_still_told(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    launched.box = jbus.wake.Box(launched.state, jbus.load().projects[0])
    launched.box.mark("rebase|alpha|cccccccccccc")
    main = move(launched)
    launched.poll()
    assert keys(launched) == [f"mainmoved|alpha|#7|{main[:12]}"]


def test_a_refused_message_is_not_sent_again_while_another_is_owed(launched):
    red, unjudged = pull(launched, "alpha", 7, "FAILURE"), pull(launched, "beta", 8)
    launched.set("open.json", [red, {**unjudged, "mergeable": "UNKNOWN"}])
    main = move(launched)
    launched.t3.refuse_send = True
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert keys(launched) == [f"mainmoved|alpha|#7|{main[:12]}"]
    assert mine(gates(launched)) == ["condition alpha: T3 Code refused the main-moved message"]


def test_a_red_pull_request_is_told_each_time_main_is_fixed_under_one_head(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    fixes = []
    for minutes in (0, 6, 12):
        move(launched, "failure")
        launched.poll(NOW + timedelta(minutes=minutes))
        fixes.append(move(launched))
        launched.poll(NOW + timedelta(minutes=minutes + 3))
    assert keys(launched) == [f"mainmoved|alpha|#7|{main[:12]}" for main in fixes]


@pytest.mark.parametrize("launched", ["success"], indirect=True)
def test_main_going_green_to_green_tells_a_red_pull_request_nothing(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    for minutes in (0, 3):
        main = move(launched)
        launched.poll(NOW + timedelta(minutes=minutes))
    assert sends(launched) == [] and launched.lines("mainmoved") == []
    assert jbus.read_json(launched.state / "main.json", {})["main"] == main


def test_main_going_red_to_green_tells_a_red_pull_request_once(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    main = move(launched)
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert keys(launched) == [f"mainmoved|alpha|#7|{main[:12]}"]


def test_main_going_red_to_red_tells_nobody_and_the_green_after_it_tells_once(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    move(launched, "failure")
    launched.poll()
    assert sends(launched) == []
    fixed = move(launched)
    launched.poll(NOW + timedelta(minutes=3))
    assert keys(launched) == [f"mainmoved|alpha|#7|{fixed[:12]}"]


def test_a_main_whose_check_has_not_ended_tells_nobody_until_it_is_green(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    main = move(launched, "")
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert sends(launched) == []
    checks(launched, main, "success")
    for minutes in (6, 9):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert keys(launched) == [f"mainmoved|alpha|#7|{main[:12]}"]


def test_a_main_whose_check_failed_after_it_landed_is_red_and_the_next_green_tells(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    first = move(launched, "")
    launched.poll()
    checks(launched, first, "failure")
    launched.poll(NOW + timedelta(minutes=3))
    assert sends(launched) == []
    fixed = move(launched)
    launched.poll(NOW + timedelta(minutes=6))
    assert keys(launched) == [f"mainmoved|alpha|#7|{fixed[:12]}"]


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
    assert keys(launched) == [f"mainmoved|alpha|#7|{red[:12]}"]
    row = f"main-red-{red[:12]}"
    green = f"retro {row}: main is green again at {red[:12]}, and its row is left as it is"
    assert [line for line in launched.lines("retro") if "green again" in line] == [green]
    assert [r.get("thread") for r in jbus.queue.load(launched.state) if r["slug"] == row] == [""]


@pytest.mark.xfail(
    strict=True,
    reason="a fix row approved once main is green again still launches: watch._retro says it "
    "green again and leaves it (features/jbus/src/jbus/watch.py:1099-1102), and dispatch "
    "launches it",
)
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
    assert [r.get("thread") for r in jbus.queue.load(launched.state) if r["slug"] == row] == [""]


def test_a_red_head_that_is_also_in_conflict_is_told_once_however_often_main_moves(launched):
    both = pull(launched, "alpha", 7, "FAILURE", mergeable="CONFLICTING")
    launched.set("open.json", [both])
    first = move(launched)
    launched.poll()
    for minutes in (3, 6):
        move(launched)
        launched.poll(NOW + timedelta(minutes=minutes))
    assert keys(launched) == [f"mainmoved|alpha|#7|{first[:12]}"]
    assert sends(launched)[0]["message"] == message("alpha", 7, first, RED)


def test_a_red_head_told_in_conflict_waits_while_github_has_not_judged_it_again(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE", mergeable="CONFLICTING")])
    first = move(launched)
    launched.poll()
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE", mergeable="UNKNOWN")])
    red = move(launched, "failure")
    launched.poll(NOW + timedelta(minutes=2))
    main = move(launched)
    launched.poll(NOW + timedelta(minutes=3))
    assert keys(launched) == [f"mainmoved|alpha|#7|{first[:12]}"]
    assert jbus.read_json(launched.state / "main.json", {})["main"] == red
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE", mergeable="CONFLICTING")])
    launched.poll(NOW + timedelta(minutes=6))
    assert keys(launched) == [f"mainmoved|alpha|#7|{first[:12]}"]
    assert jbus.read_json(launched.state / "main.json", {})["main"] == main


def test_a_green_tip_whose_message_was_lost_ends_the_red_though_the_next_tip_is_pending(launched):
    launched.set("open.json", [pull(launched, "alpha", 7, "FAILURE")])
    red = tip(launched)
    fixed = move(launched)
    launched.t3.lose_send = True
    launched.poll()
    assert mainjson.read(launched.state) == mainjson.Main(green=fixed)
    launched.t3.lose_send = False
    move(launched, "")
    launched.poll(NOW + timedelta(minutes=3))
    assert mainjson.read(launched.state).red == "", f"main reads red at {red[:12]}"
    assert keys(launched) == [f"mainmoved|alpha|#7|{fixed[:12]}"] * 2


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
