"""GitHub's API budget as a TLA+ spec, `features/jsettings/spec/GhBudget.tla`: each carrier and
condition quotes the code that writes or checks it, and the quote stands once in its file; TLC
finds that today's code, whose rotation holds a lock, keeps `NoLostGeneration` of `GhBudget.cfg`
and breaks `HeldWhenLow`, and that the canary, the unlocked rotation, breaks `NoLostGeneration`.
The TLC runs skip where no Java runs TLC."""

import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jsettings" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")

READ_SET = ("features/jsettings/src/", "features/jbus/src/")
"""The code GhBudget.tla quotes, each file as `<package>/<file>.py`."""

QUOTE = re.compile(r"([\w./-]+\.py)((?:\s*(?:,|and)?\s*`[^`]+`)+)")
"""A cite by the code it quotes, with no line number: jsettings/proc.py `if path.stat()...`.
Each quote after it joined by a comma or "and" is a quote of the same file."""


def quoted():
    """Each quote of GhBudget.tla: its file as cited, the quote, and each span of the file's lines
    that holds it."""
    text = (SPEC / "GhBudget.tla").read_text()
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)
    assert not re.search(r"\.py:\d", flat)
    for path, quotes in QUOTE.findall(flat):
        lines = (REPO / "features" / path.split("/")[0] / "src" / path).read_text().splitlines()
        for quote in re.findall(r"`([^`]+)`", quotes):
            yield path, quote, lib.located(lines, quote)


def test_each_quote_of_the_spec_stands_once_in_its_file():
    """Each quote stands in its file once, so a quote the code has changed, moved off its file or
    copied fails here, also where no Java runs TLC."""
    quotes = list(quoted())
    assert len(quotes) > 15
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, at in quotes if len(at) != 1]
    assert wrong == []


def test_each_carrier_of_the_ledger_is_a_variable_that_quotes_its_writer():
    """D-081 to D-086 each name one VARIABLE, whose comment quotes the code that writes it."""
    text = (SPEC / "GhBudget.tla").read_text()
    for row in ("D-081", "D-082", "D-083", "D-084", "D-085", "D-086"):
        block = re.search(rf"\\\* {row}, (.*?)\n  (\w+),", text, re.S)
        assert block, row
        assert re.search(r"\.py `[^`]+`", block.group(1)), row


def tlc(cfg: str) -> subprocess.CompletedProcess:
    """TLC's run of GhBudget.tla with the config `cfg`, in a copy of the spec's folder. Java's
    tmpdir is the run's own too: TLC writes Naturals.tla and the other standard modules there under
    fixed names, and a run that shares /tmp can parse one while another rewrites it."""
    found = tools.find_tlc()
    with tempfile.TemporaryDirectory(prefix="ghbudget-") as folder:
        work = Path(folder)
        (work / "tmp").mkdir()
        shutil.copy(SPEC / "GhBudget.tla", work)
        (work / "run.cfg").write_text(cfg)
        command = [found.java, f"-Djava.io.tmpdir={work / 'tmp'}"]
        command += ["-Xmx1g", "-XX:+UseParallelGC", "-cp", found.jar, "tlc2.TLC"]
        command += ["-workers", "1", "-metadir", str(work / "meta"), "-config", "run.cfg"]
        return subprocess.run(
            tools.in_test_slot([*command, "GhBudget.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=600,
        )


def only(rule: str, fault: str) -> str:
    """The spec's config with `Fault = fault`, checking only TypeOK, CappedRuns and `rule`."""
    kept = (SPEC / "GhBudget.cfg").read_text()
    assert 'Fault = "locked-rotate"' in kept
    kept = kept.replace('Fault = "locked-rotate"', f'Fault = "{fault}"')
    lines = [line for line in kept.splitlines() if not line.startswith("INVARIANT")]
    return "\n".join([*lines, "INVARIANT TypeOK", "INVARIANT CappedRuns", f"INVARIANT {rule}", ""])


@JAVA
def test_tlc_finds_that_today_s_code_starts_a_call_at_the_floor():
    """`GhBudget.cfg` is today's code, and TLC stops at its shortest broken rule: a pass reads
    the budget once and goes on calling once it is at the floor, as the cfg's comment keeps."""
    ran = tlc((SPEC / "GhBudget.cfg").read_text())
    assert ran.returncode != 0
    assert "Invariant HeldWhenLow is violated" in ran.stdout, ran.stdout[-4000:]


@JAVA
def test_the_unlocked_rotation_of_the_canary_loses_a_whole_log():
    """The canary, `Fault = "unlocked-rotate"`, the code before the lock: two processes both find
    the log past KEPT, and the second renames a new log over the full one the first kept."""
    ran = tlc(only("NoLostGeneration", "unlocked-rotate"))
    assert ran.returncode != 0
    assert "Invariant NoLostGeneration is violated" in ran.stdout, ran.stdout[-4000:]


@JAVA
def test_today_s_rotation_under_its_lock_keeps_each_whole_log():
    """`GhBudget.cfg`'s `Fault = "locked-rotate"`, today's code: one lock over the size check and
    the rename, and no rename moves a log over the last full one."""
    ran = tlc(only("NoLostGeneration", "locked-rotate"))
    assert ran.returncode == 0, ran.stdout[-4000:]
    assert "No error has been found" in ran.stdout
