---- MODULE PrVerdict ----
\* Why a pull request is not merging: one pull request into main through jmerge's verdict, as
\* Repo.judged in features/jmerge/src/jmerge/cli.py gives it, in its order, and through the run
\* that acts on it: the merge, the guards on its tree merged over main's tip, the batch, and the
\* line each base keeps for GitHub's merge of the base into a pull request (IN_LINE).
\* The verdict as of main 21112eba8 (2026-11-10), and jbus's hold of a row whose check failed at two
\* heads as of main 8644c5324 (2026-11-11). Each condition names the file that checks it and quotes
\* the code there in backticks, with no line number: cli.py, ready.py, batch.py, rows.py and
\* treeguards.py are features/jmerge/src/jmerge/; expedite.py, rebase.py, outbox.py, poll.py and
\* stall.py are features/jbus/src/jbus/.
\* test_pr_verdict_spec.py finds each quote once in its file.
\*
\* Drop names one hold to take out, or "none". With a hold out the rule must break:
\* pr_canaries.py checks that it does, so the rule holds by no accident of the model.
EXTENDS Naturals

CONSTANT Drop
CONSTANT Moves          \* how many times other work moves main under the pull request
Kept(g) == Drop # g

\* The holds for your word a pull request may carry, each asked of you and lifted only by you.
\*   "over":     its queue row is over, done or merged, with the pull request open: the hold says
\*               your accept lifts it, and today none does (Repo.judged passes no queue wait
\*               through Repo.lift).
\*   "nogo":     its queue row has no go, or is held: you approve it (jbus queue approve).
\*   "touches":  it touches a protected path: your accept lifts it at its head.
\*   "declines": its rebase dropped lines, or its crew declined a finding, the review did not
\*               uphold: your accept lifts it at its head.
\*   "mergeoff": the repo's merge-off switch is on: you turn merging on again.
Holds == {"over", "nogo", "touches", "declines", "mergeoff"}
Accepted == {"touches", "declines"}

\* The verdicts that wait on your word (verb `hold`), and those on the crew.
HoldWords == {"row-over", "row-held", "declines", "touches", "merge-off"}
CrewWords == {"check-failed", "conflicts", "merged-tree-fails"}

\* st: "open" or "merged".
\* good: the change passes its check on its own; a crew's fix may make it so, or fail again.
\* ci: the required check at its head: "none" (not ended), "pass" or "fail".
\* reviewed: its review round holds at its head (no Review: line short, findings handled, the
\*   brief met). A crew's push of new content needs a scoped review again.
\* asks: the holds for your word it carries now.
\* moved: main changed a path since its check started. overlap: its files share one of them.
\* clash: it conflicts with main's tip. tipFails: its tree merged over main's tip fails a test
\*   (the guards, CI's check of the batch, and its check after a merge of main all see it).
\* guardsSaid: jmerge kept a record that the guards failed on its head over this tip.
\* decided: GitHub has decided whether it merges cleanly.
\* mainRed: main's check failed and jbus's revert or fix row has not landed yet.
\* ahead: the pull request at the head of main's line, if any: "none", "other" (waiting on GitHub
\*   or its check, it merges by itself) or "held" (waiting on its crew or its user).
\* batch: "none", "pending" (a member of jmerge's batch with other pull requests, whose check
\*   runs), or "failed" (a member of a failed batch at this head).
\* guards: the repo names fast guards (treeguards). batchOn: the merge-batch switch is on.
\* said: jmerge's last verdict. fresh: that verdict was given at this head.
\* unheld: the holds still outstanding when it merged, not lifted by your word at its head.
\* fails: the heads at which its check failed on a change of its own, as jbus counts them, up to
\*   Limit, where jbus holds its row.
\* held: jbus held its row for a check that failed at Limit heads, keeping the go it took.
VARIABLES st, good, ci, reviewed, asks, moved, overlap, clash, tipFails, guardsSaid, decided,
    mainRed, movesLeft, ahead, batch, guards, batchOn, said, fresh, unheld, fails, held
vars == <<st, good, ci, reviewed, asks, moved, overlap, clash, tipFails, guardsSaid, decided,
    mainRed, movesLeft, ahead, batch, guards, batchOn, said, fresh, unheld, fails, held>>

Main == <<moved, overlap, clash, tipFails, guardsSaid, decided, mainRed, movesLeft>>
Setup == <<guards, batchOn>>

\* jbus holds a row at the second head at which its check failed (stall.py `if len(heads) < 2:`).
Limit == 2

\* The holds for your word it carries, jbus's hold among them: a held row is "nogo" to jmerge.
Asks == IF held THEN asks \cup {"nogo"} ELSE asks

Init ==
    /\ st = "open"
    /\ good \in BOOLEAN
    /\ ci = "none"
    /\ reviewed = FALSE
    /\ asks \in SUBSET Holds
    /\ moved = FALSE /\ overlap = FALSE /\ clash = FALSE /\ tipFails = FALSE
    /\ guardsSaid = FALSE
    /\ decided = TRUE
    /\ mainRed = FALSE
    /\ movesLeft = Moves
    /\ ahead \in {"none", "other", "held"}
    /\ batch = "none"
    /\ guards \in BOOLEAN
    /\ batchOn \in BOOLEAN
    /\ said = "none"
    /\ fresh = FALSE
    /\ unheld = {}
    /\ fails = 0
    /\ held = FALSE

\* ---- jmerge's verdict, in the order Repo.judged checks it

\* Repo.in_turn: GitHub's merge of main into it waits behind the pull request at the head of
\* main's line (cli.py `if ahead != one.number:`, cli.py
\* `return ready.IN_LINE.format(number=ahead, base=one.base)`), and is asked once it is its turn.
InTurn(asked) == IF ahead # "none" THEN "in-line" ELSE asked

\* A failed check is judged again as if it had passed, where it is all GitHub holds against it and
\* it merges cleanly (cli.py `held = ready.red_only(one) or ready.unrun_only(one)`, ready.py
\* `return bool(one.waiting) and one.waiting == one.failed and one.mergeable == "MERGEABLE"`,
\* cli.py `return self.judged(replace(one, waiting=(), unrun=()), default, found.why)`).
Rejudged == Kept("rejudge") /\ decided /\ ~clash

\* Repo.again: the check failed; where main moved since it started and main is not red, GitHub
\* merges main into it in its turn, and its check there decides (cli.py `or not moved[1]`,
\* cli.py `or (one.base == self.trunk and bool(self.main_state.red))`, cli.py
\* `return self.in_turn(one, moved[0], ready.BASE_MERGE_ASKED, ready.BASE_MERGE_DUE)`).
\* Otherwise the failure is its own (cli.py `return red`).
Again ==
    IF Kept("again") /\ moved /\ ~mainRed THEN InTurn("base-merge-asked") ELSE "check-failed"

\* Repo.over_main and the guards record after it: "ready" merges alone, "ready-batch" joins the
\* batch, and anything else is a wait.
\*   - main changed no path since its check started: it merges on its check (cli.py `if not paths:`).
\*   - the batch takes it: the switch is on, main is not red at the run's start (cli.py
\*     `if not check and (state / batch.SWITCH).exists() and default and not repo.main_state.red:`),
\*     and no batch it was in failed at this head (cli.py
\*     `if self.batching is not None and self.batching.takes(one, self.trunk, self.is_revert(one)):`,
\*     batch.py `failed = self.record.failed.get(str(one.number)) == one.head`,
\*     batch.py `return not revert and bool(default) and one.base == default and not failed`).
\*   - its files miss main's changes: it merges on its check, with the guards first
\*     (cli.py `if not overlaps:`), unless the guards already failed at this head over this tip
\*     (cli.py `short = short or ("" if judged.batch else self.guards.kept(one, judged.tip))`).
\*   - it overlaps them, in a repo with no guards, or where they failed here: GitHub merges main
\*     into it in its turn (cli.py
\*     `if not self.guards.command or self.is_revert(one) or self.guards.kept(one, tip):`,
\*     cli.py `return self.base_moved(one, tip), ready.Judged()`), and else it merges on the guards
\*     (cli.py `return "", ready.Judged(tip, overlaps=True)`).
OverMain ==
    IF ~moved THEN "ready"
    ELSE IF batchOn /\ ~mainRed /\ (batch # "failed" \/ ~Kept("batch-failed")) THEN "ready-batch"
    ELSE IF ~overlap THEN (IF guardsSaid THEN "merged-tree-fails" ELSE "ready")
    ELSE IF ~guards \/ guardsSaid THEN InTurn("base-moved-asked")
    ELSE "ready"

Verdict ==
    \* Its review: no round, findings not handled, a fix not reviewed, the brief not met
    \* (cli.py `short = self.lift(ready.short_of(text, one.head, heard, proven), lifted)`).
    IF ~reviewed THEN "no-review"
    \* GitHub's waits (cli.py `short = short or ("" if undecided or beside else github)`): the
    \* check not ended (ready.py `return (CHECK_FAILED if failed else NOT_PASSED).format(check=one.waiting[0])`),
    \* failed and not judged again, or a conflict with its base (ready.py
    \* `if one.mergeable == "CONFLICTING":`). An undecided GitHub is said last, and a check that
    \* can still pass after the review's range-diff (cli.py
    \* `short = short or self.row_first(brief.stem, beside)`), as `reviewed` already is here.
    \* GitHub runs no check on a pull request that conflicts with its base, so a check not ended
    \* at a conflicting head is one with no run, said as the conflict (#1721, ready.py
    \* `return CONFLICTS if one.mergeable == "CONFLICTING" else unrun`).
    ELSE IF ci = "none" /\ decided /\ clash THEN "conflicts"
    ELSE IF ci = "none" THEN "not-passed"
    ELSE IF ci = "fail" /\ ~Rejudged THEN "check-failed"
    ELSE IF decided /\ clash THEN "conflicts"
    \* Its queue row: over (rows.py `return ready.ROW_OVER.format(status=row["status"])`), then its
    \* go (cli.py `rows.short(self.queue, brief.stem, brief=self.stored(brief.stem))`,
    \* rows.py `if row.get("held"):`, rows.py `if row and not judgement.has_go(row, brief):`).
    ELSE IF "nogo" \in Asks /\ Kept("go") THEN "row-held"
    \* A drop or a decline the review did not uphold (cli.py
    \* `kind, why = ready.drops(lost, text, one.head, user=self.user, command=command)`, cli.py
    \* `kind, why = ready.declines(text, user=self.user)`, cli.py
    \* `return Judgement(brief.stem, kind, why, note, None)`).
    ELSE IF "declines" \in asks /\ Kept("declines") THEN "declines"
    \* A protected path (cli.py
    \* `hold = self.lift(ready.needs_the_user(one, self.protected, left, user=self.user), lifted)`,
    \* cli.py `return Judgement(brief.stem, "hold", hold, note, None)`).
    ELSE IF "touches" \in asks /\ Kept("touches") THEN "touches"
    \* The check that failed, judged over today's main
    \* (cli.py `return Judgement(brief.stem, "wait", self.again(one, red), note, None)`).
    ELSE IF ci = "fail" THEN Again
    \* (cli.py `return Judgement(brief.stem, "wait", ready.UNDECIDED, note, None)`)
    ELSE IF ~decided THEN "undecided"
    ELSE IF OverMain # "ready" /\ OverMain # "ready-batch" THEN OverMain
    \* The merge-off switch (cli.py
    \* `brief.stem, judgement.verb(ready.MERGE_OFF), ready.MERGE_OFF, note, None`).
    ELSE IF "mergeoff" \in asks /\ Kept("mergeoff") THEN "merge-off"
    ELSE OverMain

\* What your accept judges: every hold it lifts lifted, at the head it is given at
\* (cli.py `return ready.codes() if self.accepted == (one.number, one.head) else frozenset()`).
\* A queue wait is not passed through Repo.lift, so a row that is over still holds it.
VerdictAccepted ==
    LET a == Asks \ Accepted IN
    IF ~reviewed THEN "no-review"
    ELSE IF ci = "none" /\ decided /\ clash THEN "conflicts"
    ELSE IF ci = "none" THEN "not-passed"
    ELSE IF ci = "fail" /\ ~Rejudged THEN "check-failed"
    ELSE IF decided /\ clash THEN "conflicts"
    ELSE IF "over" \in asks /\ Kept("over") THEN "row-over"
    ELSE IF "nogo" \in a /\ Kept("go") THEN "row-held"
    ELSE IF ci = "fail" THEN Again
    ELSE IF ~decided THEN "undecided"
    ELSE IF OverMain # "ready" /\ OverMain # "ready-batch" THEN OverMain
    ELSE IF "mergeoff" \in a /\ Kept("mergeoff") THEN "merge-off"
    ELSE "ready"

\* ---- jmerge's run (cli.py `for one in repo.line_up(listed, default):`)

Open == st = "open"

\* It waits or is held, and says why.
Judge ==
    /\ Open
    /\ Verdict \notin {"ready", "ready-batch"}
    /\ said # Verdict \/ ~fresh
    /\ said' = Verdict /\ fresh' = TRUE
    /\ UNCHANGED <<st, good, ci, reviewed, asks, Main, ahead, batch, Setup, unheld, fails, held>>

\* Merged alone (cli.py `say(repo.merge(one, found.slug, found.note, found.judged))`), on the guards
\* over the tip where main moved past its check, which pass (cli.py
\* `guarded, passed = self.guards.of(one, tip)`): merges every hold left records nothing.
Merge ==
    /\ Open
    /\ Verdict = "ready"
    /\ ~(guards /\ moved /\ tipFails)
    /\ st' = "merged" /\ unheld' = Asks /\ said' = "merged"
    /\ UNCHANGED <<good, ci, reviewed, asks, Main, ahead, batch, Setup, fresh, fails, held>>

\* The guards fail on its tree over the tip (treeguards.py
\* `said = ready.MERGED_TREE_FAILS.format(**values, guard=guard(ran.said))`): it waits for its
\* crew, or, where it overlaps main's changes, for GitHub's merge of main in its turn (cli.py
\* `if guarded and judged.overlaps and self.guards.kept(one, tip):`).
GuardsFail ==
    /\ Open
    /\ Verdict = "ready"
    /\ guards /\ moved /\ tipFails
    /\ guardsSaid' = TRUE
    /\ said' = IF overlap THEN InTurn("base-moved-asked") ELSE "merged-tree-fails"
    /\ fresh' = TRUE
    /\ UNCHANGED <<st, good, ci, reviewed, asks, moved, overlap, clash, tipFails, decided,
        mainRed, movesLeft, ahead, batch, Setup, unheld, fails, held>>

\* A member the run judged with no other goes the single path in that run (batch.py
\* `return GUARDS if size >= GUARDS_LEAST else ""`, cli.py
\* `self.merge(one, slug, note, replace(found, batch=False))`): the guards on its tree over the tip,
\* where the repo names them, and it merges, or they fail as in GuardsFail. Whether other members
\* are judged in the same run is the world's, so the step has no fairness: a run may batch it.
Alone ==
    /\ Open
    /\ Verdict = "ready-batch"
    /\ IF guards /\ tipFails
       THEN /\ guardsSaid' = TRUE
            /\ said' = IF overlap THEN InTurn("base-moved-asked") ELSE "merged-tree-fails"
            /\ fresh' = TRUE
            /\ UNCHANGED <<st, unheld>>
       ELSE /\ st' = "merged" /\ unheld' = asks /\ said' = "merged"
            /\ UNCHANGED <<guardsSaid, fresh>>
    /\ UNCHANGED <<good, ci, reviewed, asks, moved, overlap, clash, tipFails, decided, mainRed,
        movesLeft, ahead, batch, Setup>>

\* Judged with other members, it joins their batch (cli.py
\* `elif on is not None and found.judged.batch:`): a guards batch of two to four, proven in the
\* run, or CI's batch of five or more, proven across runs. It waits on the batch's check.
JoinBatch ==
    /\ Open
    /\ Verdict = "ready-batch"
    /\ batch # "pending"
    /\ batch' = "pending" /\ said' = "in-batch" /\ fresh' = TRUE
    /\ UNCHANGED <<st, good, ci, reviewed, asks, Main, ahead, Setup, unheld, fails, held>>

\* CI's check of the batch passes, main's tip has not moved since it was built (cli.py
\* `elif stop is None and self.tip_of(default) != expected:`), and jmerge merges it.
BatchProves ==
    /\ Open
    /\ batch = "pending" /\ ~tipFails
    /\ st' = "merged" /\ unheld' = Asks /\ said' = "merged" /\ batch' = "none"
    /\ UNCHANGED <<good, ci, reviewed, asks, Main, ahead, Setup, fresh, fails, held>>

\* The batch's check fails: a guards batch puts each member's head under failed (cli.py
\* `on.record.alone(made.members)`), as does a CI batch narrowed to a half under five (batch.py
\* `def alone(`), and it goes the single path at this head.
BatchFails ==
    /\ Open
    /\ batch = "pending" /\ tipFails
    /\ batch' = "failed"
    /\ UNCHANGED <<st, good, ci, reviewed, asks, Main, ahead, Setup, said, fresh, unheld, fails, held>>

\* The line's holder waits on its crew or its user, so jmerge gives the line to the next (cli.py
\* `if self.line.get(one.base) == one.number and not in_line(one, found):`).
Release ==
    /\ ahead = "held" /\ Kept("release")
    /\ ahead' = "none"
    /\ UNCHANGED <<st, good, ci, reviewed, asks, Main, batch, Setup, said, fresh, unheld, fails, held>>

\* ---- the crew, the reviewer, GitHub and main

\* A new head: GitHub's merge of main into it, or a push of its crew.
NewHead ==
    /\ ci' = "none" /\ guardsSaid' = FALSE /\ decided' = FALSE /\ fresh' = FALSE
    /\ batch' = IF batch = "failed" THEN "none" ELSE batch

\* The reviewer's round on what its crew pushed.
Review ==
    /\ Open /\ ~reviewed
    /\ reviewed' = TRUE
    /\ UNCHANGED <<st, good, ci, asks, Main, ahead, batch, Setup, said, fresh, unheld, fails, held>>

\* Its check ends: it fails on a change of its own, or over a red main. jbus counts a head that
\* failed on its own, and not one whose check ran on a red main (stall.py `if check == "failed":`),
\* nor any while jbus holds its row (stall.py
\* `if row.get("held") or any(head in seen for seen in (heads, on_red, flakes, infras)):`).
CheckEnds ==
    /\ Open /\ ci = "none"
    /\ ci' = IF good /\ ~mainRed THEN "pass" ELSE "fail"
    /\ fails' = IF ~good /\ ~mainRed /\ ~held /\ fails < Limit THEN fails + 1 ELSE fails
    /\ UNCHANGED <<st, good, reviewed, asks, Main, ahead, batch, Setup, said, fresh, unheld, held>>

\* At Limit, jbus holds the row and pages you, once, with the gate `check failed twice` (stall.py
\* `said = queue.hold(run.state, slug, keep=True)`, stall.py `run.gate(slug, TWICE, text,`).
Twice ==
    /\ Open /\ fails = Limit /\ ~held /\ Kept("twice")
    /\ held' = TRUE
    /\ UNCHANGED <<st, good, ci, reviewed, asks, Main, ahead, batch, Setup, said, fresh, unheld, fails>>

\* Its check passes at a head while jbus's hold stands: jbus lifts its own hold, puts back the go
\* it took (stall.py `if ready.waiting(pull.get("statusCheckRollup") or [], required):`, stall.py
\* `said = queue.lift(run.state, slug)`), and the count starts again.
Lift ==
    /\ Open /\ held /\ ci = "pass"
    /\ held' = FALSE /\ fails' = 0
    /\ UNCHANGED <<st, good, ci, reviewed, asks, Main, ahead, batch, Setup, said, fresh, unheld>>

\* jbus tells its crew of a conflict GitHub sees, whatever jmerge's verdict says (rebase.py
\* `if pull.get("mergeable") == "CONFLICTING" and not told and not stacks.unmoved(brief):`), and
\* of a failed check or guards that failed over main's tip (expedite.py
\* `ready.CHECK_FAILED.code: "jbus.rebase tells the crew of the failed check, once per head",`,
\* expedite.py `ready.MERGED_TREE_FAILS,`). The crew rebases onto main's tip and fixes its change,
\* which needs a scoped review, and which may fail its check again. A check that failed only over
\* main's red is no fault of its own, and the crew leaves it (features/crew/the-checks.md). While
\* jbus holds its row the outbox sends its crew no rebase and no fix (outbox.py
\* `Rule("held", on_hold, frozenset(), FIXES),`), and jbus holds a row in the pass that counts its
\* Limit-th failed head before it tells the crew of it: twice is a teller (stall.py
\* `verbs.Step("tellers", 90, "stall.twice", _twice, ("world",)),`), the failed check's message is
\* rebase.py `"rebase.github",` after expedite, and a pass runs the tellers first (poll.py
\* `steps(half, "tellers")`, poll.py `steps(half, "after-expedite")`).
CrewFix ==
    /\ Open /\ ~held /\ (fails < Limit \/ ~Kept("twice"))
    /\ \/ decided /\ clash
       \/ said = Verdict /\ fresh /\ said = "merged-tree-fails"
       \/ said = Verdict /\ fresh /\ said = "check-failed" /\ ~good
    /\ good' \in BOOLEAN /\ reviewed' = FALSE
    /\ moved' = FALSE /\ overlap' = FALSE /\ clash' = FALSE /\ tipFails' = FALSE
    /\ NewHead
    /\ UNCHANGED <<st, asks, mainRed, movesLeft, ahead, Setup, said, unheld, fails, held>>

\* GitHub merges main into it, as jmerge asked: a merged tree that fails a test fails its check.
GitHubMergesBase ==
    /\ Open /\ said = Verdict /\ fresh
    /\ said \in {"base-moved-asked", "base-merge-asked"}
    /\ good' = (good /\ ~tipFails)
    /\ moved' = FALSE /\ overlap' = FALSE /\ tipFails' = FALSE
    /\ NewHead
    /\ UNCHANGED <<st, reviewed, asks, clash, mainRed, movesLeft, ahead, Setup, said, unheld, fails, held>>

GitHubDecides ==
    /\ Open /\ ~decided
    /\ decided' = TRUE
    /\ UNCHANGED <<st, good, ci, reviewed, asks, moved, overlap, clash, tipFails, guardsSaid,
        mainRed, movesLeft, ahead, batch, Setup, said, fresh, unheld, fails, held>>

\* Main moves under it: a pull request's merge may touch its files, clash with it, break its tree
\* merged over the tip, and turn main red. A batch whose tip moved stops.
MovesMain(red) ==
    /\ moved' = TRUE
    /\ overlap' \in {overlap, TRUE}
    /\ clash' \in IF overlap' THEN {clash, TRUE} ELSE {clash}
    /\ tipFails' \in {tipFails, TRUE}
    /\ guardsSaid' = FALSE /\ decided' = FALSE
    /\ mainRed' \in IF red THEN {mainRed, TRUE} ELSE {mainRed}
    /\ batch' = IF batch = "pending" THEN "none" ELSE batch

MainMoves ==
    /\ Open /\ movesLeft > 0
    /\ movesLeft' = movesLeft - 1
    /\ MovesMain(TRUE)
    /\ UNCHANGED <<st, good, ci, reviewed, asks, ahead, Setup, said, fresh, unheld, fails, held>>

\* jbus's revert or main's fix row lands, and main is green.
MainFixed ==
    /\ Open /\ mainRed
    /\ mainRed' = FALSE /\ moved' = TRUE /\ guardsSaid' = FALSE /\ decided' = FALSE
    /\ batch' = IF batch = "pending" THEN "none" ELSE batch
    /\ UNCHANGED <<st, good, ci, reviewed, asks, overlap, clash, tipFails, movesLeft, ahead,
        Setup, said, fresh, unheld, fails, held>>

\* The pull request at the head of the line merges.
OtherMerges ==
    /\ Open /\ ahead = "other"
    /\ ahead' = "none"
    /\ MovesMain(FALSE)
    /\ UNCHANGED <<st, good, ci, reviewed, asks, movesLeft, Setup, said, fresh, unheld, fails, held>>

\* ---- your word

\* You approve its row (rows.py `if row and not judgement.has_go(row, brief):`), as jmerge asks or
\* as jbus's hold pages you, and where jbus held it, the count starts again (stall.py
\* `if one.get("held_at") and not row.get("held"):`): held_at is set by that hold alone.
Approve ==
    /\ Open /\ (said = "row-held" \/ held)
    /\ asks' = asks \ {"nogo"} /\ held' = FALSE
    /\ fails' = IF held THEN 0 ELSE fails
    /\ UNCHANGED <<st, good, ci, reviewed, Main, ahead, batch, Setup, said, fresh, unheld>>

\* You turn merging on again.
MergeOn ==
    /\ Open /\ said = "merge-off"
    /\ asks' = asks \ {"mergeoff"}
    /\ UNCHANGED <<st, good, ci, reviewed, Main, ahead, batch, Setup, said, fresh, unheld, fails, held>>

\* jmerge --accept, on a hold jmerge said at this head (cli.py
\* `if not waived and not heard and was != one.head:`): every hold your accept lifts is lifted,
\* and it merges where nothing else holds it. Your word covers the head it was given at.
Accept ==
    /\ Open /\ said \in HoldWords
    /\ fresh \/ ~Kept("head")
    /\ VerdictAccepted = "ready"
    /\ ~(guards /\ moved /\ tipFails)
    /\ st' = "merged" /\ said' = "merged"
    /\ unheld' = IF fresh THEN Asks \ Accepted ELSE Asks
    /\ UNCHANGED <<good, ci, reviewed, asks, Main, ahead, batch, Setup, fresh, fails, held>>

\* You accept the pull request that holds the line, and it merges.
AcceptOther ==
    /\ Open /\ ahead = "held"
    /\ ahead' = "none"
    /\ MovesMain(FALSE)
    /\ UNCHANGED <<st, good, ci, reviewed, asks, movesLeft, Setup, said, fresh, unheld, fails, held>>

\* ---- the spec

\* What happens by itself: jmerge's run, the crew and its reviewer, GitHub, jbus's hold of a row
\* whose check failed twice, and jbus's fix of main.
System ==
    \/ Judge \/ Merge \/ GuardsFail \/ JoinBatch \/ BatchProves \/ BatchFails \/ Release
    \/ Review \/ CheckEnds \/ Twice \/ Lift \/ CrewFix \/ GitHubMergesBase \/ GitHubDecides
    \/ MainFixed \/ OtherMerges
YourWord == Approve \/ MergeOn \/ Accept \/ AcceptOther
Next == System \/ MainMoves \/ YourWord

\* Each step that happens by itself happens once it can, but Alone, which needs a run that judged
\* no other member; your word has no fairness.
Fairness ==
    /\ WF_vars(Judge) /\ WF_vars(Merge) /\ WF_vars(GuardsFail) /\ WF_vars(JoinBatch)
    /\ WF_vars(BatchProves) /\ WF_vars(BatchFails) /\ WF_vars(Release)
    /\ WF_vars(Review) /\ WF_vars(CheckEnds) /\ WF_vars(Twice) /\ WF_vars(Lift)
    /\ WF_vars(CrewFix) /\ WF_vars(GitHubMergesBase) /\ WF_vars(GitHubDecides)
    /\ WF_vars(MainFixed) /\ WF_vars(OtherMerges)

Spec == Init /\ [][Next]_vars /\ Fairness

Settled == ~ENABLED System

TypeOK ==
    /\ st \in {"open", "merged"}
    /\ good \in BOOLEAN /\ reviewed \in BOOLEAN
    /\ ci \in {"none", "pass", "fail"}
    /\ asks \subseteq Holds /\ unheld \subseteq Holds
    /\ ahead \in {"none", "other", "held"}
    /\ batch \in {"none", "pending", "failed"}
    /\ movesLeft \in 0..Moves
    /\ fails \in 0..Limit /\ held \in BOOLEAN
    /\ held => fails = Limit

\* It waits on your word: jmerge holds it for you, or jbus held its row and paged you, which your
\* approve lifts, whatever jmerge says of it.
WaitsOnYou == Open /\ (Verdict \in HoldWords \/ held)

\* "Every open pull request merges or waits on the user's word."
\* It merges with no hold of yours outstanding but those your word lifted at its head, and while
\* open it goes on to merge or to wait on your word: no path waits for ever on its crew, its
\* reviewer, GitHub, a check or jmerge.
MergesOnlyOnYourWord == st = "merged" => unheld = {}
MergesOrWaitsOnYou == [](MergesOnlyOnYourWord) /\ (Open ~> (st = "merged" \/ WaitsOnYou))
====
