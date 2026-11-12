"""The test slots' TLA+ spec, `features/jgauge/spec/TestSlot.tla`: each carrier of the machine
room is a VARIABLE that cites the code that writes it, each quote of code stands once in its file,
and TLC finds what the README says: today's code, the mode that passes, holds every rule, and
each canary, a fault the code has closed put back, breaks its own rule. The TLC tests skip where
no Java runs TLC."""

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
    assert 'Fault = "today"' in cfg and "PidReuse = TRUE" in cfg
    cfg = cfg.replace('Fault = "today"', f'Fault = "{fault}"')
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
TLC = pytest.mark.timeout(600)
"""A TLC run comes near the 120 s bound on CI: the mode that passes took 86 s at 614,686
states, and has 694,283 now."""


def test_today_s_wake_is_counted_and_recorded_under_the_waiters_lock():
    """slotwait.wake counts the free slot and records the wake in one hold of the waiters lock,
    before its send, so today's code puts no fault back: `TodayFaults` is empty, and today's
    mode is the mode that passes, whose one TLC run holds WokenGetsSlot over the whole machine
    while the canary spare-outside-lock breaks it. A second TLC run of the same states, in
    today's name, would hold a hosted runner's cores for 100 s more and check nothing new."""
    spec = (SPEC / "TestSlot.tla").read_text()
    assert re.search(r"^TodayFaults == \{\}$", spec, re.M)
    assert 'Has(f) == Fault = f \\/ (Fault = "today" /\\ f \\in TodayFaults)' in spec


@JAVA
@TLC
def test_today_s_wake_that_a_dead_pass_recorded_is_told_on_a_later_pass():
    """jbus records the wake before its send, so a pass that dies between the two leaves a crew
    whose claim holds and that no one told. slotwait.wake sends each such wake again on each pass,
    under its key, so today's code holds WokenIsTold in the full lane's room, at every point a
    pass can die."""
    code, out = tlc("today", ["WokenIsTold"], room="full")
    assert code == 0, out[-4000:]
    assert "Model checking completed. No error has been found." in out


@JAVA
@TLC
def test_the_mode_that_passes_holds_every_rule():
    code, out = tlc("none")
    assert code == 0, out[-4000:]
    assert "Model checking completed. No error has been found." in out


@JAVA
@TLC
@pytest.mark.parametrize(
    ("fault", "rule"),
    [
        ("spare-outside-lock", "WokenGetsSlot"),
        ("forget-unended", "EndNotLost"),
        ("orphan-command", "OneCommandPerSlot"),
        ("no-ledger-lock", "LedgerNoLostUpdate"),
        ("pid-alone", "NoLostHolder"),
    ],
)
def test_each_of_today_s_faults_breaks_its_rule(fault, rule):
    """A canary: one of today's faults, or one the code has closed, put back into the mode that
    passes, breaks its rule, so the rule does not hold by construction. `pid-alone` is
    `holders.running` as it was, asking only whether some process has the pid: once another
    process takes a dead command's pid, a reader counts the holder as running."""
    code, out = tlc(fault, [rule])
    assert code != 0
    assert f"Invariant {rule} is violated" in out, out[-4000:]


@JAVA
@TLC
@pytest.mark.parametrize(("fault", "code"), [("today", 0), ("orphan-command", 12)])
def test_a_killed_test_slot_takes_its_command_with_it_today(fault, code):
    """Today's code holds OneCommandPerSlot where a killed `jgauge test-slot` leaves the slot
    free, and the canary that lets its command live on breaks it there. The short lane's room
    alone, since the whole of today's mode is 694,283 states."""
    ended, out = tlc(fault, ["OneCommandPerSlot"], room="short")
    assert ended == code, out[-4000:]
    assert ("Invariant OneCommandPerSlot is violated" in out) == bool(code), out[-4000:]


@JAVA
@TLC
@pytest.mark.parametrize(("fault", "code"), [("today", 0), ("forget-unended", 12)])
def test_a_run_s_end_is_kept_for_jbus_to_tell_today(fault, code):
    """Today's code forgets a run with no end only once its `jgauge test-slot` is gone too, so
    the end it writes is on file for jbus to tell its thread, and the canary that forgets the run
    while its test-slot lives breaks EndNotLost. The short lane's room alone, which has both."""
    ended, out = tlc(fault, ["EndNotLost"], room="short")
    assert ended == code, out[-4000:]
    assert ("Invariant EndNotLost is violated" in out) == bool(code), out[-4000:]


@JAVA
@TLC
@pytest.mark.parametrize(("fault", "code"), [("today", 0), ("no-ledger-lock", 12)])
def test_each_ledger_writer_s_record_is_kept_today(fault, code):
    """Today's ledger writers each hold <ledger>.lock from their read to their rename, so no
    write drops another's record, and the canary that reads and renames with no lock breaks
    LedgerNoLostUpdate. The ledger's room alone, which has every writer."""
    ended, out = tlc(fault, ["LedgerNoLostUpdate"], room="ledger")
    assert ended == code, out[-4000:]
    assert ("Invariant LedgerNoLostUpdate is violated" in out) == bool(code), out[-4000:]
