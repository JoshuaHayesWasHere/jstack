"""The thread's TLA+ spec, `features/jbus/spec/ThreadLife.tla`: each quote of the code it models
stands once in its file, TLC finds that today's code holds its rules with `ThreadLife.cfg`, and
the canary, the code with the home's stall ladder taken out, breaks `ThreadEnds`. The TLC tests
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

SPEC = REPO / "features" / "jbus" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

READ_SET = ("features/jbus/spec/", "features/jbus/src/jbus/")
"""The spec and the code its quotes cite: a change to either runs these tests."""

lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")

QUOTE = re.compile(r"([\w./-]+\.(?:py|md))\s*`([^`]+)`")
"""A cite of ThreadLife.tla with the code it quotes, and no line number:
jbus/threads.py `CARRY_ONS = 2`, so a line that only moves needs no edit."""
STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
OR = re.compile(r"\bor\b")


def quoted():
    """Each quote of ThreadLife.tla: its file as cited, the quote, the file's lines, and each
    span of them that holds the quote."""
    text = (SPEC / "ThreadLife.tla").read_text()
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)
    files = subprocess.run(
        ["git", "ls-files", "features/jbus/src/jbus"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert not re.search(r"\.(?:py|md):\d", flat)
    for path, quote in QUOTE.findall(flat):
        (found,) = [one for one in files if one.endswith(f"/{path}")]
        lines = (REPO / found).read_text().splitlines()
        yield path, quote, lines, lib.located(lines, quote)


def test_each_quote_of_the_thread_spec_stands_once_in_its_file():
    """A quote the code moved off its block, changed or copied fails here, also where no Java
    runs TLC. A line shift alone changes nothing a cite says."""
    quotes = list(quoted())
    assert len(quotes) > 30
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, _, at in quotes if len(at) != 1]
    assert wrong == []


def test_a_quote_of_one_python_line_holds_each_or_on_it():
    """A quote that stands on one line of Python holds every `or` of that line, so a disjunct the
    code gains fails here until the spec takes it in."""

    def disjuncts(code):
        return len(OR.findall(STRING.sub("", code)))

    short = [
        f"{path} `{quote}`"
        for path, quote, lines, at in quoted()
        if path.endswith(".py")
        and len(at) == 1
        and at[0][0] == at[0][1]
        and disjuncts(quote) != disjuncts(lines[at[0][0] - 1])
    ]
    assert short == []


def tlc(drop):
    """TLC's output for ThreadLife.cfg with `Drop` set to `drop`, run in a copy of the spec, as
    the spec's README runs it."""
    found = tools.find_tlc()
    cfg = (SPEC / "ThreadLife.cfg").read_text()
    assert 'Drop = "none"' in cfg
    with tempfile.TemporaryDirectory(prefix="thread-life-") as folder:
        work = Path(folder)
        shutil.copy(SPEC / "ThreadLife.tla", work)
        (work / "ThreadLife.cfg").write_text(cfg.replace('"none"', f'"{drop}"'))
        command = [found.java, "-XX:+UseParallelGC", "-cp", found.jar, "tlc2.TLC"]
        command += ["-workers", tools.workers(), "-metadir", str(work / "meta")]
        ran = subprocess.run(
            tools.in_test_slot([*command, "-config", "ThreadLife.cfg", "ThreadLife.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
        )
    return ran.returncode, ran.stdout + ran.stderr


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
def test_today_s_code_holds_every_rule():
    code, out = tlc("none")
    assert code == 0, out[-4000:]
    assert "Model checking completed. No error has been found." in out


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
def test_without_the_stall_ladder_a_thread_ends_with_no_one_told():
    """With the home's stall ladder out, a thread jbus holds can stop where nothing archives it
    and no line tells its home: ThreadEnds breaks, so it does not hold by construction."""
    code, out = tlc("ladder")
    assert code != 0
    assert "Temporal properties were violated" in out, out[-4000:]
