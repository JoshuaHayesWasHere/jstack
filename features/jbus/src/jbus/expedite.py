"""Tell a crew what its pull request is short of. A home used to send this wake, and no
longer does.

A crew ends its turn, and nothing wakes it for what it left undone. `jmerge` reports a wait
in a line that nobody reads. `tell` reads those lines. When a line gives the same
crew-fixable reason for the same head for `AFTER` passes, `tell` sends the crew one
message that says what to do, under the key `<kind>|<slug>|<head 12>`. A `proved-` or `checked-`
reason is one only the crew's own proof or check clears (`Short.spells`): `tell` sends it on the
first pass that sees it, and once more at the same head when a new idle spell of the crew starts,
that is, on the first pass with the crew not at work after a pass that saw it at work since the
message. That second message goes under `<kind>|<slug>|<head 12>|2`, and there is no third
(`TELLS`). `TABLE` holds every reason with its sentence:

- `unfixed`, `the Result has no Fixed line`: write an answer for each finding, by id, and
  the `Fixed:` line. The line is `Fixed: none needed` when the crew declines every finding,
  and then the crew pushes nothing for it;
- `unpushed`, `nothing was pushed after them`: push the fix and name its head, or decline
  every finding in writing, as above;
- `unended`, `<k> of <n> have no Finding line`: write the lines that are missing;
- `unanswered`, `unproven`, `uncited`, `repeated` and `risky`, the waits of an answer by id
  (`jbriefs.findings`): answer each finding by id, and give a decline of a finding with a proof
  a reason that cites a path:line, a command or a gate. Give each finding its own reason, and
  park a gate for a risky one. A finding with no proof tag (`unproven`) takes a decline with
  any reason. For each of these five reasons and the three above, the line lists by id the
  findings that have no answer that counts;
- `fix`, `the scoped review of it is not written`: launch the scoped reviewer of the fix
  with the two ranges, the patch the last review saw and the patch at the head, owed only after
  a `Meets the brief: no` and while no `Proved:` line holds at the head. Where the crew cannot
  work out a range, run the crew skill's block, which says what to do;
- `meets-no`, `meets-unread` and `meets-miscounted`, the last review round's `Meets the brief:`
  line (`jbriefs.meets`) says `no`, has no shape `jmerge` reads, or counts other lines than the
  brief has: run the crew skill's block of "A second pass", which gives the scoped review the
  line is owed, after a fix for a `no`. A `Waived:` line on the user's own word is the only other
  way out, and `jmerge` already counts it before it gives `meets-no`;
- `overruled`, `the scoped review did not uphold the decline of <ids>`: fix each finding and answer
  it `fixed`, or, where the crew still stands by the decline, tell its home. The stall for this
  reason goes to the home's thread on the one list (`jbus.wakes`) and never to the user. Only a
  decline on one of `findings.RISKS` is the user's to settle. That one is a `hold`, and jbus asks
  no crew to lift it;
- `unruled`, a `hold` that says `the review of <head> did not rule on the drops in <files>`:
  launch the scoped pass over the rebase, and push nothing meanwhile;
- `unreviewed`, `it has no review yet`: launch the reviewer the pull request is owed. Or send a
  reviewer that ended its turn with no `## Review` back to work, with `/pr-review run <slug> again`.
  `features/crew/templates/rerun.md` says a reviewer accepts that line whether or not the brief has
  a section. `tell` does not send this reason for a pull request that the crew skill leaves with no
  reviewer, since the crew skill has told somebody of it already. Such a brief names no launched
  reviewer, and either its `Reviewer:` line says `none` or it has an `Unrun:`, `Stuck:` or
  `Stale base:` line for the head;
- `renumber`, `its migration <name> takes number <n>, which <default> has: renumber it to
  <free>`: rebase with the crew skill's "A conflict" block, run with `stale`. Then renumber
  the migration and the ones after it, consecutively.
- `browser`, `its browser run failed at <head12>`: the pull request's own browser run failed, and
  main's last one did not. Fix the failed tests and push.
- `skills`, `its Result has no artifact under Skills run: for <names>`: add the item each name
  owes, and the line lists each with the artifact `templates/skill-artifacts.md` names for it;
- the `proved-` reasons, each of `ready.short_on_proved`'s (`missing`, `unread`, `not-exempt`,
  `unnamed`, `stale`): run the proof block of the crew skill's do-the-task.md, which appends the
  `Proved:` line, and push nothing for it. For `base-passed` and `head-failed` the crew first fixes
  and pushes the tests, and for `not-kind` it writes the kinds again or adds the test the change
  needs.
- `checked-missing`, `checked-stale`, `checked-cut`, `checked-failed` and `checked-part`, the
  brief's last `Checked:` line is missing, of a head whose patch changed since, a time limit's
  124, a failure, or not the desk's check (`ready.short_on_checked`): run the crew's check block
  at the head, fix what it finds, and run it again until it ends 0. A 124 is no pass.
- `no-verdict` and `no-head`, a review with no verdict or no head: send its reviewer `/pr-review
  run <slug> again`. A `Fixed:` line short of a full commit is the crew's own to write again;
- `rereview`, drops no scoped review ruled on or a rebase that changed the content: launch the one
  scoped reviewer over the reason's range-diff. It is `jbus.rebase`'s kind, so a head is told once,
  and it tells where a scoped reviewer of the head the Result names ended with no review;
- `fresh-conflict`, `merged-tree`, `base` and `not-upheld`: rebase with "A conflict" run with
  `stale` (and fix the guards that fail for `merged-tree`), retarget to the default branch, or
  put back a drop the review did not uphold, else tell the home.

Every reason of `ready.reasons()` is a row of `TABLE`, in `UNTOLD` (no crew can fix it) or in
`ELSEWHERE` (another part of jbus tells the crew), and a test holds the three to `ready`.

`tell` judges each thread by the status that T3 Code lists for it. It leaves alone a crew whose
thread is at work (`watch.at_work`: starting, `running` or `waiting`), since the line may be
what the crew is about to write. It tells a crew that ended its turn (`completed`, `failed`,
`interrupted`, `cancelled`). The last four reasons wait for a review, so `tell` also does
not send them while a thread titled `review: <slug>` is at work.

The outbox holds a message to a crew whose instance is capped (`jbus.outbox`), and the first pass
after the reset sends it. While it waits the count stays at `AFTER`, as if the message were due for
the first time, so a hold the message is about stays in hand until the reset, and `LAPSE`
counts from the reset.

The message is a quiet event, `expedite`: it starts no POST. `expedite.json` counts the
passes. After the message, a pass is an idle one when the reason and the head are as they
were and nobody is at work, neither the crew nor a reviewer the reason waits for. The
`PASSES`th idle pass logs one `stall` event, quiet and in the digest, which names the pull
request, the reason and the crew's thread, once, and only of a crew that did not act.
Long work does not delay the stall forever. The `REVIEWING`th pass after the message
also sends that stall, and where somebody is at work in that pass, the stall says so.

A `hold` is the user's, except for `unruled`. `tell` returns the pull requests whose hold
it has in hand, and a pass shows those to the user as a `wait`. A hold that is not in hand is an
item of the user's list (`waiting`), and the user learns of it when it appears on that list. Such a
hold always has an owner. A hold that `tell` cannot take on goes to the user at once: a hold whose
crew jbus did not launch, or one whose crew kept no head before its rebase to take the ranges from.
A hold also goes to the user when jbus could not tell its crew by the `LAPSE`th pass, because the
thread stays at work or the message is not delivered. A hold that its crew did not lift goes to the
user too. Starting with the pass after a stall that finds nobody at work, that hold is an item of
the user's list, until the reason or the head changes. A stall that jbus sends while work is still
going on does not make the hold the user's. The hold becomes the user's once that work has ended and
`PASSES` idle passes have gone by. A pass that could not ask T3 Code or GitHub has no crew to ask.
Then `told` keeps in hand the holds `tell` had in hand, and every other hold is the user's.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jbriefs import below, findings, skills
from jbriefs.home import thread_of
from jbus import END_TURN, dispatch, merge, outbox, read_json, rebase, verbs, write_json
from jbus.passes import Pass
from jbus.stall import PASSES, REVIEWING
from jbus.t3 import Client, T3Error
from jbus.watch import World, at_work, task_brief
from jmerge import ready

if TYPE_CHECKING:
    from jbus.poll import Half

EVENTS = {"expedite": "quiet"}
EXPEDITE = "expedite"
STALL = "stall"
AFTER = 3
LAPSE = AFTER + PASSES
TELLS = 2
"""The messages a crew gets at one head for a row only its own proof or check clears
(`Short.spells`): one on the first pass that sees it, and one more when a new idle spell starts."""
NO_THREAD = "short pull request with no thread to tell"
REFUSED = "T3 Code refused the message about what a pull request is short of"
FILE = "expedite.json"
REVIEW = "review: "
NO_RANGE = "its crew kept no head before its rebase, so the hold is the user's"
NO_RANGES = "jmerge names no range-diff and its crew kept no head before its rebase to ask for"
_OWED = re.compile(r"^Scoped review: needed since ([0-9a-f]{40}),", re.M)
SECOND_PASS = (
    'Run the block of the crew skill\'s "A second pass" in your worktree and do what it prints: '
)
NO_FIX_RANGE = (
    SECOND_PASS
    + "the Result says a scoped review of the fix is owed, and jbus could not work out its two "
    "ranges."
)
RERUN = "rerun.md"
ANSWERED = (
    "unfixed",
    "unpushed",
    "unended",
    "unanswered",
    "unproven",
    "uncited",
    "repeated",
    "risky",
)
AGAIN = "/pr-review run {slug} again"
SCOPED = "/pr-review run {slug} scoped {old} {new}"
PROVE_STEP = "Once the check passed, prove the change with the tests it changes"
PROVE = (
    f'Run the proof block of the crew skill\'s do-the-task.md, its step "{PROVE_STEP}", in your '
    "worktree, with the work committed: it appends the `Proved:` line to the Result itself, and "
    "`jmerge` reads the last one. "
)
PROVE_ONLY = "Push nothing for it: the line is in the Result, not the branch."
SCOPE_REBASE = (
    "Where the Result has no `Scoped reviewer:` line of {head}, launch ONE scoped reviewer, not a "
    'full review, the way the crew skill\'s "The review" launches a reviewer, with the message '
    f"`{SCOPED}`, and add `Scoped reviewer: <threadId>, of {{head}}` to the Result. Where it "
    "has one and that thread ended its turn with no `## Review`, send that thread the same line "
    "with `t3_thread_send`, and launch no second one. Push nothing and do not rebase until its "
    "`## Review` is written."
)
_RANGE_DIFF = re.compile(r"git range-diff --no-color (\S+\.\.\S+) (\S+\.\.\S+)$")
RERUN_REVIEWER = (
    "Send the thread of the Result's last `Reviewer:`, `Second reviewer:` or `Scoped reviewer:` "
    f"line, the one that wrote that `## Review`, the one line `{AGAIN}` with `t3_thread_send`, and "
    f"write `Woke: jbus, sent {AGAIN}` in the Result, the line as sent. Never write or mend a "
    "review's line yourself, and launch no second reviewer."
)
FIX_TESTS = (
    "fix the tests until they fail over the base's code and pass at the head, commit and push "
    "that fix alone, and run the block again at the new head."
)
MESSAGE = (
    "jbus: pull request #{number} waits on you, and jmerge keeps saying the same of it "
    "({reason}). {sentence} " + END_TURN
)


@dataclass(frozen=True)
class Short:
    """A `Short` holds one thing a crew can fix: the word, the `Reason` that `jmerge` gives for it,
    and the sentence that tells the crew what to do. A line is the row's when its reason has that
    `Reason`'s code.
    `reviewed` marks a reason that a review clears. `tell` does not send such a reason while a
    reviewer is at work. `unless` reads the brief for a head, and says when the crew cannot fix
    the thing after all. `sends` is the line that the
    sentence asks the crew to send to a reviewer. The event repeats that line as the crew sent it.
    `rerun` adds the statement in `features/crew/templates/rerun.md`, the one place that says when a
    re-run needs `again`. The reviewer's Start 1 prints that statement when it refuses a message."""

    kind: str
    word: str
    reason: ready.Reason
    sentence: str
    reviewed: bool = False
    unless: Callable[[str, str], bool] | None = None
    sends: str = ""
    rerun: bool = False

    @property
    def spells(self) -> bool:
        """Say whether only the crew's own proof or check clears the row, so `tell` sends it on
        the first pass that sees it, and once more when a new idle spell of the crew starts."""
        return self.kind.startswith(("proved-", "checked-"))

    @property
    def after(self) -> int:
        """The passes of one reason at one head before `tell` sends the row."""
        return 1 if self.spells else AFTER

    @property
    def tells(self) -> int:
        """The messages `tell` sends a crew of the row at one head."""
        return TELLS if self.spells else 1


def no_reviewer_by_rule(brief: str, head: str) -> bool:
    """Say whether the brief records, by the crew skill's rule, that the pull request has
    no reviewer at this head. That is so when the crew launched no reviewer, and either none
    can run (`Reviewer: none`) or none runs yet (no check ran, a check is stuck, or the base
    is stale). A pull request whose crew launched a reviewer still waits for that review."""
    said = below.reviewers(brief, "Reviewer")
    if any(map(below.launched, said)):
        return False
    gated = rf"^(?:Unrun|Stuck|Stale base): at {re.escape(head)},"
    return bool(said) or bool(re.search(gated, brief, re.M))


CHECKED = (
    'Run the check block of the crew skill\'s "Do the task" in your worktree at the head the '
    "reason names: it runs the lint, the touched tests and the repo-guards tests and writes the "
    "`Checked:` line `jmerge` reads. Where it ends other than 0, a 124 too, fix what it found, "
    "commit, push, and run it again, until its line says `PART=touched exit 0` (`PART=guards "
    "exit 0` on an earlier head's line) at the head. Never write a `Checked:` line by hand."
)
TABLE = (
    Short(
        "unfixed",
        "wait",
        ready.NO_FIXED,
        f"Write one line in the Result for each finding, {findings.ANSWER}, and then the `Fixed:` "
        "line: `Fixed: <the head you pushed>` where you pushed a fix, or `Fixed: none needed, "
        "<reason>` when every finding is declined. Push nothing for a `Fixed: none needed`.",
    ),
    Short(
        "unpushed",
        "wait",
        ready.NOT_PUSHED,
        "The `Fixed:` line names the head the review saw, so no fix is at the head. Push the "
        "fix and set `Fixed:` to the head you pushed. Or, when every finding is declined, write "
        f"{findings.ANSWER} for each and `Fixed: none needed, <reason>`, and push nothing for "
        "that.",
    ),
    Short(
        "unended",
        "wait",
        ready.UNENDED,
        "Write the lines that are missing, one for each finding of both passes, "
        f"{findings.ANSWER}. Set `Fixed:` to the head you pushed where you push for them, and "
        "push nothing where you decline them.",
    ),
    Short(
        "unanswered",
        "wait",
        ready.UNANSWERED,
        f"Answer each finding the reason names by its id, {findings.ANSWER}: `jbriefs --findings "
        "<the brief>` lists them. An answer with no id answers none of them.",
    ),
    Short(
        "unproven",
        "wait",
        ready.UNPROVEN,
        "Each finding the reason names blocks with no proof tag: no run, check, doc line or "
        "`Done when` line shows it. Fix it or decline it, by its id, "
        f"{findings.ANSWER}: a decline of it needs no cited reason.",
    ),
    Short(
        "uncited",
        "wait",
        ready.UNCITED,
        "Give the decline of each finding the reason names a reason that cites a path:line, a "
        f"command in backticks, or the gate it is parked on, {findings.ANSWER}, or fix it.",
    ),
    Short(
        "repeated",
        "wait",
        ready.REPEATED,
        "A reason given for one finding does not decline another: give the decline of each "
        f"finding the reason names a reason of its own, {findings.ANSWER}, or fix it.",
    ),
    Short(
        "risky",
        "wait",
        ready.RISK_UNASKED,
        "A finding on security, auth, billing, data, migrations or concurrency is not declined "
        'by the crew alone: park it as a gate (the crew skill, "Do the task") with the default '
        "that it is fixed, fix it, and answer it `Finding F<n>: fixed, ...`; where the user "
        "answers that it stays, answer it `Finding F<n>: not fixed, ..., because question <n>: "
        "<the answer>`, with the Result's `Gate: question <n>` line.",
    ),
    Short(
        "fix",
        "wait",
        ready.FIX_UNREVIEWED,
        "Launch ONE scoped reviewer of the fix now, not a full review, the way the crew skill's "
        f'"The review" launches a reviewer, with the message `{SCOPED}`, '
        "and add `Scoped reviewer: <threadId>, of {head}` to the Result, in place of a "
        "`Scoped reviewer:` line whose thread wrote no `## Review`. Push nothing until its "
        "`## Review` is written.",
        reviewed=True,
        sends=SCOPED,
    ),
    Short(
        "unruled",
        "hold",
        ready.UNRULED_DROPS,
        'Launch ONE scoped reviewer over the rebase, the way the crew skill\'s "The review" '
        f"launches a reviewer, with the message `{SCOPED}`, and "
        "add `Scoped reviewer: <threadId>, of {head}` to the Result. Push nothing and do not "
        "rebase until its `## Review` is written: a `Dropped on rebase:` line is read for this "
        "head and no other.",
        reviewed=True,
        sends=SCOPED,
    ),
    Short(
        "unreviewed",
        "wait",
        ready.NO_REVIEW,
        "No thread titled `review: {slug}` is at work, and the brief has no `## Review`. Run "
        'the block of the crew skill\'s "The checks" and then the blocks of "The review", and '
        "do what they print. Where they say `launch a reviewer`, launch it and add `Reviewer: "
        "<threadId> #<n>` to the Result, `<n>` its number. Where they say `launch no reviewer` "
        "because the Result has a `Reviewer:` line, that reviewer ended its turn and wrote "
        "nothing: send its thread "
        f"the one line `{AGAIN}` with `t3_thread_send`, and write `Woke: jbus, sent {AGAIN}` "
        "in the Result, the line as sent. Launch no second one.",
        reviewed=True,
        unless=no_reviewer_by_rule,
        sends=AGAIN,
        rerun=True,
    ),
    Short(
        "meets-no",
        "wait",
        ready.MEETS_NO,
        SECOND_PASS + "the last review says the brief is not met, so fix each `Done when` line "
        "the reason names and push, and the block gives the one scoped review whose own "
        "`Meets the brief:` line must say yes. Never write or rewrite a review's line yourself: "
        "only the user's `Waived:` line, as the crew skill's \"The review\" says, clears a line "
        "otherwise.",
        reviewed=True,
    ),
    Short(
        "meets-unread",
        "wait",
        ready.MEETS_UNREAD,
        SECOND_PASS + "the last review has no `Meets the brief:` line `jmerge` reads, so the block "
        "gives the one scoped review whose own line judges the brief. Never write or rewrite a "
        "review's line yourself.",
        reviewed=True,
    ),
    Short(
        "meets-miscounted",
        "wait",
        ready.MEETS_MISCOUNTED,
        SECOND_PASS + "the last review's `Meets the brief:` line counts other `Done when` lines "
        "than the brief has, so the block gives the one scoped review whose own line counts the "
        "brief's. Never write or rewrite a review's line yourself.",
        reviewed=True,
    ),
    Short(
        "overruled",
        "wait",
        ready.DECLINES_OVERRULED,
        "The scoped pass did not uphold the decline of the findings the reason names. Fix each, "
        "push, and answer it `Finding F<n>: fixed, ...`: declining it again does not lift the "
        'ruling. Where you still hold a decline, send the home one line ("Telling the home"), '
        "`<slug>: <pull request url>, the decline of F<n> is not upheld and I hold it: <why>`, "
        "and end your turn: the home settles it with you.",
    ),
    Short(
        "renumber",
        "wait",
        ready.MIGRATION_TAKEN,
        'Rebase onto the default branch with the crew skill\'s "A conflict" block, run with '
        "`stale`. Then renumber the migration the reason "
        "names to the number it gives, and each migration of yours after it to the numbers that "
        "follow, one each and in their order: the files, and every other line that names an old "
        "number. Run the check command, and push with the block's push.",
    ),
    Short(
        "browser",
        "wait",
        ready.BROWSER_RED,
        "Your pull request's own browser run (browser.yml) failed at its head, and main's last "
        "browser run did not: the red is yours. Read its failed tests with `gh run view <run> "
        "--log-failed`, the run `gh pr checks` names for `browser`, fix them, run `make "
        "check-browser` in your worktree, and push. Leave the kept shots of the view as main "
        "has them: a moved shot fails no pull request's run, and only the shots row redraws "
        "them. `jmerge` merges once the browser run of the new head passes.",
    ),
    Short(
        "skills",
        "wait",
        ready.SKILLS_UNRUN,
        "The Result's `Skills run:` leaves out a skill its brief names. For each name the reason "
        "gives, do what the skill's file says if you have not, and add one item `- <name>: <the "
        "artifact>` under `Skills run:` in the last Result, the artifact the crew skill's "
        "`templates/skill-artifacts.md` names for it. Push nothing for it.",
    ),
    Short(
        "proved-missing",
        "wait",
        ready.PROVED_MISSING,
        PROVE + "The Result has no `Proved:` line, and the pull request changes the tests the "
        "reason names. " + PROVE_ONLY,
    ),
    Short(
        "proved-unread",
        "wait",
        ready.PROVED_UNREAD,
        PROVE + "The last `Proved:` line has no shape `jmerge` reads: never write or mend the "
        "line by hand, the block's line replaces it. " + PROVE_ONLY,
    ),
    Short(
        "proved-not-exempt",
        "wait",
        ready.PROVED_NOT_EXEMPT,
        PROVE + "The line says `none`, and the pull request changes the tests the reason names, "
        "so it is no exemption: the block's line names those tests. " + PROVE_ONLY,
    ),
    Short(
        "proved-not-kind",
        "wait",
        ready.PROVED_NOT_KIND,
        "The `Proved:` line says `none` for kinds that leave out the file the reason names. "
        "Where that file is docs or config, write the line again as `Proved: none, <kinds>` with "
        "each kind the pull request's files are, and push nothing. Otherwise the change needs a "
        "test that names it: add or change the test that fails without it, commit and push that "
        "alone, then run the proof block of the crew skill's do-the-task.md, its step "
        f'"{PROVE_STEP}", which appends the `Proved:` line that names the changed tests.',
    ),
    Short(
        "proved-unnamed",
        "wait",
        ready.PROVED_UNNAMED,
        PROVE + "The last `Proved:` line leaves out the tests the reason names, and the block's "
        "line names every test the branch changes. " + PROVE_ONLY,
    ),
    Short(
        "proved-base-passed",
        "wait",
        ready.PROVED_BASE_PASSED,
        PROVE
        + "The last line says the tests did not fail at the base, so they prove nothing: "
        + FIX_TESTS,
    ),
    Short(
        "proved-head-failed",
        "wait",
        ready.PROVED_HEAD_FAILED,
        PROVE + "The last line says the tests did not pass at the head: " + FIX_TESTS,
    ),
    Short(
        "proved-stale",
        "wait",
        ready.PROVED_STALE,
        PROVE + "The last line is of a head whose patch the pull request no longer carries, so "
        "run the block at the head as it is. " + PROVE_ONLY,
    ),
    *(
        Short(reason.code, "wait", reason, CHECKED)
        for reason in (
            ready.CHECKED_MISSING,
            ready.CHECKED_STALE,
            ready.CHECKED_CUT,
            ready.CHECKED_FAILED,
            ready.CHECKED_PART,
        )
    ),
    Short(
        "no-verdict",
        "wait",
        ready.NO_VERDICT,
        "The last `## Review` has no verdict `jmerge` reads, so no review has judged the head. "
        + RERUN_REVIEWER,
        reviewed=True,
        sends=AGAIN,
        rerun=True,
    ),
    Short(
        "no-head",
        "wait",
        ready.NO_HEAD,
        "Neither the `Fixed:` line nor the last `## Review` names a full commit, so `jmerge` has "
        "no head to compare the rebase with. Where your `Fixed:` line names the head you pushed "
        "by less than its 40 characters, write it again with the full commit and push nothing. "
        "Otherwise: " + RERUN_REVIEWER,
        reviewed=True,
        sends=AGAIN,
        rerun=True,
    ),
    Short(
        "rereview",
        "wait",
        ready.SCOPED_UNRULED,
        "No scoped review ruled yet on the drops your Result explains. " + SCOPE_REBASE,
        reviewed=True,
        sends=SCOPED,
    ),
    Short(
        "rereview",
        "wait",
        ready.CONTENT_CHANGED,
        "Your rebase changed the content after its review. " + SCOPE_REBASE,
        reviewed=True,
        sends=SCOPED,
    ),
    Short(
        "fresh-conflict",
        "wait",
        ready.FRESH_CONFLICT,
        "`jmerge` merged your head over the default branch's tip and it conflicts, though GitHub "
        'does not say so yet. Rebase with the crew skill\'s "A conflict" block, run with `stale`, '
        "resolve the conflict, run the check command, and push with the block's push.",
    ),
    Short(
        "merged-tree",
        "wait",
        ready.MERGED_TREE_FAILS,
        "Merged over today's default branch, your head fails the guards the reason names: a clash "
        'with what merged since your check. Rebase with the crew skill\'s "A conflict" block, run '
        "with `stale`, run the check command, fix what fails, and push with the block's push.",
    ),
    Short(
        "base",
        "wait",
        ready.BASE,
        "Its base is not the default branch, and jbus stacked it on no link. Retarget it with `gh "
        "pr edit {number} --base <the default branch the reason names>`, then rebase onto that "
        'branch with the crew skill\'s "A conflict" block, run with `stale`, and push with the '
        'block\'s push. Where that base is meant, send the home one line ("Telling the home"), '
        "`<slug>: <pull request url>, its base <base> is meant`, and end your turn: only the user "
        "adds a merge base, with `jbus project bases --add`.",
    ),
    Short(
        "not-upheld",
        "hold",
        ready.NOT_UPHELD,
        "The review did not uphold the drop in the files the reason names, so the lines come "
        "back: put them back, take each such file's `Dropped on rebase:` line out of the Result, "
        "run the check command, commit and push. Where you still hold a drop, send the home one "
        'line ("Telling the home"), `<slug>: <pull request url>, the drop in <file> is not upheld '
        "and I hold it: <why>`, and end your turn: the home settles it with you.",
    ),
)
_USERS = "the user's to lift, by a word, a go or a setting, and no push of a crew's lifts it"
_RUNNER = "a wait on GitHub or the merge runner, which jmerge asks again and no crew's push moves"
_AHEAD = "a wait on a pull request that merges first, which ends when that one has merged"
_CHECKOUT = "a failure of git in jmerge's main checkout, which no push of a crew's mends"
UNTOLD = {
    ready.NO_BRIEF.code: "no brief names the pull request, so there is no crew to tell",
    ready.HAND_DRAFT.code: "the draft is somebody's by hand, and jmerge never marks it ready",
    ready.OTHER_HOME.code: "another home's pull request, whose crew this home does not tell",
    ready.RISKY_OVERRULED.code: "a decline on a risk is the user's to settle (findings.RISKS)",
    ready.NO_RUN.code: "GitHub started no run at the head, a gate of The checks and no push's",
    ready.MAIN_BROWSER_RED.code: "main's own browser run failed too, so the red is not the crew's",
    ready.CANCELLED_UNRUN.code: "jbus.cancelled runs a cancelled check again, and a push does not",
    ready.QUEUED_UNREOPENED.code: "jmerge closed it and could not reopen it: tell sees open ones",
    ready.CANCELLED_TWICE.code: "jbus.cancelled takes a check cancelled twice to the home",
    **{
        code: why
        for codes, why in (
            (
                "main-moved merging merge-failed no-messages undecided not-passed live-run "
                "queue-unreadable carries-unknown base-merge-asked base-merge-due "
                "base-merge-refused base-moved-asked base-moved-due in-line queued-restarted "
                "queued-unopened queued-unclosed queued-gave-up queued-unrestarted "
                "merged-tree-unended merged-tree-unbuilt merged-tree-no-time merged-tree-no-slot",
                _RUNNER,
            ),
            ("merges-after carries-after stacked-on migration-merging migration-rebasing", _AHEAD),
            ("unmerged cannot-check", _CHECKOUT),
            ("merge-off no-go row-held review-none touches renames-unsaid unlisted", _USERS),
        )
        for code in codes.split()
    },
}
"""Each code no crew can fix, and why: `tell` sends nothing for it, and a test checks each code."""
ELSEWHERE = {
    ready.MAIN_CHANGED.code: "jbus.rebase tells the crew to rebase, once for the pull request",
    ready.CONFLICTS.code: "jbus.rebase tells the crew of the conflict at each head",
    ready.DROPPED.code: "jbus.rebase tells the crew of the drop, once per head",
    ready.CHECK_FAILED.code: "jbus.rebase tells the crew of the failed check, once per head",
    ready.STACKED_UNMOVED.code: "jbus.stack tells the crew to move its commits onto the base",
}
"""Each code a crew fixes that another part of jbus tells it of: `tell` sends nothing for it."""


def short_of(said: merge.Line) -> Short | None:
    """Return the row of `TABLE` that a line of `jmerge` is about, by its reason's code, or
    nothing for a line no crew can fix. A line as `jmerge` prints it has no code, and takes the
    one its text gives (`ready.code_of`)."""
    code = said.code or ready.code_of(said.reason)
    return next((row for row in TABLE if row.word == said.word and row.reason.code == code), None)


def _kept(run: Pass, slug: str) -> str:
    """Return the head the crew kept before its last rebase, or nothing where it kept none.
    That head is the newest commit under the slug's `refs/jstack/pre-rebase/` directory."""
    ref = f"refs/jstack/pre-rebase/{slug}/"
    asked = ("git", "for-each-ref", "--sort=-committerdate", "--count=1", "--format=%(objectname)")
    kept = run.run(*asked, ref)
    return "" if kept.returncode else kept.stdout.strip()


def ranges(run: Pass, slug: str, head: str, kind: str) -> tuple[str, str] | None:
    """Return the two ranges of a scoped review that ends on `head`: the patch before it and
    the patch after. Each patch starts where its branch left the default branch.

    The patch before ends on one commit. For a rebase, that commit is the newest head the crew
    kept under `refs/jstack/pre-rebase/<slug>/`, which `jmerge` reads too: the crew's keep step
    writes the ref, and a `Rebase:` line an older brief has is read as no line. For a fix, it is
    the head the last `Scoped review: needed since` line names, the one the last review saw."""
    if kind == "fix":
        before = (_OWED.findall(task_brief(run, slug)) or [""])[-1]
    else:
        before = _kept(run, slug)
    default = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if not before or default.returncode:
        return None
    old, new = (run.run("git", "merge-base", default.stdout.strip(), to) for to in (before, head))
    if old.returncode or new.returncode:
        return None
    return f"{old.stdout.strip()}..{before}", f"{new.stdout.strip()}..{head}"


def _reviewing(run: Pass, client: Client, slug: str) -> bool | None:
    """Say whether a reviewer of the slug is at work, or return None where T3 Code did not
    say."""
    asked = {"projectId": run.project.project_id, "titleContains": REVIEW + slug, "limit": 100}
    try:
        found = client.call("t3_thread_list", asked).get("threads", [])
    except T3Error as error:
        run.say(f"wait {slug}: its reviewers could not be listed ({error})")
        return None
    mine = (t for t in found if re.fullmatch(re.escape(REVIEW + slug) + r"(,.*)?", t["title"]))
    return at_work(mine)


def _busy(run: Pass, client: Client, world: World, slug: str, row: Short) -> bool | None:
    """Say whether somebody is at work on what the row is short of: the crew, or a reviewer
    for a row that a review clears. Return None where T3 Code did not say."""
    if at_work(world.threads.get(slug, [])):
        return True
    return _reviewing(run, client, slug) if row.reviewed else False


def _capped(run: Pass, client: Client, slug: str) -> bool:
    """Say whether the crew's instance is capped, so the outbox holds the message to it."""
    return bool(outbox.capped(run, client, thread_of(run.home, slug)))


def told(run: Pass, pulls: merge.Said) -> set[int]:
    """Return the holds in hand in a pass that could not ask T3 Code or GitHub, and so has
    no crew to ask. They are the holds `tell` had in hand for the same reason when it last
    could ask. A hold `tell` never took on, or one that is the user's by now, stays the
    user's in such a pass. So the list gains and loses no hold just because one pass could
    not ask."""
    was: dict[str, Any] = read_json(run.state / FILE, {})
    asked = {
        (entry.get("number"), entry.get("reason"))
        for entry in was.values()
        if not entry.get("users")
    }
    said = (line for line in map(merge.parse, pulls) if line and line.word == "hold")
    return {line.number for line in said if short_of(line) and (line.number, line.reason) in asked}


def tell(run: Pass, client: Client, world: World, pulls: merge.Said) -> set[int]:
    """Tell each crew what its pull request has been short of for `AFTER` passes, once per
    reason and head. Send a stall for a crew that has made no progress after `PASSES` idle
    passes. Return the pull requests whose hold `tell` is dealing with. The user sees each of
    them as a `wait`. `tell` deals with a hold that stalled with nobody at work for that pass
    only. From the next pass on, the hold is the user's.
    """
    by_number = {pull["number"]: slug for slug, pull in world.open.items()}
    was: dict[str, Any] = read_json(run.state / FILE, {})
    kept: dict[str, Any] = dict(was) if pulls.failed else {}
    sent = run.box.sent()
    hand: set[int] = set()
    for text in pulls:
        said = merge.parse(text)
        row = short_of(said) if said else None
        if not said or not row:
            continue
        number, reason = said.number, said.reason
        slug = by_number.get(number, "")
        head = world.open[slug].get("headRefOid", "") if slug else ""
        if row.unless and row.unless(task_brief(run, slug), head):
            continue
        if not head or not dispatch.launched(run, slug):
            continue
        seen = was.get(slug, {})
        same = (seen.get("head"), seen.get("reason")) == (head, reason)
        entry = {**seen, "passes": seen["passes"] + 1} if same else {"passes": 1}
        entry |= {"head": head, "reason": reason, "number": number}
        kept[slug] = entry
        due = not entry.keys() & {"told", "users"} and entry["passes"] >= row.after
        if due and _capped(run, client, slug):
            entry["passes"] = row.after
        passes = entry["passes"]
        if due and rebase.mark(row.kind, slug, head) in sent:
            entry |= {"told": passes, "tells": 1}
            due = False
        asked = "told" in entry and not entry.get("users")
        busy = _busy(run, client, world, slug, row) if due or asked else None
        if asked and busy:
            entry["worked"] = True
        again = asked and entry.get("worked") and entry.get("tells", 1) < row.tells
        if (due or again) and busy is False:
            n = entry.get("tells", 0) + 1 if again else 1
            went = _tell(run, client, world, number, slug, row, entry, n)
            told = {"told": passes, "tells": n, "worked": False, "idle": 0}
            entry |= told if went == "told" else {"users": True} if went else {}
        if row.word == "hold" and due and "told" not in entry and passes >= LAPSE:
            run.say(
                f"wait {slug}: its crew was not told in {passes} passes, so the hold is the user's"
            )
            entry["users"] = True
        if entry.get("users"):
            continue
        if row.word == "hold":
            hand.add(number)
        since = passes - entry.get("told", passes)
        if since and busy is False:
            entry["idle"] = entry.get("idle", 0) + 1
        if entry.get("idle", 0) >= PASSES or since >= REVIEWING:
            thread = thread_of(run.home, slug) or "not known"
            work = ", with its crew or a reviewer at work" if busy else ""
            line = (
                f"{STALL} {slug}: #{number} is as short as it was {since} passes after its "
                f"crew was told{work}, at {head[:12]}, {reason}; its crew's thread is {thread}"
            )
            run.find(slug, STALL, line, key=f"{head[:12]} {row.kind}")
            if row.word == "hold" and busy is False and entry.get("idle", 0) >= PASSES:
                entry["users"] = True
    if kept != was:
        write_json(run.state / FILE, kept)
    return hand


def _tell(
    run: Pass,
    client: Client,
    world: World,
    number: int,
    slug: str,
    row: Short,
    entry: dict,
    n: int = 1,
) -> str:
    """Send the message that is due, the `n`th at the head, and return how it went: `told`,
    `users` for a hold no message can lift, or nothing when the next pass must try the message
    again. A message after the first goes under its own key, `<kind>|<slug>|<head 12>|<n>`."""
    head = entry["head"]
    sentence, sent = row.sentence, row.sends.replace("{slug}", slug)
    if row.kind in ("unruled", "fix", "rereview"):
        named = _RANGE_DIFF.search(entry["reason"]) if row.kind == "rereview" else None
        found = named.groups() if named else ranges(run, slug, head, row.kind)
        if not found and row.kind != "fix":
            run.say(f"wait {slug}: {NO_RANGE if row.word == 'hold' else NO_RANGES}")
            return "users"
        if found:
            sentence = sentence.replace("{old}", found[0]).replace("{new}", found[1])
            sent = sent.replace("{old}", found[0]).replace("{new}", found[1])
        else:
            sentence, sent = NO_FIX_RANGE, ""
    if row.rerun:
        sentence += " " + skills.where("template", RERUN).read_text().strip()
    if row.kind in ANSWERED:
        left = [one.id for one in findings.triage(task_brief(run, slug)).blocking()]
        sentence += f" The findings with no answer that counts: {', '.join(left)}." if left else ""
    if row.kind == "skills":
        owes = [
            f"`- {name}: {skills.owed(skills.resolve(name).name)}`"
            for name in skills.missing(task_brief(run, slug))
        ]
        sentence += f" The items it owes: {'; '.join(owes)}." if owes else ""
    message = MESSAGE.replace("{sentence}", sentence)
    ask = rebase.Ask(
        row.kind, "", "told what it is short of", message, no_thread=NO_THREAD, refused=REFUSED
    )
    window = str(n) if n > 1 else ""
    went = rebase.post(run, client, world, number, entry["reason"], ask, window)
    if not went:
        return ""
    line = f"{EXPEDITE} {slug}: told the crew what #{number} is short of ({row.kind}, {head[:12]})"
    line += f", sent `{sent}`" if sent else ""
    line += f", again at a new idle spell ({n} of {row.tells})" if n > 1 else ""
    run.find(slug, EXPEDITE, line, went[2], key=f"{row.kind} {head[:12]} {window}".strip())
    run.say(line)
    return "told"


def tells_left(was: dict[str, Any], slug: str, number: int, reason: str, head: str) -> int | None:
    """Return how many messages `tell` still owes the crew about a wait at the head, from
    `expedite.json` as `was` holds it, or None where `tell` does not own the wait: no row of
    `TABLE` is its reason, `tell` keeps no count of it at that head, or the wait is the user's."""
    row = short_of(merge.Line("wait", number, "", reason))
    entry = was.get(slug)
    if row is None or not isinstance(entry, dict) or entry.get("users"):
        return None
    if (entry.get("head"), entry.get("reason")) != (head, reason) or not head:
        return None
    return max(row.tells - entry.get("tells", 1 if "told" in entry else 0), 0)


def _step(half: Half) -> None:
    """Run `tell` where the pass could ask T3 Code and GitHub, and `told` where it could not."""
    world = half.seen.world
    if world is not None and half.client is not None:
        half.crews = tell(half.run, half.client, world, half.said)
    else:
        half.crews = told(half.run, half.said)


STEPS = (verbs.Step("after-expedite", 1, "expedite.tell", _step),)
