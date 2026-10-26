"""Every gate carries a default that is the recommended option, and the thread acts on it at once.
The first pass that sees a question closes it with that default, unless its gate holds. A gate
holds when its default is irreversible or slow to revert, and it names its fail-safe, and it
waits for the user however long.

The tests run the real `jbus gate`, `jbus answer` and pass against the faked T3 Code server of
`test_jbus_kitchen`, with the clock of `jbus gate` held at `NOW`.
"""

import json
from datetime import datetime, timedelta

import pytest

import jbus
from jbus import Refused, questions
from test_jbus_kitchen import NOW, Kitchen

THREAD = "mcp:crew-alpha"
AT = "2026-10-12 19:30 ET"
LINES = (
    "## Gate <n>: tea or coffee?\nStatus: open\nAsked by: alpha, thread mcp:a-thread\n"
    "Default: made tea\nBuilt on it: the cups\nUndo: pour it out\n"
)
OPTIONS = "Option: tea (default, recommended): the cups stay\nOption: coffee: they go\n"
HOLDS = (
    "deletes data",
    "rewrites history",
    "spends money",
    "touches prod or real users",
    "changes access or secrets",
    "publishes",
)
SAFE = "Fail-safe: dry-run lists the 3 branches that go, bundle at ~/b.bundle, then hold\n"


class Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.brief("alpha", f"Thread: {THREAD}\n")
    made.quiet()
    monkeypatch.setattr(questions, "datetime", Frozen)
    yield made
    made.close()


def gate(kitchen, lines=LINES + OPTIONS):
    return kitchen.main("gate", "alpha", stdin=lines)


def record(kitchen):
    (one,) = json.loads((kitchen.state / "questions.json").read_text())["records"]
    return one


def waiting(kitchen):
    kept = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    return [one["key"] for one in kept if one["kind"] == "gate"]


def test_a_gate_with_no_default_is_refused(kitchen):
    code, said = gate(kitchen, LINES.replace("Default: made tea\n", "") + OPTIONS)
    assert (code, said) == (1, "not sent: the gate has no Default: line that is filled in.\n")
    assert not (kitchen.state / "questions.json").exists()


@pytest.mark.parametrize(
    ("options", "why"),
    [
        (
            "Option: tea (default): the cups stay\nOption: coffee (recommended): they go\n",
            "the option marked (recommended) is coffee, and the default that was taken is tea",
        ),
        (
            "Option: tea (default): the cups stay\nOption: coffee: they go\n",
            "no option is marked (recommended), and the default that was taken is the one",
        ),
    ],
)
def test_a_gate_whose_default_is_not_the_recommended_option_is_refused(kitchen, options, why):
    code, said = gate(kitchen, LINES + options)
    assert (code, said.startswith(f"not sent: {why}")) == (1, True), said
    assert not (kitchen.state / "questions.json").exists()


@pytest.mark.parametrize("case", HOLDS)
def test_a_gate_that_holds_names_one_case_from_the_table_and_its_fail_safe(kitchen, case):
    lines = LINES + f"Holds: {case}\n" + SAFE + OPTIONS
    assert gate(kitchen, lines) == (0, "queued: question 1\n")
    one = record(kitchen)
    assert (one["holds"], one["fail_safe"]) == (case, SAFE[len("Fail-safe: ") :].strip())


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("Holds: deletes data\n", "the gate holds (deletes data) and has no Fail-safe: line"),
        (
            "Holds: deletes data\nFail-safe: <the dry-run>\n",
            "the gate holds (deletes data) and has no Fail-safe: line",
        ),
        ("Holds: it is late\n" + SAFE, 'the Holds: line says "it is late"'),
        ("Holds: <deletes data | publishes>\n" + SAFE, 'the Holds: line says "<deletes data'),
        ("Holds:\n" + SAFE, 'the Holds: line says ""'),
        ("Holds: spends money\nHolds: publishes\n" + SAFE, "the gate has two Holds: lines"),
        (SAFE, "the gate has a Fail-safe: line and no Holds: line"),
    ],
)
def test_a_holds_line_with_no_fail_safe_or_an_unknown_case_is_refused(kitchen, line, why):
    code, said = gate(kitchen, LINES + line + OPTIONS)
    assert (code, said.startswith(f"not sent: {why}")) == (1, True), said
    assert not (kitchen.state / "questions.json").exists()


def test_a_waiting_question_says_whether_it_was_acted_on_or_holds(kitchen):
    gate(kitchen)
    gate(
        kitchen,
        LINES.replace("tea or coffee?", "drop the branches?")
        + "Holds: deletes data\n"
        + SAFE
        + OPTIONS,
    )
    shown = {
        one["key"]: (one["acted"], one["holds"], one["fail_safe"])
        for one in map(questions.item, questions.load(kitchen.state))
    }
    assert shown == {
        "gate:q1": (True, "", ""),
        "gate:q2": (False, "deletes data", SAFE[len("Fail-safe: ") :].strip()),
    }


def test_a_plain_gate_asked_this_pass_settles_on_its_default_at_once(kitchen):
    gate(kitchen)
    assert record(kitchen)["holds"] == ""

    said = kitchen.poll(NOW)
    answer = record(kitchen)["answer"]
    assert answer == {
        "words": "default",
        "by": "jbus",
        "at": "2026-10-12T15:00:00+00:00",
        "where": "settled at once",
        "keeps": True,
        "told": "",
        "closed_by": "silence",
        "ref": "",
        "said_in": "",
        "checked": False,
    }
    assert waiting(kitchen) == []
    line = "note alpha: question 1 closed with its default, settled at once"
    assert line in said
    assert kitchen.lines("note") == [line]
    kitchen.poll(NOW + timedelta(hours=1))
    assert kitchen.t3.messages == {}
    assert kitchen.lines("note") == [line]
    with pytest.raises(Refused, match="jbus has no word of it"):
        questions.basis(kitchen.state, "1")
    assert gate(kitchen) == (
        0,
        "already answered: question 1: closed with its default by jbus, "
        "2026-10-12T15:00:00+00:00: settled at once\n",
    )


@pytest.mark.parametrize("case", HOLDS)
def test_a_gate_that_holds_is_open_after_days(kitchen, case):
    gate(kitchen, LINES + f"Holds: {case}\n" + SAFE + OPTIONS)
    kitchen.poll(NOW)
    kitchen.poll(NOW + timedelta(days=5))
    assert record(kitchen)["answer"] is None
    assert waiting(kitchen) == ["gate:q1"]


def test_a_later_answer_that_differs_is_taken_and_carried_to_the_thread(kitchen):
    gate(kitchen)
    kitchen.poll(NOW)
    code, said = kitchen.main("answer", "1", "--by", "user", "--at", AT, "--differs", "coffee")
    assert (code, said.startswith('answered: question 1: "coffee", by user')) == (0, True), said
    answer = record(kitchen)["answer"]
    assert (answer["closed_by"], answer["words"], answer["keeps"]) == (
        "jbus answer",
        "coffee",
        False,
    )
    kitchen.poll(NOW + timedelta(hours=3))
    (sent,) = kitchen.t3.messages.values()
    assert (sent["threadId"], sent["clientRequestId"]) == (THREAD, "answer|alpha|1")
    assert '"coffee"' in sent["message"]
    code, said = kitchen.main("answer", "1", "--by", "user", "--at", AT, "--differs", "water")
    assert (code, said.startswith("refused: question 1 was answered already")) == (1, True)


def test_a_home_that_answered_in_its_gates_file_replaces_a_close_by_silence(kitchen):
    gate(kitchen)
    kitchen.poll(NOW)
    status = "answered 2026-10-12: coffee"
    (kitchen.home / "gates.md").write_text(
        LINES.replace("<n>", "3").replace("open", status) + OPTIONS
    )
    kitchen.poll(NOW + timedelta(hours=3))
    answer = record(kitchen)["answer"]
    assert (answer["closed_by"], answer["words"]) == ("gates.md", status)


def test_a_gate_that_holds_answered_with_its_default_goes_to_its_thread_as_a_go_ahead(kitchen):
    gate(kitchen, LINES + "Holds: deletes data\n" + SAFE + OPTIONS)
    code, said = kitchen.main("answer", "1", "--by", "user", "--at", AT, "--default", "yes")
    assert (code, said.endswith("the next pass tells alpha's thread\n")) == (0, True), said
    kitchen.poll(NOW + timedelta(minutes=10))
    kitchen.poll(NOW + timedelta(minutes=20))
    (sent,) = kitchen.t3.messages.values()
    assert (sent["threadId"], sent["clientRequestId"]) == (THREAD, "answer|alpha|1")
    assert sent["message"].startswith(
        "jbus: user answered question 1 (tea or coffee?) with the default (made tea), which "
        "held for the answer (deletes data)."
    )
    assert "Go ahead with the default now" in sent["message"]


def test_a_plain_gate_answered_with_its_default_sends_nothing(kitchen):
    gate(kitchen)
    kitchen.main("answer", "1", "--by", "user", "--at", AT, "--default", "yes")
    kitchen.poll(NOW + timedelta(minutes=10))
    assert kitchen.t3.messages == {}


def test_a_links_conflict_asks_its_home_and_is_never_closed_by_silence(kitchen):
    asked = "alpha: https://example.test/pull/7 has a conflict, and it is a link of a stack"
    gate(kitchen, (LINES + OPTIONS).replace("tea or coffee?", asked))
    kitchen.poll(NOW + timedelta(hours=48))
    assert record(kitchen)["answer"] is None


def test_the_line_on_the_list_says_acted_on_or_what_holds_with_its_fail_safe(kitchen):
    gate(kitchen)
    held = LINES.replace("tea or coffee?", "drop the branches?") + "Holds: deletes data\n"
    gate(kitchen, held + SAFE + OPTIONS)
    lines = {one["key"]: one["line"] for one in map(questions.item, questions.load(kitchen.state))}
    assert lines == {
        "gate:q1": "question 1: tea or coffee? Its default is acted on already, and stands "
        "unless you stop it.",
        "gate:q2": "question 2: drop the branches? It holds (deletes data) for your answer, "
        "with its fail-safe: dry-run lists the 3 branches that go, bundle at ~/b.bundle, then "
        "hold.",
    }
    kitchen.poll(NOW)
    assert waiting(kitchen) == ["gate:q2"]


def test_a_gate_that_holds_answered_otherwise_tells_its_thread_not_to_take_the_default(kitchen):
    gate(kitchen, LINES + "Holds: deletes data\n" + SAFE + OPTIONS)
    kitchen.main("answer", "1", "--by", "user", "--at", AT, "--differs", "keep", "them")
    kitchen.poll(NOW + timedelta(minutes=10))
    (sent,) = kitchen.t3.messages.values()
    assert sent["message"] == (
        "jbus: user answered question 1 (tea or coffee?), which held for the answer (deletes "
        f'data), and the answer is not the default (made tea). The words, {AT}: "keep them". '
        "Do not take the default: do what the answer says, and add one line to the last "
        "Result or Report saying what you did. "
        "End your turn only once no check or proof you started runs in your "
        "worktree: wait for one that runs, in this turn."
    )
