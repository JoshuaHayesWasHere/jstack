---
name: verify-home-tree-today
description: Check HomeTreeToday.tla, today's code for the root and child homes; use when changing jbus/children.py, wakes, the merge run or lock, or the handoff block.
paths: "features/home/spec/HomeTreeToday.tla, features/jbus/src/jbus/children.py, features/jbus/src/jbus/wakes.py, features/jbus/src/jbus/merge.py, features/jmerge/src/jmerge/cli.py, features/jmerge/src/jmerge/lock.py, features/jbriefs/src/jbriefs/home.py, features/home/skills/handoff/SKILL.md"
---

# verify-home-tree-today

`features/home/spec/HomeTreeToday.tla` models today's code for a root home and two sibling child homes: child a does one feature and is archived, child b is a routine with a rhythm, each with a pull request, a crew thread and two calls to you, and a call reaches you through the root's home thread, which can fail.
It extends `HomeTree.tla`, which holds the variables, the start and the rules (`verify-home-tree`).
Each condition names the file that checks it and quotes the code, and its constant `Drop` takes one guard out.

The rules are `HomeTree.tla`'s; their harms are in `verify-home-tree`.
This skill is for what the code does: when a step here stops being the code's, the rules are checked on code that no longer exists.

## The record

Model: `features/home/spec/HomeTreeToday.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/jbus/src/jbus/children.py`: `watch`, `_act`, `_stall`, `keep_alive`, `launch`, `_going`, `_failed`, `_waits`, `_stage`, `started`, `live`, `whose`, `watched`, `_rhythm`, `STAGES`, `FAILURE`, `PATIENCE`, `USERS`, `LAUNCHES`
- `features/jbus/src/jbus/wakes.py`: `need_items`, `pick`, `kept`, `_send`
- `features/jbus/src/jbus/merge.py`: `start`, `keep`
- `features/jmerge/src/jmerge/cli.py`: `Repo.merge`, `Repo.merge_holding`
- `features/jmerge/src/jmerge/lock.py`: `MergeLock.take`, `MergeLock.give`
- `features/jbriefs/src/jbriefs/home.py`: `stands_in`
- `features/home/skills/handoff/SKILL.md`: `home-id`, `plan-archived.md`

At the sync commit every action's guards and quotes were read against these: `Acts`' timing against `children.watch`'s start (`last or since + patience*rank`), `keep_alive`, `_going`, `_failed` and `_waits` against `KeepAlive`, `StartEnds`, `StartWrites` and `CauseClears`, the merge lock against `merge_holding`, and the order of the handoff block.
The upkeep below fixed one of the three older mismatches and kept two as stated assumptions.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, how a call or a gate reaches you, when a quiet home is nudged or launched again, or who may merge.
`features/home/tests/test_home_tree_spec.py` fails when a quote of either spec no longer stands once in its file.

## Run it

```sh
uv run pytest features/home/tests/test_home_tree_spec.py -q
```

It runs the 30 runs of `canaries.py` (each rule in each scene, and each canary), the quote checks, and four tests that drive the real code along the stories the code once broke; it takes seconds when TLC's verdicts come from the statechart tools' cache (`tools.kept`), and skips where no Java runs TLC.
By hand, from the repo root:

```sh
uv run python features/home/spec/canaries.py
```

It prints one line a run and ends 0 when every run says what it should.

- **Bounds:** `K = 2`, `Rhythm = 1`; the scenes are `a` (child a alone with both calls and a home thread that can fail, 398,880 states), `b` (the same for child b, 237,780) and `siblings` (both children, no calls, a home thread that never fails, 280,108).
  `HomeTreeToday.cfg`, the chart's scene, is child a with one call, `K = 1` and a home thread that never fails.
- **The canaries** (`Drop`): `hand-over`, `keep-on-fail`, `flag`, `beat`, `needs`, `nudge-cap`, `relaunch-once`, `ask`, `one-merger`, `lock`, `all-homes`, `drop-release`, `keep-alive`, `going`, `waits`, each breaking the rule that rests on it; `canaries.py` names each one's rule and scene.
- **Assumptions:** two children; a pull request drops at most once; the home thread fails at most once; a nudge and a launch are always sent; weak fairness on the steps that happen by themselves.
  The rest is in `features/home/spec/README.md`, "What the model leaves out".

## A real bug or a modeling error

Each condition quotes its code.
Open each quote of a trace at its file and check the code still guards the step as quoted; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the homes' story (a call, a nudge, a launch, a merge) in the code's words, and add a test that drives the real code along it, as `test_home_tree_spec.py` has for the four rules the code once broke.

## Change the model when the code changes on purpose

- A new guard: add it with a `Drop` value and a canary in `canaries.py` that breaks the rule it holds.
- A change to how a call reaches you: model each route the code takes (see the last upkeep below), not one `up` flag.
- Show a changed rule failing on a scratch break first (take the guard out in your own worktree, uncommitted, see the trace, `git restore` the file).

## The last upkeep

`/maintain-formal-verification-skill` ran at the sync commit (st-model-upkeep-run): the covered code is unchanged from it to the row's base, and the three older mismatches were settled from the code.

- **Fixed, `RaiseCall`:** a call no longer calms the spell. `children.watch` leaves calls out of the spell's signature (`USERS`), so a call is only a write of the child's home thread, which ends the spell only while it is `calm`.
  Every rule still holds in every scene with the same states (398,880, 237,780, 280,108), and every canary still breaks its rule: `uv run pytest features/home/tests/test_home_tree_spec.py -q` printed `46 passed`.
- **Kept as an assumption, a failed nudge or launch:** modeled, a send that fails while T3 Code is down leaves a quiet child `calm` past its patience, which `StallFlagged` forbids as worded, and a rule's words change only on the user's word.
  The code tries again each pass, so the step is late, not lost. The README's "leaves out" says so.
- **Kept as an abstraction, one route to you:** `wakes.need_items` sends a child's gate to its own home thread, and approve, stalled, install and self-asked gates to no thread; the model's single `up` flag is every route, and the README's "leaves out" says so.
- The spec's header no longer names main 21112eba8, and the README and `canaries.py` give `uv run python`.
