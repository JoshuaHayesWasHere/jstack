---- MODULE HomeTreeToday ----
\* Today's code, at main f2b8921b. A child home is a scoped home (scoped-homes.md), the root is
\* the repo's root home, and jbus's pass is the root's check. Each condition of a step names the
\* file and line that checks it: jbus/ is features/jbus/src/jbus/, jmerge/ is
\* features/jmerge/src/jmerge/, jbriefs/ is features/jbriefs/src/jbriefs/, and the skills are in
\* features/home/skills/home/ and features/crew/skills/crew/.
EXTENDS HomeTree

Set(f, k, v) == [f EXCEPT ![k] = v]

\* ---- a child's own steps

\* Only the root home makes a scope, on the user's word (scoped-homes.md:12).
MakeChild(k) ==
    /\ k \in Made /\ life[k] = "unmade" /\ life' = Set(life, k, "working")
    /\ UNCHANGED <<work, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The child home queues a brief and jbus's pass launches its crew.
LaunchCrew(k) ==
    /\ life[k] = "working"     \* jbus/dispatch.py:517 a running home's queued row is launched
    /\ work[k] = "none" /\ work' = Set(work, k, "crew") /\ quiet' = Set(quiet, k, 0)
    /\ UNCHANGED <<life, msg, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The crew opens the pull request ("Do the task" in the crew skill).
OpenPr(k) ==
    /\ work[k] = "crew" /\ work' = Set(work, k, "open")
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* Its checks pass (jmerge/ready.py:887) and its review is written (jmerge/ready.py:591).
PrReady(k) ==
    /\ work[k] \in {"open", "again"}
    /\ work' = Set(work, k, IF work[k] = "open" THEN "ready" ELSE "back")
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* A check turns red or a review goes stale (jmerge/ready.py:887, jmerge/ready.py:591): the
\* pull request is not ready, and jmerge judges it again.
PrDrops(k) ==
    /\ work[k] = "ready" /\ work' = Set(work, k, "again")
    /\ seen' = Set(seen, k, [b \in Mergers |-> NoTip])
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, blind, lock, mode>>
\* A crew stays on its pull request until it merges ("Stay on the pull request" in the crew
\* skill), and T3 Code settles it then.
CrewEnds(k) ==
    /\ work[k] = "merged" /\ work' = Set(work, k, "done")
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* A gate or an item for Josh goes into the outbox of each route the setting picks, once: its
\* key is in sent.json from then on, so it is never queued again (jbus/wake.py:349-352). The
\* model's setting picks one route, home or webhook, and leaves out both.
RaiseCall(c) ==
    /\ c \in Raised
    /\ life[OwnerOf[c]] = "working"     \* jbus/mirror.py:182 the scope's gates.md is read too
    /\ msg[c] = "none" /\ msg' = Set(msg, c, wake)     \* jbus/wake.py:355 self.routes
    /\ quiet' = Set(quiet, OwnerOf[c], 0)
    /\ UNCHANGED <<life, work, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The child does something jbus can see: a turn in its thread, a commit, a push.
Activity(k) ==
    /\ life[k] = "working"     \* jbus/live.py:63 a thread silent under QUIET_MINUTES is moving
    /\ quiet' = Set(quiet, k, 0)
    /\ UNCHANGED <<life, work, msg, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The child stops: its turn ended and nothing will wake it. Only the child could tell.
GetsStuck(k) ==
    /\ life[k] = "working" /\ life' = Set(life, k, "stuck")
    /\ UNCHANGED <<work, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The root or Josh retires a child by hand: the scope's handoff.md says so, and nothing checks
\* what it still has out (scoped-homes.md:6). A brief of a scope with no home-id and no Was home
\* line falls back to the root (jbriefs/home.py:59).
Retire(k) ==
    /\ life[k] \in {"working", "stuck"} /\ life' = Set(life, k, "retired")
    /\ UNCHANGED <<work, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>

\* ---- Josh, and the routes

Answer(c) ==
    /\ msg[c] = "told" /\ msg' = Set(msg, c, "none")
    /\ UNCHANGED <<life, work, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* A pass posts what waits in the outbox of each route the setting picks, and only those: a
\* route the setting leaves out keeps what waits for it, which goes only if the setting picks
\* the route again (jbus/alert.py:296-306). A post that fails leaves it in the outbox.
Deliver(m) ==
    \E r \in Routes :
        /\ msg[m] = r
        /\ r = wake     \* jbus/alert.py:318 for route in run.box.routes
        /\ up[r]        \* jbus/wake.py:599 a post that fails breaks the flush
        /\ msg' = Set(msg, m, "told")
        /\ UNCHANGED <<life, work, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock,
                       mode>>
\* The wake setting changes between home and webhook (jbus/__init__.py:117-121).
ChangeWake ==
    /\ RoutesMove
    /\ ~moved /\ moved' = TRUE
    /\ wake' = IF wake = "home" THEN "webhook" ELSE "home"
    /\ UNCHANGED <<life, work, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
RouteFails(r) ==
    /\ RoutesMove
    /\ ~broke /\ broke' = TRUE
    /\ up[r] /\ up' = Set(up, r, FALSE)
    /\ UNCHANGED <<life, work, msg, quiet, watch, wake, moved, tip, seen, blind, lock, mode>>
RouteMends(r) ==
    /\ ~up[r] /\ up' = Set(up, r, TRUE)
    /\ UNCHANGED <<life, work, msg, quiet, watch, wake, moved, broke, tip, seen, blind, lock, mode>>

\* ---- the root's check, one jbus pass

\* jbus counts the silence of every thread, but tells nobody: a hung thread is a quiet event,
\* logged and never posted (jbus/stall.py:57, jbus/stall.py:435), and the root home is sent
\* nothing while a scope works (scoped-homes.md:6). Nothing flags a child, nudges it or asks.
Check ==
    /\ quiet' = Ticked
    /\ UNCHANGED <<life, work, msg, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>

\* ---- merging: a read of main's tip, then the merge

\* Who may merge a child's pull request. On jbus merges, jbus runs jmerge only while the root's
\* home-thread is empty, as the root, and a child's pull request waits as another home's. On
\* home merges, the child runs jmerge for its own, and the root may add --all.
MayMerge(a, k) ==
    /\ mode = "home"     \* jbus/merge.py:148 jbus runs jmerge only with no home-thread
    /\ a \in {"root", "child"}     \* jmerge/cli.py:1067 another home's waits, without --all
    /\ a = "child" => life[k] = "working"     \* jmerge/cli.py:715-717 a retired home is NOBODY
\* jmerge checks that main's tip is still the one it judged (jmerge/cli.py:1343-1344) and then
\* merges (jmerge/cli.py:1368). No lock spans the gap between the two, and two runners can run
\* at once (merging-a-pull-request-that-is-ready.md:5).
Read(a, k) ==
    /\ MayMerge(a, k)     \* jmerge/cli.py:1067 each runner judges its own home's pull requests
    /\ Ready(k)     \* jmerge/cli.py:1166 the judgement is ready
    /\ seen[k][a] = NoTip /\ seen' = [seen EXCEPT ![k][a] = tip]     \* jmerge/cli.py:1343
    /\ UNCHANGED <<life, work, msg, quiet, watch, wake, moved, up, broke, tip, blind, lock, mode>>
Merge(a, k) ==
    /\ seen[k][a] # NoTip     \* jmerge/cli.py:1344 the tip it read is the one it judged
    /\ Ready(k) /\ work' = Set(work, k, "merged")     \* jmerge/cli.py:1368 gh pr merge
    /\ blind' = (blind \/ seen[k][a] # tip)
    /\ tip' = Up(tip, 2)
    /\ seen' = Set(seen, k, [b \in Mergers |-> NoTip])
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, lock, mode>>

Next ==
    \/ \E k \in Kids : MakeChild(k) \/ LaunchCrew(k) \/ OpenPr(k) \/ PrReady(k) \/ PrDrops(k)
                       \/ CrewEnds(k)
                       \/ Activity(k) \/ GetsStuck(k) \/ Retire(k)
    \/ \E c \in Calls : RaiseCall(c) \/ Answer(c)
    \/ \E m \in Msgs : Deliver(m)
    \/ ChangeWake \/ \E r \in Routes : RouteFails(r) \/ RouteMends(r)
    \/ Check
    \/ \E a \in Mergers, k \in Kids : Read(a, k) \/ Merge(a, k)
Fair ==
    /\ \A m \in Msgs : WF_vars(Deliver(m))
    /\ \A r \in Routes : WF_vars(RouteMends(r))
    /\ WF_vars(Check)
    /\ \A k \in Kids : WF_vars(PrReady(k))     \* a crew fixes a pull request that dropped
    /\ \A a \in Mergers, k \in Kids : WF_vars(Read(a, k)) /\ WF_vars(Merge(a, k))
Spec == Init /\ [][Next]_vars /\ Fair
====
