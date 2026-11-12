---
name: verify-thread-life
description: Rerun TLC on ThreadLife.tla, the model of one crew thread from jbus's launch record to its archive or its home told, and read what it finds. Use on any change to the launch in `jbus/dispatch.py` (`Turns.take`, `settle_lost`), `jbus/crewthread.py`, `threads.resume`, `_stopped` or `settle`, the liveness of `jbus/live.py`, `leftover.tell`, or the stall ladder of `jbus/children.py`.
---

# verify-thread-life

`features/jbus/spec/ThreadLife.tla` follows one crew thread of one row: the launch record a pass writes, the words `live.py` gives the thread's turn, the carry-ons `threads.resume` sends, and its end, put away with its scratch cleared (`threads.settle`) or the row its home's because jbus told the home.
Each condition of a step names its file and quotes the code, with no line number.

The rules, each with its harm:

- **`ThreadEnds`:** every thread jbus holds is archived in the end, or its home was told the row is the home's (or, with no home thread, `leftover.json` made it yours).
  Broken, a crew thread hangs with nobody told.
- **`LineFollows`:** the brief's `Thread:` line names the crew thread jbus holds (`crewthread.move`, or the next pass's `crewthread.repair`).
  Broken, a word for the crew goes to no thread or the wrong one.
- **`ScratchGoes`:** a thread put away has its scratch cleared.
- **`CarryOnsBounded`:** jbus sends a thread at most two carry-ons.
- **`ArchivesFinished`:** jbus archives only a finished slug's thread, once its turn is over.

## The record

Model: `features/jbus/spec/ThreadLife.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/jbus/src/jbus/dispatch.py`: `Turns.take`, `settle_lost`, `scratch`
- `features/jbus/src/jbus/crewthread.py`: `move`, `repair`, `crew`, `_answer`
- `features/jbus/src/jbus/threads.py`: `resume`, `_stopped`, `settle`, `held`, `shut`, `finished`, `CARRY_ONS`, `STOPPED`, `OWES_PULL`
- `features/jbus/src/jbus/live.py`: `judge`, `QUIET_MINUTES`, `HUNG_MINUTES`, `LIVENESS`
- `features/jbus/src/jbus/watch.py`: `ENDED`
- `features/jbus/src/jbus/leftover.py`: `tell`, `his`, `NO_HOME`
- `features/jbus/src/jbus/children.py`: `watch`, `_stall`, `_act`

At the sync commit the model was read against these: the launch's write order (intent, the call, then the launch and `crewthread.move`), a refused and a dropped launch, the adopt, retry and gate branches of `settle_lost`, `resume`'s guards, key, carry-on count and its owes-pull tell sent once, `crew()`'s fallback to the last launch, `_stopped`, and the settle-or-archive split.
The only change to these files since the model's main (21112eba8) was 23f42940f, which moved imports and changed no step.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, or a new place that writes a launch record, a brief's `Thread:` line, `leftover.json`, or archives or settles a crew thread.
`features/jbus/tests/test_spec_quotes.py` fails when a quote of the spec no longer stands once in its file: move the quote with the code, then rerun.

## Run it

```sh
uv run pytest features/jbus/tests/test_thread_life_spec.py -q
```

It prints `3 passed` in about ten seconds, and skips where no Java runs TLC.
The bare TLC command is in `features/jbus/spec/README.md`, "Check the rules of the thread"; run it in a copy of the folder, since TLC writes `states/` where it runs.

- **Bounds:** one thread of one row, `CarryOns = 2`, `Drop = "none"`, 45694 distinct states.
- **The canaries:** `Drop = "ladder"` takes the stall ladder out and `ThreadEnds` breaks; `Drop = "repair"` takes the next pass's repair out and `LineFollows` breaks.
  Each runs on a cfg with its own rule alone.
- **Assumptions:** the home thread is there and quiet in the end; one instance, no failover, no reviewers; no lost launch the lookup misses; no settled thread a message wakes, no removed row, no `MERGED` message; the turns and Results T3 Code reports are folded as the spec says beside each variable.
  The rest is in the README's "What the thread model leaves out".

## A real bug or a modeling error

Each step of a trace quotes the code that lets it happen.
Open each quote at its file and check that the code still guards the step as the quote says, in that order; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the thread's story in the code's words (launch, turn, carry-on, tell), and leave the rule as it is.

## Change the model when the code changes on purpose

- A new carry-on, a new way the home is told, or a new end of a thread: give it a step with its quote, rerun, and say in the README what it changes.
- A rule that changes: show it failing on a scratch break first (take the guard out in your own worktree, uncommitted, see the trace, `git restore` the file).

## Drift at the sync commit

`/maintain-formal-verification-skill` fixes it; it breaks no rule as modeled.

- **`ResumeGuard` asks `~told`, and `threads.resume` reads no such thing.**
  `resume` checks neither `leftover.json` nor whether the home was told, so after a leftover from a hung turn with no Result the code still carries on a turn that later fails, where the model blocks it.
  The model is stricter than the code here.
