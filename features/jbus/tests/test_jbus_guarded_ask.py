"""When the crew of a guarded pull request pushes a fix after its last review, the head has no
proof, so `jmerge` waits on the pull request. jbus asks its crew, once per head, for the one
scoped review that proves it. Like `test_jbus_rereview.py`, the tests run the real pass against
the fakes, with the line `jmerge` prints for such a pull request, over commits that are really
there."""

import subprocess
from datetime import timedelta

import pytest

import jbus
from jmerge import proof
from test_jbus_kitchen import NOW
from test_jbus_queue import add, gates
from test_jbus_unlock import sends

URL = "https://example.test/pull/7"
PATH = "src/jbus/alert.py"
DONE = "\n## Result\nStatus: done\nBranch: alpha   Pull request: {url}\nLeft: none\n"


def review(head, verdict="findings"):
    """A review its reviewer sent the crew itself, so `jbus.reviewed` sends no notice of it."""
    return (
        f"\n## Review\nVerdict: {verdict}\nHead: {head}   Unchanged by the review: yes\n"
        "Sent to: mcp:thread-1\n"
    )


def waits(text, head):
    """Return what `jmerge` prints after the url for a guarded head with no proof at it."""
    return f"guarded (touches {PATH}), {proof.short(text, head)}"


class Fixed:
    """Alpha is a row that a pass launched. A review saw the first commit of its branch, and the
    second commit is the fix the crew pushed for the findings. Alpha's branch is open as pull
    request #7 at the fix. Alpha's thread's turn has ended, since jbus asks nothing of a thread
    at work."""

    def __init__(self, kitchen):
        self.kitchen = kitchen
        add(kitchen, "alpha")
        assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
        (self.thread,) = kitchen.t3.threads
        self.thread["status"] = "completed"
        self.start = self.commit()
        self.saw = self.commit("the task")
        self.head = self.commit("the fix")
        self.launched = (kitchen.home / "tasks/alpha.md").read_text()
        self.out()

    def commit(self, message=""):
        if message:
            self.kitchen.git("commit", "-q", "--allow-empty", "-m", message)
        asked = ["git", "rev-parse", "HEAD"]
        ran = subprocess.run(asked, cwd=self.kitchen.checkout, capture_output=True, text=True)
        return ran.stdout.strip()

    def out(self, result="", reviews=None, head=None, status="done", named=None):
        """Write what the crew and its reviewers wrote, and set what `jmerge` says of the head,
        or of the commit it compared the head with."""
        head = head or self.head
        done = DONE.format(url=URL).replace("Status: done", f"Status: {status}")
        text = self.launched + done + result + (review(self.saw) if reviews is None else reviews)
        (self.kitchen.home / "tasks/alpha.md").write_text(text)
        self.kitchen.set("open.json", [{**self.kitchen.opened("alpha", 7), "headRefOid": head}])
        self.kitchen.set("jmerge.txt", f"wait 7 {URL}: {waits(text, named or head)}\n")


@pytest.fixture
def fixed(kitchen):
    return Fixed(kitchen)


def test_a_fix_no_review_proved_asks_its_crew_for_one_scoped_review_once(fixed, kitchen):
    said = kitchen.poll()
    short = fixed.head[:12]
    (given,) = sends(kitchen)
    assert given == {
        "threadId": "mcp:thread-1",
        "message": (
            "jbus: the fix you pushed to pull request #7 has no review at its head, and jmerge "
            f"waits on it (guarded (touches {PATH}), no proven safety fact at {short} "
            "(blast-radius, review step 5)). If the Result already has a `Scoped reviewer:` line "
            "that names this head, launch nothing more. Otherwise launch ONE scoped reviewer, "
            'not a full review, in your own worktree: the same way the crew skill\'s "The review" '
            "launches a reviewer, with `workspaceStrategy` `existing_worktree` on that worktree "
            f"and the message `/pr-review run alpha scoped {fixed.start}..{fixed.saw} "
            f"{fixed.start}..{fixed.head}`. Add `Scoped reviewer: <threadId>, of {fixed.head}` to "
            "the Result, in place of a `Scoped reviewer:` line that names another head no "
            "`## Review` has. Do not rebase again until its `## Review` is written. Handle its "
            "findings as a review's: a `Finding:` line for each."
        ),
        "mode": "queue",
        "clientRequestId": f"proof|alpha|{short}",
    }
    line = f"proof alpha: asked the crew for a scoped review (#7, {short})"
    assert line in said and kitchen.lines("proof") == [line]
    assert f"proof|alpha|{short}" in jbus.read_json(kitchen.state / "sent.json", [])
    for minutes in (3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert len(sends(kitchen)) == 1 and gates(kitchen) == []


def test_a_fix_to_the_scoped_pass_s_findings_is_a_new_head_and_is_asked_once_more(fixed, kitchen):
    kitchen.poll()
    again = fixed.commit("the second fix")
    fixed.out(reviews=review(fixed.saw) + review(fixed.head), head=again)
    for minutes in (3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    first, second = sends(kitchen)
    assert second["clientRequestId"] == f"proof|alpha|{again[:12]}"
    asked = f"`/pr-review run alpha scoped {fixed.start}..{fixed.head} {fixed.start}..{again}`"
    assert asked in second["message"]


def test_a_crew_that_launched_the_scoped_review_itself_is_asked_nothing(fixed, kitchen):
    needed = f"Scoped review: needed since {fixed.saw}, guarded\n"
    fixed.out(f"Scoped reviewer: mcp:1\n{needed}Scoped reviewer: mcp:3333-cccc, of {fixed.head}\n")
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("proof") == []
    fixed.out(needed + "Scoped reviewer: mcp:1\n")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(sends(kitchen)) == 1


def rebased_after_its_review(fixed):
    rebased = fixed.commit("the rebase")
    result = (
        f"Fixed: {rebased}\nRebase: patch changed in a.py, before {fixed.head}, head {rebased}\n"
    )
    reviews = review(fixed.saw) + review(fixed.head)
    fixed.out(result, reviews=reviews, head=rebased, named=fixed.head)


def rebased_with_no_fix(fixed):
    moved = f"Rebase: patch changed in a.py, before {fixed.saw}, head {fixed.head}\n"
    fixed.out("Fixed: none needed, a clean review\n" + moved, named=fixed.saw)


@pytest.mark.parametrize(
    "wrote",
    [
        lambda fixed: fixed.out(status="paused"),
        lambda fixed: fixed.out(reviews=review(fixed.head)),
        lambda fixed: fixed.out(reviews=review(fixed.saw, "not run")),
        lambda fixed: fixed.out(reviews=review("d" * 40)),
        rebased_after_its_review,
        rebased_with_no_fix,
    ],
    ids=[
        "the task is not done",
        "the review is of the head",
        "no review ran",
        "the review saw a commit that is not here",
        "a rebase of a fix a review saw",
        "a rebase of the reviewed head, with no fix",
    ],
)
def test_a_wait_for_a_proof_that_no_scoped_review_would_give_asks_nobody(wrote, fixed, kitchen):
    wrote(fixed)
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("proof") == [] and gates(kitchen) == []


def test_a_crew_that_could_launch_no_reviewer_for_the_head_is_not_asked_again(fixed, kitchen):
    fixed.out(f"Scoped reviewer: none, no launch tool in this session, of {fixed.head}\n")
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("proof") == []


def test_a_rebase_of_a_fix_no_review_proved_is_asked_for_at_the_rebased_head(fixed, kitchen):
    rebased = fixed.commit("the rebase")
    result = (
        f"Fixed: {rebased}\nRebase: patch changed in a.py, before {fixed.head}, head {rebased}\n"
    )
    fixed.out(result, head=rebased, named=fixed.head)
    kitchen.poll()
    (given,) = sends(kitchen)
    assert given["clientRequestId"] == f"proof|alpha|{rebased[:12]}"
    asked = f"`/pr-review run alpha scoped {fixed.start}..{fixed.saw} {fixed.start}..{rebased}`"
    assert asked in given["message"]


def test_a_head_that_moved_from_under_a_launched_reviewer_is_asked_for(fixed, kitchen):
    needed = f"Scoped review: needed since {fixed.saw}, guarded\n"
    launched = needed + f"Scoped reviewer: mcp:3333-cccc, of {fixed.head}\n"
    again = fixed.commit("pushed under the reviewer")
    fixed.out(launched, head=again)
    kitchen.poll()
    (given,) = sends(kitchen)
    assert given["clientRequestId"] == f"proof|alpha|{again[:12]}"


def test_a_wait_that_names_a_head_the_crew_has_pushed_past_asks_nobody(fixed, kitchen):
    again = fixed.commit("pushed since")
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "headRefOid": again}])
    kitchen.poll()
    assert sends(kitchen) == []


def test_any_other_guarded_wait_asks_for_no_proof(fixed, kitchen):
    kitchen.set(
        "jmerge.txt", f"wait 7 {URL}: guarded (touches {PATH}), its check has no start time\n"
    )
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("proof") == []
