"""The thread's TLA+ spec, `features/jbus/spec/ThreadLife.tla`: TLC finds that today's code holds
its rules with `ThreadLife.cfg`, and each canary, the code with one guard taken out, breaks the
rule that rests on it. Its quotes are checked in test_spec_quotes.py. The TLC tests skip where
no Java runs TLC."""

import importlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jbus" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

READ_SET = ("features/jbus/spec/", "features/jbus/src/jbus/")
"""The spec and the code it models: a change to either runs these tests."""

tools = importlib.import_module("statechart.tools")


def tlc(drop, rule=None):
    """TLC's output for ThreadLife.cfg with `Drop` set to `drop`, run in a copy of the spec, as the
    spec's README runs it. With `rule`, the cfg checks that property alone, so a canary breaks its
    own rule and no other. Java's tmpdir is the run's own too: TLC writes Naturals.tla and the other
    standard modules there under fixed names, and a run that shares /tmp can parse one while another
    rewrites it."""
    found = tools.find_tlc()
    cfg = (SPEC / "ThreadLife.cfg").read_text()
    assert 'Drop = "none"' in cfg
    if rule:
        assert f"PROPERTY {rule}\n" in cfg
        kept = [line for line in cfg.splitlines() if not line.startswith(("PROPERTY", "INVARIANT"))]
        cfg = "\n".join([*kept, f"PROPERTY {rule}", ""])
    with tempfile.TemporaryDirectory(prefix="thread-life-") as folder:
        work = Path(folder)
        (work / "tmp").mkdir()
        shutil.copy(SPEC / "ThreadLife.tla", work)
        (work / "ThreadLife.cfg").write_text(cfg.replace('"none"', f'"{drop}"'))
        command = [found.java, f"-Djava.io.tmpdir={work / 'tmp'}"]
        command += ["-XX:+UseParallelGC", "-cp", found.jar, "tlc2.TLC"]
        command += ["-workers", tools.workers(), "-metadir", str(work / "meta")]
        ran = subprocess.run(
            tools.in_test_slot([*command, "-config", "ThreadLife.cfg", "ThreadLife.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
        )
    return ran.returncode, ran.stdout + ran.stderr


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
def test_today_s_code_holds_every_rule():
    code, out = tlc("none")
    assert code == 0, out[-4000:]
    assert "Model checking completed. No error has been found." in out


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
@pytest.mark.parametrize(
    ("drop", "rule"),
    [("ladder", "ThreadEnds"), ("repair", "LineFollows")],
)
def test_each_canary_breaks_the_rule_that_rests_on_it(drop, rule):
    """With the home's stall ladder out, a thread jbus holds can stop where nothing archives it
    and no line tells its home. With the next pass's repair out, a pass that dies between the
    launch record and the brief's Thread: line leaves the brief naming no crew for good."""
    code, out = tlc(drop, rule)
    assert code != 0
    assert "Temporal properties were violated" in out, out[-4000:]
