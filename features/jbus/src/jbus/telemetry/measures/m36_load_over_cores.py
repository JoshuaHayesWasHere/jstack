"""The share of today's rows of jgauge's load.tsv (`load_samples`) whose 1-minute load is above the
row's cores.

Its line is kept at 6.5%, not set from `jgauge room`'s lines: none of them fits. Each of room's
lines bounds one reading (load at 200% of the cores, CPU pressure at 40, `room.sh`), where this
measure is a share of a day's readings over 100% of the cores, a line room does not draw.
"""

from jbus.telemetry.measures import Limit, Measure, Sql

MEASURE = Measure(
    name="load-over-cores",
    group="machinery",
    says="share of today's load samples above the core count",
    unit="%",
    better="lower",
    source=Sql(
        "select 100.0 * avg(load1 > cores) as value, count(*) as n from load_samples"
        " where project = :project and at >= :begins and at < :ends"
        " and cores > 0 and load1 is not null",
        machine=True,
    ),
    window="day",
    baseline=5.4,
    baseline_of="the audit of 2026-11-09",
    kind=Limit(6.5, 100),
    tier="page",
    audit=(40,),
)
