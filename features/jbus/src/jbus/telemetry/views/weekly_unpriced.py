"""Each merge week's calls on its merged rows whose model `jgauge.spend.PRICES` does not price, so
`call_rows` gives them no dollars: each such model and its calls. A Codex model is priced by none,
which the dollars KPI's definition says, so it is not named."""

from jbus.telemetry.tokens import CODEX

SQL = (
    "SELECT l.week, c.model AS name, count(*) AS count "
    "FROM lead_times l JOIN call_rows c ON c.project = l.project AND c.slug = l.slug "
    f"WHERE c.provider <> '{CODEX}' AND c.dollars IS NULL GROUP BY l.week, c.model"
)
