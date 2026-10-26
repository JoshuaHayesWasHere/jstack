"""The home tree's TLA+ spec in `features/home/spec/`: TLC checks the design, and each rule holds
in every scene while each canary, the design with one guard taken out, breaks its rule. Each run
of `canaries.py` is a test of its own, so the workers share them out, and those tests skip where
no Java runs TLC. The code model's conditions each name a file and line, as the statechart tool
checks."""

import importlib
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from testing.layouts import assembled
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
PATIENCE = timedelta(hours=1)
"""How long a child with work out may be quiet before the root flags it."""


def test_every_condition_of_the_code_model_names_its_file_and_line():
    """The statechart tool lists no condition of HomeTreeToday.tla that no comment ties to code."""
    today = SPEC / "HomeTreeToday.tla"
    shared = lib.shared_variables(today)
    assert len(shared) == 14
    assert lib.uncited_conditions(today.read_text(), shared) == []


QUOTE = re.compile(r"([\w./-]+\.(?:py|md)):(\d+(?:-\d+)?)\s*`([^`]+)`")
"""A citation of HomeTreeToday.tla with the code it quotes: `jbus/children.py:184 `...``."""


def test_each_quote_of_the_code_model_is_on_the_lines_it_cites():
    """Each `file:line` the code model quotes holds the quoted text on those lines, so a quote
    the code has moved off or changed fails here, also where no Java runs TLC."""
    text = (SPEC / "HomeTreeToday.tla").read_text()
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)
    files = subprocess.run(
        ["git", "ls-files", "features"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    quotes = QUOTE.findall(flat)
    assert len(quotes) > 40
    stale = []
    for path, span, quote in quotes:
        (found,) = [one for one in files if one.endswith(f"/{path}")]
        first, _, last = span.partition("-")
        lines = (REPO / found).read_text().splitlines()[int(first) - 1 : int(last or first)]
        if " ".join(quote.split()) not in " ".join(" ".join(lines).split()):
            stale.append(f"{path}:{span} `{quote}`")
    assert stale == []


def test_the_runs_are_every_rule_in_every_scene_of_the_design_every_canary_and_today():
    """canaries.py runs the design in each scene once for its invariants and once for each
    property, each canary once, and today's code in each scene as the design, and the canaries
    between them break every rule."""
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
        *(
            f"today, scene {scene}: {name}"
            for scene in canaries.SCENES
            for name in ["every invariant", *canaries.PROPERTIES]
        ),
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


def test_a_property_runs_on_its_scene_alone_and_every_invariant_shows_nothing_else_moves():
    """Each run of a property gives TLC only the scene's children, calls and notices, and each
    run of every invariant checks on the whole model that nothing outside the scene moves, in
    each scene of the design and of today's code."""
    alone = [label for label, _, cfg, *_ in RUNS if "    Kids <- Made\n" in cfg]
    still = [label for label, _, cfg, *_ in RUNS if "INVARIANT SceneStill\n" in cfg]
    for label, _, cfg, *_ in RUNS:
        assert ("PROPERTY " in cfg) == (label in alone), label
        if label in alone:
            assert "    Calls <- Raised\n    Notices <- SceneNotices\n" in cfg, label
    assert still == [
        f"{model}, scene {scene}: every invariant"
        for model in ["design", "today"]
        for scene in canaries.SCENES
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
    and each rule holds in today's code in each scene."""
    out = canaries.tlc(tlc, module, cfg)
    assert canaries.verdict(out, rule) == want, out[-4000:]


class Retiring:
    """The kitchen's repo with its root home and the scoped home `sc`, whose plan has no open
    entry, a user's home directory that links the skills, and the real `jbus` on PATH, as the
    handoff skill runs it."""

    def __init__(self, kitchen, tmp_path):
        from test_jbus_leftover import home

        self.kitchen, self.user = kitchen, tmp_path / "user"
        (self.user / ".claude").mkdir(parents=True)
        (self.user / ".claude" / "skills").symlink_to(assembled() / "skills")
        (self.user / ".local" / "state").mkdir(parents=True)
        (self.user / ".local" / "state" / "home").symlink_to(kitchen.home.parent)
        jbus = kitchen.stub / "jbus"
        jbus.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m jbus "$@"\n')
        jbus.chmod(0o755)
        home(kitchen)
        self.child = home(kitchen, "sc")["threadId"]
        self.scope = kitchen.home / "sc"
        (self.scope / "plan.md").write_text("# the sc home: plan\n")

    def does(self, holding, thread):
        from test_home_thread import block, paths

        found = block("handoff", holding).replace("<threadId>", thread)
        return subprocess.run(
            ["sh", "-c", f"{paths('handoff')}\n{found}"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.user)},
            cwd=self.kitchen.checkout,
        )

    def retires(self):
        """You retire child a: its home writes its note and hands off. Return what the close
        prints, but its line about scheduled tasks."""
        from test_home_thread import NOTE
        from test_scoped_handoff import WHERE

        assert self.does(WHERE, self.child).returncode == 0
        (self.scope / "handoff.next.md").write_text(NOTE)
        ran = self.does('jbus forget "$M/home-id"', self.child)
        assert (ran.returncode, ran.stderr) == (0, "")
        return [line for line in ran.stdout.splitlines() if not line.startswith("not read:")]


@pytest.fixture
def retiring(kitchen, tmp_path):
    return Retiring(kitchen, tmp_path / "retiring")


def test_no_retire_with_open_a_child_with_its_crew_out_is_not_retired(retiring):
    """NoRetireWithOpen, along bug 1 of the chart. 1. The root makes child a: the scope `sc` has
    its home. 2. Child a launches a crew: a jbus pass launches the scope's approved row. 3. You
    retire child a: its home hands off with no open entry in its plan, and the scope stays open,
    with a next home, while its crew is out. Once the row is over, the same handoff closes it."""
    from test_jbus_queue import add, brief, rows
    from test_jbus_row_ends import result
    from test_scoped_handoff import CLOSED, THE_HOME

    kitchen = retiring.kitchen
    add(kitchen, "sc-crew", text=brief("sc-crew").replace("Home: mcp:a-home", "Home: sc"))
    now = datetime.now(UTC)
    assert any(line.startswith("launched sc-crew: ") for line in kitchen.poll(now))
    kitchen.poll(now)
    assert rows(kitchen)["sc-crew"]["status"] == "launched"

    said = retiring.retires()

    assert said[0] == THE_HOME
    assert any(line.startswith("kept open: ") and "sc-crew" in line for line in said), said
    assert "Scope closed:" not in (retiring.scope / "handoff.md").read_text()

    kitchen.brief("sc-crew", result())
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: sc-crew"]
    crew |= {"status": "completed", "settled": True}
    kitchen.poll(now)
    assert rows(kitchen)["sc-crew"]["status"] == "done"
    (retiring.scope / "home-id").write_text(f"{retiring.child}\n")
    again = retiring.retires()
    assert again[0] == CLOSED, again
    assert "\nScope closed: " in (retiring.scope / "handoff.md").read_text()


def test_stall_flagged_a_quiet_child_with_its_crew_out_is_flagged(kitchen):
    """StallFlagged and FirstStrike, along bug 2 of the chart. 1. The root makes child a: the
    root home and the scope `sc` each have a home thread, and the child's has written nothing
    for six hours. 2. Child a launches a crew: a pass launches the scope's approved row, and its
    crew then writes nothing more. 3. The root's check runs: once the child and its crew have
    been quiet for the child's patience, a pass nudges the child's home thread, and the user
    hears of it at once."""
    from test_jbus_kitchen import NOW
    from test_jbus_leftover import home
    from test_jbus_queue import add, brief
    from test_jbus_row_ends import sends

    root = home(kitchen)["threadId"]
    child = home(kitchen, "sc", idle=timedelta(hours=6))["threadId"]
    text = brief("sc-alpha").replace("Home: mcp:a-home", "Home: sc")
    add(kitchen, "sc-alpha", text=text)
    assert any(line.startswith("launched sc-alpha: ") for line in kitchen.poll(NOW))
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: sc-alpha"]
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.forget()
    for minutes in range(10, 60, 10):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert [one for one in sends(kitchen) if one["threadId"] in (root, child)] == []
    kitchen.poll(NOW + PATIENCE + timedelta(minutes=1))
    assert [one["threadId"] for one in sends(kitchen)] == [child]
    told = [e["line"] for e in kitchen.events() if e["loud"] == "user" and " sc" in e["line"]]
    assert len(told) == 1, kitchen.events()


@pytest.fixture
def merging(tmp_path):
    """jmerge's scene of a root home and the scoped home `flow` with a ready pull request, number
    7, while a home's id is in home-thread."""
    from test_jmerge_homes import ROOT, kitchen

    made = kitchen.__wrapped__(tmp_path)
    (made.home.state / "home-thread").write_text(f"{ROOT}\n")
    return made


def jmerge(kitchen, *flags):
    said = kitchen.home.sh(
        f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge {" ".join(flags)}'
    )
    assert (kitchen.home.code, kitchen.home.stderr) == (0, "")
    return said


@pytest.mark.parametrize(
    "home", ["mcp:the-root-home", "mcp:the-flow-home"], ids=["the root", "child a itself"]
)
def test_one_merger_no_home_merges_and_jbus_merges_child_a_s_pull_request(merging, home):
    """OneMerger, along bug 3 of the chart. 1. The root makes child a: the scope `flow` has its
    home-id. 2-4. Child a launches a crew, which opens its pull request, green and reviewed: the
    scene's number 7. 5. A home runs jmerge for it, the root or child a itself, and merges
    nothing, while an id is in home-thread. jbus's run, with no flag, merges it."""
    said = jmerge(merging, "--home", home)
    assert not any(line.startswith("merged ") for line in said), said
    assert merging.calls() == []
    said = jmerge(merging)
    assert any(line.startswith("merged 7 fl-task ") for line in said), said


def test_no_blind_merge_a_second_run_merges_nothing_while_one_is_merging(tmp_path):
    """NoBlindMerge, in the siblings' scene: two ready pull requests, one of each home. A second
    run of jmerge starts while the first is in the middle of its merge, after it read main's tip
    and before that merge lands. The second run merges nothing, so nothing lands over a tip its
    merger did not read, and the first merges both, one after the other."""
    from test_jmerge_fresh import GH
    from test_jmerge_homes import kitchen

    made = kitchen.__wrapped__(tmp_path)
    stub = made.home.stub
    second = f'PYTHONPATH="{made.source}" "{sys.executable}" -m jmerge > "$STUB/second.out" 2>&1'
    hook = f'    "pr merge")\n        if [ -e "$STUB/hook" ]; then rm "$STUB/hook"; {second}; fi\n'
    assert '    "pr merge")\n' in GH
    (stub / "gh").write_text(GH.replace('    "pr merge")\n', hook))
    (stub / "hook").write_text("")

    first = jmerge(made)

    assert not (stub / "hook").exists()
    second = (stub / "second.out").read_text().splitlines()
    assert second and not any(line.startswith("merged ") for line in second), second
    assert [line.split()[:3] for line in first] == [
        ["merged", "6", "root-task"],
        ["merged", "7", "fl-task"],
    ]
    assert [call.split()[2] for call in made.calls()] == ["6", "7"]


def test_each_run_takes_two_workers_and_a_test_slot(tmp_path, monkeypatch):
    """A run by hand holds a test slot, and starts TLC on 2 workers and not one for each core."""
    java = tmp_path / "java"
    java.write_text('#!/bin/sh\necho "slot ${JGAUGE_TEST_SLOT:-none}: $*"\n')
    java.chmod(0o755)
    for name in ("JGAUGE_TEST_SLOT", "TLC_WORKERS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}")
    _, module, cfg, *_ = RUNS[0]
    out = canaries.tlc(tools.Tlc(jar="tla2tools.jar", java=str(java)), module, cfg)
    assert out.startswith("slot full: "), out
    assert " -workers 2 " in out, out
