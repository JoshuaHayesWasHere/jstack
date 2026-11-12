---
name: verify-flow-design
description: Rerun TLC on FlowDesign.tla, the merge flow's design with its three guards (the cross-cutting check, rejudging a red pull request, sweeping a crew's leftover processes), and on its canaries in features/jmerge/spec/canary/, each the design with one guard out. Use on any change to the guard a rule rests on: `scripts/select_tests.py`'s selection, `jmerge.cli.Repo.again` and `in_turn`, `ready.red_only`, `rejudge.BaseMerge`, `jbus.strays.stop`, or the launch room in `jbus/dispatch.py`.
---

# verify-flow-design

`features/jmerge/spec/FlowDesign.tla` is the merge flow as designed: two pull requests open from the start, a main that can go red, and a machine a crew can leave full, with three guards.
It is the design today's code is held to, and `features/jmerge/spec/canary/` holds it with each guard out, so no rule holds by construction.
Today's code is `verify-flow-today`'s.

- **`Check`**, the cross-cutting guard: a check runs every test that reads the changed tree.
- **`Rejudge`**: a pull request red only over a red main is judged again once main moves.
- **`Sweep`**: a crew's leftover process, idle or busy, is stopped as its turn ends.

The rules are `FlowsWhenGreen`, `NoMergeTurnsMainRed`, `MachineNotLeftFull` and `MainFixWaitsOnlyOnYou`, in the words they had before 2026-11-03; their harms are `verify-flow-today`'s.

## The record

FlowDesign models no line of code: each guard stands for the code that is that guard today, and a change there can make the guard not the one the design proves.

Model: `features/jmerge/spec/FlowDesign.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `scripts/select_tests.py`: `cross_cutting`, `unowned`, `owns`, `declared`
- `features/jmerge/src/jmerge/cli.py`: `Repo.judge`, `Repo.again`, `Repo.in_turn`
- `features/jmerge/src/jmerge/ready.py`: `red_only`
- `features/jmerge/src/jmerge/rejudge.py`: `BaseMerge`
- `features/jbus/src/jbus/strays.py`: `stop`
- `features/jbus/src/jbus/dispatch.py`: `room`

At the sync commit each guard was read against this code: `Check` is the selection of `select_tests.py` with `testing/tests/test_cross_cutting.py`'s list, `Rejudge` is `Repo.again` and its turn in main's line (`in_turn`), `Sweep` is `strays.stop`, and the room a launch needs is `dispatch.room`.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the design's guards, as `/maintain-formal-verification-skill` says.

## Does a change touch it

Rerun it when the diff touches a file of the record, or the spec or a canary under `features/jmerge/spec/`.

## Run it

```sh
uv run pytest features/jmerge/tests/test_flow_spec.py -q
```

The test runs the design and its canaries in the same run as FlowToday, so it takes some minutes; the design's own runs take about a second each.
`flow_canaries.py` prints one line a run; its command is in `features/jmerge/spec/README.md`, "Check the rules".

- **Bounds:** 425 distinct states.
- **The canaries:** `NoGuard` (a check that selects by chance) breaks `NoMergeTurnsMainRed`; `NoRejudge` breaks `FlowsWhenGreen`; `NoSweep` breaks `FlowsWhenGreen` and `MachineNotLeftFull`.
- **Assumptions:** both pull requests are open from the start, so no launch and no row order; no browser run; one outside break.

## A real bug or a modeling error

The design breaking a rule is a design fault: the guards it has are not enough, and that is reported, not hidden.
A canary that no longer breaks its rule means the rule holds without that guard, so the canary or the rule no longer tests what it says: fix the model.

## Change the model when the design changes on purpose

- A new guard: add it as a step, add a canary under `canary/` that takes it out, and add both runs to `flow_canaries.py`.
- Change a rule's words here and in `FlowToday.tla` together, and say why in the README.

## Drift at the sync commit

The design differs from the code on purpose; these are comments of the spec that no longer say what is so, for `/maintain-formal-verification-skill`.

- The header cites "FlowToday.tla's `named`", which no longer exists.
- `CrewFix` calls a crew reading a failure over the red as its own "a step the code lacks"; #946 added it.
- `proved` is written and no guard or rule reads it, so "merges past the red once its own check proves the fix" describes nothing.
- `ApproveMainFix` keeps your approval of main's fix row, where jbus approves it by rule since #547.
- `Rejudge`'s `~told` ("once a head and tip") is now the `base-merges.json` record and main's line.
