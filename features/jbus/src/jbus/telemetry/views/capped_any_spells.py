"""Each read of which instances are capped (`capped_reads`), the minutes it holds, and of those the
minutes it holds one instance or more capped.

A read holds until the next read, of either reader, or the last build for the last read, and never
over `HOLD` minutes, so a gap no reader saw counts as no time at all, capped or not. `held` is the
minutes a read holds; `minutes` is the same where the read found one instance or more capped, and 0
where it found none. Reads are ordered by time and each counts only up to the next, so two readers'
reads of the same minutes count them once. A read's minutes count in the week of the read.

`capped_spells` counts only the reads that found every instance capped, when no launch can start;
this view counts the minutes launches ran on fewer accounts than the machine has.
"""

from jbus.telemetry.schema import WEEK

HOLD = 5
"""The most minutes one read holds. The pass reads about twice a minute and `jgauge limits` every
2, so while either runs no read holds near this; a longer gap is time no reader saw."""

SQL = (
    "WITH reads AS (SELECT *, lead(at) OVER (ORDER BY at, key) AS next_at FROM capped_reads "
    "WHERE at IS NOT NULL), held AS (SELECT *, round(max(0, min(julianday(coalesce(next_at, "
    f"(SELECT max(at) FROM builds), at)) - julianday(at), {HOLD} / 1440.0)) * 1440.0, 4) "
    f"AS held FROM reads) SELECT project, at, day, {WEEK.format(day='day')} AS week, reader, "
    "instances, capped, next_at, held, CASE WHEN capped > 0 THEN held ELSE 0 END AS minutes "
    "FROM held"
)
