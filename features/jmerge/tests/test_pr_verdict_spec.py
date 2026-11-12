"""PrVerdict.tla in `features/jmerge/spec/`, one pull request through jmerge's verdict: each code
line it quotes stands once in its file, and TLC says today's code holds MergesOrWaitsOnYou while
each canary, the code with one hold taken out, breaks it. The TLC runs are `pr_canaries.py`'s,
and they skip where no Java runs TLC."""

import importlib
import re
import subprocess
import sys

import pytest

from testing.paths import REPO

SPEC = REPO / "features" / "jmerge" / "spec"
STATECHART = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
sys.path.insert(0, str(STATECHART))
sys.path.insert(0, str(SPEC))

canaries = importlib.import_module("pr_canaries")
lib = importlib.import_module("statechart.lib")
tools = importlib.import_module("statechart.tools")

QUOTE = re.compile(r"(\w+\.py)\s*`([^`]+)`")
"""A citation of PrVerdict.tla, a file's name and the code it quotes, with no line number."""

FOLDERS = {
    "rebase.py": "features/jbus/src/jbus",
    "expedite.py": "features/jbus/src/jbus",
    "outbox.py": "features/jbus/src/jbus",
    "poll.py": "features/jbus/src/jbus",
    "stall.py": "features/jbus/src/jbus",
}
"""Where a cited file lives, where it is not jmerge's (the spec's header says so too)."""


def quoted():
    """Each quote of PrVerdict.tla: its file, the quote, the file's lines, and each span of them
    that holds the quote."""
    text = (SPEC / "PrVerdict.tla").read_text()
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)
    assert not re.search(r"\.py:\d", flat)
    for name, quote in QUOTE.findall(flat):
        path = REPO / FOLDERS.get(name, "features/jmerge/src/jmerge") / name
        lines = path.read_text().splitlines()
        yield name, quote, lines, lib.located(lines, quote)


def test_each_quote_of_the_verdict_stands_once_in_its_file():
    """A quote the code has changed, moved off its block or copied fails here, also where no Java
    runs TLC. A line shift alone changes nothing a cite says."""
    quotes = list(quoted())
    assert len(quotes) > 30
    wrong = [f"{name} `{quote}`: {len(at)} times" for name, quote, _, at in quotes if len(at) != 1]
    assert wrong == []


STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
OR = re.compile(r"\bor\b")


def test_a_quote_of_one_line_holds_each_or_on_it():
    """A quote of one line of Python names a condition and holds every `or` of that line, so a
    disjunct the code gains fails here until the model takes it in."""
    short = [
        f"{name} `{quote}`"
        for name, quote, lines, at in quoted()
        if len(at) == 1
        and at[0][0] == at[0][1]
        and len(OR.findall(STRING.sub("", quote)))
        != len(OR.findall(STRING.sub("", lines[at[0][0] - 1])))
    ]
    assert short == []


RUNS = list(canaries.runs())


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
@pytest.mark.timeout(1800)
@pytest.mark.parametrize(
    ("cfg", "want"),
    [run[1:] for run in RUNS],
    ids=[re.sub(r"[^\w-]+", "-", label) for label, *_ in RUNS],
)
def test_the_run_says_what_it_should(cfg, want):
    """Today's code holds the rule, and each canary breaks it."""
    out = canaries.tlc(tools.find_tlc(), cfg)
    assert canaries.verdict(out) == want, out[-4000:]


def test_the_script_names_a_canary_for_each_drop_the_spec_reads():
    """Each `Kept("...")` of the spec has its canary, and each canary a `Kept` to take out."""
    kept = set(re.findall(r'Kept\("([\w-]+)"\)', (SPEC / "PrVerdict.tla").read_text()))
    assert kept == set(canaries.CANARIES)


def test_the_rule_reads_every_open_pull_request():
    """The rule's leads-to starts from every open pull request, not from a ready one, so TLC fails
    on any path that waits for ever on a crew, a check, GitHub or jmerge."""
    text = (SPEC / "PrVerdict.tla").read_text()
    rule = re.search(r"^MergesOrWaitsOnYou ==(.*?)(?=^\S|^====)", text, re.M | re.S)
    assert rule is not None
    assert re.search(r"\(Open ~> \(st = \"merged\" \\/ WaitsOnYou\)\)", rule.group(1))


def test_a_canary_drops_jbus_s_limit_on_failed_heads():
    """A crew's fix may fail again up to jbus's hold at two failed heads, and the canary that
    drops that limit is one TLC must see break the rule."""
    assert "twice" in canaries.CANARIES
    assert ("canary twice", canaries.config("twice"), "breaks") in RUNS


def test_the_script_by_hand_ends_0_when_every_run_says_what_it_should(tmp_path):
    """pr_canaries.py by hand prints a line for each run, with a java that says each is what it
    should be."""
    java = tmp_path / "java"
    java.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = -version ]; then echo \'openjdk version "21"\' >&2; exit 0; fi\n'
        'case "$(cat run.cfg)" in *\'Drop = "none"\'*) '
        'echo "Model checking completed. No error has been found." ;; '
        '*) echo "Error: Temporal properties were violated." ;; esac\n'
    )
    java.chmod(0o755)
    (tmp_path / "tla2tools.jar").write_text("")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "JAVA": str(java),
        "TLA2TOOLS": str(tmp_path / "tla2tools.jar"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "JGAUGE_LOCKS_DIR": str(tmp_path / "locks"),
        "JGAUGE_TEST_SLOT": "test",
    }
    ran = subprocess.run(
        [sys.executable, str(SPEC / "pr_canaries.py")], capture_output=True, text=True, env=env
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    lines = ran.stdout.splitlines()
    assert lines[-1] == "every run says what it should"
    assert len(lines) == len(RUNS) + 1


def test_each_waiting_verdict_shows_the_step_that_ends_its_wait_on_the_chart():
    """A verdict jmerge says waits on someone: its check, its reviewer, its crew, GitHub, the one
    ahead, main's fix or you, and a row jbus held at two failed heads, which waits on you. The
    chart draws that one's step out of it, back to jmerge's next judgment or to merged, so no
    verdict reads as a stall."""
    words = importlib.import_module("statechart.mapping").load_mapping(SPEC / "PrVerdict.map.py")
    run = {words.STEPS[a] for a in words.RUN} | {words.STEPS["BatchProves"]}
    owners = {*words.STEPS.values(), "its check passes", "its check fails"} - run
    judged, merged = words.SAID["none"], words.SAID["merged"]
    chart = (SPEC / "PrVerdict-statechart" / "chart.mmd").read_text()
    says = lib.parse_mermaid(chart)["regions"]["What jmerge says"]
    waits = sorted(set(says["states"]) - {judged, merged})
    assert set(waits) == set(words.SAID.values()) - {judged, merged} | {words.HELD}
    unended = [
        verdict
        for verdict in waits
        if not any(
            t["from"] == verdict and t["label"] in owners and t["to"] in (judged, merged)
            for t in says["transitions"]
        )
    ]
    assert not unended, f"no step of its owner is drawn out of: {unended}"
