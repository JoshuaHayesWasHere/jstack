"""A crew's proof, review round and rebase as a TLA+ spec, `features/crew/spec/CrewProof.tla`:
each quote of the code it models stands once in its file, each carrier of the ledger is a
variable, and TLC gives the verdicts `CrewProof.cfg` keeps in its comments: today's code breaks
ProofAtHead with the trace the cfg names, each rule alone breaks or holds as the cfg says, and
the canary `Fault = "line-before-run"` breaks ProofAtHead where today's code, with no call moved
to the background, holds it. The TLC runs skip where no Java runs TLC."""

import importlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "crew" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))

READ_SET = (
    "features/crew/spec/",
    "features/crew/",
    "features/jgauge/src/jgauge/",
    "features/jbriefs/src/jbriefs/",
)
"""The spec and the code its quotes cite: a change to either runs these tests."""

lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")
JAVA = pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")

QUOTE = re.compile(r"([\w./-]+\.(?:py|md|sh))\s*`([^`]+)`")
"""A cite of CrewProof.tla with the code it quotes, and no line number:
crew/do-the-task.md `124) ran=124 ;;`, so a line that only moves needs no edit."""
CARRIERS = ("D-026", "D-028", "D-031", "D-035", "D-036", "D-041", "D-063", "D-064", "D-065")
CARRIERS += ("D-126", "D-127", "D-128", "D-129", "D-130")
"""The ledger rows of machine CrewProof in the st-state-ledger report."""


def tla() -> str:
    return (SPEC / "CrewProof.tla").read_text()


def quoted():
    """Each quote of CrewProof.tla: its file as cited, the quote, and each span of the file's
    lines that holds it."""
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", tla())
    files = subprocess.run(
        ["git", "ls-files", "features"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert not re.search(r"\.(?:py|md|sh):\d", flat)
    for path, quote in QUOTE.findall(flat):
        (found,) = [one for one in files if one.endswith(f"/{path}")]
        lines = (REPO / found).read_text().splitlines()
        yield path, quote, lib.located(lines, quote)


def test_each_quote_of_the_crew_proof_spec_stands_once_in_its_file():
    """A quote the code moved off its block, changed or copied fails here, also where no Java
    runs TLC. A line shift alone changes nothing a cite says."""
    quotes = list(quoted())
    assert len(quotes) > 30
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, at in quotes if len(at) != 1]
    assert wrong == []


def test_each_carrier_is_a_variable_whose_comment_quotes_its_writer():
    """Each ledger row of CrewProof heads the comment of one VARIABLE, and that comment quotes
    the code that writes it."""
    block = tla().split("VARIABLES", 1)[1].split("vars ==", 1)[0]
    comments = re.split(r"\n\s*\\\* (?=D-\d{3}:)", block)[1:]
    named = {one[:5]: one for one in comments}
    assert sorted(named) == sorted(CARRIERS)
    for row, text in named.items():
        variable = re.search(r"\n\s*(\w+),?\s*$", text.split("\n    \\* What is not")[0])
        assert variable, row
        assert QUOTE.search(re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)), row


def tlc(cfg: str) -> subprocess.CompletedProcess:
    """TLC's run of CrewProof.tla with the config `cfg`, in a copy of the spec's folder, on one
    worker so its first trace is always the same. Some states have no step left, so TLC is not asked
    to find deadlocks. Java's tmpdir is the run's own too: TLC writes Naturals.tla and the other
    standard modules there under fixed names, and a run that shares /tmp can parse one while another
    rewrites it."""
    found = tools.find_tlc()
    with tempfile.TemporaryDirectory(prefix="crewproof-") as folder:
        work = Path(folder)
        (work / "tmp").mkdir()
        shutil.copy(SPEC / "CrewProof.tla", work)
        (work / "run.cfg").write_text(cfg)
        command = [found.java, f"-Djava.io.tmpdir={work / 'tmp'}"]
        command += ["-Xmx2g", "-cp", found.jar, "tlc2.TLC", "-workers", "1"]
        command += ["-deadlock", "-metadir", str(work / "meta"), "-config", "run.cfg"]
        return subprocess.run(
            tools.in_test_slot([*command, "CrewProof.tla"]),
            cwd=work,
            capture_output=True,
            text=True,
            timeout=600,
        )


def kept(prefix: str) -> str:
    """What the cfg's comment line that starts `\\* <prefix>` says after it."""
    for line in (SPEC / "CrewProof.cfg").read_text().splitlines():
        if line.startswith(f"\\* {prefix}"):
            return line.removeprefix(f"\\* {prefix}").strip()
    raise AssertionError(f"CrewProof.cfg keeps no line {prefix!r}")


def trace(out: str) -> str:
    """The actions of TLC's trace, after its initial state."""
    return " ".join(re.findall(r"^State \d+: <(\w+)", out, re.M)[1:])


def alone(rules: list[str], background: bool = True, fault: str = "none") -> str:
    """CrewProof.cfg with only TypeOK and `rules`, and the constants given."""
    text = (SPEC / "CrewProof.cfg").read_text()
    text = text.replace("Background = TRUE", f"Background = {str(background).upper()}")
    text = text.replace('Fault = "none"', f'Fault = "{fault}"')
    lines = [line for line in text.splitlines() if not line.startswith("INVARIANT")]
    return "\n".join([*lines, "INVARIANT TypeOK", *(f"INVARIANT {r}" for r in rules), ""])


@JAVA
def test_tlc_breaks_proof_at_head_on_todays_code_with_the_trace_the_cfg_keeps():
    ran = tlc((SPEC / "CrewProof.cfg").read_text())
    assert ran.returncode != 0
    assert "Invariant ProofAtHead is violated" in ran.stdout, ran.stdout[-4000:]
    assert trace(ran.stdout) == kept("trace:")
    assert re.search(r"[\d,]+ distinct states found", ran.stdout)


@JAVA
@pytest.mark.parametrize("rule", ["CheckedAtHead", "RecordGoes", "OneScopedReviewer"])
def test_each_rule_the_code_breaks_breaks_with_the_trace_the_cfg_keeps(rule):
    ran = tlc(alone([rule]))
    assert f"Invariant {rule} is violated" in ran.stdout, ran.stdout[-4000:]
    assert trace(ran.stdout) == kept(f"breaks {rule}:")


def states(out: str) -> str:
    (found,) = re.findall(r"([\d,]+) distinct states found, 0 states left", out)
    return found.replace(",", "")


@JAVA
def test_the_review_and_the_rebase_record_hold_over_every_state():
    ran = tlc(alone(["ReviewHeld", "RecordKept"]))
    assert ran.returncode == 0, ran.stdout[-4000:]
    assert "No error has been found" in ran.stdout
    assert f"{states(ran.stdout)} distinct states" == kept("holds ReviewHeld RecordKept:")


@JAVA
def test_a_proof_call_in_the_background_writes_a_proved_line_only_of_the_heads_files():
    """proved.sh runs the head's side in a checkout of the head, and writes no line where HEAD
    moved or the worktree is dirty at its end: an edit, a commit or a dropped edit while its
    call sits in the background leaves no `Proved:` line of files that are not the head's."""
    ran = tlc(alone(["ProvedAtHead"]))
    assert ran.returncode == 0, ran.stdout[-4000:]
    assert "No error has been found" in ran.stdout
    assert f"{states(ran.stdout)} distinct states" == kept("holds ProvedAtHead:")


@JAVA
def test_with_no_call_in_the_background_the_proof_names_its_head():
    ran = tlc(alone(["ProofAtHead"], background=False))
    assert ran.returncode == 0, ran.stdout[-4000:]
    assert f"{states(ran.stdout)} distinct states" == kept("holds ProofAtHead:")


@JAVA
def test_a_checked_line_written_before_its_run_ends_breaks_proof_at_head():
    """The canary, `Fault = "line-before-run"`: `jgauge check` says `running` and exits 0, and
    a block with no `done:` test writes `Checked: jgauge check exit 0` for a run not over."""
    ran = tlc(alone(["ProofAtHead"], background=False, fault="line-before-run"))
    assert ran.returncode != 0
    assert "Invariant ProofAtHead is violated" in ran.stdout, ran.stdout[-4000:]
    assert trace(ran.stdout) == kept('and the canary Fault = "line-before-run" breaks it:')
