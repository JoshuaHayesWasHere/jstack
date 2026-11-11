"""The green move as a TLA+ spec, `features/jbus/spec/GreenMove.tla`: with a pass that can die
between any two steps, TLC finds that the tool runs the tree the link names and the layouts follow
it once no step is owed, that no reload is owed for a tip whose move went back, that the copy never
runs a tip that does not import, and that `live` names only a tip whose units the manager took.
Each canary breaks the rule that rests on its guard: one that keeps no owed step in green.json,
goes back owing no install, moves with no import, or stamps `live` over a refusal.
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


def canary(fault: str, rule: str) -> subprocess.CompletedProcess:
    """TLC's run of the config with `Fault = fault`, checking only TypeOK and `rule`."""
    kept = (SPEC / "GreenMove.cfg").read_text().replace('Fault = "none"', f'Fault = "{fault}"')
    assert f'Fault = "{fault}"' in kept
    lines = [line for line in kept.splitlines() if not line.startswith("INVARIANT")]
    return tlc("\n".join([*lines, "INVARIANT TypeOK", f"INVARIANT {rule}", ""]))


@JAVA
@pytest.mark.parametrize("rule", ["ToolRunsCopy", "LayoutsFollow"])
def test_a_move_that_keeps_no_owed_step_breaks_the_rule(rule):
    """The canary, `Fault = "no-owed"`: green.json keeps no step, as before st-green-step, and a
    pass that dies after it pointed the link leaves the tool and the layouts behind it."""
    ran = canary("no-owed", rule)
    assert ran.returncode != 0
    assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]


@JAVA
@pytest.mark.parametrize("rule", ["ToolRunsCopy", "NoReloadForRemoved"])
def test_a_move_that_goes_back_owing_only_a_relink_breaks_the_rule(rule):
    """The canary, `Fault = "no-back"`: a move whose install fails goes back as before
    st-green-back, owing a relink and no install, with the reload it wrote for the tip it
    removed, so the tool uv removed stays gone and systemd reloads for a tip that never was."""
    ran = canary("no-back", rule)
    assert ran.returncode != 0
    assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]


@JAVA
def test_a_move_that_does_not_import_the_tip_first_breaks_the_rule():
    """The canary, `Fault = "no-import"`: `_advance` points the link at a tip whose commands do
    not import, so the copy runs a main that breaks the commands that would revert it."""
    ran = canary("no-import", "CopyImports")
    assert ran.returncode != 0
    assert "Invariant CopyImports is violated" in ran.stdout, ran.stdout[-4000:]


@JAVA
def test_a_stamp_over_a_refused_unit_breaks_the_rule():
    """The canary, `Fault = "stamp-refused"`: `_live` stamps `live` where the manager refused a
    step, so no later pass asks for the units of that tip again."""
    ran = canary("stamp-refused", "StampTrue")
    assert ran.returncode != 0
    assert "Invariant StampTrue is violated" in ran.stdout, ran.stdout[-4000:]
