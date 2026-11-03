"""The seconds of each jbus pass (`passes.jsonl`), by the week it ran in."""

from jbus.telemetry.schema import WEEK

SQL = (
    f"SELECT {WEEK.format(day='day')} AS week, seconds FROM passes "
    "WHERE day IS NOT NULL AND seconds IS NOT NULL"
)
