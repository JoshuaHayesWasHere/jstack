---- MODULE HomeTreeToday ----
\* Today's code, as of main 859203e0 (2026-10-27): the branch hometree-rules gave main 64859143 the
\* four guards of the design, and its cites follow the code since. A child home is a scoped home (home/scoped-homes.md), the root is the repo's root
\* home, and jbus's pass is the root's check. Each condition of a step names the file and line
\* that checks it, and quotes the code there in backticks: jbus/ is features/jbus/src/jbus/,
\* jmerge/ is features/jmerge/src/jmerge/, jbriefs/ is features/jbriefs/src/jbriefs/, and home/
\* and handoff/ are the skills in features/home/skills/. Its steps are the design's, guard for
\* guard, since the code now has each of the design's guards: the retire guard, the watch of a
\* quiet child (flag, beat, strike, nudge cap and ask), jbus as the only merger for every home,
\* and the merge lock that a drop gives back.
EXTENDS HomeTree

Set(f, k, v) == [f EXCEPT ![k] = v]

\* What the child does that the root can see ends its quiet spell: a write of one of its crew or
\* reviewer threads, or a change in what it has out, its crew, pull request or call
\* (jbus/children.py:249-250 `elif latest and latest > since: since, step = latest, "calm"`,
\* jbus/children.py:236 `step = prev.get("step", "calm") if prev.get("sig") == sig else "calm"`).
\* A write of its home thread counts only before the root nudged it in this spell
\* (jbus/children.py:242 `or (one.get("id") == thread and step == "calm")`): a turn the nudge
\* started is no progress. A notice Josh has read is done.
Calmed(k, m) == [m EXCEPT ![NoticeOf(k)] = IF @ = "told" THEN "none" ELSE @]
Calm(k) ==
    /\ quiet' = Set(quiet, k, 0) /\ watch' = Set(watch, k, "calm")
    /\ msg' = Calmed(k, msg)

\* ---- a child's own steps

\* Only the root home makes a scope, on the user's word (home/scoped-homes.md:57 `**Making a scope**
\* is the root home's, and only on the user's word`).
MakeChild(k) ==
    /\ k \in Made /\ life[k] = "unmade" /\ life' = Set(life, k, "working")
    /\ UNCHANGED <<work, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* The child home queues a brief and jbus's pass launches its crew. Only a home that runs queues a
\* row, and the pass launches what is queued. A launched row is a change in what the child has
\* out, so its spell ends.
LaunchCrew(k) ==
    /\ life[k] = "working"     \* jbus/dispatch.py:635 `"t3_thread_launch",`
    /\ work[k] = "none" /\ work' = Set(work, k, "crew") /\ Calm(k)
    /\ UNCHANGED <<life, up, broke, tip, seen, blind, lock, mode>>
\* The crew opens the pull request ("Do the task" in the crew skill).
OpenPr(k) ==
    /\ work[k] = "crew" /\ work' = Set(work, k, "open")
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* Its checks pass (jmerge/cli.py:918 `short = short or ready.short_on_github(`) and its
\* review is written (jmerge/cli.py:899 `short = short or ready.short_of(text, one.head)`).
PrReady(k) ==
    /\ work[k] \in {"open", "again"}
    /\ work' = Set(work, k, IF work[k] = "open" THEN "ready" ELSE "back")
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* A check turns red or a review goes stale (jmerge/cli.py:918
\* `short = short or ready.short_on_github(`, jmerge/cli.py:899
\* `short = short or ready.short_of(text, one.head)`): the pull request is not ready, and jmerge
\* judges it again. A merge it had begun fails at the head it checked, and its run gives the merge
\* lock back as it returns (jmerge/cli.py:1326 `lock.give()`).
PrDrops(k) ==
    /\ work[k] = "ready" /\ work' = Set(work, k, "again")
    /\ seen' = Set(seen, k, [b \in Mergers |-> NoTip])
    /\ lock' = IF lock = k THEN "free" ELSE lock
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, tip, blind, mode>>
\* A crew stays on its pull request until it merges ("Stay on the pull request" in the crew
\* skill), and T3 Code settles it then.
CrewEnds(k) ==
    /\ work[k] = "merged" /\ work' = Set(work, k, "done")
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* A gate or an item for Josh goes into the home thread's outbox, once: its key is in sent.json
\* from then on, so it is never queued again (jbus/wake.py:318 `write_json(self.state /
\* "sent.json", [*sent, key])`). A new call is a change in what the child has out, so its spell
\* ends.
RaiseCall(c) ==
    /\ c \in Raised
    /\ life[OwnerOf[c]] = "working"     \* jbus/mirror.py:176 `for file in gate_files(home):`
    /\ msg[c] = "none" /\ msg' = Set(Calmed(OwnerOf[c], msg), c, "home")     \* jbus/wake.py:322 `waiting = [*self._outbox(), made]`
    /\ quiet' = Set(quiet, OwnerOf[c], 0) /\ watch' = Set(watch, OwnerOf[c], "calm")
    /\ UNCHANGED <<life, work, up, broke, tip, seen, blind, lock, mode>>
\* The child does something jbus can see: a write of one of its threads, a commit, a push.
Activity(k) ==
    /\ life[k] = "working"     \* jbus/live.py:64 `if facts.silent < QUIET_MINUTES:`
    /\ Calm(k)
    /\ UNCHANGED <<life, work, up, broke, tip, seen, blind, lock, mode>>
\* The child stops: its turn ended and nothing will wake it. Only the child could tell.
GetsStuck(k) ==
    /\ life[k] = "working" /\ life' = Set(life, k, "stuck")
    /\ UNCHANGED <<work, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* The root or Josh retires a child: the scope's handoff closes it. It closes a scope whose plan
\* has no open entry only when `jbus out --scope` says it has nothing out: no queue row of its
\* briefs that is not over, no unsettled crew or reviewer thread of theirs, no question and no
\* open gate (handoff/SKILL.md:149 `elif [ -z "$still" ]; then`, jbus/children.py:94 `if
\* row["slug"] in mine and not queue.over(row)`). A closed scope has no home-id, and the root
\* watches it no more (jbus/children.py:230 `if not thread or not (launched or beat):`).
Retire(k) ==
    /\ life[k] \in {"working", "stuck"}
    /\ ~WorkOut(k)     \* handoff/SKILL.md:147 `if ! still=$(jbus out --scope "$scope" 2>&1); then`
    /\ life' = Set(life, k, "retired") /\ Calm(k)
    /\ UNCHANGED <<work, up, broke, tip, seen, blind, lock, mode>>

\* ---- Josh, and the home thread

Answer(c) ==
    /\ msg[c] = "told" /\ msg' = Set(msg, c, "none")
    /\ UNCHANGED <<life, work, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* Josh answers the root's question about a stalled child: he gets it going again, and what it
\* then does ends the quiet spell. Retiring it instead is Retire.
Steps(k) ==
    /\ watch[k] = "asked"     \* jbus/children.py:294 `name, STALL, f"{line}: get it going, or retire it; thread {thread}", key=f"{since} ask"`
    /\ msg[NoticeOf(k)] = "told"     \* jbus/wake.py:587 `why = post(body(some))`
    /\ life' = Set(life, k, IF life[k] = "stuck" THEN "working" ELSE life[k]) /\ Calm(k)
    /\ UNCHANGED <<work, up, broke, tip, seen, blind, lock, mode>>
\* A pass posts what waits in the home thread's outbox, its one route to Josh. Only a post that
\* goes through takes a call out of the outbox (jbus/wake.py:592 `write_json(outbox,
\* waiting[sent:], mode=0o600)`), so one that fails leaves it there for the next pass.
Deliver(m) ==
    /\ msg[m] = "home"     \* jbus/alert.py:301 `sent = run.box.flush(`
    /\ up     \* jbus/wake.py:587-589 `why = post(body(some)) if why: break`
    /\ msg' = Set(msg, m, "told")
    /\ UNCHANGED <<life, work, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* The home thread fails: T3 Code is down, or the thread is gone.
RouteFails ==
    /\ MayFail
    /\ ~broke /\ broke' = TRUE
    /\ up /\ up' = FALSE
    /\ UNCHANGED <<life, work, msg, quiet, watch, tip, seen, blind, lock, mode>>
RouteMends ==
    /\ ~up /\ up' = TRUE
    /\ UNCHANGED <<life, work, msg, quiet, watch, broke, tip, seen, blind, lock, mode>>

\* ---- the root's check, one jbus pass

\* What the root reads to know a child has work out, from jbus's own records and never from the
\* child: its launched rows, its crew threads, its questions and gates (jbus/children.py:228
\* `launched = [line for line in lines if line.split(": ", 1)[1] not in QUEUED]`).
\* A routine, a scope with a `rhythm` file, owes its next beat whatever it has out
\* (jbus/children.py:229 `beat = _rhythm(scope)`). The root never reads whether a child is stuck.
Sees(k) ==
    /\ life[k] \in {"working", "stuck"}     \* jbus/children.py:230 `if not thread or not (launched or beat):`
    /\ \/ Kind[k] = "routine"     \* jbus/children.py:251 `patience = beat or PATIENCE`
       \/ work[k] \in {"crew", "open", "ready", "again", "back", "merged"} \/ \E c \in CallsOf(k) : Open(c)
\* The root acts on a child it sees each time the child has been quiet for its patience again
\* since its last step (jbus/children.py:259 `if step != "asked" and run.now - start >=
\* timedelta(minutes=patience):`): it nudges it, at most twice in one spell, and then asks Josh.
\* A nudge is a message to the child's home thread, and it may not work. Each check adds one to
\* the quiet and takes a step the check it is due, so the last step was at a patience times its
\* rank (jbus/children.py:256 `start = last or since + timedelta(minutes=patience * rank)`).
Acts(k) ==
    /\ Sees(k)     \* jbus/children.py:230 `if not thread or not (launched or beat):`
    /\ watch[k] # "asked"     \* jbus/children.py:259 `if step != "asked"`
    /\ Ticked[k] >= Patience(k) * (Rank[watch[k]] + 1)     \* jbus/children.py:259 `run.now - start >= timedelta(minutes=patience)`
\* jbus/children.py:278 `if step in ("calm", "nudged1"):` nudges, and the step after the second
\* nudge is the question (jbus/children.py:262 `spell["step"] = STEPS_OF[rank + 1]`).
After(w) ==
    CASE w = "calm" -> "nudged1"
      [] w = "nudged1" -> "nudged2"
      [] w = "nudged2" -> "asked"
      [] OTHER -> "asked"
\* On the first strike of a spell Josh hears of it (jbus/children.py:288 `run.find(name, STALL,
\* f"{line}; jbus nudged it, thread {thread}", key=f"{since} strike")`), and the root's question
\* after the nudges is the same notice, sent again (jbus/children.py:262).
Notice(k) ==
    LET w == After(watch[k]) IN
    IF ~Acts(k) THEN msg[NoticeOf(k)]
    ELSE IF w = "asked" THEN "home"
    ELSE IF watch[k] = "calm" /\ msg[NoticeOf(k)] = "none" THEN "home"
    ELSE msg[NoticeOf(k)]
\* Each check counts the quiet of every child and acts on each one due, all in one pass
\* (jbus/children.py:212 `def watch(run: Pass, client: Client, threads: list[dict[str, Any]] |
\* None) -> None:`). A spell ends when the root no longer sees work out.
Check ==
    /\ watch' = [k \in Kids |-> IF ~Sees(k) THEN "calm" ELSE IF Acts(k) THEN After(watch[k])
                                ELSE watch[k]]
    /\ quiet' = Ticked
    /\ msg' = [m \in Msgs |-> IF m \in Notices THEN Notice(OwnerOf[m]) ELSE msg[m]]
    /\ \E revived \in SUBSET {k \in Kids : Acts(k) /\ watch'[k] # "asked"} :
           life' = [k \in Kids |-> IF k \in revived /\ life[k] = "stuck" THEN "working"
                                   ELSE life[k]]
    /\ UNCHANGED <<work, up, broke, tip, seen, blind, lock, mode>>

\* ---- merging: jbus alone, every home's pull request, one merge at a time

\* jbus runs jmerge on each pass whatever home-thread holds, so it judges every home's pull
\* request, and mode plays no part (jbus/merge.py:125 `ran = run.run("jmerge",
\* timeout=JMERGE_TIMEOUT)`). A home's run names it, and merges nothing (jmerge/cli.py:1906-1907
\* `if args.home: args.check = True`).
MayMerge(a, k) ==
    /\ a = "jbus"     \* jmerge/cli.py:1906-1907 `if args.home: args.check = True`
\* The read of main's tip takes the repo's merge lock (jmerge/cli.py:1336 `while lock.take():`), a
\* run that finds it held merges nothing (jmerge/cli.py:1354 `return lines.waits("wait", number,
\* one.url, ready.MERGING)`), and the merge gives it back (jmerge/cli.py:1326 `lock.give()`).
Read(a, k) ==
    /\ MayMerge(a, k)     \* jmerge/cli.py:893 `if self.others(text) and not self.every:`
    /\ Ready(k)     \* jmerge/cli.py:1008 `return Judgement(brief.stem, "", "", note, judged)`
    /\ lock = "free"     \* jmerge/cli.py:1336 `while lock.take():`
    /\ seen[k][a] = NoTip /\ seen' = [seen EXCEPT ![k][a] = tip]     \* jmerge/cli.py:1339 `at = _run(self.main, "git", "ls-remote", "origin", f"refs/heads/{one.base}")`
    /\ lock' = k
    /\ UNCHANGED <<life, work, msg, quiet, watch, up, broke, tip, blind, mode>>
Merge(a, k) ==
    /\ seen[k][a] # NoTip     \* jmerge/cli.py:1340 `if not at.returncode and _first_word(at.stdout) == judged.tip:`
    /\ Ready(k) /\ work' = Set(work, k, "merged")     \* jmerge/cli.py:1371 `"merge",`
    /\ blind' = (blind \/ seen[k][a] # tip)
    /\ tip' = Up(tip, 2)
    /\ seen' = Set(seen, k, [b \in Mergers |-> NoTip])
    /\ lock' = IF lock = k THEN "free" ELSE lock
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, mode>>

Next ==
    \/ \E k \in Kids : MakeChild(k) \/ LaunchCrew(k) \/ OpenPr(k) \/ PrReady(k) \/ PrDrops(k)
                       \/ CrewEnds(k) \/ Activity(k)
                       \/ GetsStuck(k) \/ Retire(k) \/ Steps(k)
    \/ \E c \in Calls : RaiseCall(c) \/ Answer(c)
    \/ \E m \in Msgs : Deliver(m)
    \/ RouteFails \/ RouteMends
    \/ Check
    \/ \E a \in Mergers, k \in Kids : Read(a, k) \/ Merge(a, k)
Fair ==
    /\ \A m \in Msgs : WF_vars(Deliver(m))
    /\ WF_vars(RouteMends)
    /\ WF_vars(Check)
    /\ \A k \in Kids : WF_vars(PrReady(k))     \* a crew fixes a pull request that dropped
    /\ \A a \in Mergers, k \in Kids : WF_vars(Read(a, k)) /\ WF_vars(Merge(a, k))
Spec == Init /\ [][Next]_vars /\ Fair
====
