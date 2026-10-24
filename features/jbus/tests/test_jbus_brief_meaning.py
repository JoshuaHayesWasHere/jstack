"""`jbus queue add` checks a brief when it queues it, and a go binds to what the brief asks for,
not to its wording. Like `test_jbus_queue.py`, the tests run the real command and the real pass
against a faked T3 Code server, `gh` and `jmerge`."""

import json

import pytest

from jbriefs import meaning, parse
from jbus import queue
from test_jbus_kitchen import Kitchen
from test_jbus_queue import gates, go, rows
from testing.paths import REPO

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
# alpha: A brief whose go is kept.
Home: mcp:another-home
Task: "Make the queue check a brief."
Done when:
- An approval holds through a wording-only edit.
- `make check` exits 0 in 3 minutes, or less
-   `jbus queue add` refuses an *incomplete* brief:
    one line per fault
Proves it: `make check` runs the tests above, and `jbus queue show` lists no re-asked row.
Size: M
Where: `src/jbus/queue.py`,   `src/jbriefs/`
Do not touch: `~/.config/`
Decisions: the user's words are under Task
Design: none, the Done when list pins it, and a note
Skills: principle-model-the-domain
Pull request: ask first
Review: none
Playbook: bug-fix
Judge: the user
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
        lambda text: REWORDED,
        lambda text: text.replace("wording-only", "wordnig-only"),
        lambda text: text.replace("Decisions: none yet", "Decisions: use the user's word 13bb"),
        lambda text: text.replace("Design: none, the", "Design: none, because the"),
        lambda text: text.replace(
            "Proves it: `make check`", "Proves it: the user, and `make check`"
        ),
        lambda text: text.replace("Review: review", "Review: none"),
        lambda text: text.replace("Playbook: feature", "Playbook: bug-fix"),
        lambda text: text.replace("Pull request: open one when done", "Pull request: ask first"),
        lambda text: text.replace("Decisions:", "Judge: the user\nDecisions:"),
        lambda text: text + "\n## Note\nAn aside the crewmate may use.\n",
    ],
    ids=[
        "every field that is not meaning edited at once, the rest re-formatted",
        "a typo in Done when",
        "decisions",
        "design",
        "proves it",
        "review",
        "playbook",
        "pull request",
        "a field the template does not name",
        "a note under a heading",
    ],
)
def test_an_approved_brief_edited_outside_its_meaning_stays_approved_and_launches(kitchen, edit):
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


def test_an_approved_brief_with_its_skills_edited_keeps_its_go(kitchen):
    skilled = APPROVED.replace("Decisions:", "Skills: blast-radius\nDecisions:")
    approved(kitchen, skilled)
    again = skilled.replace(
        "Skills: blast-radius", "Skills: principle-attack-the-premise, principle-prove-it-works"
    )
    code, said = add(kitchen, again)
    assert code == 0 and ", its go holds\n" in said, said
    assert meaning.same(meaning.meaning(skilled), meaning.meaning(again))
    kitchen.poll()
    assert gates(kitchen) == []
    assert len(kitchen.t3.launches) == 1


@pytest.mark.parametrize(
    "edit",
    [
        lambda text: text.replace("Proves it:", "- the go is printed by verify\nProves it:"),
        lambda text: text.replace("- an approval holds through a wording-only edit\n", ""),
        lambda text: text.replace("Size: M", "Size: L"),
        lambda text: text.replace("3 minutes", "5 minutes"),
        lambda text: text.replace("`src/jbriefs/`", "`src/jmerge/`"),
        lambda text: text.replace("`~/.config/`", "`~/.config/`, `docs/`"),
        lambda text: text.replace("holds through", "never holds through"),
        lambda text: text.replace(
            'Task: "make the queue check a brief"', 'Task: "check briefs when they are queued"'
        ),
        lambda text: text.replace("alpha: a brief whose go is kept", "alpha: another brief"),
    ],
    ids=[
        "a done-when line added",
        "a done-when line taken out",
        "size",
        "a number",
        "a path",
        "a do-not-touch path added",
        "a content word",
        "task, the goal",
        "the title",
    ],
)
def test_an_approved_brief_whose_goal_or_scope_changed_asks_again(kitchen, edit):
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
        "- brief's Proves it: line names the crewmate, the agent's own word (name a test, a "
        "command, a metric, a dataset, an external judge or the user)",
        "- brief's Size: line says medium (S, M, L or XL)",
        "- brief's Playbook: line names autopilot-full, which is not a crewmate's playbook (name a "
        "file in playbooks/, without its .md, or none)",
        "- brief has no Design: line (run /architect or say none, <why>)",
    ]
    assert not queue.brief_path(kitchen.state, "alpha").exists()


def test_queue_add_refuses_the_template_as_it_stands_with_a_fault_for_each_field(kitchen):
    template = (REPO / "features" / "jbriefs" / "templates" / "brief.md").read_text()
    code, said = add(kitchen, template)
    assert code == 1
    faults = said.splitlines()[1:]
    assert (
        said.splitlines()[0]
        == f"refused: alpha's brief has {len(faults)} faults, and nothing is queued"
    )
    named = [
        label
        for label in (*parse.REQUIRED, "Design")
        for fault in faults
        if f" {label}: line" in fault
    ]
    assert named == [*parse.REQUIRED, "Design"], said
    assert not queue.brief_path(kitchen.state, "alpha").exists()


def test_a_line_that_starts_with_a_less_than_sign_is_filled_in():
    text = APPROVED.replace(
        "- `make check` exits 0", "- <200 ms p95 on the bench\n- `make check` exits 0"
    )
    assert parse.faults(text) == []
    noted = APPROVED.replace(
        "Playbook: feature\n", "Playbook: feature\n<The line below is a note.>\n"
    )
    assert parse.faults(noted) == []


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


def old_go(kitchen, typed):
    """Give a go as jbus recorded it before #249: the row's `brief_sha` is the sha256 of the whole
    text, its `Home:` line included, and the go has no fingerprint, either a record without one or
    a `typed` string with no record at all."""
    approved(kitchen)
    table = json.loads((kitchen.state / "queue.json").read_text())
    if typed:
        table[0].pop("approval")
        table[0]["approved"] = "Josh said go, 2026-10-20"
    else:
        for column in ("brief_sha", "scope", "meaning"):
            table[0]["approval"].pop(column)
    table[0]["brief_sha"] = queue.sha(APPROVED)
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    code, said = kitchen.main("queue", "verify", "alpha")
    assert (code, json.loads(said)["holds"]) == (0, True)


MOVED = APPROVED.replace("Home: mcp:a-home", "Home: flow\nThread: mcp:a-crew")
LONGER = "- `make check` exits 0, in 5 minutes or less"


@pytest.mark.parametrize("typed", [False, True], ids=["a record", "a typed string"])
def test_an_old_go_is_bound_to_the_meaning_so_a_home_rewrite_and_a_later_edit_keep_it(
    kitchen, typed
):
    old_go(kitchen, typed)
    assert add(kitchen, MOVED)[0] == 0
    code, said = add(kitchen, REWORDED.replace("Home: mcp:another-home", "Home: flow"))
    assert code == 0 and ", its go holds\n" in said, said
    kitchen.poll()
    assert gates(kitchen) == []
    assert len(kitchen.t3.launches) == 1


@pytest.mark.parametrize("typed", [False, True], ids=["a record", "a typed string"])
def test_an_old_go_on_a_rewritten_home_still_asks_again_for_a_done_when_change_and_names_it(
    kitchen, typed
):
    old_go(kitchen, typed)
    assert add(kitchen, MOVED)[0] == 0
    longer = MOVED.replace("3 minutes", "5 minutes")
    code, said = add(kitchen, longer)
    assert code == 0 and "its go does not hold for it: approve it again" in said, said
    assert add(kitchen, longer)[0] == 0
    code, said = kitchen.main("queue", "verify", "alpha")
    assert (code, json.loads(said)["holds"]) == (1, False)
    kitchen.poll()
    assert gates(kitchen) == [f"condition alpha: brief changed after approval: Done when: {LONGER}"]
    assert kitchen.t3.launches == []


def test_a_gate_names_each_line_that_changed_and_a_line_taken_out(kitchen):
    approved(kitchen)
    edited = APPROVED.replace("Size: M", "Size: L").replace(
        "- an approval holds through a wording-only edit\n", ""
    )
    assert add(kitchen, edited.replace("3 minutes", "5 minutes"))[0] == 0
    kitchen.poll()
    assert gates(kitchen) == [
        "condition alpha: brief changed after approval: "
        f"Done when: {LONGER}; Done when: a line taken out; Size: L"
    ]


def test_the_fingerprint_keeps_paths_numbers_and_values_exact_and_sorts_the_rest():
    made = dict((label, lines) for label, lines in meaning.meaning(APPROVED))
    assert list(made) == [parse.TITLE, "Task", "Done when", "Where", "Do not touch", "Size"]
    assert made["Size"] == [["=m"]]
    assert ["=0", "=3", "=make check", "exits", "less", "minutes", "or"] in made["Done when"]
    assert made == dict(meaning.meaning(REWORDED))
    assert meaning.same(meaning.meaning(APPROVED), meaning.meaning(REWORDED))
    swapped = APPROVED.replace("an approval holds", "an approval must hold")
    assert not meaning.same(meaning.meaning(APPROVED), meaning.meaning(swapped))


def test_the_two_lists_hold_every_field_the_template_names_once():
    template = (REPO / "features" / "jbriefs" / "templates" / "brief.md").read_text()
    labels = [label for label, _ in parse.fields(template) if label not in ("", parse.REST)]
    assert labels
    assert not set(meaning.MEANING) & set(meaning.NOT_MEANING)
    assert set(labels) <= set(meaning.MEANING) | set(meaning.NOT_MEANING)
    assert set(meaning.MEANING) <= set(labels)
    assert [label for label, _ in meaning.meaning(template)] == list(meaning.MEANING)


def test_a_go_recorded_before_the_title_and_task_were_read_holds_for_them_and_for_no_other_scope(
    kitchen,
):
    approved(kitchen)
    table = json.loads((kitchen.state / "queue.json").read_text())
    record = table[0]["approval"]
    legacy = [
        [label, lines] for label, lines in record["meaning"] if label not in (parse.TITLE, "Task")
    ]
    legacy += [["Proves it", [["=x"]]], ["Review", [["=review"]]], ["Playbook", [["=feature"]]]]
    record["meaning"] = legacy
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    code, said = add(
        kitchen, REWORDED.replace('"Make the queue check a brief."', '"Another goal."')
    )
    assert code == 0 and ", its go holds\n" in said, said
    code, said = add(kitchen, APPROVED.replace("Size: M", "Size: L"))
    assert code == 0 and "its go does not hold for it: approve it again" in said, said


def test_a_lint_added_after_an_approval_neither_refuses_the_brief_nor_voids_its_go(
    kitchen, monkeypatch
):
    approved(kitchen)
    monkeypatch.setattr(
        parse,
        "CHECKS",
        (*parse.CHECKS, ("Where", lambda text: "brief's Where: names a file")),
    )
    assert parse.faults(APPROVED) == ["brief's Where: names a file"]
    code, said = add(kitchen, APPROVED)
    assert code == 0, said
    edited = APPROVED.replace("Decisions: none yet", "Decisions: none, said again")
    code, said = add(kitchen, edited)
    assert code == 0 and ", its go holds\n" in said, said
    kitchen.poll()
    assert gates(kitchen) == []
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]


def test_a_lint_added_later_still_refuses_a_brief_first_queued_after_it(kitchen, monkeypatch):
    monkeypatch.setattr(
        parse,
        "CHECKS",
        (*parse.CHECKS, ("Where", lambda text: "brief's Where: names a file")),
    )
    code, said = add(kitchen, APPROVED)
    assert code == 1 and "- brief's Where: names a file" in said, said


def test_an_edit_to_an_approved_brief_is_refused_for_the_fault_it_brings_and_not_for_the_old(
    kitchen, monkeypatch
):
    approved(kitchen)
    monkeypatch.setattr(
        parse,
        "CHECKS",
        (*parse.CHECKS, ("Where", lambda text: "brief's Where: names a file")),
    )
    broken = APPROVED.replace("Design: none, the Done when list pins it", "Design: TBD")
    code, said = add(kitchen, broken)
    assert code == 1, said
    assert said.splitlines()[1:] == [f"- {parse.NO_DESIGN}"], said


def test_queue_show_says_which_rows_were_grandfathered_and_which_are_re_asked(kitchen, monkeypatch):
    approved(kitchen)
    assert "grandfathered" not in kitchen.main("queue", "show")[1]
    monkeypatch.setattr(
        parse,
        "CHECKS",
        (*parse.CHECKS, ("Where", lambda text: "brief's Where: names a file")),
    )
    code, said = kitchen.main("queue", "show")
    assert code == 0 and "re-asked" not in said
    assert said.endswith(
        "\ngrandfathered, approved before a lint that refuses the brief now; the go stands:\n"
        "- alpha: brief's Where: names a file\n"
    ), said
    code, said = add(kitchen, APPROVED.replace("Size: M", "Size: L"))
    assert code == 1, said
    text = queue.brief_path(kitchen.state, "alpha")
    text.write_text(APPROVED.replace("Size: M", "Size: L"))
    assert (
        "re-asked, the go does not hold for the stored brief: alpha\n"
        in (kitchen.main("queue", "show")[1])
    )
