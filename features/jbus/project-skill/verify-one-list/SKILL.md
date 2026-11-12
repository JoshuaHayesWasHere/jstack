---
name: verify-one-list
description: Check OneList.tla, the one list of what waits on the user and the marks of what a home has read; use when changing gates, questions.json, waiting-on-user.json, the streaks, the budget hold, read-seen or merge-seen.
paths: "features/jbus/spec/OneList.tla, features/jbus/src/jbus/__init__.py, features/jbus/src/jbus/questions.py, features/jbus/src/jbus/waiting.py, features/jbus/src/jbus/mirror.py, features/jbus/src/jbus/alert.py, features/jbus/src/jbus/merge.py, features/jbus/src/jbus/children.py, features/jbus/src/jbus/health.py, features/jbus/src/jbus/signin.py, features/jbus/src/jbus/budgethold.py, features/jbus/src/jbus/homestatus.py, features/jmerge/src/jmerge/cli.py, features/home/templates/gates.md, features/home/skills/handoff/SKILL.md, features/home/skills/home/when-a-home-starts.md, features/home/skills/home/merging-a-pull-request-that-is-ready.md"
---

# verify-one-list

`features/jbus/spec/OneList.tla` follows what reaches the user and what a home has read, in three scenes that share only the project's passes and `streaks.lock`.
The gates scene is one gate: the home writes it in gates.md, a thread pipes it to `jbus gate`, a pass closes its question by silence or by the home's Status line, the user answers, and the handoff moves gates.md aside.
The alerts scene is the streaks of streaks.json (jmerge's, a home's stall from before, the sign-in, a full disk), the budget hold and the kinds a pass rebuilds into waiting-on-user.json, with a pass and `jbus alarm` taking the lock in turn.
The marks scene is merge.log with merge-seen, and a brief's Result headings with read-seen.
`World` picks the acts outside the code a run lets happen ("closes", "cuts", "by-home"), `Fault` adds a canary, and `MarkBy` picks how merge-seen marks.

The rules, each with its harm, and today's verdict:

- **`ListIsTrue`** (breaks): an item is on the list exactly while its cause holds, once the cause stays.
  Broken by "closes", a closed project's jmerge alert stays open for ever, and by "by-home", a question stays open after you answered its twin.
- **`AnsweredLeaves`** (breaks): once your answer or the default by silence settles a gate, no open gate or question of it stays.
  Broken by "by-home", the handoff asks the home's gate again under the catch-all's key.
- **`ReadOnce`** (breaks): the merging block shows each merge line once, and merge-seen counts no line it did not show.
  Broken by "cuts", a cut of merge.log leaves merge-seen counting a line no block showed.

## The record

Model: `features/jbus/spec/OneList.tla`
Sync: `2fb4e2587489ad3fbebf71561ac648801edb710f`
Covers:
- `features/jbus/src/jbus/__init__.py`: `load`
- `features/jbus/src/jbus/questions.py`: `ask`, `silent`, `closed_in_files`, `Question`, `Answer`, `STEPS`
- `features/jbus/src/jbus/waiting.py`: `gates`, `keep`, `_rewrite`
- `features/jbus/src/jbus/mirror.py`: `gate_key`
- `features/jbus/src/jbus/alert.py`: `LOCK`, `jmerge`, `_keep`, `failed`, `ok`, `raise_`, `end`, `retire`
- `features/jbus/src/jbus/merge.py`: `_judged`
- `features/jbus/src/jbus/children.py`: `watch`, `_stall`
- `features/jbus/src/jbus/health.py`: `disks`, `watch`
- `features/jbus/src/jbus/signin.py`: `remind`
- `features/jbus/src/jbus/budgethold.py`: `hold`
- `features/jbus/src/jbus/homestatus.py`: `_to_read`
- `features/jmerge/src/jmerge/cli.py`: `_merging`
- `features/home/templates/gates.md`: `Status`
- `features/home/skills/handoff/SKILL.md`: `gates-moved.md`, `home-uncategorized`
- `features/home/skills/home/when-a-home-starts.md`: `read-seen`
- `features/home/skills/home/merging-a-pull-request-that-is-ready.md`: `seen`, `news`

At the sync commit, main's tip when this branch took main in, the model was read against these.
`waiting.gates` skips a file gate whose Status is not open or whose key a question holds, and lists each question with no answer, as `FileGate` and `GateListed` say.
`alert.failed` counts under the lock and returns the line only from `After` on, `alert.ok` drops a streak that had not alerted and returns the recovered line for one that had, and `children.watch` returns at once with no threads and otherwise retires every stall key, as `Streaked` says.
`budgethold.hold` keeps the hold when the budget was not read, unlinks it when not held and writes it when held, as `PassSee` and `PassBlind` say.
`signin.remind` raises the sign-in alert while a line is due and retires it once none is, and `health.watch` opens and closes the disk incident, as `SignIn` and `LookRead` say.
`homestatus._to_read` marks every heading read on the first call and shows none, as `FirstMark` says.
The merging block takes the line count as the mark where there is none, resets a mark past the count to 0, shows the lines past it and writes the count, as `Read` says.
No covered file changed between the model's commit (9e45ddde1, #1708) and the sync, and `features/jbus/tests/test_one_list_spec.py` passed there.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new kind of waiting-on-user.json, a new streak key, a new writer of questions.json, gates.md, read-seen or merge-seen, or a cfg or the spec.
The test also fails when a quote of the spec no longer stands once in its file: move the quote with the code, then rerun.

## Run it

```sh
uv run pytest features/jbus/tests/test_one_list_spec.py -q
```

It finds each quote of the spec once, checks each ledger row is a variable, and runs TLC on today's world, each act alone, no act, `MarkBy = "line"` and each canary, in under a minute; the TLC runs skip where no Java runs TLC.
The bare TLC command and the rules are in `features/jbus/spec/README.md`, "The one list, as a TLA+ spec"; run TLC in a copy of the folder, since it writes `states/` where it runs.

- **Bounds:** `After = 2`, `MaxLines = 2`, two Result headings; `OneList.cfg` with all three acts stops at `ReadOnce` at 1083 distinct states, and `OneList.chart.cfg` draws the gates scene alone.
- **The faults:** `stale-streak` is the canary that breaks `ListIsTrue` with no act; `mark-count` is the canary that breaks `ReadOnce` under `MarkBy = "line"` where merge.log is cut.
- **Assumptions:** no time (the `LASTING` span, a `once` alert's end, the hold's ten minutes, the sign-in's week); the nine kinds other than `gate` are one item; jmerge's streak stands for every key of a project; the rest is in the README's "What the one-list model leaves out".

## A real bug or a modeling error

Each step of a trace quotes the code that takes it.
Open each quote at its file and check the code still does what the step does; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the story of the item on your list or the line a home was shown, and leave the rule as it is.

## Change the model when the code changes on purpose

- A fix that changes when an item is listed or retired: change the step, rerun every cfg, and move the README's verdicts and the cfg's comment with what TLC prints.
- A new carrier of the ledger's OneList rows: give it a variable whose comment names the row and quotes its writer, and add the row to the test's `ROWS`.

## Drift at the sync commit

The pass's gate work is written in the wrong order.
The spec's comment on `Silenced` and `Closed` puts silence first and the home's Status line second, "in the order poll runs it", but `questions.STEPS` runs `closed_in_files` at before-watch 20 and `silent` at before-watch 30.
`PassSee` composes `Closed(Silenced(q))`, and since `closed_in_files` also closes a question silence closed (`_open`), a pass ends in the same state either way, so no verdict changes; the comment and the order of the composition are what st-model-upkeep-run should fix.
The README and spec say "main aa5469d97"; the one covered change from there to the model's commit, 23f42940f, moved the import of `stacked` in `cli.py` and changed no step.
