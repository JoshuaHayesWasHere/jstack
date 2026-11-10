---- MODULE FlowToday ----
\* What jstack does today with two pull requests, a main that can go red, and a machine that can fill.
\* Code as of main 21112eba8 (2026-11-10). It began as the flow-statechart scout's FlowNow.tla of main
\* 6485914, cut down to the variables FlowDesign.tla's four rules read, and README.md keeps what each
\* pull request since added to it: main's fix row and its revert, a row's go and your word, the
\* stack, the review round before the pull request, and a green pull request main moved past.
\* Since st-flow it has jmerge's batch (#1564, #1580, #1613), the line GitHub's merges of main into a
\* branch wait in (#1009, #1012, #1044), and jmerge's run off jbus's pass (#1616). How main's red is
\* rerun, judged, reverted and closed moved out to features/jbus/spec/MainRed.tla: here a red main is
\* judged in one step, to a revert or a fix row, as that spec's chart draws.
EXTENDS Naturals, FiniteSets

\* Gap: what jbus.strays stops of what a finished turn left running.
\*   "turn":  the code since #427: a crew's process, busy or idle, once the turn that left it ended.
\*   "ended": the code from #416 to #427: a busy process, and an idle one once its row ended
\*            (merged, done, left, or its worktree gone); in this model a row ends by merging.
\*   "busy":  the code before #416 (main 6485914): only a process that used CPU over the pass,
\*            so an idle one (a `sleep`, a headless browser waiting) is left for ever.
CONSTANT Gap

PRs == {"a", "b"}

\* st: "queued" (a row with your go, not launched yet), "open" (its pull request) or "merged".
\* link: how b is ordered after a. "depends" when b's brief builds on a (its Builds on: line names
\*   a), "after" when the order is only about merging (merge_after), and "none" once an edit of
\*   b's brief took a out of its Builds on: line.
\* on: what a pull request sits on, "main" or the other one (its brief's `Stacked on:` line, #411).
\* missed[p]: p's last check passed without running a test its change breaks: the selection
\*   missed it.
\* moved[p]: main moved after p's check started (jmerge's `over_main` finds the paths main
\*   changed since). A pull request on a stack has a base of its own, which main's moves leave.
\* fixes[p]: p's head carries main's fix, which the main-red row's crew put there and not in a pull
\*   request of its own.
\* brBreaks[p]: the change breaks a browser test. brFail[p]: its own browser run failed.
\* viewBroken: main's code fails a browser test. brHold: main's last browser run failed and the
\*   browser-red row jbus filed for it is open (rows.main_browser_red with browser_fixing), which
\*   holds as main's red a pull request whose own browser run failed.
\* go[p]: p's row has your go: approved, for the brief as it stands, and not held. You give it
\*   (Approve) and take it back (HoldRow), and jbus launches and jmerge merges only a row that has it.
\* needs[p]: p's change waits on your word, as one that touches a protected path does, and only
\*   your word (jmerge --accept, Accept) merges it.
\* meets[p]: p's last review round says the brief is met (its Meets the brief: line, #843). At most
\*   one round in a run says it is not.
\* busy: a process a finished turn left that uses CPU. idle[p]: one p's crew left that uses none
\*   but holds memory. full is TRUE exactly when one of them is left: TLC takes the worst case,
\*   where what is left is what tips jgauge room over.
\* mainRed: main's push run is red (main.json's red). redBy: what made it, "flake" (something
\*   outside that its one rerun passes), "outside" (something outside that stays), "merge" (one
\*   merge since the last green) or "many" (a merge that broke more on a red tip, so no one merge
\*   is its culprit). mend: what is under way to end it, "judging" (jbus reruns its push run once
\*   and judges the red tip), "revert" (jbus's revert of the one clear culprit is open), "row"
\*   (main's fix row is filed), or "none". MainRed.tla has each of these as the code does.
\* batch: the members of jmerge's batch out (batch.json's `batch`), checked by CI on one draft pull
\*   request. suspects: the members of a failed batch of two, of which the next batch is the first
\*   half (`suspects`). alone: each pull request a failed batch of one sent down the single path at
\*   its head (`failed`).
\* line: the pull request that holds main's line (base-merges.json's `line`): only it is given
\*   GitHub's merge of main into its branch, and each other that needs one waits in line behind it.
\* heard: jbus's pass has read every line the last run of jmerge printed about a failed check, a
\*   browser run or a review round, which the pass tells the crew of. Since #1616 jmerge runs off the
\*   pass, so what it said reaches the pass's tellers a pass late.
\* editsLeft: the edits still to come of b's brief that take a out of its Builds on: line, once.
VARIABLES st, ci, missed, breaks, mainRed, redBy, mend, outsideLeft, full, link, on, busy, idle,
    moved, fixes, brBreaks, brFail, viewBroken, brHold, go, needs, meets,
    batch, suspects, alone, line, heard, editsLeft
vars == <<st, ci, missed, breaks, mainRed, redBy, mend, outsideLeft, full, link, on, busy, idle,
    moved, fixes, brBreaks, brFail, viewBroken, brHold, go, needs, meets,
    batch, suspects, alone, line, heard, editsLeft>>

Init ==
    /\ st = [p \in PRs |-> "queued"]
    /\ ci = [p \in PRs |-> "none"]
    /\ missed = [p \in PRs |-> FALSE]
    /\ breaks \in [PRs -> BOOLEAN]          \* the change breaks a test that reads the whole tree
    /\ mainRed = FALSE
    /\ redBy = "none"
    /\ mend = "none"
    /\ outsideLeft = 1
    /\ full = FALSE
    /\ link \in {"depends", "after"}
    /\ on = [p \in PRs |-> "main"]
    /\ busy = FALSE
    /\ idle = [p \in PRs |-> FALSE]
    /\ moved = [p \in PRs |-> FALSE]
    /\ fixes = [p \in PRs |-> FALSE]
    /\ brBreaks \in [PRs -> BOOLEAN]
    /\ brFail = [p \in PRs |-> FALSE]
    /\ viewBroken = FALSE
    /\ brHold = FALSE
    /\ go = [p \in PRs |-> TRUE]
    /\ needs \in [PRs -> BOOLEAN]
    /\ meets \in {[p \in PRs |-> TRUE]} \cup {[p \in PRs |-> p # q] : q \in PRs}
    /\ batch = {}
    /\ suspects = {}
    /\ alone = {}
    /\ line = "none"
    /\ heard = TRUE
    /\ editsLeft = 1

Machine == <<full, busy, idle>>
Fix == <<fixes>>
Browser == <<brBreaks, brFail, viewBroken, brHold>>
Row == <<go, needs, meets>>
Main == <<mainRed, redBy, mend>>
Queue == <<batch, suspects, alone, line>>
NoFix == [p \in PRs |-> FALSE]

\* Main is red: its check failed, or its browser run failed while that run's fix is open.
Red == mainRed \/ brHold

\* A turn of p's crew ends, and may leave a process running: busy, idle, or none.
Leaves(p) ==
    \E kind \in {"none", "busy", "idle"} :
        /\ busy' = (busy \/ kind = "busy")
        /\ idle' = [idle EXCEPT ![p] = idle[p] \/ kind = "idle"]
        /\ full' = (busy' \/ \E x \in PRs : idle'[x])

\* p's head moved (its crew pushed, or GitHub merged main into it): jmerge's batch record keeps no
\* suspect and no failed member at a head that moved, and its new check has not started.
NewHead(p) ==
    /\ suspects' = suspects \ {p}           \* features/jmerge/src/jmerge/batch.py `self.suspects = tuple(m for m in self.suspects if heads.get(str(m.number)) == m.head)`
    /\ alone' = alone \ {p}                 \* features/jmerge/src/jmerge/batch.py `self.failed = {n: head for n, head in self.failed.items() if heads.get(n) == head}`
    /\ moved' = [moved EXCEPT ![p] = FALSE]

\* Main's tip moved: each open pull request on main whose check started is now one main moved past,
\* and a batch out over the old tip is stale (`batch.state_of` gives NONE), so the next run builds
\* it again over the new tip.
MainMoves ==
    /\ moved' = [q \in PRs |-> st'[q] = "open" /\ on'[q] = "main" /\ (moved[q] \/ ci[q] # "none")]
    /\ batch' = {}                          \* features/jmerge/src/jmerge/batch.py `if batch is None or tip != batch.tip or pull is None or pull.head != batch.commit:`

\* A jbus pass launches the row's crew, which opens its pull request, and its turn ends.
Launch(p) ==
    /\ st[p] = "queued"
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ go[p]                                \* features/jbus/src/jbus/dispatch.py `if not row.get("approved"):`
    \* A row that builds on an open one launches stacked on its branch (#411), and one that builds
    \* on a row with no pull request yet waits; merge_after is read only by jmerge.
    /\ (p = "b" /\ link = "depends") => st["a"] # "queued"   \* features/jbus/src/jbus/dispatch.py `on = world.stack_on(run, unmerged, brief)`
    /\ st' = [st EXCEPT ![p] = "open"]
    /\ on' = [on EXCEPT ![p] = IF p = "b" /\ link = "depends" /\ st["a"] = "open" THEN "a" ELSE "main"]
    \* Its crew proves it at the desk, jbus launches its one review round, and its crew opens it
    \* ready after that round, so its check runs after its review. A round that says the brief is
    \* not met is a line of jmerge's that the pass reads a pass late.
    \* features/jbus/src/jbus/prereview.py `short = proved(run, brief, head)`
    /\ heard' = (heard /\ meets[p])
    /\ Leaves(p)
    /\ UNCHANGED <<ci, missed, breaks, Main, outsideLeft, link, moved, Fix, Browser,
                   go, needs, meets, Queue, editsLeft>>

\* GitHub runs the pull request's check over the base as it is now: main, or since #868 the
\* branch of the open pull request it is stacked on.
Check(p) ==
    /\ st[p] = "open"                       \* .github/workflows/check.yml `pull_request:`, a pull request's check
    /\ ci[p] = "none"
    \* scripts/select_tests.py `lone = unowned()`, scripts/select_tests.py `def owns(patterns, path):`: the rules' tests, every test no rule owns (#397), and
    \* each test whose READ_SET matches the changed path (#426). A test that reads the tree through
    \* a glob or a walk needs a read set, but that guard sees only the reads it knows, so a test
    \* that reads the changed path another way, or past its read set, is selected by chance.
    \* A stacked link's check fails here only on its own change and main's red, not on its base's.
    \* A flake of main's run fails no pull request's check.
    /\ \E sel \in BOOLEAN :
        /\ ci' = [ci EXCEPT ![p] =
                IF sel /\ ((mainRed /\ redBy # "flake" /\ ~fixes[p]) \/ breaks[p]) THEN "fail" ELSE "pass"]
        \* The check passed without the test the change breaks: its selection missed it.
        /\ missed' = [missed EXCEPT ![p] = ~sel /\ breaks[p]]
    \* browser.yml runs every browser test, so its run fails exactly when one fails.
    /\ brFail' = [brFail EXCEPT ![p] = viewBroken \/ brBreaks[p]]
    \* jmerge's next run says the check failed, or the browser run did, and the pass after reads it.
    /\ heard' = (heard /\ ci'[p] = "pass" /\ ~brFail'[p])
    /\ UNCHANGED <<st, breaks, Main, outsideLeft, link, on, Machine, moved,
                   fixes, brBreaks, viewBroken, brHold, Row, Queue, editsLeft>>

\* jmerge would merge p by every rule but two: main moved after its check started, and the guards
\* on its merged tree. Its review, findings and own checks are judged first, as for any merge.
Clear(p) ==
    /\ st[p] = "open"
    \* Its row's go: a row you held, or whose go does not hold for its brief, waits on your approval.
    /\ go[p]                                \* features/jmerge/src/jmerge/rows.py `if row.get("held"):`, features/jmerge/src/jmerge/rows.py `if row and not judgement.has_go(row, brief):`
    /\ ci[p] = "pass"                       \* features/jmerge/src/jmerge/ready.py `(CHECK_FAILED if failed else NOT_PASSED).format(check=one.waiting[0])`
    \* Its one review round came before it opened, at the head its desk proof binds, and a fix its
    \* crew pushes for the findings gets no review (review-after-green-one-round,
    \* vision-review-before-pr): the merge waits on that pass and the round's verdict at the head.
    \* features/jmerge/src/jmerge/ready.py `short = _cleanup(said) if said.mode == CLEANUP else _review(said, head, proven)`
    \* Its last review round says the brief is met (#843).
    /\ meets[p]                             \* features/jmerge/src/jmerge/ready.py `return short or short_on_meets(text, heard)`
    \* A red main holds no pull request (red-main-no-hold, #862): only its own checks do.
    \* Its own browser run failed: it waits, as main's red or as its own (#575, #577).
    /\ ~brFail[p]                           \* features/jmerge/src/jmerge/cli.py `if state != ready.BROWSER_FAILED:`
    \* A link jbus stacked merges only once jbus moved it onto main and its head holds its base's merge.
    /\ on[p] = "main"                       \* features/jmerge/src/jmerge/cli.py `ready.STACKED_UNMOVED.format(`
    \* A merge_after row merges after its row.
    /\ (p = "b" /\ link = "after") => st["a"] = "merged"   \* features/jmerge/src/jmerge/rows.py `row.get("merge_after", [])`

\* jmerge merges p with no hold for your word.
Ready(p) ==
    /\ ~needs[p]                            \* features/jmerge/src/jmerge/cli.py `hold = self.lift(ready.needs_the_user(one, self.protected, left, user=self.user), lifted)`
    /\ Clear(p)

\* p is a member of the batch jmerge builds: ready, main moved after its check started, and no
\* member of a batch of one that failed at its head. jmerge batches only while main.json says main
\* is green.
Member(p) ==
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `if not check and (state / batch.SWITCH).exists() and default and not repo.main_state.red:`
    /\ Ready(p)
    /\ moved[p]                             \* features/jmerge/src/jmerge/cli.py `if self.batching is not None and self.batching.takes(one, self.trunk, self.is_revert(one)):`
    /\ p \notin alone                       \* features/jmerge/src/jmerge/batch.py `failed = self.record.failed.get(str(one.number)) == one.head`

\* What p merges on alone, the batch aside: while a batch is out on a green main, a pull request that
\* would merge alone waits for it, since its merge would move the tip the batch's check ran over.
Alone(p) ==
    /\ mainRed \/ batch = {}                \* features/jmerge/src/jmerge/cli.py `elif on is not None and on.record.batch and on.first and not repo.is_revert(one):`
    /\ ~Member(p)                           \* features/jmerge/src/jmerge/cli.py `elif on is not None and found.judged.batch:`

\* A merge of pull request p into main, alone, on its check, by jmerge on its own or on your word.
\* A merged fix ends the red once main's new tip is checked green, which this step takes as one:
\* with no hold, nothing waits for its own check to prove it first.
Merged(p) ==
    /\ st' = [st EXCEPT ![p] = "merged"]
    /\ on' = on
    /\ mainRed' = ((mainRed /\ ~fixes[p]) \/ breaks[p])
    \* The merge is the one clear culprit only when it is the first red since the last green; a merge
    \* on a red main that breaks more is a second red, and one that breaks nothing more leaves the
    \* red as it was. MainRed.tla has how jbus.culprits tells them apart.
    /\ redBy' = IF ~mainRed' THEN "none"
                ELSE IF ~mainRed \/ fixes[p] THEN "merge"
                ELSE IF breaks[p] THEN "many" ELSE redBy
    /\ mend' = IF ~mainRed' THEN "none"
               ELSE IF ~mainRed \/ fixes[p] \/ mend = "none" THEN "judging" ELSE mend
    /\ fixes' = IF fixes[p] THEN NoFix ELSE fixes
    \* No browser break merges past its own browser run.
    /\ viewBroken' = (viewBroken \/ brBreaks[p])
    /\ MainMoves
    /\ line' = IF line = p THEN "none" ELSE line
    /\ suspects' = suspects \ {p}
    /\ alone' = alone \ {p}

\* A merge alone, where it takes no turn in the line: its check ran over today's main, or main moved
\* after it and the merged-tree guards pass at its head over the tip (item F). TLC takes either for a
\* pull request main moved past, as what the guards miss of it is what its check missed.
Merges(p) ==
    /\ Clear(p)                             \* features/jmerge/src/jmerge/cli.py `found = repo.waits(one, default)`
    \* A pass over a main that moved since it started counts, with no branch update and no rerun,
    \* where the merged-tree guards pass at its head over that tip (item F,
    \* features/jmerge/src/jmerge/cli.py `return "", ready.Judged(tip, overlaps=True)`). One that
    \* conflicts waits for its rebase, which the model leaves out, and one whose guards failed goes
    \* through the line (InLine). The model keeps what the guards and the check both miss of such a
    \* merge as breaks[p] with missed[p], which main's own run and MainRed.tla's revert catch.
    /\ Merged(p)
    /\ UNCHANGED <<ci, missed, breaks, outsideLeft, link, Machine, brBreaks, brFail, brHold, Row,
                   heard, editsLeft>>

\* jmerge merges a pull request that waits on nothing: no hold for your word, and no batch.
Merge(p) ==
    /\ ~needs[p]                            \* features/jmerge/src/jmerge/cli.py `hold = self.lift(ready.needs_the_user(one, self.protected, left, user=self.user), lifted)`
    /\ Alone(p)
    /\ Merges(p)                            \* features/jmerge/src/jmerge/cli.py `say(repo.merge(one, found.slug, found.note, found.judged))`

\* You lift the hold of a pull request that waits on your word, with jmerge --accept: it merges at
\* once where nothing else holds it, and is refused otherwise. An accept is judged before jmerge
\* reads its batch, so it waits on none, and its merge moves the tip under a batch out.
Accept(p) ==
    /\ needs[p]                             \* features/jmerge/src/jmerge/cli.py `if judgement.accepted(why) and ready.code_of(why) in lifted:`
    /\ Merges(p)                            \* features/jmerge/src/jmerge/cli.py `said = self.merge(one, slug, found.note, found.judged)`

\* A ready pull request main moved past that is no member of a batch, and whose merged-tree guards
\* failed at its head over the tip, has GitHub merge main into its branch, in its turn: the holder
\* of main's line, or the first to take a free one. Each other waits in line behind the holder, and
\* GitHub is asked nothing for it until its turn (#1009). Its check at the new head decides.
InLine(p) ==
    /\ Ready(p)                             \* features/jmerge/src/jmerge/cli.py `found = repo.waits(one, default)`
    /\ Alone(p)                             \* features/jmerge/src/jmerge/cli.py `elif on is not None and on.record.batch and on.first and not repo.is_revert(one):`
    /\ moved[p]                             \* features/jmerge/src/jmerge/cli.py `if not self.guards.command or self.is_revert(one) or self.guards.kept(one, tip): return self.base_moved(one, tip), ready.Judged()`
    /\ line \in {"none", p}                 \* features/jmerge/src/jmerge/cli.py `if ahead != one.number: return ready.IN_LINE.format(number=ahead, base=one.base)`
    /\ line' = p
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ NewHead(p)
    /\ UNCHANGED <<st, missed, breaks, Main, outsideLeft, link, on, Machine, Fix, Browser, Row,
                   batch, heard, editsLeft>>

\* The holder of main's line gives it up once it waits on anything but jmerge, GitHub and its
\* check (cli.IN_LINE): it merged, its check failed, it waits on its crew, on you or on another pull
\* request, or it is a member of the batch. The next one in merge order then takes it.
KeepsLine(p) ==
    /\ st[p] = "open"
    /\ ci[p] # "fail"                       \* features/jmerge/src/jmerge/cli.py `if one.failed: return ready.code_of(found.why) in UPDATING_RED`
    /\ ~Member(p)                           \* features/jmerge/src/jmerge/cli.py `return not found.judged.batch`
    /\ go[p] /\ ~needs[p] /\ meets[p] /\ ~brFail[p] /\ on[p] = "main"   \* features/jmerge/src/jmerge/cli.py `return ready.code_of(found.why) in IN_LINE`
    /\ (p = "b" /\ link = "after") => st["a"] = "merged"   \* features/jmerge/src/jmerge/cli.py `return ready.code_of(found.why) in IN_LINE`

GiveUpLine ==
    /\ line # "none"
    /\ ~KeepsLine(line)                     \* features/jmerge/src/jmerge/cli.py `if self.line.get(one.base) == one.number and not in_line(one, found): self.base_merge.release(one.number)`
    /\ line' = "none"
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on, Machine, moved, Fix, Browser, Row,
                   batch, suspects, alone, heard, editsLeft>>

\* jmerge builds the batch over main's tip from the members it judged: the first half of the
\* suspects that are still members, and every member where no suspect is left. It builds it again,
\* from the members left, when one of the batch out is no longer a member at its head, as a held
\* row or a new head makes it. Each member waits on the batch's check, and each pull request that
\* would merge alone waits for it too (Alone). The most a batch takes (#1613) is 12 or more, and
\* the model has two.
Narrow(s) == IF s = PRs THEN {"a"} ELSE s

BuildBatch ==
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `if not check and (state / batch.SWITCH).exists() and default and not repo.main_state.red:`
    /\ \/ batch = {}
       \/ \E m \in batch : ~Member(m)       \* features/jmerge/src/jmerge/cli.py `if set(kept.members) <= judged:`
    /\ LET members == {p \in PRs : Member(p)}
           kept == suspects \cap members
       IN /\ batch' = IF kept # {} THEN Narrow(kept) ELSE members   \* features/jmerge/src/jmerge/batch.py `return [judged[one] for one in narrow(self.record.suspects)] or members`
          /\ suspects' = kept
    /\ batch' # batch
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on, Machine, moved, Fix, Browser, Row,
                   alone, line, heard, editsLeft>>

\* CI's check of the batch's pull request runs over main's tip with every member merged in. It runs
\* the tests the batch's change selects, so it may miss a test a member breaks, as a pull request's
\* check may. A pass: jmerge squash-merges each member at its own head, in order, on its next run.
\* The first member to break a test is the one clear culprit of main's red, and a second that breaks
\* more makes it many. A proven half with one suspect left sends that one down the single path.
BatchPasses ==
    /\ batch # {}
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `if not check and (state / batch.SWITCH).exists() and default and not repo.main_state.red:`
    /\ \A m \in batch : Member(m)           \* features/jmerge/src/jmerge/cli.py `if set(kept.members) <= judged:`
    /\ LET broke == {m \in batch : breaks[m]}
           left == suspects \ batch
       IN /\ st' = [p \in PRs |-> IF p \in batch THEN "merged" ELSE st[p]]   \* features/jmerge/src/jmerge/cli.py `line, expected = self.squash(found[0], found[1], [found[2], passed])`
          /\ missed' = [p \in PRs |-> missed[p] \/ p \in broke]
          /\ mainRed' = (broke # {})
          /\ redBy' = CASE broke = {} -> "none"
                        [] Cardinality(broke) = 1 -> "merge"
                        [] OTHER -> "many"
          /\ mend' = IF broke = {} THEN "none" ELSE "judging"
          /\ viewBroken' = (viewBroken \/ \E m \in batch : brBreaks[m])
          /\ on' = on
          /\ MainMoves
          /\ line' = IF line \in batch THEN "none" ELSE line
          /\ IF Cardinality(left) = 1 /\ left # suspects   \* features/jmerge/src/jmerge/batch.py `if len(left) == 1 and len(left) < len(self.suspects):`
               THEN /\ alone' = (alone \ batch) \cup left
                    /\ suspects' = {}
               ELSE /\ alone' = alone \ batch
                    /\ suspects' = left
    /\ UNCHANGED <<ci, breaks, outsideLeft, link, Machine, Fix, brBreaks, brFail, brHold, Row,
                   heard, editsLeft>>

\* CI's check of the batch fails. A batch of two is rerun once first (`gh run rerun --failed`),
\* which in this model fails again, as a member's break is no flake. A failed batch of two makes its
\* members the suspects, and a failed batch of one sends its member down the single path at that
\* head. No crew is told: the batch is jmerge's own work.
BatchFails ==
    /\ batch # {}
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `if not check and (state / batch.SWITCH).exists() and default and not repo.main_state.red:`
    /\ \A m \in batch : Member(m)           \* features/jmerge/src/jmerge/cli.py `if set(kept.members) <= judged:`
    /\ \E m \in batch : breaks[m]           \* features/jmerge/src/jmerge/batch.py `return RERUN if rerunnable and len(batch.members) > 1 else FAILED`
    /\ batch' = {}
    /\ IF Cardinality(batch) > 1            \* features/jmerge/src/jmerge/batch.py `if len(members) > 1: self.suspects = members`
         THEN /\ suspects' = batch
              /\ UNCHANGED alone
         ELSE /\ alone' = alone \cup batch  \* features/jmerge/src/jmerge/batch.py `self.failed |= {str(one.number): one.head for one in members}`
              /\ suspects' = suspects \ batch
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on, Machine, moved, Fix, Browser, Row,
                   line, heard, editsLeft>>

\* jbus's pass starts jmerge's run and returns, and the first pass after reads the lines the run
\* printed (#1616): the step on which what jmerge said of a failed check, a browser run or a review
\* round reaches the pass's tellers.
Hear ==
    /\ ~heard                               \* features/jbus/src/jbus/poll.py `half.said = merge.merge(run)`
    /\ heard' = TRUE                        \* features/jbus/src/jbus/merge.py `return _records(run, where)`
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on, Machine, moved, Fix, Browser, Row,
                   Queue, editsLeft>>

\* Its last review round says the brief is not met (MEETS_NO): jbus tells its crew (#850), which
\* fixes the lines it names and pushes, and the scoped review that follows says the brief is met.
\* Only your Waived: line is the other way out, which the model leaves out.
MeetsFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/expedite.py `world.open.items()`, open ones only
    /\ ~meets[p]                            \* features/jbus/src/jbus/expedite.py `"meets-no",`, features/jmerge/src/jmerge/ready.py `MEETS_NO = Reason(`
    /\ heard                                \* features/jbus/src/jbus/expedite.py `half.crews = tell(half.run, half.client, world, half.said)`
    /\ meets' = [meets EXCEPT ![p] = TRUE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ NewHead(p)
    /\ Leaves(p)
    /\ UNCHANGED <<st, missed, breaks, Main, outsideLeft, link, on,
                   fixes, Browser, go, needs, batch, line, heard, editsLeft>>

\* Its base merged: jbus moves the stacked pull request onto main and rebases its own commits
\* onto main itself, or tells its crew to ("A link that moved"), and its check runs again. Since
\* #868 the check's `reuse` job passes it at once where the move is a clean replay of the trees its
\* stacked check passed, and otherwise the suite runs; the model leaves out which, so TLC takes
\* either. A pass it keeps started before its base merged into main.
Restack(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/stack.py `world.open.items()`, open ones only
    /\ on[p] # "main"
    /\ st[on[p]] = "merged"                 \* features/jbus/src/jbus/stack.py `merged = world.merged.get(stacked.slug) if not merged or not rebase.crew(run, slug):`, its base merged
    /\ on' = [on EXCEPT ![p] = "main"]
    /\ \E reuse \in IF ci[p] = "pass" THEN BOOLEAN ELSE {FALSE} :   \* .github/workflows/check.yml `run: PYTHONPATH=features/jmerge/src python3 -m jmerge.reuse`
         /\ ci' = [ci EXCEPT ![p] = IF reuse THEN "pass" ELSE "none"]
         /\ moved' = [moved EXCEPT ![p] = reuse]
    /\ suspects' = suspects \ {p}
    /\ alone' = alone \ {p}
    /\ UNCHANGED <<st, missed, breaks, Main, outsideLeft, link, Machine,
                   Fix, Browser, go, needs, meets, batch, line, heard, editsLeft>>

\* The home edits b's brief, on your word, and its Builds on: line no longer names a. The edit
\* voids b's go, which you give again by approving it (#399).
HomeEdits(p) ==
    /\ p = "b"
    /\ editsLeft > 0
    /\ link = "depends"
    \* A merged row's go is read by nothing, and its brief is not edited.
    /\ st[p] # "merged"                     \* features/jmerge/src/jmerge/rows.py `if row.get("status") in judgement.FINAL:`
    /\ editsLeft' = editsLeft - 1
    /\ link' = "none"
    /\ go' = [go EXCEPT ![p] = FALSE]       \* features/jmerge/src/jmerge/rows.py `if row and not judgement.has_go(row, brief):`
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, on, Machine, moved,
                   Fix, Browser, needs, meets, Queue, heard>>

\* The crew fixes its own broken change: only when it sees the failure as its own. jbus tells the
\* crew's own thread once its turn ends, so no room is asked for, and its turn may leave a
\* process running.
CrewFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/rebase.py `sent = run.box.sent() for slug, pull in world.open.items():`, open ones only
    /\ ci[p] = "fail"
    /\ breaks[p]
    /\ heard                                \* features/jbus/src/jbus/rebase.py `lambda half: tell(half.run, half.client, half.seen.world, half.said),`
    \* The crew's block answers `fix` whenever the check command fails in its worktree, before it
    \* ever looks at the base (features/crew/the-checks.md `elif [ "$here" = failed ]; then`): CI
    \* and the crew run the same selection, so a break of its own that failed CI fails there too,
    \* whether or not its check ran over a red main.
    /\ breaks' = [breaks EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ NewHead(p)
    /\ Leaves(p)
    /\ UNCHANGED <<st, missed, Main, outsideLeft, link, on, fixes, Browser,
                   go, needs, meets, batch, line, heard, editsLeft>>

\* Its own browser run failed, and the red is its own: main's last browser run passed, or the fix
\* jbus filed for it is over. jbus tells its crew, which fixes its change, and its checks run again.
BrowserFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/expedite.py `world.open.items()`, open ones only
    /\ brFail[p]                            \* features/jbus/src/jbus/expedite.py `ready.BROWSER_RED`, its browser run failed
    /\ ~brHold                              \* features/jmerge/src/jmerge/rows.py `if red and not proves(red, failed, ran):`
    /\ heard                                \* features/jbus/src/jbus/expedite.py `half.crews = tell(half.run, half.client, world, half.said)`
    /\ brBreaks' = [brBreaks EXCEPT ![p] = FALSE]
    /\ brFail' = [brFail EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ NewHead(p)
    /\ Leaves(p)
    /\ UNCHANGED <<st, missed, breaks, Main, outsideLeft, link, on,
                   fixes, viewBroken, brHold, go, needs, meets, batch, line, heard, editsLeft>>

\* jmerge judges a red pull request again: a check that failed over a base that has moved since
\* it started, while main is green, is checked again over today's base (#350): GitHub merges the
\* base into the branch and runs check again, and a broken change then fails as its own. Since
\* #1012 the update takes its turn in main's line, as a green one's does.
Rejudge(p) ==
    /\ st[p] = "open"                       \* features/jmerge/src/jmerge/cli.py `def judge(`, every open one
    /\ ci[p] = "fail"                       \* features/jmerge/src/jmerge/ready.py `def red_only`, red_only
    /\ moved[p]                             \* features/jmerge/src/jmerge/cli.py `moved = None if one.started is None else self.moved(one.base, one.started) if ( moved is None`, base moved
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `or (one.base == self.trunk and bool(self.main_state.red))`, base not red
    /\ line \in {"none", p}                 \* features/jmerge/src/jmerge/cli.py `if ahead != one.number: return ready.IN_LINE.format(number=ahead, base=one.base)`
    /\ line' = p
    /\ ci' = [ci EXCEPT ![p] = "none"]      \* features/jmerge/src/jmerge/rejudge.py `self.ask(one)`, GitHub merges the base in
    /\ NewHead(p)
    /\ UNCHANGED <<st, missed, breaks, Main, outsideLeft, link, on, Machine,
                   Fix, Browser, Row, batch, heard, editsLeft>>

\* What jbus.strays may stop of an idle process p's crew left. A crew at work is never touched
\* (features/jbus/src/jbus/strays.py `if not slug or ("crew", slug) in busy:`), and in this model a crew's turn is one step.
Stoppable(p) ==
    CASE Gap = "busy" -> FALSE
      [] Gap = "ended" -> st[p] = "merged"
      [] Gap = "turn" -> TRUE

\* jbus.strays stops what a finished turn left (#351, #363, #416, #427): a busy process, and an
\* idle one only as Gap says.
Sweep ==
    /\ busy \/ \E p \in PRs : idle[p] /\ Stoppable(p)   \* features/jbus/src/jbus/strays.py `taken = {one.pid for found in claimed.values() for one in found}`, features/jbus/src/jbus/strays.py `burning = (taken |`
    /\ busy' = FALSE
    /\ idle' = [p \in PRs |-> idle[p] /\ ~Stoppable(p)]
    /\ full' = (\E p \in PRs : idle'[p])
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on, moved,
                   Fix, Browser, Row, Queue, heard, editsLeft>>

\* jbus reruns main's failed push run once (#672) and judges the red tip (jbus.culprits): a flake
\* passes the rerun, and main is green with nothing filed; the one clear culprit of a merge is
\* reverted (#862), or, where its head lacks the green under the tip (a skew, #899), gets main's
\* fix row; a red from outside, or one of many merges, gets main's fix row (#392). MainRed.tla has
\* the rerun, the judgement and the culprit as the code has them.
JudgeRed ==
    /\ mend = "judging"                     \* features/jbus/src/jbus/culprits.py `if run.red is not None:`
    /\ CASE redBy = "flake" ->
              /\ mainRed' = FALSE
              /\ redBy' = "none"
              /\ mend' = "none"
         [] redBy = "merge" ->
              /\ mend' \in {"revert", "row"}   \* features/jbus/src/jbus/culprits.py `return None if reverts.revert(run, found) else "jbus could not open its revert"`
              /\ UNCHANGED <<mainRed, redBy>>
         [] OTHER ->
              /\ mend' = "row"                \* features/jbus/src/jbus/culprits.py `_file(run, run.red.slug, run.red.sha, run.red.red, why)`
              /\ UNCHANGED <<mainRed, redBy>>
    /\ UNCHANGED <<st, ci, missed, breaks, outsideLeft, link, on, Machine, moved, Fix, Browser, Row,
                   Queue, heard, editsLeft>>

\* jmerge merges jbus's revert on its checks, with no review, first in merge order (#1044), and
\* main is green again. Where a merge broke more on top of the revert's culprit, main is still red
\* once the revert merged: the tip is judged again, which files main's fix row.
RevertMerges ==
    /\ mend = "revert"                      \* features/jmerge/src/jmerge/cli.py `reverted = not short and self.reverted(brief.stem, one)`
    /\ IF redBy = "many"
         THEN /\ mend' = "judging"
              /\ UNCHANGED <<mainRed, redBy, Fix>>
         ELSE /\ mainRed' = FALSE
              /\ redBy' = "none"
              /\ mend' = "none"
              /\ fixes' = NoFix
    /\ st' = st /\ on' = on
    /\ MainMoves
    /\ UNCHANGED <<st, ci, missed, breaks, outsideLeft, link, on, Machine, Browser, Row,
                   suspects, alone, line, heard, editsLeft>>

\* jbus's pass approves the main-red row jbus filed by rule, not by your word (#547), and its crew
\* either fixes main in its own pull request, which merges by its slug, or ends with no pull
\* request, its fix in an open one, as on 2026-10-27, when two flow rows held the fix. Either way
\* the row is over, and jbus files no other for the same red tip
\* (features/jbus/src/jbus/watch.py `if name in run.removed or queue.fresh(run.state, name) is not None:`).
\* The fix row's brief lets its crew leave the fix only in an open pull request that waits on no
\* other: jmerge judges a pull request whose check failed over a red main again only once main is
\* green, so a fix in one that merges after it, or is stacked on it, would wait on that green.
Unordered(q) ==
    /\ on[q] = "main"                       \* features/jbus/src/jbus/watch.py `and not stacked on an open base`
    /\ ~(q = "b" /\ link = "after" /\ st["a"] # "merged")   \* features/jbus/src/jbus/watch.py `one waits on no other open pull request: no`

FixMain ==
    /\ mend = "row"                         \* features/jbus/src/jbus/watch.py `queue.add(run.state, name, top, [], text, user=run.user, ran_by=queue.PASS)`, queued by jbus's pass
    \* features/jbus/src/jbus/queue.py `if not named and filed(row, text):`, its go by rule
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ \/ /\ mainRed' = FALSE
          /\ redBy' = "none"
          /\ mend' = "none"
          /\ fixes' = NoFix
          /\ st' = st /\ on' = on
          /\ MainMoves
          /\ UNCHANGED <<ci, suspects, alone>>
       \/ \E q \in PRs :
          /\ st[q] = "open"
          /\ Unordered(q)                     \* features/jbus/src/jbus/watch.py `in another open pull request only where that`
          /\ mend' = "none"
          /\ fixes' = [fixes EXCEPT ![q] = TRUE]
          /\ ci' = [ci EXCEPT ![q] = "none"]
          /\ NewHead(q)
          /\ UNCHANGED <<mainRed, redBy, batch>>
    /\ UNCHANGED <<st, missed, breaks, outsideLeft, link, on, Machine, Browser,
                   go, needs, meets, line, heard, editsLeft>>

\* main's browser run fails, and jbus files its browser-red row (features/jbus/src/jbus/watch.py `prefix="browser-red-"`),
\* whose run then holds as main's red each pull request whose own browser run failed.
\* browser.yml runs on main only nightly, so the hold starts with its next run.
Nightly ==
    /\ viewBroken                           \* .github/workflows/browser.yml `schedule:`, its nightly run
    /\ ~brHold
    /\ brHold' = TRUE                       \* features/jmerge/src/jmerge/rows.py `if last is None or last.get("conclusion") in NOT_RED or str(last.get("id")) not in fixing:`, red and its fix open
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on,
                   Machine, moved, Fix, brBreaks, brFail, viewBroken, Row, Queue, heard, editsLeft>>

\* jbus's pass approves the browser-red row by rule too: jbus filed it from a red run, with the
\* same Decisions: line as main's fix row (#547). Its crew fixes main's view, and its row is over,
\* so main's last run, still red until the next nightly, holds nobody (features/jmerge/src/jmerge/rows.py `fixing = {row["slug"] for row in rows or [] if row.get("status") not in judgement.FINAL}`).
FixBrowser ==
    /\ brHold                               \* features/jbus/src/jbus/queue.py `if not named and filed(row, text):`, its go by rule
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ viewBroken' = FALSE
    /\ brHold' = FALSE
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on,
                   Machine, moved, Fix, brBreaks, brFail, Row, Queue, heard, editsLeft>>

\* You approve a row, which gives it its go again (`jbus queue approve`).
Approve(p) ==
    /\ ~go[p]                               \* features/jbus/src/jbus/queue.py `again = row.get("approved") and judgement.approved_text(row, text) and not row.get("held")`
    /\ go' = [go EXCEPT ![p] = TRUE]
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on, Machine, moved,
                   Fix, Browser, needs, meets, Queue, heard, editsLeft>>

\* You hold a row that is not merged (`jbus queue hold`), which takes its go back.
HoldRow(p) ==
    \* A merged row's hold holds nothing.
    /\ st[p] # "merged"                     \* features/jmerge/src/jmerge/rows.py `if row.get("status") in judgement.FINAL:`
    /\ go[p]                                \* features/jbus/src/jbus/queue.py `took = {column: row[column] for column in GO_COLUMNS if row.get(column)} _hold(row, by)`, features/jbus/src/jbus/queue.py `row.update(approved="", brief_sha="", held=True)`
    /\ go' = [go EXCEPT ![p] = FALSE]
    /\ UNCHANGED <<st, ci, missed, breaks, Main, outsideLeft, link, on, Machine, moved,
                   Fix, Browser, needs, meets, Queue, heard, editsLeft>>

\* Something outside the queue breaks main: its check, as a flake its rerun passes or as a break
\* that stays (a tool update), or its view, which only browser.yml sees. The model leaves out a
\* hand merge, which would also move main's tip.
OutsideBreak ==
    /\ outsideLeft > 0
    /\ outsideLeft' = outsideLeft - 1
    /\ \/ /\ ~mainRed
          /\ mainRed' = TRUE
          /\ redBy' \in {"flake", "outside"}
          \* features/jbus/src/jbus/watch.py `if not slugs and not fixes and not main.red:`, features/jbus/src/jbus/watch.py `no briefed merge came in`: since #392 the fix row is filed for a
          \* red tip with no briefed merge in the day before it too, under the row's own name,
          \* once its rerun failed and jbus.culprits judged it (JudgeRed).
          /\ mend' = "judging"
          /\ UNCHANGED <<viewBroken>>
       \/ /\ ~viewBroken
          /\ viewBroken' = TRUE
          /\ UNCHANGED <<Main>>
    /\ UNCHANGED <<st, ci, missed, breaks, link, on, Machine, moved, fixes, brBreaks, brFail,
                   brHold, Row, Queue, heard, editsLeft>>

System == Sweep \/ Nightly \/ JudgeRed \/ RevertMerges \/ FixMain \/ FixBrowser
    \/ BuildBatch \/ BatchPasses \/ BatchFails \/ GiveUpLine \/ Hear
    \/ \E p \in PRs :
        Launch(p) \/ MeetsFix(p) \/ Check(p) \/ Merge(p) \/ InLine(p) \/ Restack(p)
        \/ CrewFix(p) \/ BrowserFix(p) \/ Rejudge(p)

\* Your word: a row's go, and the lift of a hold that waits on you.
YourWord == \E p \in PRs : Approve(p) \/ Accept(p)

Next == System \/ OutsideBreak \/ YourWord \/ \E p \in PRs : HoldRow(p) \/ HomeEdits(p)

Spec == Init /\ [][Next]_vars

Settled == ~ENABLED System

TypeOK ==
    /\ st \in [PRs -> {"queued", "open", "merged"}]
    /\ ci \in [PRs -> {"none", "pass", "fail"}]
    /\ redBy \in {"none", "flake", "outside", "merge", "many"}
    /\ mend \in {"none", "judging", "revert", "row"}
    /\ (redBy = "none") = ~mainRed
    /\ mend # "none" => mainRed
    /\ link \in {"depends", "after", "none"}
    /\ on \in [PRs -> {"main"} \cup PRs]
    /\ full = (busy \/ \E p \in PRs : idle[p])
    /\ brHold => viewBroken
    /\ go \in [PRs -> BOOLEAN]
    /\ missed \in [PRs -> BOOLEAN]
    /\ moved \in [PRs -> BOOLEAN]
    /\ batch \subseteq PRs /\ suspects \subseteq PRs /\ alone \subseteq PRs
    /\ \A p \in batch \cup suspects \cup alone : st[p] = "open"
    /\ line \in PRs \cup {"none"}
    /\ heard \in BOOLEAN

\* "Work never stops flowing: once nothing more happens on its own and main is green, it settles merged or waiting on your word."
\* Its words are those it had before fl-rules-1103: a pull request held on a protected path is open
\* and checked, so it waits on your word.
FlowsWhenGreen == (Settled /\ ~Red) => (\A p \in PRs : st[p] = "merged") \/ ENABLED YourWord

\* "A merge turns main red only through a test its check's selection missed, and then jbus reruns main's failed push run once and reverts the one clear culprit or files main's fix row."
\* Until it is judged, the red is due its rerun and judgement; once judged, jbus's revert is open,
\* or main's fix row is filed, or that row's crew put the fix in an open pull request.
MergeRedsMainOnlyOnAMissedTest ==
    /\ \A p \in PRs : (st[p] = "merged" /\ breaks[p]) => missed[p]
    /\ redBy \in {"merge", "many"} =>
        /\ mend = "judging" => ENABLED JudgeRed
        /\ mend # "judging" => mend \in {"revert", "row"} \/ \E q \in PRs : fixes[q]

\* "Once nothing more happens on its own, the machine has room."
MachineNotLeftFull == Settled => ~full

\* "While main is red and nothing else can happen, its fix waits on nothing of yours but your word: the lift of a pull request you hold, or your approval of a row whose brief you must approve."
\* Since #547 jbus approves every fix row it files, main's and the browser run's, by rule, so no
\* approval of a fix row is yours.
MainFixWaitsOnlyOnYou == (Settled /\ Red) => ENABLED YourWord

\* For the chart only (FlowToday.chart.cfg): no change breaks a browser test of its own, though
\* main's view may still break from outside, and no brief is edited. The chart reader holds TLC's
\* whole state graph in memory, and the whole model does not fit. flow_canaries.py checks every
\* rule on the whole model.
ChartCut == editsLeft = 1 /\ \A p \in PRs : ~brBreaks[p]

\* A probe, no rule: the case README.md names by itself. Main's fix is in b, the merge_after
\* follow-up of a, and a's check failed over the red main: jmerge judges a again only once main is
\* green (Rejudge), and b merges only after a, so the fix waits on neither your word nor anything
\* else. Main's fix brief keeps the fix out of b there (Unordered), so TLC holds it.
FixAfterARedCheck ==
    /\ mainRed /\ link = "after" /\ fixes["b"]
    /\ st["a"] = "open" /\ ci["a"] = "fail" /\ ~breaks["a"]
FixAfterARedCheckWaitsOnlyOnYou == (Settled /\ FixAfterARedCheck) => ENABLED YourWord
====
