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

When a row's Where is a `path:line` of this repo, its Value is text on that line.
`features/jgauge/tests/test_limits_doc.py` checks that the file still holds the value.
The line number is where the value was when this page was written.

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
During each run, the version of `jgauge sample` that this change built took a sample every 15 s, including `/tmp`'s file slots.
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

## The machine's sizes

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| Crew cap, `max_running` | `features/jgauge/src/jgauge/sizes.py:49`, and `max_running` in `~/.config/jbus/config.toml` | `CREW_GIB = 2` | `MAX_RUNNING = 24` in `features/jbus/src/jbus/__init__.py` by #116 (2026-10-19, yelena, the owner's "we can push the boundaries more with yelena"); 16 and 12 before on adalaide | Memory, and how many crews the reviews and merges keep up with | 24 agents are 7.4 GB of 49 GiB available; one crew a processor | Moved: derived as `min(cores, GiB // 2)`, 24 on yelena; the config's `max_running = 24` stays, the owner's word |
| Full test slots, `test_slots` | `features/jgauge/src/jgauge/sizes.py:38`, `~/.config/jstack/machine.toml`, `TEST_SLOTS`, `--slots` | `DESK_SHARE = 4` | `DEFAULT = 3` in `features/jgauge/src/jgauge/slot.py` by #109 (2026-10-19, yelena); `TEST_SLOTS=4` in the owner's zshenv (word 3593730d3e4f), which `jbus.service` never saw | CPU for whole suites, machine-wide | Four suites at once is the knee of the table above, CPU pressure 17 to 29 | Moved: derived as `cores // desk workers`, 4 on most machines of 8 cores or more (5 on 10, 11 or 15, where the floor of 2 workers or the rounding leaves room); the zshenv line is dropped |
| Memory a full slot takes | `features/jgauge/src/jgauge/sizes.py:45` | `SUITE_GIB = 4` | This change | Slots on a small machine | A suite peaks at 1.1 GB | New: binds under 16 GiB, never on yelena |
| Short test slots, `short_slots` | `features/jgauge/src/jgauge/sizes.py:53`, `~/.config/jstack/machine.toml` | `SHORT_PER_CORES = 8` | `SHORT_SLOTS = 3` in `features/jgauge/src/jgauge/slot.py` by #51 (2026-10-16, machine not named) | A targeted run or a reviewer's proof never waits behind a suite | 9 waits for a short slot on the busy night | Moved: derived as `clamp(cores // 8, 2, 8)`, 3 on yelena |
| Short lane's time limit | `features/jgauge/src/jgauge/slot.py:36` | `SHORT_LIMIT_SECONDS = 120.0` | #51 | A full suite cannot sit in the short lane | Design choice, not a machine size: a whole suite takes 89 s alone | Kept |
| Desk test workers | `Makefile:31` | `PER_CORE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1 / 1,3 / 2),1 / 4)` | #109 (yelena) | One check's share of the machine | 6 workers: 89 to 94 s, 5.2 cores busy | Kept: a share, the same on any machine |
| Runner test workers | `Makefile:31` | `PER_CORE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1 / 1,3 / 2),1 / 4)` | #109 (yelena) | A runner's check time on its quota | 6 workers on a quota of 4; not run again here | Kept: a share of the container's quota |
| Runners and each one's share | `hosts/yelena/runners/*.conf` in infra, `CPUS=4`, `MEMORY=4g` | 7 full, 2 fast | infra | CI beside the desk | The slice's 20 CPUs at CPUWeight 50 give way to the desk | infra's machine config, not jstack's: recorded, not moved |

## Room

`jgauge room` checks these lines before a launch and before a review.
They are set in `features/jgauge/src/jgauge/room.sh`.

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| Load line | `features/jgauge/src/jgauge/room.sh:3` | `LOAD=200` | #117 (2026-10-19, yelena), 85 before, sized for adalaide | A backstop for when CPU pressure cannot be read | Six suites reach 216% of the cores; the busy night's hold was at 120 to 146% | Kept: a share of the cores |
| CPU pressure line | `features/jgauge/src/jgauge/room.sh:4` | `CPU=40` | #117 (yelena) | Launches stop when work waits for a core | Five suites reach 30 and six 55, so it holds the sixth | Kept: a share of time |
| Memory floor, GB | `features/jgauge/src/jgauge/room.sh:5` | `MEMORY=6` | Before this repo's history | Room for one more launch and its check | A launch and a suite are 1.4 GB; the idle machine has 49 GiB available | Kept: a floor, not a size |
| Memory pressure line | `features/jgauge/src/jgauge/room.sh:6` | `PRESSURE=10` | Before this repo's history | Launches stop when work waits for memory | 0 in every run | Kept: a share of time |
| Plan cushion, percent | `features/jgauge/src/jgauge/room.sh:7` | `CUSHION=${HEADROOM:-90}` | #102 (the owner's gate 20) at 100; account-limits, the owner's account-failover round 1, at 90 | A launch passes an account by before its plan window is used up | The provider's, not the machine's | Moved: the user's `headroom` in `config.toml`, `CUSHION=90` with none |
| `/tmp` file slots line, percent | `features/jgauge/src/jgauge/room.sh:8` | `SLOTS=85` | Before this repo's history | `/tmp` never fills, which fails every shell | Six suites at once peak at 36% | Kept: a share |
| A review skips the load | `features/jgauge/src/jgauge/cli.py:202` | `"--light",` | #102 (yelena, "at load 30 of 24 cores") | A review is not held by load it does not add | A review is about 2% of a core | Kept |
| Passes a row waits for room before its gate | `features/jbus/src/jbus/__init__.py:427` | `room_passes=int(raw.get("room_passes", 10)),` | Before this repo's history | The owner hears of a row room holds for long | The busy night's hold was 7 passes | Kept: a design choice |

## The plan's pools

The pool logic comes from the tasks `account-failover`, `account-limits` and `jgauge-pool-limits-2`.
This page records the pool numbers and changes none of them.

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| A window is full | `features/jroles/src/jroles/ledger.py:32` | `FULL = 100.0` | #111 | An instance is out only while a window is full | The provider's, not the machine's | Kept |
| How old a ledger row may be | `features/jroles/src/jroles/ledger.py:33` | `BLIND = timedelta(hours=1)` | #111 | A stale row does not hold a launch | The provider's | Kept |

## Timers, waits and locks

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| jbus's pass | `features/jbus/units/jbus.timer:7` | `OnUnitActiveSec=1min` | Before this repo's history | How soon a launch, a wake or a merge happens | The busy night's passes took 29 s on average and 51.5 s at most | Kept |
| A sample of the load | `features/jgauge/units/jgauge-sample.timer:7` | `OnUnitActiveSec=15s` | #107 | The load history | A sample is one read of `/proc` | Kept |
| A look for a missing pass | `features/jbus/units/jbus-stale.timer:7` | `OnUnitActiveSec=15min` | #113 (yelena) | An alert when jbus stops | Design choice | Kept |
| A thread waits for a test slot | `features/jgauge/src/jgauge/sample.py:43` | `STALL_MINUTES = 5` | This change, the task's line for a stall | What the report counts as a stall | Design choice | New |
| The report's low CPU pressure | `features/jgauge/src/jgauge/sample.py:39` | `PRESSURE_LINE = 10.0` | #107 | A load over the line while CPU pressure is low is load room needn't hold | Design choice, and not room's memory `PRESSURE` | Kept |
| The hourly resend of what waits on the user | `features/jbus/src/jbus/stall.py:57` | `AGAIN = 60 * 60` | Before this repo's history | The owner is told again, once an hour | Design choice | Kept |
| The hourly list of what blocks | `features/jbus/src/jbus/leftover.py:71` | `REFRESH_MINUTES = 60` | #22 | The relay's list stays whole | Design choice | Kept |
| A blocker's one reminder | `features/jbus/src/jbus/leftover.py:70` | `REMIND_MINUTES = 15` | #22 | A blocker is not forgotten | Design choice | Kept |
| A left row is told | `features/jbus/src/jbus/leftover.py:69` | `CLOSE_MINUTES = 30` | Before this repo's history | The 30-minute leftover nag | Design choice | Kept |
| A gate acts on its default | `features/jbus/src/jbus/questions.py:153` | `QUIET = timedelta(0)` | #36, settled at once since word 3d4718ca72ab | Nothing waits on a question | Design choice | Kept |
| A pass at one head is a stall | `features/jbus/src/jbus/stall.py:67` | `PASSES = 10` | Before this repo's history | A stuck pull request is told | Design choice | Kept |
| A review's time before a stall | `features/jbus/src/jbus/stall.py:68` | `REVIEWING = 30` | Before this repo's history | A stuck review is told | Design choice | Kept |
| A thread is quiet | `features/jbus/src/jbus/live.py:25` | `QUIET_MINUTES = 10` | Before this repo's history | How a thread is shown | Design choice | Kept |
| A thread is hung | `features/jbus/src/jbus/live.py:26` | `HUNG_MINUTES = 20` | Before this repo's history | A hung turn is found | Design choice | Kept |
| A thread's timebox | `features/jbus/src/jbus/watch.py:63` | `TIMEBOX_HOURS = 4.0` | Before this repo's history | A runaway thread is found | Design choice | Kept |
| A thread waits on someone | `features/jbus/src/jbus/watch.py:64` | `WAITING_MINUTES = 30` | Before this repo's history | A waiting thread is told | Design choice | Kept |
| A thread ended with nothing written | `features/jbus/src/jbus/watch.py:65` | `UNWRITTEN_MINUTES = 15` | #86 | Its home hears of it | Design choice | Kept |
| A wake's quiet gap | `features/jbus/src/jbus/wake.py:76` | `GAP = 5 * 60` | Before this repo's history | A thread is not woken twice at once | Design choice | Kept |
| A pass's command | `features/jbus/src/jbus/wake.py:78` | `COMMAND_TIMEOUT = 300` | #42 | A slow check never stops a pass | Design choice | Kept |
| jmerge in a pass | `features/jbus/src/jbus/wake.py:79` | `JMERGE_TIMEOUT = 17 * 60` | #42 | A slow merge never stops a pass | Design choice, over the merge gate's 10 min | Kept |
| jmerge's judge | `features/jmerge/src/jmerge/cli.py:60` | `TIMEOUT_SECONDS = 120` | Before this repo's history | A model call does not hang a merge | Design choice | Kept |
| Judged again | `features/jmerge/src/jmerge/cli.py:55` | `JUDGED_AGAIN_AT_MOST = 2` | Before this repo's history | A merge is not judged forever | Design choice | Kept |
| Rows that share files | `features/jbus/src/jbus/dispatch.py:68` | `OVERLAP_PATHS = 5` | Before this repo's history | Two crews out on the same files | Design choice | Kept |
| A failover's items | `features/jbus/src/jbus/failover.py:85` | `ITEMS = 12` | Before this repo's history | A move's message stays short | Design choice | Kept |
| Runs a thread keeps | `features/jbus/src/jbus/threads.py:53` | `RUNS = 20` | Before this repo's history | A thread's history stays small | Design choice | Kept |
| Carry-ons a thread gets | `features/jbus/src/jbus/threads.py:61` | `CARRY_ONS = 2` | Before this repo's history | A thread is not woken forever | Design choice | Kept |
| Failures before an alert | `features/jbus/src/jbus/alert.py:67` | `AFTER = 3` | Before this repo's history | One failure is not an alert | Design choice | Kept |
| Passes before an expedite | `features/jbus/src/jbus/expedite.py:81` | `AFTER = 3` | Before this repo's history | A crew is told what to do | Design choice | Kept |
| A woken waiter's claim on a slot | `features/jgauge/src/jgauge/waiters.py:48` | `HOLDS = timedelta(minutes=10)` | #70 | A woken thread has its slot kept for it, and loses the claim if it does not come | Design choice: a turn takes up to a few minutes to come back | Kept |
| A wait no thread came back for | `features/jgauge/src/jgauge/waiters.py:49` | `FORGOTTEN = timedelta(hours=1)` | #70 | A dead waiter does not hold its place in the queue | Design choice | Kept |
| GitHub's file list | `features/jmerge/src/jmerge/ready.py:200` | `UNLISTED = Reason("hold", "needs {user}, GitHub listed {listed} of the {changed} files it changes")` | #2, and jmerge-all-files for the full read | No merge with files nobody saw: `gh pr list` lists at most 100, so jmerge reads the rest from GitHub's files endpoint, which lists at most 3000, and holds only past that or when the read fails | GitHub's limit, not the machine's | Moved: from 100 files to 3000 |
| The heavy-suite lock | `~/.local/state/locks/heavy-suite.lock` | One at a time | Before this repo's history | A heavy suite runs alone on the machine | Design choice | Kept |
| The browser lock | `~/.local/state/locks/browser.lock` | One at a time | Before this repo's history | One browser test at a time | Design choice | Kept |

## Size caps

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| A docs page | `features/jbus/tests/test_jbus_pages.py:16` | `CAP = 300` | #120 | A page stays short | Design choice | Kept |
| A SKILL.md | `features/repo-guards/tests/test_skill_size.py:12` | `CAP = 400` | #122 | A skill keeps a spine | Design choice | Kept |
| A test file | `features/repo-guards/tests/test_test_size.py:16` | `CAP = 1500` | #128 | A test file stays short | Design choice | Kept |
| A module | `features/repo-guards/tests/test_module_size.py:11` | `CAP = 800` | #127 | A module stays short | Design choice | Kept |
| `jbus/cli.py` | `features/jbus/tests/test_jbus_cli_size.py:16` | `LINES = 300` | #126 | The entry point stays thin | Design choice | Kept |
