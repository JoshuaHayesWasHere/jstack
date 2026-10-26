"""The merge flow's TLA+ spec in `features/jmerge/spec/`: TLC checks that today's code breaks its
rules, the design holds all four, each canary, the design with one fix taken out, breaks the rule
on that fix, and each control of today's code with another gap breaks the rules it should. The
run is `flow_canaries.py`, and it skips where no Java runs TLC. The code model's conditions, and
the design's `Rejudge`, each name a file and line."""

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jmerge" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))
sys.path.insert(0, str(SPEC))

flow = importlib.import_module("flow_canaries")
lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")
find_java = tools.find_java


def test_every_condition_of_the_code_model_names_its_file_and_line():
    today = SPEC / "FlowToday.tla"
    assert lib.uncited_conditions(today.read_text(), lib.shared_variables(today)) == []


CITE = re.compile(r"((?:features|scripts|\.github)/[\w./-]+):(\d+(?:-\d+)?(?:,\d+)*)")

CITED = {
    ".github/workflows/check.yml:4": "pull_request:",
    "scripts/select_tests.py:666-675,385": "lone = unowned()",
    "features/crew/the-checks.md:79-84": "`jmerge` judges a red pull request again by itself",
    "features/jbus/src/jbus/dispatch.py:324-356": "no room",
    "features/jbus/src/jbus/dispatch.py:459-461": "on = world.stack_on(unmerged)",
    "features/jbus/src/jbus/rebase.py:250": "world.open.items()",
    "features/jbus/src/jbus/stack.py:65": "world.open.items()",
    "features/jbus/src/jbus/stack.py:72-73": "world.merged.get(stacked.slug)",
    "features/jbus/src/jbus/strays.py:356": '("crew", slug) in busy',
    "features/jbus/src/jbus/strays.py:373-374,382": "burning = (taken |",
    "features/jbus/src/jbus/watch.py:1034-1054": "queue.add(run.state, name, top, [], text)",
    "features/jbus/src/jbus/watch.py:1330,1373,1377,1380": "no briefed merge came in",
    "features/jbus/src/jbus/watch.py:1379-1380": "_file(run, slug, sha,",
    "features/jmerge/src/jmerge/rows.py:135-138": 'row.get("merge_after", [])',
    "features/jmerge/src/jmerge/cli.py:664-672": "ready.STACKED_UNMOVED.format(",
    "features/jmerge/src/jmerge/ready.py:935-936": "NOT_PASSED",
    "features/jmerge/src/jmerge/ready.py:294-297": "def red_only",
    "features/jmerge/src/jmerge/rows.py:87": "if not main.red",
    "features/jmerge/src/jmerge/cli.py:219": 'was.get("result")',
    "features/jmerge/src/jmerge/cli.py:1038-1039": "self.moved(one.base, one.started)",
    "features/jmerge/src/jmerge/cli.py:1043": "self.fresh.command",
    "features/jmerge/src/jmerge/cli.py:1044-1046": "self.fresh.of(",
    "features/jmerge/src/jmerge/cli.py:1082": "def judge(",
    "features/jmerge/src/jmerge/cli.py:1155": "self.red(one, default",
    "features/jmerge/src/jmerge/rejudge.py:63": "self.ask(one)",
}


def lines_of(path, spans):
    text = (REPO / path).read_text().splitlines()
    found = []
    for span in spans.split(","):
        first, _, last = span.partition("-")
        found += text[int(first) - 1 : int(last or first)]
    return "\n".join(found)


def test_each_line_a_model_cites_holds_the_condition_it_names():
    """Every cite in the models is in `CITED`, and its lines hold the text pinned there, so a cite
    that drifts off its condition fails here, also where no Java runs TLC."""
    models = [SPEC / "FlowToday.tla", SPEC / "FlowDesign.tla"]
    models += [SPEC / "canary" / f"{name}.tla" for name in flow.CANARIES]
    cites = {
        f"{path}:{spans}" for model in models for path, spans in CITE.findall(model.read_text())
    }
    assert cites == set(CITED)
    for cite, text in CITED.items():
        path, _, spans = cite.rpartition(":")
        assert text in lines_of(path, spans), cite


def test_each_condition_of_the_design_s_rejudge_names_a_file_and_line():
    text = (SPEC / "FlowDesign.tla").read_text()
    rejudge = text[text.index("Rejudge(p) ==") : text.index("\\* crew-leftover-procs")]
    conditions = [line for line in rejudge.splitlines() if line.lstrip().startswith("/\\ ")]
    assert len(conditions) == 7
    assert all(CITE.search(line) for line in conditions[:6]), conditions


@pytest.mark.skipif(not find_java(), reason="no Java to run TLC")
@pytest.mark.timeout(600)
def test_today_breaks_its_rules_the_design_holds_them_and_each_canary_breaks_its_own():
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


def test_each_run_takes_two_workers_and_a_test_slot(tmp_path, monkeypatch):
    """A run by hand holds a test slot, and starts TLC on 2 workers and not one for each core."""
    java = tmp_path / "java"
    java.write_text('#!/bin/sh\necho "slot ${JGAUGE_TEST_SLOT:-none}: $*"\n')
    java.chmod(0o755)
    for name in ("JGAUGE_TEST_SLOT", "TLC_WORKERS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}")
    _, module, cfg, *_ = next(flow.runs())
    out = flow.tlc(tools.Tlc(jar="tla2tools.jar", java=str(java)), module, cfg)
    assert out.startswith("slot full: "), out
    assert " -workers 2 " in out, out


def test_the_script_by_hand_holds_one_slot_for_all_its_runs(tmp_path):
    """flow_canaries.py run by hand takes a test slot once, and each of its TLC runs is in it:
    no run waits for a slot of its own behind the suites that hold the others."""
    java = tmp_path / "java"
    java.write_text(
        '#!/bin/sh\necho "$JGAUGE_TEST_SLOT $(ps -o comm= -p $PPID)" >> "$LOG"\n'
        'echo "Model checking completed. No error has been found."\n'
    )
    java.chmod(0o755)
    (tmp_path / "tla2tools.jar").write_text("")
    env = {k: v for k, v in os.environ.items() if k not in ("JGAUGE_TEST_SLOT", "TLC_WORKERS")}
    env |= {
        "JAVA": str(java),
        "TLA2TOOLS": str(tmp_path / "tla2tools.jar"),
        "LOG": str(tmp_path / "java.log"),
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
