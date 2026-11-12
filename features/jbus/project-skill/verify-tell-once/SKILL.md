---
name: verify-tell-once
description: Check TellOnce.tla, jbus's act-once marks when a pass dies; use when changing how a pass sends, posts or acts once and marks it.
paths: "features/jbus/spec/TellOnce.tla, features/jbus/src/jbus/wake.py, features/jbus/src/jbus/clock.py, features/jbus/src/jbus/stall.py, features/jbus/src/jbus/outbox.py, features/jbus/src/jbus/item.py, features/jbus/src/jbus/word.py, features/jbus/src/jbus/owed.py, features/jbus/src/jbus/failover.py, features/jbus/src/jbus/expedite.py, features/jbus/src/jbus/cancelled.py, features/jbus/src/jbus/project.py, features/jbus/src/jbus/mainmoved.py, features/jbus/src/jbus/questions.py, features/jbus/src/jbus/culprits.py, features/jbus/src/jbus/rebase.py, features/jbus/src/jbus/reload.py, features/jbus/src/jbus/queue.py"
---

# verify-tell-once

`features/jbus/spec/TellOnce.tla` follows each of jbus's act-once steps: a pass does an act once and keeps the mark that it did in a file of its own, in a step of its own, and a pass can die between any two writes.
Each of the 21 carriers of the st-state-ledger's machine TellOnce is one variable, with the code that writes it quoted beside it.
Each act is three tables: `Code(c)`, the order its pass writes in; `Guard(c)`, the marks it reads first; `Absorbs(c)`, whether its receiver takes a repeat as the same act.

The rules, each with its harm:

- **`NoTellTwice`:** the receiver takes each act once.
  Broken, a crew, a home or GitHub gets the same message, body or rerun twice.
- **`NoTellLost`:** between passes, an act still owed whose mark is written was taken.
  Broken, a tell is marked done and nobody ever got it.

Today's code holds both on all fourteen acts.
st-fix-tell-once (#1725) closed the eight it broke: `stall.twice`'s page, the clock's stall and the finding of a hold only the user's accept lifts (`heldlift`) were lost (`NoTellLost`); failover's ask, the second target's body, a word, the account question and a skill's notice could go twice (`NoTellTwice`).
`TellOnce.cfg`'s comment names each fix, and the test checks that no act breaks.

## The record

Model: `features/jbus/spec/TellOnce.tla`
Sync: `c1ec2615c986b1bfe12f07cffc656002c77934af`
Covers:
- `features/jbus/src/jbus/wake.py`: `Box.send`, `Box.mark`, `Box.flush_blocking`, `_post_blocking`
- `features/jbus/src/jbus/clock.py`: `tick`, `_send`, `_act`, `_home`, `held`, `HELD_FILE`
- `features/jbus/src/jbus/stall.py`: `twice`
- `features/jbus/src/jbus/outbox.py`: `send`, `_log`, `_last`
- `features/jbus/src/jbus/item.py`: `write`, `COUNTER`
- `features/jbus/src/jbus/word.py`: `post`, `_change`, `deliver`
- `features/jbus/src/jbus/owed.py`: `taken`, `quoted`
- `features/jbus/src/jbus/failover.py`: `carry_lapse`, `handle`
- `features/jbus/src/jbus/expedite.py`: `tell`
- `features/jbus/src/jbus/cancelled.py`: `rerun`, `_one`
- `features/jbus/src/jbus/project.py`: `close`
- `features/jbus/src/jbus/mainmoved.py`: `account`
- `features/jbus/src/jbus/questions.py`: `park`
- `features/jbus/src/jbus/culprits.py`: `tell`
- `features/jbus/src/jbus/rebase.py`: `once`, `mark`
- `features/jbus/src/jbus/reload.py`: `tell`, `_told`
- `features/jbus/src/jbus/queue.py`: `hold`

At the sync commit `Code(c)` and `Guard(c)` were read against the code of every act, and each write order and guard matched.
For the three read last: items appends its line, then `items-next.json`, guarded by the fold's `proposed already` (`item._put`); word posts, then `_change` writes `sent_at`, guarded by `if one.sent_at` (`word.deliver`); expedite sends, logs and marks through `rebase.once`, then writes `expedite.json` at the end of `tell`, guarded by the mark or `told`.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, adds an act a pass does once and marks, or changes which file holds an act's mark or when it is written.
`features/jbus/tests/test_tell_once_spec.py` fails when a quote no longer stands once in its file, or a carrier of the ledger has no variable.

## Run it

```sh
uv run pytest features/jbus/tests/test_tell_once_spec.py -q
```

It prints `6 passed` in about five seconds, and skips where no Java runs TLC.
The bare TLC command, with `-continue` so a break reports every act it breaks on and not only the first, is in `features/jbus/spec/TellOnce.md`, "Check the rules of act once"; run it in a copy of the folder.

- **Bounds:** the 14 acts of `Carriers`, `Passes = 2`, `Fault = "none"`, 1496 distinct states; one behavior follows one act, so the acts' states add up and do not multiply.
- **The canaries:** `Fault = "mark-first"` writes the marks before the act and breaks `NoTellLost` on every act; `Fault = "no-mark"` reads no mark and breaks `NoTellTwice` on every act.
- **Assumptions:** safety only, so an act a guard keeps from running for ever passes; a clock wait never returns to a kind it had; `Box.send` keeping a finding's line with its key in `unlogged.json` is modeled for the clock's stall, `heldlift` and `stall.twice` only.
  The rest is in the README's "What the act-once model leaves out".

## A real bug or a modeling error

A trace is one act's writes and a pass that dies between two of them.
Check its order against the act's code: the writes must come in `Code(c)`'s order, the guard must read the marks `Guard(c)` names, and a receiver absorbs a repeat only under a key the code sends (T3 Code's `clientRequestId`, a question's key, GitHub's state).
A write the code makes in another order is a modeling error, and `Code(c)` is what gets fixed.
A new break on an act that held is a bug: tell it as the act, the write the pass died after, and what the next pass did again or never did.

## Change the model when the code changes on purpose

- A change that breaks an act: the test fails on `TODAY`; a break the code means to keep goes in the cfg's comment and the test's `TODAY`.
- A new act: add it to `Carriers` with its `Code`, `Guard` and `Absorbs` rows and a variable for each carrier it writes, quoted.
- Show a changed rule failing on a scratch break first (swap two writes of one act in your own worktree, uncommitted, see the trace, `git restore` the file).

## The last upkeep

`/maintain-formal-verification-skill` ran at `228c1436c` (st-model-upkeep-run) and fixed one drift in the model:

- **`clock.held`'s lift branch** was not modeled: a hold only the user's accept lifts sets `woke`, logs a finding through `run.find` and sends nothing to T3 Code.
  It is the act `heldlift`, `<<"key", "act", "record">>`, guarded by `woke` and the finding's key.
  TLC finds it breaks `NoTellLost` (bug-8): `Box.send` writes the key, the pass dies before the event line, and the next pass finds the key, logs nothing and writes `woke`, so the user is never told the hold is theirs.
  That is the clock's stall's cause, `Box.send`'s key-first write, which st-fix-tell-once (#1725) fixes in `wake.py`; once it merges, `heldlift` should hold and leave `TODAY`.

The row was then rebased onto st-model-sync, whose merge of main brought main to `8f4c21b6f`, and the upkeep diffed the covered code again from `228c1436c` to it: `queue.py` changed in #1726, in `order` and the new `lifted`, not in `hold`, so the sync commit moved there.

st-model-sync then merged main again, to `2fb4e2587`, and the row was rebased onto it; the upkeep diffed the covered code from `8f4c21b6f`: `clock.py` changed in #1736: a thread at work on a code no crew clears (`aged.BOUNDS`) no longer keeps a hold from waking its home, which decides when `held` wakes and not how it tells; this model has no thread at work on a hold, so the sync commit moved there.

st-model-sync then merged main to `631810e72`, which carried st-fix-tell-once (#1725): it rewrote the model with the code, and `heldlift` holds as forecast, so `TODAY` is empty.
The upkeep diffed the covered code from `2fb4e2587` to it.
Every change but #1725's and #1788's leaves the acts' write orders as modeled: #1752's `rebase.retell` tells again through `rebase.once` under a key of the main tip, like `revert`, and #1777's `waits` carry-on is marked in `sent.json` once T3 Code took it, like `owed`.

The row then merged main at `c1ec2615c`, and the upkeep diffed the covered code from `631810e72`: #1703 changed `stall.twice`, which keeps the pin, hold, page and `held_at` in the model's order and holds at the third failed head, or the second whose logs name no test; at a second head whose logs name failed tests it writes `told` in `fails.json` and acts nothing itself, and `rebase.github` tells the crew under its own box key, as the model's `revert` does.

## Drift at the sync commit

`/maintain-formal-verification-skill` fixes it.

- **`cancelled.unqueue` (#1788) is not modeled:** it keeps `queued.json`'s record before it asks GitHub anything, runs each stuck run again with `gh run rerun`, keeps the record after each rerun GitHub takes, and logs once through `run.find` under `queued|<slug>|<head12>`.
  A pass that dies between a rerun and its keep runs that run again; GitHub refuses a rerun of a run it has not ended, which absorbs the repeat only while the new attempt runs.
