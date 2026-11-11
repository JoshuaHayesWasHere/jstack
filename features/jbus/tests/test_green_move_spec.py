"""The green move as a TLA+ spec, `features/jbus/spec/GreenMove.tla`: with a pass that can die
between any two steps, TLC finds that the tool runs the tree the link names and the layouts follow
it once no step is owed, and that a canary which keeps no owed step in green.json breaks both.
The TLC runs skip where no Java runs TLC."""

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
tools = importlib.import_module("statechart.tools")
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")


def tlc(cfg: str) -> subprocess.CompletedProcess:
    """TLC's run of GreenMove.tla with the config `cfg`, in a copy of the spec's folder. A copy
    at main's last tip has no step left to take, so TLC is not asked to find deadlocks."""
    found = tools.find_tlc()
    with tempfile.TemporaryDirectory(prefix="greenmove-") as folder:
        work = Path(folder)
        shutil.copy(SPEC / "GreenMove.tla", work)
        (work / "run.cfg").write_text(cfg)
        command = [found.java, "-Xmx512m", "-cp", found.jar, "tlc2.TLC", "-workers", "1"]
        command += ["-deadlock", "-metadir", str(work / "meta"), "-config", "run.cfg"]
        return subprocess.run(
            tools.in_test_slot([*command, "GreenMove.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=300,
        )


@JAVA
def test_tlc_finds_that_the_tool_and_the_layouts_follow_the_link():
    ran = tlc((SPEC / "GreenMove.cfg").read_text())
    assert ran.returncode == 0, ran.stdout[-4000:]
    assert "No error has been found" in ran.stdout


@JAVA
@pytest.mark.parametrize("rule", ["ToolRunsCopy", "LayoutsFollow"])
def test_a_move_that_keeps_no_owed_step_breaks_the_rule(rule):
    """The canary, `Fault = "no-owed"`: green.json keeps no step, as before st-green-step, and a
    pass that dies after it pointed the link leaves the tool and the layouts behind it."""
    kept = (SPEC / "GreenMove.cfg").read_text().replace('Fault = "none"', 'Fault = "no-owed"')
    assert 'Fault = "no-owed"' in kept
    lines = [line for line in kept.splitlines() if not line.startswith("INVARIANT")]
    ran = tlc("\n".join([*lines, "INVARIANT TypeOK", f"INVARIANT {rule}", ""]))
    assert ran.returncode != 0
    assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]
