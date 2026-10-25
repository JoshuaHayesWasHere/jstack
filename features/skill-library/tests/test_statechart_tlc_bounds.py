"""How much of the machine TLC takes: a run starts 2 workers unless TLC_WORKERS gives another
count, and never one for each core, and a run outside a held test slot takes one of jgauge's first,
while a run inside one takes none, so it cannot wait on its own slot. `statechart from-spec`, the
home tree's canaries and the merge flow's all run TLC this way."""

import fcntl
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from statechart_support import (
    SCRIPTS,
    TOOLS,
    needs_tlc,
    node,
    statechart_tools,
    write,
    write_slow_pay,
)
from testing.paths import REPO

BIN = Path(sys.executable).parent
# Spelled in two pieces, so this file holds no TLC call of its own for the guard to find.
AUTO = "au" + "to"
ANY_CORE = re.compile(rf"""-workers["',\s]*{AUTO}\b|\bworkers\s*=\s*["']{AUTO}["']""")


@pytest.fixture
def outside_a_slot(monkeypatch, tmp_path):
    """A run as one by hand starts it: in no test slot, with jgauge on PATH, on a machine of one
    slot whose lock files are the test's own. It gives the lock of that one slot."""
    for name in ("JGAUGE_TEST_SLOT", "TLC_WORKERS"):
        monkeypatch.delenv(name, raising=False)
    locks = tmp_path / "locks"
    locks.mkdir()
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(locks))
    monkeypatch.setenv("TEST_SLOTS", "1")
    monkeypatch.setenv("PATH", f"{BIN}{os.pathsep}{os.environ['PATH']}")
    return locks / "test-slot.1.lock"


def test_no_call_in_the_repo_starts_tlc_with_a_worker_for_each_core():
    """TLC's `auto` count of workers starts one for each core of the machine, and several such
    runs at once loaded a 24-core machine to 126: no file the repo tracks passes it."""
    files = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    found = []
    for name in filter(None, files.split("\0")):
        path = REPO / name
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="ignore")
        found += [f"{name}: {m.group(0)!r}" for m in ANY_CORE.finditer(text)]
    assert found == []


def test_the_guard_finds_each_way_a_call_spells_it():
    for call in [
        f"-workers {AUTO}",
        f'"-workers",\n                "{AUTO}",',
        f'run(cfg, file, workers="{AUTO}")',
    ]:
        assert ANY_CORE.search(call), call
    assert not ANY_CORE.search('"-workers",\n    tools.workers(),')


def test_tlc_runs_on_two_workers_unless_tlc_workers_names_another_count(monkeypatch):
    monkeypatch.delenv("TLC_WORKERS", raising=False)
    assert statechart_tools.workers() == "2"
    monkeypatch.setenv("TLC_WORKERS", "3")
    assert statechart_tools.workers() == "3"
    for bad in (AUTO, "0", "-1", "two"):
        monkeypatch.setenv("TLC_WORKERS", bad)
        with pytest.raises(statechart_tools.NoTlc, match="TLC_WORKERS"):
            statechart_tools.workers()


def test_a_run_outside_a_slot_waits_for_one_and_runs_once_it_is_free(outside_a_slot):
    held = os.open(outside_a_slot, os.O_RDWR | os.O_CREAT)
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        ran = subprocess.Popen(
            statechart_tools.in_test_slot(["sh", "-c", 'echo "ran in $JGAUGE_TEST_SLOT"']),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with pytest.raises(subprocess.TimeoutExpired):
            ran.wait(timeout=1)
    finally:
        os.close(held)
    assert ran.communicate(timeout=10) == (
        "ran in full\n",
        "test-slot: waiting for one of 1 slots\n",
    )


def test_a_run_inside_a_held_slot_takes_no_second_one(outside_a_slot):
    """A suite under `jgauge test-slot` holds the one slot, and the TLC run it starts runs at
    once: were it to wait for a slot of its own, it would wait on its suite forever."""
    run = (
        "import subprocess, sys, statechart.tools as tools;"
        " sys.exit(subprocess.run(tools.in_test_slot(['echo', 'ran'])).returncode)"
    )
    suite = subprocess.run(
        ["jgauge", "test-slot", "--", sys.executable, "-c", run],
        env={**os.environ, "PYTHONPATH": str(SCRIPTS)},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert (suite.returncode, suite.stdout, suite.stderr) == (0, "ran\n", "")


def test_with_no_jgauge_a_run_takes_no_slot(outside_a_slot, monkeypatch, tmp_path):
    """Where the skill is installed alone, with no jgauge, TLC runs as it is."""
    monkeypatch.setenv("PATH", str(tmp_path))
    assert statechart_tools.in_test_slot(["java", "-version"]) == ["java", "-version"]


@needs_tlc
def test_from_spec_runs_each_rule_on_the_set_workers_in_a_test_slot(tmp_path, outside_a_slot):
    """from-spec checks each rule on TLC_WORKERS workers, and its graph and its shortest paths
    on one, and each run of TLC holds a test slot."""
    write_slow_pay(tmp_path, 0)
    write(tmp_path / "Pay.cfg", "SPECIFICATION Spec\nINVARIANT ChargedAtMostTwice\n")
    log = tmp_path / "java.log"
    java = tmp_path / "java"
    write(
        java,
        """#!/bin/sh
echo "slot ${JGAUGE_TEST_SLOT:-none}: $*" >> "$LOG"
exec "$REAL_JAVA" "$@"
""",
        0o755,
    )
    env = {"JAVA": str(java), "TLA2TOOLS": TOOLS.jar, "REAL_JAVA": TOOLS.java, "LOG": str(log)}
    r = node("statechart", ["from-spec", "Pay.tla"], tmp_path, {**env, "TLC_WORKERS": "3"})
    assert r.returncode == 0, r.stderr
    runs = log.read_text().splitlines()
    assert [re.search(r"-workers (\S+)", run)[1] for run in runs] == ["1", "3"]
    assert all(run.startswith("slot full: ") for run in runs), runs


def test_a_java_that_cannot_start_in_a_slot_is_said_as_without_one(tmp_path, outside_a_slot):
    """jgauge, holding the slot, is the one that starts Java, and from-spec still says that it
    cannot run TLC, and why."""
    write_slow_pay(tmp_path, 0)
    write(tmp_path / "Pay.cfg", "SPECIFICATION Spec\nINVARIANT ChargedAtMostTwice\n")
    write(tmp_path / "tla2tools.jar", "")
    env = {"JAVA": str(tmp_path / "no-java"), "TLA2TOOLS": str(tmp_path / "tla2tools.jar")}
    r = node("statechart", ["from-spec", "Pay.tla"], tmp_path, env)
    assert (r.returncode, r.stderr) == (2, "cannot run TLC: No such file or directory\n")
