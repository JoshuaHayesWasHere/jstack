"""The test slots' TLA+ spec, `features/jgauge/spec/TestSlot.tla`: each carrier of the machine
room is a VARIABLE that cites the code that writes it, each quote of code stands once in its file,
and TLC finds what the README says: today's code loses a ledger write, the mode that passes holds
every rule, and each canary, one of today's faults put back, breaks its own rule. The TLC tests
skip where no Java runs TLC."""

import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jgauge" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

READ_SET = (
    "features/jgauge/spec/",
    "features/jgauge/src/jgauge/",
    "features/jgauge/hooks/",
    "features/jbus/src/jbus/",
    "features/jroles/src/jroles/",
    "features/jsettings/src/jsettings/",
)
"""The spec and the code its quotes cite: a change to either runs these tests."""

lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")

QUOTE = re.compile(r"([\w./-]+\.(?:py|sh))\s*`([^`]+)`")
"""A cite of TestSlot.tla with the code it quotes, and no line number:
jgauge/waiters.py `HOLDS = timedelta(minutes=10)`, so a line that only moves needs no edit."""
CARRIERS = ("048", "049", "050", "054", "055", "056", "057", "058", "059", "060", "066", "067")
CARRIERS += ("070", "073", "074")
"""The st-state-ledger rows of the machine TestSlot, each a carrier the spec keeps."""


def flat(text: str) -> str:
    return re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)


def quoted():
    """Each quote of TestSlot.tla: its file as cited, the quote, and each span of the file's lines
    that holds it."""
    files = subprocess.run(
        ["git", "ls-files", "features"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    text = flat((SPEC / "TestSlot.tla").read_text())
    assert not re.search(r"\.(?:py|sh):\d", text)
    for path, quote in QUOTE.findall(text):
        (found,) = [one for one in files if one.endswith(f"/{path}")]
        yield path, quote, lib.located((REPO / found).read_text().splitlines(), quote)


def test_each_quote_of_the_spec_stands_once_in_its_file():
    """A quote the code changed, moved off its block or copied fails here, also where no Java
    runs TLC. A line shift alone changes nothing a cite says."""
    quotes = list(quoted())
    assert len(quotes) > 40
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, at in quotes if len(at) != 1]
    assert wrong == []


def test_each_carrier_is_a_variable_that_cites_its_writer():
    """Each ledger row of the machine is one VARIABLE, whose comment names the row and quotes,
    with its file, the code that writes the carrier."""
    text = (SPEC / "TestSlot.tla").read_text()
    block = text.split("VARIABLES", 1)[1].split("vars ==", 1)[0]
    rows = re.findall(r"\\\* D-(\d{3}) (.*?)\n  (\w+),", block, re.S)
    assert [row for row, _, _ in rows] == list(CARRIERS)
    uncited = [name for _, comment, name in rows if not QUOTE.search(flat(comment))]
    assert uncited == []


def tlc(
    fault: str,
    rules: list[str] | None = None,
    pid_reuse: bool = False,
    room: str = "",
    workers: str = "",
) -> tuple[int, str]:
    """TLC's output for TestSlot.cfg with `Fault` set to `fault`, in a copy of the spec's folder,
    as the README runs it. With `rules`, TLC checks TypeOK and those rules alone, with `room`,
    that room alone, and with `workers`, on that many workers. On more than one, the first
    counterexample is whichever a worker finds first, so a test that reads its steps asks for
    one. Each run has a java.io.tmpdir of its own, since TLC writes the standard modules there
    under fixed names, and a run that shares it can read one while another rewrites it."""
    found = tools.find_tlc()
    cfg = (SPEC / "TestSlot.cfg").read_text()
    assert 'Fault = "today"' in cfg and "PidReuse = FALSE" in cfg
    cfg = cfg.replace('Fault = "today"', f'Fault = "{fault}"')
    if pid_reuse:
        cfg = cfg.replace("PidReuse = FALSE", "PidReuse = TRUE")
    if room:
        cfg = re.sub(r"Rooms = \{.*\}", f'Rooms = {{"{room}"}}', cfg)
    if rules is not None:
        kept = [line for line in cfg.splitlines() if not line.startswith("INVARIANT")]
        cfg = "\n".join([*kept, *(f"INVARIANT {rule}" for rule in ["TypeOK", *rules]), ""])
    with tempfile.TemporaryDirectory(prefix="test-slot-") as folder:
        work = Path(folder)
        shutil.copy(SPEC / "TestSlot.tla", work)
        (work / "TestSlot.cfg").write_text(cfg)
        (work / "tmp").mkdir()
        command = [found.java, "-XX:+UseParallelGC", "-Xmx2g", f"-Djava.io.tmpdir={work / 'tmp'}"]
        command += ["-cp", found.jar, "tlc2.TLC", "-workers", workers or tools.workers()]
        command += ["-metadir", str(work / "meta")]
        ran = subprocess.run(
            tools.in_test_slot([*command, "-config", "TestSlot.cfg", "TestSlot.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=600,
        )
    return ran.returncode, ran.stdout + ran.stderr


JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")


@JAVA
def test_today_s_code_loses_a_ledger_write():
    """TestSlot.cfg is today's code, and TLC's first finding is the one its comment keeps: two
    writers read the ledger, and the second write drops the first one's record."""
    code, out = tlc("today", workers="1")
    assert code != 0
    assert "Invariant LedgerNoLostUpdate is violated" in out, out[-4000:]
    steps = re.findall(r"^State \d+: <(\w+)", out, re.M)
    assert steps == ["Initial", "Read", "Read", "Write", "Write"], out[-4000:]


@JAVA
def test_the_mode_that_passes_holds_every_rule():
    code, out = tlc("none")
    assert code == 0, out[-4000:]
    assert "Model checking completed. No error has been found." in out


@JAVA
@pytest.mark.parametrize(
    ("fault", "rule"),
    [
        ("spare-outside-lock", "WokenGetsSlot"),
        ("forget-unended", "EndNotLost"),
        ("orphan-command", "OneCommandPerSlot"),
        ("no-ledger-lock", "LedgerNoLostUpdate"),
    ],
)
def test_each_of_today_s_faults_breaks_its_rule(fault, rule):
    """A canary: one of today's faults, put back into the mode that passes, breaks its rule, so
    the rule does not hold by construction."""
    code, out = tlc(fault, [rule])
    assert code != 0
    assert f"Invariant {rule} is violated" in out, out[-4000:]


@JAVA
@pytest.mark.parametrize(("fault", "code"), [("today", 0), ("orphan-command", 12)])
def test_a_killed_test_slot_takes_its_command_with_it_today(fault, code):
    """Today's code holds OneCommandPerSlot where a killed `jgauge test-slot` leaves the slot
    free, and the canary that lets its command live on breaks it there. The short lane's room
    alone, since the whole of today's mode is 1.45 million states."""
    ended, out = tlc(fault, ["OneCommandPerSlot"], room="short")
    assert ended == code, out[-4000:]
    assert ("Invariant OneCommandPerSlot is violated" in out) == bool(code), out[-4000:]


@JAVA
def test_a_dead_holder_whose_pid_is_taken_reads_as_running():
    """`holders.running` asks only whether some process has the pid: once another process takes
    a dead command's pid, a reader counts the holder as running, and NoLostHolder breaks."""
    code, out = tlc("none", ["NoLostHolder"], pid_reuse=True)
    assert code != 0
    assert "Invariant NoLostHolder is violated" in out, out[-4000:]
