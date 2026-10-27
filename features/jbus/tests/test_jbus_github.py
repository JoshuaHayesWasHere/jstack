"""No T3 Code watch wakes a crew. Instead, jbus tells the crew what GitHub says it must act on,
once per head:

- A check that ran and failed is one message.
- A conflict before the review is another message.
- A conflict after the review is the rebase message.
- When a green pull request owes the home a line, jbus tells its crew that it passed.
- When a green pull request owes nothing, jbus tells its crew nothing.

Like `test_jbus_main_moved.py`, the tests run the real pass against the fakes."""

import json
from datetime import timedelta

import pytest

import jbus
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, gates, rows

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


MAIN = "9" * 40


def kept(kitchen, name):
    path = kitchen.stub / name
    return json.loads(path.read_text()) if path.exists() else {}


def red_on(kitchen, head, *tests, onto="", by="web-flow", parents=(MAIN,)):
    """Put the pull request at `head`, its check red on `tests`, in the job that its first eight
    hex digits number. With `onto`, the head is GitHub's merge of main into the branch at `onto`,
    as update-branch makes it; without, the crew pushed it. `by` and `parents` make another
    commit on `onto`: one the crew committed, or one with no second parent."""
    job = str(int(head[:8], 16))
    log = "".join(f"2026-10-26T13:36:00Z FAILED {test} - assert False\n" for test in tests)
    kitchen.set("logs.json", {**kept(kitchen, "logs.json"), job: log})
    if onto:
        made = [{"sha": sha} for sha in (onto, *parents)]
        merge = {"parents": made, "committer": {"login": by}}
        kitchen.set("commit-made.json", {**kept(kitchen, "commit-made.json"), head: merge})
    kitchen.set("open.json", [pull(kitchen, [failed(job)], head=head)])


def test_merges_of_main_red_on_the_failure_told_are_not_told_again_but_a_new_one_is(launched):
    """jmerge's update-branch makes a new head for each merge of main, and each one was a new
    `failed` tell, though the crew was told of that failure already (#494, 2026-10-26: nine)."""
    one, two, three, four, five = ("a" * 40, "b" * 40, "c" * 40, "d" * 40, "e" * 40)
    first, second = "tests/test_x.py::test_one", "tests/test_x.py::test_two"
    for minute, (head, test, onto) in enumerate(
        [
            (one, first, "f" * 40),
            (two, first, one),
            (three, first, two),
            (four, second, three),
            (five, first, ""),
        ]
    ):
        red_on(launched, head, test, onto=onto)
        passes(launched, 3 * minute)
    assert keys(launched) == [
        "failed|alpha|aaaaaaaaaaaa",
        "failed|alpha|dddddddddddd",
        "failed|alpha|eeeeeeeeeeee",
    ]


@pytest.mark.parametrize(
    "made",
    [{"by": "JoshuaHayesWasHere"}, {"parents": ()}],
    ids=["the crew's own merge of main", "a commit of GitHub's with one parent"],
)
def test_a_head_on_the_one_told_that_is_not_githubs_merge_of_main_is_told(launched, made):
    red_on(launched, "a" * 40, "tests/test_x.py::test_one")
    passes(launched, 0)
    red_on(launched, "b" * 40, "tests/test_x.py::test_one", onto="a" * 40, **made)
    passes(launched, 3)
    assert keys(launched) == ["failed|alpha|aaaaaaaaaaaa", "failed|alpha|bbbbbbbbbbbb"]


def test_the_record_of_a_tell_keeps_the_failure_it_told_beside_the_head(launched):
    red_on(launched, "a" * 40, "tests/test_x.py::test_one")
    passes(launched, 0)
    red_on(launched, "b" * 40, "tests/test_x.py::test_one", onto="a" * 40)
    passes(launched, 3)
    sent = jbus.read_json(launched.state / "sent.json", [])
    told = [key for key in sent if key.startswith(("failed|", "failure|"))]
    assert [key.rpartition("|")[0] for key in told] == [
        "failed|alpha",
        "failure|alpha|aaaaaaaaaaaa",
        "failed|alpha",
        "failure|alpha|bbbbbbbbbbbb",
    ]
    assert told[1].rpartition("|")[2] == told[3].rpartition("|")[2]


def test_494s_nine_merges_of_main_on_2026_10_26_are_told_once(launched):
    """The replay of #494: the crew's push 9f7bf939, then GitHub's nine merges of main into it,
    each red on the same test, as `gh api repos/JoshuaHayesWasHere/jstack/pulls/494/commits` and
    scout rejudge-loop give them."""
    red = (
        "features/repo-guards/tests/test_run_not_read.py::"
        "test_no_test_added_or_changed_on_this_branch_reads_words_and_runs_nothing"
    )
    heads = [
        "9f7bf9398161",
        "74dc4bb0f172",
        "2cbf4171b04e",
        "4d8d1f1b798c",
        "87834253b290",
        "5093dbdae626",
        "7c3bd4b63693",
        "f3e2de3d6c10",
        "f37b6509fa63",
        "5a93c17549b6",
    ]
    whole = [head + head[:12] + head[:12] + head[:4] for head in heads]
    for minute, head in enumerate(whole):
        red_on(launched, head, red, onto=whole[minute - 1] if minute else "")
        passes(launched, 3 * minute)
    assert keys(launched) == ["failed|alpha|9f7bf9398161"]


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


def test_a_draft_is_told_neither_green_nor_red_since_ci_runs_no_check_on_it(launched):
    """CI runs no check on a draft (check.yml), so what its rollup holds, a skipped check or one
    from before it was turned back to a draft, says nothing of the head: its crew marks it ready
    once its fix round is pushed, and the check that runs then is the one jbus tells of."""
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: none\n"))
    launched.set("jmerge.txt", "")
    launched.set("open.json", [{**pull(launched), "isDraft": True}])
    passes(launched, 0, 3)
    launched.set("open.json", [{**pull(launched, [failed()]), "isDraft": True}])
    passes(launched, 6, 9)
    assert sends(launched) == []
    launched.set("open.json", [{**pull(launched), "isDraft": False}])
    passes(launched, 12, 15)
    assert keys(launched) == ["green|alpha|cccccccccccc"]


REVIEWED = f"\n## Review\nVerdict: findings\nHead: {'b' * 40}\nFindings:\n- warning: a thing\n"


@pytest.mark.parametrize("mode", ["fixed", "after"])
def test_no_green_line_is_owed_after_a_fix_or_for_review_after_whatever_the_switch_holds(
    launched, mode
):
    """jbus is the only merger, so no home waits to hear that a pull request is green: a fixed
    pull request, or one whose brief says `Review: after`, owes no line on green, also with an id
    in `home-thread`."""
    brief = launched.home / "tasks" / "alpha.md"
    if mode == "after":
        brief.write_text(brief.read_text().replace("Review: review\n", "Review: after\n"))
        result(launched, "Reviewer: mcp:reviewer\n")
        launched.set("jmerge.txt", "")
    else:
        result(launched, f"Reviewer: mcp:reviewer\nFixed: {HEAD}\n" + REVIEWED)
    (launched.home / "home-thread").write_text("mcp:home\n")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert keys(launched) == []


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
    here = f"Stale base: at {HEAD}, check\n"
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace("Review: review\n", "Review: none\n"))
    result(launched, here)
    launched.set("jmerge.txt", "")
    launched.set("open.json", [pull(launched)])
    passes(launched, 0, 3)
    assert sends(launched) == []


def cancelled(conclusion="CANCELLED", job="11"):
    """A required check whose latest run ended cancelled, or past its `timeout-minutes`."""
    return {**failed(job), "conclusion": conclusion}


def ran(kitchen, attempt=1, head=HEAD, minutes=30, job="11", name="check"):
    """A job of workflow run 5 as GitHub gives it, the check's own by default: at `attempt`, on
    `head`, `minutes` long. Its attempt before, if any, ran as long."""
    times = {"started_at": "2026-10-24T10:00:00Z", "completed_at": f"2026-10-24T10:{minutes}:00Z"}
    steps = [{"name": "make check"}]
    kitchen.set(
        "jobs.json", {job: {"steps": steps, "run_attempt": attempt, "head_sha": head, **times}}
    )
    kitchen.set("run-jobs.json", {str(attempt - 1): [{"name": name, **times}]})


def reruns(kitchen):
    return [line for line in kitchen.log("gh") if line.startswith("run rerun")]


def to_home(kitchen):
    return [given for given in sends(kitchen) if given["threadId"] == "mcp:home"]


TIMEOUT = (
    "##[error]The job running on runner r has exceeded the maximum execution time of 30 minutes."
)


@pytest.mark.parametrize("conclusion", ["CANCELLED", "TIMED_OUT"])
def test_a_check_cancelled_at_its_first_attempt_is_run_again_once_and_journaled(
    launched, conclusion
):
    (launched.home / "home-id").write_text("mcp:home\n")
    ran(launched)
    launched.set("open.json", [pull(launched, [cancelled(conclusion)])])
    passes(launched, 0, 3, 6)
    assert reruns(launched) == ["run rerun 5 --failed"]
    assert launched.lines("cancelled") == [
        "cancelled alpha: ran #7's check again, run 5 at cccccccccccc"
    ]
    assert sends(launched) == []


@pytest.mark.parametrize("line", ["a line", "\x1b[36;1ma line in colour\x1b[0m"])
def test_a_check_cancelled_again_at_its_rerun_is_told_to_the_home_once_and_not_run_again(
    launched, line
):
    """GitHub's log has escape sequences in it, which `gh api` gives only when asked to."""
    (launched.home / "home-id").write_text("mcp:home\n")
    ran(launched, attempt=2)
    launched.set("logs.json", {"11": line + "\n" + TIMEOUT + "\n"})
    launched.set("open.json", [pull(launched, [cancelled()])])
    passes(launched, 0, 3, 6)
    said = "alpha: #7: its check was cancelled twice, at 30 min each: its timeout of 30 min"
    assert [given["message"] for given in to_home(launched)] == [said]
    assert reruns(launched) == [] and keys(launched) == ["cancelled|alpha|cccccccccccc"]
    assert rows(launched)["alpha"]["why"] == said.removeprefix("alpha: ")
    assert len([line for line in launched.log("gh") if "/attempts/1/jobs" in line]) == 1


def test_a_run_cancelled_at_a_head_the_pull_request_has_left_is_neither_run_nor_told(launched):
    (launched.home / "home-id").write_text("mcp:home\n")
    ran(launched, head="b" * 40)
    launched.set("open.json", [pull(launched, [cancelled()])])
    passes(launched, 0, 3)
    assert reruns(launched) == [] and sends(launched) == [] and launched.lines("cancelled") == []


def test_a_rerun_github_refuses_is_told_to_the_home_once_and_not_tried_again(launched):
    (launched.home / "home-id").write_text("mcp:home\n")
    launched.set("gh-no-rerun", "")
    ran(launched)
    launched.set("open.json", [pull(launched, [cancelled()])])
    passes(launched, 0, 3, 6)
    said = (
        "alpha: #7: its check was cancelled at 30 min, and GitHub did not run it again: "
        "run cannot be rerun"
    )
    assert reruns(launched) == ["run rerun 5 --failed"]
    assert [given["message"] for given in to_home(launched)] == [said]


def sharded(*parts):
    """The check workflow since its four parts: `check` failed because of its parts, and each
    part, job 12 on, ended as `parts` says."""
    each = [
        {**failed(str(12 + at)), "name": f"check {at + 1} of 4", "conclusion": conclusion}
        for at, conclusion in enumerate(parts)
    ]
    return [failed(), *each]


def test_a_check_failed_by_a_part_that_ran_past_its_timeout_is_run_again_not_told_to_the_crew(
    launched,
):
    ran(launched, job="13", name="check 2 of 4")
    launched.set(
        "open.json", [pull(launched, sharded("SUCCESS", "CANCELLED", "SUCCESS", "SUCCESS"))]
    )
    passes(launched, 0, 3)
    assert reruns(launched) == ["run rerun 5 --failed"] and sends(launched) == []


def test_a_part_cancelled_twice_is_told_with_its_own_minutes_and_timeout(launched):
    (launched.home / "home-id").write_text("mcp:home\n")
    ran(launched, attempt=2, job="13", name="check 2 of 4", minutes=31)
    launched.set("logs.json", {"13": TIMEOUT + "\n"})
    launched.set(
        "open.json", [pull(launched, sharded("SUCCESS", "CANCELLED", "SUCCESS", "SUCCESS"))]
    )
    passes(launched, 0, 3)
    said = "alpha: #7: its check was cancelled twice, at 31 min each: its timeout of 30 min"
    assert [given["message"] for given in to_home(launched)] == [said] and reruns(launched) == []


def test_a_part_that_failed_beside_one_cancelled_is_a_failed_check_for_the_crew(launched):
    launched.set(
        "open.json", [pull(launched, sharded("FAILURE", "CANCELLED", "SUCCESS", "SUCCESS"))]
    )
    passes(launched, 0, 3)
    assert reruns(launched) == [] and keys(launched) == ["failed|alpha|cccccccccccc"]


def test_a_check_told_cancelled_twice_that_then_passes_at_the_same_head_leaves_the_why(launched):
    (launched.home / "home-id").write_text("mcp:home\n")
    ran(launched, attempt=2)
    launched.set("open.json", [pull(launched, [cancelled()])])
    passes(launched, 0, 3)
    assert rows(launched)["alpha"]["why"].startswith("#7: its check was cancelled twice")
    launched.set("open.json", [pull(launched)])
    passes(launched, 6)
    assert "cancelled" not in rows(launched)["alpha"]["why"]


def blockers(kitchen):
    code, said = kitchen.main("--project", "demo", "clear")
    assert code == 0, said
    return said.strip()


@pytest.mark.parametrize("conclusion", ["CANCELLED", "TIMED_OUT"])
def test_a_cancelled_check_jbus_runs_again_is_no_blocker_jbus_clear_asks_a_fix_for(
    launched, conclusion
):
    """FlowBlockers' OneOwnerPerCancel: in the pass that runs a cancelled check again, the home's
    `jbus clear` briefs no fix of it, and spends no try of the retry cap."""
    (launched.home / "home-id").write_text("mcp:home\n")
    ran(launched)
    launched.set("open.json", [pull(launched, [cancelled(conclusion)])])
    passes(launched, 0)
    assert reruns(launched) == ["run rerun 5 --failed"]
    assert blockers(launched) == "nothing blocks this home"
    passes(launched, 3)
    assert blockers(launched) == "nothing blocks this home"


def test_a_check_cancelled_again_at_its_rerun_is_a_blocker_once_the_home_is_told(launched):
    (launched.home / "home-id").write_text("mcp:home\n")
    ran(launched, attempt=2)
    launched.set("open.json", [pull(launched, [cancelled()])])
    passes(launched, 0)
    assert len(to_home(launched)) == 1
    assert blockers(launched).startswith("fix check:alpha: its check failed, brief a fix")


def test_a_check_that_failed_is_a_blocker_at_the_first_pass(launched):
    (launched.home / "home-id").write_text("mcp:home\n")
    launched.set("open.json", [pull(launched, [failed()])])
    passes(launched, 0)
    assert reruns(launched) == []
    assert blockers(launched).startswith("fix check:alpha: its check failed, brief a fix")
