"""A pass approves a follow-up of approved work by itself: no home approves it, and nothing of it
reaches the user.

A follow-up is a row that names its parent P and is one of three kinds (`queue.KINDS`): a
`cleanup-P`, a fix row that jbus filed from P (`main-red-`, `train-red-`, `workflow-red-`, with a
`Follows: P` line), or a sync of a train that the home's `integration` file names (its slug says
`sync-main`, its pull request goes against the train, and it has a `Follows: P` line). Its ground is
P's go, which holds, and the record names P and P's go. The follow-up rule is known by what it says,
never by its number in a home's `standing.md`, so these tests keep a `follow-rule` file whose number
no standing rule has, and no `standing.md` at all. Every row here is queued as a filer queues it,
with `queue.add` and no approval, and the real pass runs against the kitchen's fakes.
"""

import pytest

import jbus
from jbus import queue
from test_jbus_kitchen import SAID, Kitchen
from test_jbus_queue import brief, rows, sha12

TRAIN = "train/demo"
RED, TRAIN_RED, SIDE_RED = "main-red-" + "a" * 12, "train-red-demo-" + "b" * 12, "workflow-red-x-c"
SYNC = "demo-sync-main-1"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "follow-rule").write_text("9\n")
    (made.home / "integration").write_text(f"{TRAIN}\n")
    made.word()
    yield made
    made.close()


def text(slug, parent="", against="", wider=False):
    """Return a brief that follows `parent`, whose pull request goes against `against`, and that
    asks for one thing more where it is `wider`."""
    made = brief(slug, f"Follows: {parent}\n" if parent else "")
    if against:
        made = made.replace("open one when done", f"open one against {against} when done")
    return made.replace("- it is done\n", "- it is done\n- and more\n") if wider else made


def filed(kitchen, slug, parent="", against="", wider=False):
    """Queue a row as a filer does: no approval, and no home in the loop."""
    queue.add(kitchen.state, slug, 0, [], text(slug, parent, against, wider))


def approve(kitchen, slug):
    sha = sha12((kitchen.state / "briefs" / f"{slug}.md").read_text())
    code, said = kitchen.main("queue", "approve", slug, "--word", SAID, "--sha", sha)
    assert code == 0, said


def went(kitchen, slug):
    """Return the parent and the basis of the row's go, or nothing for a row with none."""
    made = rows(kitchen)[slug].get("approval") or {}
    return (
        (made.get("follows", ""), made.get("basis", "")) if rows(kitchen)[slug]["approved"] else ()
    )


def asked_the_user(kitchen):
    """Return every slug that a decision, a word or a question of the pass names."""
    named = {line.split(":")[0].split()[-1] for line in kitchen.lines("decision")}
    waits = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    return named | {one["key"].partition(":")[2] for one in waits}


def test_each_kind_of_follow_up_is_approved_on_a_pass_and_nothing_reaches_the_user(kitchen):
    filed(kitchen, "alpha")
    approve(kitchen, "alpha")
    filed(kitchen, "unsaid")
    kinds = {
        "cleanup-alpha": ("", ""),
        RED: ("alpha", ""),
        TRAIN_RED: ("alpha", ""),
        SIDE_RED: ("alpha", ""),
        SYNC: ("alpha", TRAIN),
    }
    for slug, (parent, against) in kinds.items():
        filed(kitchen, slug, parent, against)
    left = {
        "cleanup-unsaid": ("", ""),
        "delta": ("", ""),
        "beta": ("alpha", ""),
        "other-sync-main-2": ("alpha", "elsewhere"),
        "main-red-" + "d" * 12: ("", ""),
    }
    for slug, (parent, against) in left.items():
        filed(kitchen, slug, parent, against)
    assert all(went(kitchen, slug) == () for slug in kinds)
    kitchen.quiet()
    for slug in kinds:
        assert went(kitchen, slug) == ("alpha", queue.RULE), slug
        made = rows(kitchen)[slug]["approval"]
        assert made["ref"] == queue.FOLLOW_REF
        assert made["words"].startswith(queue.FOLLOW_RULE)
        assert rows(kitchen)["alpha"]["approved"] in made["words"]
        assert made["ran_by"]["by"] == "jbus"
    assert all(went(kitchen, slug) == () for slug in left)
    kitchen.poll()
    assert not asked_the_user(kitchen) & set(kinds)
    assert asked_the_user(kitchen) >= set(left) - {"cleanup-unsaid"}


def test_a_follow_up_of_a_follow_up_is_approved_on_the_same_pass(kitchen):
    """The train sync after a red main's fix: the fix follows the merge that turned main red, and
    the sync follows the fix. A chain goes back to the user's word one go at a time."""
    filed(kitchen, "alpha")
    approve(kitchen, "alpha")
    filed(kitchen, RED, "alpha")
    filed(kitchen, SYNC, RED, TRAIN)
    filed(kitchen, f"cleanup-{SYNC}")
    kitchen.quiet()
    assert went(kitchen, RED) == ("alpha", queue.RULE)
    assert went(kitchen, SYNC) == (RED, queue.RULE)
    assert went(kitchen, f"cleanup-{SYNC}") == (SYNC, queue.RULE)


def test_a_hold_of_the_root_takes_back_the_whole_chain(kitchen):
    filed(kitchen, "alpha")
    approve(kitchen, "alpha")
    filed(kitchen, RED, "alpha")
    filed(kitchen, SYNC, RED, TRAIN)
    kitchen.quiet()
    code, said = kitchen.main("queue", "hold", "alpha")
    assert code == 0, said
    assert said.splitlines()[0].startswith(f"held alpha, and {SYNC}, {RED} with it")
    kitchen.poll()
    assert (went(kitchen, RED), went(kitchen, SYNC)) == ((), ())


def test_an_edit_voids_the_go_and_the_pass_approves_the_new_brief_only_for_the_same_parent(
    kitchen,
):
    for parent in ("alpha", "gamma"):
        filed(kitchen, parent)
        approve(kitchen, parent)
    filed(kitchen, RED, "alpha")
    filed(kitchen, TRAIN_RED, "alpha")
    kitchen.quiet()
    filed(kitchen, RED, "alpha", wider=True)
    moved = text(TRAIN_RED, "gamma", wider=True)
    queue.add(kitchen.state, TRAIN_RED, 0, [], moved)
    stored = queue.brief(kitchen.state, RED)
    assert not queue.approved_text(rows(kitchen)[RED], stored)
    kitchen.poll()
    assert went(kitchen, RED) == ("alpha", queue.RULE)
    assert queue.approved_text(rows(kitchen)[RED], stored)
    assert not queue.approved_text(rows(kitchen)[TRAIN_RED], moved)


def test_a_row_the_users_word_approved_waits_for_the_user_after_an_edit_voids_it(kitchen):
    filed(kitchen, "alpha")
    approve(kitchen, "alpha")
    filed(kitchen, "cleanup-alpha")
    approve(kitchen, "cleanup-alpha")
    wider = text("cleanup-alpha", wider=True)
    queue.add(kitchen.state, "cleanup-alpha", 0, [], wider)
    kitchen.quiet()
    assert not queue.approved_text(rows(kitchen)["cleanup-alpha"], wider)


def test_queue_add_approves_a_follow_up_whatever_number_the_follow_rule_file_holds(kitchen):
    """A home's standing rules were renumbered: the file says 9, no rule 9 exists, and
    standing.md is gone. The follow-up is approved all the same, in the write that queues it."""
    filed(kitchen, "alpha")
    approve(kitchen, "alpha")
    argv = ("queue", "add", "cleanup-alpha", "--priority", "1")
    code, said = kitchen.main(*argv, stdin=brief("cleanup-alpha"))
    assert code == 0, said
    assert said.startswith("added cleanup-alpha")
    assert "approved cleanup-alpha" in said
    assert went(kitchen, "cleanup-alpha") == ("alpha", queue.RULE)
