from jbus.telemetry.measures import Limit, Measure, Sql

PARTS = (
    "WITH spans AS (SELECT instance, span, min(prev) AS first, max(at) AS last, "
    "sum(rise) AS points FROM quota_rises "
    "WHERE at > strftime('%Y-%m-%dT%H:%M:%S.000000Z', :ends, '-7 days') AND at <= :ends "
    "GROUP BY instance, span), "
    "lines AS (SELECT instance, min(CASE WHEN s.points >= 5 THEN (SELECT sum(units) "
    "FROM call_rows r "
    "WHERE r.instance = s.instance AND r.day >= date(s.first, '-1 day') "
    "AND r.at > s.first AND r.at <= s.last) / s.points * 100 "
    "/ CASE s.span WHEN 'seven_day' THEN 168.0 ELSE 5.0 END END) AS line "
    "FROM spans s GROUP BY instance), "
    "parts AS (SELECT l.instance AS label, (SELECT coalesce(sum(units), 0) FROM call_rows r "
    "WHERE r.instance = l.instance AND r.day >= date(:begins, '-1 day') "
    "AND r.at >= :begins AND r.at < :ends) / 1e6 AS value, l.line / 1e6 AS line "
    "FROM lines l WHERE l.line IS NULL OR l.line > 0) "
)
"""Each account's units in the last hour, and its capped line: the units an hour it can run
without end, from the units it ran per point its quota rose over the 7 days before (`quota_rises`),
times the 100 points of a window, over the window's hours, the lower of its two windows. An
account whose windows rose under 5 points in those days has no line yet, and is shown with its
units alone: a point is where a percent rounds, and a line from one or two of them swings
tenfold."""

MEASURE = Measure(
    name="units-vs-capped-line",
    group="machinery",
    says=(
        "units an hour on the account nearest its capped line, as a share of that line, which "
        "is the units an hour that fill its quota in its window; each account is shown"
    ),
    unit="%",
    better="lower",
    source=Sql(
        PARTS + "SELECT max(100.0 * value / line) AS value, count(line) AS n FROM parts",
        machine=True,
        each=PARTS + "SELECT label, value, line FROM parts ORDER BY label",
    ),
    window="hour",
    baseline=708,
    baseline_of="the store at 2026-11-10 02:40 UTC: claudeAgent ran 36.9 M of a 5.2 M line",
    kind=Limit(100, 1),
    tier="page",
    each_unit="M units an hour",
)
