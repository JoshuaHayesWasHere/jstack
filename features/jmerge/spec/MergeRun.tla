---- MODULE MergeRun ----
\* One run of `jmerge` that jbus's pass starts, as the code of main aa5469d97 takes it, with a crash
\* at each step. jbus's pass (`jbus.merge.merge`) starts a detached process (`keep`), which holds
\* going.lock, runs `jmerge --if-free` and writes what it printed to ran-<at>.json; the next pass
\* reads each record (`_records`): it replaces ran-<at>.json with read.json, then sends its lines
\* (`_judged`). Inside, `jmerge` holds the repo's run lock (`jmerge.lock.running`) and goes in the
\* order of `jmerge.cli`: it settles the restarts a run left owed and drops the records of closed
\* pull requests (`Repo.open_only`), reads where its batch stands (`Repo.start_batch`), judges
\* each pull request, which may restart one whose run GitHub left queued (`Repo.unstuck`) or merge
\* one and close its wait spell (`Repo.timed`), and then merges a proven batch or builds the next
\* (`Repo.batched`). jbus's merge tick runs `jmerge --if-free` too, with its own list.
\*
\* A death at each step: the pass dies (a timeout, a reboot, an OOM kill), the detached process
\* dies, or `jmerge` dies (JMERGE_TIMEOUT kills it, or its unit is stopped). The disk and GitHub
\* keep what they hold, and every step `jmerge` held in memory is gone: `Stops` is both a run that
\* ended and one that died, from any step.
\*
\* Two pull requests stand for every other: P, whose required run GitHub left queued, which
\* jmerge restarts (`rejudge.BaseMerge.restart`), and W, which jmerge merges alone. The batch
\* stands for CI's batch of five or more over the members it took. The pass starts MaxRuns runs,
\* and the tick MaxTicks.
\*
\* Fault = "replace-first" is today's code: `os.replace` before `_judged`. Fault = "judge-first"
\* sends a record's lines before it replaces the record, the fix RunHeard asks for. Fault =
\* "no-run-lock" is today's code with a pass's run that does not take the run lock: the canary of
\* OneRunAtATime. Fault = "fresh-list" reads whether P is open from GitHub in the run, not from the
\* list the pass handed it before the run started, the fix RestartReopens asks for. Fault =
\* "log-on-sweep" has `open_only` log the spell it drops of a merged W, the fix WaitKept might
\* reach for: the canary of WaitLoggedOnce. Fault = "unlink-first" is the start stamp as the code
\* of aa5469d97 kept it: the pass removes a stale stamp before it tells of the run, holds no lock
\* while it does, and tells of a run whose record stands, and a run removes whatever stamp stands
\* and runs with no look at it: the canary of DeathTold and NoFalseNoRecord. Each value other than
\* "replace-first" changes that one thing of today's code.
\*
\* ReplyLost is the world, not the code: GitHub took a close whose reply gh lost, so gh exited
\* non-zero.
\*
\* Inside is the parts of jmerge's run the model follows, of "restart", "batch" and "waits": a part
\* it does not follow is a step the run skips. The parts share nothing but the run lock and a
\* death, so each config follows the parts its rules read, and TLC's state space stays a product
\* it can walk.
EXTENDS Naturals, FiniteSets
CONSTANTS MaxRuns, MaxTicks, Fault, Inside, ReplyLost

Runs == 1..MaxRuns
Tick == MaxRuns + 1      \* the merge tick's run of `jmerge`, or one by hand
Holders == {0} \cup Runs \cup {Tick}
PassG == MaxRuns + 2     \* the pass, as the holder of going.lock while it judges the stamp
Old == Fault = "unlink-first"
Min(s) == CHOOSE x \in s : \A y \in s : x <= y
\* `most`, by level: 1 is LEAST (5), 2 is START (12), 3 is MOST (48); a halve and a double move it
\* one level, which keeps what `_full` reads: whether a batch holds as many as the most.
Levels == 1..3
\* The six values `batch.state_of` returns. PrVerdict.batch has none, pending and failed;
\* proven, late and rerun are the ones it lacks.
BatchStates == {"none", "pending", "proven", "failed", "late", "rerun"}

VARIABLES
  \* B-059, jmerge-runs/, the pass's runs of jmerge: each run's detached process, by run.
  \* jbus/merge.py `where.mkdir(parents=True, exist_ok=True)`
  runs,
  \* B-060, jmerge-runs/started: the stamp a pass writes when it starts a run, and which run's
  \* pass wrote it (`by`, 0 for none); `old` once STARTING went by. The code keeps a time and a
  \* token that names the run: jbus/merge.py `(where / STARTED).write_text(stamp + "\n")`
  started,
  \* B-061, jmerge-runs/going.lock: the run whose process holds the flock, the pass (PassG)
  \* while it judges the stamp, or 0.
  \* jbus/merge.py `fcntl.flock(going, fcntl.LOCK_EX) if _stamp(where) != stamp:`
  going,
  \* B-062, jmerge-runs/ran-<at>.json: the runs whose record is written and not yet read.
  \* jbus/merge.py `write_json(where / f"ran-{at}.json", record)`
  ran,
  \* B-063, jmerge-runs/read.json: the run whose record the pass read last, or 0.
  \* jbus/merge.py `os.replace(path, where / READ)`
  read,
  \* C-023, base-merges.json `stuck` of P: none, owed (`reopen` owed, the close not yet known to
  \* have taken), closed (`closed`, the reopen owed), took, refused (`why`, no reopen owed), and
  \* unopened.
  \* jmerge/rejudge.py `self._put(number, {**(was if isinstance(was, dict) else {}), "stuck": kept}, by, move)`
  stuck,
  \* C-023, on GitHub: whether P is open.
  \* jmerge/rejudge.py `closed = self.gh("pr", "close", str(one.number))`
  prOpen,
  \* C-029, batch.json `again`: the batch out, or the next one built, is built again after a
  \* timeout.
  \* jmerge/batch.py `self.batch, self.again = None, True`
  again,
  \* C-029, batch.json `most`, by level (Levels).
  \* jmerge/batch.py `self.most = max(self.most // 2, LEAST)`
  most,
  \* C-031, the kind of batch the run chose (`Chosen.kind`), in memory: "" (alone), guards, ci.
  \* jmerge/batch.py `return GUARDS if size >= GUARDS_LEAST else ""`
  kind,
  \* C-033, the branch jmerge/batch on GitHub: none, the commit batch.json names (batch), or
  \* one it does not name (other).
  \* jmerge/batch.py `ran = _git(main, "push", "-q", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")`
  branch,
  \* C-033, the batch's standing draft pull request on GitHub.
  \* jmerge/cli.py `why = self.open_batch(default)`
  draft,
  \* C-043, merge-waits.json: whether W has an open wait spell.
  \* jmerge/waits.py `store.write_json(self.state / SPELLS, kept)`
  spell,
  \* C-044, merge-waits.jsonl: how many lines W's closed wait has.
  \* jmerge/waits.py `store.append_jsonl(self.state / LOG, [wait.line()], sort_keys=True)`
  logged,
  \* batch.json's batch out, as the record keeps it (C-029's record): none, full (as many members
  \* as `most`, not narrowed: `_full`), or part; `rerunKept`, its `rerun`; `suspects`, whether it
  \* keeps any.
  \* jmerge/batch.py `store.write_json(self.path, {**kept, **rest, "most": self.most})`
  batch, rerunKept, suspects,
  \* CI's check of the commit on the branch (none, running, passed, failed, rerunning, and
  \* failed-again, failed after its rerun); whether main moved past the batch's tip; and how many
  \* times the batch out merged.
  ci, tipMoved, merges,
  \* W merged on GitHub.
  wMerged,
  \* jmerge's run lock (`lock.running`): who holds it, or 0; where the run that holds it is (`jm`),
  \* the batch's state it read (`seen`), both in memory; and how many runs the tick made.
  lock, jm, seen, ticks,
  \* The pass: where it is (`pc`), the run whose record it holds in memory (`reading`), the run
  \* whose stamp it moved to jmerge-runs/died and is to tell of (`blamed`, a file that outlives
  \* the pass; with Fault = "unlink-first" the run it unlinked the stamp of, in memory), the run
  \* it is starting (`child`), each
  \* run's count of `_judged` calls (`judged`), the runs it said ended with no record (`told`),
  \* and the open/closed state of P in the list it hands `jmerge` (`handed`, `--pulls`).
  pc, reading, blamed, child, judged, told, handed,
  \* History: the runs that wrote a record.
  recorded

vars == <<runs, started, going, ran, read, stuck, prOpen, again, most, kind, branch, draft,
          spell, logged, batch, rerunKept, suspects, ci, tipMoved, merges, wMerged,
          lock, jm, seen, ticks, pc, reading, blamed, child, judged, told, handed, recorded>>
passV == <<pc, reading, blamed, child, judged, told, read, handed>>
childV == <<runs, started, going, ran, recorded>>
runV == <<lock, jm, seen, kind, ticks>>
restartV == <<stuck, prOpen>>
batchV == <<batch, rerunKept, again, most, suspects, branch, draft, ci, tipMoved, merges>>
waitV == <<spell, logged, wMerged>>

NoStamp == [by |-> 0, old |-> FALSE]
Phases == {"none", "spawned", "going", "jmerge", "done", "kept", "ended", "died"}
Steps == {"idle", "open", "batch", "rerun-ask", "restart", "closing", "closed", "reopening",
          "reopened", "mergew", "said", "logged", "batched", "merged", "building", "pushing",
          "opening", "keeping", "end"}

TypeOK ==
  /\ runs \in [Runs -> Phases]
  /\ started \in [by : {0} \cup Runs, old : BOOLEAN]
  /\ going \in {0} \cup Runs \cup {PassG} /\ ran \subseteq Runs /\ read \in {0} \cup Runs
  /\ stuck \in {"none", "owed", "closed", "took", "refused", "unopened"} /\ prOpen \in BOOLEAN
  /\ again \in BOOLEAN /\ most \in Levels /\ kind \in {"", "guards", "ci"}
  /\ branch \in {"none", "batch", "other"} /\ draft \in BOOLEAN
  /\ spell \in BOOLEAN /\ logged \in 0..2 /\ wMerged \in BOOLEAN
  /\ batch \in {"none", "full", "part"} /\ rerunKept \in BOOLEAN /\ suspects \in BOOLEAN
  /\ ci \in {"none", "running", "passed", "failed", "rerunning", "failed-again"}
  /\ tipMoved \in BOOLEAN /\ merges \in 0..2
  /\ lock \in Holders /\ jm \in Steps /\ seen \in BatchStates /\ ticks \in 0..MaxTicks
  /\ pc \in {"idle", "telling", "unlinked", "unmarking", "unstamping", "stamping", "spawning",
            "reading", "judging", "replacing"}
  /\ reading \in {0} \cup Runs /\ blamed \in {0} \cup Runs /\ child \in {0} \cup Runs
  /\ judged \in [Runs -> 0..2] /\ told \subseteq Runs /\ handed \in BOOLEAN
  /\ recorded \subseteq Runs

Init ==
  /\ runs = [r \in Runs |-> "none"] /\ started = NoStamp /\ going = 0 /\ ran = {} /\ read = 0
  /\ stuck = "none" /\ prOpen = TRUE
  /\ again = FALSE /\ most = 2 /\ kind = "" /\ branch = "none" /\ draft = FALSE
  /\ spell = FALSE /\ logged = 0 /\ wMerged = FALSE
  /\ batch = "none" /\ rerunKept = FALSE /\ suspects = FALSE /\ ci = "none"
  /\ tipMoved = FALSE /\ merges = 0
  /\ lock = 0 /\ jm = "idle" /\ seen = "none" /\ ticks = 0
  /\ pc = "idle" /\ reading = 0 /\ blamed = 0 /\ child = 0
  /\ judged = [r \in Runs |-> 0] /\ told = {} /\ handed = TRUE /\ recorded = {}

----
\* The pass (`jbus.merge.merge`).

\* `_stamped`: the pass takes going.lock without waiting,
\* jbus/merge.py `fcntl.flock(going, fcntl.LOCK_EX | fcntl.LOCK_NB)`, and leaves a stamp younger
\* than STARTING: jbus/merge.py `if _starting(where):`, where jbus/merge.py
\* `return verbs.clock() - at < STARTING`. A stamp that stands then is judged:
\* jbus/merge.py `if stale := _stamp(where):`. A record that names it, read or not, is a run that
\* died after it kept its record, which is no death:
\* jbus/merge.py `return any(read_json(path, {}).get("stamp") == stamp for path in kept)`, here
\* the run in `ran` or `read`. Any other stamp is moved aside, in one step, to the died file
\* (`blamed`), which no run starts from and the next pass tells of where this one dies:
\* jbus/merge.py `os.replace(where / STARTED, where / DIED)`, then
\* jbus/merge.py `if (where / DIED).exists():`. With Fault = "unlink-first" the pass holds no
\* lock, removes the stamp first, keeps the run to tell of in memory, and tells of whatever run
\* wrote the stamp.
PassStarts ==
  /\ pc = "idle"
  /\ IF going = 0 /\ ~(started.by /= 0 /\ ~started.old)
       THEN /\ going' = IF Old THEN going ELSE PassG
            /\ IF started.by = 0
                 THEN /\ pc' = (IF blamed = 0 THEN "stamping" ELSE "telling")
                      /\ UNCHANGED <<started, blamed>>
               ELSE IF Old
                 THEN started' = NoStamp /\ blamed' = started.by /\ pc' = "unlinked"
               ELSE IF started.by \in ran \/ read = started.by
                 THEN pc' = "unstamping" /\ UNCHANGED <<started, blamed>>
               ELSE started' = NoStamp /\ blamed' = started.by /\ pc' = "telling"
       ELSE pc' = "reading" /\ UNCHANGED <<started, blamed, going>>
  /\ UNCHANGED <<runs, ran, recorded, reading, child, judged, told, read, handed>>
  /\ UNCHANGED <<runV, restartV, batchV, waitV>>

\* jbus/merge.py `_told(run, died, f"its run ended with no record: {_last(where / CHILD_LOG)}")`,
\* once for the stamp: jbus/merge.py `if run.box.send("", "no-record", line, key=f"no-record|{stamp}"):`,
\* so a tell again after a pass died is the same tell, as `told` is a set. Then the died file goes.
\* With Fault = "unlink-first" the stamp went first (`unlinked`) and the pass tells after.
PassTells ==
  /\ pc \in {"telling", "unlinked"} /\ told' = told \cup {blamed}
  /\ IF pc = "telling"
       THEN pc' = "unmarking" /\ UNCHANGED blamed
       ELSE pc' = "stamping" /\ blamed' = 0
  /\ UNCHANGED <<childV, reading, child, judged, read, handed, runV, restartV, batchV, waitV>>

\* jbus/merge.py `(where / DIED).unlink()`, once the run is told of.
PassUnmarks ==
  /\ pc = "unmarking" /\ blamed' = 0 /\ pc' = "stamping"
  /\ UNCHANGED <<childV, reading, child, judged, told, read, handed, runV, restartV, batchV, waitV>>

\* jbus/merge.py `_unstamp(where, stale)`, the stamp of a run that kept its record: the pass holds
\* going.lock, so it is the stamp it judged.
PassUnstamps ==
  /\ pc = "unstamping" /\ started' = NoStamp /\ pc' = "stamping"
  /\ UNCHANGED <<runs, going, ran, recorded, reading, blamed, child, judged, told, read, handed>>
  /\ UNCHANGED <<runV, restartV, batchV, waitV>>

\* jbus/merge.py `(where / STARTED).write_text(stamp + "\n")`, a stamp of the run's own, and then
\* going.lock goes back, since the run takes it itself. The model starts MaxRuns runs, and a pass
\* after the last only reads.
PassStamps ==
  /\ pc = "stamping"
  /\ going' = IF going = PassG THEN 0 ELSE going
  /\ LET free == {r \in Runs : runs[r] = "none"} IN
       IF free = {}
         THEN pc' = "reading" /\ UNCHANGED <<started, child>>
         ELSE /\ started' = [by |-> Min(free), old |-> FALSE] /\ child' = Min(free)
              /\ pc' = "spawning"
  /\ UNCHANGED <<runs, ran, recorded, reading, blamed, judged, told, read, handed>>
  /\ UNCHANGED <<runV, restartV, batchV, waitV>>

\* `start`: jbus/merge.py `child += handed(run)`, the pass's list of the open pull requests, read
\* now and run later, beside the stamp that names the run:
\* jbus/merge.py `child = (sys.executable, "-c", code, _stamp(where), str(where), str(run.project.checkout))`
PassSpawns ==
  /\ pc = "spawning" /\ runs' = [runs EXCEPT ![child] = "spawned"] /\ handed' = prOpen
  /\ pc' = "reading" /\ child' = 0
  /\ UNCHANGED <<started, going, ran, recorded, reading, blamed, judged, told, read>>
  /\ UNCHANGED <<runV, restartV, batchV, waitV>>

\* `_records`, oldest first: jbus/merge.py `for path in sorted(where.glob("ran-*.json")):`, then
\* jbus/merge.py `os.replace(path, where / READ)` and jbus/merge.py `lines = _judged(run, ran, record["at"])`.
\* Today the replace comes first; with Fault = "judge-first" the lines are sent first.
PassReads ==
  /\ pc = "reading"
  /\ IF ran = {}
       THEN pc' = "idle" /\ UNCHANGED <<ran, read, reading, judged>>
       ELSE LET r == Min(ran) IN
            /\ reading' = r
            /\ IF Fault = "judge-first"
                 THEN judged' = [judged EXCEPT ![r] = IF @ < 2 THEN @ + 1 ELSE 2]
                      /\ pc' = "replacing"
                      /\ UNCHANGED <<ran, read>>
                 ELSE ran' = ran \ {r} /\ read' = r /\ pc' = "judging" /\ UNCHANGED judged
  /\ UNCHANGED <<runs, started, going, recorded, blamed, child, told, handed>>
  /\ UNCHANGED <<runV, restartV, batchV, waitV>>

\* `_judged`: jbus/merge.py `lines = _sent(run, ran, at=at)` sends each line once by its key,
\* jbus/merge.py `run.find(slug or f"#{line.number}", "jmerge", text, key=f"{line.number} {text}")`,
\* and counts the run on the jmerge streak, which no key guards:
\* jbus/merge.py `alert.tell(run, streak, alert.ok(run.config.state_dir, streak, user=run.user))`.
PassJudges ==
  /\ pc = "judging" /\ judged' = [judged EXCEPT ![reading] = IF @ < 2 THEN @ + 1 ELSE 2]
  /\ reading' = 0 /\ pc' = "reading"
  /\ UNCHANGED <<childV, blamed, child, told, read, handed, runV, restartV, batchV, waitV>>

\* With Fault = "judge-first": the replace after the lines were sent.
PassReplaces ==
  /\ pc = "replacing" /\ ran' = ran \ {reading} /\ read' = reading
  /\ reading' = 0 /\ pc' = "reading"
  /\ UNCHANGED <<runs, started, going, recorded, blamed, child, judged, told, handed>>
  /\ UNCHANGED <<runV, restartV, batchV, waitV>>

\* The pass dies between two of its steps, and the kernel gives going.lock back; the next pass
\* starts at `merge`'s top. A run stamped and not yet spawned never starts: it died with no
\* record, and its stamp, a token of its own, is never written again.
PassDies ==
  /\ pc /= "idle" /\ pc' = "idle" /\ reading' = 0 /\ child' = 0
  /\ blamed' = IF Old THEN 0 ELSE blamed
  /\ going' = IF going = PassG THEN 0 ELSE going
  /\ runs' = IF pc = "spawning" THEN [runs EXCEPT ![child] = "died"] ELSE runs
  /\ UNCHANGED <<started, ran, recorded, judged, told, read, handed>>
  /\ UNCHANGED <<runV, restartV, batchV, waitV>>

----
\* The run's detached process (`keep`).

\* The run takes going.lock, which waits while another holds it, and looks at the stamp:
\* jbus/merge.py `fcntl.flock(going, fcntl.LOCK_EX) if _stamp(where) != stamp:`. A run whose stamp
\* is gone was told dead, a run that started slower than STARTING: it runs nothing, keeps no
\* record, and ends, which gives going.lock back. With Fault = "unlink-first" it runs whatever
\* stamp stands.
TakesGoing(r) ==
  /\ runs[r] = "spawned" /\ going = 0
  /\ IF Old \/ started.by = r
       THEN going' = r /\ runs' = [runs EXCEPT ![r] = "going"]
       ELSE runs' = [runs EXCEPT ![r] = "ended"] /\ UNCHANGED going
  /\ UNCHANGED <<started, ran, recorded, passV, runV, restartV, batchV, waitV>>

\* jbus/merge.py `ran = proc.run(*RUN, *more, cwd=checkout, timeout=JMERGE_TIMEOUT)`, with
\* `--if-free`: jmerge/lock.py `fcntl.flock(held, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)`.
\* A run that finds the lock held exits BUSY at once. With Fault = "no-run-lock" the pass's run
\* goes on without it.
RunsJmerge(r) ==
  /\ runs[r] = "going"
  /\ \/ /\ lock = 0 /\ lock' = r /\ jm' = "open" /\ runs' = [runs EXCEPT ![r] = "jmerge"]
     \/ /\ lock /= 0 /\ Fault /= "no-run-lock" /\ runs' = [runs EXCEPT ![r] = "done"]
        /\ UNCHANGED <<lock, jm>>
     \/ /\ lock /= 0 /\ Fault = "no-run-lock" /\ runs' = [runs EXCEPT ![r] = "jmerge"]
        /\ UNCHANGED <<lock, jm>>
  /\ UNCHANGED <<started, going, ran, recorded, passV, seen, kind, ticks>>
  /\ UNCHANGED <<restartV, batchV, waitV>>

\* With Fault = "no-run-lock": the run that went on without the lock ends.
EntrantEnds(r) ==
  /\ runs[r] = "jmerge" /\ lock /= r /\ runs' = [runs EXCEPT ![r] = "done"]
  /\ UNCHANGED <<started, going, ran, recorded, passV, runV, restartV, batchV, waitV>>

\* jbus/merge.py `write_json(where / f"ran-{at}.json", record)`, whether jmerge ended, timed out
\* or was busy.
Keeps(r) ==
  /\ runs[r] = "done" /\ ran' = ran \cup {r} /\ recorded' = recorded \cup {r}
  /\ runs' = [runs EXCEPT ![r] = "kept"]
  /\ UNCHANGED <<started, going, passV, runV, restartV, batchV, waitV>>

\* After the record, jbus/merge.py `write_json(where / f"ran-{at}.json", record) _unstamp(where, stamp)`,
\* which removes the stamp only where it is the run's own:
\* jbus/merge.py `if _stamp(where) == stamp: (where / STARTED).unlink(missing_ok=True)`. The
\* process ends, which gives going.lock back. With Fault = "unlink-first" the run removes whatever
\* stamp stands.
Unstamps(r) ==
  /\ runs[r] = "kept" /\ going' = 0
  /\ started' = IF Old \/ started.by = r THEN NoStamp ELSE started
  /\ runs' = [runs EXCEPT ![r] = "ended"]
  /\ UNCHANGED <<ran, recorded, passV, runV, restartV, batchV, waitV>>

\* The process dies, and the kernel gives going.lock back. jmerge dies with it where systemd stops
\* its unit, or goes on where it outlives a process started by hand (`start_new_session=True`).
ChildDies(r) ==
  /\ runs[r] \in {"spawned", "going", "jmerge", "done", "kept"}
  /\ runs' = [runs EXCEPT ![r] = "died"] /\ going' = IF going = r THEN 0 ELSE going
  /\ \/ /\ lock = r /\ lock' = 0 /\ jm' = "idle" /\ seen' = "none" /\ kind' = ""
     \/ UNCHANGED <<lock, jm, seen, kind>>
  /\ UNCHANGED <<started, ran, recorded, ticks, passV, restartV, batchV, waitV>>

\* STARTING goes by.
StampAges ==
  /\ started.by /= 0 /\ ~started.old /\ started' = [started EXCEPT !.old = TRUE]
  /\ UNCHANGED <<runs, going, ran, recorded, passV, runV, restartV, batchV, waitV>>

\* The merge tick's run of `jmerge --if-free`, with its own read of the open pull requests.
TickRuns ==
  /\ ticks < MaxTicks /\ lock = 0 /\ lock' = Tick /\ ticks' = ticks + 1 /\ jm' = "open"
  /\ UNCHANGED <<seen, kind, childV, passV, restartV, batchV, waitV>>

\* jmerge's run ends, from its last step, or dies at any step: the run lock goes back, and every
\* step it held in memory is gone.
Stops ==
  /\ lock /= 0 /\ jm /= "idle"
  /\ lock' = 0 /\ jm' = "idle" /\ seen' = "none" /\ kind' = ""
  /\ runs' = IF lock \in Runs /\ runs[lock] = "jmerge" THEN [runs EXCEPT ![lock] = "done"] ELSE runs
  /\ UNCHANGED <<started, going, ran, recorded, ticks, passV, restartV, batchV, waitV>>

----
\* Inside jmerge's run, in the order of `jmerge.cli`.

\* Whether P is in the list the run judges: the pass hands its read (`--pulls`), read before the
\* run started; the tick reads GitHub's, as does every run with Fault = "fresh-list".
Listed == IF lock = Tick \/ Fault = "fresh-list" THEN prOpen ELSE handed

\* `Repo.open_only`: jmerge/cli.py `self.base_merge.reopen(heads)`, then the records of pull
\* requests no longer listed go, but one whose reopen is owed: jmerge/rejudge.py `kept = {number: was for number, was in known.items() if number in numbers or _owed(was)}`.
\* `reopen`: one listed took (jmerge/rejudge.py `if number in numbers:`), one past
\* RESTART_MINUTES is `unopened`, and any other is reopened again
\* (jmerge/rejudge.py `elif why := self.reopened(number):`). A merged W's spell goes too:
\* jmerge/waits.py `self._write({n: spell for n, spell in spells.items() if int(n) in numbers})`.
OpenOnly ==
  /\ lock /= 0 /\ jm = "open"
  /\ "restart" \notin Inside => UNCHANGED <<stuck, prOpen>>
  /\ "restart" \in Inside =>
     \/ /\ stuck \in {"owed", "closed", "unopened"} /\ Listed /\ stuck' = "took"
        /\ UNCHANGED prOpen
     \/ /\ stuck \in {"owed", "closed"} /\ ~Listed /\ stuck' = "unopened" /\ UNCHANGED prOpen
     \/ /\ stuck \in {"owed", "closed"} /\ ~Listed /\ prOpen' \in {prOpen, TRUE}
        /\ UNCHANGED stuck
     \/ /\ stuck \in {"refused", "took"} /\ ~Listed /\ stuck' = "none" /\ UNCHANGED prOpen
     \/ /\ \/ stuck = "none"
           \/ stuck \in {"refused", "took"} /\ Listed
           \/ stuck = "unopened" /\ ~Listed
        /\ UNCHANGED <<stuck, prOpen>>
  /\ spell' = IF wMerged THEN FALSE ELSE spell
  /\ logged' = IF Fault = "log-on-sweep" /\ wMerged /\ spell THEN logged + 1 ELSE logged
  /\ jm' = "batch"
  /\ UNCHANGED <<lock, seen, kind, ticks, childV, passV, batchV, wMerged>>

\* `batch.state_of`, but late, which is time: jmerge/batch.py `if batch is None or tip != batch.tip or pull is None or pull.head != batch.commit:`,
\* jmerge/batch.py `return RERUN if rerunnable and len(batch.members) > 1 else FAILED`, and a failed
\* check whose jobs are those its rerun was started for is the first attempt, so pending.
BatchState ==
  IF batch = "none" \/ branch /= "batch" \/ ~draft \/ tipMoved THEN "none"
  ELSE IF ci = "passed" THEN "proven"
  ELSE IF ci = "failed" /\ ~rerunKept THEN "rerun"
  ELSE IF ci = "failed-again" THEN "failed"
  ELSE "pending"

\* `Record.fail`: jmerge/batch.py `self.most = max(self.most // 2, LEAST)` where `_full`, and
\* `_suspect`: jmerge/batch.py `self.batch, self.again = None, False`.
Fail ==
  /\ most' = IF batch = "full" THEN IF most > 1 THEN most - 1 ELSE 1 ELSE most
  /\ suspects' = TRUE /\ batch' = "none" /\ again' = FALSE /\ rerunKept' = FALSE

\* `Record.late`: jmerge/batch.py `if len(members) > 1 and not self.again:` builds it again, and
\* any other suspects its members and leaves the most.
Late ==
  /\ IF ~again
       THEN again' = TRUE /\ UNCHANGED suspects
       ELSE again' = FALSE /\ suspects' = TRUE
  /\ batch' = "none" /\ rerunKept' = FALSE /\ UNCHANGED most

\* `Record.prove`: jmerge/batch.py `self.most = min(self.most * 2, MOST)` where `_full`, so a
\* batch proven again is full no more; jmerge/batch.py `self.suspects, self.again = left, False`.
Prove ==
  /\ most' = IF batch = "full" /\ most < 3 THEN most + 1 ELSE most
  /\ batch' = IF batch = "full" /\ most < 3 THEN "part" ELSE batch
  /\ suspects' = FALSE /\ again' = FALSE /\ UNCHANGED rerunKept

\* `Repo.start_batch`: jmerge/cli.py `state = batch.state_of(kept, pull, tip, run, now, jobs)`, then
\* jmerge/cli.py `record.batch = None if state == batch.NONE else record.batch` and its write. A
\* batch to rerun keeps its rerun before it asks GitHub: jmerge/cli.py `record.rerun(jobs, now)`.
StartBatch ==
  /\ lock /= 0 /\ jm = "batch" /\ "batch" \in Inside
  /\ \E st \in (IF BatchState = "pending" THEN {"pending", "late"} ELSE {BatchState}) :
       /\ seen' = st
       /\ CASE st = "none" ->
                 batch' = "none" /\ rerunKept' = FALSE /\ jm' = "restart"
                 /\ UNCHANGED <<again, most, suspects>>
            [] st = "pending" ->
                 jm' = "restart" /\ UNCHANGED <<batch, rerunKept, again, most, suspects>>
            [] st = "rerun" ->
                 rerunKept' = TRUE /\ jm' = "rerun-ask" /\ UNCHANGED <<batch, again, most, suspects>>
            [] st = "failed" -> Fail /\ jm' = "restart"
            [] st = "late" -> Late /\ jm' = "restart"
            [] st = "proven" -> Prove /\ jm' = "restart"
  /\ UNCHANGED <<branch, draft, ci, tipMoved, merges, lock, kind, ticks>>
  /\ UNCHANGED <<childV, passV, restartV, waitV>>

\* The run follows no batch: the batch's switch is off, or the model does not follow it.
SkipsBatch ==
  /\ lock /= 0 /\ "batch" \notin Inside /\ jm \in {"batch", "batched"}
  /\ jm' = IF jm = "batch" THEN "restart" ELSE "end"
  /\ UNCHANGED <<lock, seen, kind, ticks, childV, passV, restartV, batchV, waitV>>

\* `Repo.rerun_batch`: jmerge/cli.py `if _run(self.main, "gh", "run", "rerun", one, "--failed", *self.about).returncode:`
\* GitHub refused fails the batch.
RerunAsks ==
  /\ lock /= 0 /\ jm = "rerun-ask" /\ jm' = "restart"
  /\ \/ /\ ci' = "rerunning" /\ seen' = "pending"
        /\ UNCHANGED <<batch, rerunKept, again, most, suspects>>
     \/ /\ Fail /\ seen' = "failed" /\ UNCHANGED ci
  /\ UNCHANGED <<branch, draft, tipMoved, merges, lock, kind, ticks>>
  /\ UNCHANGED <<childV, passV, restartV, waitV>>

\* `Repo.unstuck` on P, whose run GitHub left queued: jmerge/cli.py `if restarted is None and not rejudge.late(stuck.get("asked") or now.isoformat(), now):`.
\* `restart` keeps the try first, with the reopen owed:
\* jmerge/rejudge.py `one, since=since.isoformat(), asked=asked, reopen=True, url=one.url, check=check`
RestartAsks ==
  /\ lock /= 0 /\ jm = "restart" /\ "restart" \in Inside /\ Listed
  /\ stuck \in {"none", "refused"}
  /\ stuck' = "owed" /\ jm' = "closing"
  /\ UNCHANGED <<lock, seen, kind, ticks, prOpen, childV, passV, batchV, waitV>>

\* No run of P's is queued long enough, its restart was spent, or it is past RESTART_MINUTES.
RestartSkips ==
  /\ lock /= 0 /\ jm = "restart" /\ jm' = "mergew"
  /\ UNCHANGED <<lock, seen, kind, ticks, childV, passV, restartV, batchV, waitV>>

\* jmerge/rejudge.py `closed = self.gh("pr", "close", str(one.number))`: the close took; GitHub
\* refused it, jmerge/rejudge.py `self._restarted(one, reopen=None, why=_said(closed))`; or GitHub
\* took it and gh exited non-zero all the same (a reply lost on the way back), which jmerge keeps
\* as a refusal.
Closes ==
  /\ lock /= 0 /\ jm = "closing"
  /\ \/ /\ prOpen' = FALSE /\ jm' = "closed" /\ UNCHANGED stuck
     \/ /\ stuck' = "refused" /\ jm' = "mergew" /\ UNCHANGED prOpen
     \/ /\ ReplyLost /\ prOpen' = FALSE /\ stuck' = "refused" /\ jm' = "mergew"
  /\ UNCHANGED <<lock, seen, kind, ticks, childV, passV, batchV, waitV>>

\* jmerge/rejudge.py `self._restarted(one, closed=now)`
RecordsClosed ==
  /\ lock /= 0 /\ jm = "closed" /\ stuck' = "closed" /\ jm' = "reopening"
  /\ UNCHANGED <<lock, seen, kind, ticks, prOpen, childV, passV, batchV, waitV>>

\* jmerge/rejudge.py `said = self.gh("pr", "reopen", str(number))`: it took, or not, and the
\* reopen stays owed.
Reopens ==
  /\ lock /= 0 /\ jm = "reopening"
  /\ \/ prOpen' = TRUE /\ jm' = "reopened"
     \/ jm' = "mergew" /\ UNCHANGED prOpen
  /\ UNCHANGED <<lock, seen, kind, ticks, stuck, childV, passV, batchV, waitV>>

\* jmerge/rejudge.py `self._restarted(one, **({"why": why} if why else {"reopen": None, "took": now}))`
RecordsTook ==
  /\ lock /= 0 /\ jm = "reopened" /\ stuck' = "took" /\ jm' = "mergew"
  /\ UNCHANGED <<lock, seen, kind, ticks, prOpen, childV, passV, batchV, waitV>>

\* `Spells.saw`: W is seen ready and held: jmerge/waits.py `self._spell(spells, one, at).held(code, at)`
SeesW ==
  /\ lock /= 0 /\ jm = "mergew" /\ "waits" \in Inside /\ ~wMerged /\ spell' = TRUE /\ jm' = "batched"
  /\ UNCHANGED <<lock, seen, kind, ticks, logged, wMerged, childV, passV, restartV, batchV>>

\* jmerge merges W on GitHub, which moves main past the batch's tip; its `merged` line is said
\* after `gh pr merge`, a fetch and the clear-up.
MergesW ==
  /\ lock /= 0 /\ jm = "mergew" /\ "waits" \in Inside /\ ~wMerged /\ wMerged' = TRUE /\ tipMoved' = TRUE
  /\ jm' = "said"
  /\ UNCHANGED <<lock, seen, kind, ticks, spell, logged, childV, passV, restartV>>
  /\ UNCHANGED <<batch, rerunKept, again, most, suspects, branch, draft, ci, merges>>

\* W is not judged in this run, or not ready.
SkipsW ==
  /\ lock /= 0 /\ jm = "mergew" /\ jm' = "batched"
  /\ UNCHANGED <<lock, seen, kind, ticks, childV, passV, restartV, batchV, waitV>>

\* `Spells.merged`: jmerge/waits.py `store.append_jsonl(self.state / LOG, [wait.line()], sort_keys=True)`
LogsW ==
  /\ lock /= 0 /\ jm = "said" /\ logged' = logged + 1 /\ jm' = "logged"
  /\ UNCHANGED <<lock, seen, kind, ticks, spell, wMerged, childV, passV, restartV, batchV>>

\* Then jmerge/waits.py `self._write(spells) return wait`, without W's spell.
DropsW ==
  /\ lock /= 0 /\ jm = "logged" /\ spell' = FALSE /\ jm' = "batched"
  /\ UNCHANGED <<lock, seen, kind, ticks, logged, wMerged, childV, passV, restartV, batchV>>

\* `Repo.batched`: a proven batch merges: jmerge/cli.py `said = self.merge_members(kept.members, judged, kept.tip, default, passed)`
MergesBatch ==
  /\ lock /= 0 /\ jm = "batched" /\ "batch" \in Inside /\ seen = "proven" /\ batch /= "none"
  /\ merges' = merges + 1 /\ tipMoved' = TRUE /\ jm' = "merged"
  /\ UNCHANGED <<batch, rerunKept, again, most, suspects, branch, draft, ci>>
  /\ UNCHANGED <<lock, seen, kind, ticks, childV, passV, restartV, waitV>>

\* jmerge/cli.py `on.record.batch = None on.record.write() return said`, then the next batch is
\* built of the members left (`after_batch`).
BatchMerged ==
  /\ lock /= 0 /\ jm = "merged" /\ batch' = "none" /\ rerunKept' = FALSE /\ jm' = "building"
  /\ UNCHANGED <<again, most, suspects, branch, draft, ci, tipMoved, merges>>
  /\ UNCHANGED <<lock, seen, kind, ticks, childV, passV, restartV, waitV>>

\* A pending batch whose members all stand at their heads: each waits on it,
\* jmerge/cli.py `if set(kept.members) <= judged:`
WaitsOnBatch ==
  /\ lock /= 0 /\ jm = "batched" /\ "batch" \in Inside /\ seen = "pending" /\ batch /= "none"
  /\ jm' = "end"
  /\ UNCHANGED <<lock, seen, kind, ticks, childV, passV, restartV, batchV, waitV>>

\* `build_batch`: `Batching.chosen` picks the kind (`kind_of`). Alone or a guards batch is
\* proven in this run and kept nowhere, jmerge/cli.py `if chosen.kind != batch.CI:`, and the
\* suspects whose half is under LEAST go alone: jmerge/batch.py `record.alone(suspects)`.
Chooses ==
  /\ lock /= 0 /\ "batch" \in Inside
  /\ \/ jm = "building"
     \/ jm = "batched" /\ ~(seen = "proven" /\ batch /= "none")
  /\ \E k \in {"", "guards", "ci"} :
       /\ kind' = k
       /\ IF k = "ci"
            THEN jm' = "pushing" /\ UNCHANGED <<batch, rerunKept, again, suspects, tipMoved>>
            ELSE /\ batch' = "none" /\ rerunKept' = FALSE /\ again' = FALSE /\ suspects' = FALSE
                 /\ tipMoved' \in {tipMoved, TRUE} /\ jm' = "end"
  /\ UNCHANGED <<most, branch, draft, ci, merges, lock, seen, ticks, childV, passV, restartV, waitV>>

\* A batch not made: jmerge/cli.py `on.record.alone(on.record.suspects)`, `again` dropped, written,
\* and each member goes alone.
Unmade ==
  /\ suspects' = FALSE /\ again' = FALSE /\ batch' = "none" /\ rerunKept' = FALSE
  /\ jm' = "end"

\* jmerge/cli.py `why = why or batch.push(self.main, made.commit)`: the branch holds a commit no
\* record names yet, and CI starts on it.
Pushes ==
  /\ lock /= 0 /\ jm = "pushing"
  /\ \/ /\ branch' = "other" /\ ci' = "running" /\ jm' = "opening"
        /\ UNCHANGED <<batch, rerunKept, again, suspects>>
     \/ Unmade /\ UNCHANGED <<branch, ci>>
  /\ UNCHANGED <<most, draft, tipMoved, merges, lock, seen, kind, ticks>>
  /\ UNCHANGED <<childV, passV, restartV, waitV>>

\* jmerge/cli.py `if not why and on.pull is None:`, the standing draft opened where GitHub lists
\* none.
Opens ==
  /\ lock /= 0 /\ jm = "opening"
  /\ \/ /\ draft /\ jm' = "keeping" /\ UNCHANGED <<draft, batch, rerunKept, again, suspects>>
     \/ /\ ~draft /\ draft' = TRUE /\ jm' = "keeping"
        /\ UNCHANGED <<batch, rerunKept, again, suspects>>
     \/ /\ ~draft /\ Unmade /\ UNCHANGED draft
  /\ UNCHANGED <<most, branch, ci, tipMoved, merges, lock, seen, kind, ticks>>
  /\ UNCHANGED <<childV, passV, restartV, waitV>>

\* jmerge/cli.py `kept = batch.Batch(tip, made.tree, made.commit, made.members, now, narrowed=narrowed)`,
\* then written: a narrowed half is never full.
KeepsBatch ==
  /\ lock /= 0 /\ jm = "keeping"
  /\ batch' \in (IF suspects THEN {"part"} ELSE {"full", "part"})
  /\ branch' = "batch" /\ tipMoved' = FALSE /\ rerunKept' = FALSE /\ merges' = 0 /\ jm' = "end"
  /\ UNCHANGED <<again, most, suspects, draft, ci, lock, seen, kind, ticks>>
  /\ UNCHANGED <<childV, passV, restartV, waitV>>

----
\* GitHub.

\* CI's check of the commit on the branch ends.
CIEnds ==
  /\ \/ ci = "running" /\ ci' \in {"passed", "failed"}
     \/ ci = "rerunning" /\ ci' \in {"passed", "failed-again"}
  /\ UNCHANGED <<batch, rerunKept, again, most, suspects, branch, draft, tipMoved, merges>>
  /\ UNCHANGED <<childV, passV, runV, restartV, waitV>>

Next ==
  \/ PassStarts \/ PassTells \/ PassUnmarks \/ PassUnstamps \/ PassStamps \/ PassSpawns \/ PassReads \/ PassJudges
  \/ PassReplaces \/ PassDies
  \/ \E r \in Runs : TakesGoing(r) \/ RunsJmerge(r) \/ EntrantEnds(r) \/ Keeps(r)
                     \/ Unstamps(r) \/ ChildDies(r)
  \/ StampAges \/ TickRuns \/ Stops
  \/ OpenOnly \/ StartBatch \/ RerunAsks \/ RestartAsks \/ RestartSkips \/ Closes
  \/ RecordsClosed \/ Reopens \/ RecordsTook \/ SeesW \/ MergesW \/ SkipsW \/ LogsW \/ DropsW
  \/ SkipsBatch \/ MergesBatch \/ BatchMerged \/ WaitsOnBatch \/ Chooses \/ Pushes \/ Opens \/ KeepsBatch
  \/ CIEnds
Spec == Init /\ [][Next]_vars

----
\* The rules.

\* Every run's lines are judged once: a run that wrote its record has its lines sent, or the
\* record is still on disk for the next pass, or the pass holds it on its way to `_judged`.
RunHeard ==
  \A r \in recorded : r \in ran \/ judged[r] >= 1 \/ (pc = "judging" /\ reading = r)
\* The jmerge streak counts each run once.
StreakOnce == \A r \in Runs : judged[r] <= 1
\* The pass says a run ended with no record only of a run that wrote none.
NoFalseNoRecord == told \cap recorded = {}
\* A run that died before it wrote its record is told, or its stamp still stands, as the stamp or
\* the died file, to be told.
DeathTold ==
  \A r \in Runs : runs[r] = "died" /\ r \notin recorded =>
    r \in told \/ started.by = r \/ blamed = r
\* No two runs hold the repo: one run of `jmerge` at a time, the pass's, the tick's or one by hand.
OneRunAtATime == Cardinality({r \in Runs : runs[r] = "jmerge"} \cup ({lock} \ {0})) <= 1
\* A pull request jmerge closed to restart is reopened or the user is told: while it is closed,
\* its record owes the reopen, which each run tries again, or is `unopened`, which each run says
\* (`Repo.unopened`) and jbus raises to the home.
RestartReopens == ~prOpen => stuck \in {"owed", "closed", "unopened"}
\* A merged pull request's wait is logged once at most. Today it holds since `Spells.merged` runs
\* only at the merge, which comes once; a run that died between its append and its drop leaves a
\* spell of a merged W, so a sweep that logged such a spell (Fault = "log-on-sweep") logs it twice.
WaitLoggedOnce == logged <= 1
\* A merged pull request's wait is logged, once the run that merged it is past the log.
WaitKept == wMerged /\ jm /= "said" => logged = 1
\* A batch's members merge once.
BatchMergedOnce == merges <= 1
====
