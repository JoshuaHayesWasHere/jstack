"""A brief is checked when it is queued, and a go is bound to what the brief asks for, not
to its wording. Run as `tests/test_jbus_queue.py` runs: the real command and the real pass,
against a faked T3 Code server, `gh` and `jmerge`."""

import json
from pathlib import Path

import pytest

from jbriefs import meaning, parse
from jbus import queue
from test_jbus_kitchen import Kitchen
from test_jbus_queue import gates, go, rows

APPROVED = """\
# alpha: a brief whose go is kept
Home: mcp:a-home
Task: "make the queue check a brief"
Done when:
- `jbus queue add` refuses an incomplete brief, with one line per fault
- an approval holds through a wording-only edit
- `make check` exits 0, in 3 minutes or less
Proves it: `make check` runs the tests above
Size: M
Where: `src/jbus/queue.py`, `src/jbriefs/`
Do not touch: `~/.config/`
Decisions: none yet
Design: none, the Done when list pins it
Pull request: open one when done
Review: review
Playbook: feature
"""

REWORDED = """\
# alpha: the brief, its title said again
Home: mcp:another-home
Task: "Make the queue check every brief before it is queued, in the user's words."
Done when:
- An approval holds through a wording-only edit.
- `make check` exits 0 in 3 minutes, or less
-   `jbus queue add` refuses an *incomplete* brief:
    one line per fault
Proves it: `make check` runs the tests above.
Size: M
Where: `src/jbus/queue.py`,   `src/jbriefs/`
Do not touch: `~/.config/`
Decisions: the user's words are under Task
Design: none, the Done when list pins it
Pull request: open one when done
Review: review
Playbook: feature
"""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def add(kitchen, text, slug="alpha"):
    return kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)


def approved(kitchen, text=APPROVED):
    assert add(kitchen, text)[0] == 0
    assert go(kitchen, "alpha")[0] == 0


@pytest.mark.parametrize(
    "edit",
    [
        lambda text: text.replace(
            'Task: "make the queue check a brief"', 'Task: "check briefs when they are queued"'
        ),
        lambda text: REWORDED,
        lambda text: text.replace("wording-only", "wordnig-only"),
    ],
    ids=["task", "done when reordered, re-wrapped and re-punctuated", "a typo"],
)
def test_an_approved_brief_edited_only_in_its_wording_stays_approved_and_launches(kitchen, edit):
    approved(kitchen)
    again = edit(APPROVED)
    assert again != APPROVED
    code, said = add(kitchen, again)
    assert code == 0 and ", its go holds\n" in said, said
    kitchen.poll()
    assert gates(kitchen) == []
    (launch,) = kitchen.t3.launches
    assert launch["title"] == "crew: alpha"
    assert launch["message"] == f"/crew alpha\n\n{queue.body(again)}"


@pytest.mark.parametrize(
    "edit",
    [
        lambda text: text.replace("Proves it:", "- the go is printed by verify\nProves it:"),
        lambda text: text.replace("- an approval holds through a wording-only edit\n", ""),
        lambda text: text.replace("Size: M", "Size: L"),
        lambda text: text.replace("Review: review", "Review: none"),
        lambda text: text.replace("3 minutes", "5 minutes"),
        lambda text: text.replace("`src/jbriefs/`", "`src/jmerge/`"),
        lambda text: text.replace("holds through", "never holds through"),
        lambda text: text.replace("Decisions:", "Judge: the user\nDecisions:"),
    ],
    ids=[
        "a done-when line added",
        "a done-when line taken out",
        "size",
        "review",
        "a number",
        "a path",
        "a content word",
        "a field the template does not name",
    ],
)
def test_an_approved_brief_whose_scope_changed_asks_again(kitchen, edit):
    approved(kitchen)
    again = edit(APPROVED)
    assert again != APPROVED
    code, said = add(kitchen, again)
    assert code == 0 and "its go does not hold for it: approve it again" in said, said
    kitchen.poll()
    assert gates(kitchen) == ["condition alpha: brief changed after approval"]
    assert kitchen.t3.launches == []
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll()
    assert len(kitchen.t3.launches) == 1


@pytest.mark.parametrize(
    "line, fault",
    [
        ("Size: M\n", "brief has no Size: line (S, M, L or XL)"),
        (
            "Playbook: feature\n",
            "brief has no Playbook: line",
        ),
        ("Proves it: `make check` runs the tests above\n", "brief has no Proves it: line"),
    ],
    ids=["size", "playbook", "proves it"],
)
def test_queue_add_refuses_a_brief_missing_a_field_and_queues_nothing(kitchen, line, fault):
    assert line in APPROVED
    code, said = add(kitchen, APPROVED.replace(line, ""))
    assert (code, said) == (
        1,
        f"refused: alpha's brief has 1 fault, and nothing is queued\n- {fault}\n",
    )
    assert not (kitchen.state / "queue.json").exists() or rows(kitchen) == {}
    assert not queue.brief_path(kitchen.state, "alpha").exists()


def test_queue_add_says_every_fault_one_line_each(kitchen):
    text = (
        "# alpha: a brief\nTask: <the request>\nDone when:\nProves it: the crewmate reviews it\n"
        "Size: medium\nWhere: `src/`\nPull request: open one when done\nReview: review\n"
        "Playbook: autopilot-full\nDesign: TBD\n"
    )
    code, said = add(kitchen, text)
    assert code == 1
    assert said.splitlines() == [
        "refused: alpha's brief has 6 faults, and nothing is queued",
        "- brief's Task: line is the template's own text",
        "- brief's Done when: line is empty",
        "- brief has no Design: line (run /architect or say none, <why>)",
        "- brief's Proves it: line names the crewmate, the agent's own word (name a test, a "
        "command, a metric, a dataset, an external judge or the user)",
        "- brief's Size: line says medium (S, M, L or XL)",
        "- brief's Playbook: line names autopilot-full, which is not a crewmate's playbook (name a "
        "file in playbooks/, without its .md, or none)",
    ]
    assert not queue.brief_path(kitchen.state, "alpha").exists()


def test_queue_add_refuses_the_template_as_it_stands_with_a_fault_for_each_field(kitchen):
    template = (Path(__file__).parents[1] / "templates" / "brief.md").read_text()
    code, said = add(kitchen, template)
    assert code == 1
    faults = said.splitlines()[1:]
    for label in parse.REQUIRED:
        assert any(f" {label}: line" in fault for fault in faults), (label, said)
    assert not queue.brief_path(kitchen.state, "alpha").exists()


def test_a_negation_made_by_a_contraction_asks_again(kitchen):
    approved(kitchen)
    again = APPROVED.replace("an approval holds", "an approval shouldn't hold")
    swapped = APPROVED.replace("an approval holds", "an approval should hold")
    assert not meaning.same(meaning.meaning(swapped), meaning.meaning(again))
    assert "its go does not hold for it: approve it again" in add(kitchen, again)[1]


def test_a_batch_whose_add_has_a_faulty_brief_applies_nothing(kitchen):
    approved(kitchen)
    before = (kitchen.state / "queue.json").read_text()
    text = "hold alpha\nadd beta --priority 2\n--- brief beta\n# beta: a brief\n--- end\n"
    code, said = kitchen.main("queue", "apply", stdin=text)
    assert code == 1
    assert said.startswith(
        "refused: line 2: beta's brief has 9 faults, and nothing is queued, and nothing in the "
        "batch was applied\n- brief has no Task: line\n"
    ), said
    assert (kitchen.state / "queue.json").read_text() == before


def test_verify_prints_the_record_and_whether_the_go_holds_for_a_brief(kitchen, tmp_path):
    approved(kitchen)
    code, said = kitchen.main("queue", "verify", "alpha")
    assert code == 0
    shown = json.loads(said)
    row = rows(kitchen)["alpha"]
    record = row["approval"]
    stored = queue.brief_sha(APPROVED)
    assert (shown["slug"], shown["holds"], shown["brief_sha"]) == ("alpha", True, stored)
    assert shown["approval"] == record
    assert (record["basis"], record["ref"], record["brief_sha"]) == ("word", "said-by-user", stored)
    assert record["scope"] == meaning.fingerprint(record["meaning"])
    assert shown["brief"]["brief_sha"] == stored and shown["brief"]["scope"] == record["scope"]

    held = tmp_path / "held.md"
    held.write_text(REWORDED)
    code, said = kitchen.main("queue", "verify", "alpha", "--brief", str(held))
    shown = json.loads(said)
    assert (code, shown["holds"], shown["approval"]) == (0, True, record)
    assert shown["brief"]["brief_sha"] == queue.brief_sha(REWORDED) != stored

    held.write_text(APPROVED.replace("Size: M", "Size: L"))
    code, said = kitchen.main("queue", "verify", "alpha", "--brief", str(held))
    assert (code, json.loads(said)["holds"]) == (1, False)
    assert kitchen.main("queue", "verify", "nope") == (1, "refused: the queue has no row nope\n")


def test_a_row_approved_before_the_fingerprint_is_held_to_its_sha(kitchen):
    approved(kitchen)
    table = json.loads((kitchen.state / "queue.json").read_text())
    for column in ("brief_sha", "scope", "meaning"):
        table[0]["approval"].pop(column)
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    code, said = kitchen.main("queue", "verify", "alpha")
    assert (code, json.loads(said)["holds"]) == (0, True)
    assert add(kitchen, APPROVED.replace("a brief", "every brief"))[0] == 0
    kitchen.poll()
    assert gates(kitchen) == ["condition alpha: brief changed after approval"]


def test_the_fingerprint_keeps_paths_numbers_and_values_exact_and_sorts_the_rest():
    made = dict((label, lines) for label, lines in meaning.meaning(APPROVED))
    assert list(made) == [
        "Done when",
        "Proves it",
        "Size",
        "Where",
        "Do not touch",
        "Pull request",
        "Review",
        "Playbook",
    ]
    assert made["Size"] == [["=m"]]
    assert ["=0", "=3", "=make check", "exits", "less", "minutes", "or"] in made["Done when"]
    assert made == dict(meaning.meaning(REWORDED))
    assert meaning.same(meaning.meaning(APPROVED), meaning.meaning(REWORDED))
    swapped = APPROVED.replace("an approval holds", "an approval must hold")
    assert not meaning.same(meaning.meaning(APPROVED), meaning.meaning(swapped))
