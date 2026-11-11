"""The merge run's TLA+ spec, `features/jmerge/spec/MergeRun.tla`: each quote of the code it
models stands once in its file, each carrier of the ledger has its variable, and TLC gives each
rule the verdict its config keeps: today's code breaks RunHeard with `os.replace` before
`_judged`, and the run that judges first holds it. The TLC runs skip where no Java runs TLC."""

import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jmerge" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

READ_SET = ("features/jmerge/spec/", "features/jmerge/src/jmerge/", "features/jbus/src/jbus/")
"""The spec and the code its quotes cite: a change to either runs these tests."""

lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")

QUOTE = re.compile(r"([\w./-]+\.py)\s*`([^`]+)`")
"""A cite of MergeRun.tla: its file, as `jbus/merge.py`, and the code it quotes, with no line
number, so a line that only moves needs no edit."""
CARRIERS = (
    *("B-059", "B-060", "B-061", "B-062", "B-063"),
    *("C-023", "C-029", "C-031", "C-033", "C-043", "C-044"),
)
"""The rows of the st-state-ledger ledger whose machine is MergeRun."""


def quoted():
    """Each quote of MergeRun.tla: its file as cited, the quote, and each span of the file's
    lines that holds it."""
    text = (SPEC / "MergeRun.tla").read_text()
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)
    assert not re.search(r"\.py:\d", flat)
    files = subprocess.run(
        ["git", "ls-files", "features/jbus/src/jbus", "features/jmerge/src/jmerge"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for path, quote in QUOTE.findall(flat):
        (found,) = [one for one in files if one.endswith(f"/{path}")]
        yield path, quote, lib.located((REPO / found).read_text().splitlines(), quote)


def test_each_quote_of_the_merge_run_spec_stands_once_in_its_file():
    """A quote the code moved off its block, changed or copied fails here, also where no Java
    runs TLC. A line shift alone changes nothing a cite says."""
    quotes = list(quoted())
    assert len(quotes) > 40
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, at in quotes if len(at) != 1]
    assert wrong == []


def test_each_carrier_of_the_ledger_has_a_variable_that_quotes_its_writer():
    """Each ledger row names its variable in a comment of the VARIABLES block, with the code
    that writes it quoted on the comment."""
    text = (SPEC / "MergeRun.tla").read_text()
    block = text[text.index("VARIABLES") : text.index("vars ==")]
    missing = []
    for row in CARRIERS:
        at = block.find(f"\\* {row}")
        rest = block[at:]
        variable = re.search(r"^  (\w+)(?:,|$)", rest, re.M) if at >= 0 else None
        if variable is None or not QUOTE.search(rest[: variable.start()]):
            missing.append(row)
    assert missing == []


def tlc(cfg: str, rules: list[str] | None = None, **constants: str) -> str:
    """TLC's output for the config `cfg` of the spec, with `constants` set over its own and,
    where `rules` is given, those invariants and TypeOK in place of its own, run in a copy of
    the spec's folder, as the spec's README runs it. TLC unpacks Naturals.tla and its kin into
    java.io.tmpdir, /tmp by default, where one run can parse the copy another run is still
    writing, so each run unpacks into that copy's folder."""
    text = (SPEC / cfg).read_text()
    for name, value in constants.items():
        text, count = re.subn(rf"(?m)^(\s*{name} = ).*$", rf"\g<1>{value}", text)
        assert count == 1, name
    if rules is not None:
        kept = [line for line in text.splitlines() if not line.startswith("INVARIANT")]
        text = "\n".join([*kept, *(f"INVARIANT {rule}" for rule in ["TypeOK", *rules]), ""])
    found = tools.find_tlc()
    with tempfile.TemporaryDirectory(prefix="merge-run-") as folder:
        work = Path(folder)
        shutil.copy(SPEC / "MergeRun.tla", work)
        (work / "run.cfg").write_text(text)
        command = [found.java, "-XX:+UseParallelGC", "-Xmx1g", f"-Djava.io.tmpdir={work}"]
        command += ["-cp", found.jar, "tlc2.TLC"]
        command += ["-workers", tools.workers(), "-metadir", str(work / "meta")]
        ran = subprocess.run(
            tools.in_test_slot([*command, "-config", "run.cfg", "MergeRun.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=600,
        )
    return ran.stdout + ran.stderr


def expected(cfg: str) -> list[str]:
    return re.findall(r"(?m)^\\\* expect: (\w+)$", (SPEC / cfg).read_text())


@JAVA
@pytest.mark.parametrize(
    "cfg", ["MergeRun.cfg", "MergeRun.restart.cfg", "MergeRun.waits.cfg", "MergeRun.batch.cfg"]
)
def test_tlc_gives_each_config_the_verdict_its_comment_keeps(cfg):
    """TLC on each config as committed: a config with an `expect:` line breaks that rule, and
    one with none holds every rule. TLC prints the distinct states it found either way."""
    out = tlc(cfg)
    assert "distinct states found" in out, out[-4000:]
    broken = re.findall(r"Invariant (\w+) is violated", out)
    if want := expected(cfg):
        assert broken and broken[0] in want, out[-4000:]
    else:
        assert "Model checking completed. No error has been found." in out, out[-4000:]


RULES = [
    ("MergeRun.cfg", {}, "RunHeard", False),
    ("MergeRun.cfg", {}, "StreakOnce", True),
    ("MergeRun.cfg", {}, "NoFalseNoRecord", False),
    ("MergeRun.cfg", {}, "DeathTold", False),
    ("MergeRun.cfg", {}, "OneRunAtATime", True),
    ("MergeRun.cfg", {"Fault": '"judge-first"'}, "RunHeard", True),
    ("MergeRun.cfg", {"Fault": '"judge-first"'}, "StreakOnce", False),
    ("MergeRun.cfg", {"Fault": '"no-run-lock"'}, "OneRunAtATime", False),
    ("MergeRun.restart.cfg", {}, "RestartReopens", False),
    ("MergeRun.restart.cfg", {"ReplyLost": "FALSE"}, "RestartReopens", False),
    (
        "MergeRun.restart.cfg",
        {"ReplyLost": "FALSE", "Fault": '"fresh-list"'},
        "RestartReopens",
        True,
    ),
    ("MergeRun.waits.cfg", {}, "WaitLoggedOnce", True),
    ("MergeRun.waits.cfg", {}, "WaitKept", False),
    ("MergeRun.batch.cfg", {}, "BatchMergedOnce", True),
]
"""Each rule alone, on its config, over today's code or one change to it: whether it holds.
`Fault = "replace-first"` is today's code; a canary is a row that must break, and one that
holds instead fails here."""


@JAVA
@pytest.mark.parametrize(
    ("cfg", "constants", "rule", "holds"),
    RULES,
    ids=[f"{cfg}-{rule}-{'-'.join(c.values()) or 'today'}" for cfg, c, rule, _ in RULES],
)
def test_each_rule_holds_or_breaks_as_the_spec_says(cfg, constants, rule, holds):
    out = tlc(cfg, [rule], **constants)
    if holds:
        assert "Model checking completed. No error has been found." in out, out[-4000:]
    else:
        assert f"Invariant {rule} is violated" in out, out[-4000:]
