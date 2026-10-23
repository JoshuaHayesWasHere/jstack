# Measure the CI

`jbus ci` records what a project's GitHub Actions CI costs and measures it against nine targets, so you can compare a change to CI with what came before it.
It works for any repo of the config.
It needs nothing from the repo's workflows, since the fields a job adds with `--notice` are optional.
`jbus --project <name> ci` collects and prints the nine targets, each with how it was counted.
It asks GitHub, read-only through `gh api`, for three things:

- the workflow runs of the last `--days` days, 14 by default
- the jobs of each run that has finished and is not stored yet
- the pull requests, with their timelines


It keeps what it collects in two files in the project's state directory:

- `ci.jsonl`, one line per job, written once.
  A second run adds no line it already has.
  A line holds the run, the job and the attempt.
  It also holds the job's `name`, `sha`, `branch`, `pr`, `event`, `created`, `started`, `completed` and `conclusion`.
  It names the `runner` and its `kind`, `hosted` or `local`, and the targets count the two kinds apart.
  For a red job on the local runner, it lists the failing `tests` and the runner faults (`signs`).
  A job cancelled while it waited has no runner and no start, and `jbus ci` keeps it and counts it.
- `ci-prs.jsonl`, one line per pull request, rewritten each run, with the times its branch was force-pushed.

A line also has a field for each change meant to move a number.
A field is empty when the run did not give it.

- `full` and `tree`: one suite per tree.
- `selection` and `reason`: what a check that runs part of the suite ran, `all` or how many files, and why.
- `slowest_s` and `tail_s`: the slowest file, and the wall time less the summed test time over the workers.
- `cpu_pressure`, `cgroup_pressure` and `workers`: the first line of `/proc/pressure/cpu`, the first line of the job's `cpu.pressure`, and the worker count.
- `tmp_inode_pct`.

A job gives these fields while it runs, and `jbus ci --notice` is the only way to give them.
`jbus ci --notice full=true workers=4 cpu_pressure="$(head -n 1 /proc/pressure/cpu)"` prints a `::notice title=jstack-ci::` annotation holding the fields as JSON, and the collector reads it back from the job's check run.
The API cannot read a job summary, so the fields travel in the annotation.
Where `GITHUB_STEP_SUMMARY` is set, `--notice` also writes the fields there as a table.
`--notice` refuses a name that is not a field of the line.

### The nine targets

Each target is counted over the period, from job-level rows only.
A job counts once, and a run never does.
Four targets count only the jobs of self-hosted runners, whose `kind` is `local`: queue, wasted-minute share, own-cause reds and time-to-green.
Queue, wasted-minute share and time-to-green also show the figure for GitHub-hosted runners beside the self-hosted one.
On a repo that runs on GitHub-hosted runners alone, these four targets read `no data`.
The other five count every pull request, push to main or job, whatever runner it ran on.
Flaky tests reads a red job's failing tests from the log of a self-hosted job only, so on a hosted-only repo it counts 0.

| Target | Held to | Counted as |
| --- | --- | --- |
| queue p50 under exec p50 | the wait is under the run | median minutes from `created` to `started`, against the median from `started` to `completed`, of green jobs. A job cancelled while it waited is in neither. |
| wasted-minute share | under 15% | execution minutes of jobs that failed or were cancelled, over all execution minutes |
| own-cause reds | over 70% | of the failed local jobs on a run's last attempt, the share that is the pull request's own. A red job is `main` when main was red with the same failing tests when the job started. It is `runner` when its log shows a runner fault and another branch fails the same tests, and `flake` when no fault shows. Any other red job is `own`. |
| rebases per merged PR | under 0.3 | force-pushes of the branches of the pull requests merged in the period, over those pull requests |
| staleness-only rebases | none | force-pushes whose cause was only that main had moved, read from the jbus event that came before them |
| time-to-green p50 | under 15 min | median minutes from the first job on a merged pull request's final head to the last green one |
| main-red minutes per day | under 30 min | minutes main was red, from its first failed run to the next green one, per day |
| flaky tests | under 3 | tests that failed two branches with no runner fault and no red main to blame |
| /tmp inode peak | under 80% | the highest `tmp_inode_pct` a job wrote. It shows no data until a job writes one. |

`features/jbus/tests/fixtures/ci/` holds a recording of the Actions API that the tests count these numbers from.

### The week's report

The report is optional, and a project asks for it with `ci_report = true` in its `[[project]]` table of `~/.config/jbus/config.toml`.
The install enables `jbus-ci.timer` only while a project asks for the report.
When no project asks, the install leaves the timer off, and nothing alerts.
The timer runs `jbus-ci.service` every Monday at 09:00 in the machine's own zone.
With `Persistent=true`, a run the machine slept through starts once the machine is up.
The service runs `jbus ci --report --each`.
For each project that asks, it collects, then writes `reports/ci-week-<date>.md` in that project's home.
The report has the nine targets over the last 7 days, each with how it was counted.
It counts the jobs, the local and the hosted ones apart, and says how many were cancelled while they waited.
It ends with main's red minutes by day.
A week where every target is met, or has no data, sends nothing.
A week with a target missed sends one `alert` event, naming each target missed and the report, once for that day.
A run that fails shows in `journalctl --user -u jbus-ci`.

The `ci` panel of [the view](the-view.md) opens at `#/<project>/ci`.
It has no card, so the first screen keeps its size.
It draws from the same files: each target with its value and what it is held to, and its series by day.
`MARKS` in `features/jbus/src/jbus/view/panels/ci/panel.py` names the slugs of changes to CI.
Where one of those slugs merged in the project's home, the panel draws a dashed mark at its merge.
A repo where none of them merged has no mark.
