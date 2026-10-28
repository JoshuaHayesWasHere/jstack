---- MODULE NoProof ----
\* The design: today's code with cross-cutting-guard (#349), rejudge-red-prs and crew-leftover-procs.
\* Main's fix comes as today's does (#583): the main-red row jbus files, whose crew fixes main or
\* ends with no pull request, its fix in an open one, which merges past the red once its own check
\* proves the fix. The design takes the red run's logs to name the tests that failed there, which
\* the code does not always have (FlowToday.tla's `named`).
EXTENDS Naturals

PRs == {"a", "b"}

\* fixRow: a main-red-<sha> row is queued for main's fix, with no approval.
\* fixes[p]: p's head carries main's fix. proved[p]: p's check, over main's red tip, passed the
\*   tests that failed there.
VARIABLES st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, fixes, proved
vars == <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, fixes, proved>>

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
    /\ fixRow = FALSE
    /\ fixes = [p \in PRs |-> FALSE]
    /\ proved = [p \in PRs |-> FALSE]

NoFix == [p \in PRs |-> FALSE]

\* GitHub runs the pull request's check over the base as it is now.
Check(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "none"
    \* cross-cutting-guard: every test that reads the whole tree is on Cross-cutting, so it always runs.
    \* So it runs the tests main failed too, and a check of main's fix proves it.
    /\ ci' = [ci EXCEPT ![p] = IF (mainRed /\ ~fixes[p]) \/ breaks[p] THEN "fail" ELSE "pass"]
    /\ proved' = [proved EXCEPT ![p] = mainRed /\ fixes[p] /\ ~breaks[p]]
    /\ ranRed' = [ranRed EXCEPT ![p] = mainRed]
    /\ UNCHANGED <<st, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, fixes>>

\* jmerge merges a pull request whose check passed.
Merge(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "pass"                       \* features/jmerge/src/jmerge/ready.py:1068-1070
    /\ ~mainRed                             \* features/jmerge/src/jmerge/rows.py:139, as before #583
    /\ st' = [st EXCEPT ![p] = "merged"]
    /\ mainRed' = ((mainRed /\ ~proved[p]) \/ breaks[p])
    /\ redBy' = IF breaks[p] THEN "merge" ELSE IF proved[p] THEN "none" ELSE redBy
    /\ fixRow' = ((fixRow /\ ~proved[p]) \/ breaks[p])
    /\ fixes' = IF proved[p] THEN NoFix ELSE fixes
    /\ proved' = IF proved[p] THEN NoFix ELSE proved
    /\ UNCHANGED <<ci, ranRed, breaks, told, outsideLeft, full>>

\* The crew fixes its own broken change: only when it sees the failure as its own.
CrewFix(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "fail"
    /\ breaks[p]
    \* rejudge-red-prs: the crew acts on its own failure, or on jmerge's one message. The crew of a
    \* pull request that carries main's fix reads a failure over that red as its own, since main
    \* goes green only once it merges: a step the code lacks (FlowToday.tla's CrewFix).
    /\ (~ranRed[p] \/ told[p] \/ fixes[p])
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py:332-364, no room
    /\ breaks' = [breaks EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ full' \in BOOLEAN                    \* a turn may leave processes running
    /\ told' = [told EXCEPT ![p] = FALSE]
    /\ proved' = [proved EXCEPT ![p] = FALSE]
    /\ UNCHANGED <<st, ranRed, mainRed, redBy, outsideLeft, fixRow, fixes>>

\* rejudge-red-prs: a pull request whose check failed, over a base that has moved since the check
\* started and is green now, is checked again over today's base: GitHub merges the base into
\* the branch and runs check again, and a broken change then fails as its own.
Rejudge(p) ==
    /\ st[p] = "open"                       \* features/jmerge/src/jmerge/cli.py:771, every open one
    /\ ci[p] = "fail"                       \* features/jmerge/src/jmerge/ready.py:398-401, red_only
    /\ ranRed[p]                            \* features/jmerge/src/jmerge/cli.py:742, base moved
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py:845, base not red
    /\ ~told[p]                             \* features/jmerge/src/jmerge/rejudge.py:93, once a head and tip
    /\ ci' = [ci EXCEPT ![p] = "none"]      \* features/jmerge/src/jmerge/rejudge.py:73, GitHub merges the base in
    /\ UNCHANGED <<st, told, ranRed, breaks, mainRed, redBy, outsideLeft, full, fixRow, fixes, proved>>

\* crew-leftover-procs: when a turn ends, what it left running is stopped.
Sweep ==
    /\ full
    /\ full' = FALSE
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, fixes, proved>>

\* You approve the main-red row jbus filed, and its crew fixes main in its own pull request, or
\* ends with no pull request, its fix in an open one. Either way the row is over.
ApproveMainFix ==
    /\ mainRed
    /\ fixRow
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py:332-364, no room
    /\ fixRow' = FALSE
    /\ \/ /\ mainRed' = FALSE
          /\ redBy' = "none"
          /\ fixes' = NoFix
          /\ proved' = NoFix
          /\ UNCHANGED ci
       \/ \E q \in PRs :
          /\ st[q] = "open"
          /\ fixes' = [fixes EXCEPT ![q] = TRUE]
          /\ ci' = [ci EXCEPT ![q] = "none"]
          /\ proved' = [proved EXCEPT ![q] = FALSE]
          /\ UNCHANGED <<mainRed, redBy>>
    /\ UNCHANGED <<st, ranRed, breaks, told, outsideLeft, full>>

\* Something outside the queue breaks main (a flake, a hand merge, a tool update).
OutsideBreak ==
    /\ outsideLeft > 0
    /\ ~mainRed
    /\ mainRed' = TRUE
    /\ redBy' = "outside"
    /\ outsideLeft' = outsideLeft - 1
    /\ fixRow' = TRUE
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, full, fixes, proved>>

System == Sweep \/ \E p \in PRs : Check(p) \/ Merge(p) \/ CrewFix(p) \/ Rejudge(p)

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
