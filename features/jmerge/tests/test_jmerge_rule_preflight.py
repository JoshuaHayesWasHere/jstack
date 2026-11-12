"""The rule preflight (`jmerge.preflight`): before `jmerge` merges a pull request that adds or
tightens a test, it runs that test on each open pull request's head merged with it, and holds it
while one fails, until it carries the fix or its Result names each pull request it breaks.

The replay: #1702 merged at 01:16Z on 2026-11-12 with
`test_each_state_but_a_final_one_shows_an_arrow_out_that_says_who_takes_it`, and #1711, #1712,
#1713 and #1716, each open with a new statechart whose drawing has a state with no arrow out,
went red on it within the half hour. Here each is a pull request of the same shape, against a
real origin and the fake `gh` of `test_jmerge_fresh.Kitchen`, run through the `jmerge` command
(`jmerge.cli`, whose judging asks the preflight last): the rule is a pytest file over each
chart's `summary.json`, and the four add a chart with a waiting state and no way out of it, as
their models did."""

import json
import sys
from types import SimpleNamespace

import pytest

from jmerge import lines, preflight, ready
from test_jmerge_fresh import Kitchen, url

RULE = "features/skill-library/tests/test_statechart_site.py"
TEST = "test_each_state_but_a_final_one_shows_an_arrow_out_that_says_who_takes_it"
RULE_TEXT = f"""\
import json
import pathlib

import pytest

EXEMPT = {{exempt}}
CHARTS = sorted(pathlib.Path(".").glob("features/*/spec/*-statechart/summary.json"))


@pytest.mark.parametrize("chart", CHARTS, ids=lambda path: path.parent.name)
def {TEST}(chart):
    if chart.parent.name in EXEMPT:
        return
    drawn = json.loads(chart.read_text())
    left = {{one[0] for one in drawn["arrows"] if one[2]}}
    assert set(drawn["states"]) - set(drawn["final"]) <= left
"""
BROKEN = {
    1711: "features/jsettings/spec/GhBudget-statechart/summary.json",
    1712: "features/jsettings/spec/GhLogRotate-statechart/summary.json",
    1713: "features/jmerge/spec/MergeRun-statechart/summary.json",
    1716: "features/jinstall/spec/Setup-statechart/summary.json",
}


def chart(*arrows, final=("merged",)):
    states = sorted({one for arrow in arrows for one in arrow[:2]} | set(final))
    return json.dumps({"states": states, "final": list(final), "arrows": [*arrows]}) + "\n"


SOUND = chart(["judging", "merged", "jmerge"])
STALLS = chart(["judging", "waiting", "jmerge"], ["judging", "merged", "jmerge"])
"""A chart of the four's shape: `waiting` is no final state, and no arrow leaves it."""


@pytest.fixture
def kitchen(tmp_path):
    return made(tmp_path)


def made(tmp_path, on_main=None):
    """The kitchen, main holding one sound chart and `on_main`, with the state's preflight."""
    ran = tmp_path / "rules-ran"
    files = {"a.txt": "a\n", "features/jmerge/spec/PrVerdict-statechart/summary.json": SOUND}
    made = Kitchen(tmp_path, {**files, **(on_main or {})})
    command = f'echo "$RULES" >> {ran}; "{sys.executable}" -m pytest -q -p no:cacheprovider '
    command += "-o addopts= $RULES"
    (made.home.state / preflight.NAME).write_text(command + "\n")
    made.ran = ran
    return made


def runs(kitchen):
    return len(kitchen.ran.read_text().splitlines()) if kitchen.ran.exists() else 0


def the_four(kitchen):
    for number, path in BROKEN.items():
        kitchen.crew(f"st-{number}", number, {path: STALLS})


def rule(kitchen, exempt="set()", files=None, breaks="", text=None):
    """Open #1702, the rule, with its tests-only `Proved:` line and any `Breaks:` line."""
    text = text if text is not None else RULE_TEXT.replace("{exempt}", exempt)
    head = kitchen.crew("statechart-arrows", 1702, {RULE: text, **(files or {})})
    named(kitchen, head, breaks)
    return head


def named(kitchen, head, breaks):
    proved = f"Proved: {RULE} head exit 0 at {head}, tests only\n"
    kitchen.brief("statechart-arrows", head, proved + (f"Breaks: {breaks}\n" if breaks else ""))


def by_number(said):
    """Each line of a run by its pull request's number: a `ready` line of `--check` as a `Line`
    of the word `ready`, which `lines.one` leaves to the reader."""
    found = {}
    for text in said:
        if text.startswith("ready "):
            found[int(text.split()[1])] = (SimpleNamespace(word="ready", reason=""), text)
        elif line := lines.one(text):
            found[line.number] = (line, text)
    return found


def test_1702_is_held_and_names_1711_1712_1713_and_1716_at_their_01_16z_heads(kitchen):
    the_four(kitchen)
    kitchen.crew("st-other", 1715, {"a.txt": "b\n"})
    rule(kitchen)
    said = by_number(kitchen.run("--check"))
    line, text = said[1702]
    assert line.word == "wait", text
    assert ready.code_of(line.reason) == "rule-breaks"
    for number in BROKEN:
        assert f"#{number} ({RULE}::{TEST}[" in line.reason, line.reason
    assert "#1715" not in line.reason
    assert text == lines.waits("wait", 1702, url(1702), line.reason)


def test_the_merge_run_holds_it_too_and_runs_each_pair_once_until_a_head_moves(kitchen):
    the_four(kitchen)
    rule(kitchen)
    first = by_number(kitchen.run("--check"))[1702][0]
    ran = runs(kitchen)
    assert ran == 1 + 4, "the head alone, then each pair: no row has the new file to run alone"
    again = by_number(kitchen.run())[1702][0]
    assert (again.word, again.reason) == (first.word, first.reason)
    assert [call for call in kitchen.calls() if call.split()[2] == "1702"] == []


def test_a_breaks_line_naming_each_lifts_the_hold_and_the_merge_names_them_for_jbus(kitchen):
    the_four(kitchen)
    head = rule(kitchen)
    named(kitchen, head, "#1711 #1712 #1713")
    held = by_number(kitchen.run("--check"))[1702][0]
    assert held.word == "wait" and "#1716 (" in held.reason
    named(kitchen, head, "#1711 #1712 #1713 #1716")
    _, text = by_number(kitchen.run())[1702]
    assert text.startswith("merged 1702 statechart-arrows "), text
    assert lines.breaks_of(text) == ((RULE,), tuple(BROKEN))


def test_a_rule_that_carries_its_exemption_holds_nothing(kitchen):
    the_four(kitchen)
    exempt = {path.split("/")[-2] for path in BROKEN.values()}
    rule(kitchen, str(sorted(exempt)))
    line, text = by_number(kitchen.run("--check"))[1702]
    assert line.word == "ready", text
    assert not lines.breaks_of(text)[1]


def test_a_rule_that_fails_on_its_own_head_here_proves_nothing_and_holds_nothing(kitchen):
    """CI passed the rule at its head, so a failure there on this machine is of the machine, not
    of the rows: it holds nothing, and no row is run."""
    the_four(kitchen)
    here = RULE_TEXT.replace("{exempt}", "set()") + "\n\ndef test_not_here():\n    assert 0\n"
    rule(kitchen, text=here)
    assert by_number(kitchen.run("--check"))[1702][0].word == "ready"
    assert runs(kitchen) == 1


def test_a_row_already_red_on_the_rule_at_its_own_head_is_not_the_rule_s_to_name(tmp_path):
    """The rule's file was on main, and #1702 tightens it: #1711 fails it at its own head too, so
    the red is #1711's own, which its check shows its crew."""
    kitchen = made(tmp_path, {RULE: RULE_TEXT.replace("{exempt}", "set()")})
    the_four(kitchen)
    rule(kitchen, text=RULE_TEXT.replace("{exempt}", "set()") + "\n")
    line, text = by_number(kitchen.run("--check"))[1702]
    assert line.word == "ready", text


def test_with_no_rule_preflight_file_nothing_runs(kitchen):
    (kitchen.home.state / preflight.NAME).unlink()
    the_four(kitchen)
    rule(kitchen)
    assert by_number(kitchen.run("--check"))[1702][0].word == "ready"
    assert runs(kitchen) == 0


def test_the_preflight_waits_carry_their_code_and_step():
    breaks = ready.RULE_BREAKS.format(tests=RULE, breaks="#1711 (x)")
    unrun = ready.RULE_UNRUN.format(tests=RULE, ran=2, open=5)
    assert (ready.code_of(str(breaks)), ready.step_of("rule-breaks")) == ("rule-breaks", "result")
    assert (ready.code_of(str(unrun)), ready.step_of("rule-unrun")) == ("rule-unrun", "check")
