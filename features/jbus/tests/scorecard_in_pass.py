"""The kitchen's start of a pass's build of the scorecard page (`jbus.telemetry.start`): the build
goes to its end inside the pass and says its line to the log, as the child does, so a test that
looks at the state after a pass sees what a real pass leaves once its child has ended, and no
child writes after it looks. `test_jbus_scorecard_outlives.py` and `test_jbus_scorecard_page.py`
run the real start.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_kitchen.py` imports it.
"""

from datetime import UTC, datetime

from jbus import telemetry


def start(config, out):
    project, store = config.projects[0].name, telemetry.path(config)
    said = telemetry._scorecard_page(config, project, store, out, datetime.now(UTC))
    out.with_name(f".{telemetry.SCORECARD}.log").write_text(f"{said}\n")
    return ""


def patch(monkeypatch):
    monkeypatch.setattr(telemetry, "start", start)
