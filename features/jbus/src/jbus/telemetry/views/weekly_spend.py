"""Each week of `spend_kept`: its units, and the shares of jbus's sends and the homes
(`coordination`) and of the runs that failed on a cap (`capped`)."""

from jbus.telemetry.schema import WEEK

SQL = (
    f"SELECT {WEEK.format(day='spent_on')} AS week, count(*) AS days, sum(units) AS units, "
    "100.0 * sum(coalesce(sends, 0) + coalesce(homes, 0)) / nullif(sum(units), 0) "
    "AS coordination, 100.0 * sum(coalesce(capped, 0)) / nullif(sum(units), 0) AS capped "
    "FROM spend_kept GROUP BY 1"
)
