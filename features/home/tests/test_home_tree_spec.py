"""The home tree's TLA+ spec in `features/home/spec/`: TLC checks the design, and each rule holds
in every scene while each canary, the design with one guard taken out, breaks its rule. Each run
of `canaries.py` is a test of its own, so the workers share them out, and those tests skip where
no Java runs TLC. The code model's conditions each name a file and line, as the statechart tool
checks."""

import importlib
import re
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

canaries = importlib.import_module("canaries")
lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")

RUNS = list(canaries.runs())


def test_every_condition_of_the_code_model_names_its_file_and_line():
    """The statechart tool lists no condition of HomeTreeToday.tla that no comment ties to code."""
    today = SPEC / "HomeTreeToday.tla"
    shared = lib.shared_variables(today)
    assert len(shared) == 14
    assert lib.uncited_conditions(today.read_text(), shared) == []


def test_the_runs_are_every_scene_of_the_design_every_canary_and_today():
    """canaries.py runs the design once in each scene, each canary once, and today's code once for
    each rule it breaks or keeps, and the canaries between them break every rule."""
    assert all(path.is_file() for path in FILES)
    labels = [label for label, *_ in RUNS]
    assert labels == [
        *(f"design, scene {scene}: every rule" for scene in canaries.SCENES),
        *(
            f"canary {guard}, scene {scene}: {rule}"
            for guard, (rule, scene) in canaries.CANARIES.items()
        ),
        *(f"today, scene {scene}: {rule}" for rule, scene in canaries.TODAY_BREAKS.items()),
        *(f"today, scene a: {rule}" for rule in canaries.TODAY_HOLDS),
    ]
    assert {rule for rule, _ in canaries.CANARIES.values()} == set(canaries.RULES)


def test_canaries_py_prints_a_line_for_each_run_and_ends_0_when_each_says_what_it_should(
    monkeypatch, capsys
):
    """The script the spec's README gives prints `ok` for each run whose verdict is the one it
    wants, then its last line, with a TLC that answers each run as it should."""
    said = {
        "holds": "Model checking completed. No error has been found.",
        "breaks": "Temporal properties were violated.",
    }
    answers = {cfg: said[want] for _, _, cfg, _, want in RUNS}
    for _, _, cfg, rule, want in RUNS:
        if want == "breaks" and rule in canaries.INVARIANTS:
            answers[cfg] = f"Error: Invariant {rule} is violated."
    monkeypatch.setattr(canaries.tools, "find_tlc", lambda: None)
    monkeypatch.setattr(canaries, "tlc", lambda found, module, cfg: answers[cfg])
    assert canaries.main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "every run says what it should"
    assert [line.split(" (")[0] for line in lines[:-1]] == [
        f"ok    {label} {want}" for label, _, _, _, want in RUNS
    ]


@pytest.fixture(scope="module")
def tlc():
    return tools.find_tlc()


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
@pytest.mark.timeout(600)
@pytest.mark.parametrize(
    ("module", "cfg", "rule", "want"),
    [run[1:] for run in RUNS],
    ids=[re.sub(r"[^\w-]+", "-", label) for label, *_ in RUNS],
)
def test_the_run_says_what_it_should(tlc, module, cfg, rule, want):
    """TLC says each rule holds in the design's scene, the canary breaks the rule on its guard,
    and today's code breaks or keeps the rule it breaks or keeps today."""
    out = canaries.tlc(tlc, module, cfg)
    assert canaries.verdict(out, rule) == want, out[-4000:]
