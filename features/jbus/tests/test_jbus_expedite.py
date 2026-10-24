"""When a pull request is short of something its crew can fix, jbus tells the crew what to do,
once per reason and head. The desk gets a message only when that did not work. Like
`test_jbus_guarded_ask.py`, the tests run the real pass against the fakes, with the lines
`jmerge` prints, over commits that are really there."""

import os
import re
import subprocess
from datetime import timedelta

import pytest

import jbus
import jsettings
from jbriefs import findings
from jbus import merge
from jmerge import ready
from jroles import ledger
from test_jbus_kitchen import GATE, NOW, PROJECT
from test_jbus_queue import add, gates
from test_jbus_unlock import sends
from test_pr_review_skill import ASKED, block
from testing.paths import REPO

URL = "https://example.test/pull/7"
DONE = "\n## Result\nStatus: done\nBranch: alpha   Pull request: {url}\nLeft: none\n"
REVIEW = "\n## Review\nVerdict: findings\nHead: {saw}\nFindings:\n- minor a.py:1 a made up one\n"
NO_FIXED = "its findings are not handled: the Result has no Fixed line"
NOT_PUSHED = "its findings are not handled: nothing was pushed after them"
NO_FINDING = "its findings are not handled: 1 of 2 have no Finding line"
NO_SECOND = "its fix changed more than the findings named: the second pass is not written"
NO_FIX_REVIEW = "its fix is not reviewed: the scoped review of it is not written"
NO_REVIEW = "it has no review yet"
NO_TWICE = "its second review is not written at bbbbbbbbbbbb"
RENUMBER = ready.MIGRATION_TAKEN.format(
    name="0005_insulin", number="0005", default="main", free="0006"
)
ENDED = ("completed", "failed", "interrupted", "cancelled")


def later(minutes):
    return NOW + timedelta(minutes=minutes)


class Short:
    """Alpha is a row that a pass launched. Its thread ended its turn with pull request #7 open
    at the second of two commits. A pass has read its Result, and the test has cleared what the
    first passes sent from the outbox and the webhook."""

    def __init__(self, kitchen):
        self.kitchen = kitchen
        add(kitchen, "alpha")
        assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
        (self.thread,) = kitchen.t3.threads
        self.thread["status"] = "completed"
        self.start = self.commit()
        self.saw = self.commit("the task")
        self.head = self.commit("the rebase")
        self.launched = (kitchen.home / "tasks/alpha.md").read_text()
        self.minute = 0
        self.heard()

    def heard(self, result=""):
        """Run a pass that reads the Result as it is, while the pull request is short of nothing
        yet. Then clear what the pass sent from the outbox and the webhook."""
        self.out("", result=result)
        self.kitchen.poll(NOW - timedelta(minutes=20 - self.minute))
        jbus.write_json(self.kitchen.state / "outbox.json", [])
        self.kitchen.webhook.posts.clear()

    def commit(self, message=""):
        if message:
            self.kitchen.git("commit", "-q", "--allow-empty", "-m", message)
        asked = ["git", "rev-parse", "HEAD"]
        ran = subprocess.run(asked, cwd=self.kitchen.checkout, capture_output=True, text=True)
        return ran.stdout.strip()

    def out(self, reason, word="wait", result="", head=None, review=True):
        """Write what the crew wrote, and set what `jmerge` says its pull request is short of."""
        head = head or self.head
        text = self.launched + DONE.format(url=URL) + result
        text += REVIEW.format(saw=self.saw) if review else ""
        (self.kitchen.home / "tasks/alpha.md").write_text(text)
        self.kitchen.set("open.json", [{**self.kitchen.opened("alpha", 7), "headRefOid": head}])
        self.kitchen.set("jmerge.txt", f"{word} 7 {URL}: {reason}\n" if reason else "")

    def passes(self, count):
        """Run that many passes, a minute apart, and return everything they said."""
        said = []
        for _ in range(count):
            said += self.kitchen.poll(later(self.minute))
            self.minute += 1
        return said

    def unruled(self, files="a.py"):
        return f"needs user, the review of {self.head[:12]} did not rule on the drops in {files}"

    def rebased(self):
        return f"Rebase: patch changed in a.py, before {self.saw}, head {self.head}\n"


@pytest.fixture
def short(kitchen):
    return Short(kitchen)


FINDING_LINES = findings.ANSWER
SAYS = {
    "unfixed": (
        f"Write one line in the Result for each finding, {FINDING_LINES}, and then the `Fixed:` "
        "line: `Fixed: <the head you pushed>` where you pushed a fix, or `Fixed: none needed, "
        "<reason>` when every finding is declined. Push nothing for a `Fixed: none needed`."
    ),
    "unpushed": (
        "The `Fixed:` line names the head the review saw, so no fix is at the head. Push the "
        "fix and set `Fixed:` to the head you pushed. Or, when every finding is declined, write "
        f"{FINDING_LINES} for each and `Fixed: none needed, <reason>`, and push nothing for that."
    ),
    "unended": (
        f"Write the lines that are missing, one for each finding of both passes, {FINDING_LINES}. "
        "Set `Fixed:` to the head you pushed where you push for them, and push nothing where "
        "you decline them."
    ),
    "second": (
        'Launch the second reviewer now, the way the crew skill\'s "A second pass" says, with '
        "the message `/pr-review run alpha again`, and add `Second reviewer: <threadId>` to the "
        "Result, in place of a `Second reviewer:` line whose thread wrote no `## Review`. Push "
        "nothing until its `## Review` is written."
    ),
    "twice": (
        "Its brief says `Review: twice`: launch its second review of the head you pushed now, "
        'the way the crew skill\'s "The review" says, with the message `/pr-review run alpha '
        "again`, and add `Second reviewer: <threadId>` to the Result, in place of a `Second "
        "reviewer:` line whose thread wrote no `## Review`. Fix nothing it finds: its findings "
        "go to a cleanup row."
    ),
    "fix": (
        "Launch ONE scoped reviewer of the fix now, not a full review, the way the crew skill's "
        '"The review" launches a reviewer, with the message `/pr-review run alpha scoped {old} '
        "{new}`, and add `Scoped reviewer: <threadId>, of {head}` to the Result, in place of a "
        "`Scoped reviewer:` line whose thread wrote no `## Review`. Push nothing until its "
        "`## Review` is written."
    ),
    "unreviewed": (
        "No thread titled `review: alpha` is at work, and the brief has no `## Review`. Run "
        'the block of the crew skill\'s "The checks" and then the blocks of "The review", and '
        "do what they print. Where they say `launch a reviewer`, launch it and add `Reviewer: "
        "<threadId> #<n>` to the Result, `<n>` its number. Where they say `launch no reviewer` "
        "because the Result has a `Reviewer:` line, that reviewer ended its turn and wrote "
        "nothing: send its thread "
        "the one line `/pr-review run alpha again` with `t3_thread_send`, and write `Woke: "
        "jbus, sent /pr-review run alpha again` in the Result, the line as sent. Launch no "
        "second one. "
        + (REPO / "features" / "crew" / "templates" / "rerun.md")
        .read_text()
        .strip()
        .replace("{slug}", "alpha")
    ),
    "renumber": (
        'Rebase onto the default branch with the crew skill\'s "A conflict" block, run with '
        "`stale`: it counts the rebase toward the cap of two after fixed and green, and holds a "
        "third only where its range-diff is not empty. Then renumber the migration the reason "
        "names to the number it gives, and each migration of yours after it to the numbers that "
        "follow, one each and in their order: the files, and every other line that names an old "
        "number. Run the check command, and push with the block's push."
    ),
}


def test_the_reasons_these_tests_give_jmerge_are_the_ones_it_prints():
    saw, fix, head = "a" * 40, "b" * 40, "c" * 40
    result = "\n## Result\nStatus: done\n"
    second = f"Second pass: needed since {saw}, the fix also changed b.py\n"
    first, last = REVIEW.format(saw=saw), REVIEW.format(saw=fix)
    assert ready.short_of(result + first, head) == NO_FIXED
    assert ready.short_of(result + f"Fixed: {saw}\n" + first, head) == NOT_PUSHED
    assert ready.short_of(result + second + f"Fixed: {head}\n" + first, head) == NO_SECOND
    owed = f"Scoped review: needed since {saw}, the fix changed b.py\n"
    assert ready.short_of(result + owed + f"Fixed: {head}\n" + first, head) == NO_FIX_REVIEW
    handled = f"Finding: fixed, a made up one\n{second}Fixed: {head}\n"
    assert ready.short_of(result + handled + first + last, head) == NO_FINDING
    assert ready.short_of(result + "Reviewer: mcp:9\n", head) == NO_REVIEW
    twice = "Review: twice\n" + result + f"Finding F1: fixed, a made up one\nFixed: {fix}\n"
    assert ready.short_of(twice + first, fix) == NO_TWICE
    assert ready.short_of(result + "Reviewer: none, no launch tool in this session\n", head) == (
        NO_REVIEW
    )


NAMED = " The findings with no answer that counts: F1."
for answered in ("unfixed", "unpushed", "unended"):
    SAYS[answered] += NAMED


def said_to(short, kind, reason, sentence):
    return {
        "threadId": "mcp:thread-1",
        "message": (
            "jbus: pull request #7 waits on you, and jmerge keeps saying the same of it "
            f"({reason}). {sentence} "
            f"End your turn only once no check or proof you started runs in your "
            "worktree: wait for one that runs, in this turn."
        ),
        "mode": "queue",
        "clientRequestId": f"{kind}|alpha|{short.head[:12]}",
    }


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("unfixed", NO_FIXED),
        ("unpushed", NOT_PUSHED),
        ("unended", NO_FINDING),
        ("second", NO_SECOND),
        ("twice", NO_TWICE),
        ("renumber", RENUMBER),
    ],
)
def test_the_third_pass_of_one_reason_at_one_head_tells_the_crew_once(kind, reason, short, kitchen):
    short.out(reason)
    short.passes(2)
    assert sends(kitchen) == []
    said = short.passes(1)
    assert sends(kitchen) == [said_to(short, kind, reason, SAYS[kind])]
    line = f"expedite alpha: told the crew what #7 is short of ({kind}, {short.head[:12]})"
    if kind in ("second", "twice"):
        line += ", sent `/pr-review run alpha again`"
    assert line in said
    (event,) = kitchen.events("expedite")
    assert (event["slug"], event["line"], event["loud"]) == ("alpha", line, "quiet")
    assert "say" not in event and event["text"] == sends(kitchen)[0]["message"]
    short.passes(6)
    assert len(sends(kitchen)) == 1
    assert kitchen.webhook.posts == [] and kitchen.lines("stall") == [] and gates(kitchen) == []
    assert f"{kind}|alpha|{short.head[:12]}" in jbus.read_json(kitchen.state / "sent.json", [])


def test_a_fix_whose_review_is_owed_asks_the_crew_for_the_scoped_reviewer_with_its_ranges(
    short, kitchen
):
    owed = f"Scoped review: needed since {short.saw}, the fix changed a.py\n"
    short.out(NO_FIX_REVIEW, result=owed)
    short.passes(2)
    assert sends(kitchen) == []
    short.passes(1)
    sentence = (
        SAYS["fix"]
        .replace("{old}", f"{short.start}..{short.saw}")
        .replace("{new}", f"{short.start}..{short.head}")
        .replace("{head}", short.head)
    )
    assert sends(kitchen) == [said_to(short, "fix", NO_FIX_REVIEW, sentence)]
    short.passes(6)
    assert len(sends(kitchen)) == 1 and kitchen.lines("stall") == [] and gates(kitchen) == []


def test_a_fix_review_owed_is_not_asked_for_while_a_reviewer_is_at_work(short, kitchen):
    owed = f"Scoped review: needed since {short.saw}, the fix changed a.py\n"
    reviewer = kitchen.t3.thread("alpha", title="review: alpha, scoped")
    short.out(NO_FIX_REVIEW, result=owed)
    short.passes(5)
    assert sends(kitchen) == []
    reviewer["status"] = "completed"
    short.passes(1)
    assert [sent["clientRequestId"] for sent in sends(kitchen)] == [f"fix|alpha|{short.head[:12]}"]


@pytest.mark.parametrize("since", ["-", "d" * 40])
def test_a_fix_review_owed_with_no_range_sends_the_crew_to_the_block_and_then_stalls(
    since, short, kitchen
):
    short.out(NO_FIX_REVIEW, result=f"Scoped review: needed since {since}, it could not be\n")
    short.passes(3)
    sentence = (
        'Run the block of the crew skill\'s "A second pass" in your worktree and do what it '
        "prints: the Result says a scoped review of the fix is owed, and jbus could not work "
        "out its two ranges."
    )
    assert sends(kitchen) == [said_to(short, "fix", NO_FIX_REVIEW, sentence)]
    short.passes(9)
    assert kitchen.lines("stall") == []
    short.passes(1)
    (stalled,) = kitchen.lines("stall")
    assert stalled.startswith("stall alpha: #7 is as short as it was 10 passes after")


def test_a_review_that_never_came_is_told_to_the_crew_once_and_logged_as_one_stall(short, kitchen):
    """The reviewer ended its turn and wrote no section. Nothing wakes the reviewer, so jbus
    wakes the crew."""
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']}\n", review=False)
    short.passes(2)
    assert sends(kitchen) == []
    said = short.passes(1)
    assert sends(kitchen) == [said_to(short, "unreviewed", NO_REVIEW, SAYS["unreviewed"])]
    line = f"expedite alpha: told the crew what #7 is short of (unreviewed, {short.head[:12]}), "
    line += "sent `/pr-review run alpha again`"
    assert line in said
    (event,) = kitchen.events("expedite")
    assert (event["line"], event["loud"]) == (line, "quiet")
    short.passes(9)
    assert len(sends(kitchen)) == 1
    posted = [event for post in kitchen.webhook.posts for event in post]
    assert [event["line"] for event in posted if event["loud"] == "user"] == []
    assert kitchen.lines("stall") == [] and gates(kitchen) == []
    short.passes(1)
    stalled = (
        f"stall alpha: #7 is as short as it was 10 passes after its crew was told, at "
        f"{short.head[:12]}, {NO_REVIEW}; its crew's thread is mcp:thread-1"
    )
    assert kitchen.lines("stall") == [stalled]
    (event,) = kitchen.events("stall")
    assert (event["loud"], event["posted"]) == ("quiet", None)
    assert not [one for post in kitchen.webhook.posts for one in post if one["event"] == "stall"]
    short.passes(12)
    assert kitchen.lines("stall") == [stalled] and len(sends(kitchen)) == 1
    assert gates(kitchen) == []


def test_an_expedite_sent_while_the_crew_s_instance_is_capped_is_sent_again_after_the_reset(
    short, kitchen
):
    """The reviewer wrote nothing, and jbus asks the crew for `/pr-review run alpha again` while
    the crew's instance is capped, 22 minutes before the cap resets. The turn the message starts
    ends at once on the limit, so the crew stays as it was. The first pass after the reset sends
    the message again, once, and a later pass sends nothing more."""
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']}\n", review=False)
    resets = later(2) + timedelta(minutes=22)
    ledger.file_of("claudeAgent").write_text(f"five_hour 100 {int(resets.timestamp())}\n")
    short.passes(3)
    (first,) = sends(kitchen)
    assert "`/pr-review run alpha again`" in first["message"]
    short.passes(21)
    assert later(short.minute - 1) < resets and sends(kitchen) == [first]
    said = short.passes(1)
    assert later(short.minute - 1) == resets
    again = [one for one in sends(kitchen) if one != first]
    assert [(one["threadId"], one["message"]) for one in again] == [
        ("mcp:thread-1", first["message"])
    ]
    line = f"expedite alpha: told the crew what #7 is short of (unreviewed, {short.head[:12]}), "
    assert line + "sent `/pr-review run alpha again`" in said
    short.passes(12)
    assert len(sends(kitchen)) == 2


def test_a_hold_sent_into_a_cap_longer_than_its_idle_passes_stays_in_hand_and_is_sent_again(
    short, kitchen
):
    """The crew is asked for a scoped pass over its rebase while its instance is capped for 40
    minutes. The passes of the cap are not the crew's idleness, so the hold is not the user's by
    the reset, and the first pass after it sends the message again."""
    short.out(short.unruled(), "hold", short.rebased())
    resets = later(2) + timedelta(minutes=40)
    ledger.file_of("claudeAgent").write_text(f"five_hour 100 {int(resets.timestamp())}\n")
    short.passes(3)
    (first,) = sends(kitchen)
    short.passes(39)
    assert later(short.minute - 1) < resets and sends(kitchen) == [first]
    assert listed(kitchen) == []
    short.passes(1)
    assert [one["message"] for one in sends(kitchen)] == [first["message"]] * 2


def test_a_send_into_a_cap_whose_pass_kept_no_count_is_still_sent_again_after_the_reset(
    short, kitchen
):
    """A pass sent into a cap and stopped before it wrote `expedite.json`. The next pass finds the
    message's mark, and the first pass after the reset still sends it again."""
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']}\n", review=False)
    resets = later(2) + timedelta(minutes=22)
    ledger.file_of("claudeAgent").write_text(f"five_hour 100 {int(resets.timestamp())}\n")
    short.passes(2)
    counted = jbus.read_json(kitchen.state / "expedite.json", {})
    short.passes(1)
    (first,) = sends(kitchen)
    jbus.write_json(kitchen.state / "expedite.json", counted)
    short.passes(21)
    assert later(short.minute - 1) < resets and sends(kitchen) == [first]
    short.passes(1)
    assert [one["message"] for one in sends(kitchen)] == [first["message"]] * 2


def test_a_cap_longer_than_a_review_logs_no_stall_and_a_crew_short_after_the_resend_stalls(
    short, kitchen
):
    """The crew is asked for `/pr-review run alpha again` while its instance is capped for an hour,
    longer than `REVIEWING` passes. A crew the cap locks out is not one that did not act, so no
    stall is logged during the cap. After the reset the message is sent again, and a crew that
    stays short `PASSES` idle passes after that gets its stall."""
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']}\n", review=False)
    resets = later(2) + timedelta(minutes=60)
    ledger.file_of("claudeAgent").write_text(f"five_hour 100 {int(resets.timestamp())}\n")
    short.passes(3)
    (first,) = sends(kitchen)
    short.passes(59)
    assert later(short.minute - 1) < resets and sends(kitchen) == [first]
    assert kitchen.lines("stall") == []
    short.passes(1)
    assert [one["message"] for one in sends(kitchen)] == [first["message"]] * 2
    short.passes(9)
    assert kitchen.lines("stall") == []
    short.passes(1)
    (stalled,) = kitchen.lines("stall")
    assert stalled.startswith("stall alpha: #7 is as short as it was 10 passes after")


def test_a_hold_whose_crew_is_at_work_at_the_reset_stays_in_hand_and_is_sent_once_it_is_idle(
    short, kitchen
):
    """The crew is asked for a scoped pass over its rebase while its instance is capped for 40
    minutes, and it is at work on the pass at the reset. The passes of the cap are not passes the
    message waited to be sent, so the hold is not the user's, and the first pass with the crew
    idle sends the message again."""
    short.out(short.unruled(), "hold", short.rebased())
    resets = later(2) + timedelta(minutes=40)
    ledger.file_of("claudeAgent").write_text(f"five_hour 100 {int(resets.timestamp())}\n")
    short.passes(3)
    (first,) = sends(kitchen)
    short.passes(39)
    short.thread["status"] = "running"
    short.passes(1)
    assert later(short.minute - 1) == resets and sends(kitchen) == [first]
    assert listed(kitchen) == []
    short.thread["status"] = "completed"
    short.passes(1)
    assert [one["message"] for one in sends(kitchen)] == [first["message"]] * 2
    assert listed(kitchen) == []


def reviewer_says(tmp_path, asked, brief):
    """Return what the reviewer's Start 1 prints when `asked` starts the reviewer on a brief."""
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "alpha.md").write_text(brief)
    script = block("### Start", "case $asked").replace("<slug>", "alpha").replace(ASKED, asked)
    env = {**os.environ, "H": str(tmp_path), "T": str(REPO / "features" / "crew" / "templates")}
    ran = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, check=True)
    return ran.stdout.splitlines()


def test_the_line_a_crew_sends_a_reviewer_that_wrote_nothing_is_one_the_reviewer_accepts(
    short, kitchen, tmp_path
):
    """Pull request 69: jbus's nudge told the crew to send the plain line again, and the reviewer
    refused it, twice. The line that the nudge names must work on a brief with a `## Review` and
    on one without. The event, the `Woke:` line that jbus tells the crew to write, and the line
    the crew sends must have the same text."""
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']}\n", review=False)
    said = short.passes(3)
    (sent,) = sends(kitchen)
    (to_send,) = re.findall(r"send its thread the one line `([^`]+)`", sent["message"])
    (woke,) = re.findall(r"write `Woke: jbus, sent ([^`]+)` in the Result", sent["message"])
    assert to_send == woke == "/pr-review run alpha again"
    assert f"sent `{to_send}`" in " ".join(said)
    quiet = "# alpha: a task\nReview: review\nReviewer: mcp:thread-9\n"
    for brief in (quiet, quiet + REVIEW.format(saw="a" * 40)):
        assert reviewer_says(tmp_path, to_send, brief)[0].startswith("go: ")


def test_a_reviewer_that_waits_for_room_inside_its_turn_is_whom_the_pull_request_waits_for(
    short, kitchen
):
    reviewer = kitchen.t3.thread("alpha", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']}\n", review=False)
    short.passes(6)
    assert sends(kitchen) == [] and kitchen.lines("stall") == []
    reviewer["status"] = "completed"
    short.passes(1)
    assert len(sends(kitchen)) == 1


NO_REVIEWER = {
    "no launch tool": "Reviewer: none, no launch tool in this session\n",
    "no check ran": "Unrun: at {head}, no check ran\n",
    "a check failed twice": "Stuck: at {head}, check\n",
    "the base moved": "Stale base: at {head}, check\n",
}


@pytest.mark.parametrize("why", NO_REVIEWER)
def test_a_pull_request_the_crew_skill_leaves_with_no_reviewer_is_not_the_crew_s_to_fix(
    why, short, kitchen
):
    """Each of these already has its own gate or message, so the desk gets nothing more."""
    short.out(NO_REVIEW, result=NO_REVIEWER[why].format(head=short.head), review=False)
    short.passes(16)
    assert sends(kitchen) == [] and kitchen.lines("stall") == [] and gates(kitchen) == []
    assert kitchen.events("expedite") == []


@pytest.mark.parametrize("why", [why for why in NO_REVIEWER if why != "no launch tool"])
def test_a_reviewer_launched_beside_a_check_that_then_ended_badly_is_still_owed(
    why, short, kitchen
):
    """The crew launches its reviewer on `wait`, so the brief can have both the line and a
    reviewer."""
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    result = f"Reviewer: {reviewer['threadId']}\n" + NO_REVIEWER[why].format(head=short.head)
    short.out(NO_REVIEW, result=result, review=False)
    short.passes(3)
    assert [sent["clientRequestId"] for sent in sends(kitchen)] == [
        f"unreviewed|alpha|{short.head[:12]}"
    ]


def test_a_line_about_a_head_that_is_gone_does_not_hide_a_review_that_never_came(short, kitchen):
    short.out(NO_REVIEW, result=f"Unrun: at {short.saw}, no check ran\n", review=False)
    short.passes(3)
    assert [sent["clientRequestId"] for sent in sends(kitchen)] == [
        f"unreviewed|alpha|{short.head[:12]}"
    ]


def test_drops_a_review_did_not_rule_on_ask_the_crew_for_the_scoped_pass_not_the_user(
    short, kitchen
):
    reason = short.unruled("a.py, b.py")
    short.heard(short.rebased())
    short.out(reason, "hold", short.rebased())
    short.passes(2)
    assert sends(kitchen) == []
    short.passes(1)
    sentence = (
        'Launch ONE scoped reviewer over the rebase, the way the crew skill\'s "The review" '
        f"launches a reviewer, with the message `/pr-review run alpha scoped {short.start}.."
        f"{short.saw} {short.start}..{short.head}`, and add `Scoped reviewer: <threadId>, of "
        f"{short.head}` to the Result. Push nothing and do not rebase until its `## Review` is "
        "written: a `Dropped on rebase:` line is read for this head and no other."
    )
    assert sends(kitchen) == [said_to(short, "unruled", reason, sentence)]
    short.passes(6)
    assert len(sends(kitchen)) == 1
    assert kitchen.webhook.posts == [] and gates(kitchen) == []
    assert kitchen.lines("waiting") == [] and kitchen.lines("waiting-on-user") == []
    assert jbus.read_json(kitchen.state / "waiting-on-user.json", []) == []


def test_ten_passes_after_the_message_with_nothing_changed_is_one_stall_in_the_log(short, kitchen):
    short.out(NO_FIXED)
    short.passes(12)
    assert len(sends(kitchen)) == 1 and kitchen.lines("stall") == []
    short.passes(1)
    stalled = (
        f"stall alpha: #7 is as short as it was 10 passes after its crew was told, at "
        f"{short.head[:12]}, {NO_FIXED}; its crew's thread is mcp:thread-1"
    )
    assert kitchen.lines("stall") == [stalled]
    (event,) = kitchen.events("stall")
    assert (event["slug"], event["loud"], event["posted"]) == ("alpha", "quiet", None)
    assert not [one for post in kitchen.webhook.posts for one in post if one["event"] == "stall"]
    short.passes(12)
    assert kitchen.lines("stall") == [stalled] and len(sends(kitchen)) == 1


def test_a_hold_the_crew_did_not_lift_is_one_stall_and_one_decision_from_the_next_pass(
    short, kitchen
):
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(12)
    assert kitchen.lines("stall") == []
    kitchen.webhook.posts.clear()
    short.passes(1)
    (stalled,) = kitchen.lines("stall")
    assert stalled.endswith(f"{short.unruled()}; its crew's thread is mcp:thread-1")
    assert kitchen.webhook.posts == []
    assert listed(kitchen) == []
    kitchen.webhook.posts.clear()
    short.passes(1)
    assert listed(kitchen) == ["#7"]
    assert kitchen.lines("waiting")[-1] == "waiting demo: 1 wait on user, 1 new (hold 7), 0 gone"
    assert kitchen.lines("gate") == [] and gates(kitchen) == []
    short.passes(12)
    posted = [[event["event"] for event in post] for post in kitchen.webhook.posts]
    assert posted == [["decision"]] and kitchen.waiting() == []
    (decided,) = kitchen.events("decision")
    assert decided["line"].endswith(
        'a pull request jmerge holds for your word. Reply: "demo #7: merge it"'
    )
    assert listed(kitchen) == ["#7"]
    assert len(sends(kitchen)) == 1


@pytest.mark.parametrize("changed", ["the head", "the reason"])
def test_a_stalled_hold_is_off_the_user_s_list_once_its_head_or_its_reason_changes(
    changed, short, kitchen
):
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(14)
    assert listed(kitchen) == ["#7"]
    if changed == "the head":
        short.head = short.commit("a fix")
        short.out(short.unruled(), "hold", short.rebased())
    else:
        short.out(short.unruled("b.py"), "hold", short.rebased())
    short.passes(1)
    assert listed(kitchen) == []


def test_a_hold_that_stalls_over_a_review_at_work_is_the_user_s_only_once_that_work_ended(
    short, kitchen
):
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(3)
    reviewer = kitchen.t3.thread("alpha", title="review: alpha, scoped")
    short.passes(32)
    (stalled,) = kitchen.lines("stall")
    assert "with its crew or a reviewer at work" in stalled
    assert listed(kitchen) == [] and gates(kitchen) == []
    reviewer["status"] = "failed"
    short.passes(10)
    assert listed(kitchen) == [] and gates(kitchen) == []
    short.passes(1)
    assert listed(kitchen) == ["#7"] and gates(kitchen) == []
    assert kitchen.lines("stall") == [stalled]


def test_a_stalled_hold_is_the_user_s_on_a_next_pass_that_cannot_ask_t3_code(short, kitchen):
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(13)
    assert len(kitchen.lines("stall")) == 1 and gates(kitchen) == []
    kitchen.t3.down.add(PROJECT)
    short.passes(1)
    assert listed(kitchen) == ["#7"] and kitchen.lines("gate") == []
    assert kitchen.lines("waiting")[-1] == "waiting demo: 1 wait on user, 1 new (hold 7), 0 gone"


def test_a_hold_on_the_user_s_list_no_longer_asks_t3_code_who_is_reviewing(short, kitchen):
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(14)
    asked = len(kitchen.t3.calls)
    assert listed(kitchen) == ["#7"]
    short.passes(1)
    titles = [given.get("titleContains") for _, given in kitchen.t3.calls[asked:]]
    assert "review: alpha" not in titles


def test_a_crew_that_acted_is_never_a_stall_and_a_new_head_is_told_again(short, kitchen):
    short.out(NO_FIXED)
    short.passes(8)
    again = short.commit("a fix")
    short.out(NOT_PUSHED, head=again)
    short.passes(8)
    first, second = sends(kitchen)
    assert first["clientRequestId"] == f"unfixed|alpha|{short.head[:12]}"
    assert second["clientRequestId"] == f"unpushed|alpha|{again[:12]}"
    short.out("its check has not passed", head=again)
    short.passes(12)
    assert kitchen.lines("stall") == [] and len(sends(kitchen)) == 2


def test_a_reason_that_came_back_at_a_head_already_told_is_not_told_twice_and_still_stalls(
    short, kitchen
):
    short.out(NO_FIXED)
    short.passes(3)
    short.out("its check has not passed")
    short.passes(1)
    short.out(NO_FIXED)
    short.passes(12)
    assert len(sends(kitchen)) == 1 and kitchen.lines("stall") == []
    short.passes(1)
    assert len(kitchen.lines("stall")) == 1


@pytest.mark.parametrize("status", ENDED)
def test_a_running_thread_is_left_alone_and_one_that_ended_its_turn_is_told(status, short, kitchen):
    short.thread["status"] = "running"
    short.out(NO_FIXED)
    short.passes(6)
    assert sends(kitchen) == [] and kitchen.lines("stall") == []
    short.thread["status"] = status
    short.passes(1)
    assert sends(kitchen) == [said_to(short, "unfixed", NO_FIXED, SAYS["unfixed"])]


@pytest.mark.parametrize(
    ("title", "reason", "word"),
    [
        ("review: alpha, second pass", NO_SECOND, "wait"),
        ("review: alpha, scoped", None, "hold"),
    ],
)
def test_a_reviewer_that_is_out_is_whom_the_pull_request_waits_for(
    title, reason, word, short, kitchen
):
    reviewer = kitchen.t3.thread("alpha", title=title)
    kitchen.t3.thread("alphabet", title="review: alphabet")
    short.out(reason or short.unruled(), word, short.rebased())
    short.passes(5)
    assert sends(kitchen) == [] and gates(kitchen) == []
    reviewer["status"] = "completed"
    short.passes(1)
    assert len(sends(kitchen)) == 1


def test_findings_not_handled_do_not_wait_for_a_reviewer(short, kitchen):
    kitchen.t3.thread("alpha", title="review: alpha")
    short.out(NO_FIXED)
    short.passes(3)
    assert len(sends(kitchen)) == 1


def test_a_hold_for_a_guarded_path_is_the_user_s_at_once(short, kitchen):
    held = f"hold 7 {URL}: needs user, touches src/jmerge/cli.py"
    kitchen.set("jmerge.txt", held + "\n")
    short.passes(1)
    assert gates(kitchen) == [] and kitchen.lines("gate") == []
    assert kitchen.lines("jmerge") == [held]
    assert [one["kind"] for one in jbus.read_json(kitchen.state / "waiting-on-user.json", [])] == [
        "hold"
    ]
    short.passes(4)
    assert sends(kitchen) == [] and kitchen.events("expedite") == []


def test_a_gate_a_crew_parks_is_logged_at_once_and_not_posted(short, kitchen):
    short.out(NO_FIXED)
    code, _ = kitchen.main(
        "--project",
        "demo",
        "gate",
        "alpha",
        stdin=GATE.format(n="<n>", asked="a made up question", status="open", slug="alpha"),
    )
    assert code == 0
    (event,) = kitchen.events("gate")
    assert event["loud"] == "quiet"
    assert kitchen.waiting() == []


def test_unruled_drops_jbus_cannot_ask_a_crew_about_are_the_user_s_as_before(short, kitchen):
    short.out(short.unruled(), "hold")
    short.passes(2)
    assert listed(kitchen) == []
    said = short.passes(1)
    assert listed(kitchen) == ["#7"] and sends(kitchen) == []
    assert (
        "wait alpha: its Result has no Rebase line for its head, so the hold is the user's" in said
    )
    short.passes(3)
    assert listed(kitchen) == ["#7"] and gates(kitchen) == [] and kitchen.lines("gate") == []


def test_unruled_drops_with_no_rebase_line_are_asked_from_the_head_the_crew_kept(short, kitchen):
    """The crew skill keeps the head before a rebase under refs/jstack/pre-rebase/<slug>/ and
    writes no `Rebase:` line. So the old range of the scoped review starts at that ref."""
    kitchen.git("update-ref", f"refs/jstack/pre-rebase/alpha/{short.saw[:12]}", short.saw)
    short.out(short.unruled(), "hold")
    said = short.passes(3)
    (given,) = sends(kitchen)
    assert f"..{short.saw} " in given["message"] and given["message"].count(short.head) >= 1
    assert not [line for line in said if "no Rebase line" in line]


def test_unruled_drops_of_a_pull_request_jbus_launched_no_crew_for_are_the_user_s_at_once(
    short, kitchen
):
    mine = {**kitchen.opened("alpha", 7), "headRefOid": short.head}
    kitchen.set("open.json", [mine, {**kitchen.opened("beta", 8), "headRefOid": short.head}])
    held = f"hold 8 {URL}: {short.unruled()}"
    kitchen.set("jmerge.txt", held + "\n")
    short.passes(1)
    assert kitchen.lines("gate") == [] and sends(kitchen) == []
    listed = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    assert [one["key"] for one in listed if one["kind"] == "hold"] == ["#8"]


def test_no_line_jbus_writes_for_a_short_pull_request_has_an_address_in_it(short, kitchen):
    short.out(short.unruled(), "hold", short.rebased())
    said = short.passes(14)
    (given,) = sends(kitchen)
    written = [given["message"], *kitchen.lines("expedite"), *kitchen.lines("stall")]
    written += [line for line in said if line.startswith(("expedite", "stall"))]
    assert len(written) == 4
    assert [line for line in written if "://" in line or "example.test" in line] == []


def test_the_hold_these_tests_give_jmerge_is_the_one_it_prints_and_the_one_merge_reads(short):
    head = short.head
    lost = (ready.Drop("a.py", 1, 0),)
    result = (
        f"Rebase: patch changed in a.py, before {short.saw}, head {head}\n"
        f"Dropped on rebase: a.py, 1 of main's, 0 of its own, at {head[:12]}: made up\n"
        f"## Review\nVerdict: clean\nHead: {head}\nFindings:\n"
    )
    word, reason = ready.drops(lost, result, head, user=jsettings.DEFAULTS)
    assert (word, reason) == ("hold", short.unruled())
    assert merge.UNRULED.fullmatch(reason)
    assert not merge.UNRULED.fullmatch("needs user, touches src/jmerge/cli.py")


def listed(kitchen):
    return [one["key"] for one in jbus.read_json(kitchen.state / "waiting-on-user.json", [])]


def test_with_t3_code_silent_nobody_can_be_asked_so_the_hold_is_the_user_s_at_once(short, kitchen):
    short.heard(short.rebased())
    short.out(short.unruled(), "hold", short.rebased())
    kitchen.t3.down.add(PROJECT)
    short.passes(2)
    assert gates(kitchen) == ["condition demo: T3 Code could not be asked"]
    assert sends(kitchen) == [] and listed(kitchen) == ["#7"]


def test_a_hold_in_hand_before_its_crew_is_told_stays_in_hand_through_a_silent_pass(short, kitchen):
    """The test runs three passes: one that can ask, one that cannot, and one that can. The list
    gains nothing and loses nothing."""
    short.heard(short.rebased())
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(1)
    assert sends(kitchen) == [] and listed(kitchen) == []
    kitchen.t3.down.add(PROJECT)
    short.passes(1)
    assert listed(kitchen) == []
    kitchen.t3.down.clear()
    short.passes(1)
    assert listed(kitchen) == [] and kitchen.lines("waiting") == []
    assert kitchen.webhook.posts == []


def test_a_silent_pass_after_the_crew_was_told_puts_no_hold_on_the_user_s_list(short, kitchen):
    short.heard(short.rebased())
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(3)
    assert len(sends(kitchen)) == 1
    kitchen.t3.down.add(PROJECT)
    short.passes(2)
    assert listed(kitchen) == []
    kitchen.t3.down.clear()
    short.passes(3)
    assert listed(kitchen) == [] and kitchen.lines("gate") == []
    assert len(sends(kitchen)) == 1


def test_a_stall_after_work_that_ended_does_not_say_somebody_is_at_work(short, kitchen):
    short.out(NO_SECOND)
    short.passes(3)
    reviewer = kitchen.t3.thread("alpha", title="review: alpha, second pass")
    short.passes(25)
    reviewer["status"] = "failed"
    short.passes(5)
    (stalled,) = kitchen.lines("stall")
    assert stalled.startswith("stall alpha: #7 is as short as it was 30 passes after its crew was")
    assert "at work" not in stalled


@pytest.mark.parametrize("stuck", ["the crew's thread waits", "the send errors"])
def test_a_hold_whose_crew_is_not_told_by_its_thirteenth_pass_is_the_user_s(stuck, short, kitchen):
    short.heard(short.rebased())
    if stuck == "the send errors":
        kitchen.t3.lose_send = True
    else:
        short.thread["status"] = "waiting"
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(12)
    assert gates(kitchen) == [] and listed(kitchen) == []
    said = short.passes(1)
    assert "wait alpha: its crew was not told in 13 passes, so the hold is the user's" in said
    assert listed(kitchen) == ["#7"]
    short.passes(3)
    assert listed(kitchen) == ["#7"] and gates(kitchen) == []
    assert kitchen.lines("stall") == [] and kitchen.events("expedite") == []


def test_a_message_t3_code_refuses_is_a_gate_in_this_ask_s_own_words(short, kitchen):
    kitchen.t3.refuse_send = True
    short.out(NO_FIXED)
    short.passes(4)
    refused = "condition alpha: T3 Code refused the message about what a pull request is short of"
    assert gates(kitchen) == [refused] and kitchen.events("expedite") == []


def test_a_hold_the_user_had_is_off_their_list_while_its_crew_is_asked(short, kitchen):
    short.heard(short.rebased())
    kitchen.set("jmerge.txt", f"hold 7 {URL}: needs user, touches src/jmerge/cli.py\n")
    short.passes(1)
    assert listed(kitchen) == ["#7"]
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(4)
    assert len(sends(kitchen)) == 1 and listed(kitchen) == []


@pytest.mark.parametrize("who", ["a reviewer", "the crew"])
def test_work_started_after_the_message_is_no_stall_until_it_ends_or_lasts_thirty_passes(
    who, short, kitchen
):
    short.out(short.unruled(), "hold", short.rebased())
    short.passes(3)
    assert len(sends(kitchen)) == 1
    if who == "a reviewer":
        worker = kitchen.t3.thread("alpha", title="review: alpha, scoped")
    else:
        worker = short.thread
        worker["status"] = "running"
    short.passes(12)
    assert kitchen.lines("stall") == []
    worker["status"] = "completed"
    short.passes(9)
    assert kitchen.lines("stall") == []
    short.passes(1)
    (stalled,) = kitchen.lines("stall")
    told = "stall alpha: #7 is as short as it was 22 passes after its crew was told, at "
    assert stalled.startswith(told + short.head[:12])


def test_work_that_lasts_thirty_passes_after_the_message_is_the_stall_and_says_so(short, kitchen):
    short.out(NO_SECOND)
    short.passes(3)
    kitchen.t3.thread("alpha", title="review: alpha, second pass")
    short.passes(29)
    assert kitchen.lines("stall") == []
    short.passes(1)
    assert kitchen.lines("stall") == [
        "stall alpha: #7 is as short as it was 30 passes after its crew was told, with its crew "
        f"or a reviewer at work, at {short.head[:12]}, {NO_SECOND}; its crew's thread is "
        "mcp:thread-1"
    ]


def test_a_jmerge_that_stopped_before_it_reached_a_pull_request_keeps_its_count(short, kitchen):
    short.out(NO_FIXED)
    short.passes(2)
    kitchen.set("jmerge.txt", f"wait 9 {URL}: its check has not passed\n")
    (kitchen.stub / "jmerge-dies-late").write_text("a made up end")
    short.passes(1)
    (kitchen.stub / "jmerge-dies-late").unlink()
    short.out(NO_FIXED)
    short.passes(1)
    assert len(sends(kitchen)) == 1


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("unanswered", ready.UNANSWERED.format(ids="F1, F3")),
        ("uncited", ready.UNCITED.format(ids="F2")),
        ("repeated", ready.REPEATED.format(ids="F2", first="F1")),
        ("risky", ready.RISK_UNASKED.format(ids="F1", risks="auth")),
    ],
)
def test_each_wait_for_an_answer_by_id_is_a_row_its_crew_is_told(kind, reason):
    from jbus import expedite

    row = expedite.short_of(merge.Line("wait", 7, URL, reason))
    assert row is not None and row.kind == kind
    assert kind in expedite.ANSWERED
