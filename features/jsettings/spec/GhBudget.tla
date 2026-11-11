---- MODULE GhBudget ----
\* GitHub's API budget as jstack keeps it, over many processes at once. Every `gh` a process of
\* jstack runs goes through `jsettings.proc.run`: it waits for one of GH_CAP slots, runs, lets the
\* slot go, and then `_log` appends one line to gh-calls.jsonl, after it renames a log grown past
\* KEPT bytes to gh-calls.old.jsonl. A jbus pass first reads what is left (`budget.logged`): the
\* lowest `remaining` of the log's lines of the last WITHIN seconds and of gh-rate-limit.json, the
\* last answer of `gh api rate_limit`, which it asks for again under a lock where it has none.
\* With what is left at or under FLOOR the pass is held, and asks GitHub nothing else.
\*
\* GitHub's own count only falls (one call, one call less), so a line is named by the `remaining`
\* it logged, and a log is the set of the lines it holds. One window stands for `core` and
\* `graphql`: `held` reads the lower of them. A minute passing (`Tick`) ages every line logged so
\* far and the kept answer out of WITHIN.
\*
\* Fault = "unlocked-rotate" is today's code: the size check and the rename are two steps, with no
\* lock. Fault = "locked-rotate" is the fix: one lock held over the check and the rename.
EXTENDS Naturals, FiniteSets
CONSTANTS
  Procs,  \* the processes that run `gh` through `proc.run`
  Cap,    \* GH_CAP, the slots (jsettings/proc.py `GH_CAP = 16`)
  Kept,   \* KEPT, in lines: the log is renamed once it holds more than Kept
  Floor,  \* FLOOR (jsettings/budget.py `FLOOR = 1000`)
  Start,  \* what GitHub's window has left at the start
  Fault

Nothing == Start + 1  \* no reading: no line and no kept answer within WITHIN, or none on disk
None == "none"         \* a lock or a slot no process holds

VARIABLES
  \* D-081, gh-rate-limit.json: the last answer `logged` asked for, its `remaining` and whether its
  \* `at` is within WITHIN, or left = Nothing where none is on disk.
  \* jsettings/budget.py `os.replace(name, state / KEPT)`
  kept,
  \* D-082, .gh-rate-limit.json.lock: the process that holds it, or None.
  \* jsettings/budget.py `open(state / f".{KEPT}.lock", "a")), fcntl.LOCK_EX)`
  keepLock,
  \* D-083, the budget held gate, in each process's memory: "unread", "free", or "held".
  \* jsettings/budget.py `if low.remaining - calls > FLOOR:`, read by jbus/watch.py
  \* `held = budget.held(left)`
  gate,
  \* D-084, gh-calls.jsonl: the `remaining` of each line it holds. Empty is no file.
  \* jsettings/proc.py `log.write(json.dumps(line) + "\n")`
  log,
  \* D-085, gh-calls.old.jsonl: the lines of the log the last rename moved.
  \* jsettings/proc.py `os.replace(path, state / f"{Path(CALLS).stem}.old.jsonl")`
  old,
  \* D-086, gh-slots/<0..15>: the process that holds each slot's flock, or None.
  \* jsettings/proc.py `fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)`
  slots,
  left,     \* GitHub's own count of what is left, which no file of jstack's holds
  pc,       \* where each process is
  got,      \* the `remaining` GitHub answered the process's call with, which it logs
  began,    \* what `logged` read as the process's call started: "above", "low" (at or under
            \* the floor), "none" (no reading), the reading HeldWhenLow judges
  stale,    \* the lines older than WITHIN, which `_lowest` no longer reads
  dropped,  \* the lines no file holds any more
  rotLock   \* the fix's lock over the check and the rename: None in today's code
vars == <<kept, keepLock, gate, log, old, slots, left, pc, got, began, stale, dropped, rotLock>>

Lines == 0..Start
Slots == 1..Cap
Steps == {"idle", "locking", "relook", "free", "running", "logging", "checked", "rotating",
          "appending"}

TypeOK ==
  /\ kept \in [left : Lines \cup {Nothing}, fresh : BOOLEAN]
  /\ keepLock \in Procs \cup {None} /\ rotLock \in Procs \cup {None}
  /\ gate \in [Procs -> {"unread", "free", "held"}]
  /\ log \subseteq Lines /\ old \subseteq Lines /\ stale \subseteq Lines /\ dropped \subseteq Lines
  /\ slots \in [Slots -> Procs \cup {None}]
  /\ left \in Lines
  /\ pc \in [Procs -> Steps]
  /\ got \in [Procs -> Lines \cup {Nothing}] /\ began \in [Procs -> {"above", "low", "none"}]

Min(S) == CHOOSE m \in S : \A n \in S : m <= n

\* `_logged`: the lowest `remaining` of the log's lines of the last WITHIN seconds and of the kept
\* answer where its `at` is in them, or Nothing where neither says it.
Logged ==
  LET seen == (log \ stale) \cup (IF kept.fresh THEN {kept.left} ELSE {})
  IN IF seen = {} THEN Nothing ELSE Min(seen)

\* `held`: the gate a reading gives. No answer is held too.
Gate(reading) == IF reading = Nothing \/ reading <= Floor THEN "held" ELSE "free"
\* A reading in words: more than the floor left, at or under it, or none.
Said(reading) == IF reading = Nothing THEN "none" ELSE IF reading <= Floor THEN "low" ELSE "above"

Init ==
  /\ kept = [left |-> Nothing, fresh |-> FALSE] /\ keepLock = None /\ rotLock = None
  /\ gate = [p \in Procs |-> "unread"]
  /\ log = {} /\ old = {} /\ stale = {} /\ dropped = {}
  /\ slots = [s \in Slots |-> None]
  /\ left = Start
  /\ pc = [p \in Procs |-> "idle"]
  /\ got = [p \in Procs |-> Nothing] /\ began = [p \in Procs |-> "none"]

files == <<kept, log, old, stale, dropped, left>>

\* A pass reads the budget: jbus/watch.py `left = allowance.logged(paths.jbus_state_dir(),
\* asked=ask)`, which reads the files with no lock first: jsettings/budget.py `seen =
\* _lowest(state / proc.CALLS, since, now)` and `if at >= since:`. With a reading, the gate is set.
Look(p) ==
  /\ pc[p] = "idle"
  /\ IF Logged = Nothing  \* jsettings/budget.py `if len(seen) < len(WINDOWS):`
       THEN pc' = [pc EXCEPT ![p] = "locking"] /\ UNCHANGED gate
       ELSE /\ gate' = [gate EXCEPT ![p] = Gate(Logged)]
            /\ pc' = [pc EXCEPT ![p] = IF Gate(Logged) = "free" THEN "free" ELSE "idle"]
  /\ UNCHANGED <<keepLock, slots, got, began, rotLock>> /\ UNCHANGED files

\* jsettings/budget.py `with _locked(state):`
TakeKeepLock(p) ==
  /\ pc[p] = "locking" /\ keepLock = None
  /\ keepLock' = p /\ pc' = [pc EXCEPT ![p] = "relook"]
  /\ UNCHANGED <<gate, slots, got, began, rotLock>> /\ UNCHANGED files

\* Under the lock it reads the files again, and where they still say nothing it asks, and keeps
\* the answer: jsettings/budget.py `answer = read(asked)` and `if answer is not None:`. Asking
\* spends nothing. Where GitHub gives no answer the pass is held.
Relook(p) ==
  /\ pc[p] = "relook"
  /\ IF Logged /= Nothing
       THEN /\ gate' = [gate EXCEPT ![p] = Gate(Logged)] /\ UNCHANGED kept
            /\ pc' = [pc EXCEPT ![p] = IF Gate(Logged) = "free" THEN "free" ELSE "idle"]
       ELSE \/ /\ kept' = [left |-> left, fresh |-> TRUE]
               /\ gate' = [gate EXCEPT ![p] = Gate(left)]
               /\ pc' = [pc EXCEPT ![p] = IF Gate(left) = "free" THEN "free" ELSE "idle"]
            \/ /\ gate' = [gate EXCEPT ![p] = "held"] /\ pc' = [pc EXCEPT ![p] = "idle"]
               /\ UNCHANGED kept
  /\ keepLock' = None
  /\ UNCHANGED <<slots, got, began, rotLock, log, old, stale, dropped, left>>

\* A free pass starts another `gh`: jsettings/proc.py `with _slot(state / SLOTS):`, which takes
\* the first slot whose flock is free, or waits while all are held. The gate is not read again
\* for the call: the pass read it once, in `look`. GitHub refuses a call once the window is
\* spent (jmerge's backoff, left out), so a pass makes none at 0.
Call(p) ==
  /\ pc[p] = "free" /\ left > 0
  /\ \E s \in Slots :
       /\ slots[s] = None  \* jsettings/proc.py `except BlockingIOError:`
       /\ slots' = [slots EXCEPT ![s] = p]
  /\ began' = [began EXCEPT ![p] = Said(Logged)]
  /\ pc' = [pc EXCEPT ![p] = "running"]
  /\ UNCHANGED <<kept, keepLock, gate, got, rotLock>> /\ UNCHANGED files

\* The pass ends: it makes no more calls, and its gate goes with its process.
Done(p) ==
  /\ pc[p] = "free"
  /\ pc' = [pc EXCEPT ![p] = "idle"] /\ gate' = [gate EXCEPT ![p] = "unread"]
  /\ UNCHANGED <<kept, keepLock, slots, got, began, rotLock>> /\ UNCHANGED files

\* gh runs, GitHub counts it, and the slot goes as `with _slot` ends.
Run(p) ==
  /\ pc[p] = "running"
  /\ left' = left - 1 /\ got' = [got EXCEPT ![p] = left - 1]
  /\ slots' = [s \in Slots |-> IF slots[s] = p THEN None ELSE slots[s]]
  /\ pc' = [pc EXCEPT ![p] = "logging"]
  /\ UNCHANGED <<kept, keepLock, gate, log, old, stale, dropped, began, rotLock>>

\* The fix takes a lock before the size check, and today's code does not.
LockRotate(p) ==
  /\ pc[p] = "logging"
  /\ IF Fault = "locked-rotate"
       THEN rotLock = None /\ rotLock' = p
       ELSE UNCHANGED rotLock
  /\ pc' = [pc EXCEPT ![p] = "checked"]
  /\ UNCHANGED <<kept, keepLock, gate, slots, got, began>> /\ UNCHANGED files

\* jsettings/proc.py `if path.stat().st_size > KEPT:`
Check(p) ==
  /\ pc[p] = "checked"
  /\ pc' = [pc EXCEPT ![p] = IF Cardinality(log) > Kept THEN "rotating" ELSE "appending"]
  /\ rotLock' = IF pc'[p] = "appending" /\ rotLock = p THEN None ELSE rotLock
  /\ UNCHANGED <<kept, keepLock, gate, slots, got, began>> /\ UNCHANGED files

\* The rename: the log becomes the old log, and the old log's lines are gone. A log another
\* process renamed first is no file, and the rename fails, which `contextlib.suppress(OSError)`
\* lets go.
Rotate(p) ==
  /\ pc[p] = "rotating"
  /\ IF log /= {}
       THEN old' = log /\ log' = {} /\ dropped' = dropped \cup old
       ELSE UNCHANGED <<old, log, dropped>>
  /\ rotLock' = IF rotLock = p THEN None ELSE rotLock
  /\ pc' = [pc EXCEPT ![p] = "appending"]
  /\ UNCHANGED <<kept, keepLock, gate, slots, got, began, stale, left>>

\* `open(path, "a")` and one write: the line, made whole, lands in the log, or the log it makes.
Append(p) ==
  /\ pc[p] = "appending"
  /\ log' = log \cup {got[p]}
  /\ pc' = [pc EXCEPT ![p] = "free"]
  /\ UNCHANGED <<kept, keepLock, gate, slots, got, began, old, stale, dropped, left, rotLock>>

\* A minute passes: each line logged so far and the kept answer are older than WITHIN.
Tick ==
  /\ (log \ stale /= {} \/ kept.fresh)
  /\ stale' = stale \cup log /\ kept' = [kept EXCEPT !.fresh = FALSE]
  /\ UNCHANGED <<keepLock, gate, log, old, slots, left, pc, got, began, dropped, rotLock>>

Next ==
  \/ Tick
  \/ \E p \in Procs :
       \/ Look(p) \/ TakeKeepLock(p) \/ Relook(p) \/ Call(p) \/ Done(p) \/ Run(p)
       \/ LockRotate(p) \/ Check(p) \/ Rotate(p) \/ Append(p)
Spec == Init /\ [][Next]_vars

\* A rotation never drops lines another rotation kept: gh-calls.old.jsonl holds the whole log
\* that a rename found past KEPT, and never a log a second rename moved over it before that log
\* grew past KEPT.
NoLostGeneration == old = {} \/ Cardinality(old) > Kept

\* No call starts while the kept budget is under the floor: each call that runs began with
\* `logged` reading more than FLOOR left, or reading nothing. At the floor counts as under it, as
\* `held` counts it.
HeldWhenLow == \A p \in Procs : pc[p] = "running" => began[p] /= "low"

\* At most GH_CAP `gh` run at once, each in a slot of its own.
CappedRuns ==
  \A p \in Procs : pc[p] = "running" => Cardinality({s \in Slots : slots[s] = p}) = 1
====
