"""A rebase that changed the content of a reviewed patch gets one scoped review, which jbus
launches itself, once per head, in the crew's worktree, and of which it asks the crew nothing. Like
`test_jbus_unlock.py`, the tests run the real pass against the fakes, with the line `jmerge` prints
for such a pull request."""

import json
from datetime import timedelta

import pytest

import jbus
import jsettings
from jbus import rebase, reviewlaunch
from jmerge import rangediff, ready
from jroles import ledger
from test_jbus_kitchen import NOW, asks
from test_jbus_queue import add, gates
from test_jbus_unlock import sends

URL = "https://example.test/pull/7"
OLD = f"{'1' * 40}..{'a' * 40}"
TREE = "/worktrees/alpha"


def command(head):
    return f"git range-diff --no-color {OLD} {'2' * 40}..{head}"


def waits(head):
    return f"the rebase changed the content after its review; scoped review of {command(head)}"


def out(kitchen, head="c" * 40, reason=None, word="wait"):
    """Open alpha's pull request #7 at `head`, and set what `jmerge` prints about it."""
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "headRefOid": head}])
    kitchen.set("jmerge.txt", f"{word} 7 {URL}: {reason or waits(head)}\n")


def scoped(kitchen):
    """Each scoped reviewer jbus asked T3 Code to launch, refused or not."""
    return [
        given
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_launch" and given["title"] == "review: alpha, scoped"
    ]


def keys(kitchen):
    """The launch keys `sent.json` holds: `rereview|<slug>|<head 12>`, and no event's key."""
    sent = jbus.read_json(kitchen.state / "sent.json", [])
    return [key for key in sent if key.startswith("rereview|") and " " not in key]


def recorded(kitchen):
    """Each line of `review-launches.jsonl`: its slug, thread, head, kind and seat."""
    return [
        (one["slug"], one["thread"], one["head"], one["kind"], one["n"])
        for one in map(json.loads, (kitchen.state / reviewlaunch.LAUNCHES).read_text().splitlines())
    ]


def brief(kitchen):
    return (kitchen.home / "tasks/alpha.md").read_text()


@pytest.fixture
def launched(kitchen):
    """Alpha is a row that a pass launched, so it has a launch record, its `Thread:` line and a
    Result. Its thread's turn has ended, in a worktree T3 Code names."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.t3.threads[0].update(status="completed", worktreePath=TREE)
    kitchen.t3.at_work.discard("mcp:thread-1")
    path = kitchen.home / "tasks/alpha.md"
    path.write_text(path.read_text() + "\n## Result\nStatus: done\n")
    return kitchen


def test_a_changed_rebase_launches_one_scoped_reviewer_and_sends_its_crew_nothing(launched):
    out(launched)
    head = "c" * 40
    for minutes in (0, 3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    (given,) = scoped(launched)
    assert given["message"] == f"/pr-review run alpha scoped {OLD} {'2' * 40}..{head}"
    assert given["workspaceStrategy"] == {
        "type": "existing_worktree",
        "worktreePath": TREE,
        "branch": "alpha",
    }
    made = launched.t3.threads[-1]["threadId"]
    assert brief(launched).endswith(f"Scoped reviewer: {made}, of {head}\n")
    assert keys(launched) == ["rereview|alpha|cccccccccccc"]
    line = f"rereview alpha: launched the scoped reviewer {made} (#7, cccccccccccc)"
    assert launched.lines("rereview") == [line]
    assert sends(launched) == [] and gates(launched) == []
    assert recorded(launched) == [("alpha", made, head, "scoped", 1)]


def test_a_head_gets_one_reviewer_and_a_new_head_after_another_rebase_one_more(launched):
    out(launched)
    for minutes in (0, 3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    out(launched, head="d" * 40)
    for minutes in (9, 12):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert [given["message"][-12:] for given in scoped(launched)] == ["c" * 12, "d" * 12]
    assert keys(launched) == ["rereview|alpha|cccccccccccc", "rereview|alpha|dddddddddddd"]
    assert sends(launched) == []


def test_a_head_whose_result_names_its_scoped_reviewer_gets_no_other(launched):
    path = launched.home / "tasks/alpha.md"
    named = f"Scoped reviewer: mcp:earlier\nScoped reviewer: mcp:reviewer, of {'c' * 40}\n"
    path.write_text(path.read_text() + named)
    out(launched)
    launched.poll()
    launched.poll(NOW + timedelta(minutes=3))
    assert scoped(launched) == [] and sends(launched) == [] and keys(launched) == []
    assert recorded(launched) == [("alpha", "mcp:reviewer", "c" * 40, "scoped", 1)]


CARRIED = (
    "review carried over: range-diff 111111111111..aaaaaaaaaaaa 222222222222..cccccccccccc clean"
)


@pytest.mark.parametrize(
    ("word", "reason"),
    [
        ("ready", f"alpha alpha, {CARRIED}"),
        ("merged", f'alpha abc1234 "the task", {CARRIED}, revert: gh pr revert {URL}'),
        ("hold", waits("c" * 40)),
        ("wait", "the rebase changed the content after its review; scoped review of nothing"),
        ("wait", waits("c" * 40) + " and more"),
    ],
    ids=["carried over", "merged", "held", "no command", "not the whole line"],
)
def test_a_line_that_does_not_wait_on_a_scoped_review_launches_nothing(launched, word, reason):
    out(launched, reason=reason, word=word)
    launched.poll()
    assert scoped(launched) == [] and asks(launched) == [] and launched.lines("rereview") == []


def test_a_pull_request_with_no_launch_record_gets_no_reviewer(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n")
    out(kitchen)
    kitchen.poll()
    assert scoped(kitchen) == [] and sends(kitchen) == [] and gates(kitchen) == []


def test_a_range_diff_of_a_head_the_crew_has_pushed_past_waits_for_the_next_pass(launched):
    out(launched, head="d" * 40, reason=waits("c" * 40))
    launched.poll()
    assert scoped(launched) == [] and launched.lines("rereview") == []
    out(launched, head="d" * 40)
    launched.poll(NOW + timedelta(minutes=3))
    assert keys(launched) == ["rereview|alpha|dddddddddddd"] and len(scoped(launched)) == 1


def test_a_head_github_has_moved_past_since_the_list_gets_no_reviewer(launched):
    out(launched)
    launched.set("head-now.json", {"7": {"headRefOid": "d" * 40}})
    launched.poll()
    assert scoped(launched) == [] and keys(launched) == []
    (launched.stub / "head-now.json").unlink()
    launched.poll(NOW + timedelta(minutes=3))
    assert len(scoped(launched)) == 1


def test_a_crew_at_work_gets_its_reviewer_once_its_turn_ends(launched):
    out(launched)
    launched.t3.threads[0]["status"] = "running"
    launched.t3.at_work.add("mcp:thread-1")
    launched.poll()
    assert scoped(launched) == [] and keys(launched) == []
    launched.t3.threads[0]["status"] = "completed"
    launched.t3.at_work.discard("mcp:thread-1")
    launched.poll(NOW + timedelta(minutes=3))
    assert len(scoped(launched)) == 1


def test_with_no_thread_line_it_is_a_gate_once_per_head(launched):
    (launched.home / "tasks/alpha.md").unlink()
    out(launched)
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    gate = f"condition alpha: {rebase.NO_THREAD}"
    assert scoped(launched) == [] and sends(launched) == [] and gates(launched) == [gate]
    out(launched, head="d" * 40)
    launched.poll(NOW + timedelta(minutes=6))
    assert gates(launched) == [gate, gate]


def test_a_crew_with_no_worktree_gets_no_reviewer_and_a_gate_once_per_head(launched):
    del launched.t3.threads[0]["worktreePath"]
    out(launched)
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    gate = f"condition alpha: {rebase.NO_TREE}"
    assert scoped(launched) == [] and keys(launched) == [] and gates(launched) == [gate]
    out(launched, head="d" * 40)
    launched.poll(NOW + timedelta(minutes=6))
    assert gates(launched) == [gate, gate] and sends(launched) == []


def test_a_capped_review_pool_launches_nothing_and_is_a_gate_once_until_it_has_room(
    launched, jstack_config
):
    (jstack_config.parent / "roles").write_text(
        "review: claudeAgent claude-sonnet-5-5 claudeAgent effort=high\n"
    )
    full = ledger.file_of("claudeAgent")
    full.write_text(f"five_hour 100 {int((NOW + timedelta(minutes=40)).timestamp())}\n")
    out(launched)
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert scoped(launched) == [] and keys(launched) == []
    assert gates(launched) == [f"condition alpha: {rebase.CAPPED}"]
    full.unlink()
    launched.poll(NOW + timedelta(minutes=6))
    assert len(scoped(launched)) == 1 and keys(launched) == ["rereview|alpha|cccccccccccc"]


def test_a_role_map_that_gives_the_review_no_model_launches_one_reviewer_that_inherits(
    launched, jstack_config
):
    (jstack_config.parent / "roles").write_text("review: not a line the role map reads\n")
    out(launched)
    said = launched.poll()
    (given,) = scoped(launched)
    assert "modelSelection" not in given
    assert any(line.startswith("note alpha: the role map gives the review no") for line in said)


def test_a_launch_t3_code_refuses_marks_nothing_is_a_gate_once_and_goes_when_taken(launched):
    out(launched)
    launched.t3.refuse = "no more threads"
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert len(scoped(launched)) == 2 and keys(launched) == []
    assert gates(launched) == [f"condition alpha: {rebase.LAUNCH_REFUSED}"]
    assert "Scoped reviewer:" not in brief(launched) and launched.lines("rereview") == []
    launched.t3.refuse = ""
    launched.poll(NOW + timedelta(minutes=6))
    made = launched.t3.threads[-1]["threadId"]
    assert brief(launched).endswith(f"Scoped reviewer: {made}, of {'c' * 40}\n")
    assert keys(launched) == ["rereview|alpha|cccccccccccc"] and sends(launched) == []


def test_a_launch_with_no_answer_keeps_its_key_and_is_not_tried_again(launched):
    out(launched)
    launched.t3.lose = "after"
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert len(scoped(launched)) == 1 and keys(launched) == ["rereview|alpha|cccccccccccc"]
    assert gates(launched) == [f"condition alpha: {rebase.LAUNCH_LOST}"]
    assert sends(launched) == []


ERROR = "- error src/alpha/a.py:3 the rebase lost the guard"


def written(kitchen, head, found):
    """Add the scoped `## Review` of `head` its reviewer writes, with `found` as its findings."""
    path = kitchen.home / "tasks/alpha.md"
    section = (
        "\n## Review\nBy: claudeAgent claude-sonnet-5-5 high #1\n"
        f"Verdict: {'findings' if found else 'clean'}\nScope: range-diff {OLD} {'2' * 40}..{head}\n"
        f"Head: {head}\nSent to: not sent\nFindings:\n{found or '- none'}\n"
    )
    path.write_text(path.read_text() + section)


def test_the_crew_hears_once_of_its_scoped_review_with_its_findings_by_id(launched):
    head = "c" * 40
    out(launched)
    launched.poll()
    assert sends(launched) == []
    written(launched, head, ERROR)
    out(launched, reason="the scoped review's findings have no answer")
    for minutes in (3, 6, 9):
        launched.poll(NOW + timedelta(minutes=minutes))
    (given,) = sends(launched)
    assert given["threadId"] == "mcp:thread-1"
    assert given["message"].startswith(
        f"jbus: alpha's pull request #7 at {head[:12]} has its review"
    )
    assert "F1 [" in given["message"] and "the rebase lost the guard" in given["message"]
    assert len(scoped(launched)) == 1


def test_the_crew_hears_nothing_of_a_clean_scoped_review(launched):
    out(launched)
    launched.poll()
    written(launched, "c" * 40, "")
    out(launched, reason="checks are running")
    for minutes in (3, 6, 9):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert sends(launched) == [] and len(scoped(launched)) == 1


def test_the_line_jbus_reads_is_the_line_jmerge_prints():
    verdict = rangediff.Verdict(False, command("c" * 40), "why")
    line = f"wait 7 {URL}: {ready.short_on_content(verdict)}"
    number, reason, ask = rebase.content(line)
    assert (number, reason, ask.head) == (7, waits("c" * 40), "c" * 40)


def unsaid(head):
    """Return what `jmerge` prints after the url for a drop with no line at this head."""
    return ready.drops((ready.Drop("a.py", 2, 1),), "", head, user=jsettings.DEFAULTS)[1]


def test_a_drop_nobody_explained_is_told_to_its_crew_once_per_head(launched):
    head = "c" * 40
    out(launched, reason=unsaid(head))
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    (given,) = sends(launched)
    assert given == {
        "threadId": "mcp:thread-1",
        "message": (
            "jbus: the rebase dropped 2 of main's lines in a.py and 1 of its own in a.py with "
            "no Dropped on rebase line at cccccccccccc (pull request #7). Put the lines back, "
            "commit and push. Or, where a line is gone on purpose, add one line to the Result "
            "for each file, with the counts above: `Dropped on rebase: <file>, <n> of main's, "
            "<m> of its own, at cccccccccccc: <why>`. The scoped review rules on each one. "
            "End your turn only once no check or proof you started runs in your "
            "worktree: wait for one that runs, in this turn."
        ),
        "mode": "queue",
        "clientRequestId": "drops|alpha|cccccccccccc",
    }
    told = "drops alpha: told the crew of the drop (#7, cccccccccccc)"
    assert launched.lines("drops") == [told] and gates(launched) == []
    out(launched, head="d" * 40, reason=unsaid("d" * 40))
    for minutes in (6, 9):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert [given["clientRequestId"] for given in sends(launched)] == [
        "drops|alpha|cccccccccccc",
        "drops|alpha|dddddddddddd",
    ]


def test_a_drop_message_t3_code_refuses_is_a_gate_once(launched):
    out(launched, reason=unsaid("c" * 40))
    launched.t3.refuse_send = True
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert gates(launched) == [f"condition alpha: {rebase.REFUSED}"]
    assert launched.lines("drops") == []


def ruled(head, files="a.py"):
    """Return what `jmerge` prints after the url for drops the Result explains at this head, which
    no scoped review has ruled on yet."""
    return ready.SCOPED_UNRULED.format(files=files, command=command(head))


def test_drops_the_result_explains_get_one_scoped_reviewer_over_two_passes(launched):
    head = "c" * 40
    out(launched, reason=ruled(head))
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    (given,) = scoped(launched)
    assert given["message"] == f"/pr-review run alpha scoped {OLD} {'2' * 40}..{head}"
    made = launched.t3.threads[-1]["threadId"]
    assert brief(launched).endswith(f"Scoped reviewer: {made}, of {head}\n")
    line = f"rereview alpha: launched the scoped reviewer {made} (#7, cccccccccccc)"
    assert launched.lines("rereview") == [line] and gates(launched) == []
    assert sends(launched) == []


def test_drops_whose_scoped_reviewer_the_result_names_at_this_head_get_no_other(launched):
    path = launched.home / "tasks/alpha.md"
    path.write_text(path.read_text() + f"Scoped reviewer: mcp:reviewer, of {'c' * 40}\n")
    out(launched, reason=ruled("c" * 40))
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert scoped(launched) == [] and sends(launched) == [] and launched.lines("rereview") == []


def test_drops_of_a_head_already_given_its_reviewer_get_no_other(launched):
    out(launched)
    launched.poll()
    out(launched, reason=ruled("c" * 40))
    launched.poll(NOW + timedelta(minutes=3))
    assert len(scoped(launched)) == 1 and keys(launched) == ["rereview|alpha|cccccccccccc"]


def test_the_unruled_line_jbus_reads_is_the_line_jmerge_prints():
    said = ready.drops(
        (ready.Drop("a.py", 2, 1),),
        "Dropped on rebase: a.py, 2 of main's, 1 of its own, at cccccccccccc: on purpose\n",
        "c" * 40,
        user=jsettings.DEFAULTS,
        command=command("c" * 40),
    )
    assert said == ("wait", ruled("c" * 40))
    number, reason, ask = rebase.content(f"wait 7 {URL}: {said[1]}")
    assert (number, reason, ask.kind, ask.head) == (7, ruled("c" * 40), "rereview", "c" * 40)


@pytest.mark.parametrize(
    ("word", "reason", "head"),
    [
        ("wait", "the scoped review has not ruled on the drops in a.py", "c" * 40),
        ("hold", "needs user, the review did not uphold the drop in a.py: why", "c" * 40),
        ("wait", unsaid("c" * 40), "d" * 40),
    ],
    ids=["explained", "ruled against", "a head the crew pushed past"],
)
def test_a_drop_that_does_not_wait_on_the_crew_at_this_head_tells_nobody(
    launched, word, reason, head
):
    out(launched, head=head, reason=reason, word=word)
    launched.poll()
    assert asks(launched) == [] and launched.lines("drops") == []


def test_the_drop_line_jbus_reads_is_the_line_jmerge_prints():
    assert rebase.drops(f"wait 7 {URL}: {unsaid('c' * 40)}") == (7, URL, "cccccccccccc")
    assert rebase.drops(f"hold 7 {URL}: {unsaid('c' * 40)}") is None
