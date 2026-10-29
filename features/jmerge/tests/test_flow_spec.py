"""The merge flow's TLA+ spec in `features/jmerge/spec/`: TLC checks that today's code breaks its
rules, the design holds all four, each canary, the design with one fix taken out, breaks the rule
on that fix, and each control of today's code with another gap breaks the rules it should. The
run is `flow_canaries.py`, and it skips where no Java runs TLC. The code model's conditions, and
the design's `Rejudge`, each name a file and the code it quotes."""

import bisect
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


def test_every_condition_of_the_code_model_quotes_its_file():
    today = SPEC / "FlowToday.tla"
    assert lib.uncited_conditions(today.read_text(), lib.shared_variables(today)) == []


PATH = r"(?:features|scripts|\.github)/[\w./-]+\.\w+"
QUOTE = re.compile(rf"({PATH})\s*`([^`]+)`")
"""A cite of the models: the file and the text it quotes, as `features/jmerge/src/jmerge/rows.py
`ran.over == red``, with no line number, so a line that only moves needs no edit."""
MODELS = [SPEC / "FlowToday.tla", SPEC / "FlowDesign.tla"]
MODELS += [SPEC / "canary" / f"{name}.tla" for name in flow.CANARIES]


def flat(model):
    """The model's text with each line break of a comment taken out, so a quote can wrap."""
    return re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", model.read_text())


def located(lines, quote):
    """Each span of lines, first and last from 1, that holds the quote, white space aside."""
    words, line_of = [], []
    for number, line in enumerate(lines, 1):
        for word in line.split():
            words.append(word)
            line_of.append(number)
    text, want = " ".join(words), " ".join(quote.split())
    starts = [0]
    for word in words[:-1]:
        starts.append(starts[-1] + len(word) + 1)
    found, at = [], text.find(want)
    while at >= 0:
        first = bisect.bisect_right(starts, at) - 1
        last = bisect.bisect_right(starts, at + len(want) - 1) - 1
        found.append((line_of[first], line_of[last]))
        at = text.find(want, at + 1)
    return found


def cites():
    """Each cite of the models, once: its file and quote."""
    return sorted({cite for model in MODELS for cite in QUOTE.findall(flat(model))})


def test_the_models_cite_by_quote_and_never_by_line_number():
    for model in MODELS:
        assert not re.search(rf"{PATH}:\d", flat(model)), model.name
    assert len(cites()) > 30


def test_each_quote_a_model_cites_stands_once_in_its_file():
    """Each quote stands in its file once, so the cite finds its line, and a quote the code moved
    off its block, changed or copied fails here, also where no Java runs TLC. A line shift alone
    changes nothing a cite says."""
    wrong = []
    for path, quote in cites():
        found = located((REPO / path).read_text().splitlines(), quote)
        if len(found) != 1:
            wrong.append(f"{path} `{quote}`: {len(found)} times")
    assert wrong == []


def test_a_quote_finds_its_lines_after_a_shift_and_not_once_its_block_is_split():
    lines = ["def red(main):", "    if not main.red or fix:", "        return []"]
    assert located(lines, "if not main.red or fix: return []") == [(2, 3)]
    assert located(["", "", *lines], "if not main.red or fix: return []") == [(4, 5)]
    assert located([*lines[:2], "    x = 1", lines[2]], "if not main.red or fix: return []") == []
    assert located([*lines, *lines], "def red(main):") == [(1, 1), (4, 4)]
    assert located(lines, "def blue(") == []


STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
OR = re.compile(r"\bor\b")


def disjuncts(code):
    """How many `or`s the Python text holds outside its string literals."""
    return len(OR.findall(STRING.sub("", code)))


def test_a_quote_of_one_python_line_holds_each_or_on_it():
    """A quote that stands on one line of Python names a condition, and holds every `or` that
    line holds, so a disjunct the code gains, as `rows.red` gained the proof of a fix in #583,
    fails here until the model takes it in. A quote over several lines names a block."""
    checked = []
    for path, quote in cites():
        lines = (REPO / path).read_text().splitlines()
        [(first, last)] = located(lines, quote) or [(0, -1)]
        if path.endswith(".py") and first == last:
            checked.append(quote)
            assert disjuncts(quote) == disjuncts(lines[first - 1]), f"{path} `{quote}`"
    assert "ran.over == red and bool(failed)" in checked


def test_each_condition_of_the_design_s_rejudge_quotes_its_file():
    text = (SPEC / "FlowDesign.tla").read_text()
    rejudge = text[text.index("Rejudge(p) ==") : text.index("\\* crew-leftover-procs")]
    conditions = [line for line in rejudge.splitlines() if line.lstrip().startswith("/\\ ")]
    assert len(conditions) == 7
    assert all(QUOTE.search(line) for line in conditions[:6]), conditions


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
