# Measure the CI

`jbus ci` records what a project's GitHub Actions CI costs and measures it against nine targets, so you can compare a change to CI with what came before it.
It works for any repo of the config.
It needs nothing from the repo's workflows, since the fields a job adds with `--notice` are optional.
`jbus --project <name> ci` collects and prints the nine targets, each with how it was counted.
It asks GitHub, read-only through `gh api`, for three things:

- the workflow runs of the last `--days` days, 14 by default
- the jobs of each run that has finished and is not stored yet
- the pull requests, with their timelines, where a pull request changed since it was stored

For a project whose table says `ci_report = true`, each pass of jbus keeps the same two files, so they never age between two runs of `jbus ci`.
A project that does not ask gets no call to GitHub for its CI on a pass, and no ledger in its state.
A pass asks for the runs of the last 3 hours and stores at most 30 new runs, so a pass after a gap catches up over the next few passes.
It asks for the pull requests updated in those 3 hours or since the newest update `ci-prs.jsonl` holds, whichever reaches back further, and at most 14 days back, so a pass after a gap keeps every pull request merged in it.
It asks only while GitHub answered the pass and its API budget is above the floor, and it never waits while `jbus ci` holds the files.
A run that finishes more than 3 hours after GitHub created it waits for the next `jbus ci`.


It keeps what it collects in two files in the project's state directory:

- `ci.jsonl`, one line per job.
  A second run adds no line it already has.
  A line holds the run, the job and the attempt.
  It also holds the job's `name`, `sha`, `branch`, `pr`, `event`, `created`, `started`, `completed` and `conclusion`.
  It names the `runner` and its `kind`, `hosted` or `local`.
  For a red job on either kind of runner, it lists the failing `tests` and the runner faults (`signs`) that the job's log shows, and `logged` says the log was read.
  Its `step` names the step GitHub says failed, with the make target the log says failed first where the step's name does not end in it: `make check-fast: lint` for a shard that failed its lint before a test ran.
  A red job kept before `jbus ci` kept the step has no `step` field, and the next collect whose days reach it reads its run's jobs and its log and rewrites the file, or leaves it for a later collect where GitHub did not give either.
  A job cancelled while it waited has no runner and no start, and `jbus ci` keeps it and counts it.
- `ci-prs.jsonl`, one line per pull request, rewritten when one changed, with the time GitHub last updated it and the times its branch was force-pushed.

A line also has a field for each change meant to move a number.
A field is empty when the run did not give it.

- `full` and `tree`, which belong to the change that runs one suite per tree.
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

`jbus ci` counts each target over the period, from job-level rows only.
A job counts once, and a run never does.
Each target counts the jobs that ran on self-hosted runners (`kind` `local`) and on GitHub-hosted runners together, so a repo that runs on one kind alone still gets all nine numbers.
Each number names the runners it covers, with how many jobs of each, as in `local 3, hosted 40`.
Rebases per merged PR and staleness-only rebases count pull requests, not jobs, and say `pull requests, any runner`.

| Target | Held to | Counted as |
| --- | --- | --- |
| queue p50 under exec p50 | the wait is under the run | median minutes from `created` to `started`, against the median from `started` to `completed`, of green jobs. A job cancelled while it waited is in neither. |
| wasted-minute share | under 15% | execution minutes of jobs that failed or were cancelled, over all execution minutes |
| own-cause reds | over 70% | of the failed jobs on a run's last attempt, the share that is the pull request's own. A red job whose log was not read is `unread`, and counts against the share. Otherwise a red job is `main` when main was red with the same failing tests when the job started. It is `runner` when its log shows a runner fault and another branch fails the same tests, and `flake` when no fault shows. Any other red job is `own`. |
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
For each project that asks, it collects the jobs and pull requests, then writes `reports/ci-week-<date>.md` in that project's home.
The report has the nine targets over the last 7 days, each with how it was counted.
Beside each number it names the runners that number covers.
It gives the number of local jobs and the number of hosted jobs.
It also gives how many jobs were cancelled while they waited.
It gives main's red minutes by day.
It ends with S8, the wrong closes of gates, for each week a scout labelled by [Gate labels](gate-labels.md).
S8 is the share of gates closed by silence or by your word whose chosen option did not stand, of those whose outcome is known, with silence and your word apart.
For the Sunday-to-Saturday week that ended last, a week with no labels file says "not labelled" and gives no number.
The report then queues one scout row, `scout-gate-labels-<the week's first day>`, to label that week, and a week in which no gate was asked queues none.
The row follows `scorecard-s8`, whose go was the owner's word that a scout labels each week, so the follow-up rule approves it.
A week where every target is met, or has no data, sends nothing.
A week with a missed target sends one `alert` event, only once that day.
The event names each missed target and the report.
A run that fails shows in `journalctl --user -u jbus-ci` on Linux, and in `~/Library/Logs/jstack/jstack.jbus-ci.log` on macOS.

### The day's report

`jbus --project <name> ci --day` writes `reports/ci-day-<date>.md` in the project's home, and then checks main's live ruleset.
`jbus-ci-day.timer` runs `jbus-ci-day.service` every day at 06:45 in the machine's own zone, with `Persistent=true`, and the service runs `jbus ci --day --each` for each project whose table says `ci_report = true`.
The install enables the timer only while a project asks, as it does `jbus-ci.timer`.
`--day` collects nothing and starts no CI job: every number but main-red and the review step's comes from the ledger the passes keep, `ci.jsonl` and `ci-prs.jsonl`, and the rows that merged come from `transitions.jsonl`.
Main-red comes from one call, `gh run list -R <repo> --workflow check.yml --branch main --event push --limit 400 --json conclusion,status,createdAt,updatedAt,headSha`, the only call `--day` makes to GitHub.
Where that call fails, main-red reads `no data`, the report says why, and the rest of the report is written as usual.
The review step's numbers come from T3 Code's store, `~/.t3/userdata/statev2.sqlite`, opened read-only (`jgauge.spend.reviews`).
Where the store is not there or cannot be read, they read `no data`, the report says why, and the rest of the report is written as usual.
`--day` with `--report` is refused.

The ruleset check (`jbus.ci.ruleset`) reads the ruleset GitHub holds main to with one more call, `gh api repos/<repo>/rulesets/25665226`.
It compares the ruleset's `rules` with `features/repo-guards/main-ruleset.json` in the project's checkout, and its required status checks with the home's `required-checks`, which jmerge waits for.
Where they differ, it tells the home one line that names each difference, such as `it lacks macos of required-checks`, raised once for the day.
Where they agree, it prints `no drift`.
A checkout with no `main-ruleset.json` is not checked and costs no call, and a ruleset `gh` does not give is printed and tells no one.
It runs here and not in `make check`, so no pull request's check reads GitHub for it.

This is the one definition of the numbers the report gives, and `jbus.ci.daily` counts by it.
The figures the cicd plan started from, 64% red and 5.6 shas per pull request, came from a UTC day and from grouping `gh` runs by branch, and they stay as history, not as the baseline.

- **A day** is a local day of the user's zone, or of the machine's where none is set, from midnight to midnight, never UTC.
  A day the clocks change on has 23 or 25 hours.
- **The 7 days** are the 7 whole local days before the day the report runs, so the 06:45 run gives yesterday as its newest day.
- **n** is under each cell: the pull requests, jobs, runs or merged pull requests the cell counted.
- **A day under 20 pull requests** with a `check` run reads `no data` for every number from the ledger, with its n still shown.
  The ledger misses runs while jbus is down, or when more than 30 runs land in 3 hours, and a thin day shows that instead of a number.
  Head shas and open to merge count the pull requests merged that day, but the floor is the red share's n.
  Main-red is not under the floor, since `gh` gives it.
- **A wave day** is a day whose shard wait p90 is over 300 s, and its column reads `wave`.
  A wave confounds a before and after: Nov 3 and 4 measure #970 and #1009, not the rows that merged then.
- **jmerge's shadow pull requests**, whose branch starts `jstack/line/`, are left out of every count.
- **A review launch** is a thread of the project's T3 Code project that jbus titled `review: <slug>, <round>`, `<round>` being `1` or `scoped`, of any model.
  A launch that failed on its provider and was launched again on another counts twice, its tokens with it.
  Its day is the local day its first run started.
  Its tokens are its runs' summed: input is every input token, the cached and the cache-written among them.
  Its **active wall** is the time its runs ran, each from its `startedAt` to its completion, so the wait between two turns is not in it.
- **A launch's pull request** is the one its slug's brief, `tasks/<slug>.md` in the home, names on the first `Branch:` line that names one, as `jbus.watch.tied` reads it.
  Per pull request, a day sums the launches of that pull request that started that day, so a pull request reviewed on two days counts on each.
  The review numbers are not under the floor, since the store gives them.

| Number | Target | Counted as |
| --- | --- | --- |
| red share | at most 30% (proposal) | of the pull requests with a `check` job that ran (green or red) created that day, the share with a red one, any attempt. A `check` skipped whole ran nothing and is no `check` run. n is the pull requests. |
| head shas per merged PR | at most 3 (proposal) | the distinct head shas any `pull_request` job ran on, per pull request merged that day. The week report's `shas per merged PR` counts the crew's heads only, and is another number. n is the merged pull requests. |
| shard wait p90 | at most 60 s (proposal) | the 90th percentile of the seconds a pull request's `check N of M` job waited for a runner, `created` to `started`, over the jobs created that day that started. n is the jobs. |
| macos wait p90 | at most 120 s (proposal) | the same, for the `macos N of M` jobs, each a part of macos.yml's Mac tests on its own Mac, and not the gate `macos`, which runs on Linux once the parts end. |
| PR check wall p50 | at most 10 min (proposal) | the median minutes of a pull request's check run (one run attempt), from its first job's `created` to its last job's `completed`, over the attempts whose `check` was green or red, by the day the first job was created. n is the run attempts. |
| open to merge p50 | at most 1 h (proposal) | the median hours from a pull request's opening to its merge, over those merged that day. |
| first-check own red | none proposed | of the pull requests whose first `check` was created that day, the share whose first check was red for a cause of its own, as the health numbers count it. |
| main-red | at most 30 min (proposal) | the minutes of the day inside a spell, by the spell method of gap-revert-oldest-red: a spell runs from the `createdAt` of a failed run of check.yml on a push to main, found green, to the `updatedAt` of the next run to succeed, in the order the runs were created, and it is split at local midnight. A run not completed, cancelled or skipped says nothing, and a spell still open runs to now. `gh run list` shows a run's last attempt only, so a red that went green on a rerun is not a spell. A day that starts before the oldest run the call gave reads `no data`. n is the runs created that day. |
| review launches | none proposed | the review launches that started that day, those of a slug whose brief names no pull request among them. n is the pull requests they are joined to. |
| review input tokens per PR p50 | none proposed | the median, over the pull requests reviewed that day, of the input tokens of each one's launches that day. n is the pull requests. |
| review output tokens per PR p50 | none proposed | the same, for the output tokens. |
| review active wall per PR p50 | none proposed | the same, for the minutes of active wall. |
| review launches before check | none proposed | of the launches that day joined to a pull request whose newest head, `head` in `ci-prs.jsonl`, has a `check` job in the ledger, those that started before the first green `check` at that head completed, or at a head whose `check` was never green. The newest head is the ledger's as the report runs, so a push after a day's reviews counts those reviews as before `check`. n is the launches counted. |

Each target is a proposal only, from the quiet days of Oct 29 to 31.
No number is held to one, and the report raises no alert or page.
`jbus.kpis` keeps its own main-red page, over 30 minutes a day, read from the telemetry store.
The week report's `main-red minutes per day` counts from the ledger, from the first failed run's completion, and is not this number.

The report has three parts.
**By day** gives a row per number and the n row under it, with a column for each of the 7 days.
**Before and after each cicd row that merged** gives a row for each row of the cicd home, the home its brief's `Home:` line names, that merged in the last 14 days, at its last merge in `transitions.jsonl`.
For each number it gives the median over the 3 busy days before the merge's day against the 3 busy days after it, where a busy day has at least 20 pull requests, sought at most 21 days back.
It reads `moved` only when the median after is outside the least and the most of the days before, `held` when inside, and `no data` without 3 busy days on each side: `(2 of 3)` beside the days says how many it has.
Its notes say `shared with` another row that merged within 3 days of it, so neither is given the move, and `wave` when a wave day is among the days counted.
Main-red rarely reaches back to the days before, since the call gives about a week of runs.
**The newest day** is a line per number for the last day, which `jbus digest` gives under `ci`.

`jbus digest --json` gives, for each project, `ci`: the newest day's report's `path`, its `date`, the `day` its lines are from, those `lines`, and `stale`, true when the report was written before the timer's last 06:45.
A timer that failed leaves the old date in the digest, not a gap.
A project with no day's report has `ci` null.
