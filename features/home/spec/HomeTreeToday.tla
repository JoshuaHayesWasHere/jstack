---- MODULE HomeTreeToday ----
\* Today's code, at main 64859143 (6485914337716964d3116dc7598e225f941d19a8). A child home is a
\* scoped home (home/scoped-homes.md), the root is the repo's root home, and jbus's pass is the
\* root's check. Each condition of a step names the file and line that checks it at that commit,
\* and quotes the code there in backticks: jbus/ is features/jbus/src/jbus/, jmerge/ is
\* features/jmerge/src/jmerge/, jbriefs/ is features/jbriefs/src/jbriefs/, and home/ and handoff/
\* are the skills in features/home/skills/. The model was first written at main f31174a3; a
\* condition whose code changed in meaning since then names the pull request that changed it.
EXTENDS HomeTree

Set(f, k, v) == [f EXCEPT ![k] = v]

\* ---- a child's own steps

\* Only the root home makes a scope, on the user's word (home/scoped-homes.md:15 `**Making a scope**
\* is the root home's, and only on the user's word`).
MakeChild(k) ==
    /\ k \in Made /\ life[k] = "unmade" /\ life' = Set(life, k, "working")
    /\ UNCHANGED <<work, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The child home queues a brief and jbus's pass launches its crew. Only a home that runs queues a
\* row, and the pass launches what is queued.
LaunchCrew(k) ==
    /\ life[k] = "working"     \* jbus/dispatch.py:557 `"t3_thread_launch",`
    /\ work[k] = "none" /\ work' = Set(work, k, "crew") /\ quiet' = Set(quiet, k, 0)
    /\ UNCHANGED <<life, msg, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The crew opens the pull request ("Do the task" in the crew skill).
OpenPr(k) ==
    /\ work[k] = "crew" /\ work' = Set(work, k, "open")
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* Its checks pass (jmerge/cli.py:1146 `short = short or ready.short_on_github(one)`) and its
\* review is written (jmerge/cli.py:1127 `short = short or ready.short_of(text, one.head)`).
PrReady(k) ==
    /\ work[k] \in {"open", "again"}
    /\ work' = Set(work, k, IF work[k] = "open" THEN "ready" ELSE "back")
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* A check turns red or a review goes stale (jmerge/cli.py:1146 `ready.short_on_github(one)`,
\* jmerge/cli.py:1127 `ready.short_of(text, one.head)`): the pull request is not ready, and jmerge
\* judges it again. Since pull request 396 a rebase that changed the reviewed content waits on its
\* scoped review and no longer on the user, so it drops here too and comes back once reviewed.
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
\* key is in sent.json from then on, so it is never queued again (jbus/wake.py:376 `write_json(self.state
\* / "sent.json", [*sent, key])`). The model's setting picks one route, home or webhook, and
\* leaves out both.
RaiseCall(c) ==
    /\ c \in Raised
    /\ life[OwnerOf[c]] = "working"     \* jbus/mirror.py:188 `for file in gate_files(home):`
    /\ msg[c] = "none" /\ msg' = Set(msg, c, wake)     \* jbus/wake.py:378 `else self.routes:`
    /\ quiet' = Set(quiet, OwnerOf[c], 0)
    /\ UNCHANGED <<life, work, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The child does something jbus can see: a turn in its thread, a commit, a push.
Activity(k) ==
    /\ life[k] = "working"     \* jbus/live.py:63 `if facts.silent < QUIET_MINUTES:`
    /\ quiet' = Set(quiet, k, 0)
    /\ UNCHANGED <<life, work, msg, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The child stops: its turn ended and nothing will wake it. Only the child could tell.
GetsStuck(k) ==
    /\ life[k] = "working" /\ life' = Set(life, k, "stuck")
    /\ UNCHANGED <<work, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The root or Josh retires a child: the scope's handoff.md says so (home/scoped-homes.md:8 `A
\* scope that ends says so in its own`). The handoff closes a scope whose plan has no open entry,
\* and counts nothing else, so a crew, a pull request or a gate of the scope may still be out
\* (handoff/SKILL.md:145 `if [ -n "$scope" ] && [ "${open:-0}" -eq 0 ]; then closed=yes; fi`). A
\* brief of a scope with no home-id and no Was home line falls back to the root (jbriefs/home.py:59
\* `if now or was:`).
Retire(k) ==
    /\ life[k] \in {"working", "stuck"} /\ life' = Set(life, k, "retired")     \* handoff/SKILL.md:144 `open=$(awk`
    /\ UNCHANGED <<work, msg, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>

\* ---- Josh, and the routes

Answer(c) ==
    /\ msg[c] = "told" /\ msg' = Set(msg, c, "none")
    /\ UNCHANGED <<life, work, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* A pass posts what waits in the outbox of each route the setting picks, and only those. A post
\* that fails leaves it in the outbox.
Deliver(m) ==
    \E r \in Routes :
        /\ msg[m] = r
        /\ r = wake     \* jbus/alert.py:332 `for route in run.box.routes:`
        /\ up[r]        \* jbus/wake.py:683-685 `why = post(route, body(some)) if why: break`
        /\ msg' = Set(msg, m, "told")
        /\ UNCHANGED <<life, work, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock,
                       mode>>
\* Each pass first moves what waits for a route the setting leaves out to the route it picks
\* (pull request 332), so a change of the setting strands no call.
Rehome(m) ==
    /\ msg[m] \in Routes
    /\ msg[m] # wake     \* jbus/alert.py:323 `moved(run)`; jbus/wake.py:540 `for old in self.left:`
    /\ msg' = Set(msg, m, wake)
    /\ UNCHANGED <<life, work, quiet, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>
\* The wake setting changes between home and webhook (jbus/__init__.py:117-118 `def to_home(self) ->
\* bool: return self.wake in ("home", "both")`).
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
\* logged and never posted (jbus/stall.py:61 `EVENTS = {"waiting-on-user": "quiet", "stall":
\* "quiet"}`, jbus/stall.py:447 `key = f"hung {one['id']} {one['run']}"`), and the root home is sent
\* nothing while a scope works (home/scoped-homes.md:8 `The root home is sent nothing while a scope
\* works`). Since pull request 373 a crew's wait that its thread left is asked again by its age,
\* and at the second miss the brief's home, here the child itself, gets one line (jbus/clock.py:25
\* `the wait. The count starts again. At`). That watches the crew, not the child: nothing flags a
\* quiet child to the root or to Josh, nudges it or asks.
Check ==
    /\ quiet' = Ticked
    /\ UNCHANGED <<life, work, msg, watch, wake, moved, up, broke, tip, seen, blind, lock, mode>>

\* ---- merging: a read of main's tip, then the merge

\* Who may merge a child's pull request. On jbus merges, jbus runs jmerge only while the root's
\* home-thread is empty, as the root, and then no home's pull request is another's, so jbus
\* merges a child's. On home merges, the child runs jmerge for its own, and the root may add --all
\* (home/merging-a-pull-request-that-is-ready.md:96 `and merges its own`). Since pull request 370
\* jbus also runs jmerge --check where a home merges, which merges nothing.
MayMerge(a, k) ==
    /\ mode = "jbus" => a = "jbus"     \* jbus/merge.py:156-157 `home = home_thread(run) if home:`
    /\ mode = "home" => a \in {"root", "child"}     \* jmerge/cli.py:732 `if self.asking != claims.NOBODY and not _read(self.state / "home-thread").strip():`
    /\ a = "child" => life[k] = "working"     \* jmerge/cli.py:743-744 `if root_runs or handed_off: return claims.NOBODY`
\* jmerge checks that main's tip is still the one it judged (jmerge/cli.py:1403 `_first_word(at.stdout)
\* == judged.tip`) and then merges (jmerge/cli.py:1431 `"merge",`). No lock spans the gap between
\* the two, and two runners can run at once (home/merging-a-pull-request-that-is-ready.md:9 `two runs at once would race, and no lock
\* keeps them apart`).
Read(a, k) ==
    /\ MayMerge(a, k)     \* jmerge/cli.py:1121 `if self.others(text) and not self.every:`
    /\ Ready(k)     \* jmerge/cli.py:1225 `return Judgement(brief.stem, "", "", note, judged)`
    /\ seen[k][a] = NoTip /\ seen' = [seen EXCEPT ![k][a] = tip]     \* jmerge/cli.py:1402 `at = _run(self.main, "git", "ls-remote", "origin", f"refs/heads/{one.base}")`
    /\ UNCHANGED <<life, work, msg, quiet, watch, wake, moved, up, broke, tip, blind, lock, mode>>
Merge(a, k) ==
    /\ seen[k][a] # NoTip     \* jmerge/cli.py:1403 `if not at.returncode and _first_word(at.stdout) == judged.tip:`
    /\ Ready(k) /\ work' = Set(work, k, "merged")     \* jmerge/cli.py:1429-1431 `"gh", "pr", "merge",`
    /\ blind' = (blind \/ seen[k][a] # tip)
    /\ tip' = Up(tip, 2)
    /\ seen' = Set(seen, k, [b \in Mergers |-> NoTip])
    /\ UNCHANGED <<life, msg, quiet, watch, wake, moved, up, broke, lock, mode>>

Next ==
    \/ \E k \in Kids : MakeChild(k) \/ LaunchCrew(k) \/ OpenPr(k) \/ PrReady(k) \/ PrDrops(k)
                       \/ CrewEnds(k)
                       \/ Activity(k) \/ GetsStuck(k) \/ Retire(k)
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
