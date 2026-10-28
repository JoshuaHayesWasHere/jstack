"""A question for the user is one numbered record in jbus. `jbus gate` writes it, and it waits on
the user until `jbus answer` closes it. A pass delivers an answer that is not the default to the
thread that asked.

The tests run the real commands and the real pass against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import datetime, timedelta

import pytest

import jbus
from jbus import digest, questions, wake
from jbus.view import state as view_state
from test_jbus_kitchen import GATE, NOW, OPTIONS, Kitchen

AT = "2026-10-12 11:30 ET"
ACTED = " Its default is acted on already, and stands unless you stop it."
SAID = ("--by", "user", "--at", AT)
THREAD = "mcp:crew-alpha"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.brief("alpha", f"Thread: {THREAD}\n")
    made.quiet()
    yield made
    made.close()


def gate(asked="tea or coffee?", slug="alpha", n="<n>", status="open"):
    return GATE.format(n=n, asked=asked, status=status, slug=slug)


def ask(kitchen, asked="tea or coffee?", slug="alpha"):
    return kitchen.main("gate", slug, stdin=gate(asked, slug))


def answer(kitchen, number, *words, default=False):
    return kitchen.main(
        "answer", str(number), *SAID, "--default" if default else "--differs", *words
    )


def records(kitchen):
    return json.loads((kitchen.state / "questions.json").read_text())


def listed(kitchen):
    """Return the gates on the list that the last pass left."""
    kept = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    return [one for one in kept if one["kind"] == "gate"]


def shown(kitchen):
    """Return the state that the view gives for the project, read now."""
    sources = view_state.Sources(kitchen.state_dir, kitchen.root / "home")
    return view_state.build(sources, "demo", NOW, lambda _: {})


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def test_a_piped_gate_is_a_record_with_a_number_and_every_field_of_its_shape(kitchen):
    assert ask(kitchen) == (0, "queued: question 1\n")
    kept = records(kitchen)
    (one,) = kept["records"]
    assert datetime.fromisoformat(one.pop("asked_at")).tzinfo is not None
    assert kept["next"] == 2
    assert one == {
        "number": 1,
        "slug": "alpha",
        "thread": THREAD,
        "question": "tea or coffee?",
        "default": "the first one",
        "built_on": "nothing",
        "undo": "pick the other",
        "answer": None,
        "proposed": "",
        "holds": "",
        "fail_safe": "",
        "context": "",
        "options": [
            {
                "name": "the first one",
                "follows": "nothing changes",
                "default": True,
                "recommended": True,
            },
            {
                "name": "the other",
                "follows": "one more cup",
                "default": False,
                "recommended": False,
            },
        ],
    }


def test_a_question_waits_on_the_user_from_the_next_pass_with_its_default(kitchen):
    ask(kitchen)
    kitchen.poll()
    (one,) = listed(kitchen)
    wanted = {
        "kind": "gate",
        "key": "gate:q1",
        "line": "question 1: tea or coffee?" + ACTED,
        "source": "jbus",
        "number": "1",
        "question": "tea or coffee?",
        "default": "the first one",
        "slug": "alpha",
        "home": "",
    }
    assert {name: one[name] for name in wanted} == wanted
    code, out = kitchen.main("digest", "--json")
    (told,) = [o for o in json.loads(out)["projects"]["demo"]["waiting"] if o["kind"] == "gate"]
    assert (code, told["question"], told["default"]) == (0, "tea or coffee?", "the first one")
    (seen,) = [one for one in shown(kitchen)["waiting"] if one["kind"] == "gate"]
    assert (seen["number"], seen["question"], seen["default"], seen["slug"]) == (
        "1",
        "tea or coffee?",
        "the first one",
        "alpha",
    )


def test_the_gate_event_names_the_number_and_its_text_is_the_lines_as_sent(kitchen):
    ask(kitchen)
    (event,) = kitchen.events("gate")
    assert event["line"] == "gate alpha: question 1: tea or coffee?"
    assert event["text"] == gate().strip()


def test_a_number_is_never_used_twice_and_the_same_question_is_the_same_record(kitchen):
    assert ask(kitchen, "tea or coffee?") == (0, "queued: question 1\n")
    assert ask(kitchen, "milk?") == (0, "queued: question 2\n")
    assert answer(kitchen, 2, "no milk")[0] == 0
    assert ask(kitchen, "sugar?") == (0, "queued: question 3\n")
    assert ask(kitchen, "tea or coffee?") == (0, "already sent: question 1\n")
    assert ask(kitchen, "milk?") == (
        0,
        f'already answered: question 2: "no milk", by user, {AT}, in {kitchen.checkout} '
        "(not the default)\n",
    )
    assert [one["number"] for one in records(kitchen)["records"]] == [1, 2, 3]
    assert len(kitchen.lines("gate")) == 3


def test_a_number_starts_above_the_gates_a_gates_file_has(kitchen):
    (kitchen.home / "gates.md").write_text(gate("an old one?", n=7, status="answered"))
    (kitchen.home / "side").mkdir()
    (kitchen.home / "side" / "gates.md").write_text(gate("a scoped one?", n=9))
    assert ask(kitchen) == (0, "queued: question 10\n")


@pytest.mark.parametrize(
    ("lines", "why"),
    [
        (
            "a made up question\n" + OPTIONS,
            "the first line is not '## Gate <n>: ' and the question",
        ),
        ("alpha: gate\n" + gate(), "the first line is not '## Gate <n>: ' and the question"),
        (gate(asked="<the question>"), "the first line is not '## Gate <n>: ' and the question"),
        (gate() + gate(asked="milk?"), "it is not one gate"),
        (gate(status="answered"), "the gate has no Status: open line"),
        (
            "## Gate <n>: tea or coffee?\nStatus: open\n" + OPTIONS,
            "the gate has no Asked by: line that is filled in",
        ),
        (
            gate().replace("Default: the first one", "Default: <what the thread did>"),
            "the gate has no Default: line that is filled in",
        ),
        (
            gate().replace("Default: the first one", "Default:   <what the thread did>"),
            "the gate has no Default: line that is filled in",
        ),
        (
            gate().replace("Default: the first one", "Default:   "),
            "the gate has no Default: line that is filled in",
        ),
        (
            gate().replace("Undo: pick the other\n", ""),
            "the gate has no Undo: line that is filled in",
        ),
    ],
)
def test_lines_that_are_not_one_gate_of_the_template_filled_in_are_not_sent(kitchen, lines, why):
    code, said = kitchen.main("gate", "alpha", stdin=lines)
    assert (code, said) == (1, f"not sent: {why}.\n")
    assert not (kitchen.state / "questions.json").exists()
    assert kitchen.lines("gate") == []


def test_one_command_closes_a_question_and_a_second_answer_prints_the_first(kitchen):
    ask(kitchen)
    code, said = answer(kitchen, 1, "coffee,", "and", "strong")
    first = f'"coffee, and strong", by user, {AT}, in {kitchen.checkout} (not the default)'
    assert (code, said) == (
        0,
        f"answered: question 1: {first}: the next pass tells alpha's thread\n",
    )
    assert records(kitchen)["records"][0]["answer"] == {
        "words": "coffee, and strong",
        "by": "user",
        "at": AT,
        "where": str(kitchen.checkout),
        "keeps": False,
        "told": "",
        "closed_by": "jbus answer",
        "ref": "",
        "said_in": "",
        "checked": False,
    }
    assert answer(kitchen, 1, "tea") == (
        1,
        f"refused: question 1 was answered already: {first}\n",
    )
    assert records(kitchen)["records"][0]["answer"]["words"] == "coffee, and strong"


def test_an_answer_is_given_from_any_checkout_of_the_project(kitchen, tmp_path):
    ask(kitchen)
    other = tmp_path / "a-worktree"
    kitchen.git("worktree", "add", "-q", "-b", "beta", str(other))
    kitchen.monkeypatch.chdir(other)
    code, said = answer(kitchen, 1, "coffee")
    assert (code, f"in {other} " in said) == (0, True)
    assert records(kitchen)["records"][0]["answer"]["where"] == str(other)


@pytest.mark.parametrize(
    "argv, says",
    [
        (
            ["1", "--by", "Chef", "--at", AT, "--differs", "tea"],
            "refused: only user answers a question, not Chef",
        ),
        (
            ["1", "--by", "user", "--at", "today", "--differs", "tea"],
            'refused: --at is "<YYYY-MM-DD HH:MM ET>"',
        ),
        (["4", *SAID, "--differs", "tea"], "refused: no question 4, open: 1"),
    ],
)
def test_an_answer_nobody_can_give_is_refused_and_the_question_stays_open(kitchen, argv, says):
    ask(kitchen)
    assert kitchen.main("answer", *argv) == (1, says + "\n")
    assert records(kitchen)["records"][0]["answer"] is None


def test_an_answer_that_differs_goes_once_to_the_askers_thread_and_starts_no_post(kitchen):
    ask(kitchen)
    kitchen.poll()
    kitchen.wakes.posts.clear()
    answer(kitchen, 1, "coffee")
    said = kitchen.poll(later(10))
    kitchen.poll(later(20))
    kitchen.poll(later(30))
    (sent,) = kitchen.t3.messages.values()
    assert (sent["threadId"], sent["mode"], sent["clientRequestId"]) == (
        THREAD,
        "queue",
        "answer|alpha|1",
    )
    assert sent["message"] == (
        "jbus: user answered question 1 (tea or coffee?), and the answer is not the default "
        f'you took (the first one). The words, {AT}: "coffee". Undo: pick the other. Built on '
        "the default: nothing. Take the default back, do what the answer says, and add one "
        "line to the last Result or Report saying what you changed. "
        "End your turn only once no check or proof you started runs in your "
        "worktree: wait for one that runs, in this turn."
    )
    sends = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]
    assert len(sends) == 1
    assert "note alpha: told its thread the answer to question 1" in said
    assert records(kitchen)["records"][0]["answer"]["told"]
    assert kitchen.wakes.posts == []


def test_an_answer_goes_to_the_thread_of_a_scouts_request(kitchen):
    kitchen.brief("survey", "Thread: mcp:scout-1\n", kind="scouts")
    ask(kitchen, slug="survey")
    answer(kitchen, 1, "coffee")
    kitchen.poll(later(10))
    (sent,) = kitchen.t3.messages.values()
    assert (sent["threadId"], sent["clientRequestId"]) == ("mcp:scout-1", "answer|survey|1")


def test_an_answer_that_is_the_default_sends_nothing(kitchen):
    ask(kitchen)
    ask(kitchen, "milk?")
    kitchen.poll()
    kitchen.wakes.posts.clear()
    code, said = answer(kitchen, 1, "yes,", "keep", "it", default=True)
    assert (code, said.endswith("(the default stands): nothing is sent\n")) == (0, True)
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert kitchen.t3.messages == {}
    assert kitchen.wakes.posts == []


def test_an_answer_t3_code_did_not_take_is_sent_by_the_next_pass(kitchen):
    ask(kitchen)
    answer(kitchen, 1, "coffee")
    kitchen.t3.lose_send = True
    said = kitchen.poll(later(10))
    assert [line for line in said if line.startswith("wait alpha: the answer to question 1")]
    assert kitchen.t3.messages == {}
    kitchen.t3.lose_send = False
    kitchen.poll(later(11))
    assert list(kitchen.t3.messages) == ["answer|alpha|1"]


def test_a_closed_question_is_listed_nowhere_and_has_no_gate_answered_event(kitchen):
    ask(kitchen)
    (kitchen.home / "gates.md").write_text(gate(n=3))
    kitchen.poll()
    assert [one["key"] for one in listed(kitchen)] == ["gate:q1"]
    answer(kitchen, 1, "coffee")
    (kitchen.home / "gates.md").write_text(gate(n=3, status="answered 2026-10-12: coffee"))
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert listed(kitchen) == []
    code, out = kitchen.main("digest", "--json")
    assert [o for o in json.loads(out)["projects"]["demo"]["waiting"] if o["kind"] == "gate"] == []
    seen = shown(kitchen)
    assert [one for one in seen["waiting"] if one["kind"] == "gate"] == []
    assert seen["gates"] == []
    assert digest.build(jbus.load())["projects"]["demo"]["waiting"] == []
    code, out = kitchen.main("events")
    kinds = [json.loads(line)["event"] for line in out.splitlines()]
    assert "gate answered" not in kinds
    assert kinds.count("gate") == 1


def test_a_gate_only_a_gates_file_has_is_still_listed_and_still_said_when_answered(kitchen):
    (kitchen.home / "gates.md").write_text(gate("an old one?", n=3))
    kitchen.poll()
    assert [one["line"] for one in listed(kitchen)] == ["gate 3: an old one?"]
    (kitchen.home / "gates.md").write_text(gate("an old one?", n=3, status="answered: yes"))
    kitchen.poll(later(10))
    assert listed(kitchen) == []
    assert kitchen.lines("gate answered") == ["gate alpha: gate 3 answered"]


def test_a_question_a_gates_file_has_too_is_counted_once_as_the_record(kitchen):
    ask(kitchen)
    (kitchen.home / "gates.md").write_text(gate(n=3) + "\n" + gate("an old one?", n=2))
    kitchen.poll()
    assert [one["line"] for one in listed(kitchen)] == [
        "gate 2: an old one?",
        "question 1: tea or coffee?" + ACTED,
    ]
    assert [one["number"] for one in shown(kitchen)["waiting"] if one["kind"] == "gate"] == [
        "2",
        "1",
    ]
    assert kitchen.lines("gate") == [
        "gate alpha: question 1: tea or coffee?",
        "gate alpha: an old one?",
    ]


def test_an_open_question_is_listed_on_every_pass_until_it_is_closed(kitchen):
    ask(kitchen)
    for minutes in (0, 10, 70):
        kitchen.poll(later(minutes))
        assert [one["key"] for one in listed(kitchen)] == ["gate:q1"]
    answer(kitchen, 1, "tea", default=True)
    kitchen.poll(later(80))
    assert listed(kitchen) == []


def test_an_answer_says_whether_it_is_the_default_or_it_is_not_taken(kitchen):
    ask(kitchen)
    code, said = kitchen.main("answer", "1", *SAID, "yes")
    assert code == 2 and "one of the arguments --default --differs is required" in said
    assert records(kitchen)["records"][0]["answer"] is None


def test_an_answer_t3_code_refuses_is_a_gate_once_and_is_sent_when_it_is_taken(kitchen):
    ask(kitchen)
    kitchen.poll()
    kitchen.wakes.posts.clear()
    answer(kitchen, 1, "coffee")
    kitchen.t3.refuse_send = True
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert records(kitchen)["records"][0]["answer"]["told"] == ""
    assert kitchen.lines("condition") == [
        "condition alpha: T3 Code refused the answer to question 1, so its thread was not told"
    ]
    kitchen.t3.refuse_send = False
    kitchen.poll(later(30))
    assert list(kitchen.t3.messages) == ["answer|alpha|1"]
    assert records(kitchen)["records"][0]["answer"]["told"]


def test_an_answer_for_a_slug_with_no_thread_line_is_noted_and_waits_for_one(kitchen):
    ask(kitchen, slug="expert-sage-tea")
    code, said = answer(kitchen, 1, "coffee")
    assert said.endswith(
        ": expert-sage-tea has no Thread: line in a brief or request, so no thread is told\n"
    )
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert kitchen.t3.messages == {}
    code, out = kitchen.main("events", "--slug", "expert-sage-tea")
    notes = [one for one in map(json.loads, out.splitlines()) if one["event"] == "note"]
    assert [(one["line"], one["loud"]) for one in notes] == [
        ("note expert-sage-tea: the answer to question 1 has no thread to go to", "quiet")
    ]
    kitchen.brief("expert-sage-tea", "Thread: mcp:sage\n", kind="scouts")
    kitchen.poll(later(30))
    (sent,) = kitchen.t3.messages.values()
    assert sent["threadId"] == "mcp:sage"


def test_a_question_a_home_closed_in_its_gates_file_is_closed_and_nothing_is_sent(kitchen):
    ask(kitchen)
    (kitchen.home / "gates.md").write_text(gate(n=3))
    kitchen.poll()
    assert [one["key"] for one in listed(kitchen)] == ["gate:q1"]
    kitchen.wakes.posts.clear()
    (kitchen.home / "gates.md").write_text(gate(n=3, status="answered 2026-10-12: coffee"))
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert listed(kitchen) == []
    assert records(kitchen)["records"][0]["answer"] == {
        "words": "answered 2026-10-12: coffee",
        "by": "",
        "at": "",
        "where": str(kitchen.home / "gates.md"),
        "keeps": False,
        "told": "",
        "closed_by": "gates.md",
        "ref": "",
        "said_in": "",
        "checked": False,
    }
    assert kitchen.t3.messages == {} and kitchen.wakes.posts == []
    assert kitchen.lines("gate answered") == []
    assert answer(kitchen, 1, "tea") == (
        1,
        "refused: question 1 was answered already: closed by its home in "
        f'{kitchen.home / "gates.md"}, "answered 2026-10-12: coffee"\n',
    )


def held(asked="drop the old branch?", n="<n>", status="open"):
    """Return a gate that holds for the user, with its case and its fail-safe under `Undo:`."""
    return gate(asked, n=n, status=status).replace(
        "Undo: pick the other\n",
        "Undo: pick the other\nHolds: deletes data\nFail-safe: the dry-run in /tmp/gone.txt\n",
    )


def test_a_home_closes_no_gate_that_holds_in_its_gates_file_and_the_pass_says_so_once(kitchen):
    ask(kitchen)
    assert kitchen.main("gate", "alpha", stdin=held())[0] == 0
    answered = gate(n=3, status="answered: coffee") + "\n" + held(n=4, status="answered: yes")
    (kitchen.home / "gates.md").write_text(answered)
    said = kitchen.poll(later(10))
    plain, holds = records(kitchen)["records"]
    assert plain["answer"]["closed_by"] == "gates.md"
    assert holds["answer"] is None
    line = (
        "note alpha: question 2 holds (deletes data) for user's own answer, and "
        f"{kitchen.home / 'gates.md'} marked it answered: it stays open"
    )
    assert [one for one in said if "question 2" in one] == [line]
    assert [one["key"] for one in listed(kitchen)] == ["gate:q2"]
    assert [one for one in kitchen.poll(later(20)) if "question 2" in one] == []
    assert answer(kitchen, 2, "yes", default=True)[0] == 0
    assert records(kitchen)["records"][1]["answer"]["closed_by"] == "jbus answer"


@pytest.mark.parametrize("text", ["not json", "{}", '{"next": 2, "records": [{"number": 1}]}'])
def test_a_file_that_is_not_the_one_jbus_wrote_is_refused_and_left_as_it_is(kitchen, text):
    ask(kitchen)
    file = kitchen.state / "questions.json"
    file.write_text(text)
    refusal = f"refused: {file} does not parse, and nothing writes it\n"
    assert ask(kitchen, "milk?") == (1, refusal)
    assert answer(kitchen, 1, "tea") == (1, refusal)
    assert file.read_text() == text


def test_a_pass_that_cannot_read_the_questions_says_so_and_keeps_what_its_list_had(kitchen):
    ask(kitchen)
    (kitchen.home / "gates.md").write_text(gate(n=3))
    kitchen.poll()
    kitchen.wakes.posts.clear()
    file = kitchen.state / "questions.json"
    kept = file.read_text()
    file.write_text("not json")
    (kitchen.home / "gates.md").write_text(gate(n=3, status="answered: coffee"))
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert [one["line"] for one in listed(kitchen)] == ["question 1: tea or coffee?" + ACTED]
    assert kitchen.lines("condition") == ["condition demo: questions.json does not parse"]
    assert kitchen.lines("gate answered") == []
    file.write_text(kept)
    kitchen.poll(later(30))
    assert listed(kitchen) == []
    assert kitchen.lines("gate answered") == []


def test_a_gate_of_a_scoped_home_beside_a_question_is_still_listed_and_posted_nowhere(kitchen):
    ask(kitchen)
    kitchen.poll()
    kitchen.wakes.posts.clear()
    (kitchen.home / "quay").mkdir()
    (kitchen.home / "quay" / "gates.md").write_text(gate("which berth?", slug="home", n=1))
    kitchen.poll(later(10))
    event = kitchen.events("waiting")[-1]
    assert event["loud"] == "quiet" and kitchen.wakes.posts == []
    assert event["line"] == "waiting demo: 2 wait on user, 1 new (gate quay#1), 0 gone"
    assert [one["line"] for one in listed(kitchen)] == [
        "gate 1: which berth?",
        "question 1: tea or coffee?" + ACTED,
    ]


def test_an_open_question_asked_again_takes_the_new_lines_and_a_closed_one_keeps_its_own(kitchen):
    ask(kitchen)
    again = gate().replace("Built on it: nothing", "Built on it: the head abc123")
    again = again.replace("Default: the first one", "Default: the second one")
    assert kitchen.main("gate", "alpha", stdin=again) == (0, "already sent: question 1\n")
    (one,) = records(kitchen)["records"]
    assert (one["default"], one["built_on"], one["number"]) == (
        "the second one",
        "the head abc123",
        1,
    )
    answer(kitchen, 1, "tea", default=True)
    kitchen.main("gate", "alpha", stdin=gate())
    assert records(kitchen)["records"][0]["default"] == "the second one"


def test_a_file_that_does_not_parse_loses_no_number(kitchen):
    ask(kitchen)
    ask(kitchen, "milk?")
    kept = records(kitchen)
    kept["next"] = "soon"
    (kitchen.state / "questions.json").write_text(json.dumps(kept))
    assert [one.number for one in questions.load(kitchen.state)] == [1, 2]
    assert ask(kitchen, "sugar?") == (0, "queued: question 3\n")


SHELF = "Context: the shelf\nOption: tea (default, recommended): stay\nOption: coffee: they go\n"
BARE = (
    "## Gate <n>: tea or coffee?\nStatus: open\nAsked by: alpha, thread mcp:a-thread\n"
    "Default: tea\n"
    "Built on it: the cups\nUndo: pour it out\n"
)
FORM = (
    "Write the options and pipe the gate again: each option you weighed is one line, the "
    'default you took among them: "Option: <short name> (default, recommended): <what follows '
    'from it>", with both marks on the one that was taken, which is the one you recommend, '
    "and no mark on the rest."
)


def option(name, follows, default=False, recommended=False):
    return {"name": name, "follows": follows, "default": default, "recommended": recommended}


def test_a_gate_keeps_its_context_and_every_option_in_order_with_the_two_marks(kitchen):
    lines = (
        f"{BARE}Context: the cups are in https://example.test/pull/7, and tea is on the shelf\n"
        "Option: tea (default, recommended): the cups stay\n"
        "Option: coffee: the cups go back: one revert\n"
        "Option: water: nothing is brewed\n"
    )
    assert kitchen.main("gate", "alpha", stdin=lines) == (0, "queued: question 1\n")
    (one,) = records(kitchen)["records"]
    assert one["context"] == "the cups are in https://example.test/pull/7, and tea is on the shelf"
    assert one["options"] == [
        option("tea", "the cups stay", default=True, recommended=True),
        option("coffee", "the cups go back: one revert"),
        option("water", "nothing is brewed"),
    ]


def test_one_option_is_the_default_and_the_pick(kitchen):
    both = f"{BARE}Option: tea (default, recommended): the cups stay\nOption: coffee: they go\n"
    assert kitchen.main("gate", "alpha", stdin=both)[0] == 0
    assert records(kitchen)["records"][0]["options"] == [
        option("tea", "the cups stay", default=True, recommended=True),
        option("coffee", "they go"),
    ]
    assert records(kitchen)["records"][0]["context"] == ""


@pytest.mark.parametrize(
    ("options", "missing"),
    [
        ("", "the gate has no Option: lines and needs two or more"),
        (
            "Option: tea (default): the cups stay\n",
            "the gate has one Option: line and needs two or more",
        ),
        (
            "Option: tea: the cups stay\nOption: coffee (recommended): they go\n",
            "no option is marked (default), and one is the default that was taken",
        ),
        (
            "Option: tea (default): the cups stay\nOption: coffee (default): they go\n",
            "two options are marked (default), and one is the default that was taken",
        ),
        (
            "Option: tea (default, recommended): stay\nOption: coffee (recommended): they go\n",
            "two options are marked (recommended), and one is the pick",
        ),
        (
            "Option: tea (default): the cups stay\nOption: tea: they go\n",
            'two options have the name "tea"',
        ),
        (
            "Option: tea (default): the cups stay\nOption: coffee (Recommended): they go\n",
            'the name "coffee (Recommended)" ends in parentheses that are not (default), '
            "(recommended) or (default, recommended)",
        ),
        (
            "Option: tea (default) (recommended): the cups stay\nOption: coffee: they go\n",
            'the name "tea (default)" ends in parentheses that are not (default), '
            "(recommended) or (default, recommended)",
        ),
        (
            "Option: tea (default): the cups stay\nOption: coffee\n",
            'the line "Option: coffee" is not an option\'s short name and what follows from it',
        ),
        (
            "Option: tea (default): the cups stay\n"
            "Option: <an option's short name> (default, recommended): <what follows from it>\n",
            "the line \"Option: <an option's short name> (default, recommended): <what follows "
            "from it>\" is not an option's short name and what follows from it",
        ),
    ],
)
def test_a_gate_that_does_not_propose_two_options_with_the_default_is_not_sent(
    kitchen, options, missing
):
    assert kitchen.main("gate", "alpha", stdin=BARE + options) == (
        1,
        f"not sent: {missing}. {FORM}\n",
    )
    assert not (kitchen.state / "questions.json").exists()
    assert kitchen.lines("gate") == []


def test_the_refusal_alone_is_enough_to_write_lines_jbus_takes(kitchen):
    """A thread whose skill is older than the options has only the refusal to go by. jbus accepts
    the refusal's form as a gate in two ways: filled in as shown, and filled in again with no
    mark."""
    _, said = kitchen.main("gate", "alpha", stdin=BARE)
    (form,) = [part for part in said.split('"') if part.startswith("Option: ")]
    first = form.replace("<short name>", "tea").replace("<what follows from it>", "the cups stay")
    assert kitchen.main("gate", "alpha", stdin=f"{BARE}{first}\nOption: coffee: they go\n") == (
        0,
        "queued: question 1\n",
    )
    assert records(kitchen)["records"][0]["options"] == [
        option("tea", "the cups stay", default=True, recommended=True),
        option("coffee", "they go"),
    ]


def before_options(kitchen, *asked, holds=""):
    """Write a `questions.json` as jbus wrote it before a gate had options: no record has a
    `context` or an `options`. With `holds`, each record holds for the user, as a pass leaves
    only such a record open long enough to be asked for its options."""
    kept = [
        {
            "number": number,
            "slug": slug,
            "thread": f"mcp:crew-{slug}",
            "question": question,
            "default": "tea",
            "built_on": "the cups",
            "undo": "pour it out",
            "asked_at": "2026-10-12T15:00:00+00:00",
            "answer": None,
            **({"holds": holds, "fail_safe": "the dry-run"} if holds else {}),
        }
        for number, (slug, question) in enumerate(asked, 1)
    ]
    kitchen.state.mkdir(parents=True, exist_ok=True)
    file = kitchen.state / "questions.json"
    file.write_text(json.dumps({"next": len(kept) + 1, "records": kept}))
    return file


def test_a_file_written_before_options_still_loads_and_its_question_is_still_answered(kitchen):
    before_options(kitchen, ("alpha", "tea or coffee?"))
    (one,) = questions.read(kitchen.state)
    assert (one.number, one.question, one.context, one.options) == (1, "tea or coffee?", "", ())
    kitchen.poll()
    assert records(kitchen)["records"][0]["answer"]["closed_by"] == questions.SILENCE
    assert answer(kitchen, 1, "tea", default=True)[0] == 0
    (kept,) = records(kitchen)["records"]
    assert (kept["answer"]["words"], kept["context"], kept["options"]) == ("tea", "", [])
    assert ask(kitchen, "milk?") == (0, "queued: question 2\n")


def test_an_open_question_piped_again_with_options_gains_them_and_keeps_its_number(kitchen):
    before_options(kitchen, ("alpha", "tea or coffee?"), ("alpha", "milk?"))
    again = BARE + SHELF
    assert kitchen.main("gate", "alpha", stdin=again) == (0, "already sent: question 1\n")
    one, other = records(kitchen)["records"]
    assert (one["number"], one["context"], one["asked_at"]) == (
        1,
        "the shelf",
        "2026-10-12T15:00:00+00:00",
    )
    assert one["options"] == [
        option("tea", "stay", default=True, recommended=True),
        option("coffee", "they go"),
    ]
    assert (other["number"], other.get("options", [])) == (2, [])
    assert records(kitchen)["next"] == 3


def test_an_answered_question_piped_again_with_options_is_not_changed(kitchen):
    file = before_options(kitchen, ("alpha", "tea or coffee?"))
    answer(kitchen, 1, "tea", default=True)
    kept = file.read_text()
    again = BARE + SHELF
    code, said = kitchen.main("gate", "alpha", stdin=again)
    assert (code, said.startswith('already answered: question 1: "tea", by user')) == (0, True)
    assert file.read_text() == kept


def asked_for_options(kitchen):
    return [
        (given["threadId"], given["clientRequestId"])
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send" and given["clientRequestId"].startswith("options|")
    ]


def test_a_pass_asks_the_thread_of_each_open_question_with_no_options_once(kitchen):
    kitchen.brief("beta", "Thread: mcp:crew-beta\n")
    kitchen.brief("gone", "Thread: mcp:crew-gone\n")
    kitchen.brief("done", "Thread: mcp:crew-done\n")
    for slug in ("alpha", "beta", "done"):
        kitchen.t3.thread(slug, "completed", threadId=f"mcp:crew-{slug}", settled=True)
    before_options(
        kitchen,
        ("alpha", "tea or coffee?"),
        ("beta", "milk?"),
        ("gone", "sugar?"),
        ("done", "a?"),
        holds="deletes data",
    )
    assert answer(kitchen, 4, "yes", default=True)[0] == 0
    assert ask(kitchen, "a spoon?") == (0, "queued: question 5\n")
    for minutes in (10, 20, 30):
        kitchen.poll(later(minutes))
    assert asked_for_options(kitchen) == [
        (THREAD, "options|alpha|1"),
        ("mcp:crew-beta", "options|beta|2"),
    ]
    message = kitchen.t3.messages["options|alpha|1"]["message"]
    said, held = message.split("\n\n")
    assert said == (
        "jbus: question 1 is open and shows the user no options. Pipe its gate again to `jbus "
        "gate alpha`: the lines below as they are, which are the ones jbus holds, so that it "
        "stays question 1, and two things more under them. One line `Context: <what the user "
        "needs to know to answer, with the links to it>`. And each option you weighed is one "
        'line, the default you took among them: "Option: <short name> (default, recommended): '
        '<what follows from it>", with both marks on the one that was taken, which is the one '
        "you recommend, and no mark on the rest. "
        "End your turn only once no check or proof you started runs in your "
        "worktree: wait for one that runs, in this turn."
    )
    assert held == (
        "## Gate <n>: tea or coffee?\nStatus: open\nAsked by: alpha, thread mcp:crew-alpha\n"
        "Default: tea\nBuilt on it: the cups\nUndo: pour it out"
    )
    again = f"{held}\n{SHELF}"
    assert kitchen.main("gate", "alpha", stdin=again) == (0, "already sent: question 1\n")
    (one, *_) = records(kitchen)["records"]
    assert (one["default"], one["built_on"], one["undo"]) == ("tea", "the cups", "pour it out")
    assert [each["name"] for each in one["options"]] == ["tea", "coffee"]
    assert kitchen.lines("note") == [
        "note done: told its thread the answer to question 4",
        "note alpha: asked its thread for the options of question 1",
        "note beta: asked its thread for the options of question 2",
        "note gone: question 3 has no options, and its thread is gone",
    ]
    assert [one["answer"] for one in records(kitchen)["records"]][:3] == [None, None, None]


@pytest.mark.parametrize("listed", [True, False])
def test_a_question_is_asked_once_whatever_keys_a_snapshot_forgets(kitchen, listed):
    if listed:
        kitchen.t3.thread("alpha", "completed", threadId=THREAD, settled=True)
    before_options(kitchen, ("alpha", "tea or coffee?"), holds="deletes data")
    kitchen.poll(later(10))
    asked = [(THREAD, "options|alpha|1")] if listed else []
    assert asked_for_options(kitchen) == asked
    assert datetime.fromisoformat(records(kitchen)["records"][0]["proposed"]).tzinfo is not None
    wake.Box(kitchen.state, None).prune({"alpha"})
    kitchen.t3.thread("alpha", "completed", threadId=THREAD, settled=True)
    kitchen.poll(later(20))
    assert asked_for_options(kitchen) == asked


def test_a_question_with_no_thread_line_is_asked_nothing_and_a_lost_send_goes_next_pass(kitchen):
    kitchen.t3.thread("alpha", "completed", threadId=THREAD, settled=True)
    before_options(
        kitchen, ("alpha", "tea or coffee?"), ("expert-sage-tea", "milk?"), holds="deletes data"
    )
    kitchen.t3.lose_send = True
    said = kitchen.poll(later(10))
    assert "wait alpha: its thread could not be asked for options" in " ".join(said)
    assert kitchen.t3.messages == {}
    kitchen.t3.lose_send = False
    kitchen.poll(later(20))
    kitchen.poll(later(30))
    assert list(kitchen.t3.messages) == ["options|alpha|1"]
    assert kitchen.lines("note") == [
        "note expert-sage-tea: question 2 has no options and no thread to ask",
        "note alpha: asked its thread for the options of question 1",
    ]
