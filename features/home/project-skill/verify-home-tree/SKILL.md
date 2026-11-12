---
name: verify-home-tree
description: Check HomeTree.tla, the variables, start and rules of a root home with two child homes on one repo (a retired child hands over what it had out, a quiet child is flagged, a call reaches you, one merger, no blind merge), against the code that keeps each rule. Use on any change to a rule's sentence in HomeTree.tla, or to the code a rule rests on: the handoff skill, `jbus/children.py`'s stall ladder and keep-alive, `jbus/merge.py`, `jmerge --home`, `jmerge/lock.py`.
---

# verify-home-tree

`features/home/spec/HomeTree.tla` holds the home tree's variables, its start and its rules, each with its sentence; the rules are the ones Josh set for the homes on 2026-10-23 and 2026-11-08.
`HomeTreeToday.tla` extends it with today's code (`verify-home-tree-today`), and TLC checks these rules on that.
So this model is the promise, and a change here changes what every run checks.

The rules, each with its harm:

- **`RetireHandsOver`:** what a retired child had out is the catch-all's (`uncategorized`). Broken, a crew's work is left with no home.
- **`StallFlagged`, `NudgesBounded`, `AsksAfterRelaunch`, `StallOnNeeds`, `RelaunchOnce`:** a quiet child with work out is nudged, nudged once more, launched again once, and then put on `jbus needs`, never on a home thread. Broken, a stalled child stays stalled unseen, or you are nudged for ever.
- **`CallsReachJosh`:** a call reaches you, also after the home thread failed. Broken, a question to you is stranded.
- **`OneMerger`:** jbus is the only merger. **`NoBlindMerge`:** a run of jmerge holds the merge lock from its read of main's tip to its merge. Broken, two merges race on one tip.
- **`ReadyMerges`:** a ready pull request merges. **`CatchallRuns`**, **`OneStart`**, **`WaitsForCause`:** the catch-all's home runs, starts once at a time, and waits after two failed starts on one cause.

## The record

The rules stand for the code that keeps them; that code is `HomeTreeToday.tla`'s, and a rule whose code is gone is a rule nothing keeps.

Model: `features/home/spec/HomeTree.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/home/skills/handoff/SKILL.md`: `home-id`, `plan-archived.md`
- `features/jbus/src/jbus/children.py`: `watch`, `keep_alive`, `launch`, `PATIENCE`
- `features/jbus/src/jbus/wakes.py`: `need_items`
- `features/jbus/src/jbus/merge.py`: `start`
- `features/jmerge/src/jmerge/cli.py`: `Repo.merge_holding`
- `features/jmerge/src/jmerge/lock.py`: `MergeLock`
- `features/jbriefs/src/jbriefs/home.py`: `stands_in`

At the sync commit each rule was read against the code that keeps it (the README's "The four rules today's code broke" names each guard), and its quotes stand once in their files.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the rules, as `/maintain-formal-verification-skill` says.

## Does a change touch it

Rerun it when the diff changes a rule's sentence or its definition in `HomeTree.tla`, a variable or the start, or the code a rule rests on (the record above).
A rule's words change only with the user's word for it, cited in the README.

## Run it

```sh
uv run pytest features/home/tests/test_home_tree_spec.py -q
```

The runs, scenes, bounds and canaries are `verify-home-tree-today`'s: each rule is checked on today's code in each scene, and each canary breaks the rule it rests on, so no rule holds by construction.

## A real bug or a modeling error

A rule that breaks on today's code is a finding about the code: report its story, and leave the rule's words as they are.
A rule that holds with its canary's guard out tests nothing: fix the rule or the canary, not the code.

## Change the model when the rules change on purpose

- A new rule: write its sentence beside it, add a canary in `canaries.py` that breaks it, and see it break before you trust a pass.
- A changed rule: keep the old words in the README with the user's word that changed them, as "The four rules today's code broke" does.

## Drift at the sync commit

None in the rules; the three mismatches of today's code with its model are in `verify-home-tree-today`.
