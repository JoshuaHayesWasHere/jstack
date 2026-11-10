"""The merge flow's TLA+ spec in `features/jmerge/spec/`: TLC checks that today's code holds its
rules, the design holds all four, each canary, the design with one fix taken out, breaks the rule
on that fix, and each control of today's code with another gap breaks the rules it should. The
run is `flow_canaries.py`, and it skips where no Java runs TLC."""

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from testing import shard, split
from testing.paths import REPO

SPEC = REPO / "features" / "jmerge" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))
sys.path.insert(0, str(SPEC))

flow = importlib.import_module("flow_canaries")
tools = importlib.import_module("statechart.tools")
lib = importlib.import_module("statechart.lib")
find_java = tools.find_java

CITE = re.compile(r"(features/[\w./-]+\.py)\s*`([^`]+)`")
"""A cite of a flow spec: the path of the file it names and the code it quotes, with no line
number."""


def test_each_cite_of_a_flow_spec_quotes_code_its_file_holds():
    """Each backticked quote after a features/ .py path in a spec's .tla stands in the file it
    names, white space aside, so a change to the code a condition cites fails here, also where no
    Java runs TLC: six cites of FlowToday.tla went stale unseen (ci-flow-close-cite,
    ci-flow-stale-cites)."""
    cites = []
    for tla in sorted(SPEC.glob("*.tla")):
        flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", tla.read_text())
        cites += [(tla.name, path, quote) for path, quote in CITE.findall(flat)]
    assert len(cites) > 50
    missing = [
        f"{tla}: {path} `{quote}`"
        for tla, path, quote in cites
        if not lib.located((REPO / path).read_text().splitlines(), quote)
    ]
    assert not missing, "stale cites:\n" + "\n".join(missing)


@pytest.mark.skipif(not find_java(), reason="no Java to run TLC")
@pytest.mark.timeout(1800)
@pytest.mark.shard_seconds(0.23)
def test_today_and_the_design_hold_their_rules_and_each_canary_breaks_its_own():
    """About 650s on a Linux runner and 1073s on a macOS one (2026-11-05), whose speed varies by a
    fifth from run to run: the limit sits well above the slow end of that."""
    ran = subprocess.run(
        [sys.executable, str(SPEC / "flow_canaries.py")], capture_output=True, text=True, cwd=REPO
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr[-4000:]
    lines = ran.stdout.splitlines()
    assert lines[-1] == "every run says what it should"
    assert any(line.startswith("ok    design: every rule holds") for line in lines)
    for canary, rules in flow.CANARIES.items():
        for rule in rules:
            assert any(line.startswith(f"ok    canary {canary}: {rule} breaks") for line in lines)
    runs = {"today": (flow.TODAY, flow.TODAY_BREAKS), **flow.CONTROLS}
    for label, (_, breaks) in runs.items():
        for rule in flow.RULES:
            said = "breaks" if rule in breaks else "holds"
            assert any(line.startswith(f"ok    {label}: {rule} {said}") for line in lines)
    assert "FixAfterARedCheckWaitsOnlyOnYou" in flow.PROBES
    for probe in flow.PROBES:
        assert any(line.startswith(f"ok    today: {probe} holds") for line in lines)


def test_a_desk_record_writes_the_tlc_test_at_the_table_s_warm_time():
    """CI's parts restore main's TLC cache, so the TLC test takes under a second there, and a
    desk's `--shard-record` writes the seconds its `shard_seconds` pin gives in place of the
    minutes a cold desk takes. The pin is the figure the table, recorded from main's full runs,
    holds for it, so the two records agree: #1173's pin stayed at the cold 653.60 s once the
    table held the warm time."""
    test = test_today_and_the_design_hold_their_rules_and_each_canary_breaks_its_own
    (pin,) = [mark.args[0] for mark in test.pytestmark if mark.name == shard.PINNED]
    nodeid = f"features/jmerge/tests/test_flow_spec.py::{test.__name__}"
    table = split.seconds(split.read_times(split.TIMES), nodeid)
    assert pin == table, f"pin the TLC test at the table's figure: shard_seconds({table:.2f})"


def test_each_run_takes_two_workers_and_a_test_slot(tmp_path, monkeypatch):
    """A run by hand holds a test slot, and starts TLC on 2 workers and not one for each core."""
    java = tmp_path / "java"
    java.write_text('#!/bin/sh\necho "slot ${JGAUGE_TEST_SLOT:-none}: $*"\n')
    java.chmod(0o755)
    for name in ("JGAUGE_TEST_SLOT", "TLC_WORKERS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}")
    (tmp_path / "tla2tools.jar").write_bytes(b"")
    _, module, cfg, *_ = next(flow.runs())
    out = flow.tlc(tools.Tlc(jar=str(tmp_path / "tla2tools.jar"), java=str(java)), module, cfg)
    assert out.startswith("slot full: "), out
    assert " -workers 2 " in out, out


def test_the_script_by_hand_holds_one_slot_for_all_its_runs(tmp_path):
    """flow_canaries.py run by hand takes a test slot once, and each of its TLC runs is in it:
    no run waits for a slot of its own behind the suites that hold the others."""
    java = tmp_path / "java"
    java.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = -version ]; then echo \'openjdk version "21"\' >&2; exit 0; fi\n'
        'echo "$JGAUGE_TEST_SLOT $(ps -o comm= -p $PPID)" >> "$LOG"\n'
        'echo "Model checking completed. No error has been found."\n'
    )
    java.chmod(0o755)
    (tmp_path / "tla2tools.jar").write_text("")
    env = {k: v for k, v in os.environ.items() if k not in ("JGAUGE_TEST_SLOT", "TLC_WORKERS")}
    env |= {
        "JAVA": str(java),
        "TLA2TOOLS": str(tmp_path / "tla2tools.jar"),
        "LOG": str(tmp_path / "java.log"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "JGAUGE_LOCKS_DIR": str(tmp_path / "locks"),
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
    }
    ran = subprocess.run(
        [sys.executable, str(SPEC / "flow_canaries.py")], capture_output=True, text=True, env=env
    )
    assert ran.stdout.splitlines()[0].startswith("ok    design: every rule holds"), ran.stderr
    runs = (tmp_path / "java.log").read_text().splitlines()
    assert len(runs) == len(list(flow.runs()))
    assert {run.split()[0] for run in runs} == {"full"}
    assert not any("jgauge" in run for run in runs), runs


def test_a_run_whose_inputs_are_kept_starts_no_java_and_a_canary_s_change_runs_it(
    tmp_path, monkeypatch
):
    """A flow run TLC finished is kept under its inputs, so the same run starts no java, and a
    line added to a canary's spec, which each run copies, misses the cache and runs TLC again."""
    log = tmp_path / "java.log"
    java = tmp_path / "java"
    java.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = -version ]; then echo \'openjdk version "21"\' >&2; exit 0; fi\n'
        'echo "$*" >> "$LOG"\n'
        "echo 'Error: Invariant NoMergeTurnsMainRed is violated.'\nexit 13\n"
    )
    java.chmod(0o755)
    (tmp_path / "tla2tools.jar").write_bytes(b"the jar")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("JGAUGE_TEST_SLOT", "test")
    monkeypatch.setenv("LOG", str(log))
    found = tools.Tlc(jar=str(tmp_path / "tla2tools.jar"), java=str(java))
    _, module, cfg, (rule,), want = next(run for run in flow.runs() if run[4] == "breaks")
    out = flow.tlc(found, module, cfg)
    assert flow.verdict(out, rule) == want
    assert flow.tlc(found, module, cfg) == out
    assert len(log.read_text().splitlines()) == 1

    spec = tmp_path / "spec"
    (spec / "canary").mkdir(parents=True)
    for one in flow.specs():
        (spec / one.relative_to(SPEC)).write_text(one.read_text())
    canary = spec / "canary" / f"{next(iter(flow.CANARIES))}.tla"
    canary.write_text(canary.read_text() + "\\* a line\n")
    monkeypatch.setattr(flow, "HERE", spec)
    flow.tlc(found, module, cfg)
    assert len(log.read_text().splitlines()) == 2
