from jbus.telemetry.kpis import Kpi, Measured
from jgauge import spend

WAITING = (
    "CASE WHEN waiting > 0 THEN waiting || ' merge' || iif(waiting = 1, '', 's') "
    "|| ' of the week not judged yet, whose calls count' END"
)
"""The week's merges whose 7 days are not over: all-in counts their calls, and not them yet."""
OWN = (
    "CASE WHEN merges > 0 THEN 'own threads $' || printf('%.2f', own_dollars_mean) || "
    "' mean, $' || printf('%.2f', own_dollars_median) || ' median a merge' END"
)
BY = (
    "'by role, model and effort a merge: ' || (SELECT group_concat(name || ' $' || "
    "printf('%.2f', dollars / weekly_merge_cost.merges), ', ') FROM (SELECT role || ' ' || "
    "model || ' ' || coalesce(effort, 'no effort') AS name, sum(dollars) AS dollars "
    "FROM merge_cost WHERE week = weekly_merge_cost.week AND dollars IS NOT NULL "
    "GROUP BY role, model, effort ORDER BY sum(dollars) DESC, name))"
)
"""Each role, model and effort's own-thread dollars of the week's successful merges, a merge, the
dearest first."""

KPI = Kpi(
    "All-in dollars per successful merge",
    "cost",
    f"an estimate at API list prices, from jgauge.spend's price table of {spend.PRICED_ON}: "
    "the dollars of every priced call of the week, a home's, a scout's, an unmerged crew's and a "
    "redone row's too, over the week's successful merges, merged rows whose 7 days ended with no "
    "later row redoing them; a merge and a call count in the week 7 days after their day, so "
    "both are of the week before it; a Codex call adds no dollars. Beside it, a merge's own "
    "threads, and their dollars by role, model and reasoning effort",
    "$",
    None,
    "lower",
    Measured(
        "weekly_merge_cost",
        "all_in_per_merge",
        "merges",
        detail=f"concat_ws('; ', {WAITING}, {OWN}, {BY})",
    ),
)
