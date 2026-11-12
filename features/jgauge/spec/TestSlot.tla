---- MODULE TestSlot ----
\* The test slots of one machine and every record around them, as jgauge, jbus and jroles keep
\* them: the full lane's and the short lane's flocks, the short lane's line, the waiters of a full
\* slot with the claim a wake gives, the holders of a run, the slot log, the usage ledger with its
\* retry file and its note of capped reads, and the threads that wait on a capped pool.
\* Every process can die between any two of its steps (a kill, an OOM, a reboot): the kernel lets
\* go of each flock it held, and the files keep what it wrote. The command a slot runs may outlive
\* the `jgauge test-slot` that started it.
\*
\* The machine room has four rooms that share no variable, and each rule reads the variables of
\* one room. Init picks the room and Next runs that room's steps alone, so TLC checks the sum of
\* the rooms' states and not their product, which it could not finish:
\*   "full"   a crew's full-lane call with --thread, a desk's call with no thread, and jbus's pass
\*            (slotwait.wake, then slotwait.wake_ended), over one full slot;
\*   "short"  a crew's short-lane call with --thread, which waits in the line, and a short call
\*            with no thread, which takes a free slot with no place in the line, with jbus's
\*            wake_ended, over one short slot;
\*   "ledger" the three writers of the limits ledger (jgauge limits, hooks/limits.sh, jbus) and
\*            the note of each capped read;
\*   "pool"   a crew that waits on a capped review pool, and jbus's slotwait.wake_capped.
\* The holders file and the slot log are written by both lanes. A process writes only its own
\* entry and its own rows, each change of the holders file is under its lock, and jbus forgets
\* by id, so the "full" and "short" rooms each check their own entries.
\*
\* Fault = "today" is the code as it is: slotwait.wake counts `spare` outside the waiters lock
\* and records the wake after its send. A holder with no end is forgotten only once its
\* `jgauge test-slot` is gone too, a command ends with the `jgauge test-slot` that holds its
\* slot, a pid another process took reads as gone, and the ledger's writers read, merge and
\* replace it under one lock. Fault = "none" is the mode that passes: the wake is counted and
\* recorded under one hold of the waiters lock before the send.
\* The canary "spare-outside-lock" puts today's one fault back into the mode that passes, and
\* "forget-unended", "orphan-command", "pid-alone" and "no-ledger-lock" put back the ones that
\* are closed: a holder with no end forgotten while its `jgauge test-slot` lives to write the
\* end, a command that lives on after its `jgauge test-slot` died, a holder judged running by
\* its pid alone, with no check that the pid is still its command's, and a ledger writer that
\* reads and replaces the file with no lock.
\* PidReuse lets another process take the pid of a holder's dead command. Mortal is the set of
\* the processes that can be killed: TestSlot.cfg has every one, "bus" for jbus's slot pass,
\* "writers" for the ledger's writers and "pool" for the pool's crew and jbus; the chart's
\* config keeps fewer, so its state graph fits in a picture. Chart = TRUE, in the chart's config
\* alone, draws the full room with no holders file (the crew's run records none, and jbus's pass
\* there ends after slotwait.wake): the short room draws the holders.
EXTENDS Naturals, FiniteSets
CONSTANTS Fault, PidReuse, Rooms, Mortal, Chart

FullProcs == {"crew", "desk"}
ShortProcs == {"short", "quick"}
Procs == FullProcs \cup ShortProcs
Threaded == {"crew", "short"}
FullSlots == 1..1
ShortSlots == 1..1
Writers == {"limits", "hook", "jbus"}
WaitIds == {1, 2}
TodayFaults == {"spare-outside-lock"}
Has(f) == Fault = f \/ (Fault = "today" /\ f \in TodayFaults)

VARIABLES
  \* D-048 test-slot.<n>.lock, the full lane's flock: who holds each, or "free". `_claim` takes
  \* it under the waiters lock, jgauge/slot.py `got = _first_free(locks, lane) if room > 0 else
  \* None`, and `_first_free` holds it: jgauge/slot.py `fcntl.flock(held, fcntl.LOCK_EX |
  \* fcntl.LOCK_NB) except BlockingIOError: os.close(held)`
  full,
  \* D-049 test-slot-short.<n>.lock, the short lane's flock, by the same `_first_free`: with a
  \* thread, jgauge/slot.py `if first() and (held := _first_free(locks, lane)) is not None:`,
  \* and with none, jgauge/slot.py `return _first_free(locks, lane)`
  short,
  \* D-050 test-slot-short.line/, the tickets of the short calls that wait: "live" while the
  \* caller holds its ticket's lock, "dead" for one a caller that died left.
  \* jgauge/slot.py `hidden.rename(line / ticket)` puts it in, jgauge/slot.py
  \* `(line / ticket).unlink(missing_ok=True)` takes it out, and `_ahead` takes out one no one
  \* holds: jgauge/slot.py `other.unlink(missing_ok=True)`
  line,
  \* D-054 test-slot-waiters.json, the threads that wait on a full slot.
  \* Register: jgauge/waiters.py `return [*others, wait]`. Drop: jgauge/waiters.py
  \* `FILE.change(locks, lambda waiters: [one for one in waiters if one.thread != thread])`.
  \* Forget, from jbus: jgauge/waiters.py `FILE.change(locks, lambda waiters: [one for one in
  \* waiters if one.id not in ids])`
  waiters,
  \* D-055 Waiter.woken: "none", or the wake's age: "holds" up to HOLDS, "past" after it, and
  \* "lapsed" after FORGOTTEN. jgauge/waiters.py `replace(one, woken=stamp(now)) if one.id ==
  \* wait and not one.woken else one`, which jbus calls: jbus/slotwait.py
  \* `waiters.woken(slot.locks_dir(), one.id, run.now)`
  woken,
  \* D-056 test-slot-waiters.lock: who holds it, or "free". jsettings/store.py
  \* `fcntl.flock(lock, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)`, held across
  \* `_claim`'s count and take: jgauge/slot.py `with waiters.locked(locks) as held:`
  waitersLock,
  \* D-057 test-slot-holders.json, the runs with --thread on record. Hold: jgauge/holders.py
  \* `FILE.change(locks, lambda held: [*held, run])`. Forget: jgauge/holders.py
  \* `FILE.change(locks, lambda held: [one for one in held if one.id not in ids])`, which jbus
  \* calls: jbus/slotwait.py `holders.forget(locks, over)`
  holders,
  \* D-058 Holder.ended and code: the holders whose end is on record.
  \* jgauge/holders.py `replace(one, ended=jsettings.stamp(now, z=True), code=code)`
  ended,
  \* D-059 test-slot-holders.lock: who holds it, or "free". jsettings/store.py
  \* `with locked(at, self.lock):`, around each change of a LockedList.
  holdersLock,
  \* D-060 slots.jsonl: each process's rows of its last run, "none", "take", or "release".
  \* jgauge/slotlog.py `row = {"at": _stamp(now), "event": "take", **fields, "waited":
  \* round(waited, 3)}` and jgauge/slotlog.py `"event": "release",`, each appended by
  \* jgauge/slotlog.py `os.write(written, (json.dumps(row) + "\n").encode())`
  slotlog,
  \* D-066 <ledger>.retry: whether the file stands. `_keep_retry` writes it: jgauge/limits.py
  \* `file.write_text(f"{int(until.timestamp())}\n")`, and the endpoint's answer takes it out:
  \* jgauge/limits.py `retry_file(home.instance).unlink(missing_ok=True)`
  retry,
  \* D-067 capped.jsonl: the last line's read of the ledger, the writers whose record it saw.
  \* The lines before it never change. jgauge/limits.py
  \* `handle.write(json.dumps(record, sort_keys=True) + "\n")`, from `jgauge limits`
  \* (jgauge/limits.py `note(now, "limits")`) and from jbus's pass (jbus/kpis.py
  \* `limits.note(now, "pass")`).
  spells,
  \* D-070 the limits ledger, `<window> <pct> <reset>`: the writers whose record the file keeps.
  \* `merge` keeps the larger share of one window, so a record merged in stays in.
  \* jroles/ledger.py `os.replace(temporary, file)` (ledger.write, which `jgauge limits` calls,
  \* jgauge/limits.py `ledger.write(record, read=source == "endpoint")`, and jbus,
  \* jbus/failover.py `if record and ledger.write(cap.record(move.capped)):`), and
  \* jgauge/hooks/limits.sh `{ printf '%s\n' "$merged" >"$next" && mv -f "$next" "$LIMITS"; }
  \* 2>/dev/null`
  ledger,
  \* D-073 pool-waiters.json, the ids of the waits on file. Register: jroles/waits.py
  \* `wait = Wait(thread, role, moment, since, secrets.token_hex(6))`. Drop: jroles/waits.py
  \* `at, lambda waits: [one for one in waits if (one.thread, one.role) != (thread, role)]`.
  \* Forget: jroles/waits.py `FILE.change(at, lambda waits: [one for one in waits if one.id not
  \* in ids])`, which jbus calls: jbus/slotwait.py `waits.forget(at, {one.id})`
  pool,
  \* D-074 pool-waiters.lock: who holds it, or "free". jsettings/store.py
  \* `with self.held(at): was = self.peek(at)`, around each change of a LockedList.
  poolLock,
  \* The model's own: which room runs, where each process is, its command, the history the
  \* rules read, and the copies a step works from.
  room,     \* the room Init picked
  pc,       \* where each process of the slot rooms is in its `jgauge test-slot` call
  bus,      \* where jbus's pass is in slotwait.wake and slotwait.wake_ended
  child,    \* each process's command: "none", "alive", or "dead"
  reused,   \* the holders whose dead command's pid another process took
  waitId,   \* the id of the crew's wait, flipped by each new wait, so a forget or a wake by id
            \* touches only the wait it read
  wsnap,    \* the waiters jbus read: [in, woken, id]
  hsnap,    \* the holders jbus read, and their ends: [in, ended]
  missed,   \* the crews that ran again while their wake's claim held, and found no slot
  lostEnd,  \* the runs whose end their holder wrote after jbus forgot them
  lpc,      \* where each ledger writer is
  local,    \* each ledger writer's copy of the ledger, read before it merges
  wrote,    \* the writers whose write of the ledger has ended
  ledgerLock, \* who holds <ledger>.lock from its read to its write, or "free"
  ppc,      \* where the crew that waits on the pool is
  jpc,      \* where jbus's slotwait.wake_capped is
  psnap,    \* the due wait jbus read, or 0
  due,      \* the waits whose cap has ended
  used,     \* the wait ids made
  told,     \* the waits jbus told the crew of
  byThread  \* the waits the crew itself took out, or replaced with a new one

carriers == <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock,
              slotlog, retry, spells, ledger, pool, poolLock>>
slotVars == <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock,
              slotlog, pc, bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd>>
ledgerVars == <<retry, spells, ledger, lpc, local, wrote, ledgerLock>>
poolVars == <<pool, poolLock, ppc, jpc, psnap, due, used, told, byThread>>
vars == <<carriers, room, pc, bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd,
          lpc, local, wrote, ledgerLock, ppc, jpc, psnap, due, used, told, byThread>>

\* Each step runs in its room and leaves the other rooms as they are.
InSlots == room \in {"full", "short"} /\ UNCHANGED <<ledgerVars, poolVars, room>>
InLedger == room = "ledger" /\ UNCHANGED <<slotVars, poolVars, room>>
InPool == room = "pool" /\ UNCHANGED <<slotVars, ledgerVars, room>>

FullPcs == {"off", "lock", "count", "register", "registering", "drop", "dropping", "logtake",
            "spawn", "hold", "holding", "wait", "end", "ending", "logrelease", "close"}
ShortPcs == {"enter", "first", "poll"}
BusPcs == {"idle", "read", "forget", "forgetting", "spare", "sparing", "tell", "wake",
           "waking", "hread", "judge", "hforget", "hforgetting"}

TypeOK ==
  /\ room \in {"full", "short", "ledger", "pool"}
  /\ full \in [FullSlots -> FullProcs \cup {"free"}]
  /\ short \in [ShortSlots -> ShortProcs \cup {"free"}]
  /\ line \subseteq {"live", "dead"}
  /\ waiters \subseteq {"crew"}
  /\ woken \in {"none", "holds", "past", "lapsed"}
  /\ waitersLock \in {"free", "crew", "desk", "bus"}
  /\ holders \subseteq Threaded /\ ended \subseteq holders
  /\ holdersLock \in {"free", "bus"} \cup Threaded
  /\ slotlog \in [Procs -> {"none", "take", "release"}]
  /\ retry \in BOOLEAN /\ spells \subseteq Writers /\ ledger \subseteq Writers
  /\ pool \subseteq WaitIds /\ poolLock \in {"free", "crew", "bus"}
  /\ pc \in [Procs -> FullPcs \cup ShortPcs]
  /\ bus \in BusPcs
  /\ child \in [Procs -> {"none", "alive", "dead"}]
  /\ reused \subseteq holders /\ missed \subseteq {"crew"} /\ lostEnd \subseteq Threaded
  /\ waitId \in {0, 1}
  /\ lpc \in [Writers -> {"idle", "fetched", "read", "unlink", "done"}]
  /\ local \in [Writers -> SUBSET Writers] /\ wrote \subseteq Writers
  /\ ledgerLock \in Writers \cup {"free"}
  /\ ppc \in {"off", "register", "registering", "drop", "dropping"}
  /\ jpc \in {"off", "tell", "forget", "forgetting"}
  /\ psnap \in WaitIds \cup {0}
  /\ due \subseteq used /\ used \subseteq WaitIds /\ told \subseteq used /\ byThread \subseteq used

Init ==
  /\ room \in Rooms
  /\ full = [n \in FullSlots |-> "free"] /\ short = [n \in ShortSlots |-> "free"]
  /\ line = {} /\ waiters = {} /\ woken = "none" /\ waitersLock = "free"
  /\ holders = {} /\ ended = {} /\ holdersLock = "free"
  /\ slotlog = [p \in Procs |-> "none"]
  /\ retry = FALSE /\ spells = {} /\ ledger = {}
  /\ pool = {} /\ poolLock = "free"
  /\ pc = [p \in Procs |-> "off"] /\ bus = "idle" /\ child = [p \in Procs |-> "none"]
  /\ reused = {} /\ waitId = 0
  /\ wsnap = [in |-> FALSE, woken |-> "none", id |-> 0] /\ hsnap = [in |-> {}, ended |-> {}]
  /\ missed = {} /\ lostEnd = {}
  /\ lpc = [w \in Writers |-> "idle"] /\ local = [w \in Writers |-> {}] /\ wrote = {}
  /\ ledgerLock = "free"
  /\ ppc = "off" /\ jpc = "off" /\ psnap = 0 /\ due = {} /\ used = {} /\ told = {}
  /\ byThread = {}

\* ---- The slots: helpers ----

FreeFull == {n \in FullSlots : full[n] = "free"}
FreeShort == {n \in ShortSlots : short[n] = "free"}
HoldsSlot(p) == (\E n \in FullSlots : full[n] = p) \/ (\E n \in ShortSlots : short[n] = p)
\* jgauge/waiters.py `return bool(waiter.woken) and now - jsettings.when(waiter.woken) <= HOLDS`
Holding == "crew" \in waiters /\ woken = "holds"
\* jgauge/waiters.py `return sum(one.lane == lane and one.thread != but and holding(one, now)
\* for one in held)`
Claims(but) == IF Holding /\ but /= "crew" THEN 1 ELSE 0
\* jgauge/holders.py `_alive(one.pid, one.start) or _alive(one.keeper, one.keeper_start)` and
\* jgauge/holders.py `now == start`: a holder runs while its end is not on record and its
\* command's pid, or its `jgauge test-slot`'s, has the start time its run recorded, so a pid
\* another process took reads as gone. Running is the command's half, which NoLostHolder judges;
\* the `jgauge test-slot`'s half is Over's `pc[p] = "off"`. The canary "pid-alone" asks only
\* whether some process has the command's pid, as the code did before, and a reused pid reads as
\* running.
PidRuns(p) == child[p] = "alive" \/ (Has("pid-alone") /\ p \in reused)
Running(p) == p \in holders /\ p \notin ended /\ PidRuns(p)
\* The steps of a call during which `jgauge test-slot` holds its slot.
\* The processes whose run goes on the holders file: a call with --thread.
OnFile == IF Chart THEN Threaded \ {"crew"} ELSE Threaded
\* Where jbus's pass goes after slotwait.wake.
AfterWake == IF Chart THEN "idle" ELSE "hread"
Holds == {"drop", "dropping", "logtake", "spawn", "hold", "holding", "wait", "end", "ending",
          "logrelease", "close"}

\* ---- The full lane: a crew with --thread, and a desk with no thread ----

\* A call starts: `jgauge test-slot [--thread <id>]`. The model waits for the run before it to be
\* gone from the holders file and its command to end: the file keeps two runs of one thread
\* apart by id, and so does jbus's forget.
Start(p) ==
  /\ InSlots
  /\ room = IF p \in FullProcs THEN "full" ELSE "short"
  /\ pc[p] = "off" /\ p \notin holders /\ child[p] /= "alive"
  /\ pc' = [pc EXCEPT ![p] = CASE p \in FullProcs -> "lock"
                                [] p = "short" -> "enter"
                                [] OTHER -> "poll"]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock,
                 slotlog, bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* `_claim` takes the waiters lock: jgauge/slot.py `with waiters.locked(locks) as held:`
ClaimLock(p) ==
  /\ InSlots
  /\ pc[p] = "lock" /\ waitersLock = "free"
  /\ waitersLock' = p /\ pc' = [pc EXCEPT ![p] = "count"]
  /\ UNCHANGED <<full, short, line, waiters, woken, holders, ended, holdersLock, slotlog, bus,
                 child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* `_claim` counts and takes under the lock, and lets it go: jgauge/slot.py
\* `room = spare(lane, held, datetime.now(UTC), thread)`, and jgauge/slot.py
\* `return free(lane) - waiters.claims(held, name(lane), but, now)`. A crew with no slot to spare
\* registers (jgauge/slot.py `waiters.register(locks, thread, name(lane), lane.slots, command or
\* [], now)`), and a desk waits in its call and tries again (jgauge/slot.py
\* `while (held := _free_for(locks, lane)) is None:`).
\* A crew whose wake's claim holds and that finds no slot goes in `missed`.
ClaimCount(p) ==
  /\ InSlots
  /\ pc[p] = "count" /\ waitersLock = p
  /\ LET spare == Cardinality(FreeFull) - Claims(p) IN
       /\ IF spare > 0
            THEN \E n \in FreeFull :
                   /\ full' = [full EXCEPT ![n] = p]
                   /\ pc' = [pc EXCEPT ![p] = IF p = "crew" THEN "drop" ELSE "logtake"]
            ELSE /\ full' = full
                 /\ pc' = [pc EXCEPT ![p] = IF p = "crew" THEN "register" ELSE "lock"]
       /\ missed' = IF p = "crew" /\ Holding /\ spare <= 0 THEN missed \cup {p} ELSE missed
  /\ waitersLock' = "free"
  /\ UNCHANGED <<short, line, waiters, woken, holders, ended, holdersLock, slotlog, bus, child,
                 reused, waitId, wsnap, hsnap, lostEnd>>

\* Each change of the waiters file takes its lock, then writes and lets it go.
WaitersLock(p, from, to) ==
  /\ InSlots
  /\ pc[p] = from /\ waitersLock = "free"
  /\ waitersLock' = p /\ pc' = [pc EXCEPT ![p] = to]
  /\ UNCHANGED <<full, short, line, waiters, woken, holders, ended, holdersLock, slotlog, bus,
                 child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

RegisterLock == WaitersLock("crew", "register", "registering")

\* jgauge/waiters.py `if mine and same and not mine.woken:` keeps the wait and its id; a woken
\* one gets a new wait with a new id and no wake. The crew ends its turn.
Register ==
  /\ InSlots
  /\ pc["crew"] = "registering" /\ waitersLock = "crew"
  /\ waiters' = waiters \cup {"crew"}
  /\ IF "crew" \in waiters /\ woken = "none"
       THEN UNCHANGED <<woken, waitId>>
       ELSE woken' = "none" /\ waitId' = 1 - waitId
  /\ waitersLock' = "free" /\ pc' = [pc EXCEPT !["crew"] = "off"]
  /\ UNCHANGED <<full, short, line, holders, ended, holdersLock, slotlog, bus, child, reused,
                 wsnap, hsnap, missed, lostEnd>>

DropLock == WaitersLock("crew", "drop", "dropping")

\* A crew that took its slot leaves the waiters file, after `_claim` let the lock go:
\* jgauge/slot.py `waiters.drop(locks, thread)`
Drop ==
  /\ InSlots
  /\ pc["crew"] = "dropping" /\ waitersLock = "crew"
  /\ waiters' = waiters \ {"crew"} /\ woken' = "none"
  /\ waitersLock' = "free" /\ pc' = [pc EXCEPT !["crew"] = "logtake"]
  /\ UNCHANGED <<full, short, line, holders, ended, holdersLock, slotlog, bus, child, reused,
                 waitId, wsnap, hsnap, missed, lostEnd>>

\* ---- The short lane: a crew with --thread waits in the line; a call with no thread polls ----

\* jgauge/slot.py `fcntl.flock(fd, fcntl.LOCK_EX)`, then the rename puts the ticket in the line.
Enter ==
  /\ InSlots
  /\ pc["short"] = "enter"
  /\ line' = line \cup {"live"} /\ pc' = [pc EXCEPT !["short"] = "first"]
  /\ UNCHANGED <<full, short, waiters, woken, waitersLock, holders, ended, holdersLock, slotlog,
                 bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* `_ahead` unlinks a ticket ahead whose lock no one holds, and the first caller takes a free
\* slot and leaves the line: jgauge/slot.py `if first() and (held := _first_free(locks, lane))
\* is not None:`
First ==
  /\ InSlots
  /\ pc["short"] = "first"
  /\ \/ /\ "dead" \in line /\ line' = line \ {"dead"}
        /\ UNCHANGED <<short, pc>>
     \/ /\ "dead" \notin line /\ FreeShort /= {}
        /\ \E n \in FreeShort : short' = [short EXCEPT ![n] = "short"]
        /\ line' = line \ {"live"} /\ pc' = [pc EXCEPT !["short"] = "logtake"]
  /\ UNCHANGED <<full, waiters, woken, waitersLock, holders, ended, holdersLock, slotlog, bus,
                 child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* At the ceiling the call takes none and leaves the line: jgauge/slot.py
\* `if time.monotonic() >= until:`, and it ends 76.
GiveUp ==
  /\ InSlots
  /\ pc["short"] = "first"
  /\ line' = line \ {"live"} /\ pc' = [pc EXCEPT !["short"] = "off"]
  /\ UNCHANGED <<full, short, waiters, woken, waitersLock, holders, ended, holdersLock, slotlog,
                 bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* A short call with no thread has no place in the line: jgauge/slot.py
\* `return _first_free(locks, lane)`, again until a slot is free.
Poll ==
  /\ InSlots
  /\ pc["quick"] = "poll" /\ FreeShort /= {}
  /\ \E n \in FreeShort : short' = [short EXCEPT ![n] = "quick"]
  /\ pc' = [pc EXCEPT !["quick"] = "logtake"]
  /\ UNCHANGED <<full, line, waiters, woken, waitersLock, holders, ended, holdersLock, slotlog,
                 bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* ---- The run under a slot, in both lanes: `run` in jgauge/slot.py ----

\* jgauge/slot.py `logged = slotlog.take(`
LogTake(p) ==
  /\ InSlots
  /\ pc[p] = "logtake" /\ slotlog' = [slotlog EXCEPT ![p] = "take"]
  /\ pc' = [pc EXCEPT ![p] = "spawn"]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock, bus,
                 child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* jgauge/slot.py `child = subprocess.Popen(`, or a command that cannot start:
\* jgauge/slot.py `code = 126 if isinstance(error, PermissionError) else 127`
Spawn(p) ==
  /\ InSlots
  /\ pc[p] = "spawn"
  /\ \/ /\ child' = [child EXCEPT ![p] = "alive"]
        /\ pc' = [pc EXCEPT ![p] = IF p \in OnFile THEN "hold" ELSE "wait"]
     \/ /\ UNCHANGED child /\ pc' = [pc EXCEPT ![p] = "logrelease"]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock,
                 slotlog, bus, reused, waitId, wsnap, hsnap, missed, lostEnd>>

HoldersLock(p, from, to) ==
  /\ InSlots
  /\ pc[p] = from /\ holdersLock = "free"
  /\ holdersLock' = p /\ pc' = [pc EXCEPT ![p] = to]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, ended, slotlog, bus,
                 child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

HoldLock(p) == HoldersLock(p, "hold", "holding")

\* jgauge/slot.py `mine = holders.hold(`
Hold(p) ==
  /\ InSlots
  /\ pc[p] = "holding" /\ holdersLock = p
  /\ holders' = holders \cup {p} /\ ended' = ended \ {p}
  /\ holdersLock' = "free" /\ pc' = [pc EXCEPT ![p] = "wait"]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, slotlog, bus, child, reused,
                 waitId, wsnap, hsnap, missed, lostEnd>>

\* The command ends on its own, or the short lane's stop ends it (`_stop`), whether or not the
\* `jgauge test-slot` that started it still lives.
ChildEnds(p) ==
  /\ InSlots
  /\ child[p] = "alive" /\ child' = [child EXCEPT ![p] = "dead"]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock,
                 slotlog, pc, bus, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* Another process takes the pid of a holder's dead command, where PidReuse allows it.
Reuse(p) ==
  /\ InSlots
  /\ PidReuse /\ child[p] = "dead" /\ p \in holders \ ended /\ p \notin reused
  /\ reused' = reused \cup {p}
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock,
                 slotlog, pc, bus, child, waitId, wsnap, hsnap, missed, lostEnd>>

\* jgauge/slot.py `code = child.wait(timeout=lane.limit)` returns.
Ran(p) ==
  /\ InSlots
  /\ pc[p] = "wait" /\ child[p] = "dead"
  /\ pc' = [pc EXCEPT ![p] = IF p \in OnFile THEN "end" ELSE "logrelease"]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock,
                 slotlog, bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

EndLock(p) == HoldersLock(p, "end", "ending")

\* jgauge/slot.py `holders.end(lock.parent, mine.id, 1 if code is None else code,
\* datetime.now(UTC))`,
\* which marks only an entry still on file: jgauge/holders.py `if one.id == run and not one.ended`.
\* An entry jbus forgot first leaves the end with no one to tell.
End(p) ==
  /\ InSlots
  /\ pc[p] = "ending" /\ holdersLock = p
  /\ ended' = IF p \in holders THEN ended \cup {p} ELSE ended
  /\ lostEnd' = IF p \in holders THEN lostEnd ELSE lostEnd \cup {p}
  /\ holdersLock' = "free" /\ pc' = [pc EXCEPT ![p] = "logrelease"]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, slotlog, bus, child,
                 reused, waitId, wsnap, hsnap, missed>>

\* jgauge/slot.py `slotlog.release(logged, 1 if code is None else code)`, before the lock goes.
LogRelease(p) ==
  /\ InSlots
  /\ pc[p] = "logrelease"
  /\ slotlog' = [slotlog EXCEPT ![p] = IF slotlog[p] = "take" THEN "release" ELSE slotlog[p]]
  /\ pc' = [pc EXCEPT ![p] = "close"]
  /\ UNCHANGED <<full, short, line, waiters, woken, waitersLock, holders, ended, holdersLock,
                 bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* jgauge/slot.py `os.close(held) _sweep()` lets the slot go.
Close(p) ==
  /\ InSlots
  /\ pc[p] = "close"
  /\ full' = [n \in FullSlots |-> IF full[n] = p THEN "free" ELSE full[n]]
  /\ short' = [n \in ShortSlots |-> IF short[n] = p THEN "free" ELSE short[n]]
  /\ pc' = [pc EXCEPT ![p] = "off"]
  /\ UNCHANGED <<line, waiters, woken, waitersLock, holders, ended, holdersLock, slotlog, bus,
                 child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* `jgauge test-slot` dies between two steps: the kernel lets its flocks go (its slot, its
\* ticket's lock, a lock of the waiters or holders file). Its command ends with it: the flock is
\* the holder's and not the command's, and a watchdog whose pipe ends with the holder kills the
\* command and what it started (jgauge/children.py `end(int(said.split()[0]), sys.argv[1] ==
\* "1")`). The canary "orphan-command" lets the command live on.
Die(p) ==
  /\ InSlots
  /\ p \in Mortal /\ pc[p] /= "off"
  /\ full' = [n \in FullSlots |-> IF full[n] = p THEN "free" ELSE full[n]]
  /\ short' = [n \in ShortSlots |-> IF short[n] = p THEN "free" ELSE short[n]]
  /\ line' = IF p = "short" /\ "live" \in line THEN (line \ {"live"}) \cup {"dead"} ELSE line
  /\ waitersLock' = IF waitersLock = p THEN "free" ELSE waitersLock
  /\ holdersLock' = IF holdersLock = p THEN "free" ELSE holdersLock
  /\ child' = IF Has("orphan-command") THEN child ELSE [child EXCEPT ![p] = "dead"]
  /\ pc' = [pc EXCEPT ![p] = "off"]
  /\ UNCHANGED <<waiters, woken, holders, ended, slotlog, bus, reused, waitId, wsnap, hsnap,
                 missed, lostEnd>>

\* A wake's claim ages: HOLDS, then FORGOTTEN, pass.
\* jgauge/waiters.py `HOLDS = timedelta(minutes=10)`
\* and jgauge/waiters.py `FORGOTTEN = timedelta(hours=1)`
Tick ==
  /\ InSlots
  /\ woken \in {"holds", "past"}
  /\ woken' = IF woken = "holds" THEN "past" ELSE "lapsed"
  /\ UNCHANGED <<full, short, line, waiters, waitersLock, holders, ended, holdersLock, slotlog,
                 pc, bus, child, reused, waitId, wsnap, hsnap, missed, lostEnd>>

\* ---- jbus's pass: slotwait.wake, then slotwait.wake_ended ----

BusFrame == <<full, short, line, holders, ended, slotlog, pc, child, reused, missed, lostEnd>>

\* A pass starts with slotwait.wake in the full room; the short lane has no waiters.
BusStart ==
  /\ InSlots
  /\ bus = "idle" /\ bus' = IF room = "full" THEN "read" ELSE "hread"
  /\ UNCHANGED <<BusFrame, waiters, woken, waitersLock, holdersLock, waitId, wsnap, hsnap>>

\* jbus/slotwait.py `held = waiters.read(locks)`, under the lock and let go at once.
WakeRead ==
  /\ InSlots
  /\ bus = "read" /\ waitersLock = "free"
  /\ wsnap' = [in |-> "crew" \in waiters, woken |-> woken, id |-> waitId]
  /\ bus' = IF "crew" \in waiters /\ woken = "lapsed" THEN "forget" ELSE "spare"
  /\ UNCHANGED <<BusFrame, waiters, woken, waitersLock, holdersLock, waitId, hsnap>>

\* jbus/slotwait.py `gone = {one.id for one in held if waiters.lapsed(one, run.now)}`, then
\* jbus/slotwait.py `waiters.forget(locks, gone)`, which takes out that id alone.
ForgetLock ==
  /\ InSlots
  /\ bus = "forget" /\ waitersLock = "free"
  /\ waitersLock' = "bus" /\ bus' = "forgetting"
  /\ UNCHANGED <<BusFrame, waiters, woken, holdersLock, waitId, wsnap, hsnap>>

Forget ==
  /\ InSlots
  /\ bus = "forgetting" /\ waitersLock = "bus"
  /\ IF "crew" \in waiters /\ waitId = wsnap.id
       THEN waiters' = waiters \ {"crew"} /\ woken' = "none"
       ELSE UNCHANGED <<waiters, woken>>
  /\ waitersLock' = "free" /\ bus' = AfterWake
  /\ UNCHANGED <<BusFrame, holdersLock, waitId, wsnap, hsnap>>

\* Today: jbus/slotwait.py `room = slot.spare(lane, queue, run.now)` counts the free slots now
\* and the claims of the waiters it read, outside the waiters lock, and wakes the oldest
\* waiters that are not woken: jbus/slotwait.py `for one in waiting[: max(room, 0)]:`. The mode
\* that passes takes the waiters lock first, so the count and the wake's record are one hold of
\* it.
Spare ==
  /\ InSlots
  /\ bus = "spare" /\ Has("spare-outside-lock")
  /\ LET spare == Cardinality(FreeFull) - (IF wsnap.in /\ wsnap.woken = "holds" THEN 1 ELSE 0) IN
       bus' = IF spare > 0 /\ wsnap.in /\ wsnap.woken = "none" THEN "tell" ELSE AfterWake
  /\ UNCHANGED <<BusFrame, waiters, woken, waitersLock, holdersLock, waitId, wsnap, hsnap>>

SpareLock ==
  /\ InSlots
  /\ bus = "spare" /\ ~Has("spare-outside-lock") /\ waitersLock = "free"
  /\ waitersLock' = "bus" /\ bus' = "sparing"
  /\ UNCHANGED <<BusFrame, waiters, woken, holdersLock, waitId, wsnap, hsnap>>

\* The mode that passes: count and record the wake under the lock, as `_claim` counts and takes.
SpareHeld ==
  /\ InSlots
  /\ bus = "sparing" /\ waitersLock = "bus"
  /\ LET spare == Cardinality(FreeFull) - Claims("bus")
         wake == spare > 0 /\ "crew" \in waiters /\ woken = "none" IN
       /\ woken' = IF wake THEN "holds" ELSE woken
       /\ bus' = IF wake THEN "tell" ELSE AfterWake
  /\ waitersLock' = "free"
  /\ UNCHANGED <<BusFrame, waiters, holdersLock, waitId, wsnap, hsnap>>

\* jbus/slotwait.py `key=f"slot-wake|{one.thread}|{one.id}",`: T3 Code takes the message, or
\* does not. Today the
\* wake is recorded after it: jbus/slotwait.py `waiters.woken(slot.locks_dir(), one.id, run.now)`
Tell ==
  /\ InSlots
  /\ bus = "tell"
  /\ \/ bus' = IF Has("spare-outside-lock") THEN "wake" ELSE AfterWake
     \/ bus' = AfterWake
  /\ UNCHANGED <<BusFrame, waiters, woken, waitersLock, holdersLock, waitId, wsnap, hsnap>>

WakeLock ==
  /\ InSlots
  /\ bus = "wake" /\ waitersLock = "free"
  /\ waitersLock' = "bus" /\ bus' = "waking"
  /\ UNCHANGED <<BusFrame, waiters, woken, holdersLock, waitId, wsnap, hsnap>>

\* jgauge/waiters.py `replace(one, woken=stamp(now)) if one.id == wait and not one.woken else one`
Wake ==
  /\ InSlots
  /\ bus = "waking" /\ waitersLock = "bus"
  /\ woken' = IF "crew" \in waiters /\ waitId = wsnap.id /\ woken = "none" THEN "holds" ELSE woken
  /\ waitersLock' = "free" /\ bus' = AfterWake
  /\ UNCHANGED <<BusFrame, waiters, holdersLock, waitId, wsnap, hsnap>>

\* jbus/slotwait.py `for one in holders.read(locks):`, under the lock and let go at once.
EndedRead ==
  /\ InSlots
  /\ bus = "hread" /\ holdersLock = "free"
  /\ hsnap' = [in |-> holders, ended |-> ended]
  /\ bus' = "judge"
  /\ UNCHANGED <<BusFrame, waiters, woken, waitersLock, holdersLock, waitId, wsnap>>

\* jbus/slotwait.py `if told or (not one.ended and not holders.running(one)):` with `one` as
\* read: an ended run is told (or owed nothing) and goes, and a run with no end on record goes
\* once its command's pid and its `jgauge test-slot`'s, `one.keeper`, are both gone.
\* The canary "forget-unended" lets it go while its `jgauge test-slot` still lives to write the end.
Over == {p \in hsnap.in :
           \/ p \in hsnap.ended
           \/ /\ p \notin hsnap.ended /\ ~PidRuns(p)
              /\ (Has("forget-unended") \/ pc[p] = "off")}

Judge ==
  /\ InSlots
  /\ bus = "judge"
  /\ bus' = IF Over = {} THEN "idle" ELSE "hforget"
  /\ hsnap' = [in |-> Over, ended |-> hsnap.ended]
  /\ UNCHANGED <<BusFrame, waiters, woken, waitersLock, holdersLock, waitId, wsnap>>

HForgetLock ==
  /\ InSlots
  /\ bus = "hforget" /\ holdersLock = "free"
  /\ holdersLock' = "bus" /\ bus' = "hforgetting"
  /\ UNCHANGED <<BusFrame, waiters, woken, waitersLock, waitId, wsnap, hsnap>>

\* jbus/slotwait.py `holders.forget(locks, over)`
HForget ==
  /\ InSlots
  /\ bus = "hforgetting" /\ holdersLock = "bus"
  /\ holders' = holders \ hsnap.in /\ ended' = ended \ hsnap.in /\ reused' = reused \ hsnap.in
  /\ holdersLock' = "free" /\ bus' = "idle"
  /\ UNCHANGED <<full, short, line, slotlog, pc, child, missed, lostEnd, waiters, woken,
                 waitersLock, waitId, wsnap, hsnap>>

\* jbus's pass dies: the kernel lets its locks go.
BusDies ==
  /\ InSlots
  /\ "bus" \in Mortal
  /\ bus /= "idle" /\ bus' = "idle"
  /\ waitersLock' = IF waitersLock = "bus" THEN "free" ELSE waitersLock
  /\ holdersLock' = IF holdersLock = "bus" THEN "free" ELSE holdersLock
  /\ UNCHANGED <<BusFrame, waiters, woken, waitId, wsnap, hsnap>>

Run(p) ==
  \/ Start(p) \/ LogTake(p) \/ Spawn(p) \/ HoldLock(p) \/ Hold(p) \/ ChildEnds(p) \/ Reuse(p)
  \/ Ran(p) \/ EndLock(p) \/ End(p) \/ LogRelease(p) \/ Close(p) \/ Die(p)

Bus ==
  \/ BusStart \/ EndedRead \/ Judge \/ HForgetLock \/ HForget \/ BusDies

FullRoom ==
  \/ \E p \in FullProcs : Run(p) \/ ClaimLock(p) \/ ClaimCount(p)
  \/ RegisterLock \/ Register \/ DropLock \/ Drop \/ Tick
  \/ Bus \/ WakeRead \/ ForgetLock \/ Forget \/ Spare \/ SpareLock \/ SpareHeld \/ Tell
  \/ WakeLock \/ Wake

ShortRoom ==
  \/ \E p \in ShortProcs : Run(p)
  \/ Enter \/ First \/ GiveUp \/ Poll \/ Bus

\* ---- The ledger: jgauge limits, hooks/limits.sh and jbus each read, merge and replace it ----

\* jgauge/limits.py `refused = Refused(now + _waits(error))` and jgauge/limits.py
\* `_keep_retry(home.instance, refused.until)`: a 429, or no source that answers, keeps a retry
\* time and writes no line. Or the endpoint answers, and the run goes on to write.
Fetch ==
  /\ InLedger
  /\ lpc["limits"] = "idle"
  /\ \/ /\ ~retry /\ retry' = TRUE /\ UNCHANGED lpc
     \/ /\ lpc' = [lpc EXCEPT !["limits"] = "fetched"] /\ UNCHANGED retry
  /\ UNCHANGED <<spells, ledger, local, wrote, ledgerLock>>

\* jroles/ledger.py `before = _text(file)`, and
\* jgauge/hooks/limits.sh `kept=$(cat "$LIMITS" 2>/dev/null)`:
\* each writer reads the whole file under <ledger>.lock, which it holds to its rename:
\* jroles/ledger.py `fcntl.flock(held, fcntl.LOCK_EX)` and
\* jgauge/hooks/limits.sh `perl -MFcntl=:flock -e 'open(my $l, ">&=9") or exit 1; flock($l,
\* LOCK_EX) or exit 1'`.
Read(w) ==
  /\ InLedger
  /\ lpc[w] = IF w = "limits" THEN "fetched" ELSE "idle"
  /\ IF Has("no-ledger-lock") THEN UNCHANGED ledgerLock
                               ELSE ledgerLock = "free" /\ ledgerLock' = w
  /\ local' = [local EXCEPT ![w] = ledger] /\ lpc' = [lpc EXCEPT ![w] = "read"]
  /\ UNCHANGED <<retry, spells, ledger, wrote>>

\* jroles/ledger.py `merged = merge(parse(record.instance, before), [record])`, then the rename:
\* the file is what this writer read, with its own record merged in. The hook and jbus write
\* once each, which is all a lost update needs; `jgauge limits` runs again on its timer.
Write(w) ==
  /\ InLedger
  /\ lpc[w] = "read"
  /\ ledger' = local[w] \cup {w} /\ wrote' = wrote \cup {w}
  /\ ledgerLock' = IF ledgerLock = w THEN "free" ELSE ledgerLock
  /\ lpc' = [lpc EXCEPT ![w] = IF w = "limits" THEN "unlink" ELSE "done"]
  /\ UNCHANGED <<retry, spells, local>>

\* jgauge/limits.py `if source == "endpoint":`, then the retry file goes.
Unlink ==
  /\ InLedger
  /\ lpc["limits"] = "unlink" /\ retry' = FALSE /\ lpc' = [lpc EXCEPT !["limits"] = "idle"]
  /\ UNCHANGED <<spells, ledger, local, wrote, ledgerLock>>

\* jgauge/limits.py `kept = ledger.read(names)`, then one line appended to capped.jsonl.
Note ==
  /\ InLedger
  /\ spells /= ledger /\ spells' = ledger
  /\ UNCHANGED <<retry, ledger, lpc, local, wrote, ledgerLock>>

\* A writer dies between its read and its write: it writes nothing, and its lock goes.
WriterDies(w) ==
  /\ InLedger
  /\ "writers" \in Mortal
  /\ lpc[w] \notin {"idle", "done"} /\ lpc' = [lpc EXCEPT ![w] = "idle"]
  /\ ledgerLock' = IF ledgerLock = w THEN "free" ELSE ledgerLock
  /\ UNCHANGED <<retry, spells, ledger, local, wrote>>

LedgerRoom ==
  \/ Fetch \/ Unlink \/ Note \/ \E w \in Writers : Read(w) \/ Write(w) \/ WriterDies(w)

\* ---- The pool: a crew that waits on a capped review pool, and slotwait.wake_capped ----

PoolLock(who, at, to) ==
  /\ InPool
  /\ poolLock = "free" /\ poolLock' = who
  /\ IF who = "crew" THEN ppc = at /\ ppc' = to /\ UNCHANGED jpc
                     ELSE jpc = at /\ jpc' = to /\ UNCHANGED ppc
  /\ UNCHANGED <<pool, psnap, due, used, told, byThread>>

\* jroles/cli.py `wait = waits.register(waits.where(), args.thread, role, min(resets), now)`, or
\* jroles/cli.py `waits.drop(waits.where(), args.thread, role)` where the pool has headroom.
PoolCall ==
  /\ InPool
  /\ ppc = "off"
  /\ \/ ppc' = "register"
     \/ ppc' = "drop"
  /\ UNCHANGED <<pool, poolLock, jpc, psnap, due, used, told, byThread>>

\* jroles/waits.py `if mine and not mine.due(now):` keeps the wait and its id, with the newer
\* `until`; a wait that is due, or none, gets a new wait with an id of its own.
PoolRegister ==
  /\ InPool
  /\ ppc = "registering" /\ poolLock = "crew"
  /\ IF pool /= {} /\ pool \cap due = {}
       THEN UNCHANGED <<pool, used, byThread>>
       ELSE IF WaitIds \ used = {}
         THEN UNCHANGED <<pool, used, byThread>>  \* the model's bound: no third wait is made
         ELSE /\ \E i \in WaitIds \ used : pool' = {i} /\ used' = used \cup {i}
              /\ byThread' = byThread \cup pool
  /\ poolLock' = "free" /\ ppc' = "off"
  /\ UNCHANGED <<jpc, psnap, due, told>>

PoolDrop ==
  /\ InPool
  /\ ppc = "dropping" /\ poolLock = "crew"
  /\ pool' = {} /\ byThread' = byThread \cup pool
  /\ poolLock' = "free" /\ ppc' = "off"
  /\ UNCHANGED <<jpc, psnap, due, used, told>>

\* The cap's end passes: jroles/waits.py `return now >= datetime.fromisoformat(self.until)`
PoolDue ==
  /\ InPool
  /\ \E i \in pool \ due : due' = due \cup {i}
  /\ UNCHANGED <<pool, poolLock, ppc, jpc, psnap, used, told, byThread>>

\* jbus/slotwait.py `held = waits.read(at)`, under the lock and let go at once, and
\* jbus/slotwait.py `if one.id not in gone and one.due(run.now) and tell_capped(run, client, one):`
PoolRead ==
  /\ InPool
  /\ jpc = "off" /\ poolLock = "free" /\ pool \cap due /= {}
  /\ \E i \in pool \cap due : psnap' = i
  /\ jpc' = "tell"
  /\ UNCHANGED <<pool, poolLock, ppc, due, used, told, byThread>>

\* jbus/slotwait.py `key=f"pool-wake|{one.thread}|{one.id}",`: T3 Code takes the message, or
\* not, and the wait stays.
PoolTell ==
  /\ InPool
  /\ jpc = "tell"
  /\ \/ told' = told \cup {psnap} /\ jpc' = "forget"
     \/ jpc' = "off" /\ UNCHANGED told
  /\ UNCHANGED <<pool, poolLock, ppc, psnap, due, used, byThread>>

\* jbus/slotwait.py `waits.forget(at, {one.id})`: that id alone.
PoolForget ==
  /\ InPool
  /\ jpc = "forgetting" /\ poolLock = "bus"
  /\ pool' = pool \ {psnap} /\ poolLock' = "free" /\ jpc' = "off"
  /\ UNCHANGED <<ppc, psnap, due, used, told, byThread>>

PoolDies ==
  /\ InPool
  /\ "pool" \in Mortal
  /\ \/ ppc \in {"register", "registering", "drop", "dropping"} /\ ppc' = "off" /\ UNCHANGED jpc
     \/ jpc /= "off" /\ jpc' = "off" /\ UNCHANGED ppc
  /\ poolLock' = IF (poolLock = "crew" /\ ppc' /= ppc) \/ (poolLock = "bus" /\ jpc' /= jpc)
                   THEN "free" ELSE poolLock
  /\ UNCHANGED <<pool, psnap, due, used, told, byThread>>

PoolRoom ==
  \/ PoolCall \/ PoolLock("crew", "register", "registering") \/ PoolRegister
  \/ PoolLock("crew", "drop", "dropping") \/ PoolDrop \/ PoolDue \/ PoolRead \/ PoolTell
  \/ PoolLock("bus", "forget", "forgetting") \/ PoolForget \/ PoolDies

Next == FullRoom \/ ShortRoom \/ LedgerRoom \/ PoolRoom
Spec == Init /\ [][Next]_vars

\* ---- The rules ----

\* WokenGetsSlot: a woken waiter gets the slot or its claim lapses at HOLDS. A crew jbus woke,
\* that runs its command again while the wake's claim holds, finds its slot free.
WokenGetsSlot == missed = {}

\* NoLostHolder: every holder ends or its pid is dead and a reader treats it so. A run on file
\* with no end, whose command is gone, is not running to a reader (`holders.running`), so jbus
\* counts its thread at work no longer and lets the entry go.
NoLostHolder == \A p \in holders : p \in ended \/ child[p] = "alive" \/ ~Running(p)

\* EndNotLost: a run whose `jgauge test-slot` lives to its end has that end on file for jbus to
\* tell its thread, so a thread that ended its turn on "my run holds a slot" is woken.
EndNotLost == lostEnd = {}

\* LedgerNoLostUpdate: no ledger write drops another's. Each record a writer merged in is still
\* in the ledger, so a cap one writer recorded is never undone by another's older copy.
LedgerNoLostUpdate == \A w \in wrote : w \in ledger

\* LogMatchesFlock: while `jgauge test-slot` holds a slot past its take row, the slot log has
\* that take with no release (the release row is written before the lock goes).
LogMatchesFlock ==
  \A p \in Procs : pc[p] \in {"spawn", "hold", "holding", "wait", "end", "ending"} =>
                     slotlog[p] = "take" /\ HoldsSlot(p)

\* OneCommandPerSlot: a slot runs one command at a time. A command whose `jgauge test-slot` died
\* runs on with its slot free, and the next take starts a second command beside it.
OneCommandPerSlot ==
  /\ Cardinality({p \in FullProcs : child[p] = "alive"}) <= Cardinality(FullSlots)
  /\ Cardinality({p \in ShortProcs : child[p] = "alive"}) <= Cardinality(ShortSlots)

\* PoolNoLostWait: a pool wait leaves the file only once jbus told its thread, or by its own
\* thread's call.
PoolNoLostWait == \A i \in used \ pool : i \in told \/ i \in byThread
====
