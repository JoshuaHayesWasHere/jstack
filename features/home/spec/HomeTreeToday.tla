---- MODULE HomeTreeToday ----
\* Today's code, as of main 859203e0 (2026-10-27): the branch hometree-rules gave main 64859143 the
\* four guards of the design, and its cites follow the code since. A child home is a scoped home (home/scoped-homes.md), the root is the repo's root
\* home, and jbus's pass is the root's check. Each condition of a step names the file that
\* checks it, and quotes the code there in backticks, with no line number: jbus/ is features/jbus/src/jbus/,
\* jmerge/ is features/jmerge/src/jmerge/, jbriefs/ is features/jbriefs/src/jbriefs/, and home/
\* and handoff/ are the skills in features/home/skills/. It is the design too: the code has each
\* of the design's guards (#334), the retire guard, the watch of a quiet child (flag, beat,
\* strike, nudge cap and ask), jbus as the only merger for every home, and the merge lock that a
\* drop gives back.
\*
\* Drop names one guard to take out, or "none". With a guard out, the rule that rests on it must
\* break: canaries.py checks that it does, so no rule holds by construction.
EXTENDS HomeTree
CONSTANT Drop
Kept(g) == Drop # g

Set(f, k, v) == [f EXCEPT ![k] = v]

\* What the child does that the root can see ends its quiet spell: a write of one of its crew or
\* reviewer threads, or a change in what it has out, its crew, pull request or call
\* (jbus/children.py `elif latest and latest > since: since, step = latest, "calm"`,
\* jbus/children.py `step = prev.get("step", "calm") if prev.get("sig") == sig else "calm"`).
\* A write of its home thread counts only before the root nudged it in this spell
\* (jbus/children.py `or (one.get("id") == thread and step == "calm")`): a turn the nudge
\* started is no progress. A notice Josh has read is done.
Calmed(k, m) == [m EXCEPT ![NoticeOf(k)] = IF @ = "told" THEN "none" ELSE @]
Calm(k) ==
    /\ quiet' = Set(quiet, k, 0) /\ watch' = Set(watch, k, "calm")
    /\ msg' = Calmed(k, msg)

\* ---- a child's own steps

\* Only the root home makes a scope, on the user's word (home/scoped-homes.md `**Making a scope**
\* is the root home's, and only on the user's word`).
MakeChild(k) ==
    /\ k \in Made /\ life[k] = "unmade" /\ life' = Set(life, k, "working")
    /\ UNCHANGED <<work, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* The child home queues a brief and jbus's pass launches its crew. Only a home that runs queues a
\* row, and the pass launches what is queued. A launched row is a change in what the child has
\* out, so its spell ends.
LaunchCrew(k) ==
    /\ life[k] = "working"     \* jbus/dispatch.py `"t3_thread_launch",`
    /\ work[k] = "none" /\ work' = Set(work, k, "crew") /\ Calm(k)
    /\ UNCHANGED <<life, up, broke, tip, seen, blind, lock, mode>>
\* The crew opens the pull request ("Do the task" in the crew skill).
OpenPr(k) ==
    /\ work[k] = "crew" /\ work' = Set(work, k, "open")
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* Its checks pass (jmerge/cli.py `short = short or ready.short_on_github(`) and its
\* review is written (jmerge/cli.py
\* `short = short or self.lift(ready.short_of(text, one.head), lifted)`).
PrReady(k) ==
    /\ work[k] \in {"open", "again"}
    /\ work' = Set(work, k, IF work[k] = "open" THEN "ready" ELSE "back")
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* A check turns red or a review goes stale (jmerge/cli.py
\* `short = short or ready.short_on_github(`, jmerge/cli.py
\* `short = short or self.lift(ready.short_of(text, one.head), lifted)`): the
\* pull request is not ready, and jmerge judges it again. A merge it had begun fails at the head
\* it checked, and its run gives the merge lock back as it returns (jmerge/cli.py
\* `finally: lock.give()`).
PrDrops(k) ==
    /\ work[k] = "ready" /\ work' = Set(work, k, "again")
    /\ seen' = Set(seen, k, [b \in Mergers |-> NoTip])
    /\ lock' = IF lock = k /\ Kept("drop-release") THEN "free" ELSE lock
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, tip, blind, mode>>
\* A crew stays on its pull request until it merges ("Stay on the pull request" in the crew
\* skill), and T3 Code settles it then.
CrewEnds(k) ==
    /\ work[k] = "merged" /\ work' = Set(work, k, "done")
    /\ UNCHANGED <<life, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* A gate or an item for Josh is an open item of the one list, raised once: its key is in sent.json
\* from then on, so it is never raised again (jbus/wake.py `return False
\* write_json(self.state / "sent.json", [*sent, key])`). A new call is a change in what the child has out, so its spell
\* ends.
RaiseCall(c) ==
    /\ c \in Raised
    /\ life[OwnerOf[c]] = "working"     \* jbus/mirror.py `for file in gate_files(home):`
    /\ msg[c] = "none" /\ msg' = Set(Calmed(OwnerOf[c], msg), c, "home")     \* jbus/wakes.py `new = pick(items, seen, thread)`
    /\ quiet' = Set(quiet, OwnerOf[c], 0) /\ watch' = Set(watch, OwnerOf[c], "calm")
    /\ UNCHANGED <<life, work, up, broke, tip, seen, blind, lock, mode>>
\* The child does something jbus can see: a write of one of its threads, a commit, a push.
Activity(k) ==
    /\ life[k] = "working"     \* jbus/live.py `if facts.silent < QUIET_MINUTES:`
    /\ Calm(k)
    /\ UNCHANGED <<life, work, up, broke, tip, seen, blind, lock, mode>>
\* The child stops: its turn ended and nothing will wake it. Only the child could tell.
GetsStuck(k) ==
    /\ life[k] = "working" /\ life' = Set(life, k, "stuck")
    /\ UNCHANGED <<work, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* The root or Josh retires a child: the scope's handoff archives it, whatever it has out, and
\* starts no home after it. It lists what `jbus out --scope` says the scope has out, removes its
\* home-id and moves its plan out, so the scope is no home and every brief of it is the root's
\* (jbriefs/home.py `if now or was:`): the root's own watch covers that work from then on, and
\* a child with nothing out is just retired. With the hand-over dropped, a child archived with
\* work out leaves it with no home.
Retire(k) ==
    /\ life[k] \in {"working", "stuck"}     \* handoff/SKILL.md `if ! out=$(jbus out --scope "${scope:-.}" 2>&1); then`
    /\ life' = Set(life, k, IF WorkOut(k) /\ Kept("hand-over") THEN "handed" ELSE "retired")     \* handoff/SKILL.md `! uv run --project "$T/../source" jbus forget "$M/home-id" > /dev/null; then`
    /\ Calm(k)
    /\ UNCHANGED <<work, up, broke, tip, seen, blind, lock, mode>>

\* ---- Josh, and the home thread

Answer(c) ==
    /\ msg[c] = "told" /\ msg' = Set(msg, c, "none")
    /\ UNCHANGED <<life, work, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* Josh answers the root's question about a stalled child: he gets it going again, and what it
\* then does ends the quiet spell. Retiring it instead is Retire.
Steps(k) ==
    /\ watch[k] = "asked"     \* jbus/children.py `line = f"{line}: get it going, or retire it; thread {thread}"`
    /\ msg[NoticeOf(k)] = "told"     \* jbus/wakes.py `told = new if new and _send(run, client, thread, new) else []`
    /\ life' = Set(life, k, IF life[k] = "stuck" THEN "working" ELSE life[k]) /\ Calm(k)
    /\ UNCHANGED <<work, up, broke, tip, seen, blind, lock, mode>>
\* A pass sends each home thread the items of the one list new to it, its one route to Josh. Only a
\* send that goes through records them as told (jbus/wakes.py `threads[thread] = kept(items, seen, told, run.now)`),
\* so one that fails leaves them new for the next pass.
Deliver(m) ==
    /\ msg[m] = "home"     \* jbus/wakes.py `for thread in sorted(({one.to for one in items} | set(threads)) - {""}):`
    /\ up     \* jbus/wakes.py `except T3Error as error:`
    /\ msg' = Set(msg, m, "told")
    /\ UNCHANGED <<life, work, quiet, watch, up, broke, tip, seen, blind, lock, mode>>
\* With the keep-on-fail guard dropped, a send that fails takes the call out all the same, and it
\* never reaches Josh.
Lost(m) ==
    /\ ~Kept("keep-on-fail")
    /\ msg[m] = "home"     \* jbus/wakes.py `for thread in sorted(({one.to for one in items} | set(threads)) - {""}):`
    /\ ~up     \* jbus/wakes.py `except T3Error as error:`
    /\ msg' = Set(msg, m, "none")
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
\* child: its launched rows and its crew threads (jbus/children.py
\* `launched = [line for line in lines if line.split(": ", 1)[1] not in QUEUED]`).
\* A routine, a scope with a `rhythm` file, owes its next beat whatever it has out
\* (jbus/children.py `beat = _rhythm(scope)`). The root never reads whether a child is stuck.
\* A handed child's work is the root's, which the root's own watch reads as its out
\* (jbus/children.py `mine = {slug for slug, text in texts.items() if homes.home_of(root, text) == scope}`).
Sees(k) ==
    /\ life[k] \in {"working", "stuck", "handed"}     \* jbus/children.py `if not thread or not (launched or beat):`
    /\ \/ Kept("beat") /\ Kind[k] = "routine" /\ life[k] # "handed"     \* jbus/children.py `patience = beat or PATIENCE`
       \/ work[k] \in {"crew", "open", "ready", "again", "back", "merged"}
\* The root acts on a child it sees each time the child has been quiet for its patience again
\* since its last step (jbus/children.py `if step != "asked" and run.now - start >=
\* timedelta(minutes=patience):`): it nudges it, at most twice in one spell, and then asks Josh.
\* A nudge is a message to the child's home thread, and it may not work. Each check adds one to
\* the quiet and takes a step the check it is due, so the last step was at a patience times its
\* rank (jbus/children.py `start = last or since + timedelta(minutes=patience * rank)`).
Acts(k) ==
    /\ Kept("flag") /\ Sees(k)     \* jbus/children.py `if not thread or not (launched or beat):`
    /\ watch[k] # "asked"     \* jbus/children.py `if step != "asked"`
    /\ Ticked[k] >= Patience(k) * (Rank[watch[k]] + 1)     \* jbus/children.py `run.now - start >= timedelta(minutes=patience)`
\* jbus/children.py `if step in ("calm", "nudged1"):` nudges, and the step after the second
\* nudge is the question (jbus/children.py `spell["step"] = STEPS_OF[rank + 1]`).
After(w) ==
    CASE w = "calm" -> "nudged1"
      [] w = "nudged1" -> "nudged2"
      [] w = "nudged2" -> IF Kept("ask") /\ Kept("nudge-cap") THEN "asked"
                          ELSE IF Kept("nudge-cap") THEN "nudged2" ELSE "nudged3"
      [] OTHER -> "asked"
\* On the first strike of a spell Josh hears of it, an alert of the project's on the one list
\* (jbus/children.py `line = f"{line}; jbus nudged it, thread {thread}"`), and the root's question
\* after the nudges is the same notice, sent again (jbus/children.py
\* `{home} is still quiet after two nudges`).
Notice(k) ==
    LET w == After(watch[k]) IN
    IF ~Acts(k) THEN msg[NoticeOf(k)]
    ELSE IF w = "asked" THEN "home"
    ELSE IF watch[k] = "calm" /\ Kept("strike") /\ msg[NoticeOf(k)] = "none" THEN "home"
    ELSE msg[NoticeOf(k)]
\* Each check counts the quiet of every child and acts on each one due, all in one pass
\* (jbus/children.py `def watch(run: Pass, client: Client, threads: list[dict[str, Any]] |
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
\* request, and mode plays no part (jbus/merge.py `ran = run.run("jmerge",
\* timeout=JMERGE_TIMEOUT)`). A home's run names it, and merges nothing (jmerge/cli.py
\* `if args.home: args.check = True`).
MayMerge(a, k) ==
    /\ Kept("one-merger") => a = "jbus"     \* jmerge/cli.py `if args.home: args.check = True`
    /\ a = "jbus" => Kept("all-homes")
\* The read of main's tip takes the repo's merge lock (jmerge/cli.py `while lock.take():`), a
\* run that finds it held merges nothing (jmerge/cli.py `return lines.waits("wait", number,
\* one.url, ready.MERGING)`), and the merge gives it back (jmerge/cli.py `finally: lock.give()`).
Read(a, k) ==
    /\ MayMerge(a, k)     \* jmerge/cli.py `if self.others(text) and not self.every:`
    /\ Ready(k)     \* jmerge/cli.py `return Judgement(brief.stem, "", "", note, judged)`
    /\ Kept("lock") => lock = "free"     \* jmerge/cli.py `while lock.take():`
    /\ seen[k][a] = NoTip /\ seen' = [seen EXCEPT ![k][a] = tip]     \* jmerge/cli.py `at = _run(self.main, "git", "ls-remote", "origin", f"refs/heads/{one.base}")`
    /\ lock' = IF Kept("lock") THEN k ELSE lock
    /\ UNCHANGED <<life, work, msg, quiet, watch, up, broke, tip, blind, mode>>
Merge(a, k) ==
    /\ seen[k][a] # NoTip     \* jmerge/cli.py `if not at.returncode and _first_word(at.stdout) == judged.tip:`
    /\ Ready(k) /\ work' = Set(work, k, "merged")     \* jmerge/cli.py `"merge",`
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
    \/ \E m \in Msgs : Deliver(m) \/ Lost(m)
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
