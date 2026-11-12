---
name: verify-gh-budget
description: Check GhBudget.tla, the gh API budget every jstack process shares and the call log that records it; use when changing jsettings.budget's reading, its lock or kept answer, proc's slots or call log, or jbus.watch.look's budget gate.
paths: "features/jsettings/spec/GhBudget.tla, features/jsettings/src/jsettings/budget.py, features/jsettings/src/jsettings/proc.py, features/jbus/src/jbus/watch.py"
---

# verify-gh-budget

`features/jsettings/spec/GhBudget.tla` follows the budget of `gh` calls that every process of jstack shares: a pass reading what is left (`budget.logged`), with no lock first and then under the lock of `gh-rate-limit.json`, where it asks `gh api rate_limit` and keeps the answer; the gate that reading gives (`budget.held`, read once by `watch.look`); each `gh` taking one of `GH_CAP` slots (`proc._slot`); and `proc._log` renaming a call log past `KEPT` under its lock, then appending the call's line.
Each of the ledger rows D-081 to D-086 is one VARIABLE whose comment quotes its writer.
`Fault` picks today's code (`locked-rotate`) or the canary, the rotation before its lock (`unlocked-rotate`).

The rules, each with its harm, and today's verdict:

- **`NoLostGeneration`** (holds): a rotation never drops lines another rotation kept.
  Broken, a whole call log is in no file.
- **`HeldWhenLow`** (breaks): no call starts while the kept budget is at or under the floor.
  Broken, a pass keeps calling on a reading it took as it started, while its own calls and another pass's take the budget to the floor kept for merges.
- **`CappedRuns`** (holds): each running `gh` holds a slot of its own.

## The record

Model: `features/jsettings/spec/GhBudget.tla`
Sync: `2fb4e2587489ad3fbebf71561ac648801edb710f`
Covers:
- `features/jsettings/src/jsettings/budget.py`: `logged`, `_logged`, `_locked`, `_keep`, `_lowest`, `read`, `held`, `FLOOR`, `WITHIN`, `WINDOWS`, `KEPT`
- `features/jsettings/src/jsettings/proc.py`: `run`, `_slot`, `_log`, `GH_CAP`, `CALLS`, `KEPT`, `SLOTS`
- `features/jbus/src/jbus/watch.py`: `look`

At the sync commit, main's tip when this branch took main in, the model was read against these.
`logged` returns `_logged`'s reading where it has one, and only then takes `_locked`, reads again, asks with `read` and keeps a non-None answer with `_keep` (`Look`, `TakeKeepLock`, `Relook`).
`_keep` writes a temp file and then one `os.replace`, so a reader never sees half of it.
`held` holds on no answer and on `low.remaining - calls > FLOOR` failing, which is `Gate`.
`watch.look` reads `allowance.logged` and `budget.held` once per pass, and nothing in `run` reads the gate again before a call (`Call`, `HeldWhenLow`'s trace).
`run` holds `_slot` over `_run` only and calls `_log` after the slot goes (`Run`, then `LockRotate`).
`_slot` takes the first slot whose non-blocking flock succeeds and waits while all are held.
`_log` takes the flock of `.gh-calls.jsonl.lock`, checks `st_size > KEPT`, renames under `contextlib.suppress(OSError)`, lets the lock go, and then appends one line (`LockRotate`, `Check`, `Rotate`, `Append`).
No covered file changed between the model's commit (c6e2f3011, #1712) and the sync, and `features/jsettings/tests/test_gh_budget_spec.py` passed there (5 passed).
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new reader of the budget that gates calls, a new writer of `gh-calls.jsonl`, `gh-calls.old.jsonl`, `gh-rate-limit.json` or `gh-slots/`, or a cfg or the spec.
The test also fails when a quote of the spec no longer stands once in its file: move the quote with the code, then rerun.

## Run it

```sh
uv run pytest features/jsettings/tests/test_gh_budget_spec.py -q
```

It checks each quote and each ledger carrier, and runs TLC on today's code, on the rotation alone and on the canary, in under ten seconds; it skips where no Java runs TLC.
The bare TLC command and the findings are in `features/jsettings/spec/GhBudget.md`, "Check the rules" and "The findings"; run TLC in a copy of the folder, since it writes `states/` where it runs.

- **Bounds:** `Procs = {"a", "b"}`, `Cap = 1`, `Kept = 1` (a log renamed past one line), `Floor = 1`, `Start = 4`; `GhBudget.cfg` has 225,479 distinct states with `NoLostGeneration` alone, and stops at `HeldWhenLow` in 18 states.
- **The faults:** `locked-rotate` is today's code; `unlocked-rotate` is the canary that breaks `NoLostGeneration` in 26 states.
- **Assumptions:** one window stands for `core` and `graphql`; a window never resets; time is one `Tick`; `gh api rate_limit` takes no slot and logs no line; a process that dies lets its flocks go; the rest is in the README's "What the model leaves out".

## A real bug or a modeling error

Each step of a trace quotes the code that takes it.
Open each quote at its file and check the order of reads, locks and writes still is the step's; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the passes' story (read, call, log, rename), and leave the rule as it is.

## Change the model when the code changes on purpose

- A fix that gates each call, or reorders the lock, the check and the rename: change the step, rerun the cfg and the canary, and move the README's findings and the cfg's comment with what TLC prints.
- A new carrier of the ledger's GhBudget rows: give it a variable whose comment quotes its writer.

## Drift at the sync commit

- `_logged` returns no reading when `gh-rate-limit.json` is missing, unreadable, or has a window whose reset has passed, even where the log has lines of the last `WITHIN` seconds; the model's `Logged` reads the log's fresh lines with no kept answer at all.
  So in the model a pass can read the budget off the log alone, which the code never does: it asks under the lock instead.
- `_locked` runs the block with no lock where the lock file cannot be opened; the model always takes `keepLock`.
- The README says the model is "at main aa5469d97", but the model's commit c6e2f3011 is the one that put `_log`'s rename under its lock, which the model's `locked-rotate` is.
