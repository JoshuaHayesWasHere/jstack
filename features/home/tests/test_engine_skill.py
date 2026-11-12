"""The engine runs one pass in the repo's root home and in no other. Its first block runs after the
home skill's block at the top and the block that finds this home, as the root's skill and the
scheduled task run it. Each test takes the block from the engine skill."""

from test_home_thread import block
from test_scope_root import homes
from test_scoped_home import ROOT, SCOPED

__all__ = ["homes"]

ROOT_CHECK = 'echo "root: run the pass"'


def first_line(homes, thread):
    """What the engine's root check prints for the home whose thread id is `thread`."""
    ran = homes.run("home", block("engine", ROOT_CHECK), homes.main, thread)
    return ran.stdout.splitlines()[0]


def test_the_root_home_runs_the_pass(homes):
    assert first_line(homes, ROOT) == "root: run the pass"


def test_a_scoped_home_refuses_in_one_line(homes):
    ran = homes.run("home", block("engine", ROOT_CHECK), homes.main, SCOPED)
    assert ran.stdout.splitlines() == [
        "not a root home: the engine runs only in a repo's root home, so this pass does nothing."
    ]


def test_a_thread_that_is_no_home_is_refused_before_the_check(homes):
    assert first_line(homes, "mcp:no-home-of-this-repo").startswith("no home: ")
