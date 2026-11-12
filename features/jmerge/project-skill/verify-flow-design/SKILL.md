---
name: verify-flow-design
description: Check FlowDesign.tla and its canaries, the merge flow's design; use when changing the guard a rule rests on: test selection, rejudge, or the stray sweep.
paths: "features/jmerge/spec/FlowDesign.tla, scripts/select_tests.py, features/jmerge/src/jmerge/cli.py, features/jmerge/src/jmerge/ready.py, features/jmerge/src/jmerge/rejudge.py, features/jbus/src/jbus/strays.py, features/jbus/src/jbus/dispatch.py"
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
Sync: `8f4c21b6f59fc1bfbccace831d3a916bae72fb5d`
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

## The last upkeep

`/maintain-formal-verification-skill` ran at `228c1436c` (st-model-upkeep-run): the covered code is unchanged from it to the row's first base, and the stale comments were fixed.

- `proved` and `told` are gone: nothing read `proved`, and `told` was never set, so `Rejudge`'s `~told` and `CrewFix`'s `told[p]` were constants.
  The design holds over the same 425 states, and `NoGuard`, `NoRejudge` and `NoSweep` (rebuilt from it) still break their rules.
- The header no longer cites FlowToday.tla's `named`, which fl-no-draft took out; `CrewFix` says the code has the step since #946, and wider; `Rejudge` says the code's once a head and tip and main's line are FlowToday.tla's; `ApproveMainFix` says jbus approves the row by rule since #547.
- `MainFixWaitsOnlyOnYou` keeps its words, "waits only on your approval", while the approval is jbus's by rule: a rule's words change only on the user's word, so this is for them.

The row was then rebased onto st-model-sync, whose merge of main brought main to `8f4c21b6f`, and the upkeep diffed the covered code again from `228c1436c` to it: `ready.py` changed in #1715, #1721 and #1727, and `dispatch.py` in #1726, none of it in `red_only` or `room`, so the sync commit moved there.
