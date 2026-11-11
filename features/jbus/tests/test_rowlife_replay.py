"""`statechart replay` walks real lines of jbus's `transitions.jsonl` over TLC's graph of
`features/jbus/spec/RowLife.tla`, read by `RowLife.trace.py`, so a status step that no action of the
model makes fails here.

The fixture is 138 lines of jstack's own log: the rows of the four misses of the spec before
st-code-conforms (pm-scaffold-reuse and pm-film-test-in-check removed while running, st-main and
ci-flow-close-cite done after their pull request closed), po-sc-raise queued again when its thread
settled, and 20 rows that ran clean. The TLC runs skip where no Java runs TLC."""

import importlib
import json
import sys

import pytest

from jbus import queue
from test_jbus_queue import add
from testing.paths import REPO

SPEC = REPO / "features" / "jbus" / "spec"
FIXTURE = REPO / "features" / "jbus" / "tests" / "fixtures" / "rowlife-replay" / "transitions.jsonl"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))
tools = importlib.import_module("statechart.tools")
cli = importlib.import_module("statechart.cli")

pytestmark = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")


def replay(log, capsys):
    """The exit code and the lines `statechart replay` prints for the log at `log`."""
    code = cli.main(
        [
            "replay",
            str(SPEC / "RowLife.tla"),
            "--config",
            "RowLife.cfg",
            "--trace",
            "RowLife.trace.py",
            "--log",
            str(log),
        ]
    )
    return code, capsys.readouterr().out.splitlines()


def test_every_real_line_of_the_fixture_is_a_step_of_the_model(capsys):
    code, said = replay(FIXTURE, capsys)
    assert said == ["138 lines, 138 matched, 0 matched no step"]
    assert code == 0


def test_a_removal_of_a_done_row_matches_no_step(tmp_path, capsys):
    """cleanup-jv-wait-reason was removed when it was done, on 2026-10-29, before `remove`
    refused a row that is over: a final row may not leave `done` (`FinalStays`)."""
    lines = [
        {"slug": "cleanup-jv-wait-reason", "from": "queued", "to": "launched", "at": "1"},
        {"slug": "cleanup-jv-wait-reason", "from": "launched", "to": "running", "at": "2"},
        {"slug": "cleanup-jv-wait-reason", "from": "running", "to": "done", "at": "3"},
        {
            "slug": "cleanup-jv-wait-reason",
            "from": "done",
            "to": "removed",
            "at": "2026-10-29T20:47:08+00:00",
            "by": "JoshuaHayesWasHere",
        },
    ]
    log = tmp_path / "transitions.jsonl"
    log.write_text("".join(json.dumps(line) + "\n" for line in lines))
    code, said = replay(log, capsys)
    assert said[:2] == [
        "4 lines, 3 matched, 1 matched no step",
        "MISS cleanup-jv-wait-reason done -> removed 2026-10-29T20:47:08+00:00",
    ]
    assert code == 1


def test_the_go_lines_the_verbs_write_replay_as_steps_of_the_model(kitchen, capsys):
    """An approve, a hold that keeps the go, a lift and a hold each write the row's go to
    `transitions.jsonl`, and the replay reads each as the step of the model that moves it."""
    add(kitchen, "alpha")
    assert queue.hold(kitchen.state, "alpha", keep=True).startswith("held alpha")
    assert queue.lift(kitchen.state, "alpha").startswith("lifted alpha")
    assert kitchen.main("queue", "hold", "alpha")[0] == 0
    log = kitchen.state / "transitions.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(one["slug"], one["go"]) for one in lines] == [
        ("alpha", "approved"),
        ("alpha", "kept"),
        ("alpha", "approved"),
        ("alpha", "held"),
    ]
    code, said = replay(log, capsys)
    assert (code, said) == (0, ["4 lines, 4 matched, 0 matched no step"])
