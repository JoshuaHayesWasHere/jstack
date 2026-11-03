"""Each read of which instances are capped (`capped_reads`), and the minutes it holds every
instance capped.

A read that found every instance capped holds until the next read, of either reader, or until its
`ends_at`, the first reset the ledger gives, whichever is first. The last read holds up to the last
build. Reads are ordered by time and each counts only up to the next, so two readers' reads of the
same minutes count it once. The pass reads every minute and `jgauge limits` every 2, so a spell's
minutes are right to about a minute at each end. A read's minutes count in the week of the read.
"""

from jbus.telemetry.schema import WEEK

SQL = (
    "WITH reads AS (SELECT *, lead(at) OVER (ORDER BY at, key) AS next_at FROM capped_reads "
    "WHERE at IS NOT NULL) SELECT at, day, "
    f"{WEEK.format(day='day')} AS week, reader, instances, capped, ends_at, next_at, "
    "CASE WHEN ends_at IS NULL THEN 0 ELSE round(max(0, julianday(min(coalesce(next_at, "
    "(SELECT max(at) FROM builds), ends_at), ends_at)) - julianday(at)) * 1440.0, 4) END "
    "AS minutes FROM reads"
)
