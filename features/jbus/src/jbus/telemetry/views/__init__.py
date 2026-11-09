"""The store's views, one module each: a view is `<name>.py`, whose `SQL` is the view's `SELECT`.

The views hold no rows, so `jbus.telemetry.connect` drops them and makes them again on each
build: a change to a view is a change to its module and nothing else. `VIEWS` holds them in the
order of their names (`jbus.telemetry.entries`). SQLite reads the views a view selects from only
when it is queried, so a view may read one whose name sorts after its own. The SQL they share,
such as the Sunday a week starts on, is in `jbus.telemetry.schema`.

Each `weekly_*` view gives a row per `project` and `week`, so a reader filters a project's weeks
by its name, and a week of one project counts no other's. A view of the machine as a whole, such as
the pass time, gives its rows under the project `''`.
"""

from __future__ import annotations

from jbus.telemetry import entries

VIEW_MODULE = r"[a-z][a-z0-9_]*"
"""The name of a view's module, which is the view's name."""

VIEWS: tuple[tuple[str, str], ...] = tuple(
    (module.__name__.rpartition(".")[2], module.SQL)
    for module in entries.modules(__name__, __path__, VIEW_MODULE)
)
"""Each view by its name, in the order of the names."""
