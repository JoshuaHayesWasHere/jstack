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
    ".github/workflows/browser.yml:22-23": "schedule:",
    "features/jbus/src/jbus/expedite.py:323": "ready.BROWSER_RED.pattern",
    "features/jbus/src/jbus/expedite.py:434": "world.open.items()",
    "scripts/select_tests.py:884-893,597": "lone = unowned()",
    "features/crew/the-checks.md:84-89": "`jmerge` judges a red pull request again by itself",
    "features/jbus/src/jbus/dispatch.py:332-364": "no room",
    "features/jbus/src/jbus/dispatch.py:515-517": "on = world.stack_on(run, unmerged, brief)",
    "features/jbus/src/jbus/rebase.py:263": "world.open.items()",
    "features/jbus/src/jbus/stack.py:83": "world.open.items()",
    "features/jbus/src/jbus/stack.py:89-90": "world.merged.get(stacked.slug)",
    "features/jbus/src/jbus/strays.py:491": 'if not slug or ("crew", slug) in busy:',
    "features/jbus/src/jbus/strays.py:508-509,517": "burning = (taken |",
    "features/jbus/src/jbus/watch.py:1213-1240": "ran_by=queue.PASS",
    "features/jbus/src/jbus/watch.py:1221-1223": "queue.fresh(run.state, name) is not None",
    "features/jbus/src/jbus/watch.py:1286-1289": 'prefix="browser-red-"',
    "features/jbus/src/jbus/watch.py:1533,1576,1580,1583": "no briefed merge came in",
    "features/jbus/src/jbus/watch.py:1582-1583": "_file(run, slug, sha,",
    "features/jmerge/src/jmerge/rows.py:250-253": 'row.get("merge_after", [])',
    "features/jmerge/src/jmerge/cli.py:369-377": "ready.STACKED_UNMOVED.format(",
    "features/jmerge/src/jmerge/ready.py:1086-1088": "NOT_PASSED",
    "features/jmerge/src/jmerge/ready.py:398-401": "def red_only",
    "features/jmerge/src/jmerge/rows.py:139": (
        "if not main.red or mainjson.fix_of(slug) or proves(main.red, main.failed, ran):"
    ),
    "features/jmerge/src/jmerge/rows.py:132": "ran.over == red and bool(failed)",
    "features/jmerge/src/jmerge/rows.py:339-342": "if red and not proves(red, failed, ran):",
    "features/jmerge/src/jmerge/rows.py:368": (
        'if last is None or last.get("conclusion") in NOT_RED or str(last.get("id")) not in fixing:'
    ),
    "features/jmerge/src/jmerge/rows.py:383-384": 'row.get("status") not in queue.FINAL',
    "features/jmerge/src/jmerge/cli.py:1958": "if state != ready.BROWSER_FAILED:",
    "features/jmerge/src/jmerge/rejudge.py:93": 'was.get("tip")',
    "features/jmerge/src/jmerge/cli.py:742": "self.moved(one.base, one.started)",
    "features/jmerge/src/jmerge/cli.py:771": "def judge(",
    "features/jmerge/src/jmerge/cli.py:845": "or self.red(one, default, brief.stem, text)",
    "features/jmerge/src/jmerge/rejudge.py:73": "self.ask(one)",
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


STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
OR = re.compile(r"\bor\b")


def disjuncts(code):
    """How many `or`s the Python text holds outside its string literals."""
    return len(OR.findall(STRING.sub("", code)))


def test_a_cite_of_one_python_line_quotes_each_or_on_it():
    """A cite of one line of Python names a condition, and its quote holds every `or` that line
    holds, so a disjunct the code gains, as `rows.red` gained the proof of a fix in #583, fails
    here until the model takes it in. A span cites a block, and its quote names the block."""
    checked = []
    for cite, text in CITED.items():
        path, _, line = cite.rpartition(":")
        if path.endswith(".py") and line.isdigit():
            checked.append(cite)
            assert disjuncts(text) == disjuncts(lines_of(path, line)), cite
    assert "features/jmerge/src/jmerge/rows.py:139" in checked


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
    _, module, cfg, rule, want = next(run for run in flow.runs() if run[4] == "breaks")
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
