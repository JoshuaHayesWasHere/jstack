from jbus.telemetry.measures import Measure, Sql, Zero

MEASURE = Measure(
    name="macos-on-prs",
    group="quality",
    says="runs today of the macOS workflow on a pull request, which runs nightly only",
    unit="runs",
    better="lower",
    source=Sql(
        "select count(*) as value, count(*) as n from runs"
        " where project = :project and workflow = 'macos' and event = 'pull_request'"
        " and created >= :begins and created < :ends"
    ),
    window="day",
    baseline=0,
    baseline_of="0: the workflow was switched to nightly",
    kind=Zero(),
    tier="wake",
    audit=(34,),
)
