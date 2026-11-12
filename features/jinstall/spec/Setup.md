# What jstack leaves on a machine, as a TLA+ spec

`Setup.tla` models the records that say what to undo, as the code of main c49a8bd3c writes them, in three parts that change apart:

- The install, `jinstall/machine.py`: each path an install makes, and the records that undo it.
  - `~/.local/state/jstack/created` (D-092): uninstall's sweep removes the paths it names.
  - `repos` (D-093): uninstall drops the hooks of each repo it names.
  - `seeded` (D-094): uninstall removes each file it names while its bytes are unchanged.
  - The flock on HOME (D-095) lets one verb write at a time.
- The role mirror, `jroles/mirror.py` (D-078): an entry of a mirror home moves to `<name>.bak-<time>` and is linked to `~/.claude`'s, under the mirror's lock.
- An expert's webhook, `features/expert/when-an-expert-starts.md`:
  - `$E/home-id` (D-136): the thread that is the expert.
  - `$E/webhook` (D-137): the webhook kept, and the thread it posts into.
  - `$E/webhook.url` (D-138): the webhook's address.

A process or a turn can stop between any two steps, and the disk keeps what it wrote.
Each variable of a carrier, and each step, cites the code that writes it with a quote, with no line number.
`features/jinstall/tests/test_setup_spec.py` finds each quote once in its file.
It also runs TLC on `Setup.cfg`, on each rule alone, and on the canary.

## Check the rules

In a copy of this folder, since TLC writes `states/` where it runs:

```sh
cd features/jinstall/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -workers 1 -config Setup.cfg Setup.tla
```

TLC breaks no rule, over 411,730 distinct states.
Each rule alone, over the part it reads, which changes apart from the others:

| Rule | Part | Today's code |
|---|---|---|
| `UninstallComplete`: every path jstack made is recorded or not made | install | holds, 418 states |
| `RecordLevelsRecorded`: the record's folder and the levels above it are recorded | install | holds, 418 states |
| `MadePathsRecorded`: each path the install makes for its own use is recorded | install | holds, 418 states |
| `MirrorKept`: the mirror's own entry is at its name or in its backup | mirror | holds, 10 states |
| `OneWebhook`: an expert has at most one live webhook, and once a start has ended, its record names it | expert | holds |
| `UrlNamesWebhook`: once a start has ended, the address kept is the kept webhook's | expert | holds |

The canary, `Fault = "note-after"`, has `make_dirs` make a folder before it records it.
It breaks `MadePathsRecorded` and `UninstallComplete`, which today's code holds, at the folder (Begin, Make).

The expert has three canaries, each one fault of the text before expert-webhook-survives-a-stop put back:

| Fault | What it puts back | Breaks |
|---|---|---|
| `purge-own` | the purge deletes only the webhooks bound to this thread | `OneWebhook`, at Create |
| `record-first` | the record is written before the address, and a webhook with no address file is kept | `UrlNamesWebhook`, at Look |
| `no-mend` | a record that names another thread than its webhook's is kept as it is | `OneWebhook`, at Look |

## The findings

The brief expected the canary's order, make then note, to be today's.
It is not: `make_dirs`, `write_object`, `seed` and `add_repo` each write their record before the path.
`UninstallComplete` broke through `_note` itself, and both expert rules broke, in three ways.
Each is fixed now, and the model follows each fix.
Finding 1 is fixed by jinstall-note-records-its-folder, as it says.
Findings 2 to 4 are fixed by expert-webhook-survives-a-stop: step 4 of the expert's start now lists T3 Code's tasks on each start and compares them with the record.
It deletes every webhook of this expert that the record does not keep, writes the address before the record, deletes a kept webhook whose address file is missing, and writes the record before a takeover's call and mends a record whose thread is not the webhook's.
The expert's canaries above put each fault back.

1. **The record's own folder is made before a record names it.**
   Fixed: `_note` now builds the first missing level under a stage, `<level>.jstack-new`.
   It writes `created` in the stage, naming the record's folder and each level it made, and renames the stage into place, so the levels appear only with their record.
   A stop leaves only the stage, which the next `_note` builds on and the sweep removes.
   What the model found before the fix:
   `_note` makes `~/.local/state/jstack`, and any missing level above it, before it writes `created`.
   The trace is: Begin (a `make_dirs`), NoteMkdir, and the install stops.
   With no `created` file, the sweep returns at once, so uninstall leaves the folder.
   On a fresh HOME the stop also leaves `~/.local/state`, which the next `_note` finds there and never records.
   That one stays even after a later install completes.
   This one needs no stop at all:
   1. Begin `--setup` seeding a config on a HOME that has `~/.local/state`.
   2. NoteMkdir.
   3. NoteWrite, with nothing new to write.
   4. WriteRecord, the seeded line.
   5. Make.

   `_note(None)` writes no `created` when no line is new.
   So uninstall removes the seeded file and its record, and leaves `~/.local/state/jstack` empty.
   On this machine other paths filled `created` first, so the folder is covered.
   Found by an `op = None => RecordLevelsRecorded` run with `InstallDies` taken out.
2. **A takeover leaves a webhook no record names** (`OneWebhook`).
   1. Thread 1 starts the expert: it creates a webhook, and its turn stops before it keeps the id.
   2. Thread 2 starts the expert and finds no webhook kept.
   3. Its purge deletes only the tasks bound to thread 2, then it creates a second webhook.

   Two webhooks are now live, and the first still posts into thread 1.
   The orphan check of step 4 (`boundThreadId is this thread`) misses a task bound to the thread being taken over from.
3. **A stop between the record and the address loses the address for good** (`UrlNamesWebhook`).
   1. Thread 1 creates a webhook and keeps its id, and the turn stops before it writes `webhook.url`.
   2. The next start finds its own webhook kept and does nothing.

   The address can never be had again, so nothing outside the thread can ask the expert.
   A stop between the write of `webhook` and `jbus forget` instead leaves the address of the webhook that was deleted.
4. **A takeover that stops after the rebind leaves a record that names the wrong thread** (`OneWebhook`).
   1. Thread 2 takes over: `update_scheduled_task` binds the webhook to thread 2.
   2. The turn stops before the block that rewrites `webhook` as `<id> thread-2`.
   3. Thread 1 starts again and reads `<id> thread-1`, so it keeps the webhook.

   That webhook now posts into thread 2, and asks sent to the expert reach a thread that is no longer the expert.

## Draw the chart

```sh
S=../../skill-library/skills/statechart/scripts
cd features/jinstall/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec Setup.tla --config Setup.chart.cfg --also-config Setup.cfg \
    --title "Does an uninstall or an expert's takeover leave anything behind?"
```

It runs over 82,346 model states.
It writes `Setup-statechart/`, labelled by `Setup.map.py`: 22 chart states and 37 arrows, with no bug chart, in two regions:

- What an uninstall would leave.
- The expert's webhook.

`Setup.chart.cfg` leaves the mirror out, which breaks no rule, so the graph stays drawable.
`--also-config Setup.cfg` runs it with the mirror once more for the tables alone: its 411,730 states add 171 states and 1,308 arrows, and `states.tsv` and `arrows.tsv` list all 228 states and 1,668 arrows between them, each with its action and its count of model steps in each run.
Its `tlc/` folder holds TLC's output, which is not committed.

## What the model leaves out

- The temporary `<name>.<pid>.new` that `_beside` writes beside every record and file.
  A stop before its rename leaves it, unrecorded.
  It also keeps the record's folder from being empty, so the sweep keeps that folder.
- `.jroles-mirror.lock` in the main home and in each mirror: `open("a")` makes it, and nothing records or removes it.
  The `.bak-<time>` backups are kept for good by design, and no uninstall removes them.
- The rest of uninstall's order: it is one step here.
  It drops the kinds, then the repos, then sweeps, and a stop inside it leaves records that the next run reads again.
- A seeded file the user changed, which uninstall keeps on purpose.
- Uninstall removes each level above the record only when it is empty: the model takes them as empty.
- A HOME `alone` cannot open, where no lock is held.
- Of the expert:
  - a create that returns no address (T3 Connect off);
  - a webhook in another project;
  - the pin;
  - more than two threads and two webhooks;
  - two threads that start the expert at once: the model runs one start at a time.
