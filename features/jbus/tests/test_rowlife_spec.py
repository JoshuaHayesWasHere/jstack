"""The row's life as a TLA+ spec, `features/jbus/spec/RowLife.tla`: each status edge of TLC's
graph of it is a move of `queue.MOVES`, and the table has no other, and TLC finds that a row that
merged or is done never leaves, as the facts `work.status` reads change and `queue.derive` keeps a
final status (`work.kept`). The TLC runs skip where no Java runs TLC."""

import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from jbus import queue, work
from testing.paths import REPO

SPEC = REPO / "features" / "jbus" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))
tools = importlib.import_module("statechart.tools")

replay = importlib.import_module("statechart.replay")


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
def test_queue_moves_are_the_status_edges_of_the_spec_graph():
    """Each move one step of the spec makes is a move of `queue.MOVES`, and the table has no
    other, so a move the model gains or drops, or one the code's table gains, fails here until the
    other side takes it in."""
    graph = replay.dump_graph(str(SPEC / "RowLife.tla"), str(SPEC / "RowLife.cfg"), ())
    assert graph.moves("status") == set(queue.MOVES)


def test_the_spec_has_each_status_of_the_queue():
    """The spec's statuses are `queue.STATUSES` and the `removed` line of `remove`."""
    text = (SPEC / "RowLife.tla").read_text()
    (listed,) = re.findall(r"^Statuses ==\s*\{([^}]*)\}", text, re.M)
    assert set(re.findall(r'"(\w+)"', listed)) == {*queue.STATUSES, "removed"}


JOINED = {
    **dict.fromkeys(
        ("result", "review", "findings", "second", "stacked", "rebase", "hold"), "check"
    ),
    "quiet": "working",
}
"""The values of work.json's line the spec joins, each to the value that stands for it, as the
comment over its `Values` says: the steps of an open pull request, and a quiet thread at work."""


def test_the_spec_has_each_value_of_work_json_or_names_its_join():
    """The spec's `Values` are `work.VALUES` less the joined ones, so a value the code gains fails
    here until the spec takes it in or names its join."""
    text = (SPEC / "RowLife.tla").read_text()
    (listed,) = re.findall(r"^Values ==\s*\{([^}]*)\}", text, re.M)
    spec = set(re.findall(r'"(\w+)"', listed))
    assert spec == set(work.VALUES) - set(JOINED)
    assert set(JOINED.values()) <= spec


def tlc(cfg: str) -> subprocess.CompletedProcess:
    """TLC's run of RowLife.tla with the config `cfg`, in a copy of the spec's folder. Java's tmpdir
    is the run's own too: TLC writes Naturals.tla and the other standard modules there under fixed
    names, and a run that shares /tmp can parse one while another rewrites it."""
    found = tools.find_tlc()
    with tempfile.TemporaryDirectory(prefix="rowlife-") as folder:
        work = Path(folder)
        (work / "tmp").mkdir()
        shutil.copy(SPEC / "RowLife.tla", work)
        (work / "run.cfg").write_text(cfg)
        command = [found.java, f"-Djava.io.tmpdir={work / 'tmp'}"]
        command += ["-Xmx512m", "-cp", found.jar, "tlc2.TLC", "-workers", "1"]
        command += ["-metadir", str(work / "meta"), "-config", "run.cfg", "RowLife.tla"]
        return subprocess.run(
            tools.in_test_slot(command), cwd=work, capture_output=True, text=True, timeout=300
        )


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
def test_tlc_finds_that_merged_and_done_never_leave():
    """TLC checks the spec's own config, and every rule in it holds."""
    ran = tlc((SPEC / "RowLife.cfg").read_text())
    assert ran.returncode == 0, ran.stdout[-4000:]
    assert "No error has been found" in ran.stdout


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
def test_a_derive_that_writes_over_a_final_status_breaks_the_rule():
    """The canary: the spec with `work.kept` taken out of derive (`Fault = "no-latch"`) breaks
    `FinalStays`, so the facts can leave a final row, and the rule holds by the code's latch."""
    cfg = (SPEC / "RowLife.cfg").read_text().replace('Fault = "none"', 'Fault = "no-latch"')
    assert 'Fault = "no-latch"' in cfg
    ran = tlc(cfg)
    assert ran.returncode != 0
    assert "FinalStays is violated" in ran.stdout, ran.stdout[-4000:]


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
def test_a_settled_thread_that_queues_its_row_again_makes_a_move_the_table_lacks(tmp_path):
    """The canary: the spec with a settled thread's row `queued` again (`Fault = "settled-queued"`),
    as `work._THREAD` had it, has status edges `queue.MOVES` lacks, so the table matches the graph
    by `work.status` giving that row `stale`."""
    cfg = (SPEC / "RowLife.cfg").read_text().replace('Fault = "none"', 'Fault = "settled-queued"')
    assert 'Fault = "settled-queued"' in cfg
    (tmp_path / "RowLife.cfg").write_text(cfg)
    graph = replay.dump_graph(str(SPEC / "RowLife.tla"), str(tmp_path / "RowLife.cfg"), ())
    assert ("running", "queued") in graph.moves("status") - set(queue.MOVES)
