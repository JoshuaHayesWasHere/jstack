---- MODULE NoGuard ----
\* The design: today's code with cross-cutting-guard (#349), rejudge-red-prs and crew-leftover-procs.
\* Main's fix comes as today's does (#583): the main-red row jbus files, whose crew fixes main or
\* ends with no pull request, its fix in an open one, which merges past the red once its own check
\* passes: every test that reads the whole tree runs in it (cross-cutting-guard), so it runs the tests
\* main failed. The design differs from the code on purpose; FlowToday.tla is the code.
EXTENDS Naturals

PRs == {"a", "b"}

\* fixRow: a main-red-<sha> row is queued for main's fix, with no approval.
\* fixes[p]: p's head carries main's fix.
VARIABLES st, ci, ranRed, breaks, mainRed, redBy, outsideLeft, full, fixRow, fixes
vars == <<st, ci, ranRed, breaks, mainRed, redBy, outsideLeft, full, fixRow, fixes>>

Init ==
    /\ st = [p \in PRs |-> "open"]
    /\ ci = [p \in PRs |-> "none"]
    /\ ranRed = [p \in PRs |-> FALSE]
    /\ breaks \in [PRs -> BOOLEAN]          \* the change breaks a test that reads the whole tree
    /\ mainRed = FALSE
    /\ redBy = "none"
    /\ outsideLeft = 1
    /\ full = FALSE
    /\ fixRow = FALSE
    /\ fixes = [p \in PRs |-> FALSE]

NoFix == [p \in PRs |-> FALSE]

\* GitHub runs the pull request's check over the base as it is now.
Check(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "none"
    \* cross-cutting-guard: every test that reads the whole tree is on Cross-cutting, so it always runs.
    \* So it runs the tests main failed too, and a check of main's fix proves it.
    /\ \E sel \in BOOLEAN :
        ci' = [ci EXCEPT ![p] = IF sel /\ ((mainRed /\ ~fixes[p]) \/ breaks[p]) THEN "fail" ELSE "pass"]
    /\ ranRed' = [ranRed EXCEPT ![p] = mainRed]
    /\ UNCHANGED <<st, breaks, mainRed, redBy, outsideLeft, full, fixRow, fixes>>

\* jmerge merges a pull request whose check passed.
Merge(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "pass"                       \* features/jmerge/src/jmerge/ready.py `(CHECK_FAILED if failed else NOT_PASSED).format(check=one.waiting[0])`
    /\ st' = [st EXCEPT ![p] = "merged"]
    /\ mainRed' = ((mainRed /\ ~fixes[p]) \/ breaks[p])
    /\ redBy' = IF breaks[p] THEN "merge" ELSE IF fixes[p] THEN "none" ELSE redBy
    /\ fixRow' = ((fixRow /\ ~fixes[p]) \/ breaks[p])
    /\ fixes' = IF fixes[p] THEN NoFix ELSE fixes
    /\ UNCHANGED <<ci, ranRed, breaks, outsideLeft, full>>

\* The crew fixes its own broken change: only when it sees the failure as its own.
CrewFix(p) ==
    /\ st[p] = "open"
    /\ ci[p] = "fail"
    /\ breaks[p]
    \* rejudge-red-prs: the crew acts on a failure over a green base as its own. The crew of a pull
    \* request that carries main's fix reads a failure over that red as its own too, since main
    \* goes green only once it merges. The code has the step since #946, and wider: its crew answers
    \* `fix` whenever the check fails in its worktree (FlowToday.tla's CrewFix).
    /\ (~ranRed[p] \/ fixes[p])
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ breaks' = [breaks EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ full' \in BOOLEAN                    \* a turn may leave processes running
    /\ UNCHANGED <<st, ranRed, mainRed, redBy, outsideLeft, fixRow, fixes>>

\* rejudge-red-prs: a pull request whose check failed, over a base that has moved since the check
\* started and is green now, is checked again over today's base: GitHub merges the base into
\* the branch and runs check again, and a broken change then fails as its own. The code asks once a
\* head and tip (base-merges.json) and takes its turn in main's line; the design needs neither, since
\* a check over a green base leaves nothing to judge again (FlowToday.tla's Rejudge).
Rejudge(p) ==
    /\ st[p] = "open"                       \* features/jmerge/src/jmerge/cli.py `def judge(`, every open one
    /\ ci[p] = "fail"                       \* features/jmerge/src/jmerge/ready.py `def red_only`, red_only
    /\ ranRed[p]                            \* features/jmerge/src/jmerge/cli.py `moved = None if one.started is None else self.moved(one.base, one.started) if ( moved is None`, base moved
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `or (one.base == self.trunk and bool(self.main_state.red))`, base not red
    /\ ci' = [ci EXCEPT ![p] = "none"]      \* features/jmerge/src/jmerge/rejudge.py `self.ask(one)`, GitHub merges the base in
    /\ UNCHANGED <<st, ranRed, breaks, mainRed, redBy, outsideLeft, full, fixRow, fixes>>

\* crew-leftover-procs: when a turn ends, what it left running is stopped.
Sweep ==
    /\ full
    /\ full' = FALSE
    /\ UNCHANGED <<st, ci, ranRed, breaks, mainRed, redBy, outsideLeft, fixRow, fixes>>

\* The main-red row jbus filed is approved, and its crew fixes main in its own pull request, or ends
\* with no pull request, its fix in an open one. Either way the row is over. The design has it as
\* your approval; since #547 jbus's pass approves the row by rule (FlowToday.tla's FixMain).
ApproveMainFix ==
    /\ mainRed
    /\ fixRow
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ fixRow' = FALSE
    /\ \/ /\ mainRed' = FALSE
          /\ redBy' = "none"
          /\ fixes' = NoFix
          /\ UNCHANGED ci
       \/ \E q \in PRs :
          /\ st[q] = "open"
          /\ fixes' = [fixes EXCEPT ![q] = TRUE]
          /\ ci' = [ci EXCEPT ![q] = "none"]
          /\ UNCHANGED <<mainRed, redBy>>
    /\ UNCHANGED <<st, ranRed, breaks, outsideLeft, full>>

\* Something outside the queue breaks main (a flake, a hand merge, a tool update).
OutsideBreak ==
    /\ outsideLeft > 0
    /\ ~mainRed
    /\ mainRed' = TRUE
    /\ redBy' = "outside"
    /\ outsideLeft' = outsideLeft - 1
    /\ fixRow' = TRUE
    /\ UNCHANGED <<st, ci, ranRed, breaks, full, fixes>>

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
