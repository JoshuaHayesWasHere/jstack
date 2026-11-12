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

Today's code breaks `EntryOnce` (a close cut short and run again appends a second copy) and `FixCountedWhereRead` (a move cut before `blockers.rehome`); `PlanScope.cfg` keeps each trace.

## The record

Model: `features/home/spec/PlanScope.tla`
Sync: `6b542bfe10eb0f8288d96b81401349595ad3210e`
Covers:
- `features/jbus/src/jbus/plan.py`: `close`, `entries`, `Stage`, `Entry`
- `features/jbus/src/jbus/blockers.py`: `admit`, `rehome`, `tries`, `ledger`, `head`, `LEDGER`, `LOCK`
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

It finds each quote of the spec once in its file, runs TLC on `PlanScope.cfg` and on each canary (`Fault = "close-twice"`, `Fault = "move-one-lock"`), and skips the TLC runs where no Java runs TLC.

## A real bug or a modeling error

A rule today's code breaks is a finding about the code: the cfg's `expect:` lines keep its trace, and the fix is a brief of its own (st-plan-close-once, st-retire-carries-fixes).
A canary that does not break its rule tests nothing: fix the rule or the canary, not the code.

## Drift at the sync commit

None: the two rules today's code breaks are expected in the cfg, not drift.
