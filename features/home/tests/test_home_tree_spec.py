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


def test_the_runs_are_every_rule_in_every_scene_of_the_design_every_canary_and_today():
    """canaries.py runs the design in each scene once for its invariants and once for each
    property, each canary once, and today's code once for each rule it breaks or keeps, and the
    canaries between them break every rule."""
    assert all(path.is_file() for path in FILES)
    labels = [label for label, *_ in RUNS]
    assert labels == [
        *(
            f"design, scene {scene}: {name}"
            for scene in canaries.SCENES
            for name in ["every invariant", *canaries.PROPERTIES]
        ),
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


@pytest.fixture
def handing_off(tmp_path):
    from test_scoped_handoff import HandingOff

    return HandingOff(tmp_path)


def test_bug_1_a_child_retires_with_its_crew_out(handing_off):
    """NoRetireWithOpen. 1. The root makes child a: the scene starts with the scope `second` and
    its home. 2. Child a launches a crew: the scope's brief carries the crew's `Thread:` line, as
    jbus's launch writes it, and no Result. 3. You retire child a: its home hands off with no
    open entry in its plan, and the handoff closes the scope with the crew still out."""
    from test_scoped_handoff import CLOSED
    from test_scoped_home import SCOPE, SCOPED

    brief = handing_off.sent("tasks", "sc-crew", f"Home: {SCOPE}", "Thread: mcp:the-crew")
    (handing_off.scope_dir / "plan.md").write_text("# the second home: plan\n")
    _, said = handing_off.hands_off(SCOPED, handing_off.scope_dir)
    assert said[0] == CLOSED
    assert "\nScope closed: " in (handing_off.scope_dir / "handoff.md").read_text()
    left = brief.read_text()
    assert "Thread: mcp:the-crew" in left and "## Result" not in left


def test_bug_2_a_quiet_child_with_a_crew_out_is_flagged_to_nobody(kitchen):
    """StallFlagged. 1. The root makes child a: the root home and the scope `sc` each have a
    home thread, and the child's has written nothing for six hours. 2. Child a launches a crew: a
    pass launches the scope's approved row. 3. The root's check runs: an hour of passes, and none
    sends the root, the child or the user a word about the quiet child."""
    from datetime import timedelta

    from test_jbus_kitchen import NOW
    from test_jbus_leftover import home
    from test_jbus_queue import add, brief, rows
    from test_jbus_row_ends import sends

    root = home(kitchen)["threadId"]
    child = home(kitchen, "sc", idle=timedelta(hours=6))["threadId"]
    text = brief("sc-alpha").replace("Home: mcp:a-home", "Home: sc")
    add(kitchen, "sc-alpha", text=text)
    launched = kitchen.poll(NOW - timedelta(minutes=90))
    assert any(line.startswith("launched sc-alpha: ") for line in launched)
    kitchen.forget()
    for minutes in range(0, 70, 10):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert rows(kitchen)["sc-alpha"]["status"] == "launched"
    assert [one for one in sends(kitchen) if one["threadId"] in (root, child)] == []
    assert kitchen.waiting() == []
    assert not any("sc" in line.split(":")[0] for line in kitchen.lines() if "stall" in line)


@pytest.fixture
def merging(tmp_path):
    """jmerge's scene of a root home and the scoped home `flow` with a ready pull request, number
    7, while a home merges: the root's id is in home-thread."""
    from test_jmerge_homes import ROOT, kitchen

    made = kitchen.__wrapped__(tmp_path)
    (made.home.state / "home-thread").write_text(f"{ROOT}\n")
    return made


@pytest.mark.parametrize(
    "runs", ["--all", "--home mcp:the-flow-home"], ids=["the root, with --all", "child a itself"]
)
def test_bug_3_a_home_merges_child_a_s_pull_request(merging, runs):
    """OneMerger. 1. The root makes child a: the scope `flow` has its home-id. 2-4. Child a
    launches a crew, which opens its pull request, green and reviewed: the scene's number 7. 5.
    The root reads main to merge child a's pull request, with `--all` as the merge skill's sweep
    runs it, or child a runs jmerge for its own: either way a home, not jbus, merges it."""
    said = merging.home.sh(f'PYTHONPATH="{merging.source}" "{sys.executable}" -m jmerge {runs}')
    assert merging.home.code == 0
    assert any(line.startswith("merged 7 fl-task ") for line in said)
