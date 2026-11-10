from jbus.telemetry.measures import Limit, Measure, Sql

WEEK = "week in (date(:begins), date(:begins, '+1 day'))"
"""The week the window begins, a Sunday in the user's zone, whose start `:begins` holds in UTC."""

MEASURE = Measure(
    name="change-failure",
    group="quality",
    says=(
        "share of this week's merges whose commit opened a red spell of main's push check that a "
        "change caused, not a flake or the infrastructure (main-reds.jsonl); each spell is shown"
    ),
    unit="%",
    better="lower",
    source=Sql(
        f"select 100.0 * rate as value, merged as n from weekly_change_failure"
        f" where project = :project and {WEEK}",
        each=(
            "select '#' || coalesce(start_pr, '?') || ' ' || cause || ' at '"
            " || substr(start_sha, 1, 9) as label,"
            " case when cause in ('change', 'unjudged') then 1.0 else 0.0 end as value,"
            f" null as line from main_spells where project = :project and {WEEK}"
            " order by first_fail_at"
        ),
    ),
    window="week",
    baseline=3.0,
    baseline_of="last week's weekly_change_failure, the week of 2026-11-01",
    kind=Limit(3.6, 20),
    tier="page",
    each_unit="counted, 1, or not, 0",
)
