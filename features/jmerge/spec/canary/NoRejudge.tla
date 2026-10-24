---- MODULE NoRejudge ----
\* The design: today's code with cross-cutting-guard (#349), rejudge-red-prs and crew-leftover-procs.
EXTENDS Naturals

PRs == {"a", "b"}

VARIABLES st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, full
vars == <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, full>>

Init ==
    /\ st = [p \in PRs |-> "open"]
    /\ ci = [p \in PRs |-> "none"]
    /\ ranRed = [p \in PRs |-> FALSE]
    /\ breaks \in [PRs -> BOOLEAN]          \* the change breaks a test that reads the whole tree
    /\ told = [p \in PRs |-> FALSE]
    /\ mainRed = FALSE
    /\ redBy = "none"
    /\ outsideLeft = 1
    /\ full = FALSE

\* GitHub runs the pull request's check over the base as it is now.
Check(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "none"
    \* cross-cutting-guard: every test that reads the whole tree is on Cross-cutting, so it always runs.
    /\ ci' = [ci EXCEPT ![p] = IF mainRed \/ breaks[p] THEN "fail" ELSE "pass"]
    /\ ranRed' = [ranRed EXCEPT ![p] = mainRed]
    /\ UNCHANGED <<st, breaks, told, mainRed, redBy, outsideLeft, full>>

\* jmerge merges a pull request whose check passed.
Merge(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "pass"                       \* features/jmerge/src/jmerge/ready.py:918-919
    /\ ~mainRed                             \* features/jmerge/src/jmerge/rows.py:87
    /\ st' = [st EXCEPT ![p] = "merged"]
    /\ mainRed' = (mainRed \/ breaks[p])
    /\ redBy' = IF breaks[p] THEN "merge" ELSE redBy
    /\ UNCHANGED <<ci, ranRed, breaks, told, outsideLeft, full>>

\* The crew fixes its own broken change: only when it sees the failure as its own.
CrewFix(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "fail"
    /\ breaks[p]
    \* rejudge-red-prs: the crew acts on its own failure, or on jmerge's one message.
    /\ (~ranRed[p] \/ told[p])
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py:324-356, no room
    /\ breaks' = [breaks EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ full' \in BOOLEAN                    \* a turn may leave processes running
    /\ told' = [told EXCEPT ![p] = FALSE]
    /\ UNCHANGED <<st, ranRed, mainRed, redBy, outsideLeft>>

\* rejudge-red-prs: a pull request whose check failed, over a base that has moved since the check
\* started and is green now, is checked again over today's base. With a fresh-check file a really
\* broken change fails there and its crew gets one message; otherwise GitHub merges the base into
\* the branch and runs check again, and a broken change then fails as its own.
Rejudge(p) ==
    /\ st[p] = "open"                       \* features/jmerge/src/jmerge/cli.py:1083, every open one
    /\ ci[p] = "fail"                       \* features/jmerge/src/jmerge/ready.py:289-292, red_only
    /\ ranRed[p]                            \* features/jmerge/src/jmerge/cli.py:1039-1040, base moved
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py:1154, base not red
    /\ ~told[p]                             \* features/jmerge/src/jmerge/cli.py:216, once a head and tip
    /\ \E fresh \in BOOLEAN :               \* features/jmerge/src/jmerge/cli.py:1044, a fresh-check file
        IF fresh /\ breaks[p]
            \* features/jmerge/src/jmerge/cli.py:1045-1047: it fails over today's base, one message
            THEN /\ told' = [told EXCEPT ![p] = TRUE] /\ UNCHANGED ci
            \* features/jmerge/src/jmerge/rejudge.py:63: GitHub merges the base in, check runs again
            ELSE /\ ci' = [ci EXCEPT ![p] = "none"] /\ UNCHANGED told
    /\ UNCHANGED <<st, ranRed, breaks, mainRed, redBy, outsideLeft, full>>

\* crew-leftover-procs: when a turn ends, what it left running is stopped.
Sweep ==
    /\ full
    /\ full' = FALSE
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft>>

\* You approve the main-red row jbus filed, and its crew fixes main.
ApproveMainFix ==
    /\ mainRed
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py:324-356, no room
    /\ mainRed' = FALSE
    /\ redBy' = "none"
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, outsideLeft, full>>

\* Something outside the queue breaks main (a flake, a hand merge, a tool update).
OutsideBreak ==
    /\ outsideLeft > 0
    /\ ~mainRed
    /\ mainRed' = TRUE
    /\ redBy' = "outside"
    /\ outsideLeft' = outsideLeft - 1
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, full>>

System == Sweep \/ \E p \in PRs : Check(p) \/ Merge(p) \/ CrewFix(p)

Next == System \/ ApproveMainFix \/ OutsideBreak

Spec == Init /\ [][Next]_vars

Settled == ~ENABLED System

TypeOK ==
    /\ st \in [PRs -> {"open", "merged"}]
    /\ ci \in [PRs -> {"none", "pass", "fail"}]
    /\ redBy \in {"none", "merge", "outside"}

\* "Work never stops flowing: once nothing more happens on its own and main is green, every pull request has merged."
FlowsWhenGreen == (Settled /\ ~mainRed) => \A p \in PRs : st[p] = "merged"

\* "A merge never turns main red."
NoMergeTurnsMainRed == redBy # "merge"

\* "Once nothing more happens on its own, the machine has room."
MachineNotLeftFull == Settled => ~full

\* "While main is red and nothing else can happen, its fix waits only on your approval."
MainFixWaitsOnlyOnYou == (Settled /\ mainRed) => ENABLED ApproveMainFix
====
