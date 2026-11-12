---
name: verify-setup
description: Check Setup.tla, the records that undo an install, the role mirror and an expert's webhook; use when changing jinstall's records, uninstall's sweep, jroles' mirror or an expert's start.
paths: "features/jinstall/spec/Setup.tla, features/jinstall/src/jinstall/machine.py, features/jinstall/src/jinstall/__main__.py, features/jroles/src/jroles/mirror.py, features/expert/when-an-expert-starts.md"
---

# verify-setup

`features/jinstall/spec/Setup.tla` follows what jstack leaves on a machine and the records that undo it, in three parts that change apart.
The install part is `jinstall/machine.py`'s `created`, `repos` and `seeded` records, each written by `_note` or its writer before the path it names, under HOME's lock, and uninstall as one step.
The mirror part is one entry of a role mirror moved to its `.bak-<time>` backup and linked to `~/.claude`'s, under the mirror's lock.
The expert part is steps 3 and 4 of `features/expert/when-an-expert-starts.md`: `home-id`, the kept `webhook`, and `webhook.url`, across two threads that can each take the expert over.
A process or a turn can stop between any two steps, and the disk keeps what it wrote.
`Parts` picks the parts a run follows, and `Fault = "note-after"` changes one thing of today's code.

The rules, each with its harm, and today's verdict:

- **`UninstallComplete`** (breaks): every path jstack made is recorded or not made.
  Broken, an uninstall leaves the record's own folder behind.
- **`RecordLevelsRecorded`** (breaks): the record's folder and the levels above it are recorded.
  `_note` makes `~/.local/state/jstack`, and any missing level above it, before it writes `created`.
- **`MadePathsRecorded`** (holds): each path the install makes for its own use is recorded first.
- **`MirrorKept`** (holds): the mirror's own entry is at its name or in its backup.
- **`OneWebhook`** (breaks): an expert has at most one live webhook, and once a start has ended, its record names it.
  Broken, a takeover that stopped leaves a webhook no record names, or a record that names the wrong thread.
- **`UrlNamesWebhook`** (breaks): once a start has ended, the address kept is the kept webhook's.
  Broken, a stop between the record and the address loses the address for good.

## The record

Model: `features/jinstall/spec/Setup.tla`
Sync: `bc13624077653b4458133d4486544d863a602141`
Covers:
- `features/jinstall/src/jinstall/machine.py`: `Machine.alone`, `Machine._note`, `Machine._write_record`, `Machine.make_dirs`, `Machine.add_repo`, `Machine.forget_repos`, `Machine._write_seeded`, `Machine.seed`, `Machine.sweep`, `_levels`, `_beside`
- `features/jinstall/src/jinstall/__main__.py`: `setup`, `set_up_repo`, `uninstall`, `act`
- `features/jroles/src/jroles/mirror.py`: `plan`, `apply`, `run`, `_backup`, `LOCK`
- `features/expert/when-an-expert-starts.md`: `home-id`, `webhook.url`, `update_scheduled_task`, `list_scheduled_tasks`, `delete_scheduled_task`, `schedule_task`, `boundThreadId`

At the sync commit, main's tip when this branch took main in, the model was read against these.
`_note` lists the missing levels above the record, makes the record's folder with `mkdir(parents=True)`, and writes the record only where a line is new, the order of `NoteMkdir` then `NoteWrite`.
`make_dirs` calls `_note(level)` before `level.mkdir`, `seed` writes the seeded record through `_write_seeded` before it writes the file, and `add_repo` calls `_note(None)` and writes `repos` before `install` makes the hooks, as `Order` says.
`act` holds `alone`'s flock on HOME for every verb that writes, and `uninstall` runs the kinds, then `forget_repos`, then `sweep`, which returns at once where no `created` file is.
`run` takes the mirror's lock and then the main home's, `plan` makes a step `backup` where the entry is there, and `apply` renames it to `_backup`'s name before `symlink_to`, as `Rename` then `Link`.
The expert's start writes `home-id`, reads the kept webhook into create, keep or take, takes over with `update_scheduled_task` and checks `boundThreadId` in `list_scheduled_tasks`'s reply, deletes on `not taken`, purges a task bound to this thread before `schedule_task`, and then writes `webhook`, forgets `webhook.url`, and writes the address, the order of `KeepId`, `ForgetUrl` and `KeepUrl`.
No covered file changed between the model's commit (bc1362407, #1716) and the sync, which is that commit, and `features/jinstall/tests/test_setup_spec.py` passed there (11 passed).
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new writer of `created`, `repos` or `seeded`, a new step of uninstall, a new path the install makes, the mirror's lock or plan, the expert's webhook blocks, or a cfg or the spec.
The test also fails when a quote of the spec no longer stands once in its file: move the quote with the code, then rerun.

## Run it

```sh
uv run pytest features/jinstall/tests/test_setup_spec.py -q
```

It finds each quote of the spec once in its file, then runs TLC on `Setup.cfg`, on each rule alone over the part it reads, and on the canary, in seconds, and skips the TLC runs where no Java runs TLC.
The bare TLC command, the table of rules and verdicts, and the four findings are in `features/jinstall/spec/README.md`; run TLC in a copy of the folder, since it writes `states/` where it runs.

- **Bounds:** `MaxId = 2` webhooks, two threads, and one mirror entry; `Setup.cfg` follows all three parts and stops at the first break, `UninstallComplete`, after 15 distinct states; `MadePathsRecorded` alone holds over 609 states and `MirrorKept` over 10.
- **The canary:** `Fault = "note-after"` has `make_dirs` make a folder before it records it, and breaks `MadePathsRecorded`, which today's code holds.
- **Assumptions:** uninstall is one step; each level above the record is empty when uninstall reaches it; the `_beside` temporary file, the mirror's `.jroles-mirror.lock` and a seeded file the user changed are out; the expert has no create without an address, no webhook in another project and no pin; the rest is in the README's "What the model leaves out".

## A real bug or a modeling error

Each step of a trace quotes the code or the block that takes it.
Open each quote at its file and check the order of writes still is the step's; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the run's story (an install and where it stopped, or two threads and their calls), and leave the rule as it is.

## Change the model when the code changes on purpose

- A fix that records the record's folder before it is made: change `NoteMkdir` and `NoteWrite`, rerun every rule alone, and move the README's verdict table and the cfg's comment with what TLC prints.
- A new record or a new path the install makes: give it a variable or a member of `disk` whose comment quotes its writer, and add it to `Covered`.
- A change to the expert's blocks: move the step and its quote with the block, and rerun `OneWebhook` and `UrlNamesWebhook`.

## Drift at the sync commit

None found in the steps.
`seed` calls `make_dirs(path.parent)` between the seeded record and the file, which the model folds into `seed`'s `make` step, so a missing parent's own `_note` steps are not followed there; `MadePathsRecorded` is the rule they would touch, and `make_dirs` notes each level before it makes it.
The README and spec say "the code of main c49a8bd3c"; no covered file changed from there to the sync.
