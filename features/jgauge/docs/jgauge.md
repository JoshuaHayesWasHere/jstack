# jgauge

`jgauge` tells you what a thread cost in tokens, and whether the machine and your Claude plan have room for one more thread.
jstack runs `jgauge room` before each launch.
jstack also runs each test command under one of jgauge's machine-wide test slots.
The slots stop many threads at once from overloading the machine or using up the plan.

## What it reads and sends

- `jgauge session` and `jgauge context` read only the transcripts Claude Code writes under `~/.claude/projects/`.
- `jgauge spend` reads T3 Code's store, `~/.t3/userdata/statev2.sqlite`, opened read-only.
- `jgauge room` reads `/proc`, `df`, your role map and the ledger files of your plan's limits.
  On macOS it reads `sysctl` and `vm_stat` in place of `/proc`, and no `df`.
- `jgauge limits` reads your Claude OAuth access token and calls Anthropic's usage API with it.
  The Claude homes are `~/.claude` and each home that `~/.config/jstack/providers.json` declares.
  For each home, it reads the token from `<home>/.credentials.json`.
  It then calls `GET https://api.anthropic.com/api/oauth/usage`, which is the call Claude Code makes for its usage command.
  Where the token has expired, it reads the usage response that Claude Code cached in that home's `.claude.json` instead.
  It never refreshes, writes or prints a token.
  The install (`jinstall`) enables `jgauge-limits.timer`, which runs `jgauge limits` every 2 minutes.
  To stop the calls on Linux, run `systemctl --user disable --now jgauge-limits.timer`.
  On macOS, run `launchctl bootout gui/$(id -u)/jstack.jgauge-limits`.
  After that, two writers update the ledger: the status line command, and `jbus` when an account reaches a cap ([jroles](../../jroles/docs/jroles.md#the-ledger)).
  Each `jinstall` run enables the timer on Linux, or loads the agent on macOS, so the next run turns it back on.
  Until then, `jinstall --check` reports `jgauge-limits.timer is not enabled` on Linux, or `jstack.jgauge-limits is not loaded` on macOS.

## See what a thread cost

1. Find the thread's transcript, `~/.claude/projects/<project>/<session>.jsonl`.
2. Run `jgauge session ~/.claude/projects/<project>/<session>.jsonl`.
   It prints a row for the session, a row for each subagent that the session started, and the total.

To get the same report as JSON, add `--format json`.

## See what Claude spent, and when every account was capped

Run `jgauge spend --day <YYYY-MM-DD>`, or `jgauge spend --since <time> --until <time>` for any span, in local time.
Add `--project <name>` to count only one T3 project's threads.
It prints the spend of every Claude run that started in the period, in units: uncached input x1, cache write x1.25, cache read x0.1, output x5, and an Opus run x5/3.
The spend is split by kind of run, by instance and by five-hour window.
The kinds are first crew run, reviews, fix rounds, jbus sends, homes, scouts and capped failures.
A crew's later run is a fix round or a jbus send by the key jbus put in the message it sent, and by that message's text where the key says nothing.
A five-hour window ends at the reset that a five-hour usage-limit failure names, and otherwise starts at the first run outside any window.
Last, for each day it prints the minutes in which every Claude instance that ran in the week was capped.
An instance is capped from each usage-limit failure to the reset that failure names.

## Check for room before you start a thread

1. Run `jgauge room`.
2. When it prints `go`, start the thread.
   When it prints `wait: ` and a reading, wait until that reading is back on the safe side of its threshold.
   [`jgauge room` prints `wait:`](troubleshooting/jgauge-room-prints-wait.md) explains each reading and its threshold.

To make `jgauge room` keep checking until there is room, run `jgauge room --wait <seconds>`.

## Run a test command under a slot

Run `jgauge test-slot -- <command>`.
It waits for one of the machine-wide test slots, runs the command, and exits with the command's exit code.
For a short targeted run, use the short lane, `jgauge test-slot --short -- <command>`.
A short run never waits for a slot that a whole suite holds.
The command runs with `JGAUGE_TEST_SLOT` set to its lane, `full` or `short`, so a TLC model check it starts takes no second slot.

To change how many slots there are, see [The limits and how to change them](jgauge/change-a-limit.md).

## The commands

| Command | What it does |
|---|---|
| `jgauge session [--format json] <project>/<session>.jsonl` | Prints what one thread cost: a row for the session, a row for each subagent it started (found under `<session>/subagents/`), and the total. It prints a table, and with `--format json` the same report as JSON. |
| `jgauge context <project>/<session>.jsonl` | Prints one number: how full the thread's context is now. It is the input side of the transcript's last call, and 0 for a transcript with no call. `features/home/hooks/home-gauge.sh` tells a home the same count, which it works out with `jq`. |
| `jgauge spend [--day <date> \| --since <time> --until <time>] [--project <name>] [--store <path>]` | Prints Claude's spend in units by kind, by instance and by five-hour window, and the minutes each day with every Claude instance capped ("See what Claude spent, and when every account was capped"). The day is today by default. |
| `jgauge room` | Prints `go`, or `wait: ` and the first reading with no room ("jgauge room"). |
| `jgauge limits` | Reads each Claude account's five-hour and weekly use into the ledger, ahead of any cap ("jgauge limits"). |
| `jgauge limits --check` | Reads no account: prints `stale <instance>: <why>` for each Claude instance whose ledger file is missing or was written 15 min ago or more, and exits 1 when there is one. |
| `jgauge sample` | Appends one row of load and pressure to the log ("jgauge sample"). |
| `jgauge sample --report [--since <time>] [--until <time>] [--pressure <line>]` | Counts the rows of the log ("jgauge sample"). |
| `jgauge sizes` | Prints the machine's three sizes, `test_slots`, `short_slots` and `max_running`, each as its caller gets it and where it came from (a flag or `TEST_SLOTS`, `~/.config/jstack/machine.toml` or jbus's config, else derived from the processors of `/proc/stat` and `MemTotal`, or on macOS `hw.ncpu` and `hw.memsize` of `sysctl`), with the derived value beside an override, then room's six lines. [The limits and how to change them](jgauge/change-a-limit.md) has each one. |
| `jgauge test-slot [--slots N] -- <command>` | Runs the command while it holds one of N machine-wide test slots, and ends with the command's exit code. A slot is a lock file, `~/.local/state/locks/test-slot.<n>.lock`. When all are held it prints `test-slot: waiting for one of <N> slots` on stderr and waits. N is `--slots`, else `TEST_SLOTS`, else `test_slots` in `~/.config/jstack/machine.toml`, else what the machine derives: every slot at once runs at most one desk worker a processor, 4 on most machines of 8 cores or more, 5 on 10, 11 or 15. |
| `jgauge test-slot --short -- <command>` | The same, in the short lane: one of the slots of its own (`short_slots`, which `jgauge sizes` prints), lock files `~/.local/state/locks/test-slot-short.<n>.lock`, which no full run takes, so a short run never waits behind a full suite. When all are held it prints `test-slot: waiting for one of <n> short slots`. `jgauge` stops a command still running at the lane's time limit (`SHORT_LIMIT_SECONDS`), and the run ends 124 and says so on stderr. It does not take `--slots`. |
| `jgauge test-slot [--short \| --slots N] --thread <id> -- <command>` | The same, for a thread that must not wait in a call. It tries once. With a slot free it runs the command as above and takes the thread out of the waiters. With every slot of the lane taken, or every free one held for a woken waiter of another thread, it registers the thread as a waiter (thread id, lane, command) in `~/.local/state/locks/test-slot-waiters.json`, prints one line saying it waits and that jbus will wake it, and ends 76. `jbus poll` sends the oldest waiter on a lane one message when a slot of the lane is free (`slotwait.wake`, features/jbus/docs/jbus.md), and the thread runs the same command again. A run that takes its slot is on record in `~/.local/state/locks/test-slot-holders.json` (thread id, the command's pid, lane, command, start) while its command runs, and with its end and exit code once the command ends, however it ends: jbus counts the thread as at work while the run holds the slot, and wakes it once when the run ends (`slotwait.wake_ended`). `JGAUGE_LOCKS_DIR` moves the lock files, the waiters file and the holders file, for a test. |
| `jgauge test-slot --waiters` | Prints the registered waiters, oldest wait first: the thread, the lane, since when, when it was woken, and its command. |
| `jgauge check [--thread <id>] [--wait <seconds>] < <the check command>` | Starts the check command it reads from stdin on this worktree, under a slot of the full lane, in a session of its own, or joins the run an earlier call started, and waits on it for up to 540 s; it prints `started`, `joined` or `checked`, then `waiting` (exit 76, with every slot taken, the thread registered as with `test-slot --thread`), `stale` (exit 75, the worktree changed while it ran), `done: the check exited <n>` (exit n), `running` or `lost`, and keeps its files in `<git dir>/crew-check/`: `pid`, `out`, `exit`, `tree` (the worktree's tree, written with an index of its own), `told` and `run`. |
| `jgauge proof --dir <dir> --kept <head> [--thread <id>] [--wait <seconds>] < <the proof>` | The same for a reviewer's proof, in the short lane, only while the checkout is at `<head>` with no rebase going on (else `unproven:`, exit 1); it runs the proof with `D` set to `<dir>`, prints `exit <n>`, the last 5 lines, `unproven: the head moved under the proof` when the head moved, and `git status --porcelain`, ends 0 on that answer, and keeps `proof.pid`, `proof.out`, `proof.exit`, `proof.key`, `proof.told` and `proof.cmd` in `<dir>`. |

### jgauge room

`jgauge room` prints `go`, or `wait: ` and the first reading with no room.
It checks these readings, each against its line:

- the one-minute load at or over 200% of the cores, a second check in case CPU pressure cannot be read
- CPU pressure (`some avg60` of `/proc/pressure/cpu`) at or over 40
- under 6 GB of memory available
- memory pressure (`some avg60`) at or over 10
- more than 85% of the file slots of `/tmp` used
- the plan's five-hour or weekly limit at or over your `headroom`, which `config.toml` sets and which is 90% when not set

`jgauge room` passes `headroom` to `room.sh` as `HEADROOM`.
If `jgauge room` cannot read a machine reading, it prints `wait: `.
If it cannot read a plan limit, it does not wait on that limit.
It prints `go`, and writes a `note: ` line on stderr.

On macOS, which has no `/proc`, it reads the load from `sysctl -n vm.loadavg`, the cores from `sysctl -n hw.ncpu`, and the memory available from `vm_stat`, as its free, inactive and speculative pages.
macOS has no pressure lines and APFS no fixed count of file slots, so on macOS the CPU pressure, the memory pressure and the file slots are not read and hold no launch.
On Linux a pressure file that cannot be read still prints `wait: `.
On macOS `jgauge room` also skips its sweep of stale pytest runs from a full `/tmp`: the sweep finds the runs a live process holds through `/proc`, so with no `/proc` every run would look unheld.

| Flag | What it does |
|---|---|
| `jgauge room --wait <seconds>` | Looks again until the answer is `go` or that long has passed, then prints the last answer and exits 0 on `go` and 75 on a `wait: `. |
| `jgauge room --wait <seconds> --every <seconds>` | With `--wait`, sets the pause between two looks, 15 seconds by default. |
| `jgauge room --light` | Skips the load and the CPU pressure and keeps every other reading. A review runs it this way, since a review is about 2% of one core and its proof runs in the short test lane. |
| `jgauge room --role <role>` | Reads the plan limits of each instance of that role's pool, from its ledger file `<LIMITS>.<id>` ([jroles](../../jroles/docs/jroles.md#the-ledger)), and waits on them only while every instance of a line's pool is full. The `wait: ` names each one and the first reset, and with one full and another free it prints `go` with a `note: ` naming both. With no `--role` it reads the crew's pool, and a role with no pool reads `claudeAgent`'s file, the one `LIMITS` names. |
| `jgauge room --instance <id>` | Reads that one instance's file in place of a pool. `jbus` uses it for the instance a launch goes to. |

`features/jgauge/src/jgauge/room.sh` is the only implementation of the room check.

### jgauge limits

`jgauge limits` reads each Claude account's five-hour and weekly use and writes it to the ledger ([jroles](../../jroles/docs/jroles.md#the-ledger)), before the account reaches a cap.
The accounts are the Claude instances of `~/.config/jstack/providers.json`, each at its `config.homePath`.
When no instance of the file has `~/.claude` as its home, the accounts also include `claudeAgent` at `~/.claude`.
For each account, it calls `GET https://api.anthropic.com/api/oauth/usage` with the home's own access token from `<home>/.credentials.json`, while the token has not expired.
When the token has expired, it reads `cachedUsageUtilization`, the answer Claude Code cached in the home's `.claude.json` (`~/.claude.json` for `~/.claude`).
It uses the cached response only while the response is under 15 minutes old and belongs to the account signed in to that home.
It never refreshes, writes or prints a token, and never writes either file.
It rounds each reset time down to the whole second, as the other writers do.
The ledger treats resets under 5 minutes apart as one window, because the endpoint's reset time moves by a second from call to call.
It prints `<instance> from the <endpoint or cache>: <shares>, into <file>`, sets the file's time to now, and exits 0.
If neither the endpoint nor the cache has usage for a home, it writes nothing and prints `stale <instance>: <why>`.
The home's last ledger line stays in place.
A test can set `JGAUGE_USAGE_URL` to name another endpoint.
`features/jgauge/units/jgauge-limits.timer` runs it every 2 minutes, and 1 minute after boot.
The install (`jinstall`) links and enables the timer when it links and enables the jbus units.

### jgauge sample

`jgauge sample` appends one row to `~/.local/state/jgauge/load.tsv`, a TSV file with a header that names its columns.
`JGAUGE_LOAD_LOG` sets another path for the log.
The columns are, in order:

- the time in seconds since the epoch
- the number of cores
- the three loads of `/proc/loadavg`, or of `sysctl -n vm.loadavg` on macOS
- `some` and `full`, each as `avg10` and `avg60`, of `/proc/pressure/cpu`, `memory` and `io`, empty on macOS, which has no pressure lines
- the file slots of `/tmp`, and how many of them are used

`TMPFS` sets another path in place of `/tmp`.
When `jgauge sample` cannot read a file, it leaves that file's fields empty.
If the log predates the two `/tmp` columns, `jgauge sample` rewrites it once and leaves those columns empty in the old rows.
`PROC` sets another path in place of `/proc`, as it does for `room.sh`.
The log holds at most 30 days of rows.
Once its first row is older than that, `jgauge sample` rewrites the log with the last 29 days, about once a day.
`features/jgauge/units/jgauge-sample.timer` runs it every 15 seconds, so the log gets a row every 15 to 16 seconds.
The timer sets `OnUnitActiveSec=15s` and `AccuracySec=1s`.
It also sets `OnBootSec=1min` for the first run, since `OnUnitActiveSec` counts from the last start.
A week of samples is a little under 40,320 rows.
On Linux each run adds its start and finish lines to the user journal.
On macOS each run writes them to `~/Library/Logs/jstack/jstack.jgauge-sample.log`.
The install (`jinstall`) links and enables the timer with the jbus units.

`jgauge sample --report` reads the rows of the log from `--since` up to `--until`.
Each bound is seconds since the epoch, or an ISO date or time in local time with no zone.
The report first prints the number of rows, their span, and how many rows the span would hold at one row every 15 seconds.
It then counts the rows where CPU pressure (`some avg60`) was under `--pressure`, 10 by default, and the one-minute load was at or over the load line of `jgauge room`.
That line is `LOAD` in `room.sh`, 200% of the cores, rounded the way `room.sh` rounds it.
The report gives that count, its share of the rows read, and its share of the rows over the load line.
The count shows how often `jgauge room` held a launch on load alone while CPU pressure was under its line.
The report prints the count of rows with no load or no CPU pressure as a separate output line, and leaves those rows out of the load count.
Then it prints the highest CPU pressure and memory pressure, each with how many rows were at or over room's line for it, the highest load as a share of the cores, and the highest `/tmp` use with how many rows were over room's line.
Last, it prints what jbus recorded in the span, from each project's `events.jsonl` under `JBUS_STATE_DIR`:

- the `stall` events
- the threads woken from a wait for a test slot, and how many of them waited over 5 minutes
- the rows that jbus gated because `jgauge room` found no room

For a span with no rows, the report prints that last part only when both `--since` and `--until` are given.

## How jstack uses it

The `home` skill runs `jgauge room` before a launch, the `pr-review` skill runs it before a review, and `jbus` runs it before each launch.
A crewmate runs the check command that `notes.md` names.
It runs that command once, under a test slot, as `jgauge check`, with the check command on stdin.
A reviewer's proof runs in the short lane as `jgauge proof`, with the proof on stdin.
A crewmate's targeted test runs run in the short lane, as `jgauge test-slot --short -- uv run pytest <files>`.
A thread's step calls `jgauge check` and `jgauge proof` so that it holds no delete and no inner shell, which Claude Code asks the user about before it runs them (`features/repo-guards/tests/test_blocks_ask_nothing.py`).
The check command never runs in the short lane.

## How it counts tokens

The counting rule is in `features/jgauge/src/jgauge/transcript.py`.
[What `jgauge` reads from a transcript](meter-findings.md) records what two probe sessions of one version of Claude Code showed, and the rule follows from those observations.

- **A call** is one `message.id`.
  A message has one line per content block, so `jgauge` never counts lines.
  When a message id appears in two transcripts of one report, `jgauge` counts it once.
- **Total** is input, cache write, cache read and output added up.
- **Peak context** is the largest input side (input plus cache read plus cache write) of any one call.
  Across rows it is the largest value, never a sum.
- **Context** is the input side of the last call, which is what the next call sends again.
- **A floor** is the output of a call that has no finished line in the transcript.
  `jgauge` includes it in the total as the least that the call's output can be.
  A note under the table says how many calls and how many tokens are floors.
  `jgauge` never estimates a count upward.

A subagent's last call often has no finished line in its own transcript, so its output is a floor.
`jgauge session` on a reviewer thread counts the whole review in the thread's own row, because a reviewer starts no subagent.

## The limits writer

`features/jgauge/hooks/limits.sh` is a status line command, one of the ledger's three writers.
The other two are `jgauge limits`, which writes the ledger ahead of time every two minutes, and `jbus`, which writes it when an account reaches a cap ([jroles](../../jroles/docs/jroles.md#the-ledger)).
Claude Code pipes its status JSON to the script.
The script writes the plan's five-hour and weekly limits to the ledger file of the account the session runs as.
That account is the instance of `~/.config/jstack/providers.json` whose `config.homePath` is the session's `CLAUDE_CONFIG_DIR`.
For a session in `~/.claude`, the account is `claudeAgent`.
`claudeAgent`'s file is `~/.local/state/claude/limits`, or the path in `LIMITS`.
Another instance's file is `<that path>.<instanceId>`.
The script writes nothing for an account the inventory does not declare, so the ledger never records one account's limits as another's.
`jgauge room` reads those files ([jroles](../../jroles/docs/jroles.md#the-ledger)).
The script prints nothing and exits 0 on any input, so the status line stays empty.

The install (`jinstall`) sets it as `statusLine` in `~/.claude/settings.json` only when that key is absent:

```json
{
  "statusLine": {
    "type": "command",
    "command": "sh '<layout>/hooks/limits.sh'"
  }
}
```

The install leaves a status line of your own as it is.
[Configuration](../../jinstall/docs/configuration.md#the-limits-file) shows how to call the script from it.
