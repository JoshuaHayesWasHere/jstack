"""`/deeper` loads only when typed, and the gate its "Run by a home" section pipes is one that
`jbus gate` keeps: the block is cut out of the skill, filled in, and handed to the code of
`jbus gate`, which numbers it and keeps its two options."""

import re
from datetime import UTC, datetime
from pathlib import Path

from jbus import questions
from jdrift.explained import FRONT_MATTER

REPO = Path(__file__).parent.parent
SKILL = REPO / "skills" / "deeper" / "SKILL.md"
HEREDOC = re.compile(r"<< 'THE_GATE_ENDS_HERE'\n(.*?)^THE_GATE_ENDS_HERE$", re.M | re.S)
NOW = datetime(2026, 10, 15, 6, 0, tzinfo=UTC)


def front_matter():
    found = FRONT_MATTER.match(SKILL.read_text())
    assert found, "skills/deeper/SKILL.md has no front matter"
    return dict(line.split(": ", 1) for line in found.group(1).splitlines() if ": " in line)


def gate_lines(slug):
    """The skill's gate, with each `<...>` but `<n>` filled in as a home would."""
    (block,) = HEREDOC.findall(SKILL.read_text())
    filled = block.replace("<slug>", slug).replace("<the home's thread id>", "mcp:home-1")
    filled = re.sub(r"<answer (\d)>", r"answer \1", filled)
    filled = filled.replace(
        "<the four answers of /deeper, on this one line, separated by semicolons>",
        "a profiler; the raw log; py-spy; a test",
    )
    return filled


def test_the_skill_is_manual_and_is_named_for_its_directory():
    said = front_matter()
    assert said["name"] == "deeper"
    assert said["disable-model-invocation"] == "true"


def test_the_gate_a_home_pipes_is_kept_with_the_rewrite_as_default_and_two_options(tmp_path):
    lines = gate_lines("perf-brief")
    assert "<" not in lines.replace("## Gate <n>:", "")
    (home := tmp_path / "home" / "tasks").mkdir(parents=True)
    (home / "perf-brief.md").write_text("# perf-brief: a task\nThread: mcp:home-1\n")

    kept, new = questions.ask(tmp_path / "state", home.parent, "perf-brief", lines, NOW)

    assert new
    assert kept.question == (
        "perf-brief: keep the task as written, or take the deeper rewrite of it?"
    )
    assert kept.default == "the brief is written from the rewrite /deeper gave"
    assert [(one.name, one.default, one.recommended) for one in kept.options] == [
        ("use the rewrite", True, True),
        ("keep the original", False, False),
    ]
    assert kept.options[0].follows == (
        "the brief starts from answer 2, works with answer 3, and is proved by answer 4"
    )


def test_the_same_gate_piped_again_is_the_same_question(tmp_path):
    (home := tmp_path / "home" / "tasks").mkdir(parents=True)
    first, _ = questions.ask(tmp_path / "state", home.parent, "a", gate_lines("a"), NOW)
    again, new = questions.ask(tmp_path / "state", home.parent, "a", gate_lines("a"), NOW)
    assert not new
    assert again.number == first.number
