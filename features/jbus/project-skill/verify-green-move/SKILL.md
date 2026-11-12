---
name: verify-green-move
description: Check GreenMove.tla, jbus moving its green copy; use when changing jbus/green.py or jinstall's relink.
paths: "features/jbus/spec/GreenMove.tla, features/jbus/src/jbus/green.py, features/jinstall/src/jinstall/green.py, features/jmerge/src/jmerge/mainjson.py"
---

# verify-green-move

`features/jbus/spec/GreenMove.tla` follows one green copy (`jbus/green.py`) as passes move it to main's green tip.
A move grows the new tip's tree, writes the step it owes to `green.json` (`move`, `owes: install`), points the link, installs the tool again, writes `owes: relink`, removes the trees no command runs, and puts the harness layouts again (`jinstall.green.relink`); only a relink that is taken drops `move`.
Each pass resumes an owed step (`_resume`) before `_advance` reads `main.json`, and a failed install goes back (`_back`).
Each step's comment quotes the code it stands for.

The rules, each with its harm:

- **`ToolRunsCopy`:** once no move is in flight or owed, the tool runs the tree the link names.
  Broken, a unit starts on a tool the copy no longer holds (the journal's 203/EXEC on `~/.local/bin/jbus`).
- **`ToolTreeThere`:** the tree the tool runs is on disk.
- **`LayoutsFollow`:** once settled, the harness layouts were put from the tree the link names.
- **`NoReloadForRemoved`:** `green.json` owes systemd no reload for a tip whose move went back.
- **`CopyImports`:** the link never names a tip that does not import.
- **`StampTrue`:** `live` names no tip whose units the manager did not take.
- **`CopyOwned`:** the link names a tree on disk whose `jstack-checkout` marker `owner` reads.

## The record

Model: `features/jbus/spec/GreenMove.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/jbus/src/jbus/green.py`: `move`, `_resume`, `_advance`, `_settle`, `_back`, `_point`, `_reinstall`, `_grow`, `_live`, `reload`, `owner`, `in_flight`, `imports`, `FILE`, `MOVE`, `OWED`
- `features/jinstall/src/jinstall/green.py`: `relink`, `live`
- `features/jmerge/src/jmerge/mainjson.py`: `read`

At the sync commit the model was read against these with no drift found: `_advance`'s guard, `_grow`, `imports` and the refuse write, then the `owes` write and `_settle`; `_settle`'s point, reinstall, `_back` on failure, the relink write, the clean and `relink`; `_back`'s order; `_resume` before `_advance`; `_live` stamping only with no `why`; `reload` clearing only on success.
No other writer moves the copy: `jmerge/follow.py` reinstalls only a tool whose source is the main checkout.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, the order of `green.json`'s writes, or adds a writer of the link, the tool install or the harness layouts.
`features/jbus/tests/test_spec_quotes.py` fails when a quote of the spec no longer stands once in its file.

## Run it

```sh
uv run pytest features/jbus/tests/test_green_move_spec.py -q
```

It prints `7 passed` in about five seconds, and skips where no Java runs TLC.
The bare TLC command, with `-deadlock` since a copy at main's last tip has no step left, is in `features/jbus/spec/README.md`, "Check the rules of the green move"; run it in a copy of the folder.

- **Bounds:** `MaxTip = 3`, tip 2 one that does not import (`Broken = {2}`), 11614 distinct states.
- **The canaries:** `Fault = "no-owed"` (`ToolRunsCopy`, `LayoutsFollow`), `"no-back"` (`ToolRunsCopy`, `NoReloadForRemoved`), `"no-import"` (`CopyImports`), `"stamp-refused"` (`StampTrue`); `CopyOwned` has none.
- **Assumptions:** uv's install and the `owes: relink` write after it are one step, and a second install never fails; `took` is all units or none, with no transient units; of the owed reload only `at` and whether systemd takes it; a tree a hand removed takes `_back`.
  A pass that dies between `_grow` and the `owes` write, and a `_grow` that fails, are not modeled: both leave an unowed tree the next clean removes.

## A real bug or a modeling error

A trace is a pass's steps and the point it died.
Replay each step against `green.py` in order, with what `green.json` holds after each write; a step whose write the code makes in another order, or a resume the code does not take, is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the move's writes, where the pass died, and what the next pass found.

## Change the model when the code changes on purpose

- A new owed step or a new write to `green.json`: give it a step with its quote, in the code's order, and a canary that drops it.
- Show a changed rule failing on a scratch break first (drop the write it rests on in your own worktree, uncommitted, see the trace, `git restore` the file).

## Drift at the sync commit

None found.
