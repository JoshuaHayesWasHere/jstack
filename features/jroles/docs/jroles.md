# jroles

`jroles` picks the model each kind of thread runs on.
A home, a crewmate, a scout, a reviewer and an expert are roles.
The role map names a model for each role, or says that the role's thread runs on the model of the thread that launched it.
Whatever launches a thread runs `jroles` just before the launch, to get the model.

## Set a role's model

1. Open the role map, `${XDG_CONFIG_HOME:-~/.config}/jstack/roles`.
   `install.sh --setup` wrote the map with every role set to `inherit`.
   With that map, every thread runs on the model of the thread that launched it:

   ```
   # Written once by install.sh --setup. Edit it: setup never writes over it.
   crew: inherit
   scout: inherit
   review: inherit
   home: inherit
   expert: inherit
   ```

2. Replace `inherit` with a provider and a model on the line of each role you want to set.
3. Run `jroles <role>` to see what a launch of that role would get.
   It prints one JSON line for each selection, and nothing for a role that inherits.
   When it cannot use a line, it says why on stderr.

This map is an example, not a default:

```
# An example: Opus builds, and each pull request gets two reviews, on two providers
crew: claudeAgent claude-opus-5-5
scout: claudeAgent claude-haiku-5-5 effort=low
review: claudeAgent claude-sonnet-5-5 effort=high
review: codex gpt-5-codex
home: inherit
```

## The role map

A line is `<role>: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<level>] [fast=<on|off>]`.
A `#` starts a comment.
The roles are `crew`, `scout`, `review`, `home` and `expert`.
The handoff skill reads the `expert` line when it hands off a party that is not a repo's home.
The expert skill handles an expert's own rollover, and that rollover does not read this map.
`<provider>` is T3 Code's id for Claude, Codex, Cursor or Grok: `claudeAgent`, `codex`, `cursor` or `grok`.
`<role>: inherit` has the same effect as leaving the line out, and so does a missing map file.

## The review list

`review` alone may have several lines.
Each `review` line is one reviewer, in the order written.
Every pull request gets one review from each reviewer.
The crewmate launches a reviewer thread for each line with the message `/pr-review run <slug> <n>`.
`<n>` is the line's number, counting from 1.
The crewmate writes `Reviewer: <threadId> #<n>` in its Result.
Each reviewer writes its own `## Review` section into the brief, with a `By: <provider> <model> <effort> #<n>` line under the heading.
Two lines with the same provider and model are two reviewers, and only their numbers differ.
`jmerge` reads the sections at one head as one round.
It waits until it has a section for each number that the `Reviewer:` lines name.
The round's verdict is the worst verdict among those sections.
Once a `Reviewer:` line has a number, `jmerge` treats the unnumbered `Reviewer:` lines as a launch that the numbered lines replaced.
`jmerge` no longer waits on the unnumbered reviewers, and their sections are not part of the round's verdict.
The findings in those sections still need answers.
When no `Reviewer:` line of a brief has a number, `jmerge` matches sections to reviewers by their `By:` lines.
A scoped pass or a second pass has one reviewer, from the first `review` line, and that reviewer writes `#1`.
`jroles` refuses the map if it names any other role twice, or has `review: inherit` beside another review line.
A reviewer from a Claude `review` line, whether the line names the built-in instance or a pool, launches on an instance and moves on a cap the same way as any other Claude thread (see Pools).

## Models

This table lists the Claude model ids that the docs name.
A `claudeAgent` line may give any of them as `<model>`.
`jroles` passes the id to T3 Code as written, and does not check it against any list.
`scripts/check-jstack-docs.py` fails a page that names a Claude id this table lacks, so add a new model here first.

| Model | Name |
| --- | --- |
| `claude-opus-5-5` | Claude Opus 5.5 |
| `claude-sonnet-5-5` | Claude Sonnet 5.5 |
| `claude-haiku-5-5` | Claude Haiku 5.5 |

## Effort and fast

Each provider names its effort with its own T3 Code option id.
`jroles` takes only the levels in this table:

| Provider | Option id | Levels | With no `effort=` |
| --- | --- | --- | --- |
| `claudeAgent` | `effort` | `low`, `medium`; `high` too on a `review` line | `medium`, always sent |
| `codex` | `reasoningEffort` | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` | the model's default, nothing sent |
| `cursor` | `reasoning_effort` | `low`, `medium`, `high`, `xhigh` | the model's default, nothing sent |
| `grok` | none | none: a Grok line names no effort and no `fast=` | nothing sent |

A thread from a Claude line always runs at `medium`, or at the level the line names.
`jroles` always sends a Claude level.
Without one, T3 Code launches the model at its own default, which is `high` for Claude Sonnet 5.5 and Claude Opus 5.5.
`jroles` itself limits the Claude levels (`PROVIDERS` in `features/jroles/src/jroles/__init__.py`), and a map cannot raise them.
A `crew`, `scout`, `home` or `expert` line takes `low` or `medium`, and a `review` line takes `high` too.
T3 Code lists `xhigh` and `max` for Claude too.
If a line names a level above its role's limit, `jroles` refuses the role, and the role's launch inherits.
`jroles` refuses the role the same way for a level the provider does not list, such as `effort=turbo` on a Codex line.

`fast=on` or `fast=off` applies only to Cursor, and `jroles` sends it as `{"id": "fastMode", "value": true}` or `false`.
T3 Code turns Fast on by default for Cursor's Grok 4.7 model, so to turn Fast off on a Cursor line, write `fast=off`.

If `jroles` refuses one line of a role, it refuses every line of that role, so it never launches only part of a list of reviewers.

## Running it

Before a launch a thread runs `jroles <role>`.
For a role the map names, `jroles` prints one JSON line for each selection, such as `{"provider": "claudeAgent", "model": "claude-sonnet-5-5", "options": [{"id": "effort", "value": "high"}]}`.
The launching thread sends that line as `modelSelection`.
For `review` it prints one line for each reviewer, in order, and each line is one launch.
It prints nothing when the launch inherits.
A selection names the instance of its pool that `jroles` chose (see Pools).
While any review line's pool is capped, no reviewer on the list launches.
When `jroles` cannot use the map, it says so on stderr, the launch inherits, and `jroles` exits 0.
It does not ask T3 Code whether the model exists.

## Pools

The instances a line names are the line's pool, in order.
In this example, `claudeAgent_work` is a second Claude account that `providers.json` declares:

```
crew: claudeAgent claude-opus-5-5 claudeAgent,claudeAgent_work effort=medium
```

A launch goes to the first instance of the pool with headroom in the ledger.
The selection names that instance as its `instanceId`.
So every launch goes to `claudeAgent` until that account reaches its `headroom` (see The ledger).
Launches then go to `claudeAgent_work`, and go back to `claudeAgent` once `claudeAgent`'s window has reset.
`jroles` does not rotate through the pool launch by launch.
A thread stays on the account it started on, and moves only when a cap stops its turn.
[A usage limit](../../jbus/docs/working-on-jbus/tying-a-crewmate-to-its-thread.md#a-usage-limit), in the jbus docs, describes the move.
One instance is a pool of one.
A line that names no instance uses the provider's built-in instance as its pool, and its selection names no instance.

A capped thread can move in either direction between the instances of its pool.
A thread capped on `claudeAgent` goes on to `claudeAgent_work`, and one capped on `claudeAgent_work` goes back to `claudeAgent` while `claudeAgent` has headroom.
In any project of `~/.config/jbus/config.toml`, a thread can move if its turn failed on a usage limit and the thread is not settled.
The rule applies to a crew, a reviewer and a scout, which `jbus` finds by a title that starts with `crew: `, `review: ` or `scout: `.
It also applies to the homes that a `home-id` names: the root home and each scope's home.
A thread with no work left stays on its instance:

- a crew whose task merged or ended clean
- a reviewer whose task is over and whose brief's last Review has a verdict
- a scout whose Report is written

A scoped or second-pass reviewer of a task that is still running still has its own pass to run.
A thread's pool comes from the first map line that names the thread's instance.
The search covers the thread's own role's lines first, then every other role's lines.
So a Claude reviewer whose `review` lines name Codex and Cursor moves within the `crew` line's Claude pool.
A thread on an instance that no line names has a pool of one instance, and waits for that instance's reset.
A thread moves only on a cap.
It then stays on the account it moved to until that account caps.
`jbus` does not move it back once the first account is free, because each move is a handoff that loses some context.
With both accounts capped, `jbus` sends the thread nothing.
`jbus` reports the wait once, as a `stall`.
On its first pass after the first reset, `jbus` tells the thread to carry on.
`jbus failover --replay <items.json> --thread <id>` replays a recorded cap on one live thread, and moves that thread as a real cap would.
It sets the reset as far from now as the recorded reset was from the recording.
It does not write the cap to the ledger.
`jbus failover --replay <items.json> --thread <id> --dry-run` prints the move and writes nothing.

For a pool of more than one, and for any launch that a cap moved, `jroles` says on stderr which instance it chose and why.
For example: `jroles: crew on claudeAgent: the first of claudeAgent,claudeAgent_work with headroom`, or `jroles: crew on claudeAgent_work: claudeAgent is capped until 2026-10-18T20:00:00+00:00`.
While every instance of the pool is capped, `jroles` prints nothing on stdout and exits 75.
On stderr it prints a line such as `jroles: crew waits: claudeAgent and claudeAgent_work are both capped until ...`.
The launch waits for the first reset.

To add an instance to a pool, first add one line for it to the provider inventory, `~/.config/jstack/providers.json` ([configuration](../../jinstall/docs/configuration.md#provider-instances)).
Then add its id to the role line.
Each id must be the provider's built-in instance or one the inventory declares under the line's provider.
`jroles` refuses a line that names any other id, so a Claude pool never names a Codex or a Cursor instance.
With no inventory, `jroles` takes the line as written.
`jroles` also refuses a line that names an id twice or has an empty id, such as `claudeAgent,`.

## The ledger

A usage limit, the five-hour or the weekly one, caps an instance until its window resets.
The ledger keeps each instance's use of each window.
For `claudeAgent` the ledger is the file `LIMITS` names (`~/.local/state/claude/limits`), and for any other instance it is the file beside it, `<LIMITS>.<instanceId>`.
Each file has a line for each window, `five_hour <percent used> <reset>` and `seven_day <percent used> <reset>` ([configuration](../../jinstall/docs/configuration.md#the-limits-file)).
For a new launch, an instance has headroom while none of its windows is at or over your `headroom`, which is 90% by default ([configuration](../../jinstall/docs/configuration.md#jstack)).
A window counts only while its reset is in the future.
A thread already running moves off its instance only at a real cap of 100%, as "A usage limit" in the jbus docs says.
Three writers write the ledger, and all three follow one rule in `features/jroles/src/jroles/ledger.py`.
If two resets are under 5 minutes apart, the writer treats them as one window and keeps the larger share.
Otherwise the writer keeps the line with the later reset.
A writer rounds its reset down to the second, and the usage endpoint's reset can differ by a second either way between calls.
The rule means that a lower share of a window never replaces a cap on it.
`jgauge limits` writes the ledger on a schedule, before a launch needs it.
`jgauge-limits.timer` runs `jgauge limits` every two minutes.
`jgauge limits` reads each Claude account's use from the usage endpoint with that home's own token.
When the token has expired, it reads the answer Claude Code cached in that home's `.claude.json`, while that answer is under 15 minutes old ([jgauge](../../jgauge/docs/jgauge.md)).
The other two writers write only after an event.
The status line (`features/jgauge/hooks/limits.sh`) writes for the account whose `CLAUDE_CONFIG_DIR` it runs under.
`jbus` writes 100% when T3 Code ends a turn on a usage limit.
A writer that fails writes nothing, so the last line stays in the file and no reader takes a capped account for free.
`jgauge limits --check` and `jinstall --check` name each ledger file that is 15 minutes old or more.

`jgauge room --role <role>` reads the ledger for that role's pool.
Plain `jgauge room`, with no role, reads the ledger for the crew's pool.
It waits on the plan only while every instance of a line's pool is full, and not while one instance has room.
The `wait:` line names each instance and the first reset, as in `wait: claudeAgent and claudeAgent_work are both at or over 90%: claudeAgent's five-hour limit is 100% used and resets in 2 h 0 min, claudeAgent_work's weekly limit is 100% used and resets in 1 d 6 h 0 min; the first resets in 2 h 0 min`.
When an instance is full on both windows, `jgauge room` reports the window that resets later, since the instance has no headroom until then.
While one instance is full and another has room, `jgauge room` prints `go`.
On stderr it prints a `note:` that names the full instance and the first instance with room.
For `review`, the role with several lines, each line is a pool.
If all the instances of any one line are full, `jgauge room` waits.
For a role with no pool, `jgauge room` reads the file that `LIMITS` names.
`jgauge room --instance <id>` reads only that instance's file.

## Mirrors

You need `jroles mirror` only when you run a second Claude account.
Each extra account is a `claudeAgent` instance in `~/.config/jstack/providers.json`.
It has its own Claude home at its `config.homePath`, such as `~/.claude_work` for an instance `claudeAgent_work` ([configuration](../../jinstall/docs/configuration.md#provider-instances)).
`jroles mirror` makes each such home a mirror of `~/.claude`.
It replaces every entry of the extra home with a symlink into `~/.claude`, except the login's own files.
So under both accounts, Claude Code reads and writes the same memory, transcripts, history, skills, plugins, `settings.json` and `CLAUDE.md`.
The two homes differ only in the login.
It also copies the shared keys of `~/.claude.json` into the extra home's `.claude.json`.
It changes `~/.claude` too.
`jroles mirror` moves an entry that only the extra home has into `~/.claude`, and puts a link to it in the mirror.
`jroles mirror` also combines the skill use of every home into `~/.claude.json`.
The install (`jinstall`) enables `jroles-mirror.timer`, which runs `jroles mirror` every 5 minutes.
When `providers.json` has no extra Claude home, `jroles mirror` has nothing to mirror and changes nothing.

The mirror shares every entry of `~/.claude` as a symlink: `projects` (the memory and the transcripts), `history.jsonl`, `file-history`, `downloads`, `uploads`, `skills`, `plugins`, `settings.json`, `CLAUDE.md`, and any entry that `~/.claude` gains later, from the next run on.
`jroles mirror` never links the entries that belong to one login, and each mirror keeps its own copy of them: `.credentials.json`, `.claude.json`, `sessions`, `session-env`, `shell-snapshots`, `cache`, `backups`, `debug`, `statsig`, `telemetry`, `ide`, `stats-cache.json`, `.last-cleanup` and `.last-update-result.json`.

`<home>/.claude.json` stays a file, because it holds that home's account keys.
A run keeps the account keys of that file: `oauthAccount`, `userID`, `cachedUsageUtilization` and every other `cached*` key, every key ending in `Cache` or `CacheAt`, and the rest of `ACCOUNT_KEYS` in `features/jroles/src/jroles/mirror.py`.
A run copies every other key from `~/.claude.json`, such as `mcpServers`.
It merges `projects` one project at a time, and where the files differ, it keeps the value from `~/.claude.json`.
A run combines `skillUsage` instead, because every account belongs to the same user.
For each skill, each field of its entry takes the highest value any home has: the highest use count and the latest last-used time.
A run writes the combined `skillUsage` into `~/.claude.json` and into every mirror, so no account loses the use recorded in another.

A run reads each mirror, then changes only what differs:

| What the mirror holds | What a run does | What it prints |
| --- | --- | --- |
| No entry where `~/.claude` has one | Links it | `linked    <entry> -> <target>` |
| A real file or directory where `~/.claude` has one, or a link elsewhere | Merges a directory's files into `~/.claude`, moves the entry to `<name>.bak-<time>` and links it | `backup    <entry> -> <backup>`, then `linked` |
| A file both hold with other bytes | Keeps the one in `~/.claude`, and the mirror's copy stays in the backup | `conflict  <file> kept; the mirror's copy is in <backup file>` |
| An entry only the mirror has | Moves it into `~/.claude` and links it back | `moved     <entry> -> <target>, linked` |
| A link into `~/.claude` whose entry is gone | Removes it | `removed   dangling <entry>` |
| Shared keys of `.claude.json` that differ | Writes the file again, mode 600 | `synced    shared keys of ~/.claude.json into <file>` |
| Less skill use than the pool, in a mirror or in `~/.claude.json` | Writes the pool into the file | `pooled    skillUsage into <file>` |

A run with nothing to do prints nothing and writes nothing.
A run changes each mirror under that mirror's own lock, `<home>/.jroles-mirror.lock`, and under the main home's lock, `~/.claude/.jroles-mirror.lock`.
So no two runs interleave on one mirror.
Two runs on different mirrors also cannot both move the same new entry into `~/.claude`.
A run does not move an entry if the target has appeared in `~/.claude` since the run read the mirror.
It prints `kept`, and the next run backs the entry up and merges it.
A run merges a directory before it moves it, and again after.
So a run that stopped halfway leaves nothing unmerged, and the next run continues from where the stopped run ended.
When a mirror's home does not exist, the run says so on stderr and exits 2.
Claude Code makes the home when you first sign in to that account.

`jroles mirror --check` changes nothing and takes no lock.
It prints `would ...` for each entry that differs, and exits 1 if any entry differs.
For `.claude.json`, it prints `would sync <keys> of ~/.claude.json into <home>/.claude.json`, which names only the shared keys whose values differ.
So a changed account key does not count as drift.
It compares each home's `skillUsage` with the combined `skillUsage` of every home.
The comparison includes `~/.claude.json` unless you pass `--instance`.
For a home whose `skillUsage` is behind only because of skills used since the last sync, `--check` prints `pooling   skillUsage <skills> into <file>`, and that does not count as drift.
The longest gap between two runs is 7 minutes, counting the timer's accuracy and the time a run takes.
For a home that lacks a skill whose last use is older than that gap, `--check` prints `would pool skillUsage <skills> into <file>` and exits 1.
When an entry of `skillUsage` is not an object of numbers, `jroles mirror` says so on stderr, `<file>: skillUsage <skill> is malformed`, and exits 2.
A run then combines no `skillUsage` until someone fixes the entry.
For a mirror with nothing to do, `--check` prints `ok <home> mirrors ~/.claude`.
`jroles mirror --instance <id>` reads or mirrors only that instance, and exits 2 for an id that is not a mirror.
`features/jroles/units/jroles-mirror.timer` runs `jroles mirror` every 5 minutes, through `jroles-mirror.service`.
The install (`jinstall`) links and enables both units with the jbus units.
`jinstall --check` prints `ok optional mirror <home>`, or `old optional mirror <home> -> <the first line of --check>` while the mirror differs.

Before `jbus` launches a crew on a mirror instance, or moves a capped thread onto one, it runs `jroles mirror --check --instance <id>`.
If the check finds a difference, `jbus` runs `jroles mirror --instance <id>` once and checks again.
`jbus` skips an instance that still differs for the rest of the pass, and prints `wait <slug>: <id> is not mirrored`.
The launch or the move goes to the next instance of the pool with headroom, or waits for a later pass.
