---
name: verify-main-fix
description: Check MainFix.tla, main's revert and fix rows filed write by write; use when changing reverts.revert, watch._file or _nightly_red, or the pass order.
paths: "features/jbus/spec/MainFix.tla, features/jbus/src/jbus/reverts.py, features/jbus/src/jbus/culprits.py, features/jbus/src/jbus/watch.py, features/jbus/src/jbus/poll.py"
---

# verify-main-fix

`features/jbus/spec/MainFix.tla` takes the two steps `MainRed.tla` folds into one, `reverts` and `fixes`, and gives each write its own step, with a pass that can die between any two writes while the disk and GitHub keep what was written.
Each variable is a carrier of the st-state-ledger's MainFix rows, and its comment quotes the code that writes it: the revert's brief (`revertBrief`), the revert a pass set out to open (`opening`, `reverts-opening.json`), main's fix row and its brief (`fix`), the Mac's fix row (`macFix`), and the runs each nightly has seen (`browserSeen`, `macosSeen`, `scheduledSeen`).

The rules, each with its harm:

- **`FiledWhole`:** after a pass that ran every step, no fix or nightly brief stands without its row.
  Broken, a brief with no row is a fix nobody launches, and no pass queues it once it judges the red another way or the run stale.
- **`RevertKnown`:** an open revert on GitHub has its `reverts.json` record by the next pass.
  Broken, jmerge never merges it and `reverts.close` never closes it, since both read only a revert on record.
- **`RevertSaid`:** each revert on record has its line in `events.jsonl`.
  Broken, every later pass reads the revert as its own (`Keep.OPENED`), and nobody hears of it.
- **`RefinesMainRed`:** each step is `MainRed.tla`'s `reverts` or `fixes` step, or leaves both as they are.

## The record

Model: `features/jbus/spec/MainFix.tla`
Sync: `5f87506cc406181412c7013343cf0152ebe1061a`
Covers:
- `features/jbus/src/jbus/reverts.py`: `revert`, `opened`, `branch_of`, `FIELDS`, `brief`, `_keep`, `_own`, `_intend`, `_drop_intent`, `known`, `_aged`, `OPENING`, `READ_WAIT`, `macos`, `_mac_red`, `_mac_file`, `culprit`, `Keep`, `tested`
- `features/jbus/src/jbus/culprits.py`: `judge`, `kept_why`
- `features/jbus/src/jbus/watch.py`: `_file`, `copy_brief`, `watch`, `look`, `NIGHTLIES`, `_nightly_red`, `_filed`, `drawn_apart`, `NIGHTLY_WINDOW`, `NIGHTLY_RED`
- `features/jbus/src/jbus/poll.py`: `steps`, `first_half`, `second_half`

At the sync commit the model was read against these: `revert`'s write order (`opened`, `_intend`, `gh pr revert`, a missing branch, the brief, then `_own`'s event line, `_keep` and `_drop_intent`), `known` keeping or dropping the name `reverts-opening.json` holds, a refused revert going to `_file` or `_mac_file`, `_file` and `_mac_file` running `queue.add` behind `queue.fresh` and then `copy_brief`, `_nightly_red`'s `seen` branches, its stale skip, `drawn_apart` on every nightly, `_filed`, then the run kept as seen, and the pass's slots: `tellers` (`reverts.known`, `watch.watch`) before `after-expedite` (`reverts.macos`, `culprits.judge`), each step skipped where `poll.steps` finds a need unmet.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, the order of a revert's or a fix row's writes, the nightlies jbus watches, or where in the pass `reverts.known`, `watch.watch`, `reverts.macos` or `culprits.judge` runs.
`features/jbus/tests/test_main_fix_spec.py` fails when a quote no longer stands once in its file, or a carrier has no variable.
A change to a red's culprit, its revert's holders, `close` or `_withdraw` is `verify-main-red`'s.

## Run it

```sh
uv run pytest features/jbus/tests/test_main_fix_spec.py -q
```

It prints `13 passed` in about two minutes, with each TLC test under 25 s on a desk, and skips the TLC runs where no Java runs TLC.
`features/jbus/tests/test_main_fix_crashes.py` stops the real pass at each write the canaries' traces name and runs the next one.
The bare TLC command is in `features/jbus/spec/MainFix.md`, "Check the rules of main's fix"; run it in a copy of the folder.

- **Bounds:** `MainFix.cfg` is a pass that dies and no other fault (`World = {}`), `MaxTip = 3`, all three nightlies watched, 329948 distinct states, counted by its `VIEW View`, which tells each variable apart only by what a later step or a rule can still read of it.
  Every rule holds too with `World = {"hand"}` (669004), `{"refuses"}` (1339244), `{"late"}` (1006483) and `{"blind"}` (586960).
- **The canaries**, each a fix of st-main-fix-crash-gaps (#1728) taken back: `Fault = "keep-first"` (the record before the line) breaks `RevertSaid`, `"no-known"` (no `reverts.known`) breaks `RevertKnown` with `"hand"`, and `"brief-first"` (the brief before its row) breaks `FiledWhole` with `"refuses"` and with `"late"`.
  `MainFix.cfg`'s comment keeps each trace, and the test's `CANARIES` checks each still breaks.
- **The findings:** none today; the test's `FIXED` holds each of the five that st-model-main-fix found, and `FINDINGS` is where a new one goes.
- **Assumptions:** one red, with no holders, `close`, `_withdraw` or stuck revert (`MainRed.tla` has them); no `_add_tip`; a queue that never refuses a brief; no first pass, no `NIGHTLY_GRACE`; no run with both shots and other failures; one scheduled workflow.
  The rest is in the README's "What the main-fix model leaves out".

## A real bug or a modeling error

A trace is a pass's writes, the one it died after, and what the next pass did.
Replay each write against the record's code in order; a step whose condition carries no quote is the world's (GitHub, a hand, time) or the pass's own place, and must be one the code can meet.
A write the code makes in another order is a modeling error, and the model is what gets fixed.
A new break, past `FINDINGS`, is a bug: tell it as the writes, the crash, and the half-filed state the next pass left.

## Change the model when the code changes on purpose

- A fix for a finding: move its row from the test's `FINDINGS` to `FIXED`, and give it a canary that takes the fix back.
- A new carrier: give it a variable whose comment quotes its writer, and steps in the code's order.
- Show a changed rule failing on a scratch break first (swap two writes in your own worktree, uncommitted, see the trace, `git restore` the file).

## The last upkeep

`/maintain-formal-verification-skill` ran at `228c1436c` (st-model-upkeep-run) and fixed two drifts in the model; neither broke a rule, and no new finding came of them:

- **The pass order:** a pass reads the nightlies, then judges the Mac and main, as `poll.first_half` runs `tellers` before `after-expedite`.
  The World fault `"blind"` is a pass with no world (no token, T3 Code or GitHub silent, the budget under its floor): it skips `watch.watch` and `reverts.macos`, which need one, and runs `culprits.judge` alone.
  `FiledWhole` now reads "by the next pass that runs every step": a blind pass launches nothing, and the next pass with a world queues the brief.
  The break: counting a blind pass as whole makes `FiledWhole` fail under `"blind"`.
- **The shots row is any nightly's:** every nightly's run may be its shots alone (`drawn_apart` runs on each), the Mac's only after a run that passed, and a nightly's day is taken only when both its row and the shots row are.

The row was then rebased onto st-model-sync, whose merge of main brought main to `8f4c21b6f`, and the upkeep diffed the covered code again from `228c1436c` to it: `watch.py` changed in #1724, in `left` and the words it keeps, which no step here stands for, so the sync commit moved there.

st-model-sync then merged main again, to `2fb4e2587`, and the row was rebased onto it; the upkeep diffed the covered code from `8f4c21b6f`: no covered file changed, so the sync commit moved there.

Then #1728 (st-main-fix-crash-gaps) fixed the five findings in `reverts.py` and `watch.py` and wrote its own model of them: `reverts.known` before the nightlies, `reverts-opening.json`, the line before the record, and the row before its brief.
The row merged main at `5f87506cc` and put the two drifts above on #1728's model: a blind pass skips `reverts.known` too, which needs the world, and `culprits.judge` still needs none.
Every rule holds in each world, `"blind"` among them, and each canary still breaks its rule, so the sync commit moved there.

On CI the merged model's TLC tests passed 120 s (`FiledWhole` with `"late"` was 10480668 states), so `MainFix.cfg` gained `VIEW View`, and `NextRun` takes a pass past a nightly's last run straight to its next step.
The view tells a nightly run kept as seen only as "passed" or seen, a pull request's run as seen, and a red run that aged unseen as late; it drops the tip and `clear` once main and its Mac are green again, `sight` between passes, and `before` after a pass that died.
The tla's comment above `RunView` says why no step and no rule reads what it drops, so every rule holds and each canary breaks as before, over a quarter to a tenth as many states.
A view that drops what a step still reads would hide a break: before you widen it, check that a canary still breaks.
