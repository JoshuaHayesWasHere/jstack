# Limits

Every number in jstack that caps work, where it is set, what it protects, and the measurement it rests on.
The machine is yelena: 24 processors (Intel Core Ultra 7 270K Plus, no SMT), 62 GiB, a btrfs root with no inode limit, and `/tmp` a 32 GB tmpfs of 1,048,576 file slots.
The measurements are of 2026-10-20 unless a row says otherwise, and "the busy night" is 2026-10-19 22:00 to 2026-10-20 01:00 ET.

Three of the numbers are sizes of the machine, and `jgauge.limits` derives them from its processors and memory ([Configuration](configuration.md#the-machines-sizes)).
`jgauge limits` prints the three as their callers get them, and room's lines.
A local value goes in `~/.config/jstack/machine.toml`, or `max_running` in `~/.config/jbus/config.toml`, and nowhere in jstack.
Every other number here is a design choice, a share of the machine that means the same on any machine, or a limit of another system, and says so.

A row whose Where is a `path:line` of this repo has, as its Value, text on that line, and `tests/test_limits_doc.py` holds the file to the value; the line number is where it was when this page was written.

## The measurements

The suite is jstack's own, 6,646 tests, run as the check command runs it, `pytest -n 6 --dist worksteal -m "not browser"`, each copy in a worktree of its own, with the heavy-suite lock held so that nothing else heavy ran.

| Suites at once | Wall per suite | CPU per suite | CPU pressure, some avg60, at most | 1-minute load, at most | `/tmp` files used, at most |
|---|---|---|---|---|---|
| 1 | 89 to 94 s | 456 to 483 s | 1.3 | 8 | 172,000 (16%) |
| 3 | 97 s | 493 s | 9 | 19 | 253,000 (24%) |
| 4 | 113 and 133 s | 530 and 570 s | 17 and 29 | 27 and 33 | 302,000 to 329,000 (29 to 31%) |
| 5 | 135 and 137 s | 560 and 565 s | 30 | 34 | 343,000 to 344,000 (33%) |
| 6 | 195 to 198 s, one test flaked | 607 to 622 s | 55 | 52 | 382,000 (36%) |

A worker keeps 0.86 of a core busy alone (483 s of CPU over a 94 s run at 6 workers), and a suite peaks at 1.0 to 1.1 GB of memory and about 45,000 `/tmp` files.
Memory pressure was 0 in every run, and the idle machine had 49 GiB available.
Four suites at once give 2.0 suites a minute and five give 2.2, at 50% more time a suite and CPU pressure 30; six give 1.85 and pass room's CPU line.
An agent's `claude` process is 0.31 GB and about 1% of a core: seven of them were 2.2 GB and 8% of a core in all.

On the busy night jbus ran 170 passes, 29 s each on average and 51.5 s at most.
Threads waited 29 times for a full test slot and 9 times for a short one, and jbus raised 17 `stall` events.
One row, `hot-semantic-lines`, was held by room for 7 passes, 23:32 to 23:38, at a load of 29 to 35 on 24 cores, under the load line of 85% the machine had then.
`jgauge sample` had no rows for that night: its timer started on 2026-10-20 at 07:30.

The runners are infra's: 7 full runners of 4 CPUs and 4 GB, `jstack`, `infra`, `Winnifred` and `caveman`, and 2 fast ones, all under the system slice `gh-runner.slice`, capped at 20 CPUs and 32 GiB with CPUWeight 50, half a desk's weight.

## The load runs at these limits

Two runs on 2026-10-20, each sampled every 15 s by `jgauge sample` of this change, with `/tmp`'s file slots, and read with `jgauge sample --report --since --until`.

| Run | Rows | CPU pressure, at most | At or over room's 40 | Memory pressure, at most | `/tmp` used, at most | 1-minute load, at most | jbus events |
|---|---|---|---|---|---|---|---|
| Every full and short slot kept busy, 12:20:47 to 12:53:42 | 132 | 52.15 | 13 rows | 0 | 43.1% | 56.1 | 0 stalls, 25 slot waits, 0 rows gated |
| Real crews alone, 12:55:26 to 13:30:17 | 139 | 39.97 | 0 rows | 0 | 39.9% | 53.6 | 1 stall, 20 slot waits, 0 rows gated |

In the first run four loopers kept the 4 full slots busy with whole suites and three kept the 3 short slots busy with targeted runs, each giving way for 3 minutes to any thread that waited on its lane.
With those alone, from 12:22 to 12:36, CPU pressure stayed at 30 to 33.
It went over 40 only after jbus launched 10 real crews in two passes, at 12:36:59 and 12:38:21, whose start-up, CI runs and checks came on top, in two spells of about 1 and 2 minutes; room then held the next launch for two passes.
All 40 suites passed, at 135 to 183 s each, and 10 of the 224 short runs ended with one test in error; the one whose output was kept was a race in the tests, a copy of a template repo while git's maintenance holds `objects/maintenance.lock`.
In the second run 23 to 35 agent processes ran, about 19 crews were out, and no row waited on the crew cap or on room.
Threads waited for a test slot in 69 of the 139 samples, and while 4 or more waited, CPU pressure was 31 at the median and 40 at most, so the slots waited on the CPU and not on a count set too low.
The stall was a review that had not been written, not the machine.

## The machine's sizes

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| Crew cap, `max_running` | `src/jgauge/limits.py:49`, and `max_running` in `~/.config/jbus/config.toml` | `CREW_GIB = 2` | `MAX_RUNNING = 24` in `src/jbus/__init__.py` by #116 (2026-10-19, yelena, the owner's "we can push the boundaries more with yelena"); 16 and 12 before on adalaide | Memory, and how many crews the reviews and merges keep up with | 24 agents are 7.4 GB of 49 GiB available; one crew a processor | Moved: derived as `min(cores, GiB // 2)`, 24 on yelena; the config's `max_running = 24` stays, the owner's word |
| Full test slots, `test_slots` | `src/jgauge/limits.py:38`, `~/.config/jstack/machine.toml`, `TEST_SLOTS`, `--slots` | `DESK_SHARE = 4` | `DEFAULT = 3` in `src/jgauge/slot.py` by #109 (2026-10-19, yelena); `TEST_SLOTS=4` in the owner's zshenv (word 3593730d3e4f), which `jbus.service` never saw | CPU for whole suites, machine-wide | Four suites at once is the knee of the table above, CPU pressure 17 to 29 | Moved: derived as `cores // desk workers`, 4 on 8 cores or more; the zshenv line is dropped |
| Memory a full slot takes | `src/jgauge/limits.py:45` | `SUITE_GIB = 4` | This change | Slots on a small machine | A suite peaks at 1.1 GB | New: binds under 16 GiB, never on yelena |
| Short test slots, `short_slots` | `src/jgauge/limits.py:53`, `~/.config/jstack/machine.toml` | `SHORT_PER_CORES = 8` | `SHORT_SLOTS = 3` in `src/jgauge/slot.py` by #51 (2026-10-16, machine not named) | A targeted run or a reviewer's proof never waits behind a suite | 9 waits for a short slot on the busy night | Moved: derived as `clamp(cores // 8, 2, 8)`, 3 on yelena |
| Short lane's time limit | `src/jgauge/slot.py:36` | `SHORT_LIMIT_SECONDS = 120.0` | #51 | A full suite cannot sit in the short lane | Design choice, not a machine size: a whole suite takes 89 s alone | Kept |
| Desk test workers | `Makefile:31` | `PER_CORE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1 / 1,3 / 2),1 / 4)` | #109 (yelena) | One check's share of the machine | 6 workers: 89 to 94 s, 5.2 cores busy | Kept: a share, the same on any machine |
| Runner test workers | `Makefile:31` | `PER_CORE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1 / 1,3 / 2),1 / 4)` | #109 (yelena) | A runner's check time on its quota | 6 workers on a quota of 4; not run again here | Kept: a share of the container's quota |
| Runners and each one's share | `hosts/yelena/runners/*.conf` in infra, `CPUS=4`, `MEMORY=4g` | 7 full, 2 fast | infra | CI beside the desk | The slice's 20 CPUs at CPUWeight 50 give way to the desk | infra's machine config, not jstack's: recorded, not moved |

## Room

`jgauge room` asks these before a launch and a review, in `src/jgauge/room.sh`.

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| Load line | `src/jgauge/room.sh:3` | `LOAD=200` | #117 (2026-10-19, yelena), 85 before, sized for adalaide | A backstop for when CPU pressure cannot be read | Six suites reach 216% of the cores; the busy night's hold was at 120 to 146% | Kept: a share of the cores |
| CPU pressure line | `src/jgauge/room.sh:4` | `CPU=40` | #117 (yelena) | Launches stop when work waits for a core | Five suites reach 30 and six 55, so it holds the sixth | Kept: a share of time |
| Memory floor, GB | `src/jgauge/room.sh:5` | `MEMORY=6` | Before this repo's history | Room for one more launch and its check | A launch and a suite are 1.4 GB; the idle machine has 49 GiB available | Kept: a floor, not a size |
| Memory pressure line | `src/jgauge/room.sh:6` | `PRESSURE=10` | Before this repo's history | Launches stop when work waits for memory | 0 in every run | Kept: a share of time |
| Plan cushion, percent | `src/jgauge/room.sh:7` | `CUSHION=100` | #102 (the owner's gate 20) | Launches go until a plan window is used up | The provider's, not the machine's | Kept |
| `/tmp` file slots line, percent | `src/jgauge/room.sh:8` | `SLOTS=85` | Before this repo's history | `/tmp` never fills, which fails every shell | Six suites at once peak at 36% | Kept: a share |
| A review skips the load | `src/jgauge/cli.py:202` | `"--light",` | #102 (yelena, "at load 30 of 24 cores") | A review is not held by load it does not add | A review is about 2% of a core | Kept |
| Passes a row waits for room before its gate | `src/jbus/__init__.py:329` | `room_passes=int(raw.get("room_passes", 10)),` | Before this repo's history | The owner hears of a row room holds for long | The busy night's hold was 7 passes | Kept: a design choice |

## The plan's pools

The pool logic is `account-failover`'s, `account-limits`' and `jgauge-pool-limits-2`'s: this page records its numbers and moves none.

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| A window is full | `src/jroles/ledger.py:32` | `FULL = 100.0` | #111 | An instance is out only while a window is full | The provider's, not the machine's | Kept |
| How old a ledger row may be | `src/jroles/ledger.py:33` | `BLIND = timedelta(hours=1)` | #111 | A stale row does not hold a launch | The provider's | Kept |

## Timers, waits and locks

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| jbus's pass | `templates/jbus.timer:7` | `OnUnitActiveSec=1min` | Before this repo's history | How soon a launch, a wake or a merge happens | The busy night's passes took 29 s on average and 51.5 s at most | Kept |
| A sample of the load | `templates/jgauge-sample.timer:7` | `OnUnitActiveSec=15s` | #107 | The load history | A sample is one read of `/proc` | Kept |
| A look for a missing pass | `templates/jbus-stale.timer:7` | `OnUnitActiveSec=15min` | #113 (yelena) | An alert when jbus stops | Design choice | Kept |
| A thread waits for a test slot | `src/jgauge/sample.py:43` | `STALL_MINUTES = 5` | This change, the task's line for a stall | What the report counts as a stall | Design choice | New |
| The report's low CPU pressure | `src/jgauge/sample.py:39` | `PRESSURE_LINE = 10.0` | #107 | A load over the line while CPU pressure is low is load room needn't hold | Design choice, and not room's memory `PRESSURE` | Kept |
| The hourly resend of what waits on the user | `src/jbus/stall.py:56` | `AGAIN = 60 * 60` | Before this repo's history | The owner is told again, once an hour | Design choice | Kept |
| The hourly list of what blocks | `src/jbus/leftover.py:65` | `REFRESH_MINUTES = 60` | #22 | The relay's list stays whole | Design choice | Kept |
| A blocker's one reminder | `src/jbus/leftover.py:64` | `REMIND_MINUTES = 15` | #22 | A blocker is not forgotten | Design choice | Kept |
| A left row is told | `src/jbus/leftover.py:63` | `CLOSE_MINUTES = 30` | Before this repo's history | The 30-minute leftover nag | Design choice | Kept |
| A gate acts on its default | `src/jbus/questions.py:137` | `QUIET = timedelta(hours=2)` | #36 | Nothing waits on a question for long | Design choice | Kept |
| A pass at one head is a stall | `src/jbus/stall.py:66` | `PASSES = 10` | Before this repo's history | A stuck pull request is told | Design choice | Kept |
| A review's time before a stall | `src/jbus/stall.py:67` | `REVIEWING = 30` | Before this repo's history | A stuck review is told | Design choice | Kept |
| What is left, before a stall | `src/jbus/stall.py:68` | `LEFT = 300` | Before this repo's history | A left row is told | Design choice | Kept |
| A thread is quiet | `src/jbus/live.py:25` | `QUIET_MINUTES = 10` | Before this repo's history | How a thread is shown | Design choice | Kept |
| A thread is hung | `src/jbus/live.py:26` | `HUNG_MINUTES = 20` | Before this repo's history | A hung turn is found | Design choice | Kept |
| A thread's timebox | `src/jbus/watch.py:52` | `TIMEBOX_HOURS = 4.0` | Before this repo's history | A runaway thread is found | Design choice | Kept |
| A thread waits on someone | `src/jbus/watch.py:53` | `WAITING_MINUTES = 30` | Before this repo's history | A waiting thread is told | Design choice | Kept |
| A thread ended with nothing written | `src/jbus/watch.py:54` | `UNWRITTEN_MINUTES = 15` | #86 | Its home hears of it | Design choice | Kept |
| A wake's quiet gap | `src/jbus/wake.py:78` | `GAP = 5 * 60` | Before this repo's history | A thread is not woken twice at once | Design choice | Kept |
| A pass's command | `src/jbus/wake.py:80` | `COMMAND_TIMEOUT = 300` | #42 | A slow check never stops a pass | Design choice | Kept |
| jmerge in a pass | `src/jbus/wake.py:81` | `JMERGE_TIMEOUT = 17 * 60` | #42 | A slow merge never stops a pass | Design choice, over jmerge's own 15 min | Kept |
| jmerge's own run | `src/jmerge/cli.py:220` | `    TIMEOUT = 15 * 60` | Before this repo's history | jmerge ends under the pass's limit | Design choice | Kept |
| jmerge's judge | `src/jmerge/cli.py:80` | `TIMEOUT_SECONDS = 120` | Before this repo's history | A model call does not hang a merge | Design choice | Kept |
| Judged again | `src/jmerge/cli.py:79` | `JUDGED_AGAIN_AT_MOST = 2` | Before this repo's history | A merge is not judged forever | Design choice | Kept |
| Rows that share files | `src/jbus/dispatch.py:50` | `OVERLAP_PATHS = 5` | Before this repo's history | Two crews out on the same files | Design choice | Kept |
| A failover's items | `src/jbus/failover.py:44` | `ITEMS = 12` | Before this repo's history | A move's message stays short | Design choice | Kept |
| Runs a thread keeps | `src/jbus/threads.py:119` | `RUNS = 20` | Before this repo's history | A thread's history stays small | Design choice | Kept |
| Carry-ons a thread gets | `src/jbus/threads.py:129` | `CARRY_ONS = 2` | Before this repo's history | A thread is not woken forever | Design choice | Kept |
| Failures before an alert | `src/jbus/alert.py:38` | `AFTER = 3` | Before this repo's history | One failure is not an alert | Design choice | Kept |
| Passes before an expedite | `src/jbus/expedite.py:81` | `AFTER = 3` | Before this repo's history | A crew is told what to do | Design choice | Kept |
| GitHub's file list | `src/jmerge/ready.py:150` | `UNLISTED = Reason("hold", "needs {user}, GitHub listed {listed} of the {changed} files it changes")` | #2 | No merge with files nobody saw: GitHub lists at most 100 | GitHub's limit, not the machine's | Kept |
| The heavy-suite lock | `~/.local/state/locks/heavy-suite.lock` | One at a time | Before this repo's history | A heavy suite runs alone on the machine | Design choice | Kept |
| The browser lock | `~/.local/state/locks/browser.lock` | One at a time | Before this repo's history | One browser test at a time | Design choice | Kept |

## Size caps

| Limit | Where | Value | Set by, for | Protects | Its yelena basis | Now |
|---|---|---|---|---|---|---|
| A docs page | `tests/test_jbus_pages.py:16` | `CAP = 300` | #120 | A page stays short | Design choice | Kept |
| A SKILL.md | `tests/test_skill_size.py:12` | `CAP = 400` | #122 | A skill keeps a spine | Design choice | Kept |
| A test file | `tests/test_test_size.py:16` | `CAP = 1500` | #128 | A test file stays short | Design choice | Kept |
| A module | `tests/test_module_size.py:11` | `CAP = 800` | #127 | A module stays short | Design choice | Kept |
| `jbus/cli.py` | `tests/test_jbus_cli_size.py:16` | `LINES = 300` | #126 | The entry point stays thin | Design choice | Kept |
