"""The kitchen's start of a pass's run of `jmerge` (`jbus.merge.start`): the real start, whose
process runs here, to its end, inside the pass, before the pass reads what ended, so a test reads
the lines of the run its pass started, as when the pass waited on the run. The process is the
code and argv the real start gives it, so a flag the start hands `jmerge` (`merge.handed`)
reaches the kitchen's `jmerge` only where the real start passes it on.
`test_jbus_merge_off_pass.py` runs the real start with its process of its own.

A pass runs its projects side by side, on threads, so `patch` swaps `merge`'s `subprocess` once
for the whole test, never per start: a swap per start would show one project's thread the
stand-in while another's start ran.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_kitchen.py` imports it.
"""

import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest import mock

from jbus import merge, verbs

REAL = merge.start
ONE = threading.Lock()


def run_here(child, **_):
    """Run the start's child, `python -c <code> <args>`, here, with the `sys.argv` that Python
    gives such a process: `-c`, then its args."""
    at = child.index("-c")
    with mock.patch.object(sys, "argv", ["-c", *child[at + 2 :]]):
        exec(child[at + 1], {"__name__": "__main__"})


HERE = SimpleNamespace(**{**vars(subprocess), "Popen": run_here})
"""`subprocess` as `merge` sees it in the kitchen: all of it, but a `Popen` that runs here."""


def start(run):
    """Start the run with the clock at the pass's time, so the run ends at its own moment, as a
    real run does: no two runs keep a record under one `at`. One start at a time, so each puts
    back the clock it found."""
    with ONE, mock.patch.object(verbs, "clock", lambda: run.now):
        return REAL(run)


def patch(monkeypatch):
    """Make the kitchen's start the start, over one a test's own fixture set before it."""
    monkeypatch.setattr(merge, "start", start)
    monkeypatch.setattr(merge, "subprocess", HERE)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
