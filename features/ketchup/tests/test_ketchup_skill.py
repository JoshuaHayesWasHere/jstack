"""The ketchup skill's block: it prints the gates that are open, in the root home and in each
scoped one, and says so when none is."""

from skill_blocks import aged, block, home, outside, repo, run

__all__ = ["home", "outside", "repo"]


GATES = """\
## Gate 1: May the cache be dropped on deploy?
Status: open
Asked by: fix-login, thread mcp:1
Default: it is kept

## Gate 2: Which name does the flag get?
Status: answered
Default: the old one

## Gate 3: Is the old endpoint still called?
Status: open
"""


def test_ketchup_prints_the_gates_that_are_open(repo, home):
    aged(home / ".local" / "state" / "home" / "demo" / "gates.md", 0, GATES)
    root = home / ".local" / "state" / "home" / "demo" / "gates.md"
    scoped = aged(root.parent / "speed" / "gates.md", 0, GATES.replace("Gate 1", "Gate 7"))
    aged(root.parent / "tasks" / "gates.md", 0, "## Gate 9: Closed?\nStatus: answered\n")
    assert run(block("ketchup", "gates.md"), repo, home) == [
        f"## Gate 1: May the cache be dropped on deploy?, in {root}",
        f"## Gate 3: Is the old endpoint still called?, in {root}",
        f"## Gate 7: May the cache be dropped on deploy?, in {scoped}",
        f"## Gate 3: Is the old endpoint still called?, in {scoped}",
    ]


def test_ketchup_says_so_when_no_gate_is_open(repo, home, outside):
    body = block("ketchup", "gates.md")
    gates = home / ".local" / "state" / "home" / "demo" / "gates.md"
    none = f"no gates: none is open in {gates} or in a scoped home's, {gates.parent}/*/gates.md"
    assert run(body, repo, home) == [none]
    aged(gates, 0, GATES.replace("Status: open", "Status: answered"))
    assert run(body, repo, home) == [none]
    assert run(body, outside, home) == ["no gates: this is not a git repository"]
