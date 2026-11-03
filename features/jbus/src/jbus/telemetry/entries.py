"""A package whose modules are its entries, one each, collected in the order of their names.

A tuple each change appends to is one place every change edits, so two changes that each add an
entry conflict when they merge. A package of entries has no such place: an entry is a new file,
and the order is the modules' names sorted, never the order in which they were imported. The
KPIs (`jbus.telemetry.kpis`), the views (`jbus.telemetry.views`) and the migrations
(`jbus.telemetry.migrations`) are each such a package.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Iterable
from types import ModuleType


def modules(package: str, path: Iterable[str], form: str) -> list[ModuleType]:
    """Each module of `package`, found at `path`, in the order of their names. A module whose
    name `form` does not match in full is refused: its place in the order would be by chance."""
    names = sorted(found.name for found in pkgutil.iter_modules(path))
    stray = [name for name in names if not re.fullmatch(form, name)]
    if stray:
        raise ImportError(f"{package}: {', '.join(stray)} not named as {form}")
    return [importlib.import_module(f"{package}.{name}") for name in names]
