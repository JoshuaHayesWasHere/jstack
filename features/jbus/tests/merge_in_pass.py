"""The kitchen's start of a pass's run of `jmerge` (`jbus.merge.start`): the run goes to its end
inside the pass, before the pass reads what ended, so a test reads the lines of the run its pass
started, as when the pass waited on the run. `test_jbus_merge_off_pass.py` runs the real start.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_kitchen.py` imports it.
"""

from jbus import merge


def start(run):
    merge.keep(merge.runs(run), run.project.checkout, *merge.handed(run))
    return ""


def patch(monkeypatch):
    monkeypatch.setattr(merge, "start", start)
