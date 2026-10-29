"""Read what a module of jbus declares at its top off its source, and import nothing.

`jbus.wake` reads each module's `EVENTS` this way, and `jbus.verbs` each module's `VERBS`. So a
module that imports either one can still declare to it, and `jbus --help` lists every verb
without loading the module of any. `modules` gives each module's name and source. `statement`
finds the one statement that declares a name, and parses that statement alone: parsing the
whole source of every module took 100 ms on each command.

The statement is the first line of the source that starts at its left edge with the name alone,
set (`NAME = ...`) or annotated (`NAME: <type> = ...`), and the lines under it up to the next
line that starts at the left edge with anything but a closing bracket. That is where `ruff
format` ends a statement at the top of a module. So the name among the names of a tuple, set
under an `if` or a `try`, or added to with `|=`, is no declaration, and nor is the name set
again below. A line of a string that starts at the left edge with the name would read as one:
a test holds every module of jbus to what a parse of its whole source finds.
"""

from __future__ import annotations

import ast
import pkgutil
import re
from collections.abc import Iterable, Iterator

_END = re.compile(r"^[^\s)\]}]", re.M)


def modules(paths: Iterable[str], prefix: str, deep: bool = False) -> Iterator[tuple[str, str]]:
    """Return every module under `paths`, each as its name and its source, and with `deep` the
    modules of its subfolders too."""
    for module in pkgutil.iter_modules(paths, prefix):
        spec = module.module_finder.find_spec(module.name)
        yield module.name, spec.loader.get_source(module.name)
        if deep and module.ispkg:
            yield from modules(spec.submodule_search_locations, f"{module.name}.", deep)


def statement(source: str, name: str) -> ast.stmt | None:
    """Return the statement at the top of `source` that declares `name`, parsed alone, or None
    where there is none. A statement that does not parse alone raises a `SyntaxError`."""
    start = re.search(rf"^{re.escape(name)}[ \t]*(?::|=(?!=))", source, re.M)
    if start is None:
        return None
    end = _END.search(source, start.end())
    return ast.parse(source[start.start() : end.start() if end else len(source)]).body[0]
