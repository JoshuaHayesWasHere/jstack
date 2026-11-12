---
name: verify-row-life
description: Check RowLife.tla, a queue row's status and go; use when changing work.status, queue.MOVES, queue.derive or the go verbs.
---

# verify-row-life

`features/jbus/spec/RowLife.tla` follows one row of jbus's queue from `jbus queue add` to its end, in two regions at once: the status a pass derives from the facts (`work.status`, written by `queue.derive`), and the go the verbs move (`_grant`, `_hold`, `_lift`, `_void`).

- **The rule, `FinalStays`:** a row that is over stays over; a `done` row may only become `merged`, and a `merged` one stays so.
- **The harm if it breaks:** the queue, `watch.final` and jmerge all read `work.over`, so a row seen over and then not is launched, merged or judged again.

It holds because `queue.derive` keeps the status of a row that is over (`work.kept`), so the check is of the code's derive and not only of the table.

## The record

Model: `features/jbus/spec/RowLife.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/jbus/src/jbus/work.py`: `status`, `kept`, `over`, `FINAL`, `PATTERNS`, `VALUES`
- `features/jbus/src/jbus/queue.py`: `MOVES`, `derive`, `_grant`, `_hold`, `_lift`, `_void`, `_take_out`
- `features/jbus/src/jbus/restated.py`: `restate`
- `features/jbus/src/jbus/dispatch.py`: `Turns.take`

At the sync commit the model was read against each of these, step by step: every pattern of `ValueOf` against `work.PATTERNS` in order, `StatusOf` against `work.status`, `Kept` against `work.kept`, the go verbs, and the launch's `approved` and depends guards in `Turns.take`.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new writer of a row's status or go, or `docs/jbus/row-moves.md`.
`features/jbus/tests/test_rowlife_spec.py` also fails when `queue.MOVES` and the spec's `Moves` differ, or when `work.VALUES` gains a value the spec neither has nor names as joined.

## Run it

```sh
uv run pytest features/jbus/tests/test_rowlife_spec.py -q
```

It runs TLC in a copy of the spec folder and prints `5 passed` in a few seconds; it skips where no Java runs TLC.
The bare TLC command is in `features/jbus/spec/README.md`, "Check the rule"; run it in a copy of the folder, since TLC writes `states/` where it runs.

- **Bounds:** one row, `Fault = "none"`, 2450 distinct states, `TypeOK` and `FinalStays`.
- **The canary:** `Fault = "no-latch"` takes `work.kept` out, and `FinalStays` breaks (`test_a_derive_that_writes_over_a_final_status_breaks_the_rule`).
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

## Drift at the sync commit

Neither breaks the rule as modeled; `/maintain-formal-verification-skill` fixes them.

- **Remove's guard:** the model lets Remove happen only from `queued`, `left` and `pr`, through `Moves`.
  The code's remove (`queue._do`) refuses only a row whose thread is at work, whose pull request is open or merged, whose launch is under way, or that others depend on, and `_take_out` then removes a row of any other status, `done` included; `withdraw` also removes a `gate` row.
  A removed `done` row would break `FinalStays` if modeled, and the README's "leaves out" names neither path.
- **Restate between approved values:** the model's `Restated` recomputes the value on every change of the go; `restated.restate` keeps an approved facet beside another approved one, so `behind` to `ready` waits for the next pass.
  It moves `value` only, never the status.
