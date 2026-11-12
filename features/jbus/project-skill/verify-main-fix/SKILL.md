---
name: verify-main-fix
description: Rerun TLC on MainFix.tla, the model of how jbus files main's revert, main's fix row, the Mac's fix row and each nightly's row write by write when a pass dies between two writes, and read what it finds. Use on any change to `reverts.revert`, `opened`, `_mac_file`, `macos`, `watch._file`, `watch._nightly_red` or `_filed`, the runs files the nightlies keep, or the slot order of `jbus/poll.py` that runs them.
---

# verify-main-fix

`features/jbus/spec/MainFix.tla` takes the two steps `MainRed.tla` folds into one, `reverts` and `fixes`, and gives each write its own step, with a pass that can die between any two writes while the disk and GitHub keep what was written.
Each variable is a carrier of the st-state-ledger's MainFix rows, and its comment quotes the code that writes it: the revert's brief (`revertBrief`), main's fix brief and row (`fix`), the Mac's fix row (`macFix`), and the runs each nightly has seen (`browserSeen`, `macosSeen`, `scheduledSeen`).

The rules, each with its harm:

- **`FiledWhole`:** after any crash, a red tip has a fix row and its brief, or neither, by the next pass.
  Broken, a brief with no row is a fix nobody launches, and a row with no brief a crew with nothing to do.
- **`RevertKnown`:** an open revert on GitHub has its `reverts.json` record by the next pass.
  Broken, jmerge never merges it and `reverts.close` never closes it, since both read only a revert on record.
- **`RefinesMainRed`:** each step is `MainRed.tla`'s `reverts` or `fixes` step, or leaves both as they are.

## The record

Model: `features/jbus/spec/MainFix.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/jbus/src/jbus/reverts.py`: `revert`, `opened`, `FIELDS`, `brief`, `_keep`, `macos`, `_mac_red`, `_mac_file`, `culprit`, `Keep`, `tested`
- `features/jbus/src/jbus/culprits.py`: `judge`, `kept_why`
- `features/jbus/src/jbus/watch.py`: `_file`, `watch`, `NIGHTLIES`, `_nightly_red`, `_filed`, `drawn_apart`, `NIGHTLY_WINDOW`, `NIGHTLY_RED`
- `features/jbus/src/jbus/poll.py`: `steps`, `first_half`, `second_half`

At the sync commit the model was read against these: `revert`'s write order (`opened`, `gh pr revert`, a missing branch, the brief, `_keep`, the event line), a refused revert going to `_file` or `_mac_file`, `_file` and `_mac_file` writing the brief and then `queue.add` behind `queue.fresh`, and `_nightly_red`'s `seen` branches, its stale skip, `_filed`, then the run kept as seen.
The only change to these files since the model's main (aa5469d97) was 23f42940f, which moved imports.
Two places the model differs are below.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, the order of a revert's or a fix row's writes, the nightlies jbus watches, or where in the pass `watch.watch`, `reverts.macos` or `culprits.judge` runs.
`features/jbus/tests/test_main_fix_spec.py` fails when a quote no longer stands once in its file, or a carrier has no variable.
A change to a red's culprit, its revert's holders, `close` or `_withdraw` is `verify-main-red`'s.

## Run it

```sh
uv run pytest features/jbus/tests/test_main_fix_spec.py -q
```

It prints `9 passed` in about half a minute, and skips where no Java runs TLC.
The bare TLC command is in `features/jbus/spec/README.md`, "Check the rules of main's fix"; run it in a copy of the folder.

- **Bounds:** `MainFix.cfg` is a pass that dies and no other fault (`World = {}`), `MaxTip = 3`, all three nightlies watched, 1244712 distinct states; with `World = {"refuses"}` `RefinesMainRed` holds over 12557140 states in about a minute.
- **The canary:** `Fault = "no-reopen-check"` is `opened` not asking GitHub for the revert's branch, and `RevertKnown` breaks.
- **The findings** the test's `FINDINGS` keeps breaking: `RevertSaid` on a crash alone (a pass dying between `reverts.json` and `events.jsonl`), `RevertKnown` with `"hand"` and with `"refuses"`, `FiledWhole` with `"refuses"` and with `"late"`.
  `MainFix.cfg`'s comment keeps each trace.
- **Assumptions:** one red, with no holders, `close`, `_withdraw` or stuck revert (`MainRed.tla` has them); no `_add_tip`; a queue that never refuses a brief; no first pass, no `NIGHTLY_GRACE`; no run with both shots and other failures; one scheduled workflow.
  The rest is in the README's "What the main-fix model leaves out".

## A real bug or a modeling error

A trace is a pass's writes, the one it died after, and what the next pass did.
Replay each write against the record's code in order; a step whose condition carries no quote is the world's (GitHub, a hand, time) or the pass's own place, and must be one the code can meet.
A write the code makes in another order is a modeling error, and the model is what gets fixed.
A new break, past `FINDINGS`, is a bug: tell it as the writes, the crash, and the half-filed state the next pass left.

## Change the model when the code changes on purpose

- A fix for a finding: the test's `FINDINGS` fails until the cfg's comment and the list drop it.
- A new carrier: give it a variable whose comment quotes its writer, and steps in the code's order.
- Show a changed rule failing on a scratch break first (swap two writes in your own worktree, uncommitted, see the trace, `git restore` the file).

## Drift at the sync commit

Neither breaks a rule as modeled, since the variables they touch do not overlap; `/maintain-formal-verification-skill` fixes them.

- **The pass order:** the model and the README say a pass judges the Mac (step 9), then main (12), then reads each nightly (40).
  In `poll.py`, `watch.watch` (rank 40) is in the `tellers` slot, which runs before `after-expedite`, so the nightlies are read first; and step 40 needs a client, so a pass with no T3 Code sign-in reads no nightly at all.
- **The shots row is not the browser's alone:** `drawn_apart` runs on every nightly, and a `shots-<day>` row is free to any of them; the model lets "shots" happen only on the browser run.
