"""The home tree's TLA+ spec in `features/home/spec/`: TLC checks the design, and each rule holds
in every scene while each canary, the design with one guard taken out, breaks its rule. The run
is `canaries.py`, as the spec's README gives it, and it skips where no Java runs TLC. The code
model's conditions each name a file and line, as the statechart tool checks."""

import subprocess
import sys

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "home" / "spec"
FILES = (
    SPEC / "HomeTree.tla",
    SPEC / "HomeTreeToday.tla",
    SPEC / "HomeTreeDesign.tla",
    SPEC / "HomeTreeToday.cfg",
    SPEC / "HomeTreeDesign.cfg",
    SPEC / "HomeTreeToday.map.py",
    SPEC / "canaries.py",
)
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))
sys.path.insert(0, str(SPEC))

import canaries  # noqa: E402
from statechart.lib import shared_variables, uncited_conditions  # noqa: E402
from statechart.tools import find_java  # noqa: E402


def test_every_condition_of_the_code_model_names_its_file_and_line():
    """The statechart tool lists no condition of HomeTreeToday.tla that no comment ties to code."""
    today = SPEC / "HomeTreeToday.tla"
    shared = shared_variables(today)
    assert len(shared) == 14
    assert uncited_conditions(today.read_text(), shared) == []


@pytest.mark.skipif(not find_java(), reason="no Java to run TLC")
@pytest.mark.timeout(1200)
def test_every_rule_holds_in_the_design_and_every_canary_breaks_its_rule():
    """canaries.py says each rule holds in each scene of the design, each canary breaks the rule
    on its guard, and today's code breaks the rules it breaks today."""
    assert all(path.is_file() for path in FILES)
    ran = subprocess.run(
        [sys.executable, str(SPEC / "canaries.py")], capture_output=True, text=True, cwd=REPO
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr[-4000:]
    lines = ran.stdout.splitlines()
    assert lines[-1] == "every run says what it should"
    for scene in canaries.SCENES:
        assert any(
            line.startswith(f"ok    design, scene {scene}: every rule holds") for line in lines
        )
    for guard, (rule, scene) in canaries.CANARIES.items():
        assert any(
            line.startswith(f"ok    canary {guard}, scene {scene}: {rule} breaks") for line in lines
        )
    assert {rule for rule, _ in canaries.CANARIES.values()} == set(canaries.RULES)
