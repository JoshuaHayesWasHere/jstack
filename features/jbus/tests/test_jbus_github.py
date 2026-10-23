"""No T3 Code watch wakes a crew. Instead, jbus tells the crew what GitHub says it must act on,
once per head:

- A check that ran and failed is one message.
- A conflict before the review is another message.
- A conflict after the review is the rebase message.
- When a green pull request owes the home a line, jbus tells its crew that it passed.
- When a green pull request owes nothing, jbus tells its crew nothing.

Like `test_jbus_main_moved.py`, the tests run the real pass against the fakes."""

from datetime import timedelta

import pytest

import jbus
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, gates

HEAD = "c" * 40
JOB = "https://example.test/o/r/actions/runs/5/job/{}"
FAILED = (
    "jbus: check failed on your pull request #7 at {short}. In your own worktree, run the "
    'block of "The checks" and do what it prints. '
    "End your turn only once no check or proof you started runs in your "
    "worktree: wait for one that runs, in this turn."
)
CONFLICTED = (
    "jbus: your pull request #7 is in conflict with its base at {short}. In your own "
    'worktree, run the first block of "A conflict" as it is, and do what it prints: it does '
    "not rebase while a review is running. "
    "End your turn only once no check or proof you started runs in your "
    "worktree: wait for one that runs, in this turn."
)


@pytest.fixture
def launched(tmp_path, monkeypatch):
    """Alpha is a row that a first pass launched, and its thread's turn has ended. jbus tells
    nothing yet to a thread that is at work."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    yield kitchen
    kitchen.close()


def pull(kitchen, checks=None, mergeable="MERGEABLE", head=HEAD):
    made = {**kitchen.opened("alpha", 7), "mergeable": mergeable, "headRefOid": head}
    return {**made, **({"statusCheckRollup": checks} if checks is not None else {})}


def failed(job="11", name="check"):
    return {
        "name": name,
        "status": "COMPLETED",
        "conclusion": "FAILURE",
        "detailsUrl": JOB.format(job),
    }


def sends(kitchen):
    return [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]


def keys(kitchen):
    return [given["clientRequestId"] for given in sends(kitchen)]


def passes(kitchen, *minutes):
    for minute in minutes:
        kitchen.poll(NOW + timedelta(minutes=minute))


def test_a_check_that_failed_at_a_head_is_told_once_and_a_new_head_once_more(launched):
    launched.set("open.json", [pull(launched, [failed()])])
    passes(launched, 0, 3)
    assert sends(launched) == [
        {
            "threadId": "mcp:thread-1",
            "message": FAILED.format(short="cccccccccccc"),
            "mode": "queue",
            "clientRequestId": "failed|alpha|cccccccccccc",
        }
    ]
    assert launched.lines("failed") == ["failed alpha: told the crew (#7, cccccccccccc)"]
    launched.set("open.json", [pull(launched, [failed()], head="d" * 40)])
    passes(launched, 6, 9)
    assert keys(launched) == ["failed|alpha|cccccccccccc", "failed|alpha|dddddddddddd"]


def test_a_check_that_failed_with_no_step_run_is_not_told(launched):
    launched.set("jobs.json", {"11": {"steps": []}})
    launched.set("open.json", [pull(launched, [failed()])])
    passes(launched, 0, 3)
    assert sends(launched) == [] and launched.lines("failed") == []


def test_only_the_checks_that_ran_are_named_beside_one_that_never_started(launched):
    launched.set("jobs.json", {"11": {"steps": []}})
    launched.set("open.json", [pull(launched, [failed("11", "lint"), failed("12", "check")])])
    launched.poll()
    assert [given["message"] for given in sends(launched)] == [FAILED.format(short="cccccccccccc")]


def test_a_failed_check_is_kept_back_while_the_thread_is_at_work_and_told_after(launched):
    launched.t3.threads[0]["status"] = "running"
    launched.set("open.json", [pull(launched, [failed()])])
    said = launched.poll()
    assert sends(launched) == []
    assert "wait alpha: its thread is at work, so its crew is not told of cccccccccccc yet" in said
    launched.t3.threads[0]["status"] = "completed"
    passes(launched, 3, 6)
    assert keys(launched) == ["failed|alpha|cccccccccccc"]


def test_a_failed_check_of_a_pull_request_jbus_did_not_launch_is_not_told(tmp_path, monkeypatch):
    kitchen = Kitchen(tmp_path, monkeypatch)
    try:
        kitchen.brief("alpha", "Thread: mcp:crew\n")
        kitchen.set("open.json", [pull(kitchen, [failed()])])
        passes(kitchen, 0, 3)
        assert sends(kitchen) == [] and gates(kitchen) == []
    finally:
        kitchen.close()


def test_a_conflict_before_the_review_is_told_once_for_a_head(launched):
    launched.set("jmerge.txt", "wait 7 https://example.test/pull/7: it has no review yet\n")
    launched.set("open.json", [pull(launched, mergeable="CONFLICTING")])
    passes(launched, 0, 3)
    assert sends(launched) == [
        {
            "threadId": "mcp:thread-1",
            "message": CONFLICTED.format(short="cccccccccccc"),
            "mode": "queue",
            "clientRequestId": "conflict|alpha|cccccccccccc",
        }
    ]


def test_a_conflict_after_the_review_gets_the_rebase_message_and_no_other(launched):
    launched.set("jmerge.txt", "wait 7 https://example.test/pull/7: it conflicts with its base\n")
    launched.set("open.json", [pull(launched, mergeable="CONFLICTING")])
    passes(launched, 0, 3)
    assert keys(launched) == ["rebase|alpha|cccccccccccc"]
    assert launched.lines("conflict") == []


def test_a_head_told_of_its_conflict_before_the_review_gets_the_rebase_message_after_it(
    launched,
):
    launched.set("jmerge.txt", "wait 7 https://example.test/pull/7: it has no review yet\n")
    launched.set("open.json", [pull(launched, mergeable="CONFLICTING")])
    launched.poll()
    launched.set("jmerge.txt", "wait 7 https://example.test/pull/7: it conflicts with its base\n")
    passes(launched, 3, 6)
    assert keys(launched) == ["conflict|alpha|cccccccccccc", "rebase|alpha|cccccccccccc"]


def test_a_green_pull_request_reviewed_and_fixed_is_told_nothing(launched):
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(
        brief.read_text()
        + f"\n## Result\nStatus: done\nReviewer: mcp:reviewer\nFixed: {HEAD}\n"
        + f"\n## Review\nVerdict: findings\nHead: {'b' * 40}\nFindings:\n- warning: a thing\n"
        + "Finding: fixed, a thing\n"
    )
    launched.set("jmerge.txt", "")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3, 6)
    assert sends(launched) == []
    sent = jbus.read_json(launched.state / "sent.json", [])
    told = ("failed|", "conflict|", "rebase|", "mainmoved|")
    assert [key for key in sent if key.startswith(told)] == []


GREEN = (
    "jbus: every check of your pull request #7 passed at cccccccccccc, and the home is owed a "
    'line on green. In your own worktree, run the block of "The checks", then do what "The '
    'review" says of a green pull request: the message of the `Reviewer: none` line, or the '
    "`fixed and green` line. "
    "End your turn only once no check or proof you started runs in your "
    "worktree: wait for one that runs, in this turn."
)


def result(kitchen, lines):
    brief = kitchen.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text() + "\n## Result\nStatus: done\n" + lines)


def test_a_green_pull_request_whose_crew_wrote_its_reviewer_none_line_is_told_nothing(
    launched,
):
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: none\n"))
    result(launched, "Reviewer: none, the brief says Review: none\n")
    launched.set("jmerge.txt", "")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert sends(launched) == []


def test_a_green_pull_request_whose_brief_asks_for_no_review_is_told_once_for_a_head(launched):
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: none\n"))
    launched.set("jmerge.txt", "")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert [(given["clientRequestId"], given["message"]) for given in sends(launched)] == [
        ("green|alpha|cccccccccccc", GREEN)
    ]


REVIEWED = f"\n## Review\nVerdict: findings\nHead: {'b' * 40}\nFindings:\n- warning: a thing\n"


def test_a_fixed_green_pull_request_is_told_once_while_a_home_merges(launched):
    result(launched, f"Reviewer: mcp:reviewer\nFixed: {HEAD}\n" + REVIEWED)
    (launched.home / "home-thread").write_text("mcp:home\n")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert keys(launched) == ["green|alpha|cccccccccccc"]


@pytest.mark.parametrize("home", [True, False])
def test_a_green_after_pull_request_is_told_once_while_a_home_merges_with_its_reviewer_out(
    launched, home
):
    """A `Review: after` pull request merges on green, and its review never holds it. The crew
    tells the merging home that the pull request is green, while the crew's reviewer may still be
    at work."""
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: after\n"))
    result(launched, "Reviewer: mcp:reviewer\n")
    if home:
        (launched.home / "home-thread").write_text("mcp:home\n")
    launched.set("jmerge.txt", "")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert keys(launched) == (["green|alpha|cccccccccccc"] if home else [])


def test_a_pending_pull_request_that_owes_a_line_on_green_is_told_nothing_yet(launched):
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: none\n"))
    launched.set("jmerge.txt", "")
    running = [{"status": "IN_PROGRESS", "conclusion": ""}]
    launched.set("open.json", [pull(launched, running)])
    passes(launched, 0, 3)
    assert sends(launched) == []


def test_a_check_that_fails_again_after_its_rerun_at_one_head_is_told_once_more(launched):
    launched.set("open.json", [pull(launched, [failed()])])
    passes(launched, 0, 3)
    launched.set("jobs.json", {"21": {"steps": [{"name": "make check"}], "run_attempt": 2}})
    launched.set("open.json", [pull(launched, [failed("21")])])
    passes(launched, 6, 9)
    assert keys(launched) == ["failed|alpha|cccccccccccc", "refailed|alpha|cccccccccccc"]


def test_a_reviewed_pull_request_red_and_in_conflict_gets_the_rebase_message(launched):
    result(launched, "Reviewer: mcp:reviewer\n" + REVIEWED)
    launched.set("jmerge.txt", "wait 7 https://example.test/pull/7: check has not passed\n")
    launched.set("open.json", [pull(launched, [failed()], mergeable="CONFLICTING")])
    passes(launched, 0, 3, 6)
    assert keys(launched) == ["failed|alpha|cccccccccccc", "rebase|alpha|cccccccccccc"]


def test_a_fixed_pull_request_whose_scoped_reviewer_is_out_is_told_green_once_it_wrote(
    launched,
):
    fixed = f"Reviewer: mcp:reviewer\nFixed: {HEAD}\n" + REVIEWED
    result(launched, fixed + "Scoped reviewer: mcp:scoped, of " + HEAD + "\n")
    (launched.home / "home-thread").write_text("mcp:home\n")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert sends(launched) == []
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text() + f"\n## Review\nVerdict: clean\nHead: {HEAD}\n")
    passes(launched, 6, 9)
    assert keys(launched) == ["green|alpha|cccccccccccc"]


def test_a_gated_line_of_an_old_head_does_not_hold_back_green_at_a_new_one(launched):
    old = "Stale base: at " + "b" * 40 + ", check\n"
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: none\n"))
    result(launched, old)
    launched.set("jmerge.txt", "")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert keys(launched) == ["green|alpha|cccccccccccc"]


def test_a_gated_line_of_this_head_holds_back_green(launched):
    here = f"Stuck: at {HEAD}, check\n"
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: none\n"))
    result(launched, here)
    launched.set("jmerge.txt", "")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert sends(launched) == []


STALE = f"Stale base: at {HEAD}, check\n"


def on(kitchen, base, checks):
    return {**pull(kitchen, checks), "baseRefName": base}


def reruns(kitchen):
    return [line for line in kitchen.log("gh") if line.startswith("run rerun")]


@pytest.mark.parametrize("base", ["train/macos", "main"])
def test_a_failed_check_on_a_stale_base_is_rerun_once_and_a_second_failure_is_told_to_rebase(
    launched, base
):
    """#326: its check failed at a head whose base had moved, so its crew wrote `Stale base:` and
    waited for the rebase message. jmerge never runs a fresh check while the check is red, so that
    message never came. jbus reruns the failed jobs once for the head, and when they fail again it
    sends the rebase message, onto the pull request's own base."""
    launched.set("open.json", [on(launched, base, [failed()])])
    launched.poll(NOW)
    result(launched, STALE)
    passes(launched, 3, 6, 9)
    assert reruns(launched) == ["run rerun 5 --failed"]
    assert launched.lines("rerun") == ["rerun alpha: ran the failed jobs again (#7, cccccccccccc)"]
    launched.set("jobs.json", {"21": {"steps": [{"name": "make check"}], "run_attempt": 2}})
    launched.set("open.json", [on(launched, base, [failed("21")])])
    passes(launched, 12, 15, 18)
    assert reruns(launched) == ["run rerun 5 --failed"]
    assert keys(launched) == ["failed|alpha|cccccccccccc", "rebase|alpha|cccccccccccc"]
    told = sends(launched)[-1]["message"]
    assert f"jbus: {base} moved under your pull request #7" in told
    assert f"onto origin/{base}," in told
    assert launched.lines("rebase") == ["rebase alpha: told the crew (#7, cccccccccccc)"]


def test_a_stale_base_whose_rerun_passes_is_told_nothing_more(launched):
    launched.set("open.json", [on(launched, "train/macos", [failed()])])
    launched.poll(NOW)
    result(launched, STALE)
    passes(launched, 3)
    launched.set("open.json", [on(launched, "train/macos", None)])
    passes(launched, 6, 9)
    assert reruns(launched) == ["run rerun 5 --failed"]
    assert keys(launched) == ["failed|alpha|cccccccccccc"]


def test_a_stale_base_whose_rerun_passes_is_told_green_when_the_home_is_owed_the_line(launched):
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: none\n"))
    launched.set("jmerge.txt", "")
    launched.set("open.json", [on(launched, "train/macos", [failed()])])
    launched.poll(NOW)
    result(launched, STALE)
    passes(launched, 3)
    launched.set("open.json", [on(launched, "train/macos", None)])
    passes(launched, 6, 9)
    assert keys(launched) == ["failed|alpha|cccccccccccc", "green|alpha|cccccccccccc"]
