"""The setup records as a TLA+ spec, `features/jinstall/spec/Setup.tla`: each quote of the code it
models stands once in its file, each carrier of the ledger is a variable, and TLC's verdicts on
today's code and on the canaries are the ones the spec's README keeps. Today's code holds the
mirror, records each path the install makes for its own use, and holds OneWebhook and
UrlNamesWebhook however an expert's turn stops, and it breaks UninstallComplete through the
record's own folder. The install's canary, which makes a folder before it records it, breaks
UninstallComplete through the folder, and each expert canary breaks the rule its fault broke.
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

SPEC = REPO / "features" / "jinstall" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

READ_SET = (
    "features/jinstall/spec/",
    "features/jinstall/src/jinstall/",
    "features/jroles/src/jroles/",
    "features/expert/",
)
"""The spec and the code its quotes cite: a change to either runs these tests."""

lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")

QUOTE = re.compile(r"([\w./-]+\.(?:py|md))\s*`([^`]+)`")
"""A cite of Setup.tla with the code it quotes, and no line number:
jinstall/machine.py `fcntl.flock(held, fcntl.LOCK_EX)`, so a line that only moves needs no edit."""

CARRIERS = ("D-078", "D-092", "D-093", "D-094", "D-095", "D-136", "D-137", "D-138")

RULES = {
    "MirrorKept": ("mirror", None),
    "MadePathsRecorded": ("install", None),
    "RecordLevelsRecorded": ("install", "NoteMkdir"),
    "UninstallComplete": ("install", "NoteMkdir"),
    "OneWebhook": ("expert", None),
    "UrlNamesWebhook": ("expert", None),
}
"""Each rule of Setup.tla, the part whose variables it reads, and the step at which today's code
breaks it, or None where it holds. The parts change apart, so a rule checked on its own part
alone has the verdict it has on all three. The expert's rules hold since step 4 of
expert/when-an-expert-starts.md compares its record with T3 Code's tasks on each start."""

EXPERT_FAULTS = {
    "purge-own": ("OneWebhook", "Create"),
    "record-first": ("UrlNamesWebhook", "Look"),
    "no-mend": ("OneWebhook", "Look"),
}
"""Each canary of the expert's part, the rule it breaks and the step at which it breaks it: each
puts back one fault of the text before, so a rule that holds is shown to catch it."""


def quoted():
    """Each quote of Setup.tla: its file as cited, the quote, and each span of the file's lines
    that holds it."""
    text = (SPEC / "Setup.tla").read_text()
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)
    files = subprocess.run(
        ["git", "ls-files", *READ_SET[1:]],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert not re.search(r"\.(?:py|md):\d", flat)
    for path, quote in QUOTE.findall(flat):
        (found,) = [one for one in files if one.endswith(f"/{path}")]
        lines = (REPO / found).read_text().splitlines()
        yield path, quote, lib.located(lines, quote)


def test_each_quote_of_the_setup_spec_stands_once_in_its_file():
    """A quote the code moved off its block, changed or copied fails here, also where no Java
    runs TLC."""
    quotes = list(quoted())
    assert len(quotes) > 20
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, at in quotes if len(at) != 1]
    assert wrong == []


def test_each_carrier_of_the_ledger_is_a_variable_that_quotes_its_writer():
    """Each ledger row of the Setup machine names a VARIABLE, whose comment cites the file that
    writes it with a quote."""
    text = (SPEC / "Setup.tla").read_text()
    block = text[text.index("VARIABLES") : text.index("vars ==")]
    for carrier in CARRIERS:
        comment = block[block.index(carrier) :]
        comment = comment[: re.search(r"^\s+\w+,?\s*$", comment, re.M).start()]
        assert QUOTE.search(re.sub(r"\s*\n\s*\\\*\s*", " ", comment)), carrier


def tlc(cfg: str) -> subprocess.CompletedProcess:
    """TLC's run of Setup.tla with the config `cfg`, on one worker, in a copy of the spec's
    folder, so its trace is the same on each run."""
    found = tools.find_tlc()
    with tempfile.TemporaryDirectory(prefix="setup-") as folder:
        work = Path(folder)
        shutil.copy(SPEC / "Setup.tla", work)
        (work / "run.cfg").write_text(cfg)
        command = [found.java, "-Xmx512m", "-cp", found.jar, "tlc2.TLC", "-workers", "1"]
        command += ["-metadir", str(work / "meta"), "-config", "run.cfg", "Setup.tla"]
        return subprocess.run(
            tools.in_test_slot(command),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=300,
        )


def last_step(out: str) -> str:
    """The action of the last state of TLC's trace."""
    return re.findall(r"^State \d+: <(\w+)", out, re.M)[-1]


def alone(rule: str, part: str, fault: str = "none") -> subprocess.CompletedProcess:
    """TLC's run of `rule` with TypeOK, over `part` alone, with `Fault = fault`."""
    cfg = (SPEC / "Setup.cfg").read_text()
    cfg = cfg.replace('Fault = "none"', f'Fault = "{fault}"')
    cfg = re.sub(r"Parts = \{[^}]*\}", f'Parts = {{"{part}"}}', cfg)
    lines = [line for line in cfg.splitlines() if not line.startswith("INVARIANT")]
    return tlc("\n".join([*lines, "INVARIANT TypeOK", f"INVARIANT {rule}", ""]))


@JAVA
def test_tlc_on_setup_cfg_finds_the_record_folder_made_before_its_record():
    """Setup.cfg, today's code on all three parts: the trace its comment keeps."""
    ran = tlc((SPEC / "Setup.cfg").read_text())
    assert "distinct states found" in ran.stdout, ran.stdout[-4000:]
    assert "Invariant UninstallComplete is violated" in ran.stdout, ran.stdout[-4000:]
    assert re.findall(r"^State \d+: <(\w+)", ran.stdout, re.M) == ["Initial", "Begin", "NoteMkdir"]


@JAVA
@pytest.mark.parametrize("rule", sorted(RULES))
def test_tlc_gives_each_rule_the_verdict_the_readme_keeps(rule):
    part, breaks_at = RULES[rule]
    ran = alone(rule, part)
    if breaks_at is None:
        assert ran.returncode == 0, ran.stdout[-4000:]
        assert "No error has been found" in ran.stdout
    else:
        assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]
        assert last_step(ran.stdout) == breaks_at


@JAVA
@pytest.mark.parametrize("rule", ["UninstallComplete", "MadePathsRecorded"])
def test_a_folder_made_before_its_record_breaks_the_rule(rule):
    """The canary, `Fault = "note-after"`: make_dirs makes the folder and records it after, so a
    stop between the two leaves a folder no record names. It breaks MadePathsRecorded, which
    today's code holds, and UninstallComplete at the folder and not at the record's own."""
    ran = alone(rule, "install", "note-after")
    assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]
    assert last_step(ran.stdout) == "Make"


@JAVA
@pytest.mark.parametrize("fault", sorted(EXPERT_FAULTS))
def test_each_fault_of_the_expert_text_before_breaks_its_rule(fault):
    """A turn that stops between a call and its write: the purge of this thread's strays alone
    leaves two webhooks, the record before the address loses it, and a record kept as it is
    names a thread its webhook no longer posts into."""
    rule, breaks_at = EXPERT_FAULTS[fault]
    ran = alone(rule, "expert", fault)
    assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]
    assert last_step(ran.stdout) == breaks_at
