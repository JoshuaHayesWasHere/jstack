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

Today's code breaks them on seven acts, recorded as findings: `stall.twice`'s page and the clock's stall are lost (`NoTellLost`); failover's ask, the second target's body, a word, the account question and a skill's notice can go twice (`NoTellTwice`).
`TellOnce.cfg`'s comment keeps each trace, and the test checks that each still breaks.
The other six acts (held, items, expedite, cancelled, closed, revert) hold both.

## The record

Model: `features/jbus/spec/TellOnce.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
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

At the sync commit `Code(c)` and `Guard(c)` were read against the code of the acts twice, clock, held, blocking, owed, account, reload, revert, cancelled and closed, and each write order and guard matched; items, word and expedite were checked by their quotes, not read in depth.
The only change to these files since the model's main (aa5469d97) was 23f42940f, which moved imports and changed no act.
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
The bare TLC command, with `-continue` so it reports all seven breaks and not only the first, is in `features/jbus/spec/README.md`, "Check the rules of act once"; run it in a copy of the folder.

- **Bounds:** the 13 acts of `Carriers`, `Passes = 2`, `Fault = "none"`, 1676 distinct states; one behavior follows one act, so the acts' states add up and do not multiply.
- **The canaries:** `Fault = "mark-first"` writes the marks before the act and breaks `NoTellLost` on every act; `Fault = "no-mark"` reads no mark and breaks `NoTellTwice` on every act.
- **Assumptions:** safety only, so an act a guard keeps from running for ever passes; a clock wait never returns to a kind it had; `Box.send` writing a finding's key before its line is modeled for the clock's stall and `stall.twice` only.
  The rest is in the README's "What the act-once model leaves out".

## A real bug or a modeling error

A trace is one act's writes and a pass that dies between two of them.
Check its order against the act's code: the writes must come in `Code(c)`'s order, the guard must read the marks `Guard(c)` names, and a receiver absorbs a repeat only under a key the code sends (T3 Code's `clientRequestId`, a question's key, GitHub's state).
A write the code makes in another order is a modeling error, and `Code(c)` is what gets fixed.
A new break on an act that held is a bug: tell it as the act, the write the pass died after, and what the next pass did again or never did.

## Change the model when the code changes on purpose

- A fix for one of the seven: the test's expected breaks fail until the cfg's comment and the test's list drop it.
- A new act: add it to `Carriers` with its `Code`, `Guard` and `Absorbs` rows and a variable for each carrier it writes, quoted.
- Show a changed rule failing on a scratch break first (swap two writes of one act in your own worktree, uncommitted, see the trace, `git restore` the file).

## Drift at the sync commit

`/maintain-formal-verification-skill` fixes it.

- **`clock.held`'s lift is not modeled:** a hold that lifts sets `woke` and only finds the run again, sending nothing to T3 Code; the model has no such branch, and the README's "leaves out" does not name it.
