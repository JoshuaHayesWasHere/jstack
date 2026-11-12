"""The kitchen's start of a pass's run of `jmerge` (`jbus.merge.start`): the run goes to its end
inside the pass, before the pass reads what ended, so a test reads the lines of the run its pass
started, as when the pass waited on the run. `test_jbus_merge_off_pass.py` runs the real start.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_kitchen.py` imports it.
"""

from unittest import mock

from jbus import merge, verbs


def start(run):
    """Run `keep` with the clock at the pass's time, so the run ends at its own moment, as a
    real run does: no two runs keep a record under one `at`."""
    where = merge.runs(run)
    stamp = (where / merge.STARTED).read_text().strip()
    with mock.patch.object(verbs, "clock", lambda: run.now):
        merge.keep(where, run.project.checkout, *merge.handed(run), stamp=stamp)
    return ""


def patch(monkeypatch):
    monkeypatch.setattr(merge, "start", start)
