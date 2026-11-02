# The telemetry store

`jbus telemetry` compiles the records jbus keeps for every project into one SQLite file, `~/.local/state/jbus/telemetry.sqlite`.
The file keeps every row forever, and its views give the KPIs that the week audit's scorecard counted by hand.
It costs no call to GitHub and runs no service: each pass of jbus brings it up to date.

## What it holds

The store has one table for each record file of each project, with a `project` column:

| Table | Source | One row is |
|---|---|---|
| `events` | `events.jsonl` | an event jbus logged, keyed by the id `jbus events` gives it |
| `acts` | `acts.jsonl` | an act: a go, hold, word, answer, withdraw or remove |
| `items` | `items.jsonl` | a work item's record |
| `transitions` | `transitions.jsonl` | a row's move from one status to another |
| `outbox` | `outbox.jsonl` | a message jbus sent or held |
| `ci_jobs` | `ci.jsonl` | a job of a GitHub Actions run, for a project whose table says `ci_report = true` |
| `merges` | the home's `merge.log` | a line `jmerge` logged: its verb, its pull request, a merge's slug and a wait's label |
| `questions` | `questions.json` | a gate and its answer |
| `queue` | `queue.json` | a row of the queue, with its approval's times |
| `merged` | `merged.json` | a merged pull request of a row |
| `ci_prs` | `ci-prs.jsonl` | a pull request the CI ledger keeps |
| `brief_versions` | `brief-versions.jsonl` | a change of a stored brief's sha, or its removal (no sha) |
| `row_pulls` | `row-pulls.jsonl` | a pull request a row had, the first time a pass saw it open, and again merged |
| `runs` | `runs.jsonl` | a completed attempt of a workflow run, of every project |
| `spend_days` | `spend.jsonl` | a project's Claude spend of one local day (`spent_on`), in units, tokens and units by kind |
| `spend_rows` | `spend-rows.jsonl` | a day's spend of one role and row, by the title jbus gave the thread |
| `word_sends` | `word-sends.json` | the thread a carried word went to and when, or that it still waits |
| `passes` | the machine's `passes.jsonl` | a pass of jbus: its start and its seconds, under the project `''` |
| `messages` | T3 Code's store, read only | a message of a T3 Code thread, the user's or the assistant's, keyed by its id |

Each time is in UTC, written `YYYY-MM-DDTHH:MM:SS.ffffffZ`, so that text order is time order.
Each table also has `day`, the local date of its main time in the zone that `jsettings` gives.
`builds` records each build: when, how long in milliseconds, the bytes it read and the rows it added.

`messages` reads T3 Code's `statev2.sqlite` on from the last message it read.
Its `project` is the jbus project of the thread, or T3 Code's own id of a project jbus does not know.
A user's message has a `kind`: `text`, `command`, `answer`, `resume`, or `dropped` for a text that T3 Code or an agent put in the user's turn.

No table holds the text of a message.
A row keeps ids, times, counts and labels, and in place of each text, its length in a column that ends `_len`, such as `acts.words_len`.
`acts.checked` says whether jbus read the act's words in T3 Code itself.
What the user said stays in T3 Code's store.
The file is readable by you alone.

## The records jbus keeps for the store

Four logs keep what jbus's snapshots overwrite, each written from what jbus already holds, so none costs a call to GitHub (`jbus.history`, `jbus.spent`):

- `brief-versions.jsonl`: the queue's one writer of a stored brief adds a line each time the brief's sha changes, and keeps each version's text once in `brief-versions/<sha>.md` beside it, out of the store.
- `row-pulls.jsonl`: a pass adds a line for each pull request it sees under a row's slug, once open and once merged.
- `runs.jsonl`: the pass's list of the repo's last 40 workflow runs, which it asks for already, adds each completed attempt once.
  An attempt that ends and is rerun between two passes is not seen.
- `spend.jsonl` and `spend-rows.jsonl`: once a pass, a chore reads T3 Code's store for each local day that ended six hours ago and is not kept yet, and keeps one line for the day and one for each role and row.
  The first time, it keeps the last 30 days.

A writer reads its log before it adds, and adds no line whose key the log holds, so each log only grows and holds each line once.

## The audit's data faults

The week audit could not answer six questions from the records it had.
Each now has a query:

| Fault | Query |
|---|---|
| F1, no brief history | `SELECT slug, launched_at, sha, changed_after FROM brief_at_launch` |
| F2, the latest CI attempt only | `SELECT project, run, attempts, first_fail_attempt, first_fail_at, last_conclusion FROM run_attempts WHERE attempts > 1` |
| F3, one pull request a row | `SELECT project, slug, group_concat(DISTINCT number) FROM row_pulls GROUP BY project, slug` |
| F4, carried words missing | `SELECT project, word, kept_at, said_in, thread, sent_at, waiting FROM carried_words` |
| F5, no tokens per row | `SELECT spent_on, role, slug, units FROM spend_rows WHERE slug IS NOT NULL` |
| F8, spend stored nowhere | `SELECT project, spent_on, units, runs FROM spend_days` |

F5's spend is Claude's alone, by day: a turn's tokens to its row and role, with Codex, is the next step.

## The KPI views

| View | Gives |
|---|---|
| `lead_times` | S5 for each merged row: minutes from its go to its merge, where the go is the earliest of its first approved item, its approval and its first launch |
| `main_spells` | each red spell of the push checks on main, from the first commit whose check failed to the next commit whose check passed, with `minutes_to_green` |
| `change_failures` | S6 for each merged row: whether its pull request opened a spell |
| `weekly_lead_time` | each week's S5: `n`, `median` and `p85` |
| `weekly_change_failure` | each week's S6: `failures`, `merged` and `rate` |
| `brief_at_launch` | F1 for each launch of a row: the sha of the brief stored then, and how many versions came after |
| `run_attempts` | F2 for each run: its attempts, when and at which attempt it first failed, and how its last attempt ended |
| `carried_words` | F4 for each word a home carried: from `acts.jsonl`, with the thread it went to from `word-sends.json` |
| `weekly_restore` | each week's S7: `spells`, `median`, `most`, `still_open` and `negative` |
| `ask_ledger` | each message you typed and what it joined: a `row` or an `answer`, an act that cites the message by id, else a `reply` in its thread within 120 minutes; with none, `waiting`, then `unanswered` |
| `weekly_lost_asks` | each week's S3 with no labels: `typed`, `lost`, `waiting` and `rate` |

A week starts on Sunday.
The median and the 85th percentile are the scorecard's (`reports/week-audit/scorecard.py` in the home).
To read one, open the file with any SQLite reader:

```sh
sqlite3 ~/.local/state/jbus/telemetry.sqlite 'SELECT * FROM weekly_lead_time ORDER BY week'
```

A lost ask is an `unanswered` message: no act cites it, and no reply came in its thread within the wait.
The wait is counted to the last build, so a view read twice gives the same answer.
A reply counts as an answer, so a message answered in words whose work never became a row is not lost here.

The spells come from `ci.jsonl`, so S6 and S7 count only the projects whose table says `ci_report = true`, and only the runs their ledger holds.

## The KPI alerts

Each pass, after the build, `jbus.kpis` reads each threshold as a count against its limit, never a burn rate:

| Alert | Count | Alerts | Owner |
|---|---|---|---|
| `doors` | the one-way doors opened today without the user's word: a `done` act on a door whose words jbus did not read in T3 Code | on 1 | the project |
| `main-red` | the minutes main's push check was red today, a spell still open counted up to now | over 30 | the project |
| `capped` | the minutes today with every Claude instance capped, as `jgauge spend` counts them | over 30 | the machine |
| `lost-asks` | the asks lost today: a typed message `ask_ledger` calls `unanswered`, counted on the day its wait ran out | on 1 | the project |
| `pass-time` | the 90th percentile of the seconds of the passes of the last hour, once the store holds a pass an hour old | over 60 | the machine |

An alert goes on jbus's one list of alerts, so the owner's home hears of it as it hears of any other.
A crossing alerts once: a later pass that finds it still crossed sends nothing, whatever the count has become.
A daily alert ends with its day, and a crossing the next day is a new alert.
An alert whose count falls back under its limit ends with a `recovered` line.

## How it stays current

Each pass runs a build after its launches and before any project's second half.
A build reads only what is new: a log on from the offset the last build reached, and a snapshot only when it changed.
A pass reads at most 16 MiB of new records and leaves the rest to the next pass.
`jbus telemetry` reads everything that is new and prints what it added and how long it took.

The daily trim keeps `events.jsonl` to 14 days, and drops only the lines the store holds.
A line the store has not read yet stays in the file, however old, until a build reads it.
With no store, the trim drops nothing.

A build run twice adds nothing the second time, and a build stopped part way leaves each file read or not, so the next build carries on.
A store kept up pass by pass holds what a store built from nothing would hold, and the rows that the sources have since dropped as well.
`jbus telemetry --rebuild <path>` writes a new store at a new path from the sources alone, so you can compare the two.
It never writes over a file, and it never replaces the store, which holds rows the sources no longer have.

## Change the store

`PRAGMA user_version` is the schema's version.
A change to a table is a new migration at the end of `MIGRATIONS` in `jbus.telemetry.schema`, run once on each store.
The first migration is written out as SQL, so a column a `Source` gains is a later migration and never an edit of it.
A new KPI is a new view in `VIEWS`, with a test beside it, and no migration: the views hold no rows, so each build makes them again.
A new record file is a `Source` in `jbus.telemetry.records`, with its allow-list of columns, and a migration that makes its table.
