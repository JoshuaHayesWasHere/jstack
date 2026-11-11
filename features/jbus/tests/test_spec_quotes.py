"""The quotes of jbus's TLA+ specs, `features/jbus/spec/{RowLife,ThreadLife,GreenMove}.tla`: each
cite names a file and quotes its code, with no line number, and each quote stands once in that
file, so a quote the code moved off its block, changed or copied fails here, also where no Java
runs TLC. A line shift alone changes nothing a cite says."""

import importlib
import re
import subprocess
import sys

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jbus" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))
lib = importlib.import_module("statechart.lib")

READ_SET = ("features/jbus/spec/", "features/jbus/src/jbus/", "features/home/skills/")
"""The specs and the code their quotes cite: a change to either runs these tests."""

SPECS = {"RowLife.tla": 15, "ThreadLife.tla": 30, "GreenMove.tla": 8}
"""Each spec, and fewer quotes than it holds, so a regex that stops matching fails here."""

HOME = "features/jbus/src/jbus/"
"""Where a cite's bare file name points when the repo holds more than one of that name."""

QUOTE = re.compile(r"([\w./-]+\.(?:py|md))\s*`([^`]+)`")
"""A cite with the code it quotes: jbus/threads.py `CARRY_ONS = 2`."""
STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
OR = re.compile(r"\bor\b")


def quoted(spec):
    """Each quote of `spec`: its file as cited, the quote, the file's lines, and each span of them
    that holds the quote."""
    text = (SPEC / spec).read_text()
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)
    files = subprocess.run(
        ["git", "ls-files", "features"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert not re.search(r"\.(?:py|md):\d", flat), f"{spec} cites a line number"
    for path, quote in QUOTE.findall(flat):
        found = [one for one in files if one.endswith(f"/{path}")]
        if len(found) > 1:
            # A bare name is jbus's own module, as queue.py is jbus/queue.py and not the
            # telemetry record of the same name.
            found = [one for one in found if one == HOME + path]
        assert len(found) == 1, f"{spec}: {path} names {len(found)} files"
        lines = (REPO / found[0]).read_text().splitlines()
        yield path, quote, lines, lib.located(lines, quote)


@pytest.mark.parametrize("spec", SPECS)
def test_each_quote_of_the_spec_stands_once_in_its_file(spec):
    quotes = list(quoted(spec))
    assert len(quotes) > SPECS[spec]
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, _, at in quotes if len(at) != 1]
    assert wrong == []


@pytest.mark.parametrize("spec", SPECS)
def test_a_quote_of_one_python_line_holds_each_or_on_it(spec):
    """A quote that stands on one line of Python holds every `or` of that line, so a disjunct the
    code gains fails here until the spec takes it in."""

    def disjuncts(code):
        return len(OR.findall(STRING.sub("", code)))

    short = [
        f"{path} `{quote}`"
        for path, quote, lines, at in quoted(spec)
        if path.endswith(".py")
        and len(at) == 1
        and at[0][0] == at[0][1]
        and disjuncts(quote) != disjuncts(lines[at[0][0] - 1])
    ]
    assert short == []
