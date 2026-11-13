---
name: verify-row-life
description: Check RowLife.tla, a queue row's status and go; use when changing work.status, queue.MOVES, queue.derive or the go verbs.
paths: "features/jbus/spec/RowLife.tla, features/jbus/src/jbus/work.py, features/jbus/src/jbus/queue.py, features/jbus/src/jbus/restated.py, features/jbus/src/jbus/dispatch.py, features/jbus/src/jbus/watch.py, features/jbus/src/jbus/asks.py, features/jbus/src/jbus/reverts.py"
---

# verify-row-life

`features/jbus/spec/RowLife.tla` follows one row of jbus's queue from `jbus queue add` to its end, in two regions at once: the status a pass derives from the facts (`work.status`, written by `queue.derive`), and the go the verbs move (`_grant`, `_hold`, `_lift`, `_void`).

- **The rule, `FinalStays`:** a row that is over stays over; a `done` row may only become `merged`, and a `merged` one stays so.
- **The harm if it breaks:** the queue, `watch.final` and jmerge all read `work.over`, so a row seen over and then not is launched, merged or judged again.
- **The table:** `queue.MOVES` is each change of status one step of TLC's graph of the spec makes, so a pass marks `"legal": false` only a fault.

It holds because `queue.derive` keeps the status of a row that is over (`work.kept`), so the check is of the code's derive and not only of the table.

## The record

Model: `features/jbus/spec/RowLife.tla`
Sync: `d3f642c80a2c52ebbf134aa981d95894e892201a`
Covers:
- `features/jbus/src/jbus/work.py`: `status`, `kept`, `over`, `FINAL`, `PATTERNS`, `VALUES`
- `features/jbus/src/jbus/queue.py`: `MOVES`, `derive`, `_grant`, `_hold`, `_lift`, `_void`, `_take_out`, `_launching`, `reland`
- `features/jbus/src/jbus/asks.py`: `_asks`
- `features/jbus/src/jbus/restated.py`: `restate`
- `features/jbus/src/jbus/dispatch.py`: `Turns.take`
- `features/jbus/src/jbus/watch.py`: `gone`, `unwritten`, `KNOWN`, `unlanded`
- `features/jbus/src/jbus/reverts.py`: `reland`

The first sync, 228c1436c, read the model against each of these, step by step: every pattern of `ValueOf` against `work.PATTERNS` in order, `StatusOf` against `work.status`, `Kept` against `work.kept`, the go verbs, `remove`'s guard (`out` in `asks._asks`, `_launching`), and the launch's `approved` and depends guards in `Turns.take`.
At this sync, main's tip when this branch last took main in, the four covered changes since were read against the model.
#1720 (7e68838af) and #1759 (d3f642c80) changed the model with the code: `Moves` is `queue.MOVES` move for move, `StatusOf` gives a launched row whose thread is none, missing or settled `stale` and an unlaunched one `queued`, as `work.status` and `_THREAD` do, and a launch derives with a `starting` thread, as `watch.gone` leaves it.
#1726 (ee2657c3a) changed only the order a pass launches in (`queue.order`, `Turns.take`'s ranking), which the model does not follow.
#1724 (1bf7b41df) changed `work.PATTERNS`, and the upkeep below changed the model with it.
`features/jbus/tests/test_rowlife_spec.py` passed there (6 passed).
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new writer of a row's status or go, or `docs/jbus/row-moves.md`.
`features/jbus/tests/test_rowlife_spec.py` also fails when `queue.MOVES` and the status edges of TLC's graph differ, or when `work.VALUES` gains a value the spec neither has nor names as joined.

## Run it

```sh
uv run pytest features/jbus/tests/test_rowlife_spec.py -q
```

It runs TLC in a copy of the spec folder and prints `7 passed` in a few seconds; it skips where no Java runs TLC.
The bare TLC command is in `features/jbus/spec/RowLife.md`, "Check the rule"; run it in a copy of the folder, since TLC writes `states/` where it runs.

- **Bounds:** one row, a scout's or a crewmate's, `Fault = "none"`, 13256 distinct states, `TypeOK` and `FinalStays`.
- **The canaries:** `Fault = "no-latch"` takes `work.kept` out, and `FinalStays` breaks (`test_a_derive_that_writes_over_a_final_status_breaks_the_rule`); `Fault = "any-hand-over"` lets the hand-over take a crewmate's done row, and `FinalStays` breaks (`test_a_hand_over_of_a_crewmates_done_row_breaks_the_rule`); `Fault = "settled-queued"` gives a settled thread's row `queued` again, and its graph has status edges `queue.MOVES` lacks.
- **Assumptions:** a fact's change and the pass that sees it are one step (no restate drift between passes, no one-source pass); the facts are folded (an open pull request's eight steps are `check`, `quiet` is `working`); no clock, so `watch.unwritten`'s stale to left is out; a scout's row only as far as its role and the hand-over, and no `merge_after`.
  The rest is in the README's "What the model leaves out".

## A real bug or a modeling error

Each step of a trace must be a move the code makes.
Replay it against the record's files: a fact's change is one input `work.status` reads, the pass is `queue.derive`, and a go step is the verb of `queue.py` its name gives.
A step no code makes is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the row's moves in the code's words, and leave the rule as it is.

## Change the model when the code changes on purpose

- A new status or value: add it to `ValueOf` and `StatusOf` in the order of `work.PATTERNS`, then rerun.
- A new move in `queue.MOVES`: the test fails until the spec's graph makes it.
- A new writer of the status: model it as a step, or say in the README why it moves nothing.
- Show a changed rule failing on a scratch break before you trust a pass: take the guard out in your own worktree, uncommitted, see the trace, `git restore` the file.

## The last upkeep

`/maintain-formal-verification-skill` ran at `228c1436c` (st-model-upkeep-run) and fixed two drifts in the model:

- **Remove's guard** followed `Moves`, which names the removals seen and guards none; it now follows `out` in `asks._asks`: no thread at work, no open or merged pull request.
  A `done` row may be removed, so `FinalStays` lets a `done` row leave for good as `removed` (queue.py's doc: "`remove` takes a row out for good"; `rows.remove(row)`), and a removed row stays removed.
  Old: `status \in Final => status' \in Final`; new: `status \in Final => status' \in Final \cup {"removed"}`, and `removed` stays.
  The break: dropping the merged guard lets a merged row be removed, and `FinalStays` fails.
- **An add's new depends:** `Depends` moves an approved row between free and behind with its line unchanged (`restated.restate` keeps an approved facet beside another), and `Pass` writes the line again with no fact changed.

The row was then rebased onto st-model-sync, whose merge of main brought main to `8f4c21b6f`, and the upkeep diffed the covered code again from `228c1436c` to it: #1724 drifted the model: a thread at work with no pull request is now at work whatever its last Result says (`work.py`'s `WORKING`, and the leftover pattern's `apart`), so `ValueOf` reads a leftover of a thread at work with no pull request as `working`, and every rule still holds with each canary breaking its rule.
#1726's order (`queue.order`, `Turns.rest`) is not in what this model covers.
The sync commit moved there.

st-model-sync then merged main again, to `2fb4e2587`, and the row was rebased onto it; the upkeep diffed the covered code from `8f4c21b6f`: #1720 made `queue.MOVES` hold every move `work.status` makes and added `MovesKnown` here, guarding `Remove` by `Moves` as before.
With this row's `Remove`, which follows `asks.out`, `MovesKnown` broke at once (queued, then `gate` on a question, then `removed`), since a removal is the `remove` verb's, which `derive` never judges (queue.py's `MOVES` docstring); `MovesKnown` now judges every move but a removal, and both rules hold over 2502 distinct states with each canary breaking its rule.
The sync commit moved there.

st-model-sync then merged into main as #1734, and the row's own commits moved onto main at `cf26d3e5f`, where #1759 had moved the sync to `d3f642c80` with the model: its `stale` launch and `settled-queued` canary stand beside this row's `Remove`, `ValueOf` and `MovesKnown`, and both rules hold with each canary breaking its rule.

st-code-conforms then took main in at `74f067be2`.
There `queue.MOVES` is the graph's status edges, so `Moves` and `MovesKnown` are gone, and `remove` refuses a row that is over (queue.py `{verb.slug} is {row['status']}, and a row that is over stays`).
So `Remove` guards on `status \notin Final \cup {"removed"}` alone, and `FinalStays` is again `status \in Final => status' \in Final`.
`remove`'s other refusals, a thread at work, an open or merged pull request, a launch with no answer yet, read T3 Code and GitHub at the verb, not the facts a pass last saw, so the spec leaves them out (RowLife.md's "What the model leaves out"), and the graph keeps each removal a replayed log can show.
`Depends`, `Pass` and #1724's `ValueOf` stand, and `FinalStays` holds over 3092 distinct states with each canary breaking its check.

st-hand-over-line then gave the row a `role`, scout or crew, and a `HandOver` step, the add of a crewmate's brief over a scout's done row, which `queue._hand_over` writes as a line marked `handed`.
`FinalStays` lets a scout's done row leave only by it (`status' \in Final \/ (role = "scout" /\ role' = "crew")`), and holds over 6184 distinct states with each canary breaking its check.

reverted-row-reland then gave the row a `reverted` fact and a `Reland` step: once the revert jbus opened of a merged row's merge merges, `reverts.reland` moves the row from `merged` to `left` with a line marked `reverted`, and `watch.unlanded` reads that merge as no merge of the row's, so its pull request reads as closed or none and the row's redo goes the normal path.
`FinalStays` lets a merged row leave only by it, once (`Reopened == ~reverted /\ reverted'`), `queue.MOVES` holds `merged` to `left`, and the rule holds over 13256 distinct states with each canary breaking its check.
The Sync line stays where it was: this row read only its own change against the model.
