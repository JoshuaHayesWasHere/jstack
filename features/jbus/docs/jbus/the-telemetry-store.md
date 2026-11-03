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
| `queue` | `queue.json` | a row of the queue, with its approval's times and `follows`, the parent a follow-up's go names |
| `merged` | `merged.json` | a merged pull request of a row |
| `ci_prs` | `ci-prs.jsonl` | a pull request the CI ledger keeps |
| `brief_versions` | `brief-versions.jsonl` | a change of a stored brief's sha, or its removal (no sha) |
| `row_pulls` | `row-pulls.jsonl` | a pull request a row had, the first time a pass saw it open, and again merged |
| `runs` | `runs.jsonl` | a completed attempt of a workflow run, of every project |
| `spend_days` | `spend.jsonl` | a project's Claude spend of one local day (`spent_on`), in units, tokens and units by kind |
| `spend_rows` | `spend-rows.jsonl` | a day's spend of one role and row, by the title jbus gave the thread |
| `word_sends` | `word-sends.json` | the thread a carried word went to and when, or that it still waits |
| `reverts` | `reverts.json` | a revert jbus opened for a red main, by its red tip: the culprit's `slug`, the revert's `branch` and its `pr` |
| `passes` | the machine's `passes.jsonl` | a pass of jbus: its start and its seconds, under the project `''` |
| `launch_arms` | the launch records, `launches/<project>/<slug>/<sha>.json` | a launched record's arm of one dial (`dial`, `arm`, `covered` 1), or for a launch from before records named their arm, one row with no dial or arm and `covered` 0 |
| `review_rounds` | `review-rounds.jsonl` | a settled review round of a row's pull request: its number, head, sections, `Meets the brief` verdict (`meets`, `met` of `done_when`) and its findings by severity (`errors`, `warnings`, `infos`, `others`, `dismissed`) |
| `messages` | T3 Code's store, read only, and the `word` acts of `acts` | a message of a T3 Code thread, the user's or the assistant's, keyed by its id, or a word you said with no T3 message, keyed `word:<id>` |

Each time is in UTC, written `YYYY-MM-DDTHH:MM:SS.ffffffZ`, so that text order is time order.
Each table also has `day`, the local date of its main time in the zone that `jsettings` gives.
`builds` records each build: when, how long in milliseconds, the bytes it read and the rows it added.

`messages` reads T3 Code's `statev2.sqlite` on from the last message it read.
Its `project` is the jbus project of the thread, or T3 Code's own id of a project jbus does not know.
A user's message has a `kind`: `text`, `command`, `answer`, `resume`, or `dropped` for a text that T3 Code or an agent put in the user's turn.
A word you said through the bots' chat or the view, which `jbus word` keeps as an act, is a message of yours too, of kind `text`.
Each build writes it from the store's `acts`, at the time you said it, in the thread jbus carried it to, with `creation_source` `word:` and the act's source, such as `word:bot-chat`.
A word recorded from your own T3 message is that message, and the message jbus carries a word in is T3 Code's, so each word is one ask.

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

Two more records are what an A/B or a simulator of a dial needs (the kpi-lab build order: records first):

- The arm of each launch: a launch record written while a dial ran names, under `arms`, the arm of each dial the row launched on, `off` while that dial's pilot was not started.
  crew-router-pilot was that dial, and it ended with its read, so a record jbus writes now names none.
  The store reads the records whose time is at or after the newest it read, keeps the launched ones once by their key and dial, and never updates a row (`jbus.telemetry.launches`).
  A record from before `arms` that names `priming` gives that arm of `crew-router-pilot`; one that names neither, from before the store could tell or after the pilot ended, reads `covered` 0, with no arm guessed.
- `review-rounds.jsonl`: a pass adds a line for each review round of an open pull request's brief once the round is settled, that is a later round began or no reviewer the crew launched still owes its section (`jbus.reviewed.rounds`), once by row, pull request and round number.
  A round is the sections in a row that ran at one head, and a scoped pass is a round of its own.
  A pull request the pass sees merged within the week has every round settled, so the last round of one that merged before a pass saw it settled gets its line on the first pass that sees the merge.

Each line keeps ids, times, counts and labels, and no text of a finding or a review.
The spells an account was capped or signed out are the row `tm-capped-spells`' record.

## Questions the records answer

| Question | Query |
|---|---|
| Which brief did a row launch with, and did it change after? | `SELECT slug, launched_at, sha, changed_after FROM brief_at_launch` |
| Which runs took more than one attempt, and at which attempt did each first fail? | `SELECT project, run, attempts, first_fail_attempt, first_fail_at, last_conclusion FROM run_attempts WHERE attempts > 1` |
| Which pull requests did each row open? | `SELECT project, slug, group_concat(DISTINCT number) FROM row_pulls GROUP BY project, slug` |
| Which thread did each word a home carried go to, and when? | `SELECT project, word, kept_at, said_in, thread, sent_at, waiting FROM carried_words` |
| What did each row spend, by role? | `SELECT spent_on, role, slug, units FROM spend_rows WHERE slug IS NOT NULL` |
| What did each day spend? | `SELECT project, spent_on, units, runs FROM spend_days` |
| Which arm did each row launch on? | `SELECT project, slug, role, dial, arm, at FROM launch_arms WHERE covered` |
| How did each pull request's review rounds go? | `SELECT project, slug, pr, round_number, meets, errors, warnings FROM review_rounds ORDER BY project, slug, round_number` |

`spend_rows` is Claude's alone, by day, from T3 Code's count of each run; each call's tokens to its row and role, Codex's too, are in `call_rows` and `row_spend` ("Token usage" below).

## Token usage

The store also keeps the token usage of every Claude and Codex call that a T3 Code thread made, by its thread:

| Table | Source | One row is |
|---|---|---|
| `sessions` | T3 Code's store | a native Claude or Codex session, with its thread and the project, role and slug its title gives |
| `calls` | Claude Code transcripts and Codex rollouts | a call: its session, its subagent where one made it, its model, its time and four counts |

Claude Code deletes a transcript whose last write is older than its `cleanupPeriodDays` setting, 30 days unless its settings say otherwise.
Each pass copies the calls written since the last one, so a call is in the store long before its transcript is gone.
A Claude call is one message, counted with its final counts once Claude Code wrote them.
A Codex call is one `token_count` event.
`input` is the input not read from the cache, for both.

| View | Gives |
|---|---|
| `call_rows` | each call with its thread, project, role and slug, and its spend in the units of `jgauge spend` |
| `row_spend` | each merged row's spend by role and provider: calls, the four counts and units |

`jgauge spend` reads T3 Code's own count of each run, which leaves out the calls of a run's subagents.
A day of it is the day's Claude calls with no `agent`:

```sh
sqlite3 ~/.local/state/jbus/telemetry.sqlite "SELECT sum(units) FROM call_rows WHERE provider = 'claude' AND agent IS NULL AND thread IS NOT NULL AND day = '2026-11-01'"
```

## The KPI views

| View | Gives |
|---|---|
| `lead_times` | S5 for each merged row: minutes from its go to its merge, where the go is the earliest of its first approved item, its approval and its first launch |
| `main_spells` | each red spell of the push checks on main, from the first commit whose check failed to the next commit whose check passed, with `minutes_to_green` |
| `ci_projects` | each project whose push checks on main the store holds |
| `ci_rows` | each merged row of a project in `ci_projects`, `kept` where the store holds a push check of main for its pull request |
| `ci_gaps` | each day with merged rows that are not `kept`, and how many `rows` |
| `change_failures` | S6 for each `kept` row of `ci_rows`: whether its pull request opened a spell |
| `weekly_lead_time` | each week's S5: `n`, `median` and `p85` |
| `weekly_change_failure` | each week's S6: `failures`, `merged` and `rate` |
| `brief_at_launch` | each launch of a row: the sha of the brief stored then, and how many versions came after |
| `run_attempts` | each run: its attempts, when and at which attempt it first failed, and how its last attempt ended |
| `carried_words` | each word a home carried: from `acts.jsonl`, with the thread it went to from `word-sends.json` |
| `weekly_restore` | each week's S7: `spells`, `median`, `most`, `still_open` and `negative` |
| `ask_ledger` | each message you typed or word you said, what it `asks`, and what it joined: a `row` or an `answer`, an act that cites the message by id (a word by its own id), else a `reply` in its thread within 120 minutes; with none, `waiting`, then `unanswered` |
| `weekly_lost_asks` | each week's S3 with no labels: `typed`, `lost`, `waiting` and `rate` |
| `weekly_needs_asks` | each week's messages you `typed`, waiting or not, and the `asks` among them whose label is `needs` |
| `weekly_typed_per_row` | each week's messages you `typed`, resumes apart, rows `merged`, and `per_row` |
| `pr_times` | each pull request of `ci-prs.jsonl` that `jmerge` logged as merged, in the week of its first merge line from a minute before it opened on: `minutes` from open to merge, and `first_round` where no check of it failed and `jmerge` never waited on a crew's fix round, or none where `ci.jsonl` kept no `pull_request` check of it |
| `fix_rounds_since` | the first `day` of a wait in `merge.log` labelled as a crew's fix round |
| `weekly_pr_to_merge` | each week's open-to-merge `n`, `median` and `p85` |
| `weekly_first_round` | each week's `n` of pull requests whose checks were kept, `first_round` and `share`, in percent |
| `weekly_merges` | each week's rows `merged` |
| `rows_since` | the first `day` of jbus's row records, `items.jsonl` |
| `weekly_doors` | each week's door acts `done`, and `not_yours`, those a home, a bot or jbus did |
| `weekly_pass_time` | each week's jbus passes: `n`, and the `median` and `p85` of their seconds |
| `weekly_row_spend` | each merge week's `rows` with any call recorded in `row_spend`, their `units`, and `per_row` in millions |
| `weekly_spend` | each week of the days `jgauge spend` counted, each project's last line of a day (`spend_kept`): `days`, `units`, and in percent the `coordination` share, jbus's sends and the homes, and the `capped` share, runs that failed on a usage limit or part way |
| `row_words` | S1 for each merged row with a go: the messages you typed, resumes apart, after its go and by its merge that name it, cited by an act of the row's project on the row or typed in its crew's thread |
| `weekly_no_word` | each week's rows `merged`, those `quiet`, with no such message, and their `share`, in percent |
| `redos` | each later row that redoes a merged row and `how`: a `follow-up` or `main-red` fix whose go names it, a `main-red-<sha12>` fix of the row whose merge commit that red tip is, or a `revert` jbus opened, with when it came (`at`) |
| `redo_rows` | each merged row in the week its 7 days end, `judged` once they ended by the last build, and the first row that redid it in them (`redone_by`, `how`) |
| `weekly_redo` | each week's rows `redone` of those `judged`, those `waiting`, and the `rate`, in percent |
| `redo_since` | the first `day` of a follow-up's go that names its parent |

A week starts on Sunday.
The median and the 85th percentile are the scorecard's (`reports/week-audit/scorecard.py` in the home).
To read one, open the file with any SQLite reader:

```sh
sqlite3 ~/.local/state/jbus/telemetry.sqlite 'SELECT * FROM weekly_lead_time ORDER BY week'
```

What a message asks is one label: `needs` where it asks what needs you, else `other`.
A build works the label out of the text as it reads it and keeps only the label, in `messages.asks` and in `acts.asks` for a word.
`features/jbus/src/jbus/telemetry/asks.py` writes the rule, what it leaves out on purpose and what it misses.

A lost ask is an `unanswered` message: no act cites it, and no reply came in its thread within the wait.
The wait is counted to the last build, so a view read twice gives the same answer.
A reply counts as an answer, so a message answered in words whose work never became a row is not lost here.

The spells come from `ci.jsonl`, so S6 and S7 count only the projects whose table says `ci_report = true`, and only the runs their ledger holds.
S6 counts a merged row only where the store holds a push check of main for its pull request, since a row with none could never fail.
The KPI page names the projects S6 covers and the days of the week with rows it left out.
A merge line counts for a pull request only from a minute before it opened on, since `merge.log` can hold an older repo's lines of the same number, as jstack's does from 2026-10-10 to 10-14.
`pr_times` reads `ci-prs.jsonl` too, so it has the same projects.
A crew's fix round is a wait in `merge.log` with one of the labels `CREW_FIX` names in `jbus.telemetry.schema`.
`merge.log` has no such labels before 2026-10-28, so for a pull request merged before then `first_round` counts a fix round only when a check failed.
The KPI page shows no first-round share for a week that begins before `fix_rounds_since`, since such a week would count a fix round with no red check as a first round.
`ci.jsonl` kept no `pull_request` check of 33 of the 48 jstack pull requests merged on 2026-10-20, of every one from 2026-10-21 to 2026-10-25, of 58 of 100 on 10-26 and of 46 of 49 on 10-27, the whole set in the store built on 2026-11-03, and `first_round` is none for those: whether a check of theirs failed is not known.

## The KPI page

`jbus kpis` writes `kpis.html` in jbus's state directory: one static page that answers "is the vision met this week".
It reads the store alone, calls no `gh` and runs no service, so it costs nothing to build again.

```sh
jbus telemetry && jbus kpis
```

Each of the 23 KPIs is a row: what it counts, its target, and last week and this week so far, each with its value, the count `n` it is of, and `met`, `missed`, `tracked` where it has no target yet, `no data` where nothing in the week counts, or `not covered` where the week begins before the records the KPI reads do, with a note that says when they begin.
A KPI the store has no instrument for yet says so, and names what it needs.
A week starts on Sunday, as the views' does.
The page names no row, path or thread, and no project but those the change failure rate says it covers.
The store holds no text of a message.

Each KPI, its target and the view it reads is a module of its own in `jbus.telemetry.kpis`, `k<NN>_<slug>.py`, whose `KPI` is one `Kpi`.
The page shows them in the order of the modules' names, so `NN` is a KPI's place, and two KPIs of the same `NN` are in the order of their slugs.
A new KPI is a new module, and no list names it.
To measure a KPI that lacks an instrument, add the record and its weekly view as "Change the store" says, then give the KPI a `Measured` in place of its `Lacks`.

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

A change to a table is a new migration, a module of its own in `jbus.telemetry.migrations`, run once on each store.
Its name is `v<NNN>_<slug>.py`, where `NNN` only orders it: it need not be free, or one more than the last migration's.
The store keeps the name of each migration it has run in its `migrations` table, and runs each one it has not, in the order of their names.
So two changes that each add a `v010_` both run, and a migration changes only what the migrations named before it made.
A store that counted its migrations by `PRAGMA user_version`, as stores did before, is moved to the table once, with the names of as many of them as its version.
A migration that has merged is never edited, renamed or removed.
The first migration is written out as SQL, so a column a `Source` gains is a later migration and never an edit of it.
A new view is a module of its own in `jbus.telemetry.views`, named as the view, whose `SQL` is its `SELECT`, with a test beside it, and no migration: the views hold no rows, so each build makes them again.
The SQL the views share, such as `WEEK` and `TYPED`, is in `jbus.telemetry.schema`.
A new record file is a `Source` in `jbus.telemetry.records`, with its allow-list of columns, and a migration that makes its table.
