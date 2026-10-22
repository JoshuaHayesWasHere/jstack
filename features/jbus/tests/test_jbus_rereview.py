"""A rebase that changed the content of a reviewed patch gets one scoped review, which jbus
asks its crew to launch, once per head. Run as `tests/test_jbus_unlock.py` runs: the real
pass, against the fakes, with the line `jmerge` prints for such a pull request."""

from datetime import timedelta

import pytest

import jbus
import jsettings
from jbus import rebase
from jmerge import rangediff, ready
from test_jbus_kitchen import NOW
from test_jbus_queue import add, gates
from test_jbus_unlock import sends

URL = "https://example.test/pull/7"
OLD = f"{'1' * 40}..{'a' * 40}"


def command(head):
    return f"git range-diff --no-color {OLD} {'2' * 40}..{head}"


def waits(head):
    return f"the rebase changed the content after its review; scoped review of {command(head)}"


def out(kitchen, head="c" * 40, reason=None, word="wait"):
    """Alpha's pull request #7 at `head`, and what `jmerge` prints about it."""
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "headRefOid": head}])
    kitchen.set("jmerge.txt", f"{word} 7 {URL}: {reason or waits(head)}\n")


@pytest.fixture
def launched(kitchen):
    """Alpha, launched by a pass, so it has a launch record and its `Thread:` line, with
    its thread's turn ended: one at work is told nothing."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.t3.threads[0]["status"] = "completed"
    return kitchen


def test_a_rebase_that_changed_the_content_asks_its_crew_for_one_scoped_review(launched):
    out(launched)
    said = launched.poll()
    head = "c" * 40
    (given,) = sends(launched)
    assert given == {
        "threadId": "mcp:thread-1",
        "message": (
            "jbus: your rebase of pull request #7 changed its content after its review "
            f"({command(head)}). If the Result already has a `Scoped reviewer:` line that names "
            "this head, launch nothing more. Otherwise launch ONE scoped reviewer, not a full "
            'review: the same way the crew skill\'s "The review" launches a reviewer, with the '
            f"message `/pr-review run alpha scoped {OLD} {'2' * 40}..{head}`. Add `Scoped "
            f"reviewer: <threadId>, of {head}` to the Result, in place of a `Scoped reviewer:` "
            "line that names another head no `## Review` has. Do not rebase again until its "
            "`## Review` is written. Handle its findings as a review's: a `Finding:` line for each."
        ),
        "mode": "queue",
        "clientRequestId": "rereview|alpha|cccccccccccc",
    }
    line = "rereview alpha: asked the crew for a scoped review (#7, cccccccccccc)"
    assert line in said and launched.lines("rereview") == [line]
    assert "rereview|alpha|cccccccccccc" in jbus.read_json(launched.state / "sent.json", [])
    assert launched.lines("rebase") == [] and gates(launched) == []


def test_a_head_is_asked_once_and_a_new_head_after_another_rebase_once_more(launched):
    out(launched)
    for minutes in (0, 3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert len(sends(launched)) == 1
    out(launched, head="d" * 40)
    for minutes in (9, 12):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert [given["clientRequestId"] for given in sends(launched)] == [
        "rereview|alpha|cccccccccccc",
        "rereview|alpha|dddddddddddd",
    ]
    assert launched.lines("rereview") == [
        "rereview alpha: asked the crew for a scoped review (#7, cccccccccccc)",
        "rereview alpha: asked the crew for a scoped review (#7, dddddddddddd)",
    ]


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
def test_a_line_that_does_not_wait_on_a_scoped_review_asks_nobody(launched, word, reason):
    out(launched, reason=reason, word=word)
    launched.poll()
    assert sends(launched) == [] and launched.lines("rereview") == []


def test_a_pull_request_with_no_launch_record_is_asked_nothing(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n")
    out(kitchen)
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("rereview") == [] and gates(kitchen) == []


def test_a_range_diff_of_a_head_the_crew_has_pushed_past_waits_for_the_next_pass(launched):
    out(launched, head="d" * 40, reason=waits("c" * 40))
    launched.poll()
    assert sends(launched) == [] and launched.lines("rereview") == []
    out(launched, head="d" * 40)
    launched.poll(NOW + timedelta(minutes=3))
    assert [given["clientRequestId"] for given in sends(launched)] == [
        "rereview|alpha|dddddddddddd"
    ]


def test_with_no_thread_line_it_is_a_gate_once_per_head(launched):
    (launched.home / "tasks/alpha.md").unlink()
    out(launched)
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    gate = f"condition alpha: {rebase.NO_THREAD}"
    assert sends(launched) == [] and gates(launched) == [gate]
    out(launched, head="d" * 40)
    launched.poll(NOW + timedelta(minutes=6))
    assert gates(launched) == [gate, gate]


def test_a_message_t3_code_refuses_is_a_gate_once_and_goes_when_it_is_taken(launched):
    out(launched)
    launched.t3.refuse_send = True
    for minutes in (0, 3):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert gates(launched) == [f"condition alpha: {rebase.REFUSED}"]
    assert launched.lines("rereview") == [] and len(sends(launched)) == 2
    launched.t3.refuse_send = False
    launched.poll(NOW + timedelta(minutes=6))
    assert launched.lines("rereview") == [
        "rereview alpha: asked the crew for a scoped review (#7, cccccccccccc)"
    ]
    assert len(launched.t3.messages) == 1


def test_a_message_with_no_answer_waits_and_is_tried_again(launched):
    out(launched)
    launched.t3.lose_send = True
    said = launched.poll()
    (wait,) = [line for line in said if line.startswith("wait alpha: ")]
    assert wait.startswith("wait alpha: its crew could not be asked for a scoped review (")
    assert launched.lines("rereview") == [] and gates(launched) == []
    launched.t3.lose_send = False
    launched.poll(NOW + timedelta(minutes=3))
    assert launched.lines("rereview") == [
        "rereview alpha: asked the crew for a scoped review (#7, cccccccccccc)"
    ]


def test_a_scoped_review_needs_no_default_branch(launched):
    out(launched)
    launched.git("symbolic-ref", "-d", "refs/remotes/origin/HEAD")
    launched.poll()
    assert len(sends(launched)) == 1


def test_the_line_jbus_reads_is_the_line_jmerge_prints():
    verdict = rangediff.Verdict(False, command("c" * 40), "why")
    line = f"wait 7 {URL}: {ready.short_on_content(verdict)}"
    number, reason, ask = rebase.content(line)
    assert (number, reason, ask.head) == (7, waits("c" * 40), "c" * 40)


def unsaid(head):
    """What `jmerge` prints after the url for a drop with no line at this head."""
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
    assert sends(launched) == [] and launched.lines("drops") == []


def test_the_drop_line_jbus_reads_is_the_line_jmerge_prints():
    assert rebase.drops(f"wait 7 {URL}: {unsaid('c' * 40)}") == (7, URL, "cccccccccccc")
    assert rebase.drops(f"hold 7 {URL}: {unsaid('c' * 40)}") is None
