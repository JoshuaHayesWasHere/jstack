"""A plan entry's `Stage:` line says one of four stages, and only a proposed or planned entry is
briefed once its `Builds on:` has merged. `jbus plan` flags an entry whose stage is none of the
four, by the entry and the word, and such an entry is never briefed: real plans held `queued`
and `paused`, which jbus used to take for a go. The tests run the real `jbus plan` against the
kitchen's config and home, and ask `buildable` what a pass would wake."""

import pytest

from jbus import plan as plans
from test_jbus_kitchen import Kitchen

BRIEFED = {"proposed": True, "planned": True, "parked": False, "scouting": False}
MERGED = [{"slug": "base", "status": "merged"}]


def entry(word: str) -> str:
    return f"""\
# demo: plan

## next: build on base
Stage: {word}
Builds on: base
Done when:
- it works
"""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def test_the_test_names_every_stage():
    assert sorted(stage.value for stage in plans.Stage) == sorted(BRIEFED)


@pytest.mark.parametrize("word", sorted(BRIEFED))
def test_a_known_stage_is_briefed_by_its_value_and_flagged_by_no_line(kitchen, word):
    (kitchen.home / "plan.md").write_text(entry(word))
    briefed = [one.entry for one in plans.buildable(kitchen.home, MERGED)]
    assert briefed == (["next"] if BRIEFED[word] else [])
    code, said = kitchen.main("plan")
    assert code == 0, said
    assert said.splitlines() == [f"next | build on base | {word}"]


@pytest.mark.parametrize(
    "said", ["queued", "paused (all code merged: #63, #64; its branch has no PR)"]
)
def test_a_stage_outside_the_four_is_flagged_and_never_briefed(kitchen, said):
    (kitchen.home / "plan.md").write_text(entry(said))
    word = said.split()[0]
    assert plans.buildable(kitchen.home, MERGED) == []
    code, lines = kitchen.main("plan")
    assert code == 0, lines
    flagged = [line for line in lines.splitlines() if "is no stage" in line]
    assert flagged == [
        f"next: Stage {word} is no stage (proposed, planned, parked, scouting), "
        "so it is never briefed"
    ]
