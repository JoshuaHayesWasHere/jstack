"""A plan entry's life and a scope's retire, as a TLA+ spec, `features/home/spec/PlanScope.tla`:
each quote of the code it models stands once in its file, each carrier of the state ledger is a
variable whose comment quotes the code that writes it, TLC finds that today's code holds
RetireWhole and FixCountedOnce and breaks the rules `PlanScope.cfg` expects broken along the
story it keeps, and each canary breaks its rule. The TLC tests skip where no Java runs TLC."""

import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "home" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

READ_SET = (
    "features/home/spec/",
    "features/home/skills/",
    "features/home/templates/",
    "features/jbus/src/jbus/",
    "features/jbriefs/src/jbriefs/",
)
"""The spec and the code its quotes cite: a change to either runs these tests."""

lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")

QUOTE = re.compile(r"([\w./-]+\.(?:py|md))\s*`([^`]+)`")
"""A cite of PlanScope.tla with the code it quotes, and no line number:
jbus/plan.py `os.replace(new, plan)`, so a line that only moves needs no edit."""

CARRIERS = {
    "A-168": "clear",
    "C-065": "stage",
    "C-066": "typed",
    "C-067": "buildsOn",
    "C-068": "done",
    "C-073": "handoff",
    "C-074": "next",
    "C-081": "ledger",
    "C-082": "lock",
    "C-095": "home",
    "C-099": "fixOf",
}
"""Each row of the state ledger whose machine is PlanScope, and the variable that carries it."""

TEXT = (SPEC / "PlanScope.tla").read_text()


def flat(text):
    return re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)


def quoted():
    """Each quote of PlanScope.tla: its file as cited, the quote, and each span of the file's
    lines that holds it."""
    files = subprocess.run(
        ["git", "ls-files", "features"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    for path, quote in QUOTE.findall(flat(TEXT)):
        found = [one for one in files if one.endswith(f"/{path}")]
        assert len(found) == 1, f"{path} names {len(found)} files: {found}"
        lines = (REPO / found[0]).read_text().splitlines()
        yield path, quote, lib.located(lines, quote)


def test_each_quote_of_the_spec_stands_once_in_its_file():
    """A quote the code changed, moved off its block or copied fails here, also where no Java
    runs TLC. A line shift alone changes nothing a cite says."""
    quotes = list(quoted())
    assert len(quotes) > 40
    assert not re.search(r"\.(?:py|md):\d", flat(TEXT))
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, at in quotes if len(at) != 1]
    assert wrong == []


def test_each_carrier_is_a_variable_whose_comment_quotes_its_code():
    """Each ledger row's carrier is a VARIABLE whose comment, the lines above it, names the row
    and quotes code by its file."""
    block = TEXT.split("VARIABLES", 1)[1].split("vars ==", 1)[0]
    missing = []
    for row, name in CARRIERS.items():
        comment = re.search(rf"((?:\s*\\\*[^\n]*\n)+)\s*{name},", block)
        said = flat(comment[1]) if comment else ""
        if row not in said or not QUOTE.search(said):
            missing.append(f"{row} {name}")
    assert missing == []


def tlc(rule, fault="none"):
    """TLC's output for PlanScope.cfg with `Fault = fault`, checking TypeOK and `rule` alone, as
    statechart from-spec checks each rule, in a copy of the spec's folder."""
    found = tools.find_tlc()
    cfg = (SPEC / "PlanScope.cfg").read_text()
    assert 'Fault = "none"' in cfg
    kept = [line for line in cfg.splitlines() if not line.startswith("INVARIANT")]
    kept = "\n".join([*kept, "INVARIANT TypeOK", f"INVARIANT {rule}", ""])
    with tempfile.TemporaryDirectory(prefix="plan-scope-") as folder:
        work = Path(folder)
        shutil.copy(SPEC / "PlanScope.tla", work)
        (work / "run.cfg").write_text(kept.replace('Fault = "none"', f'Fault = "{fault}"'))
        command = [found.java, "-XX:+UseParallelGC", "-Xmx1g", "-cp", found.jar, "tlc2.TLC"]
        command += ["-workers", tools.workers(), "-metadir", str(work / "meta")]
        ran = subprocess.run(
            tools.in_test_slot([*command, "-config", "run.cfg", "PlanScope.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=600,
        )
    return ran.returncode, ran.stdout + ran.stderr


def rules():
    cfg = (SPEC / "PlanScope.cfg").read_text()
    every = re.findall(r"^INVARIANT (\w+)", cfg, re.M)
    broken = re.findall(r"^\\\* expect: (\w+)", cfg, re.M)
    return every, broken


def test_the_cfg_expects_the_two_rules_today_s_code_breaks():
    every, broken = rules()
    assert set(broken) == {"EntryOnce", "FixCountedWhereRead"}
    assert set(broken) < set(every)
    assert {"EntryOnce", "RetireWhole", "FixCountedOnce"} <= set(every)


@JAVA
@pytest.mark.parametrize("rule", [r for r in rules()[0] if r not in rules()[1]])
def test_today_s_code_holds_the_rule(rule):
    code, out = tlc(rule)
    assert code == 0, out[-4000:]
    assert "Model checking completed. No error has been found." in out
    assert re.search(r"\d+ distinct states found", out)


def steps(out):
    return re.findall(r"^State \d+: <(\w+)", out, re.M)


@JAVA
def test_a_close_cut_short_and_run_again_puts_the_entry_twice_in_plan_done():
    """The story PlanScope.cfg keeps: plan close appends, dies before it rewrites the plan, and
    the home's close run again appends a second copy."""
    code, out = tlc("EntryOnce")
    assert code != 0
    assert "Invariant EntryOnce is violated" in out, out[-4000:]
    assert steps(out) == ["Initial", "CloseAppend", "CloseDies", "CloseAppend"]


@JAVA
def test_a_move_cut_before_its_carry_leaves_the_fix_where_its_home_does_not_read():
    code, out = tlc("FixCountedWhereRead")
    assert code != 0
    assert "Invariant FixCountedWhereRead is violated" in out, out[-4000:]
    assert steps(out) == ["Initial", "Admit", "MoveName", "MoveDies"]


@JAVA
@pytest.mark.parametrize(
    ("fault", "rule"), [("close-twice", "EntryOnce"), ("move-one-lock", "FixCountedOnce")]
)
def test_each_canary_breaks_its_rule(fault, rule):
    """`close-twice` appends again after a close cut short; `move-one-lock` takes only the lock
    of the ledger it carries to, so a fix admit counts in the other is lost."""
    code, out = tlc(rule, fault)
    assert code != 0
    assert f"Invariant {rule} is violated" in out, out[-4000:]
