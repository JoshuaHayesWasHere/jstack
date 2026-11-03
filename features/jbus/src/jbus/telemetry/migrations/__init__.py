"""How a store of an older schema is brought up to this one: one module a migration.

A migration is a module of this package, `v<NNN>_<slug>.py`, whose `SQL` changes the store's
tables, and `MIGRATIONS` holds each one's `SQL` by its name, in the order of the names
(`jbus.telemetry.entries`). The store keeps the name of each migration it has run in its
`migrations` table, and `jbus.telemetry.migrate` runs each one it has not, in name order, each
once, in one transaction with its name.

`NNN` only orders the names: it need not be free or one more than the last. Two changes that each
add a `v010_` both run, on a store that has run neither in name order, and on a store that has
run one of them the other alone, so a migration changes only what is there at every name before
it, never what another of its `NNN` makes. A migration that has merged is never edited, renamed
or removed. The store holds rows its sources no longer have (the daily trim, a snapshot's dropped
record), so it is never dropped and built again: a change to a table is a new migration, such as
`ALTER TABLE <t> ADD COLUMN <c>`.
"""

from __future__ import annotations

from jbus.telemetry import entries
from jbus.telemetry.records import SOURCES, Source

MIGRATION_MODULE = r"v\d{3}_[a-z0-9_]+"
"""The name of a migration's module: three digits that order it, and its slug."""


def _table(source: Source) -> str:
    """The SQL that makes a source's table."""
    columns = ", ".join(f"{name} {kind}" for name, kind in source.columns)
    return (
        f"CREATE TABLE {source.table} (project TEXT NOT NULL, key TEXT NOT NULL, {columns}, "
        f"day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
        f"CREATE INDEX {source.table}_day ON {source.table} (day);\n"
    )


def tables(*names: str) -> str:
    """The SQL that makes the tables of these sources."""
    by = {source.table: source for source in SOURCES}
    return "".join(_table(by[name]) for name in names)


def _collect(package: str, path: list[str]) -> dict[str, str]:
    """Each migration's `SQL` by its module's name, in the order of the names."""
    found = entries.modules(package, path, MIGRATION_MODULE)
    return {module.__name__.rpartition(".")[2]: module.SQL for module in found}


MIGRATIONS: dict[str, str] = _collect(__name__, __path__)
"""Each migration's `SQL` by its name, in the order a store runs them."""
