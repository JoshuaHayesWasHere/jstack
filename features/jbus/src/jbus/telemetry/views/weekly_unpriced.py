"""Each merge week's calls on its merged rows, of the provider whose models `jgauge.spend.PRICES`
prices (`tokens.PRICED`), whose model the table does not price, so `call_rows` gives them no
dollars: each such model and its calls. Another provider's model is priced by none, which the
dollars KPI's definition says, so it is not named."""

from jbus.telemetry.tokens import PRICED

SQL = (
    "SELECT l.project, l.week, c.model AS name, count(*) AS count "
    "FROM lead_times l JOIN call_rows c ON c.project = l.project AND c.slug = l.slug "
    f"WHERE c.provider = '{PRICED}' AND c.dollars IS NULL GROUP BY l.project, l.week, c.model"
)
