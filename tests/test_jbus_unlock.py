"""A shared file never stops a launch: an overlap is one event, and the safety is at merge
time, where a crew whose pull request went stale or conflicts is told to rebase, once per
head. Run as `tests/test_jbus_queue.py` runs: the real pass, against the fakes."""

import json
from datetime import timedelta

import pytest

import jbus
from test_jbus_kitchen import NOW, complete, sends
from test_jbus_queue import add, gates

URL = "https://example.test/pull/7"
CHANGED = "main changed src/jbus/cli.py after its check started"


def task(slug, *paths):
    named = ", ".join(f"`{path}`" for path in paths)
    return complete(slug).replace(f"Where: `src/{slug}/`", f"Where: {named}")


def claim(slug, *paths, state="out"):
    return f"{slug} {state} root Where: {', '.join(f'`{path}`' for path in paths)}\n"


def test_a_row_whose_file_a_running_crew_names_is_launched(kitchen):
    kitchen.config(max_running=2)
    add(kitchen, "alpha", text=task("alpha", "src/jbus/cli.py"))
    kitchen.t3.thread("other")
    kitchen.brief("other", "Thread: mcp:thread-1\n")
    kitchen.set("claims.txt", claim("other", "src/jbus/cli.py"))
    said = kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]
    assert "launched alpha: mcp:thread-2" in said and gates(kitchen) == []


def test_a_claims_check_that_fails_never_stops_a_launch(kitchen):
    add(kitchen, "alpha")
    (kitchen.stub / "claims-fail").touch()
    said = kitchen.poll()
    assert "launched alpha: mcp:thread-1" in said
    assert [line for line in said if line.startswith("wait ")] == []
    assert gates(kitchen) == [] and kitchen.lines("overlap") == []


def test_an_overlap_is_one_event_for_each_pair_and_nothing_else(kitchen):
    add(kitchen, "alpha", text=task("alpha", "src/jbus/cli.py", "tests/test_alpha.py"))
    kitchen.set(
        "claims.txt",
        claim("alpha", "src/jbus/cli.py", "tests/test_alpha.py", state="not launched")
        + claim("other", "docs/", "src/jbus/cli.py")
        + claim("apart", "src/jmerge/"),
    )
    kitchen.poll()
    line = "overlap alpha: shares src/jbus/cli.py with other; whichever merges second rebases"
    assert len(kitchen.t3.launches) == 1 and kitchen.lines("overlap") == [line]
    (event,) = kitchen.events("overlap")
    assert event["slug"] == "alpha"
    assert "overlap|alpha|alpha other" in jbus.read_json(kitchen.state / "sent.json", [])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines("overlap") == [line] and gates(kitchen) == []


def test_two_holders_are_two_events_and_a_brief_not_launched_is_none(kitchen):
    add(kitchen, "alpha", text=task("alpha", "src/jbus/"))
    kitchen.set(
        "claims.txt",
        claim("one", "src/jbus/cli.py", "src/jbus/dispatch.py")
        + claim("two", "src/jbus/", state="pull request 9")
        + claim("later", "src/jbus/cli.py", state="not launched"),
    )
    kitchen.poll()
    rebases = "whichever merges second rebases"
    assert len(kitchen.t3.launches) == 1 and kitchen.lines("overlap") == [
        f"overlap alpha: shares src/jbus/cli.py, src/jbus/dispatch.py with one; {rebases}",
        f"overlap alpha: shares src/jbus/ with two; {rebases}",
    ]


def test_an_overlap_names_five_paths_and_counts_the_rest(kitchen):
    paths = [f"src/jbus/{name}.py" for name in "abcdefg"]
    add(kitchen, "alpha", text=task("alpha", *paths))
    kitchen.set("claims.txt", claim("other", "src/jbus/"))
    kitchen.poll()
    assert kitchen.lines("overlap") == [
        f"overlap alpha: shares {', '.join(paths[:5])} and 2 more with other; "
        "whichever merges second rebases"
    ]


def test_a_row_that_is_not_launched_sends_no_overlap(kitchen):
    add(kitchen, "alpha", text=task("alpha", "src/jbus/cli.py"))
    kitchen.set("claims.txt", claim("other", "src/jbus/cli.py"))
    kitchen.t3.refuse = "no"
    kitchen.poll()
    assert gates(kitchen) == ["condition alpha: T3 Code refused the launch"]
    assert kitchen.lines("overlap") == []


def test_a_launch_whose_reply_was_lost_sends_its_overlap_when_it_is_adopted(kitchen):
    add(kitchen, "alpha", text=task("alpha", "src/jbus/cli.py"))
    kitchen.set("claims.txt", claim("other", "src/jbus/cli.py"))
    kitchen.t3.lose = "after"
    kitchen.poll()
    assert kitchen.lines("overlap") == []
    kitchen.t3.lose = None
    assert "adopted alpha: mcp:thread-1" in kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert len(kitchen.t3.launches) == 1 and kitchen.lines("overlap") == [
        "overlap alpha: shares src/jbus/cli.py with other; whichever merges second rebases"
    ]


def out(kitchen, head="c" * 40, reason=CHANGED + ": it needs a rebase", word="wait"):
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "headRefOid": head}])
    kitchen.set("jmerge.txt", f"{word} 7 {URL}: {reason}\n")


@pytest.fixture
def launched(kitchen):
    """Alpha, launched by a pass, so it has a launch record and its `Thread:` line, with
    its thread's turn ended: one at work is told nothing."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.t3.threads[0]["status"] = "completed"
    return kitchen


@pytest.mark.parametrize(
    "reason",
    [
        CHANGED + ": it needs a rebase",
        CHANGED + ": it needs a fresh check",
        "its check fails on cccccccccccc over today's main",
        "it conflicts with its base",
    ],
    ids=["guarded", "fresh", "fails over main", "conflict"],
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


def test_a_head_is_told_once_and_a_new_head_that_is_stale_again_once_more(launched):
    out(launched)
    for minutes in (0, 3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert len(sends(launched)) == 1
    out(launched, head="d" * 40)
    for minutes in (9, 12):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert [given["clientRequestId"] for given in sends(launched)] == [
        "rebase|alpha|cccccccccccc",
        "rebase|alpha|dddddddddddd",
    ]
    assert launched.lines("rebase") == [
        "rebase alpha: told the crew (#7, cccccccccccc)",
        "rebase alpha: told the crew (#7, dddddddddddd)",
    ]


def test_a_pull_request_with_no_launch_record_is_told_nothing(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n")
    out(kitchen)
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("rebase") == [] and gates(kitchen) == []


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
    assert sends(launched) == [] and launched.lines("rebase") == [] and gates(launched) == []
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


def test_a_reason_that_names_a_head_the_crew_has_pushed_past_waits_for_the_next_pass(launched):
    out(launched, head="d" * 40, reason="its check fails on cccccccccccc over today's main")
    launched.poll()
    assert sends(launched) == [] and launched.lines("rebase") == []
    out(launched, head="d" * 40, reason="its check fails on dddddddddddd over today's main")
    launched.poll(NOW + timedelta(minutes=3))
    assert [given["clientRequestId"] for given in sends(launched)] == ["rebase|alpha|dddddddddddd"]


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
    """A brief pasted from an old task file: its line names a thread that is not this crew's."""
    add(kitchen, "alpha", text=task("alpha", "src/alpha/") + "Thread: mcp:an-old-thread\n")
    kitchen.poll(NOW - timedelta(minutes=30))
    (kitchen.home / "tasks/alpha.md").unlink()
    out(kitchen)
    kitchen.poll()
    assert sends(kitchen) == []
    assert gates(kitchen) == ["condition alpha: stale pull request with no thread to tell"]
