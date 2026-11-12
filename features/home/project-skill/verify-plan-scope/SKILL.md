---
name: verify-plan-scope
description: Check PlanScope.tla, a plan entry's close, a scope's retire and a blocker's fixes moved between homes; use when changing jbus plan close, the blockers ledger, jbus queue move, a brief's Home: line or the handoff's retire.
paths: "features/home/spec/PlanScope.tla, features/jbus/src/jbus/plan.py, features/jbus/src/jbus/blockers.py, features/jbus/src/jbus/queue.py, features/jbus/src/jbus/asks.py, features/jbriefs/src/jbriefs/home.py, features/home/skills/handoff/SKILL.md, features/home/skills/home/clearing-its-own-blockers.md, features/home/templates/plan-entry.md"
---

# verify-plan-scope

`features/home/spec/PlanScope.tla` holds one variable for each carrier of a home's plan and scopes (ledger rows A-168, C-065 to C-068, C-073, C-074, C-081, C-082, C-095, C-099), each with a comment that quotes the code that writes it.
A process can die between any two writes, so the model keeps the half-done states the disk shows.

The rules, each with its harm:

- **`EntryOnce`:** an entry is in plan.md or plan-done.md, and in both only between the two writes of one close.
  Broken, a closed entry is lost, or plan-done.md holds it twice.
- **`RetireWhole`:** a retired scope's work has a home: its open gate is the catch-all's question, and each brief that named it is the catch-all's.
  Broken, a crew's work is left with no home after a retire.
- **`FixCountedOnce`:** a blocker's fix is counted once across a move between two homes.
  Broken, the retry cap counts a fix twice or never.
- **`FixCountedWhereRead`:** each counted fix is in the ledger of the home admit reads.
  Broken, a fix moved part way is counted where nothing reads it.
- **`FixCountedWhereReadOrMoveAgain`:** each counted fix is in the ledger admit reads, or is the one a move cut short left behind, which the move run again carries.
  Broken, a fix is stranded where no step ever carries it, as the plan's archive did before `jbus retire`.

Today's code breaks only `FixCountedWhereRead` (a move cut before `blockers.rehome`), and `PlanScope.cfg` keeps its trace; `FixCountedWhereReadOrMoveAgain` holds, so a move run again is the only way out of it.
`jbus retire` (`blockers.retire`, #1793) carries the scope's tries to the catch-all's ledger under both locks before the plan is archived.
A close cut short and run again appends no second copy, since `plan.close` skips the append when plan-done.md already ends with the entry's section, so `EntryOnce` holds; the `close-twice` canary puts the second append back and breaks it.

## The record

Model: `features/home/spec/PlanScope.tla`
Sync: `5262b615eb33fbb34378feceace804d7a4421cda`
Covers:
- `features/jbus/src/jbus/plan.py`: `close`, `entries`, `Stage`, `Entry`
- `features/jbus/src/jbus/blockers.py`: `admit`, `rehome`, `tries`, `ledger`, `head`, `retire`, `LEDGER`, `LOCK`
- `features/jbus/src/jbus/queue.py`: `move`
- `features/jbus/src/jbus/asks.py`: `_move`
- `features/jbriefs/src/jbriefs/home.py`: `home_of`, `scopes`, `WAS`
- `features/home/skills/handoff/SKILL.md`: `handoff.next.md`, `plan-archived.md`, `home-id`
- `features/home/skills/home/clearing-its-own-blockers.md`: `When green:`
- `features/home/templates/plan-entry.md`: `Stage:`

At the sync commit each backticked quote of the spec stood once in its file, as `features/home/tests/test_plan_scope_spec.py` checks on every run.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says.

## Does a change touch it

Rerun it when the diff changes a carrier's writer or reader above, a step or rule in `PlanScope.tla`, or `PlanScope.cfg`.

## Run it

```sh
uv run pytest features/home/tests/test_plan_scope_spec.py -q
```

It finds each quote of the spec once in its file, runs TLC on `PlanScope.cfg` and on each canary (`Fault = "close-twice"` breaks `EntryOnce`, `Fault = "move-one-lock"` breaks `FixCountedOnce`, and `Fault = "retire-no-carry"` and `Fault = "carry-then-unlock"` break `FixCountedWhereReadOrMoveAgain`), and skips the TLC runs where no Java runs TLC.

## A real bug or a modeling error

A rule today's code breaks is a finding about the code: the cfg's `expect:` lines keep its trace, and the fix is a brief of its own (st-plan-close-once, st-retire-carries-fixes).
A canary that does not break its rule tests nothing: fix the rule or the canary, not the code.

## Drift at the sync commit

None: the one rule today's code breaks is expected in the cfg, not drift.
st-model-upkeep-run merged main at `5262b615e`, where st-retire-carries-fixes (#1793) added `jbus retire` and brought the model with it: the retire's carry, its rule and its two canaries; the skill moved there.
