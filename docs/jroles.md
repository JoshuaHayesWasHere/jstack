# jroles

`jroles` picks the model for a role.

A launched thread runs on the model of the thread that launched it, unless the role map names one for its role. The map is `${XDG_CONFIG_HOME:-~/.config}/jstack/roles`, one line a role, with `#` for a comment:

```
# Two Claude Sonnet 5.5 reviewers on High (the user, 2026-10-20)
crew: claudeAgent claude-sonnet-5-5
scout: claudeAgent claude-sonnet-5-5
review: claudeAgent claude-sonnet-5-5 effort=high
review: claudeAgent claude-sonnet-5-5 effort=high
home: inherit
```

A line is `<role>: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<level>] [fast=<on|off>]`. The roles are `crew`, `scout`, `review`, `home` and `expert`. The handoff of a party that is no repo's home reads `expert`. An expert's own rollover is the expert skill's and does not go this way. `<provider>` is T3 Code's id for Claude, Codex, Cursor or Grok: `claudeAgent`, `codex`, `cursor` or `grok`. `<role>: inherit` is the same as no line, and so is no file.

## The review list

`review` alone may have several lines.
Each is one reviewer, in the order written, and every pull request gets one review from each.
The crewmate launches a reviewer thread for each line with the message `/pr-review run <slug> <n>`, `<n>` the line's number from 1, and writes `Reviewer: <threadId> #<n>` in its Result.
Each reviewer writes its own `## Review` section into the brief, with a `By: <provider> <model> <effort> #<n>` line under the heading.
Two lines of one provider and model are two reviewers, told apart by the number alone.
`jmerge` reads the sections at one head as one round: it waits until a section carries each number the `Reviewer:` lines name, and the round's verdict is the worst of them.
Once a `Reviewer:` line carries a number, the unnumbered `Reviewer:` lines are a launch it replaced: the round waits on them no more, and their sections are not its verdict, though their findings still need their answers.
A brief none of whose lines carries a number is read as before, by the `By:` texts.
A scoped pass or a second pass is one reviewer, on the first line, and writes `#1`.
Any other role named twice refuses the map, and so does `review: inherit` beside another review line.

Since the user's word of 2026-10-20 every review runs as two Claude Sonnet 5.5 threads at `high`, from the main Claude pool, and no review line names Codex or Cursor.
It replaces, for now, the earlier rule that Claude does the coding and the other providers review.
A review line that names Claude's built-in instance, or a pool of Claude instances, is placed and moved on a cap like any other Claude thread (see Pools).

## Effort and fast

Each provider names its effort with its own T3 Code option id, and takes only the levels T3 Code lists for it, up to the ceiling the user's rule gives the role:

| Provider | Option id | Levels | With no `effort=` |
| --- | --- | --- | --- |
| `claudeAgent` | `effort` | `low`, `medium`; `high` too on a `review` line | `medium`, always sent |
| `codex` | `reasoningEffort` | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` | the model's default, nothing sent |
| `cursor` | `reasoning_effort` | `low`, `medium`, `high`, `xhigh` | the model's default, nothing sent |
| `grok` | none | none: a Grok line names no effort | nothing sent |

A Claude line always launches at `medium`, or at the level it names.
T3 Code launches a model with no effort at that model's own default, which is `high` for Claude Sonnet 5.5 and Claude Opus 5, and no Claude thread here runs above medium unless the user says so.
The user said so for reviews (2026-10-20): a `review` line may name `high`, and no higher.
A `crew`, `scout`, `home` or `expert` line takes `low` or `medium` alone.
T3 Code lists `xhigh` and `max` for Claude too, and a level above a role's ceiling refuses the line's role, and its launch inherits.
A level the provider does not list, such as `effort=turbo` on a Codex line, refuses the role the same way.

`fast=on` or `fast=off` is Cursor's alone, sent as `{"id": "fastMode", "value": true}` or `false`. T3 Code's default for Cursor's Grok 4.7 is on, so a reviewer with Fast off says `fast=off`.

One line of a role that is refused refuses every line of that role: half a list of reviewers is a review nobody chose.

## Running it

Before a launch a thread runs `uv run jroles <role>`.
For a role the map names, `jroles` prints one JSON line a selection, such as `{"provider": "claudeAgent", "model": "claude-sonnet-5-5", "options": [{"id": "effort", "value": "high"}]}`, and the launch sends it as `modelSelection`.
For `review` it prints a line for each reviewer, in order, and each is one launch.
It prints nothing when the launch inherits.
A selection names the instance of its pool it chose (see Pools), and while any review line's pool is capped the whole list waits.
A map it cannot use is said on stderr, the launch inherits, and `jroles` exits 0.
It does not ask T3 Code whether the model exists.

## Pools

The instances a line names are the line's pool, in order:

```
crew: claudeAgent claude-opus-5-5 claudeAgent,claudeAgent_claude_prime effort=medium
```

A launch goes to the first instance of the pool with headroom in the ledger, and the selection names it as its `instanceId`.
So every launch goes to `claudeAgent` until it nears a usage limit, then to `claudeAgent_claude_prime`, and back to `claudeAgent` once its window has reset.
Nothing goes round the pool launch by launch: a thread stays on the account it started on, and moves only when a cap stops it (`jbus`, "A usage limit" in [jbus](jbus/tying-a-crewmate-to-its-thread.md#a-usage-limit)).
One instance is a pool of one.
A line that names none has the provider's built-in instance as its pool, and its selection names no instance, as before.

The move goes both ways: a thread capped on `claudeAgent` goes on to `claudeAgent_claude_prime`, and one capped on `claudeAgent_claude_prime` goes back to `claudeAgent` while that one has headroom.
The threads that move are every thread of every project in `~/.config/jbus/config.toml` that failed on a usage limit and is not settled: a crew (`crew: `), a reviewer (`review: `) or a scout (`scout: `) by its title, and the homes in a `home-id`, the root home's and each scope's.
A thread that owes nothing stays where it is: a crew whose task merged or ended clean, a reviewer whose task is over and whose brief's last Review has a verdict (a scoped or second-pass reviewer of a task still out owes its own pass), a scout whose Report is written.
A thread's pool is the first line of the map that names its instance, its own role's lines first and then every other role's.
So a Claude reviewer whose `review` lines name Codex and Cursor moves in the `crew` line's Claude pool, and a thread on an instance no line names is a pool of one and waits for its reset.
A move happens only on a cap, and it is sticky: a thread stays on the account it moved to until that account caps, and nothing moves it back once the first one is free, since each move is a handoff that loses some context.
With both capped the thread is sent nothing: `jbus` says so once, as a `stall`, and the first pass after the first reset sends it on.
`jbus failover --replay <items.json> --thread <id>` replays a recorded cap on one live thread through the same move, with the reset as far from now as it was from the recording, and keeps the cap out of the ledger; `jbus failover --replay <items.json> --thread <id> --dry-run` prints the move and writes nothing.

For a pool of more than one, and for any launch a cap moved, stderr says which instance it chose and why: `jroles: crew on claudeAgent: the first of claudeAgent,claudeAgent_claude_prime with headroom`, or `jroles: crew on claudeAgent_claude_prime: claudeAgent is capped until 2026-10-18T20:00:00+00:00`. While every instance of the pool is capped it prints nothing, says so on stderr (`jroles: crew waits: claudeAgent and claudeAgent_claude_prime are both capped until ...`) and exits 75: the launch waits for the first reset.

A pool grows by one line of the provider inventory, `~/.config/jstack/providers.json` ([configuration](configuration.md#provider-instances)), and one more id on the role line. Each id must be the provider's built-in instance or one the inventory declares under the line's provider: any other refuses the line, so a Claude pool never names a Codex or a Cursor instance. With no inventory the line is taken as written. An id named twice, or an empty one (`claudeAgent,`), refuses the line too.

## The ledger

A usage limit, the five-hour or the weekly one, caps an instance until its window resets.
The ledger keeps each instance's use of each window: the file `LIMITS` names (`~/.local/state/claude/limits`) for `claudeAgent`, and the file beside it, `<LIMITS>.<instanceId>`, for any other, each with a line for a window, `five_hour <percent used> <reset>` and `seven_day <percent used> <reset>` ([configuration](configuration.md#the-limits-file)).
For a new launch an instance has headroom while none of its windows is at the user's `headroom` or over with its reset ahead, 90% by default ([configuration](configuration.md#jstack)).
A thread already running moves off its instance only at a real cap, 100% (`jbus`, "A usage limit").
Three writers keep the ledger, by one rule (`src/jroles/ledger.py`): two resets under 5 minutes apart are one window, which keeps the larger share, and otherwise the later reset wins.
A writer floors its reset to the second, and the usage endpoint's moves a second either way between calls, so a lower share of a window never replaces a cap on it.
`jgauge limits` is the writer ahead of time: every two minutes, from `jgauge-limits.timer`, it reads each Claude account's use from the usage endpoint with that home's own token, or from the answer Claude Code cached in that home's `.claude.json` while it is under 15 minutes old ([jgauge](jgauge.md)).
The other two write only when something happens: the status line (`hooks/limits.sh`), for the account whose `CLAUDE_CONFIG_DIR` it runs under, and `jbus`, at 100% from a turn T3 Code ended on a usage limit.
A source that fails writes nothing, so the last line stands and a capped account is never read as free.
`jgauge limits --check` and `install.sh --check` name a file 15 minutes old or more.

`jgauge room` reads the ledger for the pool of the role it checks for, `jgauge room --role <role>`, the crew's where it names none.
It waits on the plan only while every instance of a line's pool is full, and the `wait:` names each instance and the first reset: `wait: claudeAgent and claudeAgent_claude_prime are both at or over 90%: claudeAgent's five-hour limit is 100% used and resets in 2 h 0 min, claudeAgent_claude_prime's weekly limit is 100% used and resets in 1 d 6 h 0 min; the first resets in 2 h 0 min`.
An instance full on both windows is named by the one that resets later, since it has no headroom until then.
While one instance is full and another has room, `jgauge room` prints `go` and a `note:` on stderr that names the full one and the first with room.
For a role with several lines, `review`, each line is a pool, and one whose instances are all full holds the check.
A role with no pool reads the file `LIMITS` names, as before, and `jgauge room --instance <id>` reads that one instance's file alone.

## Mirrors

A second Claude account runs as an instance of its own, in a home of its own: the `config.homePath` of a `claudeAgent` instance of `~/.config/jstack/providers.json`, such as `~/.claude_prime` for `claudeAgent_claude_prime` ([configuration](configuration.md#provider-instances)).
A thread on it should know what a thread on `~/.claude` knows, and differ only in its login.
`jroles mirror` keeps each such home a mirror of `~/.claude`: every Claude instance of `providers.json` whose home is not `~/.claude` is one, and nothing else in jstack names the homes.
The instance ids and the homes are infra's, in `providers.json`; the code that mirrors them is jstack's.

What is shared is every entry of `~/.claude`, as a symlink in the mirror: `projects` (the memory and the transcripts), `history.jsonl`, `file-history`, `downloads`, `uploads`, `skills`, `plugins`, `settings.json`, `CLAUDE.md`, and any entry `~/.claude` gains later, on the next run.
What is per login stays the mirror's own and is never linked: `.credentials.json`, `.claude.json`, `sessions`, `session-env`, `shell-snapshots`, `cache`, `backups`, `debug`, `statsig`, `telemetry`, `ide`, `stats-cache.json`, `.last-cleanup` and `.last-update-result.json`.

`<home>/.claude.json` stays a file, since it holds the account.
Its account keys are kept: `oauthAccount`, `userID`, `cachedUsageUtilization` and every other `cached*` key, every key ending in `Cache` or `CacheAt`, and the rest of `ACCOUNT_KEYS` in `src/jroles/mirror.py`.
Every other key is copied from `~/.claude.json`, such as `mcpServers`, and `projects` is merged project by project, with `~/.claude.json` winning.

A run reads each mirror, then changes only what differs:

| What the mirror holds | What a run does | What it prints |
| --- | --- | --- |
| No entry where `~/.claude` has one | Links it | `linked    <entry> -> <target>` |
| A real file or directory where `~/.claude` has one, or a link elsewhere | Merges a directory's files into `~/.claude`, moves the entry to `<name>.bak-<time>` and links it | `backup    <entry> -> <backup>`, then `linked` |
| A file both hold with other bytes | Keeps the one in `~/.claude`, and the mirror's copy stays in the backup | `conflict  <file> kept; the mirror's copy is in <backup file>` |
| An entry only the mirror has | Moves it into `~/.claude` and links it back | `moved     <entry> -> <target>, linked` |
| A link into `~/.claude` whose entry is gone | Removes it | `removed   dangling <entry>` |
| Shared keys of `.claude.json` that differ | Writes the file again, mode 600 | `synced    shared keys of ~/.claude.json into <file>` |

A run with nothing to do prints nothing and writes nothing.
Each mirror is changed under its own lock, `<home>/.jroles-mirror.lock`, and under the main home's, `~/.claude/.jroles-mirror.lock`, so no two runs interleave, on one mirror or on two that would move the same new entry into `~/.claude`.
A move whose target appeared in `~/.claude` since the plan was read is not made: it prints `kept`, and the next run backs the entry up and merges it.
A directory is merged before it is moved and again after, so a run that stopped halfway leaves nothing unmerged, and the next run picks up where it stopped.
A mirror whose home is not there is said on stderr, and the run exits 2: the home is made by the account's first login, which is infra's.

`jroles mirror --check` changes nothing, takes no lock, prints `would ...` for each entry that differs and exits 1 if there is one.
`jroles mirror --instance <id>` reads or mirrors that instance alone, and exits 2 for an id that is no mirror.
`templates/jroles-mirror.timer` runs `jroles mirror` every 5 minutes, through `jroles-mirror.service`, and `install.sh` links and enables both with the jbus units.
`install.sh --check` prints `ok optional mirror <home>`, or `old optional mirror <home> -> <the first line of --check>` while it differs.

Before `jbus` launches a crew on a mirror instance, or moves a capped thread onto one, it runs `jroles mirror --check --instance <id>`.
On drift it runs `jroles mirror --instance <id>` once and checks again.
An instance that still differs is passed over for the rest of the pass, with `wait <slug>: <id> is not mirrored`: the launch or the move goes to the next instance of the pool with headroom, or waits for a later pass.
