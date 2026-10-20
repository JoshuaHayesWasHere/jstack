"""When the default branch goes from red to green, the crew of each open pull request that
is red is told once to rebase and carry on, so one that main broke does not sit idle after
main is fixed. A main that moved from green to green tells nobody. A conflict is told once
per head by `rebase.github`, and not here (`test_jbus_github.py`).
Run as `tests/test_jbus_unlock.py` runs: the real pass, against the fakes, with the kitchen's
own origin as the remote whose main moves."""

import json
import subprocess
from datetime import timedelta

import pytest

import jbus
from test_jbus_kitchen import NOW
from test_jbus_queue import add, gates

HEAD = "c" * 40
RED = "red: checks failed"


@pytest.fixture
def launched(kitchen, request):
    """Alpha and beta, launched by a first pass that also records where main is, red unless
    the test asks for `success`, with each thread's turn ended: one at work is told nothing."""
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
    """The conclusion of main's one check run at a commit, `""` for one still running."""
    kept = kitchen.stub / "check-runs.json"
    runs = json.loads(kept.read_text()) if kept.exists() else {}
    runs[sha] = [{"status": "completed" if conclusion else "in_progress", "conclusion": conclusion}]
    kitchen.set("check-runs.json", runs)


def move(kitchen, conclusion="success"):
    """A merge lands on origin's main from another clone: the checkout never fetches it. Its
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
    """The main-moved messages that went: a red head is also told of its failed check once,
    by `rebase.github`, where this module did not tell it first."""
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
    }


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
