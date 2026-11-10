"""Each merge week's calls on its merged rows, of the provider whose models `jgauge.spend.PRICES`
prices (`tokens.PRICED`), whose model the table does not price, so `call_rows` gives them no
dollars: each such model and its calls. A row's calls are the ones `row_spend` gives it (its
`OWNED`): its own threads', the home turns that led to it, and its scout's even share, which
counts as a part of a call, as `row_spend`'s `unpriced` does. Another provider's model is priced by
none, which the dollars KPI's definition says, so it is not named."""

from jbus.telemetry.tokens import PRICED
from jbus.telemetry.views.row_spend import OWNED

CALLS = "round(sum(o.share), 2)"
"""A week's calls of a model, a scout's share as its part of a call, to two places."""

SQL = (
    f"WITH {OWNED} "
    "SELECT l.project, l.week, o.model AS name, "
    f"CASE WHEN {CALLS} = CAST({CALLS} AS INTEGER) THEN CAST({CALLS} AS INTEGER) "
    f"ELSE {CALLS} END AS count "
    "FROM merged_rows l JOIN owned o ON o.project = l.project AND o.slug = l.slug "
    f"WHERE o.provider = '{PRICED}' AND o.dollars IS NULL GROUP BY l.project, l.week, o.model"
)
