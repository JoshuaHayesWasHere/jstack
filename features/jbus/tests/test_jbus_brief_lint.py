"""`jbus queue add` and `jbus scout add` refuse a brief that would have its thread ask the user
mid-task, a brief that claims a shared doc outside a docs sweep, and a brief whose test copies an
incident's text word for word (`jbus.queue.conduct`). Like `test_jbus_queue.py`, the tests run the
real command against a faked T3 Code server, `gh` and `jmerge`, with small made-up briefs."""

import pytest

from jbus import queue
from test_jbus_kitchen import SAID, Kitchen
from test_jbus_queue import brief
from test_jbus_scout import request

ASKS = (
    "a crewmate or scout asks the user nothing in its own thread: put the question to the "
    "user as a gate through `jbus gate`"
)
DOCS = "docs go to a docs sweep, a row whose title names docs"
COPIED = "a test's text is small and made up, never an incident's text word for word"
INCIDENT = "the release branch went red at noon and the fix row never launched for flow"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def add(kitchen, text):
    return kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=text)


def refused(kitchen, text):
    """Return the faults `queue add` refused `text` for, and check that nothing was queued."""
    code, said = add(kitchen, text)
    assert code == 1, said
    first, *faults = said.splitlines()
    assert first.startswith("refused: alpha's brief has "), said
    assert not queue.brief_path(kitchen.state, "alpha").exists()
    return faults


@pytest.mark.parametrize(
    "line, phrase",
    [
        (
            "Decisions: if the base is unclear, the crewmate stops here and asks\n",
            "stops here and asks",
        ),
        ("Decisions: ask the user which port to take\n", "ask the user"),
        ("Decisions: settle the name in the crewmate's thread\n", "in the crewmate's thread"),
        ("Decisions: confirm with the user before the push\n", "confirm with the user"),
    ],
)
def test_a_brief_that_asks_the_user_mid_task_is_refused_naming_jbus_gate(kitchen, line, phrase):
    assert refused(kitchen, brief("alpha", line)) == [
        f'- brief asks the user mid-task ("{phrase}"): {ASKS}'
    ]


def test_a_brief_that_quotes_the_words_or_routes_through_a_gate_is_queued(kitchen):
    text = brief(
        "alpha",
        'Decisions: a brief that says "stops here and asks" is refused; `ask the user` is a '
        "phrase\nNotes: if the port is unclear, ask the user through `jbus gate`\n"
        "Do not touch: the ruleset (the home asks the user)\n",
    )
    assert add(kitchen, text)[0] == 0


@pytest.mark.parametrize(
    "old, new, label",
    [
        ("- it is done\n", "- it is done\n- the README names the new verb\n", "Done when"),
        ("Where: `src/alpha/`", "Where: `src/alpha/`, `CONTRIBUTING.md`", "Where"),
        ("Where: `src/alpha/`", "Where: `src/alpha/`, `docs/queue.md`", "Where"),
    ],
)
def test_a_brief_that_claims_a_shared_doc_is_refused(kitchen, old, new, label):
    text = brief("alpha").replace(old, new)
    assert text != brief("alpha")
    [fault] = refused(kitchen, text)
    assert fault.startswith(f"- brief's {label}: line claims a shared doc (")
    assert fault.endswith(DOCS)


def test_a_docs_sweep_row_and_a_features_own_docs_are_queued(kitchen):
    sweep = brief("alpha").replace("# alpha: a task", "# alpha: docs sweep for the queue verbs")
    sweep = sweep.replace("- it is done\n", "- the README names the new verb\n")
    assert add(kitchen, sweep)[0] == 0
    nested = brief("gamma").replace("- it is done\n", "- `features/gamma/README.md` names it\n")
    assert kitchen.main("queue", "add", "gamma", "--priority", "1", stdin=nested)[0] == 0
    own = brief("beta").replace(
        "Where: `src/beta/`", "Where: `src/beta/`, `features/jbus/docs/jbus.md`"
    )
    assert kitchen.main("queue", "add", "beta", "--priority", "1", stdin=own)[0] == 0


def test_a_brief_whose_test_copies_the_task_lines_quote_is_refused(kitchen):
    text = brief("alpha").replace('Task: "do alpha"', f'Task: Josh said "{INCIDENT}"')
    text = text.replace("- it is done\n", f"- a test feeds jbus the line {INCIDENT}\n")
    [fault] = refused(kitchen, text)
    assert fault.startswith(
        "- brief's Done when: line copies the Task line's quote word for word ("
    )
    assert fault.endswith(COPIED)


def test_a_small_made_up_row_and_a_short_quote_are_queued(kitchen):
    text = brief("alpha").replace('Task: "do alpha"', f'Task: Josh said "{INCIDENT}"')
    text = text.replace(
        "- it is done\n",
        "- a test feeds jbus a made-up row, release branch red at 12:00 for beta\n"
        "- a test checks the fix row never launched\n",
    )
    assert add(kitchen, text)[0] == 0


def test_a_scout_request_that_asks_the_user_is_refused_and_a_clean_one_stored(kitchen):
    asking = request("alpha", "Notes: if the answer is unclear, stop and ask the user\n")
    code, said = kitchen.main("scout", "add", "alpha", stdin=asking)
    assert code == 1
    assert said.splitlines() == [
        "refused: alpha's request has 1 fault, and nothing is stored",
        f'- request asks the user mid-task ("stop and ask"): {ASKS}',
    ]
    assert kitchen.main("scout", "add", "beta", stdin=request("beta"))[0] == 0


def test_a_redirect_whose_new_brief_claims_a_shared_doc_is_refused_before_it_is_written(kitchen):
    assert add(kitchen, brief("alpha"))[0] == 0
    stored = queue.brief_path(kitchen.state, "alpha").read_text()
    row = next(one for one in queue.load(kitchen.state) if one["slug"] == "alpha")
    name = row["item"]
    seen = kitchen.main("item", "show", name)[1].partition("last event: ")[2].split()[0]
    redirected = brief("alpha").replace("- it is done\n", "- the README names the new verb\n")
    argv = ("item", "steer", name, "redirect", "--seen", seen, "--by", "user", "--word", SAID)
    code, said = kitchen.main(*argv, stdin=redirected)
    assert code == 1, said
    assert said.startswith("refused: the new brief of alpha has faults, and nothing is written")
    assert "- brief's Done when: line claims a shared doc (README)" in said
    assert queue.brief_path(kitchen.state, "alpha").read_text() == stored
    assert kitchen.main("item", "show", name)[1].partition("last event: ")[2].split()[0] == seen
