"""The kitchen's start of a pass's build of the scorecard page (`jbus.telemetry.start`): the build
goes to its end inside the pass, through the command the child runs (`jbus scorecard --out`), and
says what it printed to the log, as the child does, so a test that looks at the state after a pass
sees what a real pass leaves once its child has ended, and no child writes after it looks. A build
that is refused, as with no telemetry store, is a line in the log and not a failed pass, as it is
for the child. `test_jbus_scorecard_outlives.py` and `test_jbus_scorecard_page.py` run the real
start.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_kitchen.py` imports it.
"""

import argparse
import contextlib
import io

from jbus import telemetry


def start(config, out):
    printed = io.StringIO()
    args = argparse.Namespace(project=config.projects[0].name, store=None, out=str(out))
    with contextlib.redirect_stdout(printed):
        telemetry._scorecard(args, config)
    out.with_name(f".{telemetry.SCORECARD}.log").write_text(printed.getvalue())
    return ""


def patch(monkeypatch):
    monkeypatch.setattr(telemetry, "start", start)
