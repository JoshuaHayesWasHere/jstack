"""No module of `LAYERED` is in a cycle of imports, as `scripts/select_tests.py` reads them.

The picker selects a test for a change when the test imports the changed module through any chain
of imports. An import inside a function is an import all the same. So a cycle makes each of its
modules reach every test that imports any one of them. These modules once sat in one cycle with
most of jbus, closed by imports inside functions, and a change to a small module of it selected
about 316 test files. A module that needs a helper of a module above it now takes the helper from
a module below both (`jbus.judged`, `jbus.review`, `jbus.told`, `jbus.launches`, `jbus.roles`).
"""

import importlib.util

import pytest

from testing.paths import REPO

READ_SET = ("features/jbus/src/", "features/jmerge/src/")
SCRIPT = REPO / "scripts" / "select_tests.py"
SPEC = importlib.util.spec_from_file_location("select_tests", SCRIPT)
select = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(select)

LAYERED = (
    "jbus.outbox",
    "jbus.leftover",
    "jbus.queue",
    "jbus.view.state",
    "jbus.watch",
    "jbus.work",
    "jmerge.cli",
)


def within(name, package):
    return name == package or name.startswith(f"{package}.")


def back_to(start, edges):
    """A shortest chain of imports from `start` back to itself, or None where there is none.
    A chain that stays inside the subpackage of `start` is that subpackage's own business and
    counts for nothing: `jbus.view.state` gathers the view's panels (`panels.found`), each panel
    reads through its `Read`, and `jbus.view` imports both. A module at the top of a package,
    such as `jbus.outbox`, has no subpackage, so every chain back counts."""
    parts = start.split(".")
    own = ".".join(parts[:-1]) if len(parts) > 2 else None
    came = {}
    todo = [(start, own is None)]
    while todo:
        ahead = []
        for one in todo:
            for other in sorted(edges.get(one[0], ())):
                left = one[1] or not within(other, own)
                if other == start and left:
                    chain = [one]
                    while chain[-1][0] != start:
                        chain.append(came[chain[-1]])
                    return [start, *(step[0] for step in reversed(chain[:-1])), start]
                if other != start and (other, left) not in came:
                    came[other, left] = one
                    ahead.append((other, left))
        todo = ahead
    return None


def test_a_chain_back_is_found():
    edges = {
        "p.a": {"p.b"},
        "p.b": {"p.c"},
        "p.c": {"p.a", "p.d"},
        "p.s.e": {"p.s"},
        "p.s": {"p.s.e"},
        "p.s.f": {"p.b", "p.s"},
        "p.d": {"p.s.f"},
    }
    assert back_to("p.a", edges) == ["p.a", "p.b", "p.c", "p.a"]
    assert back_to("p.s.e", edges) is None
    edges["p.s"] = {"p.s.e", "p.s.f"}
    edges["p.b"] = {"p.c", "p.s.e"}
    assert back_to("p.s.e", edges) == ["p.s.e", "p.s", "p.s.f", "p.b", "p.s.e"]


@pytest.mark.parametrize("name", LAYERED)
def test_no_chain_of_imports_leads_back(name):
    chain = back_to(name, select.edges())
    assert chain is None, " -> ".join(chain)
