---- MODULE FlowToday ----
\* What jstack does today with two pull requests, a main that can go red, and a machine that can fill.
\* Code as of main 479438dd (2026-10-25): the flow-statechart scout's FlowNow.tla at 6485914, with
\* #416, #426 and #427 since, cut down to the variables FlowDesign.tla's four rules read.
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
\* link: how b is ordered after a. "depends" when b's brief builds on a, "after" when the order
\*   is only about merging (merge_after).
\* on: what a pull request sits on, "main" or the other one (its brief's `Stacked on:` line, #411).
\* fixRow: a main-red-<sha> row is queued for main's fix, with no approval.
\* busy: a process a finished turn left that uses CPU. idle[p]: one p's crew left that uses none
\*   but holds memory. full is TRUE exactly when one of them is left: TLC takes the worst case,
\*   where what is left is what tips jgauge room over.
VARIABLES st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, link, on, busy, idle
vars == <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, link, on, busy, idle>>

Init ==
    /\ st = [p \in PRs |-> "queued"]
    /\ ci = [p \in PRs |-> "none"]
    /\ ranRed = [p \in PRs |-> FALSE]
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

Machine == <<full, busy, idle>>

\* A turn of p's crew ends, and may leave a process running: busy, idle, or none.
Leaves(p) ==
    \E kind \in {"none", "busy", "idle"} :
        /\ busy' = (busy \/ kind = "busy")
        /\ idle' = [idle EXCEPT ![p] = idle[p] \/ kind = "idle"]
        /\ full' = (busy' \/ \E x \in PRs : idle'[x])

\* A jbus pass launches the row's crew, which opens its pull request, and its turn ends.
Launch(p) ==
    /\ st[p] = "queued"
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py:324-356, no room
    \* A row that builds on an open one launches stacked on its branch (#411), and one that builds
    \* on a row with no pull request yet waits; merge_after is read only by jmerge.
    /\ (p = "b" /\ link = "depends") => st["a"] # "queued"   \* features/jbus/src/jbus/dispatch.py:459-461
    /\ st' = [st EXCEPT ![p] = "open"]
    /\ on' = [on EXCEPT ![p] = IF p = "b" /\ link = "depends" /\ st["a"] = "open" THEN "a" ELSE "main"]
    /\ Leaves(p)
    /\ UNCHANGED <<ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link>>

\* GitHub runs the pull request's check over the base as it is now.
Check(p) ==
    /\ st[p] = "open"                       \* .github/workflows/check.yml:4, a pull request's check
    /\ ci[p] = "none"
    \* scripts/select_tests.py:666-675,385: the rules' tests, every test no rule owns (#397), and
    \* each test whose READ_SET matches the changed path (#426). A test that reads the tree through
    \* a glob or a walk needs a read set, but that guard sees only the reads it knows, so a test
    \* that reads the changed path another way, or past its read set, is selected by chance.
    /\ \E sel \in BOOLEAN :
        ci' = [ci EXCEPT ![p] = IF sel /\ (mainRed \/ breaks[p]) THEN "fail" ELSE "pass"]
    /\ ranRed' = [ranRed EXCEPT ![p] = mainRed]
    /\ UNCHANGED <<st, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine>>

\* jmerge merges a pull request whose check passed.
Merge(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "pass"                       \* features/jmerge/src/jmerge/ready.py:935-936
    /\ ~mainRed                             \* features/jmerge/src/jmerge/rows.py:87
    \* A link jbus stacked merges only once jbus moved it onto main and its head holds its base's merge.
    /\ on[p] = "main"                       \* features/jmerge/src/jmerge/cli.py:684-692
    \* A merge_after row merges after its row.
    /\ (p = "b" /\ link = "after") => st["a"] = "merged"   \* features/jmerge/src/jmerge/rows.py:135-138
    /\ st' = [st EXCEPT ![p] = "merged"]
    /\ mainRed' = (mainRed \/ breaks[p])
    /\ redBy' = IF breaks[p] THEN "merge" ELSE redBy
    \* features/jbus/src/jbus/watch.py:1379-1380: main's red tip after a briefed merge is filed.
    /\ fixRow' = (fixRow \/ breaks[p])
    /\ UNCHANGED <<ci, ranRed, breaks, told, outsideLeft, link, on, Machine>>

\* Its base merged: jbus moves the stacked pull request onto main and tells its crew, which
\* rebases its own commits onto main ("A link that moved"), and its check runs again.
Restack(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/stack.py:65, open ones only
    /\ on[p] # "main"
    /\ st[on[p]] = "merged"                 \* features/jbus/src/jbus/stack.py:72-73, its base merged
    /\ on' = [on EXCEPT ![p] = "main"]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ UNCHANGED <<st, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, Machine>>

\* The crew fixes its own broken change: only when it sees the failure as its own. jbus sends to
\* a thread already running, so no room is asked for, and its turn may leave a process running.
CrewFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/rebase.py:250, open ones only
    /\ ci[p] = "fail"
    /\ breaks[p]
    \* A failure over a base that moved reads as `stale`, and the crew waits for jmerge's one
    \* message, which jbus sends it.
    /\ (~ranRed[p] \/ told[p])              \* features/crew/the-checks.md:79-84
    /\ breaks' = [breaks EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ told' = [told EXCEPT ![p] = FALSE]
    /\ Leaves(p)
    /\ UNCHANGED <<st, ranRed, mainRed, redBy, outsideLeft, fixRow, link, on>>

\* jmerge judges a red pull request again: a check that failed over a base that has moved since
\* it started, and is green now, is checked again over today's base (#350). With a fresh-check
\* file a really broken change fails there and its crew gets one message; otherwise GitHub merges
\* the base into the branch and runs check again, and a broken change then fails as its own.
Rejudge(p) ==
    /\ st[p] = "open"                       \* features/jmerge/src/jmerge/cli.py:1102, every open one
    /\ ci[p] = "fail"                       \* features/jmerge/src/jmerge/ready.py:294-297, red_only
    /\ ranRed[p]                            \* features/jmerge/src/jmerge/cli.py:1058-1059, base moved
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py:1175, base not red
    /\ ~told[p]                             \* features/jmerge/src/jmerge/cli.py:217, once a head and tip
    /\ \E fresh \in BOOLEAN :               \* features/jmerge/src/jmerge/cli.py:1063, a fresh-check file
        IF fresh /\ breaks[p]
            \* features/jmerge/src/jmerge/cli.py:1064-1066: it fails over today's base, one message
            THEN /\ told' = [told EXCEPT ![p] = TRUE] /\ UNCHANGED ci
            \* features/jmerge/src/jmerge/rejudge.py:63: GitHub merges the base in, check runs again
            ELSE /\ ci' = [ci EXCEPT ![p] = "none"] /\ UNCHANGED told
    /\ UNCHANGED <<st, ranRed, breaks, mainRed, redBy, outsideLeft, fixRow, link, on, Machine>>

\* What jbus.strays may stop of an idle process p's crew left. A crew at work is never touched
\* (features/jbus/src/jbus/strays.py:356), and in this model a crew's turn is one step.
Stoppable(p) ==
    CASE Gap = "busy" -> FALSE
      [] Gap = "ended" -> st[p] = "merged"
      [] Gap = "turn" -> TRUE

\* jbus.strays stops what a finished turn left (#351, #363, #416, #427): a busy process, and an
\* idle one only as Gap says.
Sweep ==
    /\ busy \/ \E p \in PRs : idle[p] /\ Stoppable(p)   \* features/jbus/src/jbus/strays.py:373-374,382
    /\ busy' = FALSE
    /\ idle' = [p \in PRs |-> idle[p] /\ ~Stoppable(p)]
    /\ full' = (\E p \in PRs : idle'[p])
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on>>

\* You approve the main-red row jbus filed, and its crew fixes main.
ApproveMainFix ==
    /\ mainRed
    /\ fixRow                               \* features/jbus/src/jbus/watch.py:1034-1054, queued with no approval
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py:324-356, no room
    /\ mainRed' = FALSE
    /\ redBy' = "none"
    /\ fixRow' = FALSE
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, outsideLeft, link, on, Machine>>

\* Something outside the queue breaks main (a flake, a hand merge, a tool update).
OutsideBreak ==
    /\ outsideLeft > 0
    /\ ~mainRed
    /\ mainRed' = TRUE
    /\ redBy' = "outside"
    /\ outsideLeft' = outsideLeft - 1
    \* features/jbus/src/jbus/watch.py:1330,1373,1377,1380: since #392 the fix row is filed for a red
    \* tip with no briefed merge in the day before it too, under the row's own name.
    /\ fixRow' = TRUE
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, link, on, Machine>>

System == Sweep \/ \E p \in PRs :
    Launch(p) \/ Check(p) \/ Merge(p) \/ Restack(p) \/ CrewFix(p) \/ Rejudge(p)

Next == System \/ ApproveMainFix \/ OutsideBreak

Spec == Init /\ [][Next]_vars

Settled == ~ENABLED System

TypeOK ==
    /\ st \in [PRs -> {"queued", "open", "merged"}]
    /\ ci \in [PRs -> {"none", "pass", "fail"}]
    /\ redBy \in {"none", "merge", "outside"}
    /\ on \in [PRs -> {"main"} \cup PRs]
    /\ full = (busy \/ \E p \in PRs : idle[p])

\* "Work never stops flowing: once nothing more happens on its own and main is green, every pull request has merged."
FlowsWhenGreen == (Settled /\ ~mainRed) => \A p \in PRs : st[p] = "merged"

\* "A merge never turns main red."
NoMergeTurnsMainRed == redBy # "merge"

\* "Once nothing more happens on its own, the machine has room."
MachineNotLeftFull == Settled => ~full

\* "While main is red and nothing else can happen, its fix waits only on your approval."
MainFixWaitsOnlyOnYou == (Settled /\ mainRed) => ENABLED ApproveMainFix
====
