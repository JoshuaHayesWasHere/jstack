# jgauge

`jgauge` tells you what a thread cost in tokens, and whether the machine and your Claude plan have room for one more thread.
jstack asks it before each launch, and runs each test command under one of its machine-wide test slots, so that many threads at once do not overload the machine or use up the plan.

## What it reads and sends

- `jgauge session` and `jgauge context` read only the transcripts Claude Code writes under `~/.claude/projects/`.
- `jgauge room` reads `/proc`, `df`, your role map and the ledger files of your plan's limits.
- `jgauge limits` reads your Claude OAuth access token and calls Anthropic's usage API with it.
  For each Claude home, `~/.claude` and each one `~/.config/jstack/providers.json` declares, it reads the token from `<home>/.credentials.json` and asks `GET https://api.anthropic.com/api/oauth/usage`, the call Claude Code makes for its usage command.
  Where the token has expired, it reads the answer Claude Code cached in that home's `.claude.json` instead.
  It never refreshes, writes or prints a token.
  The install (`jinstall`) enables `jgauge-limits.timer`, which runs it every 2 minutes.
  To stop the calls, run `systemctl --user disable --now jgauge-limits.timer`: the ledger is then written only by the status line and by `jbus` at a cap ([jroles](../../jroles/docs/jroles.md#the-ledger)).

## See what a thread cost

1. Find the thread's transcript, `~/.claude/projects/<project>/<session>.jsonl`.
2. Run `jgauge session ~/.claude/projects/<project>/<session>.jsonl`.
   It prints a row for the session, a row for each subagent it started, and the total.

To get the same report as JSON, add `--format json`.

## Check for room before you start a thread

1. Run `jgauge room`.
2. On `go`, start the thread.
   On `wait: ` and a reading, wait for that reading to clear: [`jgauge room` prints `wait:`](troubleshooting/jgauge-room-prints-wait.md) says what each line means.

To wait for room in place, run `jgauge room --wait <seconds>`.

## Run a test command under a slot

Run `jgauge test-slot -- <command>`.
It waits for one of the machine-wide test slots, runs the command and ends with its exit code.
For a short targeted run, use the short lane, `jgauge test-slot --short -- <command>`, which never waits behind a whole suite.

To change how many slots there are, see [The limits and how to change them](jgauge/change-a-limit.md).

## The commands

| Command | What it does |
|---|---|
| `jgauge session [--format json] <project>/<session>.jsonl` | Prints what one thread cost: a row for the session, a row for each subagent it started (found under `<session>/subagents/`), and the total. It prints a table, and with `--format json` the same report as JSON. |
| `jgauge context <project>/<session>.jsonl` | Prints one number: how full the thread's context is now. It is the input side of the transcript's last call, and 0 for a transcript with no call. `features/home/hooks/home-gauge.sh` tells a home the same count, which it works out with `jq`. |
| `jgauge room` | Prints `go`, or `wait: ` and the first reading with no room ("jgauge room"). |
| `jgauge limits` | Reads each Claude account's five-hour and weekly use into the ledger, ahead of any cap ("jgauge limits"). |
| `jgauge limits --check` | Reads no account: prints `stale <instance>: <why>` for each Claude instance whose ledger file is missing or was written 15 min ago or more, and exits 1 when there is one. |
| `jgauge sample` | Appends one row of load and pressure to the log ("jgauge sample"). |
| `jgauge sample --report [--since <time>] [--until <time>] [--pressure <line>]` | Counts the rows of the log ("jgauge sample"). |
| `jgauge sizes` | Prints the machine's three sizes, `test_slots`, `short_slots` and `max_running`, each as its caller gets it and where it came from (a flag or `TEST_SLOTS`, `~/.config/jstack/machine.toml` or jbus's config, else derived from the processors of `/proc/stat` and `MemTotal`), with the derived value beside an override, then room's six lines. [The limits and how to change them](jgauge/change-a-limit.md) has each one. |
| `jgauge test-slot [--slots N] -- <command>` | Runs the command while it holds one of N machine-wide test slots, and ends with the command's exit code. A slot is a lock file, `~/.local/state/locks/test-slot.<n>.lock`. When all are held it prints `test-slot: waiting for one of <N> slots` on stderr and waits. N is `--slots`, else `TEST_SLOTS`, else `test_slots` in `~/.config/jstack/machine.toml`, else what the machine derives: every slot at once runs at most one desk worker a processor, 4 on most machines of 8 cores or more, 5 on 10, 11 or 15. |
| `jgauge test-slot --short -- <command>` | The same, in the short lane: one of the slots of its own (`short_slots`, which `jgauge sizes` prints), lock files `~/.local/state/locks/test-slot-short.<n>.lock`, which no full run takes, so a short run never waits behind a full suite. When all are held it prints `test-slot: waiting for one of <n> short slots`. A command still running at the lane's time limit (`SHORT_LIMIT_SECONDS`) is stopped and the run ends 124, saying so on stderr. It does not take `--slots`. |
| `jgauge test-slot [--short \| --slots N] --thread <id> -- <command>` | The same, for a thread that must not wait in a call. It tries once. With a slot free it runs the command as above and takes the thread out of the waiters. With every slot of the lane taken it registers the thread as a waiter (thread id, lane, command) in `~/.local/state/locks/test-slot-waiters.json`, prints one line saying it waits and that jbus will wake it, and ends 76. `jbus poll` sends the oldest waiter on a lane one message when a slot of the lane is free (`slotwait.wake`, features/jbus/docs/jbus.md), and the thread runs the same command again. `JGAUGE_LOCKS_DIR` moves the lock files and the waiters file, for a test. |
| `jgauge test-slot --waiters` | Prints the registered waiters, oldest wait first: the thread, the lane, since when, when it was woken, and its command. |

### jgauge room

`jgauge room` prints `go`, or `wait: ` and the first reading with no room.
The readings, each with its line:

- the one-minute load at or over 200% of the cores, a backstop;
- CPU pressure (`some avg60` of `/proc/pressure/cpu`) at or over 40;
- under 6 GB of memory available;
- memory pressure (`some avg60`) at or over 10;
- more than 85% of the file slots of `/tmp` used;
- the plan's five-hour or weekly limit at or over your `headroom` (`config.toml`, 90% with none), which `jgauge room` hands `room.sh` as `HEADROOM`.

A machine reading it cannot read is a `wait: `.
A plan limit it cannot read stops nothing: `jgauge room` then prints `go` with a `note: ` line on stderr.

| Flag | What it does |
|---|---|
| `--wait <seconds>` | Looks again until the answer is `go` or that long has passed, then prints the last answer and exits 0 on `go` and 75 on a `wait: `. |
| `--every <seconds>` | With `--wait`, sets the pause between two looks, 15 seconds with none. |
| `--light` | Skips the load and the CPU pressure and keeps every other reading. A review asks it so, since a review is about 2% of one core and its proof runs in the short test lane. |
| `--role <role>` | Reads the plan limits of each instance of that role's pool, from its ledger file `<LIMITS>.<id>` ([jroles](../../jroles/docs/jroles.md#the-ledger)), and waits on them only while every instance of a line's pool is full. The `wait: ` names each one and the first reset, and with one full and another free it prints `go` with a `note: ` naming both. With no `--role` it reads the crew's pool, and a role with no pool reads `claudeAgent`'s file, the one `LIMITS` names. |
| `--instance <id>` | Reads that one instance's file in place of a pool: `jbus` asks it for the instance a launch goes to. |

`features/jgauge/src/jgauge/room.sh` is the one copy of the room check.

### jgauge limits

`jgauge limits` reads each Claude account's five-hour and weekly use into the ledger ([jroles](../../jroles/docs/jroles.md#the-ledger)), ahead of any cap.
The accounts are the Claude instances of `~/.config/jstack/providers.json`, each at its `config.homePath`, and `claudeAgent` at `~/.claude` where none is there.
For each, it asks `GET https://api.anthropic.com/api/oauth/usage` with the home's own access token from `<home>/.credentials.json`, while the token has not expired.
Otherwise it takes the answer Claude Code cached in the home's `.claude.json` (`~/.claude.json` for `~/.claude`), `cachedUsageUtilization`, while that answer is under 15 min old and of the account signed in there.
It never refreshes, writes or prints a token, and never writes either file.
Each reset is floored to the second, as the other writers do, and the ledger takes resets under 5 min apart as one window, since the endpoint's reset moves by a second from call to call.
It prints `<instance> from the <endpoint or cache>: <shares>, into <file>`, sets the file's time to now, and exits 0.
A home neither source answers for writes nothing and prints `stale <instance>: <why>`, so its last line stands.
`JGAUGE_USAGE_URL` names another endpoint, for a test.
`features/jgauge/units/jgauge-limits.timer` runs it every 2 min, and 1 min after boot, and the install (`jinstall`) links and enables it with the jbus units.

### jgauge sample

`jgauge sample` appends one row to `~/.local/state/jgauge/load.tsv` (`JGAUGE_LOAD_LOG` moves it), a TSV under a header of its columns.
The columns are the time in seconds since the epoch, the cores, the three loads of `/proc/loadavg`, `some` and `full` `avg10` and `avg60` of `/proc/pressure/cpu`, `memory` and `io`, then the file slots of `/tmp` and how many are used (`TMPFS` moves it).
A file it cannot read leaves its fields empty.
A log from before the two `/tmp` columns is written again once, with them empty in its old rows.
`PROC` moves `/proc`, as for `room.sh`.
The log keeps 30 days at most: once its first row is older, the sampler writes it again with the last 29, about once a day.
`features/jgauge/units/jgauge-sample.timer` runs it every 15 s (`OnUnitActiveSec=15s`, `AccuracySec=1s`, and `OnBootSec=1min` for the first run, since `OnUnitActiveSec` counts from the last start), so a row comes every 15 to 16 s and a week is a little under 40,320 rows.
Each run adds its start and finish lines to the user journal.
The install (`jinstall`) links and enables the timer with the jbus units.

`jgauge sample --report` prints the rows of the log from `--since` and before `--until` (seconds since the epoch, or an ISO date or time, local with no zone), their span, and how many rows a row every 15 s would give.
It then counts the rows that had the one-minute load at or over room's line (`LOAD` in `room.sh`, 200% of the cores, rounded as `room` rounds it) while CPU pressure (`some avg60`) was under `--pressure` (10 with none): a count, its share of the rows read, and its share of the rows over the load line.
That count answers how often load held a launch that CPU pressure would have let go.
A row with no load or no CPU pressure is counted apart and not read.
Then it prints the highest CPU pressure, memory pressure, load and `/tmp` use, each with how many rows were at or over room's own line for it.
Last, it prints what jbus recorded in the span from each project's `events.jsonl` under `JBUS_STATE_DIR`: its `stall` events, the threads woken from a wait for a test slot with how many waited over 5 minutes, and the rows gated for no room.
A span with no rows still gets that last line.

## How jstack uses it

The `home` skill runs `jgauge room` before a launch, the `pr-review` skill before a review, and `jbus` before each launch.
A crewmate runs the check command `notes.md` names once, under a test slot: `jgauge test-slot -- <the check command>`.
A reviewer's proof and a crewmate's targeted test runs go in the short lane: `jgauge test-slot --short -- uv run pytest <files>`.
The check command never does.

## How it counts tokens

The counting rule is in `features/jgauge/src/jgauge/transcript.py`.
[What `jgauge` reads from a transcript](meter-findings.md) has the observations behind it, from two probe sessions of one version of Claude Code.

- **A call** is one `message.id`. A message has one line per content block, so `jgauge` never counts lines. It counts a message id seen in two transcripts of one report once.
- **Total** is input, cache write, cache read and output added up.
- **Peak context** is the largest input side (input plus cache read plus cache write) of any one call. Across rows it is the largest, never a sum.
- **Context** is the input side of the last call, which is what the next call sends again.
- **A floor** is the output of a call that has no finished line in the transcript. `jgauge` includes it in the total as the least that call's output can be, and a note under the table says how many calls and how many tokens. It estimates nothing upward.

A subagent's last call often has no finished line in its own transcript, so its output is a floor. `jgauge session` on a reviewer thread counts the whole review in the thread's own row: a reviewer starts no subagent.

## The limits writer

`features/jgauge/hooks/limits.sh` is a status line command, one of the ledger's three writers: `jgauge limits` writes it ahead of time, every two minutes, and `jbus` at a cap ([jroles](../../jroles/docs/jroles.md#the-ledger)).
Claude Code pipes its status JSON to the script, and the script writes the plan's five-hour and weekly limits to the ledger file of the account the session runs as.
The account is the instance of `~/.config/jstack/providers.json` whose `config.homePath` is the session's `CLAUDE_CONFIG_DIR`, or `claudeAgent` for `~/.claude`.
`claudeAgent`'s file is `~/.local/state/claude/limits`, or the path in `LIMITS`, and another instance's is `<that path>.<instanceId>`.
An account the inventory does not declare writes nothing, so one account's limits never stand for another's.
`jgauge room` reads those files ([jroles](../../jroles/docs/jroles.md#the-ledger)).
The script prints nothing and exits 0 on any input, so the status line it leaves is empty.

The install (`jinstall`) sets it as `statusLine` in `~/.claude/settings.json` only when that key is absent:

```json
{
  "statusLine": {
    "type": "command",
    "command": "sh '<layout>/hooks/limits.sh'"
  }
}
```

A status line of your own is left as it is.
[Configuration](../../jinstall/docs/configuration.md#the-limits-file) shows how to call the script from it.
