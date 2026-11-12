---
name: verify-test-slot
description: Check TestSlot.tla, the machine's test slots, their waiters and holders, the slot log, the usage ledger and the pool waits, with a crash between any two writes; use when changing jgauge's slots, waiters, holders or slot log, jbus's slot wakes, or a writer of the limits ledger or the pool waits.
paths: "features/jgauge/spec/TestSlot.tla, features/jgauge/src/jgauge/slot.py, features/jgauge/src/jgauge/waiters.py, features/jgauge/src/jgauge/holders.py, features/jgauge/src/jgauge/slotlog.py, features/jgauge/src/jgauge/children.py, features/jgauge/src/jgauge/limits.py, features/jgauge/hooks/limits.sh, features/jbus/src/jbus/slotwait.py, features/jbus/src/jbus/failover.py, features/jbus/src/jbus/kpis.py, features/jroles/src/jroles/ledger.py, features/jroles/src/jroles/waits.py, features/jroles/src/jroles/cli.py, features/jsettings/src/jsettings/store.py"
---

# verify-test-slot

`features/jgauge/spec/TestSlot.tla` follows one machine's test slots and every record around them: the full and short lanes' flocks, the short lane's line of tickets, `test-slot-waiters.json` with the claim a wake gives, `test-slot-holders.json` with `ended`, the slot log `slots.jsonl`, the limits ledger with its `.retry` file and `capped.jsonl`, and `pool-waiters.json`.
Every writer, jgauge's `test-slot`, jbus's pass, `jgauge limits`, the status-line hook and jroles, can die between two of its writes.
The machine has four rooms that share no variable (full lane, short lane, ledger, pool), and `Init` picks one.
`Fault` says which code TLC checks: `"today"`, `"none"` (the mode that passes), or a canary that puts one fault back.

The rules, each with its harm, and today's verdict:

- **`WokenGetsSlot`** (breaks, `TestSlot.cfg`'s verdict): a woken waiter gets its slot, or its claim lapses at `HOLDS`.
  Broken, a crew jbus woke finds its slot taken and registers again.
- **`LedgerNoLostUpdate`** (holds since #1799, canary `no-ledger-lock`): no ledger write drops another's.
- **`EndNotLost`** (holds since #1794, canary `forget-unended`): a run whose `jgauge test-slot` lives to its end has that end on file for jbus to tell.
- **`OneCommandPerSlot`** (holds since #1719, canary `orphan-command`): a slot runs one command at a time.
- **`NoLostHolder`** (holds with `PidReuse = TRUE`, canary `pid-alone`): every holder ends, or its pid is dead.
  `holders.running` checks that the pid still has the start time its run recorded, so a pid another process took reads as gone.
- **`LogMatchesFlock`** (holds): a run past its take row has that take in the log and no release.
- **`PoolNoLostWait`** (holds): a pool wait leaves the file only once jbus told its thread, or by its own thread's call.

## The record

Model: `features/jgauge/spec/TestSlot.tla`
Sync: `29d4705bd64215ec418c951f96e4a75f23f37e4e`
Covers:
- `features/jgauge/src/jgauge/slot.py`: `run`, `take`, `free`, `spare`, `_claim`, `_first_free`, `_free_for`, `_ahead`, `_line`, `_wait_in_call`, `_sweep`
- `features/jgauge/src/jgauge/waiters.py`: `register`, `drop`, `forget`, `woken`, `holding`, `claims`, `lapsed`, `HOLDS`, `FORGOTTEN`
- `features/jgauge/src/jgauge/holders.py`: `hold`, `end`, `forget`, `running`, `_alive`
- `features/jgauge/src/jgauge/slotlog.py`: `take`, `release`, `_append`
- `features/jgauge/src/jgauge/children.py`: `Watch`, `end`, `main`
- `features/jgauge/src/jgauge/limits.py`: `run`, `from_endpoint`, `keep`, `note`, `_keep_retry`
- `features/jgauge/hooks/limits.sh`: `LIMITS`
- `features/jbus/src/jbus/slotwait.py`: `wake`, `tell`, `wake_ended`, `wake_capped`, `tell_capped`
- `features/jbus/src/jbus/failover.py`: `apply`
- `features/jbus/src/jbus/kpis.py`: `CHORES`
- `features/jroles/src/jroles/ledger.py`: `write`
- `features/jroles/src/jroles/waits.py`: `Wait.due`, `register`, `drop`, `forget`
- `features/jroles/src/jroles/cli.py`: `main`
- `features/jsettings/src/jsettings/store.py`: `locked`, `LockedList.held`

At the sync commit, main's tip when this branch took main in, the model was read against these.
`slot.run` writes `slotlog.take`, starts the command under `children.Watch`, then `holders.hold` with the command's `pid` and its own as `keeper`, waits on `child.wait`, then `holders.end`, `slotlog.release`, closes the slot and calls `_sweep`, the order of `LogTake`, `Spawn`, `Hold`, `Ran`, `End`, `LogRelease` and `Close`.
`slotwait.wake` forgets the lapsed waiters under the lock, then counts `slot.spare` with no lock, and `tell` records `waiters.woken` only after the message went, which is `spare-outside-lock` as today's code.
`slotwait.wake_ended` forgets a run with no `ended` once `holders.running` says it is over, and `holders.running` counts such a run as running while `_alive` finds its command's `pid` or its `keeper`, the pid of its `jgauge test-slot`, so the run stays until that process writes the end, which is why `forget-unended` is a canary of a fault the code has closed; a record with no `keeper` (0, from an older jgauge) goes by its command alone.
`ledger.write` holds an flock of `<file>.lock` from its read with `_text` to its rename with `os.replace`, as `hooks/limits.sh` does with a perl `flock` of fd 9 around `cat` and `mv -f`, which is why `no-ledger-lock` is a canary of a fault the code has closed.
`slot.run` arms `children.Watch` before `Popen`, so a killed `jgauge test-slot` takes its command with it, which is why `orphan-command` is a canary of a fault the code has closed.
Since the last sync (2fb4e2587) three commits changed covered files. #1794 gave `holders.Holder` its `keeper`, which `holders.hold` records, `holders.running` reads through `_alive`, and `slot.run` passes as its own pid; the spec's `Over` and `TodayFaults` moved with it. #1800 has `slot.locks_dir` refuse the machine's own folder while a test runs, and #1725 has `failover._go` write its retry key first, `owed.carrying`; neither alters a step of the model.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new writer or reader of a slot's lock, the waiters or holders file, `slots.jsonl`, the limits ledger, its retry file or `capped.jsonl`, or `pool-waiters.json`, or a cfg or the spec.
The test also fails when a quote of the spec no longer stands once in its file: move the quote with the code, then rerun.

## Run it

```sh
uv run pytest features/jgauge/tests/test_test_slot_spec.py -q
```

It finds each quote of the spec once in its file, checks that each ledger row (D-048 to D-074) is a VARIABLE that cites its writer, and runs TLC on today's mode, the mode that passes and each canary, in under a minute; the TLC tests skip where no Java runs TLC.
The bare TLC command, the table of faults and the trace are in `features/jgauge/spec/TestSlot.md`, "Check the rules"; run TLC in a copy of the folder, since it writes `states/` where it runs.

- **Bounds:** one full slot, one short slot, one crew thread waiting on the full lane; `TestSlot.cfg` (`Fault = "today"`, `PidReuse = TRUE`, every process `Mortal`) stops at `WokenGetsSlot` after 18,126 distinct states on one worker; `Fault = "none"` holds every rule over 672,971 distinct states; today's mode holds `OneCommandPerSlot`, `EndNotLost`, `NoLostHolder` and `LedgerNoLostUpdate` over 927,474.
- **The faults:** `spare-outside-lock`, today's one, breaks `WokenGetsSlot`; `forget-unended`, which breaks `EndNotLost`, `orphan-command`, which breaks `OneCommandPerSlot`, `pid-alone`, which breaks `NoLostHolder`, and `no-ledger-lock`, which breaks `LedgerNoLostUpdate`, are faults the code has closed.
- **Assumptions:** the rest is in the README's "What the model leaves out": no `free()` probe outside the waiters lock but jbus's own, one jgauge slot count, no order of the short lane for a call with no thread, no crash between `Popen` and `holders.hold`, no `dead` checks in jbus, and a ledger merge joined into "each merged record stays".

## A real bug or a modeling error

Each step of a trace quotes the code that takes it, by file and code, with no line number.
Open each quote at its file and check that the write order still is the step's, and that no lock the step leaves out is held there; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the machine's story (who read, who wrote, what was lost), and leave the rule as it is.

## Change the model when the code changes on purpose

- A fix that closes one of today's faults: move its mode's step into today's code, keep the fault as a canary that puts it back, rerun every mode, and move the README's table, the cfg's comment and the test's asserted verdict with what TLC prints.
- A new carrier of the machine's st-state-ledger rows: give it a VARIABLE whose comment names its row and quotes its writer, and add the row to `CARRIERS` in the spec test.
- A new chart: redraw it with the README's "Draw the chart" block from `TestSlot.chart.cfg`.

## Drift at the sync commit

None found in the steps.
