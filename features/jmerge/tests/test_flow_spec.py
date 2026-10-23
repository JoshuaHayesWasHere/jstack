"""The merge flow's TLA+ spec in `features/jmerge/spec/`: TLC checks that today's code breaks its
rules, the design holds all four, and each canary, the design with one fix taken out, breaks the
rule on that fix. The run is `flow_canaries.py`, and it skips where no Java runs TLC. The code
model's conditions, and the design's `Rejudge`, each name a file and line."""

import importlib
import re
import subprocess
import sys

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jmerge" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))
sys.path.insert(0, str(SPEC))

flow = importlib.import_module("flow_canaries")
lib = importlib.import_module("statechart.lib")
find_java = importlib.import_module("statechart.tools").find_java


def test_every_condition_of_the_code_model_names_its_file_and_line():
    today = SPEC / "FlowToday.tla"
    assert lib.uncited_conditions(today.read_text(), lib.shared_variables(today)) == []


def test_each_condition_of_the_design_s_rejudge_cites_a_line_of_the_code_that_checks_it():
    """Every conjunct of `Rejudge` names a file and line, and each line it names exists."""
    text = (SPEC / "FlowDesign.tla").read_text()
    rejudge = text[text.index("Rejudge(p) ==") : text.index("\\* crew-leftover-procs")]
    cited = re.findall(r"(features/\S+\.py):(\d+)(?:-(\d+))?", rejudge)
    assert len(cited) >= 7
    for path, first, last in cited:
        assert len((REPO / path).read_text().splitlines()) >= int(last or first), path
    conditions = [line for line in rejudge.splitlines() if line.lstrip().startswith("/\\ ")]
    assert all("features/" in line for line in conditions[:6]), conditions


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
    for rule in flow.TODAY_BREAKS:
        assert any(line.startswith(f"ok    today: {rule} breaks") for line in lines)
