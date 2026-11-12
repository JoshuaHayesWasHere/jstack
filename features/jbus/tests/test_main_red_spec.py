"""Main's red as a TLA+ spec, `features/jbus/spec/MainRed.tla`: each condition quotes the code that
checks it, and the quote stands once in its file; the spec checks each property
`main_red_model.py` walks over the real `mainmoved.tell`; and TLC says what each rule of
`MainRed.cfg` does on today's code: every rule holds, and `BREAKS` names a rule only while the
code breaks it. The TLC runs skip where no Java runs TLC."""

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

READ_SET = ("features/jbus/src/", "features/jmerge/src/")
"""The code MainRed.tla quotes, each file as `<package>/<file>.py`."""

QUOTE = re.compile(r"([\w./-]+\.(?:py|md))((?:\s*(?:,|and)?\s*`[^`]+`)+)")
"""A cite of MainRed.tla by the code it quotes, with no line number:
jbus/mainmoved.py `*([stands] if stands else []),`, so a line that only moves needs no edit. Each
quote after it joined by a comma or "and", as in `a` and `b`, is a quote of the same file."""

AGREES = {
    "S1": "KnownRedReadAsRed",
    "S2": "NoStuckRed",
    "S3": "RedTipsOwnTests",
    "S4": "EachRedJudgedOnce",
}
"""Each property `main_red_model.py` walks, and the rule of MainRed.tla that says it."""

MOST_GENERATED = 900_000
"""The most states a TLC run of a config may generate, so each test ends in under 200 s on CI's
slowest runner: on 2026-11-11 a test of this file whose run generated at least 2,874,771 states
took over 600 s in CI's check on #1681, at most 4.8k states a second, and 200 s of that is about
958k. A step that takes facts that change nothing, each as a successor TLC checks again,
multiplies this count and not the distinct states."""

BREAKS: set[str] = set()
"""The rules today's code breaks, none: `reverts.close` closes a revert whose red main passed
at or above even where a newer tip is red, so `OneRevertOpen` holds, and waits for every check
that holds it, so `NeverRevertedTwice` holds."""


def quoted():
    """Each quote of MainRed.tla: its file as cited, the quote, the file's lines, and each span of
    them that holds the quote."""
    text = (SPEC / "MainRed.tla").read_text()
    flat = re.sub(r"\s*\n\s*(?:\\\*)?\s*", " ", text)
    assert not re.search(r"\.(?:py|md):\d", flat)
    for path, quotes in QUOTE.findall(flat):
        lines = (REPO / "features" / path.split("/")[0] / "src" / path).read_text().splitlines()
        for quote in re.findall(r"`([^`]+)`", quotes):
            yield path, quote, lines, lib.located(lines, quote)


def test_each_quote_of_the_spec_stands_once_in_its_file():
    """Each quote stands in its file once, so the cite finds its line, and a quote the code has
    moved off its block, changed or copied fails here, also where no Java runs TLC."""
    quotes = list(quoted())
    assert len(quotes) > 20
    wrong = [f"{path} `{quote}`: {len(at)} times" for path, quote, _, at in quotes if len(at) != 1]
    assert wrong == []


def test_each_condition_of_a_step_cites_its_code():
    """No condition of a step waits on something no cited code checks."""
    text = (SPEC / "MainRed.tla").read_text()
    assert lib.uncited_conditions(text) == []


def rules(cfg):
    """The INVARIANT and PROPERTY lines of a config, by name."""
    return re.findall(r"^(?:INVARIANT|PROPERTY) (\w+)$", cfg, re.M)


def test_the_spec_checks_each_property_the_walk_of_the_real_code_checks():
    """Each of S1 to S4, which `main_red_model.py` walks over the real `tell`, is a rule of
    MainRed.cfg and of the chart's config, so a property the walk gains needs its rule here."""
    sys.path.insert(0, str(REPO / "features" / "jbus" / "tests"))
    walk = importlib.import_module("main_red_model")
    assert set(AGREES) == set(walk.PROPERTIES)
    for cfg in ("MainRed.cfg", "MainRed.chart.cfg"):
        assert set(AGREES.values()) <= set(rules((SPEC / cfg).read_text())), cfg


def tlc(found, cfg):
    """TLC's output for MainRed.tla with `cfg`, in a copy of the spec folder, kept under its
    inputs as the other specs' runs are."""
    inputs = [cfg, (SPEC / "MainRed.tla").read_bytes(), *tools.tlc_inputs(found)]

    def run():
        with tempfile.TemporaryDirectory(prefix="main-red-") as folder:
            work = Path(folder)
            shutil.copy(SPEC / "MainRed.tla", work)
            (work / "run.cfg").write_text(cfg)
            ran = subprocess.run(
                tools.in_test_slot(
                    [
                        found.java,
                        "-Xmx1g",
                        "-XX:+UseParallelGC",
                        f"-Djava.io.tmpdir={work}",
                        "-cp",
                        found.jar,
                        "tlc2.TLC",
                        "-workers",
                        tools.workers(),
                        "-metadir",
                        str(work / "meta"),
                        "-config",
                        "run.cfg",
                        "MainRed.tla",
                    ]
                ),
                cwd=work,
                capture_output=True,
                text=True,
            )
        return ran.stdout + ran.stderr

    return tools.kept(run, inputs, lambda out: verdict(out) != "error")


def verdict(out):
    """`holds`, the rule TLC found broken, or `error`."""
    if "Model checking completed. No error has been found." in out:
        return "holds"
    broke = re.search(r"Invariant (\w+) is violated", out)
    if broke:
        return broke.group(1)
    return "breaks a property" if "Temporal properties were violated" in out else "error"


def generated(out):
    """The count of states TLC generated, distinct or not, from its last line that says it."""
    return int(re.findall(r"^([\d,]+) states generated", out, re.M)[-1].replace(",", ""))


def without(cfg, names):
    """The config with the rules `names` taken out."""
    lines = cfg.splitlines(keepends=True)
    return "".join(line for line in lines if not (line.split() and line.split()[-1] in names))


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
@pytest.mark.timeout(600)
@pytest.mark.parametrize("cfg", ["MainRed.cfg", "MainRed.chart.cfg"])
def test_today_s_code_holds_every_rule_but_the_ones_it_breaks(cfg):
    """TLC on today's code: with the rules it breaks left out, every other rule of the config
    holds, the property that red ends only by a merge among them, in at most MOST_GENERATED
    states; and each of those alone breaks."""
    text = (SPEC / cfg).read_text()
    found = tools.find_tlc()
    held = tlc(found, without(text, BREAKS))
    assert verdict(held) == "holds", held[-4000:]
    assert generated(held) <= MOST_GENERATED, held[-4000:]
    for rule in BREAKS:
        alone = tlc(found, without(text, set(rules(text)) - {rule, "TypeOK"}))
        assert verdict(alone) == rule, alone[-4000:]


@pytest.mark.skipif(not tools.find_java(), reason="no Java to run TLC")
@pytest.mark.timeout(600)
def test_a_revert_held_by_its_opener_alone_is_opened_twice():
    """The canary, the code before holders (`Fault = "opener-only"`): main closes its revert on
    its own green at the red commit while the Mac still leans on it, the record goes, and the
    Mac, red at that commit, opens a second revert, as #1427 did on 2026-11-09. With the Mac in
    the model, `NeverRevertedTwice` alone breaks."""
    text = (SPEC / "MainRed.chart.cfg").read_text()
    assert "CONSTANT Mac = TRUE" in text
    canary = text.replace('Fault = "none"', 'Fault = "opener-only"')
    assert 'Fault = "opener-only"' in canary
    alone = tlc(tools.find_tlc(), without(canary, set(rules(canary)) - {"NeverRevertedTwice"}))
    assert verdict(alone) == "NeverRevertedTwice", alone[-4000:]
