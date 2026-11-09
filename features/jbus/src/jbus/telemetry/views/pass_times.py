"""The seconds of each jbus pass (`passes.jsonl`), by the week it ran in, with the project its line
names: the machine's, `''`, for the pass itself."""

from jbus.telemetry.schema import WEEK

SQL = (
    f"SELECT project, {WEEK.format(day='day')} AS week, seconds FROM passes "
    "WHERE day IS NOT NULL AND seconds IS NOT NULL"
)
