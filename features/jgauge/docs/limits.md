# Limits

> This page records the measurements that set jstack's defaults.
> The owner took them on their own machine, and the page names that machine's setup.
> It does not describe your machine.
> [The limits and how to change them](jgauge/change-a-limit.md) describes each limit for any install, and how to change it.

This page lists every number in jstack that caps work: where it is set, what it protects, and the measurement behind it.
The machine is yelena: 24 processors (Intel Core Ultra 7 270K Plus, no SMT), 62 GiB, and a btrfs root with no inode limit.
Its `/tmp` is a 32 GB tmpfs of 1,048,576 file slots.
The measurements are from 2026-10-20 unless a row says otherwise.
"The busy night" is 2026-10-19 22:00 to 2026-10-20 01:00 ET.

Three of the numbers are sizes of the machine, and `jgauge.sizes` derives them from its processors and memory ([Configuration](../../jinstall/docs/configuration.md#the-machines-sizes)).
`jgauge sizes` prints the three values as their callers get them, then prints the lines of `jgauge room`.
Put a local value in `~/.config/jstack/machine.toml`, or, for `max_running`, in `~/.config/jbus/config.toml`.
Never put it in jstack's source.
Every other number here is a design choice, a share of the machine that means the same on any machine, or a limit of another system.
Each row says which.

When a row's Where is a file of this repo, its Value is text in that file, and the Value names the symbol to search for.
`features/jgauge/tests/test_limits_doc.py` checks that the file still holds the value.

## The measurements

The suite is jstack's own, 6,646 tests, run the way the check command runs it: `pytest -n 6 --dist worksteal -m "not browser"`.
Each copy ran in its own worktree and held the heavy-suite lock, so that nothing else heavy ran.

| Suites at once | Wall per suite | CPU per suite | CPU pressure, some avg60, at most | 1-minute load, at most | `/tmp` files used, at most |
|---|---|---|---|---|---|
| 1 | 89 to 94 s | 456 to 483 s | 1.3 | 8 | 172,000 (16%) |
| 3 | 97 s | 493 s | 9 | 19 | 253,000 (24%) |
| 4 | 113 and 133 s | 530 and 570 s | 17 and 29 | 27 and 33 | 302,000 to 329,000 (29 to 31%) |
| 5 | 135 and 137 s | 560 and 565 s | 30 | 34 | 343,000 to 344,000 (33%) |
| 6 | 195 to 198 s, one test flaked | 607 to 622 s | 55 | 52 | 382,000 (36%) |

One worker keeps 0.86 of a core busy (483 s of CPU over a 94 s run at 6 workers).
A suite peaks at 1.0 to 1.1 GB of memory and about 45,000 `/tmp` files.
Memory pressure was 0 in every run, and the idle machine had 49 GiB available.
Four suites at once finish 2.0 suites a minute.
Five finish 2.2 suites a minute, but each suite takes 50% longer and CPU pressure reaches 30.
Six finish 1.85 suites a minute, and CPU pressure goes over room's CPU line.
An agent's `claude` process is 0.31 GB and about 1% of a core.
Seven of them together used 2.2 GB and 8% of a core.

On the busy night jbus ran 170 passes, 29 s each on average and 51.5 s at most.
Threads waited 29 times for a full test slot and 9 times for a short one, and jbus raised 17 `stall` events.
`jgauge room` kept one row, `hot-semantic-lines`, waiting for 7 passes, from 23:32 to 23:38.
The load was 29 to 35 on 24 cores, and the load line was 85% at the time.
`jgauge sample` had no rows for that night, because its timer started on 2026-10-20 at 07:30.

The CI runners belong to infra.
There are 7 full runners of 4 CPUs and 4 GB, for `jstack`, `infra`, `Winnifred` and `caveman`, and 2 fast runners.
All of them run under the system slice `gh-runner.slice`.
infra caps that slice at 20 CPUs and 32 GiB, and gives it CPUWeight 50, half the weight of a desk.

## The load runs at these limits

Two runs on 2026-10-20 tested these limits.
During each run, `jgauge sample` took a sample every 15 s, including `/tmp`'s file slots.
`jgauge sample --report --since --until` then read the samples.

| Run | Rows | CPU pressure, at most | At or over room's 40 | Memory pressure, at most | `/tmp` used, at most | 1-minute load, at most | jbus events |
|---|---|---|---|---|---|---|---|
| Every full and short slot kept busy, 12:20:47 to 12:53:42 | 132 | 52.15 | 13 rows | 0 | 43.1% | 56.1 | 0 stalls, 25 slot waits, 0 rows gated |
| Real crews alone, 12:55:26 to 13:30:17 | 139 | 39.97 | 0 rows | 0 | 39.9% | 53.6 | 1 stall, 20 slot waits, 0 rows gated |

In the first run, four loops kept the 4 full slots busy with whole suites.
Three more loops kept the 3 short slots busy with targeted runs.
Each loop paused for 3 minutes whenever a thread waited on its lane.
While only the loops ran, from 12:22 to 12:36, CPU pressure stayed at 30 to 33.
It went over 40 only after jbus launched 10 real crews in two passes, at 12:36:59 and 12:38:21.
The crews' start-up, CI runs and checks added to the load, and CPU pressure stayed over 40 twice, for about 1 and 2 minutes.
`jgauge room` then made the next launch wait for two passes.
All 40 suites passed, at 135 to 183 s each, and 10 of the 224 short runs ended with one test in error.
The one error whose output was kept was a race in the tests.
A test copied a template repo while git's maintenance held `objects/maintenance.lock`.
In the second run, 23 to 35 agent processes and about 19 crews ran.
No row waited on the crew cap or on `jgauge room`.
Threads waited for a test slot in 69 of the 139 samples.
While 4 or more threads waited, CPU pressure was 31 at the median and 40 at most.
The threads were waiting for CPU time, and the slot count was not too low.
The one stall came from a review that the reviewer had not written, and the machine did not cause it.

### Measuring the slots

The rows above count waits from jbus's `slot-wake` events, which say who waited and for how long, but not who held the slots.
Since 2026-11-05 `jgauge test-slot` appends one row to `~/.local/state/jgauge/slots.jsonl` at each take and each release, in both lanes ([jgauge](jgauge.md#the-slot-log)).
`jgauge sample --report --since --until` reads it and prints, for each lane, the holds, the mean occupancy, and the wait in the call at p50 and p90.
It also prints the mean occupancy over the time a thread of that lane waited for a slot, from the `slot-wake` events.
While a thread waits, every slot of its lane should be held, so a share near 100% says the log sees every holder.
A share well under 100% says a holder takes slots without `jgauge test-slot`, or with another `--slots`, and the log's `command` and `cwd` name the runs it does see.

## The machine's sizes

| Limit | Where | Value | Protects | Its yelena basis |
|---|---|---|---|---|
| Crew cap, `max_running` | `features/jgauge/src/jgauge/sizes.py`, and `max_running` in `~/.config/jbus/config.toml` | `CREW_GIB = 2` | Memory, and how many crews the reviews and merges keep up with | `jgauge.sizes` derives it as `min(cores, GiB // 2)`, 24 on yelena, and the owner's config sets `max_running = 24`. 24 agents are 7.4 GB of 49 GiB available. |
| Full test slots, `test_slots` | `features/jgauge/src/jgauge/sizes.py`, `~/.config/jstack/machine.toml`, `TEST_SLOTS`, `--slots` | `DESK_SHARE = 4` | CPU for whole suites, machine-wide | `jgauge.sizes` derives it as `cores // desk workers`: 4 on most machines of 8 cores or more, and 5 on 10, 11 or 15, where the floor of 2 workers or the rounding leaves room. Four suites at once is the knee of the table above, CPU pressure 17 to 29. |
| Memory a full slot takes | `features/jgauge/src/jgauge/sizes.py` | `SUITE_GIB = 4` | Slots on a small machine | A suite peaks at 1.1 GB. The cap binds only under 16 GiB, so never on yelena. |
| Short test slots, `short_slots` | `features/jgauge/src/jgauge/sizes.py`, `~/.config/jstack/machine.toml` | `SHORT_PER_CORES = 8` | A targeted run or a reviewer's proof never waits behind a suite | `jgauge.sizes` derives it as `clamp(cores // 8, 2, 8)`, 3 on yelena. There were 9 waits for a short slot on the busy night. |
| Short lane's time limit | `features/jgauge/src/jgauge/slot.py` | `SHORT_LIMIT_SECONDS = 120.0` | A full suite cannot sit in the short lane | Design choice, not a machine size: a whole suite takes 89 s alone |
| Desk test workers | `Makefile` | `PER_CORE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1 / 1,3 / 2),1 / 4)` | One check's share of the machine | A share, the same on any machine. 6 workers: 89 to 94 s, 5.2 cores busy. |
| Runner test workers | `Makefile` | `PER_CORE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1 / 1,3 / 2),1 / 4)` | A runner's check time on its quota | A share of the container's quota. 6 workers on a quota of 4, not run again for these measurements. |
| Runners and each one's share | `hosts/yelena/runners/*.conf` in infra, `CPUS=4`, `MEMORY=4g` | 7 full, 2 fast | CI beside the desk | infra's machine config, not jstack's. The slice's 20 CPUs at CPUWeight 50 give way to the desk. |

## Room

`jgauge room` checks these lines before a launch and before a review.
They are set in `features/jgauge/src/jgauge/room.sh`.
[The limits that are fixed](jgauge/change-a-limit.md#the-limits-that-are-fixed) is the table of what each line holds a launch on.

| Limit | Where | Value | Protects | Its yelena basis |
|---|---|---|---|---|
| Load line | `features/jgauge/src/jgauge/room.sh` | `LOAD=200` | A backstop for when CPU pressure cannot be read | A share of the cores. Six suites reach 216% of the cores, and the busy night's hold was at 120 to 146%. |
| CPU pressure line | `features/jgauge/src/jgauge/room.sh` | `CPU=40` | Launches stop when work waits for a core | A share of time. Five suites reach 30 and six reach 55, so it holds the sixth. |
| Memory floor, GB | `features/jgauge/src/jgauge/room.sh` | `MEMORY=6` | Room for one more launch and its check | A floor, not a size. A launch and a suite are 1.4 GB, and the idle machine has 49 GiB available. |
| Memory pressure line | `features/jgauge/src/jgauge/room.sh` | `PRESSURE=10` | Launches stop when work waits for memory | A share of time. It was 0 in every run. |
| Plan cushion, percent | `features/jgauge/src/jgauge/room.sh` | `CUSHION=${HEADROOM:-90}` | A launch passes an account by before its plan window is used up | The provider's, not the machine's. The user's `headroom` in `~/.config/jstack/config.toml` sets it, and with none it is `CUSHION=90`. |
| `/tmp` file slots line, percent | `features/jgauge/src/jgauge/room.sh` | `SLOTS=85` | `/tmp` never fills, which fails every shell | A share. Six suites at once peak at 36%. |
| A review skips the load | `features/jgauge/src/jgauge/cli.py` | `"--light",` | A review is not held by load it does not add | A review is about 2% of a core |
| Passes a row waits for room before its gate | `features/jbus/src/jbus/__init__.py` | `room_passes=int(raw.get("room_passes", 10)),` | The owner hears of a row room holds for long | The busy night's hold was 7 passes |

## The plan's pools

[jroles](../../jroles/docs/jroles.md#the-ledger) describes how the ledger uses these numbers.

| Limit | Where | Value | Protects | Its yelena basis |
|---|---|---|---|---|
| A window is full | `features/jroles/src/jroles/ledger.py` | `FULL = 100.0` | An instance is out only while a window is full | The provider's, not the machine's |
| A reading that ends a cap early | `features/jroles/src/jroles/ledger.py` | `EARLY = 10.0` | The usage endpoint's own reading at or under it replaces a full window, since the provider reset that window ahead of time | On 2026-10-31 the endpoint read 0% from 15:00 with the same reset, and `merge` kept 100 |
| How old a ledger row may be | `features/jroles/src/jroles/ledger.py` | `BLIND = timedelta(hours=1)` | A stale row does not hold a launch | The provider's |

## Timers, waits and locks

| Limit | Where | Value | Protects | Its yelena basis |
|---|---|---|---|---|
| jbus's pass | `features/jbus/units/jbus.timer` | `OnUnitActiveSec=1min` | How soon a launch, a wake or a merge happens | The busy night's passes took 29 s on average and 51.5 s at most |
| A sample of the load | `features/jgauge/units/jgauge-sample.timer` | `OnUnitActiveSec=15s` | The load history | A sample is one read of `/proc` |
| A look for a missing pass | `features/jbus/units/jbus-stale.timer` | `OnUnitActiveSec=15min` | An alert when jbus stops | Design choice |
| The slot log's history | `features/jgauge/src/jgauge/slotlog.py` | `KEEP_DAYS = 30` | The slot log stays small: a take past it drops the rows over 29 days old | As the load log keeps |
| A thread waits for a test slot | `features/jgauge/src/jgauge/sample.py` | `STALL_MINUTES = 5` | What the report counts as a stall | Design choice |
| The report's low CPU pressure | `features/jgauge/src/jgauge/sample.py` | `PRESSURE_LINE = 10.0` | A load over the line while CPU pressure is low is load room needn't hold | Design choice, and not room's memory `PRESSURE` |
| The hourly resend of what waits on the user | `features/jbus/src/jbus/stall.py` | `AGAIN = 60 * 60` | The owner is told again, once an hour | Design choice |
| The hourly list of what blocks | `features/jbus/src/jbus/leftover.py` | `REFRESH_MINUTES = 60` | The relay's list stays whole | Design choice |
| A blocker's one reminder | `features/jbus/src/jbus/leftover.py` | `REMIND_MINUTES = 15` | A blocker is not forgotten | Design choice |
| A left row is told | `features/jbus/src/jbus/leftover.py` | `CLOSE_MINUTES = 30` | The 30-minute leftover nag | Design choice |
| A gate acts on its default | `features/jbus/src/jbus/questions.py` | `QUIET = timedelta(0)` | Nothing waits on a question | Design choice |
| A pass at one head is a stall | `features/jbus/src/jbus/stall.py` | `PASSES = 10` | A stuck pull request is told | Design choice |
| A review's time before a stall | `features/jbus/src/jbus/stall.py` | `REVIEWING = 30` | A stuck review is told | Design choice |
| A thread is quiet | `features/jbus/src/jbus/live.py` | `QUIET_MINUTES = 10` | How a thread is shown | Design choice |
| A thread is hung | `features/jbus/src/jbus/live.py` | `HUNG_MINUTES = 20` | A hung turn is found | Design choice |
| A thread's timebox | `features/jbus/src/jbus/watch.py` | `TIMEBOX_HOURS = 4.0` | A runaway thread is found | Design choice |
| A thread waits on someone | `features/jbus/src/jbus/watch.py` | `WAITING_MINUTES = 30` | A waiting thread is told | Design choice |
| A thread ended with nothing written | `features/jbus/src/jbus/watch.py` | `UNWRITTEN_MINUTES = 15` | Its home hears of it | Design choice |
| A wake's quiet gap | `features/jbus/src/jbus/wake.py` | `GAP = 5 * 60` | A thread is not woken twice at once | Design choice |
| A pass's command | `features/jbus/src/jbus/wake.py` | `COMMAND_TIMEOUT = 300` | A slow check never stops a pass | Design choice |
| jmerge in a pass | `features/jbus/src/jbus/wake.py` | `JMERGE_TIMEOUT = 17 * 60` | A slow merge never stops a pass | Design choice, over the longest thing `jmerge` runs |
| jmerge's judge | `features/jmerge/src/jmerge/cli.py` | `TIMEOUT_SECONDS = 120` | A model call does not hang a merge | Design choice |
| Judged again | `features/jmerge/src/jmerge/cli.py` | `JUDGED_AGAIN_AT_MOST = 2` | A merge is not judged forever | Design choice |
| A wait after a 429 with no `Retry-After` | `features/jgauge/src/jgauge/limits.py` | `RETRY = timedelta(minutes=10)` | The usage endpoint is not asked again before then, and the ledger keeps its last good value | Design choice |
| An owed ask's read of its thread | `features/jbus/src/jbus/owed.py` | `WINDOW, PAGES, CHARS = 100, 5, 600` | A pass reads at most this much to find an ask | Design choice |
| How old a stop may be when jbus first sees it, for its ask to be owed | `features/jbus/src/jbus/owed.py` | `RECENT = timedelta(days=1)` | A first pass sends no old asks into threads that moved on | Design choice |
| A failover's items | `features/jbus/src/jbus/failover.py` | `ITEMS = 12` | A move's message stays short | Design choice |
| Runs a thread keeps | `features/jbus/src/jbus/threads.py` | `RUNS = 20` | A thread's history stays small | Design choice |
| Carry-ons a thread gets | `features/jbus/src/jbus/threads.py` | `CARRY_ONS = 2` | A thread is not woken forever | Design choice |
| Failures before an alert | `features/jbus/src/jbus/alert.py` | `AFTER = 3` | One failure is not an alert | Design choice |
| Passes before an expedite | `features/jbus/src/jbus/expedite.py` | `AFTER = 3` | A crew is told what to do | Design choice |
| A woken waiter's claim on a slot | `features/jgauge/src/jgauge/waiters.py` | `HOLDS = timedelta(minutes=10)` | A woken thread has its slot kept for it, and loses the claim if it does not come | Design choice: a turn takes up to a few minutes to come back |
| A wait no thread came back for | `features/jgauge/src/jgauge/waiters.py` | `FORGOTTEN = timedelta(hours=1)` | A dead waiter does not hold its place in the queue | Design choice |
| GitHub's file list | `features/jmerge/src/jmerge/ready.py` | `UNLISTED = Reason("hold", "needs {user}, GitHub listed {listed} of the {changed} files it changes")` | No merge with files nobody saw: `gh pr list` lists at most 100, so jmerge reads the rest from GitHub's files endpoint, which lists at most 3000, and holds only past that or when the read fails | GitHub's limit, not the machine's |
| The heavy-suite lock | `~/.local/state/locks/heavy-suite.lock` | One at a time | A heavy suite runs alone on the machine | Design choice |
| The browser lock | `~/.local/state/locks/browser.lock` | One at a time | One browser test at a time | Design choice |

## Size caps

| Limit | Where | Value | Protects | Its yelena basis |
|---|---|---|---|---|
| A SKILL.md | `features/repo-guards/tests/test_skill_size.py` | `CAP = 400` | A skill keeps a spine | Design choice |
| A test file | `features/repo-guards/tests/test_test_size.py` | `CAP = 1500` | A test file stays short | Design choice |
| A module | `features/repo-guards/tests/test_module_size.py` | `CAP = 800` | A module stays short | Design choice |
