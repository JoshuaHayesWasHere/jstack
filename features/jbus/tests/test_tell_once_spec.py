"""jbus's act-once steps as a TLA+ spec, `features/jbus/spec/TellOnce.tla`: each quote of the code
it models stands once in its file, TLC finds today's code breaks NoTellTwice or NoTellLost on the
six acts `TellOnce.cfg` names and holds them on the other seven, and each canary, a pass that
writes its marks first or reads none, breaks its rule on every act. The TLC tests skip where no
Java runs TLC."""

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
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")

QUOTE = re.compile(r"([\w./-]+\.(?:py|md))\s*`([^`]+)`")
"""A cite of TellOnce.tla with the code it quotes, and no line number:
jbus/clock.py `wait |= {"acted": True, "passes": 0}`, so a line that only moves needs no edit."""

ACTS = {
    "clock", "held", "blocking", "items", "word", "owed", "expedite",
    "cancelled", "closed", "account", "revert", "twice", "reload",
}  # fmt: skip
TODAY = {
    ("twice", "NoTellLost"),
    ("clock", "NoTellLost"),
    ("owed", "NoTellTwice"),
    ("blocking", "NoTellTwice"),
    ("word", "NoTellTwice"),
    ("account", "NoTellTwice"),
}
"""What TLC finds in today's code, as the comment of TellOnce.cfg keeps it: the act, the rule."""


def flat() -> str:
    """TellOnce.tla on one line, its comment marks gone, so a quote may run over a line break."""
    return re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", (SPEC / "TellOnce.tla").read_text())


def quoted():
    """Each quote of TellOnce.tla: its file as cited, the quote, and each span of the file's lines
    that holds it."""
    files = subprocess.run(
        ["git", "ls-files", "features/jbus/src/jbus"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for path, quote in QUOTE.findall(flat()):
        (found,) = [one for one in files if one.endswith(f"/{path}")]
        yield path, quote, lib.located((REPO / found).read_text().splitlines(), quote)


def test_each_quote_of_the_spec_stands_once_in_its_file():
    """A quote the code moved off its block, changed or copied fails here, also where no Java runs
    TLC. A line shift alone changes nothing a cite says."""
    quotes = list(quoted())
    assert len(quotes) > 50
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, at in quotes if len(at) != 1]
    assert wrong == []


def test_every_backticked_span_cites_a_file_and_no_line():
    """Each span in backticks is a quote with its file, so the test above checks every one, and no
    cite carries a line number that a move of the lines would leave wrong."""
    text = flat()
    assert len(re.findall(r"`[^`]+`", text)) == len(QUOTE.findall(text))
    assert not re.search(r"\.(?:py|md):\d", text)


def test_each_carrier_of_the_ledger_is_a_variable():
    """The 21 rows of machine TellOnce in the st-state-ledger each name one variable."""
    text = (SPEC / "TellOnce.tla").read_text()
    rows = re.findall(r"\\\* ([AB]-\d{3}) ", text)
    assert sorted(rows) == sorted(
        "A-092 A-093 A-094 A-095 A-105 A-107 A-108 A-112 A-113 A-114 A-118 A-121 A-122 A-139 "
        "A-149 A-162 B-012 B-024 B-039 B-057 B-058".split()
    )


def tlc(fault: str) -> str:
    """TLC's output for TellOnce.cfg with `Fault = fault`, run on past each broken rule
    (`-continue`) in a copy of the spec's folder, as the spec's README runs it."""
    found = tools.find_tlc()
    cfg = (SPEC / "TellOnce.cfg").read_text()
    assert 'Fault = "none"' in cfg
    with tempfile.TemporaryDirectory(prefix="tell-once-") as folder:
        work = Path(folder)
        shutil.copy(SPEC / "TellOnce.tla", work)
        (work / "TellOnce.cfg").write_text(cfg.replace('Fault = "none"', f'Fault = "{fault}"'))
        command = [found.java, "-Xmx512m", "-cp", found.jar, "tlc2.TLC", "-workers", "1"]
        command += ["-continue", "-metadir", str(work / "meta"), "-config", "TellOnce.cfg"]
        ran = subprocess.run(
            tools.in_test_slot([*command, "TellOnce.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=300,
        )
    assert "distinct states found" in ran.stdout, ran.stdout[-4000:] + ran.stderr[-2000:]
    return ran.stdout


def broken(out: str) -> set[tuple[str, str]]:
    """Each act whose trace breaks a rule, with the rule: the act is `on` in the trace."""
    parts = re.split(r"Error: Invariant (\w+) is violated\.", out)
    return {
        (re.search(r'/\\ on = "(\w+)"', trace)[1], rule)
        for rule, trace in zip(parts[1::2], parts[2::2], strict=True)
    }


@JAVA
def test_today_s_code_breaks_the_rules_on_the_six_acts_the_config_names():
    """TLC's verdict on TellOnce.cfg: the six acts its comment names break, each its one rule, and
    the seven others hold both."""
    assert broken(tlc("none")) == TODAY
    comment = (SPEC / "TellOnce.cfg").read_text()
    assert all(re.search(rf"\\\*\s+{act}\s+{rule}", comment) for act, rule in TODAY)


@JAVA
@pytest.mark.parametrize(
    ("fault", "rule"), [("mark-first", "NoTellLost"), ("no-mark", "NoTellTwice")]
)
def test_each_canary_breaks_its_rule_on_every_act(fault, rule):
    """`Fault = "mark-first"` writes the marks before the act, so a pass that dies between them
    leaves a mark and no act; `Fault = "no-mark"` reads no mark, so the act runs again on the next
    pass. Each breaks its rule on every act, so no act holds the rule by construction."""
    assert {act for act, broke in broken(tlc(fault)) if broke == rule} == ACTS
