"""A shared file never stops a launch: the check against shared files happens at merge time.
There, jbus tells a crew to rebase, once per head, when its pull request went stale or
conflicts. Like `test_jbus_queue.py`, the tests run the real pass against
the fakes."""

import json
from datetime import timedelta

import pytest

import jbus
from test_jbus_kitchen import NOW, asks, complete, sends
from test_jbus_queue import add, gates

URL = "https://example.test/pull/7"
CHANGED = "main changed src/jbus/cli.py after its check started at 07:00 ET; it needs a fresh check"


def task(slug, *paths):
    named = ", ".join(f"`{path}`" for path in paths)
    return complete(slug).replace(f"Where: `src/{slug}/`", f"Where: {named}")


def test_a_row_whose_file_a_running_crew_names_is_launched(kitchen):
    kitchen.config(max_running=2)
    add(kitchen, "alpha", text=task("alpha", "src/jbus/cli.py"))
    kitchen.t3.thread("other")
    kitchen.brief("other", "Thread: mcp:thread-1\n")
    said = kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]
    assert "launched alpha: mcp:thread-2" in said and gates(kitchen) == []


def out(kitchen, head="c" * 40, reason=CHANGED, word="wait"):
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "headRefOid": head}])
    kitchen.set("jmerge.txt", f"{word} 7 {URL}: {reason}\n")


@pytest.fixture
def launched(kitchen):
    """Alpha is a row that a pass launched, so it has a launch record and its `Thread:` line. Its
    thread's turn has ended, since jbus tells nothing to a thread that is at work."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.t3.threads[0]["status"] = "completed"
    return kitchen


@pytest.mark.parametrize(
    "reason",
    [
        CHANGED,
        "it conflicts with its base",
    ],
    ids=["fresh", "conflict"],
)
def test_a_stale_pull_request_tells_its_crew_to_rebase_with_a_backup_ref_and_a_lease(
    launched, reason
):
    out(launched, reason=reason)
    said = launched.poll()
    head = "c" * 40
    (given,) = sends(launched)
    assert given == {
        "threadId": "mcp:thread-1",
        "message": (
            f"jbus: main moved under your pull request #7 ({reason}). Rebase it in your own "
            "worktree now, even if GitHub says MERGEABLE: run `git update-ref "
            f'refs/jstack/pre-rebase/alpha/cccccccccccc {head}` first, then "A conflict"\'s '
            "rebase onto origin/main, the check command, and push with "
            f"`git push --force-with-lease=refs/heads/alpha:{head} origin "
            "HEAD:refs/heads/alpha`. Never push without the lease. jmerge merges only after "
            "a new green check."
        ),
        "mode": "queue",
        "clientRequestId": "rebase|alpha|cccccccccccc",
    }
    line = "rebase alpha: told the crew (#7, cccccccccccc)"
    assert line in said and launched.lines("rebase") == [line]
    assert "rebase|alpha|cccccccccccc" in jbus.read_json(launched.state / "sent.json", [])


def test_a_head_is_told_once_and_a_new_head_that_is_stale_again_is_a_gate_not_a_second_rebase(
    launched,
):
    out(launched)
    for minutes in (0, 3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert len(sends(launched)) == 1
    out(launched, head="d" * 40)
    for minutes in (9, 12):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert [given["clientRequestId"] for given in sends(launched)] == ["rebase|alpha|cccccccccccc"]
    assert launched.lines("rebase") == ["rebase alpha: told the crew (#7, cccccccccccc)"]
    assert gates(launched) == ["condition alpha: stale again after its one rebase"]


@pytest.mark.parametrize(
    "first",
    [CHANGED, "it conflicts with its base"],
    ids=["stale then conflict", "conflict then conflict"],
)
def test_a_new_head_that_conflicts_again_is_told_to_rebase_again_not_gated(launched, first):
    out(launched, reason=first)
    launched.poll(NOW)
    launched.t3.threads[0]["status"] = "completed"
    out(launched, head="d" * 40, reason="it conflicts with its base")
    launched.poll(NOW + timedelta(minutes=3))
    assert [given["clientRequestId"] for given in sends(launched)] == [
        "rebase|alpha|cccccccccccc",
        "rebase|alpha|dddddddddddd",
    ]
    assert gates(launched) == []


@pytest.mark.parametrize(
    "reason",
    ["it conflicts with its base"],
    ids=["conflict"],
)
def test_a_real_conflict_or_failure_tells_the_crew_to_rebase(launched, reason):
    out(launched, reason=reason)
    launched.poll()
    assert [given["clientRequestId"] for given in sends(launched)] == ["rebase|alpha|cccccccccccc"]


def test_a_fresh_check_that_is_queued_tells_its_crew_nothing(launched):
    out(launched, reason="a fresh check is queued")
    launched.poll()
    assert sends(launched) == [] and gates(launched) == []


def test_a_pull_request_with_no_launch_record_is_told_nothing(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n")
    out(kitchen)
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("rebase") == [] and gates(kitchen) == []


def test_a_row_its_home_launched_by_hand_is_told_to_rebase_once_on_a_fresh_check_hold(kitchen):
    """The home launched the row's crew itself, so jbus has no launch record, and its queue row
    names the crew's thread. jmerge holds the pull request because main changed under its check
    and the home has no fresh-check command: the crew is woken once to rebase (Winnifred #196,
    2026-10-23)."""
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "running")
    kitchen.brief("alpha", "Thread: mcp:thread-1\n")
    kitchen.poll(NOW - timedelta(minutes=30))
    assert kitchen.t3.launches == []
    kitchen.t3.threads[0]["status"] = "completed"
    out(kitchen, reason=CHANGED)
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    (given,) = sends(kitchen)
    assert given["threadId"] == "mcp:thread-1" and given["mode"] == "queue"
    assert given["clientRequestId"] == "rebase|alpha|cccccccccccc"
    assert "it needs a fresh check" in given["message"]
    assert kitchen.lines("rebase") == ["rebase alpha: told the crew (#7, cccccccccccc)"]


@pytest.mark.parametrize(
    ("word", "reason"),
    [
        ("hold", "it touches a secret, and " + CHANGED),
        ("merged", "it conflicts with its base"),
        ("wait", "its check has not passed at cccccccccccc"),
        ("wait", "its review is not written"),
    ],
)
def test_a_line_that_is_not_a_stale_wait_tells_nobody(launched, word, reason):
    out(launched, reason=reason, word=word)
    launched.poll()
    assert asks(launched) == [] and launched.lines("rebase") == [] and gates(launched) == []
    assert launched.lines("gate") == []


def test_a_stale_pull_request_with_no_thread_line_is_a_gate_once_per_head(launched):
    (launched.home / "tasks/alpha.md").unlink()
    out(launched)
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    gate = "condition alpha: stale pull request with no thread to tell"
    assert sends(launched) == [] and gates(launched) == [gate]
    out(launched, head="d" * 40)
    launched.poll(NOW + timedelta(minutes=6))
    assert gates(launched) == [gate, gate]


def test_a_rebase_message_t3_code_refuses_is_a_gate_once_and_goes_when_it_is_taken(launched):
    out(launched)
    launched.t3.refuse_send = True
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert gates(launched) == ["condition alpha: T3 Code refused the rebase message"]
    assert launched.lines("rebase") == [] and len(sends(launched)) == 2
    launched.t3.refuse_send = False
    launched.poll(NOW + timedelta(minutes=6))
    assert launched.lines("rebase") == ["rebase alpha: told the crew (#7, cccccccccccc)"]
    assert len(launched.t3.messages) == 1


def test_a_rebase_message_with_no_answer_waits_and_is_tried_again(launched):
    out(launched)
    launched.t3.lose_send = True
    said = launched.poll()
    (wait,) = [line for line in said if line.startswith("wait alpha: ")]
    assert wait.startswith("wait alpha: its crew could not be told to rebase (")
    assert launched.lines("rebase") == [] and gates(launched) == []
    launched.t3.lose_send = False
    launched.poll(NOW + timedelta(minutes=3))
    assert launched.lines("rebase") == ["rebase alpha: told the crew (#7, cccccccccccc)"]
    assert (
        json.loads((launched.state / "sent.json").read_text()).count("rebase|alpha|cccccccccccc")
        == 1
    )


def test_a_default_branch_that_is_not_known_sends_no_message_and_is_tried_again(launched):
    out(launched)
    launched.git("symbolic-ref", "-d", "refs/remotes/origin/HEAD")
    said = launched.poll()
    assert "wait alpha: the default branch is not known, so its crew is not told" in said
    assert sends(launched) == [] and launched.lines("rebase") == []
    launched.git("remote", "set-head", "origin", "main")
    launched.poll(NOW + timedelta(minutes=3))
    assert launched.lines("rebase") == ["rebase alpha: told the crew (#7, cccccccccccc)"]


def test_a_thread_line_in_the_approved_copy_alone_is_no_thread_to_tell(kitchen):
    """The brief is pasted from an old task file, and its `Thread:` line names a thread that is
    not this crew's."""
    add(kitchen, "alpha", text=task("alpha", "src/alpha/") + "Thread: mcp:an-old-thread\n")
    kitchen.poll(NOW - timedelta(minutes=30))
    (kitchen.home / "tasks/alpha.md").unlink()
    out(kitchen)
    kitchen.poll()
    assert sends(kitchen) == []
    assert gates(kitchen) == ["condition alpha: stale pull request with no thread to tell"]
