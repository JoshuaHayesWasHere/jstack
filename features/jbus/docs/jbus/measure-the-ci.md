# Measure the CI

`jbus ci` keeps what a project's CI costs and holds it to nine targets, so a change to CI is measured against what came before it. It asks GitHub, read-only through `gh api`, for the workflow runs of the last `--days` days (14), the jobs of each run that has finished and not been kept, and the pull requests with their timelines. Two files in the project's state directory hold it:

- `ci.jsonl`, one line per job, once. A second run adds no line it has. A line is the run, job and attempt, the job's `name`, `sha`, `branch`, `pr`, `event`, `created`, `started` and `completed`, its `conclusion`, the `runner` and its `kind` (`hosted` or `local`, kept apart), and the failing `tests` and runner faults (`signs`) of a red job on the local runner. A job cancelled while it waited has no runner and no start, and is kept and counted.
- `ci-prs.jsonl`, one line per pull request, rewritten each run, with the times its branch was force-pushed.

A line also has a field for each change that is to move a number, left empty when the run did not give it: `full` and `tree` (one suite per tree), `selection` and `reason` (what `check-fast` ran, `all` or how many files, and why), `slowest_s` and `tail_s` (the slowest file, and the wall time less the summed test time over the workers), `cpu_pressure`, `cgroup_pressure` and `workers` (the first line of `/proc/pressure/cpu`, of the job's `cpu.pressure`, and the worker count) and `tmp_inode_pct`.

A job gives these as it runs, the one way: `jbus ci --notice full=true workers=4 cpu_pressure="$(head -n 1 /proc/pressure/cpu)"` prints a `::notice title=jstack-ci::` annotation holding the fields as JSON, and the collector reads it back from the job's check run. A job summary cannot be read through the API, so the annotation is the carrier; where `GITHUB_STEP_SUMMARY` is set, the fields are also written there as a table. A name that is not a field of the line is refused.

### The nine targets

Each is counted over the period, from job-level rows only: a job counts once and a run never does. The local runner is the figure a target is held to, and the hosted runner's is shown beside it where it has one. The targets other than the first five are set here, because the plan named none.

| Target | Held to | Counted as |
| --- | --- | --- |
| queue p50 under exec p50 | the wait is under the run | median minutes from `created` to `started`, against the median from `started` to `completed`, of green jobs. A job cancelled while it waited is in neither. |
| wasted-minute share | under 15% | execution minutes of jobs that failed or were cancelled, over all execution minutes |
| own-cause reds | over 70% | of the failed local jobs on a run's last attempt, the share that is the pull request's own. A red is `main` when main was red with the same failing tests when it started, `runner` when its log shows a runner fault and another branch fails the same tests, `flake` when no fault shows, else `own`. |
| rebases per merged PR | under 0.3 | force-pushes of the branches of the pull requests merged in the period, over those pull requests |
| staleness-only rebases | none | force-pushes whose cause was only that main had moved, read from the jbus event that came before them |
| time-to-green p50 | under 15 min | median minutes from the first job on a merged pull request's final head to the last green one |
| main-red minutes per day | under 30 min | minutes main was red, from its first failed run to the next green one, per day |
| flaky tests | under 3 | tests that failed two branches with no runner fault and no red main to blame |
| /tmp inode peak | under 80% | the highest `tmp_inode_pct` a job wrote. It shows no data until a job writes one. |

The numbers reproduce the plan's from a recording of the Actions API (`features/jbus/tests/fixtures/ci/jstack`): queue 26.6 against 9.67 minutes, 42.9% wasted, 7 of 35 reds the pull request's own, 29 force-pushes over 62 merged pull requests, time-to-green 33 minutes (8.6 hosted), main red 43 and 174 minutes on 10-16 and 10-17.
Two differ, and the page says by how much.
The rule finds 22 staleness-only rebases of 38 where the plan counted 21, which it read by hand from one more look-back.
It finds 2 flaky tests where the plan named 9 by hand.

### The week's report

The report is optional, and a project asks for it with `ci_report = true` in its `[[project]]` table of `~/.config/jbus/config.toml`.
The install enables `jbus-ci.timer` only while a project asks for it, and with none asking it leaves the timer off and nothing alerts.
The timer runs `jbus-ci.service` every Monday at 09:00 in the machine's own zone (`Persistent=true` runs one the machine slept through when it is up).
The service runs `jbus ci --report --each`, which for each project that asks collects, then writes `reports/ci-week-<date>.md` in that project's home: the nine targets over the last 7 days, each with how it was counted, the jobs counted (local and hosted apart, and how many were cancelled while they waited), and main's red minutes by day. A week where every target is met, or has no data, sends nothing. A week with a target missed sends one `alert` event, naming each target missed and the report, once for that day. A run that fails shows in `journalctl --user -u jbus-ci`.

The `ci` panel of [the view](the-view.md) opens at `#/<project>/ci` (it has no card, so the first screen keeps its size) and draws the same files: each target with its value and what it is held to, and its series by day, with a dashed mark at the merge of `ci-one-suite-per-tree`, `ci-slow-tail` and `ci-test-map` in this project's home and of `jstack-fast-4`, the change of the runner's CPUs, in infra's.
