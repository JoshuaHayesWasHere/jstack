"""A pytest run has test slots of its own (`jgauge_locks_of_the_run` in testing/jstack_fixtures.py),
and a TLC run a test starts outside a slot still takes one of the machine's: `in_test_slot` names
the machine's lock files for its `jgauge test-slot`, which no test's guard then refuses."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

from testing.paths import REPO

sys.path.insert(0, str(REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"))
tools = importlib.import_module("statechart.tools")

BIN = Path(sys.executable).parent


def test_a_tlc_run_a_test_starts_outside_a_slot_takes_the_machine_s_slot(tmp_path, monkeypatch):
    machine = tmp_path / "machine" / "locks"
    machine.mkdir(parents=True)
    monkeypatch.delenv("JGAUGE_TEST_SLOT", raising=False)
    monkeypatch.setenv("JGAUGE_MACHINE_LOCKS_DIR", str(machine))
    monkeypatch.setenv("TEST_SLOTS", "1")
    monkeypatch.setenv("PATH", f"{BIN}{os.pathsep}{os.environ['PATH']}")
    run = Path(os.environ["JGAUGE_LOCKS_DIR"])
    assert run == Path(os.environ["JGAUGE_RUN_LOCKS_DIR"])
    ran = subprocess.run(
        tools.in_test_slot(["sh", "-c", 'echo "$JGAUGE_TEST_SLOT $JGAUGE_LOCKS_DIR"']),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, f"full {machine}\n", "")
    assert (machine / "test-slot.1.lock").exists()


def test_a_test_with_lock_files_of_its_own_keeps_them_for_a_tlc_run(tmp_path, monkeypatch):
    monkeypatch.delenv("JGAUGE_TEST_SLOT", raising=False)
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", f"{BIN}{os.pathsep}{os.environ['PATH']}")
    held = tools.in_test_slot(["java", "-version"])
    assert held == [str(BIN / "jgauge"), "test-slot", "--", "java", "-version"]
