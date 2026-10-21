"""The process skills are gates, read from what each one leaves behind.

A review's step 5 (blast-radius) leaves a `Proof:` line in its `## Review` section, and
`jmerge` merges a guarded path only where that line proves the one safety fact at the head.
A hold is lifted by `jmerge --accept`, the user's hand-merge, which asks for the same fact.
A design call (`/architect`) leaves a `Design:` line in the brief, and `jbus queue add` queues
no brief that has none. A row already approved is grandfathered and launches.

`jmerge` is run against `test_home_merge`'s fake `gh` and real origin, and the pass as
`tests/test_jbus.py` runs it: the real command against a faked T3 Code server."""

import json
import re
from datetime import datetime
from types import SimpleNamespace

import pytest

import jsettings
import test_home_merge as merge
import test_jmerge_rangediff as rangediff
from jbriefs import parse
from jbus import stall
from jmerge import proof, ready
from test_briefs import TEMPLATE
from test_home_thread import as_read
from test_jbus_kitchen import Kitchen
from test_jbus_queue import add, brief, gates, queued_before
from test_jmerge_guarded import PROOF, SKILL, STARTED, guarded, jmerge, proven
from testing.paths import REPO

HEAD = merge.PUSHED
SECRET = "secrets/x.json"
HOLD = f"needs user, touches {SECRET}"
AT = "2026-10-12 09:30 ET"
ACCEPT = f"--accept 7 --by user --at '{AT}'"


def no_fact(head):
    return f"no proven safety fact at {head[:12]} (blast-radius, review step 5)"


UNPROVEN = "Reviewers: 2, A 0, B 0   Proof: unproven, a held pull request is never merged\n"
FAILED = "Proof: uv run pytest tests/test_a.py, exit 1, 1 failed\n"
REVIEWS = {
    "proven, on the reviewers' line": (
        merge.review("clean", HEAD) + PROOF,
        ("3 passed", "uv run pytest tests/test_a.py"),
    ),
    "proven, on a line of its own, the command in backticks": (
        merge.review("clean", HEAD) + "Proof: `sh proof.sh`, exit 0\n",
        ("sh proof.sh", "sh proof.sh"),
    ),
    "a colon after the exit code, on the reviewers' line, the command in backticks": (
        merge.review("clean", HEAD)
        + "Reviewers: 2, A 0, B 0   Proof: `sh proof.sh`, exit 0: the job ran on the runner\n",
        ("the job ran on the runner", "sh proof.sh"),
    ),
    "a colon after the exit code": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0: 2 passed\n",
        ("2 passed", "sh proof.sh"),
    ),
    "a full stop after the exit code": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0. 2 passed\n",
        ("2 passed", "sh proof.sh"),
    ),
    "a full stop after the exit code, at the end of the line": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0.\n",
        ("sh proof.sh", "sh proof.sh"),
    ),
    "two exit codes, both 0, the last with a colon": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, then sh b.sh, exit 0: 2 passed\n",
        ("2 passed", "sh a.sh"),
    ),
    "unproven, with an exit 0 after it": (
        merge.review("findings", HEAD) + "Proof: unproven, sh proof.sh, exit 0: it ran elsewhere\n",
        None,
    ),
    "a proof that failed, with a colon after the exit code": (
        merge.review("findings", HEAD) + "Proof: sh proof.sh, exit 1: 1 failed\n",
        None,
    ),
    "a proof that failed, with a full stop after the exit code": (
        merge.review("findings", HEAD) + "Proof: sh proof.sh, exit 1. 1 failed\n",
        None,
    ),
    "two exit codes that disagree, the failed one with a colon": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, then sh b.sh, exit 1: failed\n",
        None,
    ),
    "two exit codes that disagree, the passed one with a colon": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 1, then sh b.sh, exit 0: passed\n",
        None,
    ),
    "a failed exit code before a semicolon, then a passed one with a colon": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 1; then sh b.sh, exit 0: passed\n",
        None,
    ),
    "a passed exit code with a colon, then a failed one before words": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0: ok, then sh b.sh, exit 1 failed\n",
        None,
    ),
    "a passed exit code with a full stop, then a failed one in brackets": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0. ok (then sh b.sh, exit 1)\n",
        None,
    ),
    "a passed exit code, then a failed one before a dash": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, ok, then sh b.sh, exit 2 - failed\n",
        None,
    ),
    "a fact that starts with a full stop, after a comma": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0, .hidden is read\n",
        (".hidden is read", "sh proof.sh"),
    ),
    "a fact that starts with a full stop, after a colon": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0: .hidden is read\n",
        (".hidden is read", "sh proof.sh"),
    ),
    "exit 0:05, which is not exit 0": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0:05 elapsed\n",
        None,
    ),
    "two exit codes side by side, the second failed": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, exit 1, failed\n",
        None,
    ),
    "two exit codes side by side, the first failed": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 1, exit 0, passed\n",
        None,
    ),
    "two exit codes side by side, the second failed, at the end of the line": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, exit 2\n",
        None,
    ),
    "two exit codes side by side, both 0": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, exit 0, 2 passed\n",
        ("2 passed", "sh a.sh"),
    ),
    "a failed exit code right behind a passed one with a colon": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0: exit 1, failed\n",
        None,
    ),
    "a failed exit code right behind a passed one with a full stop": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0. exit 1\n",
        None,
    ),
    "a failed exit code after a colon, later on the line": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, ok, then sh b.sh: exit 2\n",
        None,
    ),
    "a passed exit code after a colon, which is no field of the line": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh said: exit 0, 2 passed\n",
        None,
    ),
    "a failed exit code inside the fact, behind a space": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0, it ends with exit 1 on a wait\n",
        None,
    ),
    "a failed exit code with a capital, behind a full stop": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0. Exit 1\n",
        None,
    ),
    "a failed exit code behind a semicolon": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0: ok; exit 1\n",
        None,
    ),
    "a failed exit code as the first words of the fact": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, EXIT 2 was printed\n",
        None,
    ),
    "exit 10 inside the fact": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, the hook said exit 10\n",
        None,
    ),
    "exit 01 inside the fact": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, the hook said exit 01\n",
        None,
    ),
    "exit 0 inside the fact, which is no failed code": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, the hook said Exit 0\n",
        ("the hook said Exit 0", "sh a.sh"),
    ),
    "a word that only ends in exit, which is no exit code": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, the turnstile_exit 1 gate opens\n",
        ("the turnstile_exit 1 gate opens", "sh a.sh"),
    ),
    "two spaces after exit, where the exit code goes": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit  0, 2 passed\n",
        ("2 passed", "sh a.sh"),
    ),
    "a tab after exit, where the exit code goes": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit\t0, 2 passed\n",
        ("2 passed", "sh a.sh"),
    ),
    "a tab and a space after exit, with a colon after the exit code": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit\t 0: 2 passed\n",
        ("2 passed", "sh a.sh"),
    ),
    "a proof that failed, two spaces after exit": (
        merge.review("findings", HEAD) + "Proof: sh a.sh, exit  1, 1 failed\n",
        None,
    ),
    "a proof that failed, a tab after exit": (
        merge.review("findings", HEAD) + "Proof: sh a.sh, exit\t1, 1 failed\n",
        None,
    ),
    "two exit codes that disagree, the failed one with two spaces after exit": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, then sh b.sh, exit  1, failed\n",
        None,
    ),
    "two spaces after exit, and exit 01, which is not exit 0": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit  01, 2 passed\n",
        None,
    ),
    "a failed exit code inside the fact, two spaces after exit": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, the hook said exit  1\n",
        None,
    ),
    "a failed exit code inside the fact, a tab after exit": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, the hook said exit\t1\n",
        None,
    ),
    "a hyphen-led pre-exit 1 inside the fact, which is read as a failed code": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, the pre-exit 1 hook ran\n",
        None,
    ),
    "a hyphen-led pre-exit 0 inside the fact, which is no failed code": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, the pre-exit 0 hook ran\n",
        ("the pre-exit 0 hook ran", "sh a.sh"),
    ),
    "no separator, and words that start with a full stop": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0  .github/x runs\n",
        None,
    ),
    "spaces before the comma after the exit code": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0 , 2 passed\n",
        ("2 passed", "sh a.sh"),
    ),
    "exit 01, which is not exit 0": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 01: 2 passed\n",
        None,
    ),
    "exit 0x, which is not exit 0": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0x: 2 passed\n",
        None,
    ),
    "exit 0.5, which is not exit 0": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh, exit 0.5 of the time\n",
        None,
    ),
    "unproven": (merge.review("findings", HEAD) + UNPROVEN, None),
    "a proof that ran and failed": (merge.review("findings", HEAD) + FAILED, None),
    "a proof that failed, whose command has an exit 0 in it": (
        merge.review("findings", HEAD) + "Proof: sh -c 'run || exit 0', exit 1, 1 failed\n",
        None,
    ),
    "a proof that failed, under a fact in words that says exit 0": (
        merge.review("findings", HEAD)
        + "Proof: (the fact: jmerge ends with exit 0 when it waits), exit 1, 1 failed\n",
        None,
    ),
    "a proof that passed, whose command has an exit 1 in it": (
        merge.review("clean", HEAD) + "Proof: sh -c 'run || exit 1', exit 0, 2 passed\n",
        None,
    ),
    "two exit codes that disagree": (
        merge.review("clean", HEAD) + "Proof: sh a.sh, exit 0, then sh b.sh, exit 1, failed\n",
        None,
    ),
    "an exit code in brackets, which is no field of the line": (
        merge.review("clean", HEAD) + "Proof: sh proof.sh passed (exit 0)\n",
        None,
    ),
    "a proof with no exit code": (merge.review("clean", HEAD) + "Proof: it looks right\n", None),
    "an older head": (merge.review("clean", merge.REVIEWED) + PROOF, None),
    "none": (merge.review("clean", HEAD), None),
    "no review": ("", None),
    "a finding that quotes the line": (
        merge.review("findings", HEAD).replace("it is wrong", "Proof: x, exit 0, fine"),
        None,
    ),
    "a second review of the head that could not prove it": (
        merge.review("clean", HEAD) + PROOF + merge.review("findings", HEAD) + UNPROVEN,
        None,
    ),
    "a review of an older head, then one of the head": (
        merge.review("findings", merge.REVIEWED) + UNPROVEN + merge.review("clean", HEAD) + PROOF,
        ("3 passed", "uv run pytest tests/test_a.py"),
    ),
    "a result that only talks about a Proof: line": ("Proof: make check, exit 0, ok\n", None),
}


@pytest.mark.parametrize("case", REVIEWS)
def test_a_fact_is_proven_only_by_the_review_of_the_head(case):
    review, found = REVIEWS[case]
    text = merge.brief(review)
    assert proof.fact(text, HEAD) == found
    assert proof.short(text, HEAD) == ("" if found else no_fact(HEAD))


@pytest.mark.parametrize(
    ("code", "found"), [("0", ("3 passed", "uv run pytest tests/test_a.py")), ("1", None)]
)
def test_the_proof_line_the_review_template_shows_is_the_one_the_gate_reads(code, found):
    """The reviewer writes the line by hand, from the form in pr-review's `templates/review.md`."""
    template = (REPO / "features" / "pr-review" / "templates" / "review.md").read_text()
    (form,) = [line.split("Proof: ")[1] for line in template.splitlines() if "Proof: " in line]
    ran, unproven = form.split(" | ")
    filled = {
        "<the command that ran>": "`uv run pytest tests/test_a.py`",
        "<its exit code>": code,
        "<the last line or two it printed>": "3 passed",
        "<the fact>": "a held pull request is never merged",
    }
    for place, value in filled.items():
        ran, unproven = ran.replace(place, value), unproven.replace(place, value)
    assert "<" not in ran + unproven
    assert proof.fact(merge.brief(merge.review("clean", HEAD) + f"Proof: {ran}\n"), HEAD) == found
    assert (
        proof.fact(merge.brief(merge.review("clean", HEAD) + f"Proof: {unproven}\n"), HEAD) is None
    )


def test_the_proof_line_written_as_step_5_says_is_proven_and_its_trap_is_refused():
    """Step 5 of the review says how the form is filled, and gives one fact each way."""
    root = REPO
    template = (root / "features" / "pr-review" / "templates" / "review.md").read_text()
    (form,) = [line.split("Proof: ")[1] for line in template.splitlines() if "Proof: " in line]
    ran = form.split(" | ")[0]
    step = as_read(root / "features" / "pr-review" / "SKILL.md")
    (said,) = [line for line in step.splitlines() if "section's `Proof:` line" in line]
    ((plain, trap),) = re.findall(r"write `([^`]+)`, not `([^`]+)`", said)
    (code,) = re.findall(r"`(exit <n>)`", said)

    def filled(fact, command="sh proof.sh"):
        line = ran.replace("<the command that ran>", f"`{command}`")
        line = line.replace("<its exit code>", "0")
        line = line.replace("<the last line or two it printed>", fact)
        assert "<" not in line
        return proof.fact(merge.brief(merge.review("clean", HEAD) + f"Proof: {line}\n"), HEAD)

    assert filled(plain) == (plain, "sh proof.sh")
    assert filled(trap) is None
    for n, stands in (("0", True), ("1", False), ("2", False)):
        named = code.replace("<n>", n)
        assert filled(f"then {named}") == ((f"then {named}", "sh proof.sh") if stands else None)
        assert bool(filled(plain, command=f"sh -c 'run || {named}'")) is stands


def test_a_guarded_pull_request_with_its_fact_proven_at_the_head_is_merged(proven_merged, rules):
    proven_merged.home.open_pull_request(proven_merged.head, checks=(STARTED,), files=[SKILL])
    (said,) = jmerge(proven_merged, rules)
    assert said.startswith("merged 7 alpha ")


@pytest.mark.parametrize("case", ["unproven", "an older head", "none"])
def test_a_guarded_pull_request_with_no_proven_fact_at_the_head_waits(proven_merged, rules, case):
    review = {
        "unproven": merge.review("clean", proven_merged.head) + UNPROVEN,
        "an older head": proven("findings", proven_merged.start)
        + f"Fixed: {proven_merged.head}\nFinding: fixed, it\n",
        "none": merge.review("clean", proven_merged.head),
    }[case]
    (proven_merged.home.tasks / "alpha.md").write_text(merge.brief(review))
    proven_merged.home.open_pull_request(proven_merged.head, checks=(STARTED,), files=["a.txt"])
    assert jmerge(proven_merged, rules, "--check") == [f"ready 7 {proven_merged.head} alpha alpha"]
    proven_merged.home.open_pull_request(proven_merged.head, checks=(STARTED,), files=[SKILL])
    assert jmerge(proven_merged, rules) == guarded(no_fact(proven_merged.head))
    assert proven_merged.untouched()


def held(proven_merged):
    """A pull request `jmerge` holds for the user, said in a pass of its own."""
    proven_merged.home.open_pull_request(proven_merged.head, files=["a.txt", SECRET])
    assert proven_merged.run() == [f"hold 7 {merge.URL}: {HOLD}"]
    assert proven_merged.untouched()


def accept(proven_merged, flags=ACCEPT):
    said = proven_merged.home.run(flags)
    return proven_merged.home.code, said


def test_accept_merges_a_held_pull_request_whose_fact_is_proven_and_logs_who_and_when(
    proven_merged,
):
    held(proven_merged)
    code, (accepted, said) = accept(proven_merged)
    commit, pulled = proven_merged.on_main()
    assert accepted == (
        f"accepted 7 {merge.URL}: {HOLD}, lifted at {proven_merged.head[:12]} by user at {AT}, "
        f"safe because 3 passed (proven at {proven_merged.head[:12]})"
    )
    assert (code, said, pulled) == (0, merge.merged_line(commit), commit)
    assert [line[17:] for line in proven_merged.log()][-2:] == [accepted, said]
    assert proven_merged.plan.read_text() == merge.PLAN


@pytest.mark.parametrize("review", ["unproven", "none"])
def test_accept_refuses_a_held_pull_request_with_no_proven_fact(proven_merged, review):
    text = merge.review("clean", proven_merged.head) + (UNPROVEN if review == "unproven" else "")
    (proven_merged.home.tasks / "alpha.md").write_text(merge.brief(text))
    held(proven_merged)
    assert accept(proven_merged) == (1, [f"refused 7 {merge.URL}: {no_fact(proven_merged.head)}"])
    assert proven_merged.untouched()


def test_accept_refuses_at_a_head_other_than_the_one_the_hold_was_at(proven_merged):
    held(proven_merged)
    was = proven_merged.head
    (proven_merged.tree / "a.txt").write_text("the task, and more\n")
    merge.git(proven_merged.tree, "commit", "-q", "-am", "more")
    merge.git(proven_merged.tree, "push", "-q")
    head = merge.git(proven_merged.tree, "rev-parse", "HEAD")
    (proven_merged.home.tasks / "alpha.md").write_text(merge.brief(proven("clean", head)))
    proven_merged.home.open_pull_request(head, files=["a.txt", SECRET])
    refused = f"refused 7 {merge.URL}: its hold was at {was[:12]}, and its head is {head[:12]}"
    assert accept(proven_merged) == (1, [refused])
    assert merge.git(proven_merged.origin, "rev-parse", "main") == proven_merged.start
    assert proven_merged.run() == [f"hold 7 {merge.URL}: {HOLD}"]
    code, said = accept(proven_merged)
    assert code == 0 and said[1].startswith("merged 7 alpha ")


def test_a_proof_carries_over_a_rebase_jmerge_compared_and_found_clean(proven_merged):
    rebased = rangediff.Rebased(proven_merged, {8: "theirs 8"}, files=(rangediff.FILE, SECRET))
    assert proven_merged.run() == [f"hold 7 {merge.URL}: {HOLD}"]
    code, said = accept(proven_merged)
    assert code == 0 and f"safe because 3 passed (proven at {rebased.before[:12]})" in said[0]
    assert said[1].startswith("merged 7 alpha ")


def test_accept_asks_a_rebase_that_dropped_a_line_for_a_proof_at_the_rebased_head(proven_merged):
    """A drop is held once a review of the rebased head did not rule on it. That head is
    compared with no other, so the proof of the commit before the rebase does not carry."""
    rebased = rangediff.Rebased(proven_merged, {11: "theirs 11"}, {11: "the task 11"})
    ack = (
        f"Dropped on rebase: {rangediff.FILE}, 1 of main's, 0 of its own, "
        f"at {rebased.head[:12]}: the task replaces it\n"
    )
    before = proven("clean", rebased.before)
    rebased.brief(before + merge.review("clean", rebased.head), ack)
    (hold,) = proven_merged.run()
    assert hold.startswith(f"hold 7 {merge.URL}: needs user, the review of {rebased.head[:12]} ")
    assert accept(proven_merged) == (1, [f"refused 7 {merge.URL}: {no_fact(rebased.head)}"])
    assert merge.git(proven_merged.origin, "rev-parse", "main") == rebased.tip
    rebased.brief(before + proven("clean", rebased.head), ack)
    code, said = accept(proven_merged)
    assert code == 0 and f"(proven at {rebased.head[:12]})" in said[0]
    assert said[1].startswith("merged 7 alpha ")


def test_accept_says_and_logs_every_hold_it_lifts(proven_merged):
    """A drop the review did not rule on, on a pull request that also changes a protected
    path: `jmerge` shows the first hold, and the accept names both."""
    files = (rangediff.FILE, SECRET)
    rebased = rangediff.Rebased(proven_merged, {11: "theirs 11"}, {11: "the task 11"}, files=files)
    ack = (
        f"Dropped on rebase: {rangediff.FILE}, 1 of main's, 0 of its own, "
        f"at {rebased.head[:12]}: the task replaces it\n"
    )
    rebased.brief(proven("clean", rebased.before) + proven("clean", rebased.head), ack)
    drop = f"needs user, the review of {rebased.head[:12]} did not rule on the drops in f.txt"
    assert proven_merged.run() == [f"hold 7 {merge.URL}: {drop}"]
    both = f"{drop} and {HOLD}"
    assert (
        accept(proven_merged, "--accept 7 --check")[1][0].split(", accepted: ")[1].startswith(both)
    )
    code, said = accept(proven_merged)
    assert code == 0 and said[0].startswith(f"accepted 7 {merge.URL}: {both}, lifted at ")
    assert proven_merged.log()[-2].endswith(said[0])


def test_a_merged_hold_is_taken_off_the_record_and_the_others_stay(proven_merged):
    held(proven_merged)
    record = proven_merged.home.state / "holds.json"
    record.write_text(json.dumps({**json.loads(record.read_text()), "9": "d" * 40}))
    assert accept(proven_merged)[0] == 0
    assert json.loads(record.read_text()) == {"9": "d" * 40}


def test_the_waiting_line_is_read_off_what_jmerge_itself_prints(proven_merged):
    """`stall.hand_merge` is given the real `jmerge --accept 7 --check`, not a stub of it."""
    held(proven_merged)

    def asked(*command):
        said = proven_merged.home.run(*command[1:])
        return SimpleNamespace(stdout="\n".join(said), returncode=proven_merged.home.code)

    run = SimpleNamespace(run=asked, user=jsettings.Settings(label="ET"))
    line = f"hand-merge #7 {merge.URL}: {HOLD}; "
    assert stall.hand_merge(run, 7, merge.URL, HOLD) == (
        f"{line}safe because 3 passed (proven at {proven_merged.head[:12]}); "
        'jmerge --accept 7 --by user --at "<YYYY-MM-DD HH:MM ET>"'
    )
    (proven_merged.home.tasks / "alpha.md").write_text(
        merge.brief(merge.review("clean", proven_merged.head))
    )
    assert (
        stall.hand_merge(run, 7, merge.URL, HOLD) == f"{line}not yet, {no_fact(proven_merged.head)}"
    )
    (proven_merged.home.state / "holds.json").unlink()
    assert stall.hand_merge(run, 7, merge.URL, HOLD) == (
        f"{line}not yet, its hold is not on record, run jmerge first, "
        f"and its head is {proven_merged.head[:12]}"
    )
    assert proven_merged.untouched()


def test_accept_refuses_a_hold_no_pass_has_said(proven_merged):
    proven_merged.home.open_pull_request(proven_merged.head, files=["a.txt", SECRET])
    assert proven_merged.home.ready() == [f"hold 7 {merge.URL}: {HOLD}"]
    refused = (
        f"refused 7 {merge.URL}: its hold is not on record, run jmerge first, "
        f"and its head is {proven_merged.head[:12]}"
    )
    assert accept(proven_merged) == (1, [refused])
    assert proven_merged.untouched()


def test_accept_lifts_nothing_but_a_hold(proven_merged):
    held(proven_merged)
    proven_merged.home.open_pull_request(
        proven_merged.head, checks=(merge.FAILED,), files=["a.txt", SECRET]
    )
    refused = f"refused 7 {merge.URL}: it is not held, it waits: {merge.NOT_PASSED}"
    assert accept(proven_merged) == (1, [refused])
    proven_merged.home.open_pull_request(proven_merged.head)
    refused = f"refused 7 {merge.URL}: it is not held, jmerge merges it by itself"
    assert accept(proven_merged) == (1, [refused])
    assert accept(proven_merged, ACCEPT.replace("7", "8")) == (
        1,
        ["refused 8: no open pull request has that number"],
    )
    assert proven_merged.untouched()


def test_accept_with_check_says_what_it_would_merge_and_merges_nothing(proven_merged):
    held(proven_merged)
    log = proven_merged.log()
    safe = f"safe because 3 passed (proven at {proven_merged.head[:12]})"
    assert (
        accept(proven_merged, "--accept 7 --check")
        == accept(proven_merged, f"{ACCEPT} --check")
        == (
            0,
            [f"ready 7 {proven_merged.head} alpha alpha, accepted: {HOLD}, {safe}"],
        )
    )
    assert proven_merged.untouched() and proven_merged.log() == log


def test_a_merge_that_is_off_is_not_lifted_by_accept(proven_merged):
    held(proven_merged)
    (proven_merged.home.state / "merge-off").write_text("")
    assert accept(proven_merged) == (1, [f"wait 7 {merge.URL}: {ready.MERGE_OFF}"])
    assert proven_merged.untouched()


@pytest.mark.parametrize(
    "flags, said",
    [
        ("--accept 7 --by Chef --at '2026-10-12 09:30 ET'", "only user accepts a hold, not Chef"),
        ("--accept 7 --at '2026-10-12 09:30 ET'", "only user accepts a hold, not nobody"),
        ("--accept 7 --by user --at today", '--at is "<YYYY-MM-DD HH:MM ET>"'),
        ("--by user", "--by and --at go with --accept"),
        ("--accept alpha --check", "--accept takes a pull request's number, not alpha"),
    ],
)
def test_accept_takes_the_users_word_and_the_time_they_said_it_at(proven_merged, flags, said):
    held(proven_merged)
    assert accept(proven_merged, flags) == (1, [])
    assert proven_merged.home.stderr.strip().splitlines()[-1] == f"jmerge: {said}"
    assert proven_merged.untouched()


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


PLAIN = "# alpha: a task\nWhere: `src/alpha/`\n"
DESIGNS = {
    "the path of a design": ("Design: scouts/alpha-design.md\n", ""),
    "none, with its reason": ("Design: none, a one-line fix\n", ""),
    "no line": ("", parse.NO_DESIGN),
    "a url": ("Design: https://example.test/designs/alpha.html#the-gate\n", ""),
    "None, with its reason": ("Design: None, a one-line fix\n", ""),
    "a path in backticks": ("Design: `scouts/alpha-design.md`\n", ""),
    "a path and a full stop": ("Design: scouts/alpha-design.md.\n", ""),
    "a path and its section": ("Design: scouts/alpha-design.md, section 2\n", ""),
    "a path after a word": ("Design: see scouts/alpha.md\n", ""),
    "an abbreviation that names no file": ("Design: later, e.g. tomorrow\n", parse.NO_DESIGN),
    "none with no reason": ("Design: none\n", parse.NO_DESIGN),
    "None with no reason": ("Design: None\n", parse.NO_DESIGN),
    "a word that names no file": ("Design: TBD\n", parse.NO_DESIGN),
    "not applicable": ("Design: n/a\n", parse.NO_DESIGN),
    "none and a comma": ("Design: none,\n", parse.NO_DESIGN),
    "an empty line": ("Design:\n", parse.NO_DESIGN),
    "the template's line, not filled in": (
        next(line for line in TEMPLATE.read_text().splitlines() if line.startswith("Design:"))
        + "\n",
        parse.NO_DESIGN,
    ),
    "a line in a result, under the head": (
        "## Result\nDesign: none, it was small\n",
        parse.NO_DESIGN,
    ),
}


@pytest.mark.parametrize("case", DESIGNS)
def test_a_brief_is_designed_by_a_design_line_in_its_head(case):
    line, short = DESIGNS[case]
    assert parse.designed(PLAIN + line) == short
    assert parse.NO_DESIGN == "brief has no Design: line (run /architect or say none, <why>)"


UNDESIGNED = brief("alpha").replace("Design: none, a test\n", "")


def test_queue_add_refuses_a_brief_with_no_design_line():
    """A lint runs when a row is first queued: `jbus queue add` is where a brief is refused."""
    assert parse.NO_DESIGN in parse.faults(UNDESIGNED)
    assert parse.faults(brief("alpha")) == []


def launched(kitchen):
    return [given["title"] for given in kitchen.t3.launches]


def test_an_approved_row_whose_brief_has_no_design_line_is_grandfathered_and_launches(kitchen):
    """A lint added after a row's go does not refuse it: it launches, and no gate is sent."""
    kitchen.config(max_running=6)
    queued_before(kitchen, "alpha", UNDESIGNED)
    add(kitchen, "beta", priority=2)
    kitchen.poll()
    assert gates(kitchen) == []
    assert launched(kitchen) == ["crew: alpha", "crew: beta"]


def test_a_row_whose_brief_proves_it_by_the_agents_word_launches_as_it_was_approved(kitchen):
    kitchen.config(max_running=6)
    said_by_reviewer = brief("alpha").replace("`make check`", "reviewed by reviewer")
    queued_before(kitchen, "alpha", said_by_reviewer)
    queued_before(kitchen, "gamma", brief("gamma").replace("Proves it: `make check`\n", ""))
    kitchen.poll()
    assert gates(kitchen) == []
    assert launched(kitchen) == ["crew: alpha", "crew: gamma"]


@pytest.mark.parametrize(
    "more",
    ["", "Size: S\nPlaybook: fix\n", "Size: S\nPlaybook: feature.\n"],
    ids=["no size", "fix", "feature."],
)
def test_a_row_approved_with_no_size_or_no_playbook_launches_as_it_was_approved(kitchen, more):
    kitchen.config(max_running=6)
    shapeless = (
        brief("alpha")
        .replace("Size: S\n", "")
        .replace("Playbook: feature\n", more or "Playbook: feature\n")
    )
    queued_before(kitchen, "alpha", shapeless)
    kitchen.poll()
    assert gates(kitchen) == []
    assert launched(kitchen) == ["crew: alpha"]


def test_a_row_with_a_go_waits_on_what_it_depends_on_and_is_not_gated_for_a_lint(kitchen):
    kitchen.config(max_running=6)
    add(kitchen, "beta", approve=False)
    queued_before(kitchen, "alpha", UNDESIGNED, depends="beta")
    kitchen.poll()
    assert gates(kitchen) == []
    assert kitchen.t3.launches == []


def test_with_no_config_accept_takes_user_at_a_time_of_the_machines_zone(
    proven_merged, jstack_config
):
    jstack_config.unlink()
    held(proven_merged)
    at = f"2026-10-12 09:30 {datetime(2026, 10, 12, 9, 30).astimezone().tzname()}"
    assert accept(proven_merged, "--accept 7 --by user --at '2026-10-12 09:30 Nowhere'") == (1, [])
    assert proven_merged.home.stderr.strip() == f'jmerge: --at is "<YYYY-MM-DD HH:MM {at[17:]}>"'
    code, (accepted, said) = accept(proven_merged, f"--accept 7 --by user --at '{at}'")
    commit, _ = proven_merged.on_main()
    assert accepted == (
        f"accepted 7 {merge.URL}: {HOLD}, lifted at {proven_merged.head[:12]} by user at {at}, "
        f"safe because 3 passed (proven at {proven_merged.head[:12]})"
    )
    assert (code, said) == (0, merge.merged_line(commit))
    assert not jstack_config.exists()


def test_a_config_that_names_robin_is_whom_jmerge_prints_and_takes(proven_merged, jstack_config):
    jstack_config.write_text(
        'user = "Robin"\ntimezone = "America/New_York"\ntimezone_label = "ET"\n'
    )
    hold = f"needs Robin, touches {SECRET}"
    proven_merged.home.open_pull_request(proven_merged.head, files=["a.txt", SECRET])
    assert proven_merged.run() == [f"hold 7 {merge.URL}: {hold}"]
    assert accept(proven_merged) == (1, [])
    assert proven_merged.home.stderr.strip() == "jmerge: only Robin accepts a hold, not user"
    code, (accepted, said) = accept(proven_merged, f"--accept 7 --by Robin --at '{AT}'")
    commit, _ = proven_merged.on_main()
    assert accepted == (
        f"accepted 7 {merge.URL}: {hold}, lifted at {proven_merged.head[:12]} by Robin at {AT}, "
        f"safe because 3 passed (proven at {proven_merged.head[:12]})"
    )
    assert (code, said) == (0, merge.merged_line(commit))


def test_a_config_jmerge_cannot_use_stops_it_before_it_judges(proven_merged, jstack_config):
    jstack_config.write_text('timezone = "Mars/Olympus"\n')
    proven_merged.home.open_pull_request(proven_merged.head, files=["a.txt"])
    assert proven_merged.home.run() == []
    said = f"jmerge: {jstack_config} has the timezone Mars/Olympus, not an IANA name"
    assert (proven_merged.home.code, proven_merged.home.stderr.strip()) == (1, said)
    assert proven_merged.untouched()
