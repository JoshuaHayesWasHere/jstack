"""How jbus files main's fix and revert, and the nightly runs it has seen, as a TLA+ spec,
`features/jbus/spec/MainFix.tla`: each quote of the spec stands once in the file it cites; each
carrier of the ledger's MainFix rows is a variable that quotes the code that writes it; and TLC
says what each rule does on today's code: `MainFix.cfg` holds, each of `FIXED` holds in its
World, each of `CANARIES` breaks its rule, and each of `FINDINGS` breaks while the code does. The
TLC runs skip where no Java runs TLC."""

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
lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")

READ_SET = ("features/jbus/src/",)
"""The code MainFix.tla quotes, each file as `jbus/<file>.py`."""

PATH = re.compile(r"\bjbus/\w+\.py\b")

CARRIERS = {
    "B-023": "revertBrief",
    "B-028": "fix",
    "B-029": "macFix",
    "B-030": "browserSeen",
    "B-031": "macosSeen",
    "B-032": "scheduledSeen",
}
"""Each row of the st-state-ledger with machine MainFix, and the variable that carries it."""

FINDINGS: set[tuple[str, str]] = set()
"""The rules today's code breaks, each with the World it breaks in, none: st-main-fix-crash-gaps
fixed the five that st-model-main-fix found, RevertSaid in `{}`, RevertKnown in `{"hand"}` and
`{"refuses"}`, FiledWhole in `{"refuses"}` and `{"late"}`. A break TLC finds again goes here,
with its trace in MainFix.cfg's comment."""

FIXED = {
    ("RevertSaid", "{}"),
    ("RevertKnown", '{"hand"}'),
    ("RevertKnown", '{"refuses"}'),
    ("FiledWhole", '{"refuses"}'),
    ("FiledWhole", '{"late"}'),
}
"""The five breaks st-model-main-fix found, each a rule and the World it broke in, which
st-main-fix-crash-gaps fixed: TLC holds each rule in its World."""

CANARIES = {
    ("RevertSaid", "{}", "keep-first"),
    ("RevertKnown", '{"hand"}', "no-known"),
    ("FiledWhole", '{"refuses"}', "brief-first"),
    ("FiledWhole", '{"late"}', "brief-first"),
}
"""Each fix of st-main-fix-crash-gaps taken back (`Fault`), with the rule and the World it was
found broken in: TLC finds each break again, so the rules still see what they were written for."""


def comments() -> str:
    """The comments of MainFix.tla, one line each joined by a space, so a quote may wrap."""
    text = (SPEC / "MainFix.tla").read_text()
    notes = [line.split("\\*", 1)[1] for line in text.splitlines() if "\\*" in line]
    return " ".join(" ".join(note.split()) for note in notes)


def quoted():
    """Each backticked quote of MainFix.tla's comments, with the file named last before it, its
    lines, and each span of them that holds the quote."""
    flat = comments()
    assert not re.search(r"\.py:\d", flat), "a cite names a line: quote the code instead"
    for found in re.finditer(r"`([^`]+)`", flat):
        named = PATH.findall(flat[: found.start()])
        path = named[-1] if named else ""
        lines = (REPO / "features" / "jbus" / "src" / path).read_text().splitlines() if path else []
        yield path, found[1], lines, lib.located(lines, found[1]) if path else []


def test_each_quote_of_the_spec_stands_once_in_its_file():
    """Each quote stands once in the file named before it, so a cite finds its line with no line
    number, and a quote the code changed, moved to another file or copied fails here."""
    quotes = list(quoted())
    assert len(quotes) > 30
    wrong = [
        f"{path or 'no file'} `{quote}`: {len(at)} times"
        for path, quote, _, at in quotes
        if len(at) != 1
    ]
    assert wrong == []


def test_each_carrier_is_a_variable_that_quotes_its_writer():
    """Each ledger row of MainFix has its variable, and the variable's comment names the row and
    quotes code of a file it names."""
    text = (SPEC / "MainFix.tla").read_text()
    block = text[text.index("VARIABLES") : text.index("vars ==")]
    code = " ".join(line.split("\\*", 1)[0] for line in block.splitlines())
    declared = set(re.findall(r"\w+", code.removeprefix("VARIABLES")))
    for row, name in CARRIERS.items():
        assert name in declared, f"{row}: no variable {name}"
        at = block.index(row)
        assert PATH.search(block[at:]) and "`" in block[at:], f"{row}: no quote of its writer"


def tlc(cfg: str) -> subprocess.CompletedProcess:
    """TLC's run of MainFix.tla with the config `cfg`, in a copy of the spec's folder. Java's tmpdir
    is the run's own too: TLC writes Naturals.tla and the other standard modules there under fixed
    names, and a run that shares /tmp can parse one while another rewrites it."""
    found = tools.find_tlc()
    with tempfile.TemporaryDirectory(prefix="mainfix-") as folder:
        work = Path(folder)
        (work / "tmp").mkdir()
        shutil.copy(SPEC / "MainFix.tla", work)
        (work / "run.cfg").write_text(cfg)
        command = [found.java, f"-Djava.io.tmpdir={work / 'tmp'}"]
        command += ["-Xmx1g", "-XX:+UseParallelGC", "-cp", found.jar, "tlc2.TLC"]
        command += ["-workers", "1", "-metadir", str(work / "meta"), "-config", "run.cfg"]
        return subprocess.run(
            tools.in_test_slot([*command, "MainFix.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=600,
        )


@JAVA
def test_tlc_finds_every_red_filed_whole_and_every_revert_known():
    ran = tlc((SPEC / "MainFix.cfg").read_text())
    assert ran.returncode == 0, ran.stdout[-4000:]
    assert "No error has been found" in ran.stdout
    states = re.search(r"([\d,]+) distinct states found, 0 states left on queue", ran.stdout)
    assert states and states[1].replace(",", "") in (SPEC / "MainFix.cfg").read_text()


def alone(rule: str, world: str = "{}", fault: str = "none") -> subprocess.CompletedProcess:
    """TLC's run of MainFix.cfg with `world` and `fault`, checking only TypeOK and `rule`."""
    kept = (SPEC / "MainFix.cfg").read_text()
    kept = kept.replace("World = {}", f"World = {world}").replace(
        'Fault = "none"', f'Fault = "{fault}"'
    )
    lines = [one for one in kept.splitlines() if not one.startswith(("INVARIANT", "PROPERTY"))]
    return tlc("\n".join([*lines, "INVARIANT TypeOK", f"INVARIANT {rule}", ""]))


@JAVA
@pytest.mark.parametrize(("rule", "world"), sorted(FIXED))
def test_each_fixed_break_holds_in_the_world_it_broke_in(rule, world):
    ran = alone(rule, world)
    assert ran.returncode == 0, ran.stdout[-4000:]
    assert "No error has been found" in ran.stdout


@JAVA
@pytest.mark.parametrize(("rule", "world", "fault"), sorted(CANARIES))
def test_each_fix_taken_back_breaks_its_rule_again(rule, world, fault):
    ran = alone(rule, world, fault)
    assert ran.returncode != 0
    assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]


@JAVA
@pytest.mark.parametrize(("rule", "world"), sorted(FINDINGS))
def test_each_finding_still_breaks_its_rule(rule, world):
    """Each finding MainFix.cfg's comment keeps is still a break of today's code."""
    ran = alone(rule, world)
    assert ran.returncode != 0
    assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]
