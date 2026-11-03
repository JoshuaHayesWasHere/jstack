"""How a store of an older schema is brought up to this one: one module a migration.

`PRAGMA user_version` is the schema's version. A migration is a module of this package,
`v<NNN>_<slug>.py`, whose `SQL` takes a store from version `NNN - 1` to `NNN`, and `MIGRATIONS`
holds them in the order of the modules' names (`jbus.telemetry.entries`), so `MIGRATIONS[n]` takes
a store from version `n` to `n + 1`. `jbus.telemetry.migrate` runs the ones a store has not had,
each once, in one transaction with its new version.

A store knows only its version, not which migrations it had, so a new migration's name sorts after
every migration a store can have had: its `NNN` is one more than the last one's. Two changes that
each add the same `NNN` are refused when the second is collected, never run out of order. A
migration that has merged is never edited, renamed or removed. The store holds rows its sources
no longer have (the daily trim, a snapshot's dropped record), so it is never dropped and built
again: a change to a table is a new migration, such as `ALTER TABLE <t> ADD COLUMN <c>`.
"""

from __future__ import annotations

from jbus.telemetry import entries
from jbus.telemetry.records import SOURCES, Source

MIGRATION_MODULE = r"v(\d{3})_[a-z0-9_]+"
"""The name of a migration's module: the version it brings a store to, three digits, and its
slug."""


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


def _collect(package: str, path: list[str]) -> tuple[str, ...]:
    """Each migration's `SQL` in order, refused where the versions are not 1, 2, 3 and on."""
    found = entries.modules(package, path, MIGRATION_MODULE)
    for version, module in enumerate(found, 1):
        name = module.__name__.rpartition(".")[2]
        if not name.startswith(f"v{version:03d}_"):
            raise ImportError(f"{package}: {name} is migration {version}: name it v{version:03d}_")
    return tuple(module.SQL for module in found)


MIGRATIONS: tuple[str, ...] = _collect(__name__, __path__)
"""`MIGRATIONS[n]` takes a store from version `n` to `n + 1`."""
