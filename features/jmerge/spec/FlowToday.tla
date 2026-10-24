---- MODULE FlowToday ----
\* What jstack does today with two pull requests, a main that can go red, and a machine that can fill.
\* Code as of main 38726c35 (2026-10-23).
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
    /\ st[p] = "open"                       \* .github/workflows/check.yml:4, a pull request's check
    /\ ci[p] = "none"
    \* scripts/select_tests.py:153-154: only tests on Cross-cutting run on every diff, and
    \* test_module_size.py and test_view_sources.py are not on it, so a diff selects them by chance.
    /\ \E sel \in BOOLEAN :
        ci' = [ci EXCEPT ![p] = IF sel /\ (mainRed \/ breaks[p]) THEN "fail" ELSE "pass"]
    /\ ranRed' = [ranRed EXCEPT ![p] = mainRed]
    /\ UNCHANGED <<st, breaks, told, mainRed, redBy, outsideLeft, full>>

\* jmerge merges a pull request whose check passed.
Merge(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "pass"                       \* features/jmerge/src/jmerge/ready.py:935-936
    /\ ~mainRed                             \* features/jmerge/src/jmerge/rows.py:87
    /\ st' = [st EXCEPT ![p] = "merged"]
    /\ mainRed' = (mainRed \/ breaks[p])
    /\ redBy' = IF breaks[p] THEN "merge" ELSE redBy
    /\ UNCHANGED <<ci, ranRed, breaks, told, outsideLeft, full>>

\* The crew fixes its own broken change: only when it sees the failure as its own.
CrewFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/rebase.py:247, open ones only
    /\ ci[p] = "fail"
    /\ breaks[p]
    \* features/crew/the-checks.md:48,79: a failure over a base that moved reads as `stale`:
    \* no rerun, no commit, no rebase, and the crew waits for a message nothing sends.
    /\ ~ranRed[p]
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py:324-356, no room
    /\ breaks' = [breaks EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ full' \in BOOLEAN                    \* a turn may leave processes running; nothing stops them
    /\ UNCHANGED <<st, ranRed, told, mainRed, redBy, outsideLeft>>

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

System == \E p \in PRs : Check(p) \/ Merge(p) \/ CrewFix(p)

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
