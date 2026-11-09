"""The SQL the store's views share: the Sunday a week starts on, the conclusions of a red and a
green check, a message the user typed, a call's spend in units and in dollars, and each week's
quantiles.

The store's tables are made by its migrations (`jbus.telemetry.migrations`), and each view is a
module of its own (`jbus.telemetry.views`), whose docstring says what it counts.
"""

from __future__ import annotations

from jgauge import spend

UNITS = (
    f"(c.input * {spend.PLAIN!r} + c.cache_write * {spend.WRITTEN!r} "
    f"+ c.cache_read * {spend.CACHED!r} + c.output * {spend.OUTPUT!r}) "
    f"* (CASE WHEN instr(c.model, '{spend.OPUS_NAME}') > 0 THEN {spend.OPUS!r} ELSE 1 END)"
)
"""A call's spend in `jgauge spend`'s units, built from `jgauge.spend`'s rates as
`jgauge.spend.units` weighs a run: `c.input` is the uncached input, and Opus goes by the call's
own model. `instr` matches case and all, as Python's `in` does, where `LIKE` would not."""
DOLLARS = (
    "(CASE c.model "
    + " ".join(
        f"WHEN '{model}' THEN c.input * {price.plain!r} + c.cache_write * {price.written!r} "
        f"+ c.cache_read * {price.cached!r} + c.output * {price.output!r}"
        for model, price in spend.PRICES.items()
    )
    + " END) / 1e6"
)
"""A call's estimated dollars at `jgauge.spend.PRICES`, as `jgauge.spend.dollars` gives them, by
the call's exact model: NULL for a model the table does not price."""
RED = "('failure', 'timed_out', 'startup_failure', 'action_required')"
GREEN = "('success', 'skipped', 'neutral')"
WEEK = "date({day}, '-6 days', 'weekday 0')"
"""The Sunday a local date's week starts on."""
WAIT = 120
"""The minutes a typed message waits for a reply before it is a lost ask: in the audit week
(2026-10-25 to 10-31) each of the user's 603 messages had its first reply within 2 hours, 597
within 5 minutes."""
TYPED = (
    "role = 'user' AND created_by = 'user' AND id NOT LIKE 'limit-resume:%' AND kind <> 'dropped'"
)
"""A message the user typed: T3 Code's `createdBy` is the user, it is not T3 Code's resume after
a usage limit, and its text is not one T3 Code or an agent put in the user's turn."""
CREW_FIX = (
    "('no-fixed', 'fix-unreviewed', 'content-changed', 'dropped', 'scoped-unruled', "
    "'unruled-drops', 'declines-unruled')"
)
"""The labels of `merge.log`'s waits on a crew's fix round: findings not handled, a fix not
reviewed, content changed after its review, and drops a rebase made and no one ruled on."""


def quantiles(table: str, value: str) -> str:
    """The median and the 85th percentile of `value` over each project's week of `table`, of the
    values that are 0 or more: the median as `statistics.median`, the mean of the two middle
    values for an even count, and the 85th as the scorecard's `pct`, the value at index
    `min(n - 1, int(0.85 * n))` of the sorted values."""
    return (
        f"WITH ranked AS (SELECT project, week, {value} AS value, "
        f"row_number() OVER (PARTITION BY project, week ORDER BY {value}) AS place, "
        f"count(*) OVER (PARTITION BY project, week) AS n FROM {table} WHERE {value} >= 0) "
        "SELECT project, week, max(n) AS n, "
        "avg(CASE WHEN place IN ((n + 1) / 2, (n + 2) / 2) THEN value END) AS median, "
        "max(CASE WHEN place - 1 = min(n - 1, CAST(0.85 * n AS INTEGER)) THEN value END) AS p85, "
        "max(value) AS most FROM ranked GROUP BY project, week"
    )
