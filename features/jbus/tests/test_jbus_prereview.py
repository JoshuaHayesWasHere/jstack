"""The review comes before the pull request. A crew whose desk proof passed pushes its branch,
writes its Result with `Pull request: after the review`, and ends its turn. jbus launches its
reviewers on the next pass, once the brief's `Checked:` and `Proved:` lines bind the head origin
has, with no pull request open and so no CI run, and tells the crew once they have all written.

Like `test_jbus_row_ends.py`, the tests run the real pass against the kitchen's fakes, with a real
origin, over a row jbus launched."""

from datetime import timedelta

import pytest

import jbus
from jbus import clock, prereview
from jgauge import slot, waiters
from jroles import ledger
from repo_template import IDENTITY
from test_jbus_kitchen import NOW
from test_jbus_queue import add, rows
from test_jbus_stack_move import signed

DESK = "make check-fast BASE=" + "e" * 40 + " PART=touched"


def sends(kitchen):
    return [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]


def reviewers(kitchen):
    return [one for one in kitchen.t3.launches if one["title"].startswith("review: ")]


def pushed_branch(kitchen, slug="alpha", push=True):
    """The crew's worktree and branch, with one commit of a doc, pushed to origin unless told
    not to. Returns the worktree and its head."""
    tree = kitchen.root / "worktrees" / slug
    kitchen.git("worktree", "add", "-q", "-b", slug, str(tree), "main")
    (tree / "docs").mkdir(exist_ok=True)
    (tree / "docs" / "notes.md").write_text("the task\n")
    kitchen.git("add", "docs/notes.md", cwd=tree)
    kitchen.git("commit", "-q", "-m", "docs: the task", cwd=tree)
    if push:
        kitchen.git("push", "-q", "origin", f"{slug}:refs/heads/{slug}", cwd=tree)
    head = kitchen.started(
        ["git", "rev-parse", "HEAD"], cwd=tree, capture_output=True, text=True
    ).stdout.strip()
    return tree, head


def proof(head, ran=0, proved="Proved: none, docs\n"):
    """The Result the crew writes at its desk proof, before its pull request."""
    return (
        "\n## Result\nStatus: done\nDone when: each holds\nProof:\n"
        f"- the check: Checked below\nChecked: {DESK} exit {ran} at {head}\n{proved}"
        "Branch: alpha   Pull request: after the review\nChanged: a doc\nSteers: none\n"
        "Left: none\n"
    )


def proved_crew(kitchen, ran=0, push=True, review="review", pull="open one when done"):
    """A row jbus launched, whose crew committed a doc, wrote its desk proof's Result and
    ended its turn. The brief's header says `Pull request: <pull>`. Returns its thread, the
    brief's path and the head."""
    add(kitchen, "alpha")
    kitchen.poll(NOW - timedelta(minutes=3))
    (thread,) = kitchen.t3.threads
    tree, head = pushed_branch(kitchen, push=push)
    thread.update(status="completed", latestRunId="run-1", worktreePath=str(tree))
    kitchen.t3.at_work.discard(thread["threadId"])
    path = kitchen.home / "tasks" / "alpha.md"
    text = path.read_text().replace("Review: review\n", f"Review: {review}\n")
    text = text.replace("Pull request: open one when done\n", f"Pull request: {pull}\n", 1)
    path.write_text(text + proof(head, ran))
    return thread, path, head


def section(head, verdict="clean", findings="- none\n", seat=1):
    return (
        f"\n## Review\nBy: claudeAgent claude-sonnet-5-5 high #{seat}\nVerdict: {verdict}\n"
        f"Head: {head}   Unchanged by the review: yes\nSent to: not sent\nFindings:\n{findings}"
    )


def test_a_crew_whose_desk_proof_holds_gets_its_review_launched_by_jbus_with_no_pull_request(
    kitchen,
):
    thread, path, head = proved_crew(kitchen)
    for minutes in (0, 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    (launched,) = reviewers(kitchen)
    assert launched["title"] == "review: alpha, 1"
    assert launched["message"] == "/pr-review run alpha 1"
    assert launched["workspaceStrategy"] == {
        "type": "existing_worktree",
        "worktreePath": thread["worktreePath"],
        "branch": "alpha",
    }
    made = kitchen.t3.threads[-1]["threadId"]
    assert path.read_text().endswith(
        f"Pull request: after the review\nChanged: a doc\n"
        f"Steers: none\nLeft: none\nReviewer: {made} #1\n"
    )
    assert kitchen.lines("prereview") == [f"launched review alpha: {made} at {head[:12]}"]
    assert not any("pr create" in line for line in kitchen.log("gh"))


@pytest.mark.parametrize(
    ("ran", "push", "why"),
    [
        (1, True, prereview.UNPROVED),
        (0, False, prereview.UNPUSHED.format(branch="alpha")),
    ],
    ids=["its check failed", "its head is not pushed"],
)
def test_a_crew_whose_desk_proof_does_not_hold_at_a_pushed_head_gets_no_review(
    kitchen, ran, push, why
):
    thread, _, head = proved_crew(kitchen, ran=ran, push=push)
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert reviewers(kitchen) == []
    assert kitchen.lines("condition") == [f"condition alpha: {why}"]
    (told,) = refused(kitchen, thread)
    assert told["clientRequestId"] == f"prereview-refused|alpha|{head[:12]}"
    assert why in told["message"], told["message"]


def refused(kitchen, thread):
    """What jbus sent the crew of a review it would not launch."""
    return [
        one
        for one in sends(kitchen)
        if one["threadId"] == thread["threadId"]
        and one["clientRequestId"].startswith("prereview-refused|")
    ]


def test_a_refused_crew_that_fixes_its_proof_and_writes_a_follow_up_result_gets_its_review(
    kitchen,
):
    """The crew told that its desk proof does not hold at its pushed head reruns it, and writes a
    follow-up Result that still says its pull request opens after the review. That Result waits
    on the review as the first did: the row is not ended, and jbus launches the reviewer."""
    thread, path, head = proved_crew(kitchen, ran=1)
    kitchen.poll()
    assert len(refused(kitchen, thread)) == 1
    again = proof(head).replace("## Result\n", "## Result, follow-up (2026-11-08, proof)\n", 1)
    path.write_text(path.read_text() + again)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [one["title"] for one in reviewers(kitchen)] == ["review: alpha, 1"]
    assert rows(kitchen)["alpha"]["status"] not in ("done", "left")
    assert not thread.get("settled")


@pytest.mark.parametrize("ran", [0, 1], ids=["its proof holds", "its proof does not hold"])
def test_a_crew_whose_result_leaves_something_still_waits_on_its_review(kitchen, ran):
    """A Result that opens its pull request after the review and whose `Left:` line names work
    for after the merge owes its review all the same: its row is not `left` while the review is
    due, running, or refused and told to the crew."""
    thread, path, head = proved_crew(kitchen, ran=ran)
    text = path.read_text()
    path.write_text(text.replace("Left: none\n", "Left: after the merge, a row for the index\n"))
    for minutes in (0, 3, 30):
        kitchen.poll(NOW + timedelta(minutes=minutes))
        assert rows(kitchen)["alpha"]["status"] not in ("done", "left")
    assert not thread.get("settled")
    if ran:
        assert reviewers(kitchen) == []
        assert len(refused(kitchen, thread)) == 1
    else:
        assert [one["title"] for one in reviewers(kitchen)] == ["review: alpha, 1"]


def test_a_brief_that_asks_for_no_review_gets_no_reviewer_before_its_pull_request(kitchen):
    proved_crew(kitchen, review="none")
    kitchen.poll()
    assert reviewers(kitchen) == []


def test_a_crew_waiting_on_its_review_is_told_once_when_it_is_written_and_not_nudged_before(
    kitchen,
):
    thread, path, head = proved_crew(kitchen)
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert [one for one in sends(kitchen) if one["threadId"] == thread["threadId"]] == []
    found = "- error docs/notes.md:1 the doc is wrong\n"
    path.write_text(path.read_text() + section(head, "findings", found))
    for minutes in (9, 12, 60):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    (told,) = [one for one in sends(kitchen) if one["threadId"] == thread["threadId"]]
    assert told["clientRequestId"] == f"prereviewed|alpha|{head[:12]}"
    assert told["message"].startswith(f"jbus: alpha's review at {head[:12]} is written")
    assert "F1 [Act on] error docs/notes.md:1 the doc is wrong" in told["message"], told["message"]
    assert len(reviewers(kitchen)) == 1


def test_a_crew_whose_brief_header_says_after_the_review_is_not_over_before_its_review(kitchen):
    """A brief whose header says `Pull request: after the review`, not `open one ...`, still
    owes its pull request once its Result says the pull request opens after the review
    (`jbus.watch.owes_pull`). A pass
    that sees that Result while the crew is still at work neither settles the crew nor marks the
    row done, and the pass after it, with the crew idle, launches the reviewer."""
    thread, _, _ = proved_crew(kitchen, pull="after the review")
    thread.update(status="running")
    kitchen.t3.at_work.add(thread["threadId"])
    kitchen.poll()
    assert not thread.get("settled")
    assert rows(kitchen)["alpha"]["status"] != "done"
    assert reviewers(kitchen) == []
    thread.update(status="completed")
    kitchen.t3.at_work.discard(thread["threadId"])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [one["title"] for one in reviewers(kitchen)] == ["review: alpha, 1"]
    assert not thread.get("settled")
    assert rows(kitchen)["alpha"]["status"] != "done"


def test_a_crew_whose_brief_header_says_after_the_review_is_told_when_its_review_is_written(
    kitchen,
):
    """The pass that launches the reviewer of an idle crew also ties up threads: the crew is not
    settled there, since its Result owes its pull request (`jbus.watch.owes_pull`), so the pass
    after its reviewer writes tells it."""
    thread, path, head = proved_crew(kitchen, pull="after the review")
    kitchen.poll()
    assert len(reviewers(kitchen)) == 1
    assert not thread.get("settled")
    path.write_text(path.read_text() + section(head))
    kitchen.poll(NOW + timedelta(minutes=3))
    (told,) = [one for one in sends(kitchen) if one["threadId"] == thread["threadId"]]
    assert told["clientRequestId"] == f"prereviewed|alpha|{head[:12]}"


def corrected_then_reviewed(kitchen):
    """A crew's brief as jbus-rows-name-a-home's stood at the pass that marked it done
    (2026-11-09T17:57:26Z): its first Result says the pull request opens after the review, jbus
    launched the reviewer, the crew wrote a follow-up Result that corrects a line and still says
    so, and the review is written and ran. No pull request is open. Returns the crew's thread."""
    thread, path, head = proved_crew(kitchen)
    kitchen.poll()
    assert len(reviewers(kitchen)) == 1
    again = proof(head).replace("## Result\n", "## Result, follow-up (2026-11-09, Left:)\n", 1)
    path.write_text(path.read_text() + again + section(head))
    return thread


def test_a_follow_up_result_that_opens_its_pull_request_after_the_review_is_not_done(kitchen):
    """A follow-up Result that still says its pull request opens after the review owes that pull
    request once the review ran, as a first Result does (`jbus.watch.owes_pull`): the row is
    not `done` while no pull request is open."""
    thread = corrected_then_reviewed(kitchen)
    for minutes in (3, 6, 30):
        kitchen.poll(NOW + timedelta(minutes=minutes))
        assert rows(kitchen)["alpha"]["status"] not in ("done", "left")
    assert not thread.get("settled")


def test_a_row_that_depends_on_a_crew_that_owes_its_pull_request_after_the_review_waits(kitchen):
    """Such a row has not ended (`jbus.watch.final`), so a row that depends on it does not
    launch before its pull request merges."""
    corrected_then_reviewed(kitchen)
    add(kitchen, "beta", priority=2, depends="alpha")
    for minutes in (3, 6, 30):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert [one["title"] for one in kitchen.t3.launches if one["title"] == "crew: beta"] == []
    assert rows(kitchen)["beta"]["status"] == "queued"


def test_a_review_before_the_pull_request_that_never_comes_is_asked_again_by_the_clock(kitchen):
    """The crew waits on jbus while its review is out, so a reviewer that ended its turn writing
    nothing is the clock's, as on an open pull request: after `clock.PASSES` passes it is sent
    its line again."""
    proved_crew(kitchen)
    kitchen.poll()
    made = kitchen.t3.threads[-1]
    made["status"] = "completed"
    kitchen.t3.at_work.discard(made["threadId"])
    for minutes in range(3, 3 * (clock.PASSES + 2), 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    asked = [one for one in sends(kitchen) if one["threadId"] == made["threadId"]]
    assert [one["message"] for one in asked] == ["/pr-review run alpha again"]


def test_a_review_before_the_pull_request_that_did_not_run_tells_the_crew_nothing(kitchen):
    """A reviewer with no room writes a section that says `Verdict: not run` and ends its turn.
    That is no review: the crew is not told its review is written, and the clock asks the
    reviewer again, as for a reviewer that wrote nothing."""
    thread, path, head = proved_crew(kitchen)
    kitchen.poll()
    made = kitchen.t3.threads[-1]
    made["status"] = "completed"
    kitchen.t3.at_work.discard(made["threadId"])
    path.write_text(path.read_text() + section(head, "not run", "- none, no room\n"))
    for minutes in range(3, 3 * (clock.PASSES + 2), 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert [one for one in sends(kitchen) if one["threadId"] == thread["threadId"]] == []
    asked = [one for one in sends(kitchen) if one["threadId"] == made["threadId"]]
    assert [one["message"] for one in asked] == ["/pr-review run alpha again"]


def launched_after(kitchen, minutes=0):
    kitchen.poll(NOW + timedelta(minutes=minutes))
    return reviewers(kitchen)


def test_the_review_launch_takes_the_model_of_the_role_map_s_review_line(kitchen, jstack_config):
    proved_crew(kitchen)
    (jstack_config.parent / "roles").write_text(
        "review: claudeAgent claude-sonnet-5-5 claudeAgent effort=high\n"
    )
    (launched,) = launched_after(kitchen)
    assert launched["modelSelection"]["model"] == "claude-sonnet-5-5"
    assert launched["modelSelection"]["instanceId"] == "claudeAgent"


def test_a_review_pool_that_is_capped_launches_no_reviewer_until_it_has_room(
    kitchen, jstack_config
):
    proved_crew(kitchen)
    (jstack_config.parent / "roles").write_text(
        "review: claudeAgent claude-sonnet-5-5 claudeAgent effort=high\n"
    )
    full = ledger.file_of("claudeAgent")
    resets = NOW + timedelta(minutes=40)
    full.write_text(f"five_hour 100 {int(resets.timestamp())}\n")
    said = kitchen.poll()
    assert reviewers(kitchen) == []
    assert any(line.startswith("wait alpha: no reviewer launched: ") for line in said), said
    full.unlink()
    assert len(launched_after(kitchen, 3)) == 1


def test_a_role_map_that_gives_the_review_no_model_launches_one_reviewer_that_inherits(
    kitchen, jstack_config
):
    proved_crew(kitchen)
    (jstack_config.parent / "roles").write_text("review: not a line the role map reads\n")
    said = kitchen.poll()
    (launched,) = reviewers(kitchen)
    assert "modelSelection" not in launched
    assert any(line.startswith("note alpha: the role map gives the review no") for line in said)


def test_a_crew_thread_t3_code_names_no_worktree_for_gets_no_reviewer(kitchen):
    thread, _, head = proved_crew(kitchen)
    del thread["worktreePath"]
    kitchen.poll()
    assert reviewers(kitchen) == []
    assert kitchen.lines("condition") == [f"condition alpha: {prereview.NO_TREE}"]
    (told,) = refused(kitchen, thread)
    assert told["clientRequestId"] == f"prereview-refused|alpha|{head[:12]}"


def test_a_review_launch_t3_code_refuses_is_a_condition_once_and_is_not_tried_again(kitchen):
    proved_crew(kitchen)
    kitchen.t3.refuse = "no more threads"
    for minutes in (0, 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert len(reviewers(kitchen)) == 1
    assert kitchen.lines("condition") == [f"condition alpha: {prereview.LOST}"]


@pytest.mark.parametrize("fault", ["refused", "no answer", "held"])
def test_the_review_message_t3_code_does_not_take_is_tried_again_or_is_a_gate(kitchen, fault):
    thread, path, head = proved_crew(kitchen)
    kitchen.poll()
    path.write_text(path.read_text() + section(head))
    if fault == "refused":
        kitchen.t3.refuse_send = True
    elif fault == "no answer":
        kitchen.t3.lose_send = True
    else:
        command = ["uv", "run", "pytest", "tests/test_alpha.py"]
        lane = slot.short()
        waiters.register(slot.locks_dir(), thread["threadId"], "short", lane.slots, command, NOW)
    kitchen.poll(NOW + timedelta(minutes=3))
    key = f"prereviewed|alpha|{head[:12]}"
    marked = key in jbus.read_json(kitchen.state / "sent.json", [])
    if fault == "refused":
        assert kitchen.lines("condition") == [
            "condition alpha: T3 Code refused the review's message"
        ]
    else:
        assert not marked


def test_a_crew_stacked_on_a_row_that_merged_gets_its_review_on_the_branch_it_merged_into(kitchen):
    """A row before its pull request whose `Stacked on:` row merged and deleted its branch: jbus
    moves the line, in the brief's head and in its Result, onto the branch that row merged into
    before it launches the reviewer, whose start block reads the base from that line and fetches
    it from origin."""
    thread, path, head = proved_crew(kitchen)
    first, _, rest = path.read_text().partition("\n")
    after = "Pull request: after the review\n"
    rest = rest.replace(after, f"{after}Stacked on: base base\n", 1)
    path.write_text(f"{first}\nStacked on: base base\n{rest}")
    merge = kitchen.started(
        ["git", "rev-parse", "main"], cwd=kitchen.checkout, capture_output=True, text=True
    ).stdout.strip()
    kitchen.set("merged.json", [{**kitchen.merged("base", 10, merge), "baseRefName": "main"}])
    for minutes in (0, 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    text = path.read_text()
    moved = f"Stacked on: base main at {merge}"
    assert [line for line in text.splitlines() if line.startswith("Stacked on:")] == [moved] * 2
    assert len(reviewers(kitchen)) == 1
    (line,) = [one for one in text.split("\n## ")[0].splitlines() if one.startswith("Stacked on:")]
    on = line.split()[3]
    fetched = kitchen.started(
        ["git", "fetch", "-q", "origin", "alpha", on],
        cwd=thread["worktreePath"],
        capture_output=True,
        text=True,
    )
    assert fetched.returncode == 0, fetched.stderr


def test_a_crew_stacked_on_a_row_that_squash_merged_is_reviewed_on_its_own_commits(
    kitchen, monkeypatch
):
    """A link before its pull request, stacked on a row whose pull request squash-merged: main
    holds a new commit with the base's tree, and none of the base's own commits. jbus moves the
    link's own commits onto main before its review, so the diff the review reads and the
    `Proved:` line answers to hold the link's change alone, not the base's code."""
    signed(monkeypatch)
    add(kitchen, "alpha")
    kitchen.poll(NOW - timedelta(minutes=3))
    (thread,) = kitchen.t3.threads
    base = kitchen.root / "worktrees" / "base"
    kitchen.git("worktree", "add", "-q", "-b", "base", str(base), "main")
    (base / "src").mkdir(exist_ok=True)
    (base / "src" / "base.py").write_text("VALUE = 1\n")
    kitchen.git("add", "src/base.py", cwd=base)
    kitchen.git("commit", "-q", "-m", "feat: the base", cwd=base)
    last = head_of(kitchen, base)
    tree = kitchen.root / "worktrees" / "alpha"
    kitchen.git("worktree", "add", "-q", "-b", "alpha", str(tree), "base")
    (tree / "docs").mkdir(exist_ok=True)
    (tree / "docs" / "notes.md").write_text("the task\n")
    kitchen.git("add", "docs/notes.md", cwd=tree)
    kitchen.git("commit", "-q", "-m", "docs: the task", cwd=tree)
    kitchen.git("push", "-q", "origin", "alpha:refs/heads/alpha", cwd=tree)
    head = head_of(kitchen, tree)
    squash = kitchen.started(
        [
            "git",
            *IDENTITY,
            "commit-tree",
            f"{last}^{{tree}}",
            "-p",
            "main",
            "-m",
            "feat: the base (#10)",
        ],
        cwd=kitchen.checkout,
        capture_output=True,
        text=True,
    ).stdout.strip()
    kitchen.git("push", "-q", "origin", f"{squash}:refs/heads/main")
    merged = {**kitchen.merged("base", 10, squash), "headRefOid": last, "baseRefName": "main"}
    kitchen.set("merged.json", [merged])
    thread.update(status="completed", latestRunId="run-1", worktreePath=str(tree))
    kitchen.t3.at_work.discard(thread["threadId"])
    path = kitchen.home / "tasks" / "alpha.md"
    first, _, rest = path.read_text().partition("\n")
    after = "Pull request: after the review\n"
    result = proof(head).replace(after, f"{after}Stacked on: base base\n", 1)
    path.write_text(f"{first}\nStacked on: base base\n{rest}{result}")
    kitchen.poll()
    moved = kitchen.started(
        ["git", "ls-remote", "origin", "refs/heads/alpha"],
        cwd=kitchen.checkout,
        capture_output=True,
        text=True,
    ).stdout.split()[0]
    again = proof(moved).replace("## Result\n", "## Result, follow-up (2026-11-08, moved)\n", 1)
    path.write_text(path.read_text() + again)
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.git("fetch", "-q", "origin")
    own = kitchen.started(
        ["git", "diff", "--name-only", "origin/main...origin/alpha"],
        cwd=kitchen.checkout,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert own == ["docs/notes.md"]
    assert [one["title"] for one in reviewers(kitchen)] == ["review: alpha, 1"]


def head_of(kitchen, tree):
    return kitchen.started(
        ["git", "rev-parse", "HEAD"], cwd=tree, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.parametrize("fault", ["refused", "no answer", "held"])
def test_a_refusal_t3_code_does_not_take_is_a_gate_or_is_sent_on_a_later_pass(kitchen, fault):
    """The message that a review was not launched goes through the outbox as `prereviewed` does:
    one T3 Code refuses is a gate, and one with no answer, or held while the crew waits on a test
    slot, is not marked, so a later pass sends it once."""
    thread, _, head = proved_crew(kitchen, ran=1)
    if fault == "refused":
        kitchen.t3.refuse_send = True
    elif fault == "no answer":
        kitchen.t3.lose_send = True
    else:
        command = ["uv", "run", "pytest", "tests/test_alpha.py"]
        lane = slot.short()
        waiters.register(slot.locks_dir(), thread["threadId"], "short", lane.slots, command, NOW)
    kitchen.poll()
    key = f"prereview-refused|alpha|{head[:12]}"
    assert key not in jbus.read_json(kitchen.state / "sent.json", [])
    if fault == "refused":
        what = "condition alpha: T3 Code refused the message that its review was not launched"
        assert what in kitchen.lines("condition")
        return
    kitchen.t3.lose_send = False
    if fault == "held":
        waiters.drop(slot.locks_dir(), thread["threadId"])
    for minutes in (3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert [one["clientRequestId"] for one in refused(kitchen, thread)][-1:] == [key]
    assert key in jbus.read_json(kitchen.state / "sent.json", [])
