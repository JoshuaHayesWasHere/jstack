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
  The Claude homes are `~/.claude` and each home that T3 Code's `providerInstances` lists.
  For each home, it reads the token from `<home>/.credentials.json`.
  It then calls `GET https://api.anthropic.com/api/oauth/usage`, which is the call Claude Code makes for its usage command.
  Where the token has expired, it reads the usage response that Claude Code cached in that home's `.claude.json` instead.
  It never refreshes, writes or prints a token.
  The install (`jinstall`) enables `jgauge-limits.timer`, which runs `jgauge limits` on the schedule that [jgauge limits](#jgauge-limits) gives.
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
It prints the spend of every Claude run that started in the period, in units.
The help of `jgauge spend` prints the rate of each kind of token.
`jgauge.spend` sets the rates, as `PLAIN, WRITTEN, CACHED, OUTPUT` and `OPUS`.
The spend is split by kind of run, by instance and by five-hour window.
The kinds are first crew run, reviews, fix rounds, jbus sends, homes, scouts and capped failures.
A crew's later run is a fix round or a jbus send by the key jbus put in the message it sent, and by that message's text where the key says nothing.
A five-hour window ends at the reset that a five-hour usage-limit failure names, and otherwise starts at the first run outside any window.
Last, for each day it prints the minutes in which every Claude instance that ran in the week was capped.
An instance is capped from each usage-limit failure until the reset that failure names, or until the start of the next run it completed after the failure, whichever comes first: a run that completes shows the cap was over.

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
It runs with `TMPDIR` set to the slot's own temporary directory, `/var/tmp/jgauge-<uid>/<hash of the lock directory>/test-slot.<n>` (or `test-slot-short.<n>`), which is emptied before the command starts and removed once it ends.
That directory is on disk under `/var/tmp`, not under `/tmp`, since a suite's basetemp runs to hundreds of MiB and `/tmp` may be a tmpfs whose per-user quota it fills.
It is not beside the lock file, since a `TMPDIR` with a hidden directory in it, such as `~/.local`, makes asar unpack no native binaries.
Once it lets the slot go, it sweeps `/tmp` (`TMPFS`) as `jgauge room` does when `/tmp` is full, whatever share of its file slots is used: each `pytest-of-<user>/pytest-<n>` run of yours over 20 minutes old that no live process holds is removed, and stderr says `test-slot: removed <n> stale pytest directories under /tmp`.
A run outside any slot, or one that was killed, leaves its basetemp there, and pytest's own retention keeps a killed run's for days.

### What each lane holds

The short lane holds a run of one test file, the lint, a step of a crew's check, a reviewer's proof and a crew's proof of its tests: each a second or a minute.
It runs on the lane's own worker count, which `make test` takes under `JGAUGE_TEST_SLOT=short` and `proved.sh` takes in place of `-n auto`, not the desk's eighth of the processors.
Its slots are sized with the full lane's inside one core budget (`workers` in `jgauge.sizes`), so with every slot of both lanes taken their workers fit the cores, and a short run that took a full lane's workers would put the machine over them.

The full lane holds a short step's rerun after the short lane stopped it at its limit (exit 124), and another repo's check command, the one its `fresh-check` names, through `jgauge check`; `jmerge`'s guards of a merged tree take it too, with no `--thread`.
It never holds the whole suite of a repo whose check selects its tests (`scripts/select_tests.py`): CI's check runs the selection on every pull request, and the whole suite nightly and before a release.
`jgauge test-slot --thread` refuses one in such a repo, in either lane, runs nothing, ends 2 and names the touched check instead.
A whole suite is `make check`, `make check-fast` with no `PART=`, `make test` with no `TESTS=`, and `pytest` with no path, as the command's own words say (`jgauge.whole`): a command inside `sh -c` is not read.
A run with no `--thread`, by hand or by `jmerge`, is not refused.

To change how many slots there are, see [The limits and how to change them](jgauge/change-a-limit.md).

## The commands

| Command | What it does |
|---|---|
| `jgauge session [--format json] <project>/<session>.jsonl` | Prints what one thread cost: a row for the session, a row for each subagent it started (found under `<session>/subagents/`), and the total. It prints a table, and with `--format json` the same report as JSON. |
| `jgauge context <project>/<session>.jsonl` | Prints one number: how full the thread's context is now. It is the input side of the transcript's last call, and 0 for a transcript with no call. |
| `jgauge spend [--day <date> \| --since <time> --until <time>] [--project <name>] [--store <path>]` | Prints Claude's spend in units by kind, by instance and by five-hour window, and the minutes each day with every Claude instance capped ("See what Claude spent, and when every account was capped"). The day is today by default. |
| `jgauge room` | Prints `go`, or `wait: ` and the first reading with no room ("jgauge room"). |
| `jgauge limits` | Reads each Claude account's five-hour and weekly use into the ledger, ahead of any cap ("jgauge limits"). |
| `jgauge limits --check` | Reads no account: prints `stale <instance>: <why>` for each Claude instance whose ledger file is missing or was written 15 min ago or more, and exits 1 when there is one. |
| `jgauge sample` | Appends one row of load and pressure to the log ("jgauge sample"). |
| `jgauge sample --report [--since <time>] [--until <time>] [--pressure <line>]` | Counts the rows of the log ("jgauge sample"), then reports the test slots' holds from the slot log ("The slot log"). |
| `jgauge sizes` | Prints the machine's four sizes, `test_slots`, `short_slots`, `max_running` and `workers`, each as its caller gets it and where it came from (a flag or `TEST_SLOTS`, `~/.config/jstack/machine.toml` or jbus's config, else derived from the processors of `/proc/stat` and `MemTotal`, or on macOS `hw.ncpu` and `hw.memsize` of `sysctl`), with the derived value beside an override, then the `total` line, the workers the slots take of `workers` with every slot taken, then room's six lines. [The limits and how to change them](jgauge/change-a-limit.md) has each one. |
| `jgauge test-slot [--slots N] -- <command>` | Runs the command while it holds one of N machine-wide test slots, and ends with the command's exit code. A slot is a lock file, `~/.local/state/locks/test-slot.<n>.lock`. When all are held it prints `test-slot: waiting for one of <N> slots` on stderr and waits. N is `--slots`, else `TEST_SLOTS`, else `test_slots` in `~/.config/jstack/machine.toml`, else what the machine derives: what `workers` holds after the short lane, at a desk run's workers a slot (an eighth of the processors, at least 2), so that every slot of both lanes at once fits `workers`: 2 on 8 cores, 3 on 12, 4 on 24 and 5 on 64. |
| `jgauge test-slot --short -- <command>` | The same, in the short lane: one of the slots of its own (`short_slots`, which `jgauge sizes` prints), lock files `~/.local/state/locks/test-slot-short.<n>.lock`, which no full run takes, so a short run never waits behind a full suite. When all are held it prints `test-slot: waiting for one of <n> short slots`. `jgauge` stops a command still running at the lane's time limit (`SHORT_LIMIT_SECONDS`), and the run ends 124 and says so on stderr. It does not take `--slots`. |
| `jgauge test-slot [--short \| --slots N] --thread <id> -- <command>` | The same, for a thread that must not wait in a call long. In the full lane it tries once, and with no slot registers the thread as a waiter jbus wakes and ends 76; in the short lane it waits up to 300 s in the call, registers nothing, and with no slot by then ends 76 and says to run it again now ([jgauge test-slot --thread](#jgauge-test-slot---thread)). |
| `jgauge test-slot --waiters` | Prints the registered waiters of the full lane, oldest wait first: the thread, the lane, since when, when it was woken, and its command. |
| `jgauge cap-shell <pid>` | Caps the shell `<pid>` at a full slot's workers: it makes `jgauge-shell` under the shell's cgroup, with a `cpu.max` of those workers, and moves the shell into its leaf `run`. It prints nothing and ends 0, also where the shell cannot be capped (cgroup v1, a cgroup you may not write, macOS) or is already in a cgroup of jgauge's, a take's or the shell's. The crew's SessionStart hook runs it at the head of each Bash command ([How jstack uses it](#how-jstack-uses-it)). |
| `jgauge check [--thread <id>] [--wait <seconds>] < <the check command>` | Runs the check command it reads from stdin under a slot of the full lane, and waits on it for up to 540 s ([jgauge check](#jgauge-check)). |
| `jgauge proof --dir <dir> --kept <head> [--thread <id>] [--wait <seconds>] < <the proof>` | The same for a reviewer's proof, in the short lane, only while the checkout is at `<head>` with no rebase going on (else `unproven:`, exit 1); it runs the proof with `D` set to `<dir>`, prints `exit <n>`, the last 5 lines, `unproven: the head moved under the proof` when the head moved, and `git status --porcelain`, ends 0 on that answer, and keeps `proof.pid`, `proof.out`, `proof.exit`, `proof.key`, `proof.told` and `proof.cmd` in `<dir>`. |

### jgauge room

`jgauge room` prints `go`, or `wait: ` and the first reading with no room.
It checks the machine's readings, each against its line in [The limits that are fixed](jgauge/change-a-limit.md#the-limits-that-are-fixed).
It also checks the plan's five-hour and weekly limits against your `headroom`, which `~/.config/jstack/config.toml` sets and which is 90% when not set.

`jgauge room` passes `headroom` to `room.sh` as `HEADROOM`.
If `jgauge room` cannot read a machine reading, it prints `wait: `.
If it cannot read a plan limit, it does not wait on that limit.
It prints `go`, and writes a `note: ` line on stderr.

On macOS, which has no `/proc`, it reads the load from `sysctl -n vm.loadavg`, the cores from `sysctl -n hw.ncpu`, and the memory available from `vm_stat`, as its free, inactive and speculative pages.
macOS has no pressure lines and APFS no fixed count of file slots, so on macOS the CPU pressure, the memory pressure and the file slots are not read and hold no launch.
On Linux a pressure file that cannot be read still prints `wait: `.
On macOS `jgauge room` and `jgauge test-slot` also skip their sweep of stale pytest runs from `/tmp`: the sweep finds the runs a live process holds through `/proc`, so with no `/proc` every run would look unheld.

| Flag | What it does |
|---|---|
| `jgauge room --wait <seconds>` | Looks again until the answer is `go` or that long has passed, then prints the last answer and exits 0 on `go` and 75 on a `wait: `. |
| `jgauge room --wait <seconds> --every <seconds>` | With `--wait`, sets the pause between two looks, 15 seconds by default. |
| `jgauge room --light` | Skips the load and the CPU pressure and keeps every other reading. A review runs it this way, since a review is about 2% of one core and its proof runs in the short test lane. |
| `jgauge room --role <role>` | Reads the plan limits of each instance of that role's pool, from its ledger file `<LIMITS>.<id>` ([jroles](../../jroles/docs/jroles.md#the-ledger)), and waits on them only while every instance of a line's pool is full. The `wait: ` names each one and the first reset, and with one full and another free it prints `go` with a `note: ` naming both. With no `--role` it reads the crew's pool, and a role with no pool reads `claudeAgent`'s file, the one `LIMITS` names. |
| `jgauge room --instance <id>` | Reads that one instance's file in place of a pool. `jbus` uses it for the instance a launch goes to. |

`features/jgauge/src/jgauge/room.sh` is the only implementation of the room check.

### jgauge test-slot --thread

`jgauge test-slot --thread <id>` tries for a slot of the full lane once and never waits in the call.
With a slot free, it runs the command as `jgauge test-slot` does and takes the thread out of the waiters.
The lane can be full, or each free slot can be held for a woken waiter of another thread.
Then it registers the thread as a waiter (thread id, lane, command) in `~/.local/state/locks/test-slot-waiters.json`, prints one line that says it waits and that jbus will wake it, and ends 76.
When a slot of the full lane is free, `jbus poll` sends the oldest waiter one message (`slotwait.wake`, [jbus](../../jbus/docs/jbus.md)).
The thread then runs the same command again.

In the short lane the call waits for a slot in the call, for up to `SHORT_WAIT_SECONDS`, 300 s, and registers nothing.
The calls that wait take the slots freed in the order they came, and jbus knows nothing of them and wakes none of them.
A short slot is held for seconds, so the wait is short.
A call that has no slot at the ceiling prints one line, that nothing ran and to run the same command again now, in this turn, and ends 76.
The ceiling, the lane's 120 s run limit and the stop's grace fit in the 10 minutes a thread gives a slot call.
A short-lane waiter left in the waiters file by an older jgauge is dropped by jbus with one line.

A run that takes its slot is on record in `~/.local/state/locks/test-slot-holders.json` while its command runs.
The record holds the thread id, the command's pid, the lane, the command and the start.
Once the command ends, however it ends, the record gets the end and the exit code.
jbus counts the thread as at work while the run holds the slot, and wakes it once when the run ends (`slotwait.wake_ended`).
For a test, `JGAUGE_LOCKS_DIR` moves the lock files, the waiters file and the holders file.

### jgauge check

`jgauge check` reads the check command from stdin and runs it on this worktree, in a session of its own, under a slot of the full lane.
If an earlier call started the same check, it joins that run instead.
It waits on the run for up to 540 s.
It first prints `started`, `joined` or `checked`, and then one of these:

- `waiting`, exit 76: every slot is taken, and the thread is registered as a waiter, as with `test-slot --thread` in the full lane.
- `stale`, exit 75: the worktree changed while the check ran.
- `done: the check exited <n>`, exit n.
- `running` or `lost`.

It keeps its files in `<git dir>/crew-check/`: `pid`, `out`, `exit`, `tree`, `told` and `run`.
`tree` is the worktree's tree, written with an index of its own.

### jgauge limits

`jgauge limits` reads each Claude account's five-hour and weekly use and writes it to the ledger ([jroles](../../jroles/docs/jroles.md#the-ledger)), before the account reaches a cap.
The accounts are the Claude instances of T3 Code's `providerInstances`, in `~/.t3/userdata/settings.json`, each at its `config.homePath`.
When no instance of the file has `~/.claude` as its home, the accounts also include `claudeAgent` at `~/.claude`.
For each account, it calls `GET https://api.anthropic.com/api/oauth/usage` with the home's own access token from `<home>/.credentials.json`, while the token has not expired.
When the token has expired, it reads `cachedUsageUtilization`, the answer Claude Code cached in the home's `.claude.json` (`~/.claude.json` for `~/.claude`).
It uses the cached response only while the response is under 15 minutes old and belongs to the account signed in to that home.
It never refreshes, writes or prints a token, and never writes either file.
It rounds each reset time down to the whole second, as the other writers do.
The ledger treats resets under 5 minutes apart as one window, because the endpoint's reset time moves by a second from call to call.
It prints `<instance> from the <endpoint or cache>: <shares>, into <file>`, sets the file's time to now, and exits 0.
A window that the answer gives as `null` is not open, as before a session opens it.
For that window it writes no line, keeps the other window's reading, and prints `<window> not open` among the shares.
If neither the endpoint nor the cache has usage for a home, it writes nothing and prints `stale <instance>: <why>`.
The home's last ledger line stays in place.
When the endpoint answers 429, `jgauge limits` changes no line of the ledger and writes a retry time to `<ledger file>.retry`.
The retry time is the answer's `Retry-After`, or 10 minutes from now (`RETRY`) when it has none.
It does not call the endpoint for that home again before the retry time.
The file also marks that the last read of the home failed, for any reason, and a good answer from the endpoint removes it.
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

Then, when the slot log exists, the report prints the test slots over the span ("The slot log"), from `--since` or the first take, to `--until` or now.
For each lane it prints:

- the holds taken in the span, and how many of them are lost: a take with no release whose holder is gone, which counts nothing, while one still running counts to the end of the span
- the mean occupancy, the slot-seconds held in the span over its length, out of the lane's slots
- Little's law from the same holds, the takes per second times the mean hold, which a span that cuts few holds keeps near the mean occupancy
- the wait in the call, p50 and p90, of the holds taken in the span
- when a thread of the lane waited for a slot in the span, by jbus's `slot-wake` events, the mean occupancy over the time it waited, and its share of the lane's slots

Then it prints the CPU of the holds released in the span, from the release rows' `cpu_user` and `cpu_system`: the total CPU seconds by lane and by repo, user plus system, and the mean cores the total comes to over the span.
A release written before the log recorded the CPU is counted apart.
A span with no release that has the CPU prints no CPU lines.

### The slot log

`jgauge test-slot` appends one JSON row to `jgauge/slots.jsonl` beside the lock files' directory, `~/.local/state/jgauge/slots.jsonl`, each time it takes a slot and each time it lets one go, in both lanes, and it moves with the lock files when `JGAUGE_LOCKS_DIR` is set.
A run with `--thread` that finds no slot, and registers as a waiter or ends at the short lane's ceiling, takes nothing and writes no row.
Each row has:

- `at`, the time in UTC, and `event`, `take` or `release`
- `id`, the same on a take and its release, and `pid`, the `jgauge test-slot` process that holds the slot
- `lane`, `slot`, the slot's number, and `slots`, the lane's size as the caller counted it
- `thread`, empty with no `--thread`, `command` and `cwd`, which name the caller
- on a take, `waited`, the seconds the call waited for the slot, and `repo`, the name of the directory that holds the git repository `cwd` is in (for a worktree, its main checkout's), or empty outside a repository
- on a release, `code`, the command's exit code, `hold`, the seconds it held the slot, `cpu_user` and `cpu_system`, the CPU seconds that every process of the take used, in user mode and in system mode, and `left`, how many of them still ran when the row was written

The CPU is the take's whole tree, a process the command started and never waited for included, such as a test's browser that outlives its runner.
The take makes a cgroup of its own under the holder's, `jgauge-take-<id>`, and moves the holder into it before the command starts, so everything the command starts is born there; the release waits up to 2 s (`DRAIN_SECONDS`) for every process but the holder to end, then reads the cgroup's `cpu.stat`.
The count includes the holder's own CPU from the take on and its watchdog's, a few hundredths of a second.
A process still running after the drain is counted up to the release only, and shows in `left`.
A release whose cgroup cannot be read (removed under it) writes its row with no `cpu_user`, `cpu_system` or `left`, and the run ends with the command's exit code all the same.
Where the take can have no cgroup of its own (cgroup v1, a cgroup the user cannot write, macOS), the CPU is what the command's waited-for tree used plus that of each process carrying the take's id in `JGAUGE_TEST_SLOT_TAKE` whose parent is outside the take, read from `/proc`.
Until 2026-11-12 the CPU was `getrusage` of the processes the command waited for alone, which put robotica's slots at 0.18 cores where they used about 3.4.

The release row is written before the lock is let go, so a slot's next take comes after it in the log.
A log that cannot be written stops no run.
Once the first row is over 30 days old, the next row written first rewrites the log with the last 29 days.

## How jstack uses it

The `home` skill runs `jgauge room` before a launch, the `pr-review` skill runs it before a review, and `jbus` runs it before each launch.
A crewmate in a repo whose check selects no tests runs the check command that the repo's `fresh-check` names.
It runs that command once, under a test slot, as `jgauge check`, with the check command on stdin.
In a repo whose check selects its tests, as jstack's does, the crewmate's check is instead the lint and the tests its change touches, each step its own `jgauge test-slot --short` call, and a step the short lane stops at its limit runs again alone in a full slot (`features/crew/do-the-task.md`).
A reviewer's proof runs in the short lane as `jgauge proof`, with the proof on stdin.
A crewmate's targeted test runs run in the short lane, as `jgauge test-slot --short -- uv run pytest <files>`.
A thread's step calls `jgauge check` and `jgauge proof` so that it holds no delete and no inner shell, which Claude Code asks the user about before it runs them (`features/repo-guards/tests/test_blocks_ask_nothing.py`).
`jgauge check` never runs in the short lane.
Every Bash command a Claude agent runs is capped at a full slot's workers, 3 on yelena, outside any slot: the crew's SessionStart hook writes a line to `CLAUDE_ENV_FILE` that runs `jgauge cap-shell $$`, where cgroup v2 is mounted and `jgauge` is on `PATH`.
So a run that skips its slot is slowed to one slot's share in every repo.
A test slot taken from that shell is made beside the shell's cgroup, with its own cap, so heavy work in a slot runs its slot's workers.
Codex agents do not read `CLAUDE_ENV_FILE` and are not capped ([limits](limits.md)).

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
The other two are `jgauge limits`, which writes the ledger ahead of time on its timer, and `jbus`, which writes it when an account reaches a cap ([jroles](../../jroles/docs/jroles.md#the-ledger)).
Claude Code pipes its status JSON to the script.
The script writes the plan's five-hour and weekly limits to the ledger file of the account the session runs as.
That account is the instance of T3 Code's `providerInstances` whose `config.homePath` is the session's `CLAUDE_CONFIG_DIR`.
For a session in `~/.claude`, the account is `claudeAgent`.
`claudeAgent`'s file is `~/.local/state/claude/limits`, or the path in `LIMITS`.
Another instance's file is `<that path>.<instanceId>`.
The script writes nothing for an account T3's settings do not list, so the ledger never records one account's limits as another's.
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
