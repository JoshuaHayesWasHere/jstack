"""`jbus queue add` and `jbus queue check` warn of a brief for a change to code whose `Proves it:`
names a test alone, and queue it all the same.

82 of the polish line's 145 merged code rows proved themselves by a test alone (po-polish-landed),
since the home's skill gave a test alone as the line to write. A test shows the code runs, not
what a user meets once it merges, so the line names beside it a command of the product with what
it prints, a measure read after the merge, or `judged: <why>`. A change no user sees keeps its
test alone, so it is a warning and never a refusal (`jbriefs.proof`,
`user_sees`). The tests run the real command against the kitchen
(`features/jbus/tests/test_jbus_kitchen.py`).
"""

import json
import re
from pathlib import Path

import pytest

from test_jbus_kitchen import Kitchen, complete

SKILL = Path(__file__).parents[2] / "home/skills/home/handing-a-task-to-a-crewmate.md"
TEST = "the touched check passes, with the test the task adds, `features/alpha/tests/test_alpha.py`"
WARNED = (
    "warning: alpha's brief's Proves it: names a test alone for a change to code: beside the "
    "test, name what a user would see, a command of the product in backticks with what it "
    "prints, a measure read after the merge, or judged: <why> (a change no user sees, such as a "
    "refactoring, may keep its test alone)"
)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def brief(proves, where="`src/alpha/`"):
    """A brief that `add` queues, with its `Proves it:` and `Where:` lines as given."""
    lines = complete("alpha").splitlines(keepends=True)
    return "".join(
        f"Proves it: {proves}\n"
        if line.startswith("Proves it:")
        else f"Where: {where}\n"
        if line.startswith("Where:")
        else line
        for line in lines
    )


def warned(kitchen, text, verb):
    """What `jbus queue <verb>` prints of a brief proved by a test alone, after it exits 0."""
    more = ("alpha", "--priority", "1") if verb == "add" else ()
    code, said = kitchen.main("queue", verb, *more, stdin=text)
    assert code == 0, said
    return [line for line in said.splitlines() if "names a test alone" in line]


@pytest.mark.parametrize("verb", ["add", "check"])
@pytest.mark.parametrize(
    ("proves", "where"),
    [
        (TEST, "`src/alpha/`"),
        ("`uv run pytest -q features/alpha/tests`, failing on main", "`features/alpha/src/a.py`"),
        (
            "the tests fail on main and pass on the branch",
            "`a.py`, `features/alpha/docs/a.md`, `tests/`",
        ),
        (f"{TEST}, and `make lint` exits 0", "`.`"),
    ],
)
def test_a_code_brief_proved_by_a_test_alone_is_warned_once_and_queued(
    kitchen, verb, proves, where
):
    assert warned(kitchen, brief(proves, where), verb) == [WARNED]
    if verb == "add":
        queued = json.loads((kitchen.state / "queue.json").read_text())
        assert [row["slug"] for row in queued] == ["alpha"]


@pytest.mark.parametrize("verb", ["add", "check"])
@pytest.mark.parametrize(
    ("proves", "where"),
    [
        (TEST, "`features/alpha/README.md`, `features/alpha/docs/`"),
        (TEST, "`pyproject.toml`, `.github/workflows/check.yml`"),
        (TEST, "`features/alpha/tests/`, `features/alpha/docs/a.md`"),
        ("judged: the user reads the new page and finds it plain", "`src/alpha/`"),
        (f"{TEST}; and `jbus queue list` prints the row as held", "`src/alpha/`"),
        (f"{TEST}; and the row shows in `jbus needs` as the user's", "`src/alpha/`"),
        (f"{TEST}; and a day after the merge the query counts 0 lost rows", "`src/alpha/`"),
        (f"{TEST}; and judged: the home's reply reads plainer", "`src/alpha/`"),
    ],
)
def test_a_brief_of_docs_config_or_tests_or_one_that_names_what_a_user_sees_is_not_warned(
    kitchen, verb, proves, where
):
    assert warned(kitchen, brief(proves, where), verb) == []


@pytest.mark.parametrize(
    "proves",
    [
        f"{TEST}; and `rg -c held src/alpha/x.py` prints 1",
        f"{TEST}; and `features/alpha/tests/test_b.py` prints the row",
        f"{TEST}; and judged:",
        f"{TEST}; and it still passes after the merge",
    ],
)
def test_a_search_of_the_repo_a_second_test_an_empty_judged_or_no_measure_still_warns(
    kitchen, proves
):
    assert warned(kitchen, brief(proves), "check") == [WARNED]


def examples():
    """The `Proves it:` lines the home's skill gives as examples of the line to write."""
    found = re.findall(r"^\s*Proves it: (.+)$", SKILL.read_text(), re.MULTILINE)
    return [line for line in found if not line.startswith("<")]


@pytest.mark.parametrize("kind", range(3), ids=["prints", "after the merge", "judged"])
def test_each_example_line_of_the_homes_skill_draws_no_warning(kitchen, kind):
    """The skill gives one line of each of the three kinds, so a skill that drops one fails here
    and no parametrize over an empty list skips it."""
    lines = examples()
    assert len(lines) == 3, lines
    assert warned(kitchen, brief(lines[kind]), "check") == []
