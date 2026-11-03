---- MODULE FlowToday ----
\* What jstack does today with two pull requests, a main that can go red, and a machine that can fill.
\* Code as of main a978b7ba9 (2026-11-02): the flow-statechart scout's FlowNow.tla at 6485914, with
\* #416, #426 and #427 since, cut down to the variables FlowDesign.tla's four rules read, and with
\* the fix a pull request's own check proves (#583, #584) and the browser run's holds (#575, #577).
\* Since cut 11 of the simplify pass, the copy of simplify-5's RowLife.tla adds a row's go, a hold
\* for your word, and until fl-no-draft the draft whose check waited on its review.
\* Since fl-statechart-1102 (the scout's FlowNow.tla at a978b7ba9) it has jbus's rerun of a red
\* push run (#672), its revert of a red main's one clear culprit and the close of a stale revert
\* (#862, #899), the fix rows' go by rule (#547), a stacked link checked while stacked and its pass
\* kept on a clean move (#868), and the hold of a review round that says the brief is not met
\* (#843, #850). Since fl-stack-by-depends-only it has no unstack: a link stays on its stack
\* until its base merged, and a stack is made by a depends alone.
\* Since fl-rules-1103 two of its rules say the flow the merged pull requests chose since.
\* Since fl-no-draft a crew opens its pull request ready, so its check runs beside its review, and
\* jmerge marks no draft ready: the draft, Ready and the lift --accept kept on a draft went.
EXTENDS Naturals

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
\* fixRow: a main-red-<sha> row is queued for main's fix.
\* named: the red run's logs name the tests that failed there, which main.json keeps as `failed`.
\* missed[p]: p's last check passed without running a test its change breaks: the selection
\*   missed it.
\* fixes[p]: p's head carries main's fix, which the main-red row's crew put there and not in a pull
\*   request of its own. proved[p]: p's check ran over main's red tip, ran each test that failed
\*   there, and passed it (rows.proves).
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
\* rerun: main's push run failed at its red tip, and jbus's one rerun of it has not ended (#672).
\* culprit: what made main's red tip, for jbus.reverts: "none" (no briefed merge: outside), "a" or
\*   "b" (the one merge since the last green, its head over the green under it), "skew" (that one
\*   merge, its head not over the green under it, #899), or "many" (a merge landed on a red tip).
\* judged: jbus.culprits judged the red tip there is now: it reverted it or filed its row.
\* revert: "open" while jbus's revert of a culprit is open (#862), else "none".
\* editsLeft: the edits still to come of b's brief that take a out of its Builds on: line, once.
VARIABLES st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, link, on, busy, idle,
    named, fixes, proved, brBreaks, brFail, viewBroken, brHold, go, needs, meets,
    rerun, culprit, judged, revert, editsLeft
vars == <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, link, on, busy, idle,
    named, fixes, proved, brBreaks, brFail, viewBroken, brHold, go, needs, meets,
    rerun, culprit, judged, revert, editsLeft>>

Init ==
    /\ st = [p \in PRs |-> "queued"]
    /\ ci = [p \in PRs |-> "none"]
    /\ ranRed = [p \in PRs |-> FALSE]
    /\ missed = [p \in PRs |-> FALSE]
    /\ breaks \in [PRs -> BOOLEAN]          \* the change breaks a test that reads the whole tree
    /\ told = [p \in PRs |-> FALSE]
    /\ mainRed = FALSE
    /\ redBy = "none"
    /\ outsideLeft = 1
    /\ full = FALSE
    /\ fixRow = FALSE
    /\ link \in {"depends", "after"}
    /\ on = [p \in PRs |-> "main"]
    /\ busy = FALSE
    /\ idle = [p \in PRs |-> FALSE]
    /\ named = FALSE
    /\ fixes = [p \in PRs |-> FALSE]
    /\ proved = [p \in PRs |-> FALSE]
    /\ brBreaks \in [PRs -> BOOLEAN]
    /\ brFail = [p \in PRs |-> FALSE]
    /\ viewBroken = FALSE
    /\ brHold = FALSE
    /\ go = [p \in PRs |-> TRUE]
    /\ needs \in [PRs -> BOOLEAN]
    /\ meets \in {[p \in PRs |-> TRUE]} \cup {[p \in PRs |-> p # q] : q \in PRs}
    /\ rerun = FALSE
    /\ culprit = "none"
    /\ judged = FALSE
    /\ revert = "none"
    /\ editsLeft = 1

Machine == <<full, busy, idle>>
Fix == <<named, fixes, proved>>
Browser == <<brBreaks, brFail, viewBroken, brHold>>
Row == <<go, needs, meets>>
Judge == <<rerun, culprit, judged, revert>>
NoFix == [p \in PRs |-> FALSE]

\* Main is red: its check failed, or its browser run failed while that run's fix is open.
Red == mainRed \/ brHold

\* A turn of p's crew ends, and may leave a process running: busy, idle, or none.
Leaves(p) ==
    \E kind \in {"none", "busy", "idle"} :
        /\ busy' = (busy \/ kind = "busy")
        /\ idle' = [idle EXCEPT ![p] = idle[p] \/ kind = "idle"]
        /\ full' = (busy' \/ \E x \in PRs : idle'[x])

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
    \* Its crew opens it ready, so its check runs beside its review.
    /\ Leaves(p)
    /\ UNCHANGED <<ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, Fix, Browser,
                   go, needs, meets, Judge, editsLeft>>

\* GitHub runs the pull request's check over the base as it is now: main, or since #868 the
\* branch of the open pull request it is stacked on.
Check(p) ==
    /\ st[p] = "open"                       \* .github/workflows/check.yml `pull_request:`, a pull request's check
    /\ ci[p] = "none"
    \* scripts/select_tests.py `lone = unowned()`, scripts/select_tests.py `if owns(patterns, path)`: the rules' tests, every test no rule owns (#397), and
    \* each test whose READ_SET matches the changed path (#426). A test that reads the tree through
    \* a glob or a walk needs a read set, but that guard sees only the reads it knows, so a test
    \* that reads the changed path another way, or past its read set, is selected by chance.
    \* The same chance decides whether it ran the tests main failed, so a check of main's fix proves
    \* it only when it selected them: scripts/select_tests.py reads the diff, not main.json.
    \* A stacked link's check fails here only on its own change and main's red, not on its base's.
    /\ \E sel \in BOOLEAN :
        /\ ci' = [ci EXCEPT ![p] =
                IF sel /\ ((mainRed /\ ~fixes[p]) \/ breaks[p]) THEN "fail" ELSE "pass"]
        \* features/jmerge/src/jmerge/rows.py `ran.over == red and bool(failed)`, the head holds the red tip and ran each failed test
        /\ proved' = [proved EXCEPT ![p] = sel /\ mainRed /\ fixes[p] /\ ~breaks[p] /\ named]
        \* The check passed without the test the change breaks: its selection missed it.
        /\ missed' = [missed EXCEPT ![p] = ~sel /\ breaks[p]]
    /\ ranRed' = [ranRed EXCEPT ![p] = mainRed]
    \* browser.yml runs every browser test, so its run fails exactly when one fails.
    /\ brFail' = [brFail EXCEPT ![p] = viewBroken \/ brBreaks[p]]
    /\ UNCHANGED <<st, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   named, fixes, brBreaks, viewBroken, brHold, Row, Judge, editsLeft>>

\* A merge of a pull request whose check passed, by jmerge on its own or on your word.
Merges(p) ==
    /\ st[p] = "open"
    \* Its row's go: a row you held, or whose go does not hold for its brief, waits on your approval.
    /\ go[p]                                \* features/jmerge/src/jmerge/rows.py `if row.get("held"):`, features/jmerge/src/jmerge/rows.py `if row and not judgement.has_go(row, brief):`
    /\ ci[p] = "pass"                       \* features/jmerge/src/jmerge/ready.py `(CHECK_FAILED if failed else NOT_PASSED).format(check=one.waiting[0])`
    \* Its last review round says the brief is met (#843).
    /\ meets[p]                             \* features/jmerge/src/jmerge/ready.py `return short or short_on_meets(text, heard)`
    \* A red main holds no pull request (red-main-no-hold, #862): only its own checks do.
    \* Its own browser run failed: it waits, as main's red or as its own (#575, #577).
    /\ ~brFail[p]                           \* features/jmerge/src/jmerge/cli.py `if state != ready.BROWSER_FAILED:`
    \* A link jbus stacked merges only once jbus moved it onto main and its head holds its base's merge.
    /\ on[p] = "main"                       \* features/jmerge/src/jmerge/cli.py `ready.STACKED_UNMOVED.format(`
    \* A merge_after row merges after its row.
    /\ (p = "b" /\ link = "after") => st["a"] = "merged"   \* features/jmerge/src/jmerge/rows.py `row.get("merge_after", [])`
    /\ st' = [st EXCEPT ![p] = "merged"]
    \* A merged fix ends the red once main's new tip is checked green, which this step takes as one:
    \* with no hold, nothing waits for its own check to prove it first.
    /\ mainRed' = ((mainRed /\ ~fixes[p]) \/ breaks[p])
    /\ redBy' = IF breaks[p] THEN "merge" ELSE IF fixes[p] THEN "none" ELSE redBy
    \* A red tip's push run is rerun once before jbus judges it (#672), and judged again.
    /\ rerun' = mainRed'
    /\ judged' = FALSE
    \* The merge is the one clear culprit only when it is the one merge since the last green
    \* (features/jbus/src/jbus/reverts.py `if len(red.since) > 1:`), and only when its head holds the green
    \* under the red tip (features/jbus/src/jbus/reverts.py `return found if status in ("ahead", "identical") else Keep.SKEW`, #899):
    \* the model leaves out what its head holds, so TLC takes either.
    /\ culprit' \in IF ~mainRed' THEN {"none"} ELSE IF mainRed THEN {"many"} ELSE {p, "skew"}
    \* A green tip withdraws a fix row that never launched (features/jbus/src/jbus/watch.py `_withdraw(run, fixes, tip)`), and in this model
    \* a queued fix row has not launched.
    /\ fixRow' = (fixRow /\ mainRed')
    /\ named' \in IF breaks[p] /\ ~(mainRed /\ ~fixes[p]) THEN BOOLEAN ELSE {named}
    /\ fixes' = IF fixes[p] THEN NoFix ELSE fixes
    /\ proved' = IF fixes[p] THEN NoFix ELSE proved
    \* No browser break merges past the hold above.
    /\ viewBroken' = (viewBroken \/ brBreaks[p])
    /\ UNCHANGED <<ci, ranRed, missed, breaks, told, outsideLeft, link, on, Machine, brBreaks, brFail, brHold, Row,
                   revert, editsLeft>>

\* jmerge merges a pull request that waits on nothing: no hold for your word.
Merge(p) ==
    /\ ~needs[p]                            \* features/jmerge/src/jmerge/cli.py `hold = self.lift(ready.needs_the_user(one, self.protected, left, user=self.user), lifted)`
    /\ Merges(p)

\* You lift the hold of a pull request that waits on your word, with jmerge --accept: it merges at
\* once where nothing else holds it, and is refused otherwise.
Accept(p) ==
    /\ needs[p]                             \* features/jmerge/src/jmerge/cli.py `if judgement.verb(why) == judgement.HOLD and ready.code_of(why) in lifted:`
    /\ Merges(p)                            \* features/jmerge/src/jmerge/cli.py `said = self.merge(one, found.slug, found.note, found.judged)`

\* Its last review round says the brief is not met (MEETS_NO): jbus tells its crew (#850), which
\* fixes the lines it names and pushes, and the scoped review that follows says the brief is met.
\* Only your Waived: line is the other way out, which the model leaves out.
MeetsFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/expedite.py `world.open.items()`, open ones only
    /\ ~meets[p]                            \* features/jbus/src/jbus/expedite.py `"meets-no",`, features/jmerge/src/jmerge/ready.py `MEETS_NO = Reason(`
    /\ meets' = [meets EXCEPT ![p] = TRUE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ proved' = [proved EXCEPT ![p] = FALSE]
    /\ Leaves(p)
    /\ UNCHANGED <<st, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   named, fixes, Browser, go, needs, Judge, editsLeft>>

\* Its base merged: jbus moves the stacked pull request onto main and rebases its own commits
\* onto main itself, or tells its crew to ("A link that moved"), and its check runs again. Since
\* #868 the check's `reuse` job passes it at once where the move is a clean replay of the trees its
\* stacked check passed, and otherwise the suite runs; the model leaves out which, so TLC takes
\* either.
Restack(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/stack.py `world.open.items()`, open ones only
    /\ on[p] # "main"
    /\ st[on[p]] = "merged"                 \* features/jbus/src/jbus/stack.py `world.merged.get(stacked.slug)`, its base merged
    /\ on' = [on EXCEPT ![p] = "main"]
    /\ \E reuse \in IF ci[p] = "pass" THEN BOOLEAN ELSE {FALSE} :   \* .github/workflows/check.yml `run: PYTHONPATH=features/jmerge/src python3 -m jmerge.reuse`
         ci' = [ci EXCEPT ![p] = IF reuse THEN "pass" ELSE "none"]
    /\ proved' = [proved EXCEPT ![p] = FALSE]
    /\ UNCHANGED <<st, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, Machine,
                   named, fixes, Browser, go, needs, meets, Judge, editsLeft>>

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
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, on, Machine,
                   Fix, Browser, needs, meets, Judge>>

\* The crew fixes its own broken change: only when it sees the failure as its own. jbus tells the
\* crew's own thread once its turn ends, so no room is asked for, and its turn may leave a
\* process running.
CrewFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/rebase.py `sent = run.box.sent() for slug, pull in world.open.items():`, open ones only
    /\ ci[p] = "fail"
    /\ breaks[p]
    \* The crew's block answers `fix` whenever the check command fails in its worktree, before it
    \* ever looks at the base (features/crew/the-checks.md `elif [ "$here" = failed ]; then`): CI
    \* and the crew run the same selection, so a break of its own that failed CI fails there too,
    \* whether or not its check ran over a red main.
    /\ breaks' = [breaks EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ told' = [told EXCEPT ![p] = FALSE]
    /\ proved' = [proved EXCEPT ![p] = FALSE]
    /\ Leaves(p)
    /\ UNCHANGED <<st, ranRed, missed, mainRed, redBy, outsideLeft, fixRow, link, on, named, fixes, Browser,
                   go, needs, meets, Judge, editsLeft>>

\* Its own browser run failed, and the red is its own: main's last browser run passed, or the fix
\* jbus filed for it is over. jbus tells its crew, which fixes its change, and its checks run again.
BrowserFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/expedite.py `world.open.items()`, open ones only
    /\ brFail[p]                            \* features/jbus/src/jbus/expedite.py `ready.BROWSER_RED`, its browser run failed
    /\ ~brHold                              \* features/jmerge/src/jmerge/rows.py `if red and not proves(red, failed, ran):`
    /\ brBreaks' = [brBreaks EXCEPT ![p] = FALSE]
    /\ brFail' = [brFail EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ proved' = [proved EXCEPT ![p] = FALSE]
    /\ Leaves(p)
    /\ UNCHANGED <<st, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   named, fixes, viewBroken, brHold, go, needs, meets, Judge, editsLeft>>

\* jmerge judges a red pull request again: a check that failed over a base that has moved since
\* it started, and is green now, is checked again over today's base (#350): GitHub merges the
\* base into the branch and runs check again, and a broken change then fails as its own. No local
\* fresh check runs.
Rejudge(p) ==
    /\ st[p] = "open"                       \* features/jmerge/src/jmerge/cli.py `def judge(`, every open one
    /\ ci[p] = "fail"                       \* features/jmerge/src/jmerge/ready.py `def red_only`, red_only
    /\ ranRed[p]                            \* features/jmerge/src/jmerge/cli.py `moved = None if one.started is None else self.moved(one.base, one.started) if ( moved is None`, base moved
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `or (one.base == self.trunk and bool(self.main_state.red))`, base not red
    /\ ~told[p]                             \* features/jmerge/src/jmerge/rejudge.py `was.get("tip")`, once a head and tip
    /\ ci' = [ci EXCEPT ![p] = "none"]      \* features/jmerge/src/jmerge/rejudge.py `self.ask(one)`, GitHub merges the base in
    /\ UNCHANGED <<st, told, ranRed, missed, breaks, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   Fix, Browser, go, needs, meets, Judge, editsLeft>>

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
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   Fix, Browser, Row, Judge, editsLeft>>

\* jbus reruns main's failed push run once (#672). A red from outside may be a flake, which the
\* rerun passes: main is green with nothing filed. A merge's red fails again.
RerunEnds ==
    /\ rerun                                \* features/jbus/src/jbus/watch.py `if bad and first and _rerun_failed(run, first, ask=rerun):`
    /\ rerun' = FALSE
    /\ \E flake \in IF redBy = "outside" /\ culprit = "none" THEN BOOLEAN ELSE {FALSE} :
         /\ mainRed' = ~flake
         /\ redBy' = IF flake THEN "none" ELSE redBy
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, outsideLeft, fixRow, link, on, Machine, Fix, Browser, Row,
                   culprit, judged, revert, editsLeft>>

\* jbus.culprits judges main's tip, red after its one rerun: it reverts the one clear culprit
\* (#862), and files main's fix row for a red that has none: a red from outside (#392), a merge
\* on a red tip, a skew (#899), or a culprit whose row jbus reverted before (the model keeps one
\* revert at a time). A tip whose revert is open gets no row.
JudgeRed ==
    /\ mainRed                              \* features/jbus/src/jbus/culprits.py `if run.red is not None:`
    /\ ~rerun                               \* features/jbus/src/jbus/watch.py `run.red = RedTip(slug, sha, commits[place : place + since], pull, culprit)`, after its one rerun
    /\ ~judged
    /\ judged' = TRUE
    /\ IF culprit \in PRs /\ revert = "none"
         THEN /\ revert' = "open"           \* features/jbus/src/jbus/culprits.py `return None if reverts.revert(run, found) else "jbus could not open its revert"`
              /\ UNCHANGED fixRow
         ELSE /\ fixRow' = TRUE             \* features/jbus/src/jbus/culprits.py `_file(run, run.red.slug, run.red.sha, run.red.red, why)`
              /\ UNCHANGED revert
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, link, on, Machine, Fix, Browser,
                   Row, rerun, culprit, editsLeft>>

\* jmerge merges jbus's revert on its checks, with no review, and main is green again. The model's
\* revert merges only while its culprit is still the red tip's: once another merge landed on the
\* red tip, main's fix row ends the red, and jbus closes the revert.
RevertMerges ==
    /\ revert = "open"                      \* features/jmerge/src/jmerge/cli.py `reverted = not short and self.reverted(brief.stem, one)`
    /\ mainRed
    /\ culprit \in PRs
    /\ revert' = "none"
    /\ mainRed' = FALSE
    /\ redBy' = "none"
    /\ culprit' = "none"
    /\ judged' = FALSE
    /\ fixRow' = FALSE
    /\ fixes' = NoFix
    /\ proved' = NoFix
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, outsideLeft, link, on, Machine, named, Browser, Row,
                   rerun, editsLeft>>

\* jbus closes its revert still open once main's check passed at a later tip without it (#899).
RevertCloses ==
    /\ revert = "open"                      \* features/jbus/src/jbus/reverts.py `asked = run.run("gh", "pr", "close", one.pull, "--comment", comment)`
    /\ ~mainRed                             \* features/jbus/src/jbus/reverts.py `if main.red or not main.green:`
    /\ revert' = "none"
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   Fix, Browser, Row, rerun, culprit, judged, editsLeft>>

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
    /\ mainRed
    /\ fixRow                               \* features/jbus/src/jbus/watch.py `queue.add(run.state, name, top, [], text, user=run.user, ran_by=queue.PASS)`, queued by jbus's pass
    \* features/jbus/src/jbus/queue.py `if not named and filed(row, text):`, its go by rule
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ fixRow' = FALSE
    /\ \/ /\ mainRed' = FALSE
          /\ redBy' = "none"
          /\ fixes' = NoFix
          /\ proved' = NoFix
          /\ culprit' = "none"
          /\ judged' = FALSE
          /\ rerun' = FALSE
          /\ UNCHANGED ci
       \/ \E q \in PRs :
          /\ st[q] = "open"
          /\ Unordered(q)                     \* features/jbus/src/jbus/watch.py `in another open pull request only where that`
          /\ fixes' = [fixes EXCEPT ![q] = TRUE]
          /\ ci' = [ci EXCEPT ![q] = "none"]
          /\ proved' = [proved EXCEPT ![q] = FALSE]
                /\ UNCHANGED <<mainRed, redBy, culprit, judged, rerun>>
    /\ UNCHANGED <<st, ranRed, missed, breaks, told, outsideLeft, link, on, Machine, named, Browser,
                   go, needs, meets, revert, editsLeft>>

\* main's browser run fails, and jbus files its browser-red row (features/jbus/src/jbus/watch.py `prefix="browser-red-"`),
\* whose run then holds as main's red each pull request whose own browser run failed.
\* browser.yml runs on main only nightly, so the hold starts with its next run.
Nightly ==
    /\ viewBroken                           \* .github/workflows/browser.yml `schedule:`, its nightly run
    /\ ~brHold
    /\ brHold' = TRUE                       \* features/jmerge/src/jmerge/rows.py `if last is None or last.get("conclusion") in NOT_RED or str(last.get("id")) not in fixing:`, red and its fix open
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   Machine, Fix, brBreaks, brFail, viewBroken, Row, Judge, editsLeft>>

\* jbus's pass approves the browser-red row by rule too: jbus filed it from a red run, with the
\* same Decisions: line as main's fix row (#547). Its crew fixes main's view, and its row is over,
\* so main's last run, still red until the next nightly, holds nobody (features/jmerge/src/jmerge/rows.py `fixing = {row["slug"] for row in rows or [] if row.get("status") not in judgement.FINAL}`).
FixBrowser ==
    /\ brHold                               \* features/jbus/src/jbus/queue.py `if not named and filed(row, text):`, its go by rule
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ viewBroken' = FALSE
    /\ brHold' = FALSE
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   Machine, Fix, brBreaks, brFail, Row, Judge, editsLeft>>

\* You approve a row, which gives it its go again (`jbus queue approve`).
Approve(p) ==
    /\ ~go[p]                               \* features/jbus/src/jbus/queue.py `again = row.get("approved") and judgement.approved_text(row, text) and not row.get("held")`
    /\ go' = [go EXCEPT ![p] = TRUE]
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   Fix, Browser, needs, meets, Judge, editsLeft>>

\* You hold a row that is not merged (`jbus queue hold`), which takes its go back.
HoldRow(p) ==
    \* A merged row's hold holds nothing.
    /\ st[p] # "merged"                     \* features/jmerge/src/jmerge/rows.py `if row.get("status") in judgement.FINAL:`
    /\ go[p]                                \* features/jbus/src/jbus/queue.py `_hold(batch.row(verb.slug), by)`, features/jbus/src/jbus/queue.py `row.update(approved="", brief_sha="", held=True)`
    /\ go' = [go EXCEPT ![p] = FALSE]
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   Fix, Browser, needs, meets, Judge, editsLeft>>

\* Something outside the queue breaks main (a flake, a hand merge, a tool update): its check, or
\* its view, which only browser.yml sees.
OutsideBreak ==
    /\ outsideLeft > 0
    /\ outsideLeft' = outsideLeft - 1
    /\ \/ /\ ~mainRed
          /\ mainRed' = TRUE
          /\ redBy' = "outside"
          \* features/jbus/src/jbus/watch.py `if not slugs and not fixes and not main.red:`, features/jbus/src/jbus/watch.py `no briefed merge came in`: since #392 the fix row is filed for a
          \* red tip with no briefed merge in the day before it too, under the row's own name,
          \* once its rerun failed and jbus.culprits judged it (JudgeRed).
          /\ rerun' = TRUE
          /\ culprit' = "none"
          /\ judged' = FALSE
          /\ named' \in BOOLEAN
          /\ UNCHANGED <<viewBroken>>
       \/ /\ ~viewBroken
          /\ viewBroken' = TRUE
          /\ UNCHANGED <<mainRed, redBy, named, rerun, culprit, judged>>
    /\ UNCHANGED <<st, ci, ranRed, missed, breaks, told, fixRow, link, on, Machine, fixes, proved, brBreaks, brFail,
                   brHold, Row, revert, editsLeft>>

System == Sweep \/ Nightly \/ RerunEnds \/ JudgeRed \/ RevertMerges \/ RevertCloses \/ FixMain \/ FixBrowser
    \/ \E p \in PRs :
        Launch(p) \/ MeetsFix(p) \/ Check(p) \/ Merge(p) \/ Restack(p)
        \/ CrewFix(p) \/ BrowserFix(p) \/ Rejudge(p)

\* Your word: a row's go, and the lift of a hold that waits on you.
YourWord == \E p \in PRs : Approve(p) \/ Accept(p)

Next == System \/ OutsideBreak \/ YourWord \/ \E p \in PRs : HoldRow(p) \/ HomeEdits(p)

Spec == Init /\ [][Next]_vars

Settled == ~ENABLED System

TypeOK ==
    /\ st \in [PRs -> {"queued", "open", "merged"}]
    /\ ci \in [PRs -> {"none", "pass", "fail"}]
    /\ redBy \in {"none", "merge", "outside"}
    /\ link \in {"depends", "after", "none"}
    /\ on \in [PRs -> {"main"} \cup PRs]
    /\ full = (busy \/ \E p \in PRs : idle[p])
    /\ brHold => viewBroken
    /\ \A p \in PRs : proved[p] => mainRed /\ fixes[p]
    /\ go \in [PRs -> BOOLEAN]
    /\ culprit \in {"none", "skew", "many"} \cup PRs
    /\ revert \in {"none", "open"}
    /\ (rerun \/ judged \/ fixRow) => mainRed
    /\ missed \in [PRs -> BOOLEAN]

\* "Work never stops flowing: once nothing more happens on its own and main is green, it settles merged or waiting on your word."
\* Its words are those it had before fl-rules-1103: a pull request held on a protected path is open
\* and checked, so it waits on your word.
FlowsWhenGreen == (Settled /\ ~Red) => (\A p \in PRs : st[p] = "merged") \/ ENABLED YourWord

\* "A merge turns main red only through a test its check's selection missed, and then jbus reruns main's failed push run once and reverts the one clear culprit or files main's fix row."
\* Until it is judged, the red is in its one rerun or due its judgement; once judged, jbus's revert
\* is open, or main's fix row is filed, or that row's crew put the fix in an open pull request.
MergeRedsMainOnlyOnAMissedTest ==
    /\ \A p \in PRs : (st[p] = "merged" /\ breaks[p]) => missed[p]
    /\ redBy = "merge" =>
        /\ ~judged => rerun \/ ENABLED JudgeRed
        /\ judged => revert = "open" \/ fixRow \/ \E q \in PRs : fixes[q]

\* "Once nothing more happens on its own, the machine has room."
MachineNotLeftFull == Settled => ~full

\* "While main is red and nothing else can happen, its fix waits on nothing of yours but your word: the lift of a pull request you hold, or your approval of a row whose brief you must approve."
\* Since #547 jbus approves every fix row it files, main's and the browser run's, by rule, so no
\* approval of a fix row is yours.
MainFixWaitsOnlyOnYou == (Settled /\ Red) => ENABLED YourWord

\* For the chart only (FlowToday.chart.cfg): no change breaks a browser test of its own, though
\* main's view may still break from outside, and no brief is edited.
\* The chart reader holds TLC's whole state graph in memory, and the whole model (15M states)
\* does not fit; with the edit and an outside break both in it, TLC 2.19's -continue run of the
\* rule then named NoMergeTurnsMainRed threw while it printed a path. flow_canaries.py checks every rule on the
\* whole model.
ChartCut == editsLeft = 1 /\ \A p \in PRs : ~brBreaks[p]

\* A probe, no rule: the case README.md names by itself. Main's fix is in b, the merge_after
\* follow-up of a, and a's check failed over the red main: jmerge judges a again only once main is
\* green (Rejudge), and b merges only after a, so the fix waits on neither your word nor anything
\* else. Main's fix brief keeps the fix out of b there (Unordered), so TLC holds it.
FixAfterARedCheck ==
    /\ mainRed /\ link = "after" /\ fixes["b"]
    /\ st["a"] = "open" /\ ci["a"] = "fail" /\ ranRed["a"]
FixAfterARedCheckWaitsOnlyOnYou == (Settled /\ FixAfterARedCheck) => ENABLED YourWord
====
