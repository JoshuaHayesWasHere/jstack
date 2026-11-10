from jbus.telemetry.measures import Limit, Measure, Sql
from jbus.telemetry.schema import RED

OWN = (
    "make *",
    "new lines",
    "prose lint",
    "lint *",
    "quick tests*",
    "handed tests",
    "test",
    "check",
)
"""The failed steps that are a change's own defect, as GLOB patterns: a make target (`make test`,
`make check-fast: lint`, and the bare target a log names where the step has no name), the guard
of the added lines, and a lint. Any other step a failed job names is the runner's fault: the
trailer fetch (`no AI co-author trailer`, whose name a real AI trailer shares, so a trailer in a
commit reads as the runner's too), the zsh or tla2tools fetch, the selection, an artifact. The
closing job's `every part passed` fails whenever another job did, so it is the runner's only
where no other job failed."""

_OWN = "(" + " OR ".join(f"j.step GLOB '{glob}'" for glob in OWN) + ")"

_FAILED_JOB = (
    "SELECT 1 FROM ci_jobs j WHERE j.project = c.project AND j.run = c.run "
    f"AND j.attempt = c.last_fail_attempt AND j.conclusion IN {RED} AND j.step IS NOT NULL"
)

RUNS = (
    "WITH counted AS (SELECT project, run, sha, day, created, last_fail_attempt, "
    "first_fail_attempt IS NOT NULL AS failed FROM run_attempts "
    "WHERE project = :project AND workflow = 'check' AND event = 'pull_request' "
    "AND created >= :begins AND created < :ends "
    "AND (first_fail_attempt IS NOT NULL OR last_conclusion = 'success')), "
    "classed AS (SELECT c.failed, CASE WHEN NOT c.failed THEN NULL "
    f"WHEN EXISTS ({_FAILED_JOB} AND {_OWN}) THEN CASE WHEN EXISTS (SELECT 1 FROM runs l "
    "WHERE l.project = c.project AND l.sha = c.sha AND l.workflow = 'check' "
    "AND l.event = 'pull_request' AND l.conclusion = 'success' AND l.day >= c.day "
    "AND (l.run = c.run AND l.attempt > c.last_fail_attempt "
    "OR l.run <> c.run AND l.created > c.created)) THEN 'flake' ELSE 'own defect' END "
    f"WHEN EXISTS ({_FAILED_JOB}) THEN 'runner fault' ELSE 'unknown' END AS class "
    "FROM counted c) "
)
"""Each check run on a pull request created in the window, once, read by its attempts: it is
counted where it failed at any attempt or its last attempt passed, so a run whose last attempt
was cancelled, or that has not ended, is not. A run that failed is classed by the failed jobs of
its last failed attempt: the runner's fault where none failed at an own step (`OWN`) and one
failed at another, and otherwise a flake where a later attempt of it, or a later run at the same
head, passed, and the change's own defect where none did. A failed run whose failed jobs name no
step, or that has none in the store, is `unknown`: it counts in the value and in no part."""

CLASSES = ("own defect", "runner fault", "flake")
"""The parts, in the order the scorecard shows them, each shown at 0 where no run is of it."""

_CLASSES = " UNION ALL ".join(f"SELECT {i} AS i, '{c}' AS label" for i, c in enumerate(CLASSES))

MEASURE = Measure(
    name="pr-checks-failed",
    group="quality",
    says=(
        "share of today's check runs on pull requests that failed at any attempt, each run once "
        "and a cancelled one left out; each class of failure is shown: own defect, runner fault, "
        "flake"
    ),
    unit="%",
    better="lower",
    source=Sql(
        RUNS + "SELECT 100.0 * sum(failed) / nullif(count(*), 0) AS value, count(*) AS n "
        "FROM classed",
        each=RUNS + "SELECT k.label, 100.0 * (SELECT count(*) FROM classed WHERE class = k.label) "
        f"/ (SELECT count(*) FROM classed) AS value, NULL AS line FROM ({_CLASSES}) k "
        "WHERE EXISTS (SELECT 1 FROM classed) ORDER BY k.i",
    ),
    window="day",
    baseline=33.8,
    baseline_of="the audit of 2026-11-09: 33.8 to 48%; 5.4% on 2026-11-05",
    kind=Limit(30, 10),
    tier="page",
    audit=(29,),
    each_unit="% of the runs",
)
