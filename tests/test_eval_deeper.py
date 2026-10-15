"""The /deeper eval's blind scorer reads a brief's text alone and gives literal counts, and the
eval reads the rewritten prompt out of the form `skills/deeper/SKILL.md` tells /deeper to print."""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
EVAL = REPO / "evals" / "deeper"


def load(name):
    sys.path.insert(0, str(EVAL))
    try:
        spec = importlib.util.spec_from_file_location(f"deeper_{name}", EVAL / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(EVAL))


score = load("score")
run = load("eval")

DEEP = """# perf: make check under 60 s
Task: "figure out what is slowing down make check"
Read: the CI job logs from `gh run view --log`, and the per-test timings of `pytest --durations=50`
Done when:
- `py-spy record` over one run names the slowest frames, and the profile is committed
- the median of 5 runs is under 60 s, with the spread
- the reviewer agrees it is faster
Where: Makefile
"""

SHALLOW = """# perf: make check faster
Task: "figure out what is slowing down make check"
Done when:
- make check is faster
- the crewmate confirms it looks right
Where: Makefile
"""


def test_a_deep_brief_names_its_raw_material_its_instruments_and_an_outside_proof():
    said = score.score(DEEP)
    assert (said.raw, said.instruments, said.beyond, said.proof_lines) == (5, 3, 1, 3)
    assert said.outside == pytest.approx(2 / 3, abs=0.001)


def test_a_shallow_brief_names_none_and_rests_on_the_crewmate():
    said = score.score(SHALLOW)
    assert (said.raw, said.instruments, said.beyond, said.outside) == (0, 0, 0, 0.0)
    assert said.proof_lines == 2


def test_proof_lines_are_the_done_when_items_and_a_proves_it_line():
    text = "Done when:\n- one\n- two\nWhere: x\nProves it: a test\n- not this\n"
    assert score.proof_lines(text) == ["one", "two", "a test"]


def test_the_eval_reads_the_rewritten_prompt_from_the_form_the_skill_prints():
    form = re.search(
        r"^````\n(.*?)^````$", (REPO / "skills/deeper/SKILL.md").read_text(), re.M | re.S
    )
    printed = form[1].replace("<the task, rewritten", "Measure it.\n<the task, rewritten")
    assert run.rewritten(printed).startswith("Measure it.\n<the task, rewritten to ask")


def test_an_output_with_no_rewritten_prompt_is_refused():
    with pytest.raises(RuntimeError, match="no Rewritten prompt"):
        run.rewritten("## 1. What a top professional would do\nnothing\n")


@pytest.mark.parametrize(
    ("wins", "losses", "p"), [(10, 0, 0.002), (8, 2, 0.109), (5, 5, 1.0), (0, 0, 1.0)]
)
def test_the_sign_test_is_two_sided(wins, losses, p):
    assert run.sign_test(wins, losses) == pytest.approx(p, abs=0.001)


def test_the_shipped_brief_is_the_text_above_its_result():
    text = "# a: b\nTask: c\n\n## Result\nStatus: done\n"
    assert run.shipped(text) == "# a: b\nTask: c"
