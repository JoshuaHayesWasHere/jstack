"""Two of the records the kpi-lab swarm found missing: the arm of each launch (`launch_arms`,
`jbus.telemetry.launches`), and each review round of a pull request (`review_rounds`,
`jbus.reviewed.rounds`)."""

from jbus.telemetry import launches
from jbus.telemetry.migrations import tables

SQL = (
    tables("review_rounds")
    + launches.TABLE_SQL
    + "CREATE INDEX review_rounds_slug ON review_rounds (project, slug, round_number);\n"
)
