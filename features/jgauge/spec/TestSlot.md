# The test slots, as a TLA+ spec

`TestSlot.tla` models one machine's test slots and every record around them, with every writer and a crash between any two steps of each:

- the full lane's flocks `test-slot.<n>.lock` and the short lane's `test-slot-short.<n>.lock` (`jgauge/slot.py`);
- the short lane's line of tickets `test-slot-short.line/` (`_line`, `_ahead`);
- the waiters of a full slot `test-slot-waiters.json`, with the claim a wake gives (`woken`, `HOLDS`, `FORGOTTEN`), and its lock (`jgauge/waiters.py`, written by `jgauge test-slot` and by jbus's `slotwait.wake`);
- the holders of a run `test-slot-holders.json`, with `ended`, and its lock (`jgauge/holders.py`, forgotten by jbus's `slotwait.wake_ended`);
- the slot log `slots.jsonl` (`jgauge/slotlog.py`);
- the limits ledger, its `.retry` file and `capped.jsonl` (`jroles/ledger.py`, `jgauge/limits.py`, `hooks/limits.sh`, and jbus's failover);
- the pool waits `pool-waiters.json` and their lock (`jroles/waits.py`, jbus's `slotwait.wake_capped`).

Each carrier is one VARIABLE, named by its row of the st-state-ledger ledger (D-048 to D-074).
Its comment quotes the code that writes it.
Each step quotes the code it stands for, by file and code, with no line number.
`features/jgauge/tests/test_test_slot_spec.py` finds each quote once in its file, and checks that each carrier row is a VARIABLE with a cite.
It also runs TLC on the config and on each canary.

The machine has four rooms that share no variable: the full lane, the short lane, the ledger and the pool.
Init picks the room, and TLC checks the sum of their states, not their product.
The holders file and the slot log are written by both lanes.
Each process writes only its own entry, under the file's lock, and jbus forgets by id, so each lane's room checks its own entries.

## The modes

`Fault` says which code TLC checks:

- `"today"`: the code as it is, with one fault (`TestSlot.cfg`).
- `"none"`: the mode that passes, where each fault is closed.
- `"spare-outside-lock"`: a canary, today's fault put back into the mode that passes.
- `"forget-unended"`, `"orphan-command"`, `"pid-alone"`, `"no-ledger-lock"`: canaries, each one that puts back a fault the code has closed.

| Fault | Today | The mode that passes | Rule it breaks |
|---|---|---|---|
| `spare-outside-lock` | `slotwait.wake` reads the waiters, counts `spare` with no lock, sends the wake, and only then records `woken` | count and record the wake under one hold of the waiters lock, before the send, as `_claim` counts and takes | `WokenGetsSlot` |
| `forget-unended` | closed: a holder records `keeper`, the pid of its `jgauge test-slot`, and `holders.running` counts a run with no `ended` as running while its command or its `jgauge test-slot` lives, so `wake_ended` keeps it until the end is written | forget such a run only once its `jgauge test-slot` is gone too | `EndNotLost` |
| `orphan-command` | closed: a killed `jgauge test-slot` takes its command with it, since a watchdog, `jgauge.children`, kills the command and what it started once the holder's pipe ends | the command ends with its holder | `OneCommandPerSlot` |
| `pid-alone` | closed: `holders.running` counts a run as running only while its pid has the start time the run recorded, from `/proc/<pid>/stat`, or from `ps` where there is no /proc, as on macOS | a pid another process took reads as gone | `NoLostHolder` |
| `no-ledger-lock` | closed: each writer holds `<ledger>.lock`, an flock beside the file, from its read to its rename (`ledger.write`, and a perl `flock` of fd 9 in `hooks/limits.sh`, since macOS has no `flock` command) | read, merge and write under one lock | `LedgerNoLostUpdate` |

`PidReuse` lets another process take a dead command's pid.
`TestSlot.cfg` sets it `TRUE`: `holders.running` checks the pid's start time, so `NoLostHolder` holds, and the canary `pid-alone` breaks it.
`Mortal` names the processes that can be killed, and `TestSlot.cfg` has every one.
`Chart` is for the chart's config alone (below).

## The rules

- `WokenGetsSlot`: a woken waiter gets the slot, or its claim lapses at `HOLDS`.
  A crew that jbus woke, and that runs its command again while the claim holds, finds its slot free.
- `NoLostHolder`: every holder ends, or its pid is dead and a reader treats it so.
  A run on file with no end, whose command is gone, is not running to `holders.running`.
- `EndNotLost`: a run whose `jgauge test-slot` lives to its end has that end on file for jbus to tell its thread.
- `OneCommandPerSlot`: a slot runs one command at a time.
- `LedgerNoLostUpdate`: no ledger write drops another's.
- `LogMatchesFlock`: while a run holds its slot past its take row, the slot log has that take and no release.
- `PoolNoLostWait`: a pool wait leaves the file only once jbus told its thread, or by its own thread's call.

## Check the rules

```sh
cd features/jgauge/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config TestSlot.cfg TestSlot.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.

### The finding: today's code misses a woken crew's slot

TLC's verdict on `TestSlot.cfg` is `Invariant WokenGetsSlot is violated`, after 18,126 distinct states on one worker.
It is the shortest trace of today's one fault, and the `.cfg` keeps it:

1. The full slot is free.
2. `Start` to `ClaimCount`: a desk's `make check` takes the slot, and the crew finds it taken.
3. `Die`: the desk's run is killed, and the slot is free again.
4. `Start` to `Register`: the desk starts again, and the crew registers as a waiter, ends its turn, and starts again.
5. `BusStart`, `WakeRead`: jbus's pass reads the waiters, the crew among them.
6. `ClaimLock`, `Spare`, `ClaimCount`: jbus counts the slot spare outside the waiters lock, and the desk takes it through `_claim`, which sees no claim yet.
7. `Tell`, `WakeLock`, `Wake`: jbus sends the wake, and only then records `woken`.
8. `ClaimLock`, `ClaimCount`: the woken crew runs again with its claim holding, finds no slot, and registers again.

The four faults the code has closed break their rules in the canaries.
`test_test_slot_spec.py` runs each canary and asserts the rule it breaks:

- `spare-outside-lock`, `WokenGetsSlot`: the finding above, in the mode that passes.
- `forget-unended`, `EndNotLost`: a run's command ends.
  jbus reads the holders, finds no end and no pid, and forgets the run.
  `jgauge test-slot` then writes the end to an entry that is no longer there, and the thread that ended its turn on "my run holds a slot" is never told the run ended.
  The window is from the reap in `child.wait` to `holders.end`.
  jbus's loop makes T3 Code calls for the other holders between its read and its `running` check, which widens it.
- `orphan-command`, `OneCommandPerSlot`: `jgauge test-slot` is killed with SIGKILL, and its command runs on with the slot free.
  The next call starts a second command in the same slot, and its `_temporary` empties the directory the first command still uses.
  Today's code holds `OneCommandPerSlot` over all 927,474 distinct states of its mode, and the test checks it in the short lane's room alone.
- `pid-alone`, `NoLostHolder`: a short call with `--thread` takes its slot, starts its command and records the run in the holders file.
  The command dies, and another process takes its pid before the end is on record.
  A reader that asks only whether some process has the pid counts the run as running, so jbus never forgets it and never tells its thread the run ended.
  Today's `holders.running` also asks that the pid have the start time the run recorded, so the reused pid reads as gone, and asks the same of its `jgauge test-slot`'s pid, `keeper`.
- `no-ledger-lock`, `LedgerNoLostUpdate`: two writers read the ledger with no lock, say the status-line hook (`kept=$(cat "$LIMITS" 2>/dev/null)`) and jbus on a turn that ended on a cap (`before = _text(file)`).
  Each renames into place its own record merged into what it read, and the second one's older copy drops the first one's record.
  A cap the hook or jbus wrote read as free until the next reading wrote it again.
  Today's code holds `LedgerNoLostUpdate`, and the test checks it in the ledger's room alone.

`Fault = "none"` holds every rule over 672,971 distinct states: 664,208 in the full lane's room, 6,226 in the short lane's, 1,690 in the ledger's and 847 in the pool's.

The mode that passes has a cost of its own.
A wake recorded before its send claims the slot for `HOLDS` even when the send fails.
`wake` then skips that waiter as woken until `FORGOTTEN` drops it, so the thread waits until it registers again.

## Draw the chart

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
W=$(mktemp -d) && cp features/jgauge/spec/TestSlot.tla features/jgauge/spec/TestSlot.chart.cfg features/jgauge/spec/TestSlot.map.py "$W"
(cd "$W" && UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec TestSlot.tla --config TestSlot.chart.cfg \
    --expect-broken WokenGetsSlot \
    --title "Who holds a test slot, who waits on one, and what the ledger keeps?" \
    --out TestSlot-statechart)
```

Run it from the repo root.
Then copy the files of `$W/TestSlot-statechart` into `TestSlot-statechart/`, all except `tlc/`.
`TestSlot.cfg` has 672,971 states in the mode that passes and 927,474 in today's mode, more than the chart's state graph can hold.
So the chart is drawn from `TestSlot.chart.cfg`: today's code, where only the short lane's crew can be killed, and the full room keeps no holders file (`Chart = TRUE`), which the short room draws.
That is 96,720 model states, and it draws one numbered path for the one bug.
`TestSlot.map.py` labels each state by what the machine's files say, and names each join of values in its header.

## What the model leaves out

- One crew thread waits on the full lane.
  The claim count is per other thread, so a second waiter adds states and no new kind of step.
  The model has one full slot and one short slot.
- A thread's next run starts once its last run's holder entry is gone and its command has ended.
  The file keeps two runs of one thread apart by id, and jbus forgets by id.
- A `free()` probe outside the waiters lock, such as jbus's own `spare` today: it can make `_first_free` inside another caller's `_claim` find a slot locked for an instant.
  In today's code this is one more way for `WokenGetsSlot` to break.
- Two jgauge versions that count a different number of slots.
  The machine's `test-slot.5.lock`, from an older count, is one of these.
- A short call with no thread does not wait in the line.
  It takes a slot freed under the first caller in the line, and the model lets it, with no rule on the order of the short lane.
- A crash between `Popen` and `holders.hold` leaves a command running with no holder entry.
  Its thread's own call returns when `jgauge test-slot` dies, so the model asks for no wake.
- `wake_capped` sends to the waits it read, which jroles may have dropped since: a wake the thread no longer needs, which no rule forbids.
  The model leaves out jbus's `dead` checks.
  `PoolNoLostWait` would count a dead thread's wait as told.
- The ledger: `merge` keeps the larger share of one window, which the model joins into "each merged record stays".
  It leaves out a window that resets, which replaces a line on purpose, and the endpoint's `EARLY` reading.
  Each writer's two windows are one write.
  The hook and jbus each write once, which is all a lost update needs.
- The retry file and `capped.jsonl` have their writes modelled, with no rule of their own.
  The retry file has one writer, `jgauge limits`, run by its timer.
- The slot's temporary directory, the sweep of `/tmp`, and the short lane's stop, which is one way the command ends.
