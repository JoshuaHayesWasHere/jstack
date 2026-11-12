"""The one list as a TLA+ spec, `features/jbus/spec/OneList.tla`: each quote of the code it models
stands once in its file, each carrier of the ledger is a variable, and TLC finds today's code as
`OneList.cfg` says. With no outside act, every rule holds; each act alone breaks the rule its
finding names; and each canary breaks its rule. The TLC runs skip where no Java runs TLC."""

import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jbus" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

READ_SET = ("features/jbus/spec/", "features/jbus/src/jbus/", "features/home/", "features/jmerge/")
"""The spec and the code and skills its quotes cite: a change to either runs these tests."""

lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")

QUOTE = re.compile(r"([\w./-]+\.(?:py|md))\s*`([^`]+)`")
"""A cite of OneList.tla with the code it quotes, and no line number:
jbus/alert.py `LOCK = "streaks.lock"`, so a line that only moves needs no edit."""

ROWS = "A-087 A-089 B-074 B-075 B-076 B-077 B-079 B-081 B-090 C-078 C-079 C-083 C-084".split()
"""The ledger rows of machine OneList, each a carrier the spec keeps as a variable."""


def text() -> str:
    return (SPEC / "OneList.tla").read_text()


def quoted():
    """Each quote of OneList.tla: its file as cited, the quote, and each span of the file's lines
    that holds it."""
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text())
    files = subprocess.run(
        ["git", "ls-files", "features"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert not re.search(r"\.(?:py|md):\d", flat)
    for path, quote in QUOTE.findall(flat):
        (found,) = [one for one in files if one.endswith(f"/{path}")]
        lines = (REPO / found).read_text().splitlines()
        yield path, quote, lib.located(lines, quote)


def test_each_quote_of_the_spec_stands_once_in_its_file():
    """A quote the code moved off its block, changed or copied fails here, also where no Java
    runs TLC. A line shift alone changes nothing a cite says."""
    quotes = list(quoted())
    assert len(quotes) > 30
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, at in quotes if len(at) != 1]
    assert wrong == []


def test_each_carrier_of_the_ledger_is_a_variable():
    """Each ledger row of OneList names the VARIABLE that keeps its carrier, in its comment."""
    block = text().split("VARIABLES", 1)[1].split("vars ==", 1)[0]
    assert [row for row in ROWS if f"\\* {row}," not in block] == []


def tlc(world: str, fault: str, rules: list[str] | None = None, mark: str = "count") -> str:
    """TLC's output for OneList.cfg with `World`, `Fault` and `MarkBy` set, and with only `rules`
    (each an `INVARIANT <rule>` or `PROPERTY <rule>` line) where they are given, run in a copy of
    the spec's folder with one worker, as the spec's README runs it. Java's tmpdir is the run's own
    too: TLC writes Naturals.tla and the other standard modules there under fixed names, and a run
    that shares /tmp can parse one while another rewrites it."""
    cfg = (SPEC / "OneList.cfg").read_text()
    assert 'Fault = "none"' in cfg and 'MarkBy = "count"' in cfg
    cfg = re.sub(r"World = .*", f"World = {world}", cfg).replace('"none"', f'"{fault}"')
    cfg = cfg.replace('MarkBy = "count"', f'MarkBy = "{mark}"')
    if rules is not None:
        kept = [line for line in cfg.splitlines() if not line.startswith(("INVARIANT", "PROPERTY"))]
        cfg = "\n".join([*kept, "INVARIANT TypeOK", *rules, ""])
    found = tools.find_tlc()
    with tempfile.TemporaryDirectory(prefix="one-list-") as folder:
        work = Path(folder)
        (work / "tmp").mkdir()
        shutil.copy(SPEC / "OneList.tla", work)
        (work / "run.cfg").write_text(cfg)
        command = [found.java, f"-Djava.io.tmpdir={work / 'tmp'}"]
        command += ["-Xmx1g", "-cp", found.jar, "tlc2.TLC", "-workers", "1"]
        command += ["-metadir", str(work / "meta"), "-config", "run.cfg", "OneList.tla"]
        ran = subprocess.run(
            tools.in_test_slot(command), cwd=work, capture_output=True, text=True, timeout=300
        )
    return ran.stdout + ran.stderr


TODAY = '{"closes", "cuts", "by-home"}'
BROKEN = "Temporal properties were violated"


@JAVA
def test_today_s_code_breaks_read_once_as_the_cfg_says():
    """OneList.cfg as it is: TLC stops at ReadOnce, at the state count its comment keeps."""
    out = tlc(TODAY, "none")
    assert "Invariant ReadOnce is violated" in out, out[-4000:]
    assert "1083 distinct states found" in out, out[-4000:]


@JAVA
def test_with_no_outside_act_every_rule_holds():
    """No project closes, no hand cuts merge.log, and no gate is the home's: today's code holds
    each rule, so each break below is the act's and not the model's."""
    out = tlc("{}", "none")
    assert "Model checking completed. No error has been found." in out, out[-4000:]


@JAVA
@pytest.mark.parametrize(
    ("act", "rule", "said"),
    [
        ("cuts", "INVARIANT ReadOnce", "Invariant ReadOnce is violated"),
        ("by-home", "PROPERTY AnsweredLeaves", BROKEN),
        ("by-home", "PROPERTY ListIsTrue", BROKEN),
    ],
)
def test_each_outside_act_breaks_the_rule_of_its_finding(act, rule, said):
    out = tlc(f'{{"{act}"}}', "none", [rule])
    assert said in out, out[-4000:]


@JAVA
def test_a_closed_projects_alert_leaves_the_list_and_a_list_that_keeps_it_breaks_list_is_true():
    """The project closes with its jmerge alert open, or the stall alert from before, and no pass
    of it runs again: the list leaves the alert out, so ListIsTrue holds. The canary,
    `Fault = "closed-listed"`, is the code before: the list keeps the alert, which no home can
    clear, and TLC breaks the rule."""
    held = tlc('{"closes"}', "none", ["PROPERTY ListIsTrue"])
    assert "Model checking completed. No error has been found." in held, held[-4000:]
    out = tlc('{"closes"}', "closed-listed", ["PROPERTY ListIsTrue"])
    assert BROKEN in out, out[-4000:]


@JAVA
def test_a_streak_no_raiser_clears_breaks_list_is_true():
    """The canary, `Fault = "stale-streak"`: the pass leaves the stall alert from before, which
    nothing raises, so it stays on the list with no cause, in a world where today's code holds."""
    out = tlc("{}", "stale-streak", ["PROPERTY ListIsTrue"])
    assert BROKEN in out, out[-4000:]


@JAVA
def test_merge_seen_as_a_count_breaks_read_once():
    """The canary, `Fault = "mark-count"`: merge-seen marked by the last line it read holds
    ReadOnce where a hand cuts merge.log, and the same mark taken as a count, as the code keeps
    it, breaks it."""
    held = tlc('{"cuts"}', "none", ["INVARIANT ReadOnce"], mark="line")
    assert "No error has been found" in held, held[-4000:]
    out = tlc('{"cuts"}', "mark-count", ["INVARIANT ReadOnce"], mark="line")
    assert "Invariant ReadOnce is violated" in out, out[-4000:]
