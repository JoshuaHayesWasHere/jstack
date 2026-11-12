---
name: verify-row-life
description: Check RowLife.tla, a queue row's status and go; use when changing work.status, queue.MOVES, queue.derive or the go verbs.
paths: "features/jbus/spec/RowLife.tla, features/jbus/src/jbus/work.py, features/jbus/src/jbus/queue.py, features/jbus/src/jbus/restated.py, features/jbus/src/jbus/dispatch.py, features/jbus/src/jbus/watch.py"
---

# verify-row-life

`features/jbus/spec/RowLife.tla` follows one row of jbus's queue from `jbus queue add` to its end, in two regions at once: the status a pass derives from the facts (`work.status`, written by `queue.derive`), and the go the verbs move (`_grant`, `_hold`, `_lift`, `_void`).

- **The rule, `FinalStays`:** a row that is over stays over; a `done` row may only become `merged`, and a `merged` one stays so.
- **The harm if it breaks:** the queue, `watch.final` and jmerge all read `work.over`, so a row seen over and then not is launched, merged or judged again.
- **The second rule, `MovesKnown`:** each move of the status is one of `queue.MOVES`, so a pass marks `"legal": false` only a fault.

It holds because `queue.derive` keeps the status of a row that is over (`work.kept`), so the check is of the code's derive and not only of the table.

## The record

Model: `features/jbus/spec/RowLife.tla`
Sync: `d3f642c80a2c52ebbf134aa981d95894e892201a`
Covers:
- `features/jbus/src/jbus/work.py`: `status`, `kept`, `over`, `FINAL`, `PATTERNS`, `VALUES`
- `features/jbus/src/jbus/queue.py`: `MOVES`, `derive`, `_grant`, `_hold`, `_lift`, `_void`, `_take_out`, `_launching`
- `features/jbus/src/jbus/asks.py`: `_asks`
- `features/jbus/src/jbus/restated.py`: `restate`
- `features/jbus/src/jbus/dispatch.py`: `Turns.take`
- `features/jbus/src/jbus/watch.py`: `gone`, `unwritten`, `KNOWN`

The first sync, 228c1436c, read the model against each of these, step by step: every pattern of `ValueOf` against `work.PATTERNS` in order, `StatusOf` against `work.status`, `Kept` against `work.kept`, the go verbs, and the launch's `approved` and depends guards in `Turns.take`.
At this sync, main's tip when this branch last took main in, the four covered changes since were read against the model.
#1720 (7e68838af) and #1759 (d3f642c80) changed the model with the code: `Moves` is `queue.MOVES` move for move, `StatusOf` gives a launched row whose thread is none, missing or settled `stale` and an unlaunched one `queued`, as `work.status` and `_THREAD` do, and a launch derives with a `starting` thread, as `watch.gone` leaves it.
#1726 (ee2657c3a) changed only the order a pass launches in (`queue.order`, `Turns.take`'s ranking), which the model does not follow.
#1724 (1bf7b41df) changed `work.PATTERNS` and not the model, which is drift (below).
`features/jbus/tests/test_rowlife_spec.py` passed there (6 passed).
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new writer of a row's status or go, or `docs/jbus/row-moves.md`.
`features/jbus/tests/test_rowlife_spec.py` also fails when `queue.MOVES` and the spec's `Moves` differ, or when `work.VALUES` gains a value the spec neither has nor names as joined.

## Run it

```sh
uv run pytest features/jbus/tests/test_rowlife_spec.py -q
```

It runs TLC in a copy of the spec folder and prints `6 passed` in a few seconds; it skips where no Java runs TLC.
The bare TLC command is in `features/jbus/spec/README.md`, "Check the rule"; run it in a copy of the folder, since TLC writes `states/` where it runs.

- **Bounds:** one row, `Fault = "none"`, 2445 distinct states, `TypeOK`, `FinalStays` and `MovesKnown`.
- **The canaries:** `Fault = "no-latch"` takes `work.kept` out, and `FinalStays` breaks (`test_a_derive_that_writes_over_a_final_status_breaks_the_rule`); `Fault = "settled-queued"` gives a settled thread's row `queued` again, and `MovesKnown` breaks.
- **Assumptions:** a fact's change and the pass that sees it are one step (no restate drift between passes, no one-source pass); the facts are folded (an open pull request's eight steps are `check`, `quiet` is `working`); no clock, so `watch.unwritten`'s stale to left is out; no scout row and no `merge_after`.
  The rest is in the README's "What the model leaves out".

## A real bug or a modeling error

Each step of a trace must be a move the code makes.
Replay it against the record's files: a fact's change is one input `work.status` reads, the pass is `queue.derive`, and a go step is the verb of `queue.py` its name gives.
A step no code makes is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the row's moves in the code's words, and leave the rule as it is.

## Change the model when the code changes on purpose

- A new status or value: add it to `ValueOf` and `StatusOf` in the order of `work.PATTERNS`, then rerun.
- A new move in `queue.MOVES`: the test fails until `Moves` in the spec has it.
- A new writer of the status: model it as a step, or say in the README why it moves nothing.
- Show a changed rule failing on a scratch break before you trust a pass: take the guard out in your own worktree, uncommitted, see the trace, `git restore` the file.

## The last upkeep

None breaks a rule as modeled; `/maintain-formal-verification-skill` fixes them.

- **A thread at work with a leftover:** #1724 made `work.WORKING` take any `written` and gave the `leftover` pattern `apart=(("thread", AT_WORK), ("pull", _set(Pull.NONE)))`, so a row whose thread is at work with no pull request reads `working` whatever its Result says.
  The model's `ValueOf` still gives such a row `leftover` and gives `working` only with `written` none or clean.
  Both values have the status `running`, so the status region and its rules are unchanged; the value is what differs.

- **Remove's guard** followed `Moves`, which names the removals seen and guards none; it now follows `out` in `asks._asks`: no thread at work, no open or merged pull request.
  A `done` row may be removed, so `FinalStays` lets a `done` row leave for good as `removed` (queue.py's doc: "`remove` takes a row out for good"; `rows.remove(row)`), and a removed row stays removed.
  Old: `status \in Final => status' \in Final`; new: `status \in Final => status' \in Final \cup {"removed"}`, and `removed` stays.
  The break: dropping the merged guard lets a merged row be removed, and `FinalStays` fails.
- **An add's new depends:** `Depends` moves an approved row between free and behind with its line unchanged (`restated.restate` keeps an approved facet beside another), and `Pass` writes the line again with no fact changed.

The row was then rebased onto st-model-sync, whose merge of main brought main to `8f4c21b6f`, and the upkeep diffed the covered code again from `228c1436c` to it: #1724 drifted the model: a thread at work with no pull request is now at work whatever its last Result says (`work.py`'s `WORKING`, and the leftover pattern's `apart`), so `ValueOf` reads a leftover of a thread at work with no pull request as `working`, and every rule still holds with each canary breaking its rule. #1726's order (`queue.order`, `Turns.rest`) is not in what this model covers. The sync commit moved there.
