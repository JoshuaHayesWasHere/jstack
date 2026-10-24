---- MODULE HomeTreeDesign ----
\* The design: the two scouts' sibling models (reports/home-tree-a/SiblingsDesign.tla and
\* reports/home-tree-b/siblings/HomeTreeSiblings.tla) with Josh's answers of 2026-10-23
\* (decisions.md, word b28ed7da6fa2) built in. Children are made and retired by the root or by
\* Josh by hand, they message each other and Josh only through the root, they have no cap and
\* no shares, a routine is a home with a declared rhythm, and jbus is the only merger.
\*
\* Drop names one guard of the design to take out, or "none". With a guard out, the rule that
\* rests on it must break: canaries.py checks that it does, so no rule holds by construction.
EXTENDS HomeTree
CONSTANT Drop
Kept(g) == Drop # g

Set(f, k, v) == [f EXCEPT ![k] = v]

\* What the child does that the root can see ends its quiet spell: a turn in its thread, a
\* commit, a push, a call, a crew, or, for a routine, its beat. A notice Josh has read is done.
Calmed(k, m) == [m EXCEPT ![NoticeOf(k)] = IF @ = "told" THEN "none" ELSE @]
Calm(k) ==
    /\ quiet' = Set(quiet, k, 0) /\ watch' = Set(watch, k, "calm")
    /\ msg' = Calmed(k, msg)

\* ---- a child's own steps, as today

MakeChild(k) ==
    /\ k \in Made /\ life[k] = "unmade" /\ life' = Set(life, k, "working")
    /\ UNCHANGED <<work, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
LaunchCrew(k) ==
    /\ life[k] = "working"
    /\ work[k] = "none" /\ work' = Set(work, k, "crew") /\ Calm(k)
    /\ UNCHANGED <<life, wake, moved, up, broke, tip, seen, blind, lock, mode>>
OpenPr(k) ==
    /\ work[k] = "crew" /\ work' = Set(work, k, "open")
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
PrReady(k) ==
    /\ work[k] \in {"open", "again"}
    /\ work' = Set(work, k, IF work[k] = "open" THEN "ready" ELSE "back")
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* A check turns red, a review goes stale, or main moves: the pull request is not ready, and a
\* merge it had begun gives the lock back.
PrDrops(k) ==
    /\ work[k] = "ready" /\ work' = Set(work, k, "again")
    /\ seen' = Set(seen, k, [b \in Mergers |-> NoTip])
    /\ lock' = IF lock = k /\ Kept("drop-release") THEN "free" ELSE lock
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, blind, mode>>
CrewEnds(k) ==
    /\ work[k] = "merged" /\ work' = Set(work, k, "done")
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
RaiseCall(c) ==
    /\ c \in Raised /\ life[OwnerOf[c]] = "working"
    /\ msg[c] = "none" /\ msg' = Set(Calmed(OwnerOf[c], msg), c, wake)
    /\ quiet' = Set(quiet, OwnerOf[c], 0) /\ watch' = Set(watch, OwnerOf[c], "calm")
    /\ UNCHANGED <<life, work, wake, moved, up, broke, tip, seen, blind, lock, mode>>
Activity(k) ==
    /\ life[k] = "working" /\ Calm(k)
    /\ UNCHANGED <<life, work, wake, moved, up, broke, tip, seen, blind, lock, mode>>
GetsStuck(k) ==
    /\ life[k] = "working" /\ life' = Set(life, k, "stuck")
    /\ UNCHANGED <<work, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The root or Josh retires a child by hand, a short-lived one once its feature is done, and
\* is refused while anything of the child's is open.
Retire(k) ==
    /\ life[k] \in {"working", "stuck"}
    /\ Kept("retire-guard") => ~WorkOut(k)
    /\ life' = Set(life, k, "retired") /\ Calm(k)
    /\ UNCHANGED <<work, wake, moved, up, broke, tip, seen, blind, lock, mode>>

\* ---- Josh, and the routes

Answer(c) ==
    /\ msg[c] = "told" /\ msg' = Set(msg, c, "none")
    /\ UNCHANGED <<life, work, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* Josh answers the root's question about a stalled child: he gets it going again, and the
\* quiet spell ends. Retiring it instead is Retire.
Steps(k) ==
    /\ watch[k] = "asked" /\ msg[NoticeOf(k)] = "told"
    /\ life' = Set(life, k, IF life[k] = "stuck" THEN "working" ELSE life[k]) /\ Calm(k)
    /\ UNCHANGED <<work, wake, moved, up, broke, tip, seen, blind, lock, mode>>
Deliver(m) ==
    \E r \in Routes :
        /\ msg[m] = r /\ r = wake /\ up[r]
        /\ msg' = Set(msg, m, "told")
        /\ UNCHANGED <<life, work, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock,
                       mode>>
\* What waits in the outbox of a route the setting no longer picks moves to the route it picks.
Rehome(m) ==
    /\ Kept("rehome")
    /\ msg[m] \in Routes /\ msg[m] # wake /\ msg' = Set(msg, m, wake)
    /\ UNCHANGED <<life, work, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
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

\* What the root reads to know a child has work out, all from signals the child does not send:
\* its crew threads (T3 Code), its pull requests (GitHub) and its calls (jbus's outboxes). A
\* routine owes its next beat whatever it has out. The root never reads whether a child is stuck.
Sees(k) ==
    /\ life[k] \in {"working", "stuck"}
    /\ \/ Kept("beat") /\ Kind[k] = "routine"
       \/ work[k] \in {"crew", "open", "ready", "again", "back", "merged"} \/ \E c \in CallsOf(k) : Open(c)
\* The root acts on a child it sees each time the child has been quiet for its patience again:
\* it nudges it, at most twice in one quiet spell, and then asks Josh. A nudge is a message to
\* the child's thread, and it may not work.
Acts(k) ==
    /\ Kept("flag") /\ Sees(k) /\ watch[k] # "asked"
    /\ Ticked[k] >= Patience(k) * (Rank[watch[k]] + 1)
After(w) ==
    CASE w = "calm" -> "nudged1"
      [] w = "nudged1" -> "nudged2"
      [] w = "nudged2" -> IF Kept("ask") /\ Kept("nudge-cap") THEN "asked"
                          ELSE IF Kept("nudge-cap") THEN "nudged2" ELSE "nudged3"
      [] OTHER -> "asked"
\* On the first strike of a spell Josh hears of it, and the root's question after the nudges is
\* the same notice, sent again.
Notice(k) ==
    LET w == After(watch[k]) IN
    IF ~Acts(k) THEN msg[NoticeOf(k)]
    ELSE IF w = "asked" THEN wake
    ELSE IF watch[k] = "calm" /\ Kept("strike") /\ msg[NoticeOf(k)] = "none" THEN wake
    ELSE msg[NoticeOf(k)]
\* Each check counts the quiet of every child and acts on each one due, all in one pass. A spell
\* ends when the root no longer sees work out.
Check ==
    /\ watch' = [k \in Kids |-> IF ~Sees(k) THEN "calm" ELSE IF Acts(k) THEN After(watch[k])
                                ELSE watch[k]]
    /\ quiet' = Ticked
    /\ msg' = [m \in Msgs |-> IF m \in Notices THEN Notice(OwnerOf[m]) ELSE msg[m]]
    /\ \E revived \in SUBSET {k \in Kids : Acts(k) /\ watch'[k] # "asked"} :
           life' = [k \in Kids |-> IF k \in revived /\ life[k] = "stuck" THEN "working"
                                   ELSE life[k]]
    /\ UNCHANGED <<work, wake, moved, up, broke, tip, seen, blind, lock, mode>>

\* ---- merging: jbus alone, every home's pull request, one merge at a time

\* jbus judges the pull requests of every home, whatever the root's home-thread file says: mode
\* plays no part here. Today it does so only while home-thread is empty. Without that guard it
\* judges no child's pull request, and a ready one never merges.
MayMerge(a, k) ==
    /\ Kept("one-merger") => a = "jbus"
    /\ a = "jbus" => Kept("all-homes")
\* The read of main's tip takes the repo's merge lock, and the merge gives it back.
Read(a, k) ==
    /\ MayMerge(a, k)
    /\ Ready(k)
    /\ Kept("lock") => lock = "free"
    /\ seen[k][a] = NoTip /\ seen' = [seen EXCEPT ![k][a] = tip]
    /\ lock' = IF Kept("lock") THEN k ELSE lock
    /\ UNCHANGED <<life, work, msg, quiet, watch, wake, moved, up, broke, tip, blind, mode>>
Merge(a, k) ==
    /\ seen[k][a] # NoTip
    /\ Ready(k) /\ work' = Set(work, k, "merged")
    /\ blind' = (blind \/ seen[k][a] # tip)
    /\ tip' = Up(tip, 2)
    /\ seen' = Set(seen, k, [b \in Mergers |-> NoTip])
    /\ lock' = IF lock = k THEN "free" ELSE lock
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, mode>>

Next ==
    \/ \E k \in Kids : MakeChild(k) \/ LaunchCrew(k) \/ OpenPr(k) \/ PrReady(k) \/ PrDrops(k)
                       \/ CrewEnds(k) \/ Activity(k)
                       \/ GetsStuck(k) \/ Retire(k) \/ Steps(k)
    \/ \E c \in Calls : RaiseCall(c) \/ Answer(c)
    \/ \E m \in Msgs : Deliver(m) \/ Rehome(m)
    \/ ChangeWake \/ \E r \in Routes : RouteFails(r) \/ RouteMends(r)
    \/ Check
    \/ \E a \in Mergers, k \in Kids : Read(a, k) \/ Merge(a, k)
Fair ==
    /\ \A m \in Msgs : WF_vars(Deliver(m)) /\ WF_vars(Rehome(m))
    /\ \A r \in Routes : WF_vars(RouteMends(r))
    /\ WF_vars(Check)
    /\ \A k \in Kids : WF_vars(PrReady(k))     \* a crew fixes a pull request that dropped
    /\ \A a \in Mergers, k \in Kids : WF_vars(Read(a, k)) /\ WF_vars(Merge(a, k))
Spec == Init /\ [][Next]_vars /\ Fair
====
