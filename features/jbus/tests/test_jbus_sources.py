"""`jbus.sources.statement` reads a module's `EVENTS` or `VERBS` off the lines that declare it, and
parses those lines alone. These tests hold it, for every module of jbus, to the first statement at
the top of the module that a parse of the whole source finds setting the name, and to what it reads
as no declaration."""

import ast

import pytest

import jbus
from jbus import sources

MODULES = list(sources.modules(jbus.__path__, "jbus.", deep=True))


def whole(source, name):
    """Return the first statement at the top of the whole parsed source that sets `name`, alone or
    beside other names it sets to the same value."""
    for node in ast.parse(source).body:
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        if isinstance(node, ast.Assign | ast.AnnAssign) and name in map(ast.unparse, targets):
            return node
    return None


@pytest.mark.parametrize("name", ["EVENTS", "VERBS"])
def test_every_module_s_declaration_is_what_a_parse_of_its_whole_source_finds(name):
    for module, source in MODULES:
        read, parsed = sources.statement(source, name), whole(source, name)
        assert (read and ast.dump(read)) == (parsed and ast.dump(parsed)), module


@pytest.mark.parametrize(
    ("source", "read"),
    [
        ('EVENTS = {\n    "a": "quiet",\n}\nX = 1\n', "EVENTS = {'a': 'quiet'}"),
        ('EVENTS: dict[str, str] = {"a": "user"}\n', "EVENTS: dict[str, str] = {'a': 'user'}"),
        ("EVENTS: dict[str, str]\nX = 1\n", "EVENTS: dict[str, str]"),
        ('EVENTS = OTHER = {"a": "user"}\n', "EVENTS = OTHER = {'a': 'user'}"),
        ('EVENTS = {"a": "user"}\nEVENTS = {"b": "user"}\n', "EVENTS = {'a': 'user'}"),
        ('EVENTS = (\n    {"a": "user"}\n)\n', "EVENTS = {'a': 'user'}"),
        ('EVENTS, X = {"a": "user"}, 1\n', None),
        ('X, EVENTS = 1, {"a": "user"}\n', None),
        ('if True:\n    EVENTS = {"a": "user"}\n', None),
        ('EVENTS |= {"a": "user"}\n', None),
        ('EVENTS == {"a": "user"}\n', None),
        ('EVENTS_TOO = {"a": "user"}\n', None),
    ],
    ids=[
        "over lines",
        "annotated",
        "annotated alone",
        "beside another name",
        "set again below",
        "in brackets",
        "first of a tuple",
        "second of a tuple",
        "under an if",
        "added to",
        "compared",
        "a longer name",
    ],
)
def test_the_statement_is_the_first_at_the_left_edge_that_sets_the_name(source, read):
    found = sources.statement(source, "EVENTS")
    assert (ast.unparse(found) if found else None) == read
