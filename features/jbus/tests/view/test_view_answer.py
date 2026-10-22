"""The one write of `jbus view`, the user's answer to a question, and how the server sends it
on."""

import json
from datetime import timedelta

import pytest

import jsettings
from jbus import questions, queue, view
from test_jbus_kitchen import GATE as PIPED
from test_jbus_kitchen import NOW as POLLED
from test_jbus_kitchen import Kitchen
from view.scene import EVIL, NOW, PANTRY, PROXIED, Served, ago, asks, et, iso, kept


def test_another_method_is_405(served):
    for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "BREW"):
        status, headers, _ = served.ask("/state.json?project=demo", method=method)
        assert (method, status, headers.get("Allow")) == (method, 405, "GET")


def test_the_one_write_is_post_answer_and_every_other_method_of_it_is_405(scene, served):
    number = asks(scene)
    for method in ("PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
        status, headers, _ = served.ask("/answer", method=method)
        assert (method, status, headers.get("Allow")) == (method, 405, "POST")
    assert served.ask("/answer")[0] == 404
    assert served.write({"numbers": [number]}, path="/state.json?project=demo")[0] == 405
    assert kept(scene.state)[number].answer is None
    status, said = served.write({"numbers": [number]})
    assert (status, [one["number"] for one in said["closed"]]) == (200, [number])


@pytest.mark.parametrize("origin", ["http://example.test", "http://127.0.0.1:1", "null", ""])
def test_a_write_from_another_origin_or_from_none_is_403_and_changes_nothing(scene, served, origin):
    number = asks(scene)
    before = questions.path(scene.state).read_bytes()
    status, said = served.write({"numbers": [number]}, origin=origin)
    assert (status, said) == (403, {"error": "only the server's own page writes"})
    assert questions.path(scene.state).read_bytes() == before


def test_a_write_is_held_to_the_host_check_and_takes_the_origin_of_each_name(scene):
    number = asks(scene)
    served = Served(scene, names=("kitchen.example.test",))
    try:
        evil = f"evil.example.test:{served.port}"
        status, said = served.write({"numbers": [number]}, origin=f"http://{evil}", host=evil)
        assert (status, said) == (403, {"error": "this is not the server's name"})
        assert kept(scene.state)[number].answer is None
        name = f"kitchen.example.test:{served.port}"
        status, _ = served.write({"numbers": [number]}, origin=f"http://{name}", host=name)
        assert status == 200
    finally:
        served.close()


def test_a_host_is_known_by_an_origin_with_or_without_its_default_port(scene, served):
    behind = Served(scene, origins=(f"https://{PROXIED}", f"http://{PANTRY}:8080"))
    try:
        for host in (PROXIED, f"{PROXIED}:443", "pantry.example.test:8080"):
            assert behind.ask("/healthz", host=host)[0] == 200, host
        for host in (
            f"{PROXIED}:80",
            f"{PROXIED}:8443",
            "pantry.example.test",
            "evil.example.test",
        ):
            assert behind.ask("/healthz", host=host)[0] == 403, host
    finally:
        behind.close()
    assert served.ask("/healthz", host=PROXIED)[0] == 403


def test_a_write_behind_a_proxy_takes_exactly_the_origin_that_names_its_host(scene):
    number = asks(scene)
    behind = Served(scene, origins=(f"https://{PROXIED}",))
    try:
        for origin in (
            f"http://{PROXIED}",
            f"https://{PROXIED}:443",
            f"https://{EVIL}",
            "",
        ):
            status, said = behind.write({"numbers": [number]}, origin=origin, host=PROXIED)
            assert (status, said) == (403, {"error": "only the server's own page writes"}), origin
        assert kept(scene.state)[number].answer is None
        nowhere = "/answer?project=nowhere"
        status, _ = behind.write({}, origin=f"https://{PROXIED}", host=PROXIED, path=nowhere)
        assert status == 404
        for host in (PROXIED, f"{PROXIED}:443"):
            status, _ = behind.write({"numbers": [number]}, origin=f"https://{PROXIED}", host=host)
            assert status == (200 if host == PROXIED else 409), host
    finally:
        behind.close()
    assert kept(scene.state)[number].answer is not None


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        {},
        {"numbers": []},
        {"numbers": "1"},
        {"numbers": [True]},
        {"numbers": ["1"]},
        {"numbers": [1, 1]},
        {"numbers": [1], "option": 3},
        {"numbers": [1], "words": ["tea"]},
    ],
)
def test_a_write_that_is_not_the_shape_is_400_and_changes_nothing(scene, served, body):
    number = asks(scene)
    if isinstance(body, dict) and body.get("numbers"):
        body = body | {
            "numbers": [number if n == 1 and n is not True else n for n in body["numbers"]]
        }
    assert served.write(body)[0] == 400
    assert kept(scene.state)[number].answer is None


def test_a_batch_with_an_option_or_words_is_refused_whole(scene, served):
    first, second = asks(scene), asks(scene, "milk?")
    for more in ({"option": "the other"}, {"words": "oat milk"}):
        status, said = served.write({"numbers": [first, second], **more})
        assert (status, said) == (
            400,
            {"error": "a batch only takes defaults: answer that one by itself"},
        )
    assert [one.answer for one in kept(scene.state).values()] == [None, None]


def test_a_second_write_to_a_question_is_refused_with_the_first_answer(scene, served):
    number = asks(scene)
    assert served.write({"numbers": [number]})[0] == 200
    status, said = served.write({"numbers": [number], "words": "coffee after all"})
    first = f'"the first one", by user, {et(NOW)}, in jbus view (the default stands)'
    assert (status, said["closed"]) == (409, [])
    (refused,) = said["refused"]
    assert refused["say"] == (
        f"Question {number} was answered already, and nothing changed: {first}."
    )
    assert (refused["first"]["words"], refused["first"]["keeps"]) == ("the first one", True)
    assert refused["first"]["line"] == first
    assert kept(scene.state)[number].answer.words == "the first one"


def test_three_are_closed_in_one_request_and_one_answered_already_is_said_by_number(scene, served):
    numbers = [asks(scene, asked) for asked in ("tea?", "milk?", "sugar?")]
    served.write({"numbers": [numbers[1]], "words": "oat milk"})
    status, said = served.write({"numbers": numbers})
    assert status == 200
    assert [(one["number"], one["keeps"], one["sent"]) for one in said["closed"]] == [
        (numbers[0], True, False),
        (numbers[2], True, False),
    ]
    assert said["closed"][0]["say"] == (
        f"Question {numbers[0]} closed at {jsettings.load().clock(NOW)} with its default, "
        "and nothing was sent."
    )
    (refused,) = said["refused"]
    assert (refused["number"], refused["first"]["words"]) == (numbers[1], "oat milk")
    assert refused["say"].startswith(f"Question {numbers[1]} was answered already")
    records = kept(scene.state)
    assert [records[n].answer.keeps for n in numbers] == [True, False, True]


def test_a_question_with_no_options_on_record_takes_the_default_and_his_words(scene, served):
    numbers = [asks(scene, asked) for asked in ("tea?", "milk?")]
    file = questions.path(scene.state)
    old = json.loads(file.read_text())
    for one in old["records"]:
        del one["options"], one["context"]
    file.write_text(json.dumps(old))
    (shown, _) = [
        one for one in served.json("/state.json?project=demo")["waiting"] if one["answerable"]
    ]
    assert (shown["options"], shown["default"]) == ([], "the first one")
    status, said = served.write({"numbers": [numbers[0]]})
    assert (status, said["closed"][0]["keeps"]) == (200, True)
    status, said = served.write({"numbers": [numbers[1]], "words": " oat  milk "})
    assert (status, said["closed"][0]["keeps"]) == (200, False)
    status, said = served.write({"numbers": [numbers[0]], "option": "the other"})
    assert status == 409
    records = kept(scene.state)
    assert [records[n].answer.words for n in numbers] == ["the first one", "oat milk"]


def test_an_option_the_question_does_not_have_closes_nothing(scene, served):
    number = asks(scene)
    status, said = served.write({"numbers": [number], "option": "a third"})
    assert (status, said["closed"]) == (409, [])
    assert said["refused"] == [
        {
            "number": number,
            "say": f"Question {number} has no option of that name, and nothing changed.",
            "first": None,
        }
    ]
    assert kept(scene.state)[number].answer is None


def test_a_gate_that_lives_only_in_a_homes_file_is_listed_and_cannot_be_answered(scene, served):
    (gate,) = [
        one for one in served.json("/state.json?project=demo")["waiting"] if one["kind"] == "gate"
    ]
    assert (gate["number"], gate["question"], gate["answerable"]) == ("4", "tea or coffee?", False)
    assert (gate["options"], gate["thread"], gate["role"]) == ([], "", "")
    before = (scene.home / "gates.md").read_bytes()
    status, said = served.write({"numbers": [4]})
    assert (status, said["closed"]) == (409, [])
    assert said["refused"][0]["say"] == "Question 4 did not close: no question 4, open: none."
    assert (scene.home / "gates.md").read_bytes() == before


def test_the_state_gives_each_open_question_what_its_gate_wrote_and_who_asked(scene, served):
    (scene.home / "tasks").mkdir()
    (scene.home / "scouts").mkdir()
    (scene.home / "tasks" / "alpha.md").write_text("# alpha\nThread: mcp:crew-alpha\n")
    (scene.home / "scouts" / "survey.md").write_text("# survey\nThread: mcp:scout-1\n")
    scene.passed(seconds_ago=20, threads=[{"id": "mcp:scout-1", "role": "home"}])
    lines = PIPED.format(n="<n>", asked="tea or coffee?", status="open", slug="alpha")
    lines += "Context: the pot holds two cups\nOption: both: a second pot\n"
    number = questions.ask(scene.state, scene.home, "alpha", lines, ago(minutes=25))[0].number
    asks(scene, "milk?", slug="survey")
    asks(scene, "sugar?", slug="expert-sage")
    shown = {one["question"]: one for one in served.json("/state.json?project=demo")["waiting"]}
    one = shown["tea or coffee?"]
    assert (one["number"], one["answerable"], one["since"]) == (
        str(number),
        True,
        iso(ago(minutes=25)),
    )
    assert (one["context"], one["default"]) == ("the pot holds two cups", "the first one")
    assert (one["built_on"], one["undo"]) == ("nothing", "pick the other")
    assert (one["role"], one["slug"], one["thread"]) == ("crew", "alpha", "mcp:crew-alpha")
    assert one["options"] == [
        {
            "name": "the first one",
            "follows": "nothing changes",
            "default": True,
            "recommended": True,
        },
        {"name": "the other", "follows": "one more cup", "default": False, "recommended": False},
        {"name": "both", "follows": "a second pot", "default": False, "recommended": False},
    ]
    assert (shown["milk?"]["role"], shown["milk?"]["thread"]) == ("home", "mcp:scout-1")
    assert (shown["sugar?"]["role"], shown["sugar?"]["thread"]) == ("", "")
    assert shown["milk?"]["context"] == ""


class Counter:
    """A kitchen of `test_jbus_kitchen`, with the view over its state: jbus's config and its sign-in
    are the kitchen's, and T3 Code is the kitchen's stand-in."""

    THREAD = "mcp:crew-alpha"

    def __init__(self, tmp_path, monkeypatch):
        self.kitchen = Kitchen(tmp_path, monkeypatch)
        self.kitchen.brief("alpha", f"Thread: {self.THREAD}\n")
        self.kitchen.quiet()
        self.state = self.kitchen.state
        if not (self.state / "queue.json").exists():
            (self.state / "queue.json").write_text("[]")
        self.t3 = self.kitchen.t3

    def app(self):
        sources = view.Sources(
            state_dir=self.kitchen.state_dir,
            home_dir=self.kitchen.root / "home",
            user=jsettings.load(),
        )
        return view.App(sources, clock=lambda: POLLED)

    def asks(self, asked="tea or coffee?"):
        lines = PIPED.format(n="<n>", asked=asked, status="open", slug="alpha")
        code, said = self.kitchen.main("gate", "alpha", stdin=lines)
        assert code == 0, said
        return int(said.split()[-1])

    def sends(self):
        """Each message the server asked the stand-in for T3 Code to send, taken or not."""
        return [given for tool, given in self.t3.calls if tool == "t3_thread_send"]

    def passes(self, many=2):
        for at in range(many):
            self.kitchen.poll(POLLED + timedelta(minutes=10 * (at + 1)))


@pytest.fixture
def counter(tmp_path, monkeypatch):
    made = Counter(tmp_path, monkeypatch)
    served = Served(made)
    yield made, served
    served.close()
    made.kitchen.close()


def test_the_default_taken_closes_the_question_through_jbus_and_sends_nothing(counter):
    counter, served = counter
    number = counter.asks()
    status, said = served.write({"numbers": [number]})
    assert status == 200 and said["refused"] == []
    assert said["closed"] == [
        {
            "number": number,
            "slug": "alpha",
            "keeps": True,
            "words": "the first one",
            "sent": False,
            "why": "",
            "thread": "",
            "role": "crew",
            "say": f"Question {number} closed at 11:00 ET with its default, and nothing was sent.",
        }
    ]
    given = kept(counter.state)[number].answer
    assert (given.keeps, given.by, given.at, given.where) == (
        True,
        "user",
        et(POLLED),
        "jbus view",
    )
    assert (given.words, given.told, given.closed_by) == ("the first one", "", "jbus answer")
    counter.passes()
    assert counter.sends() == []


@pytest.mark.parametrize(
    "more, words",
    [
        ({"option": "the other"}, "the other"),
        ({"option": "the other", "words": " and  a biscuit "}, "the other. and a biscuit"),
        ({"words": "neither, water"}, "neither, water"),
        ({"option": "the first one", "words": "but only half a cup"}, "but only half a cup"),
    ],
)
def test_another_option_or_his_words_go_once_to_the_thread_that_asked_in_the_same_request(
    counter, more, words
):
    counter, served = counter
    number = counter.asks()
    status, said = served.write({"numbers": [number], **more})
    (closed,) = said["closed"]
    assert (status, closed["keeps"], closed["sent"], closed["words"]) == (200, False, True, words)
    assert (closed["thread"], closed["why"]) == (counter.THREAD, "")
    assert closed["say"] == (
        f"Question {number} closed at 11:00 ET, and its answer went to the crew thread of alpha."
    )
    (sent,) = counter.sends()
    assert (sent["threadId"], sent["mode"], sent["clientRequestId"]) == (
        counter.THREAD,
        "queue",
        f"answer|alpha|{number}",
    )
    assert sent["message"] == (
        f"jbus: user answered question {number} (tea or coffee?), and the answer is not the "
        f'default you took (the first one). The words, {et(POLLED)}: "{words}". Undo: pick the '
        "other. Built on the default: nothing. Take the default back, do what the answer says, "
        "and add one line to the last Result or Report saying what you changed. End your "
        "turn only once no check or proof you started runs in your worktree: wait for one that "
        "runs, in this turn."
    )
    given = kept(counter.state)[number].answer
    assert (given.keeps, given.words, bool(given.told)) == (False, words, True)
    counter.passes()
    assert len(counter.sends()) == 1
    assert counter.kitchen.lines("note") == [
        f"note alpha: told its thread the answer to question {number}"
    ]


@pytest.mark.parametrize(
    "fails, why",
    [
        ("refuse_send", "T3 Code refused it (t3_thread_send: no)"),
        (
            "lose_send",
            "T3 Code did not answer (T3 Code at /mcp could not be reached: Remote end closed "
            "connection without response)",
        ),
    ],
)
def test_an_answer_t3_code_does_not_take_is_recorded_and_the_next_pass_sends_it(
    counter, fails, why
):
    counter, served = counter
    number = counter.asks()
    setattr(counter.t3, fails, True)
    status, said = served.write({"numbers": [number], "option": "the other"})
    (closed,) = said["closed"]
    assert (status, closed["keeps"], closed["sent"], closed["thread"]) == (200, False, False, "")
    assert closed["why"] == why
    assert closed["say"] == (
        f"Question {number} closed at 11:00 ET with its answer recorded and not yet sent, "
        f"since {why}: the next pass sends it."
    )
    given = kept(counter.state)[number].answer
    assert (given.words, given.keeps, given.told) == ("the other", False, "")
    assert counter.t3.messages == {}
    setattr(counter.t3, fails, False)
    before = len(counter.sends())
    counter.passes(1)
    assert len(counter.sends()) == before + 1
    assert list(counter.t3.messages) == [f"answer|alpha|{number}"]
    counter.passes(1)
    assert len(counter.sends()) == before + 1
    assert kept(counter.state)[number].answer.told


def test_an_answer_with_no_sign_in_is_recorded_and_says_why(counter):
    counter, door = counter
    number = counter.asks()
    token = counter.kitchen.config_dir / "t3.json"
    token.unlink()
    status, said = door.write({"numbers": [number], "words": "coffee"})
    assert (status, said["closed"][0]["sent"]) == (200, False)
    assert said["closed"][0]["why"] == f"no token in {token}: run `jbus t3 login`"
    assert kept(counter.state)[number].answer.words == "coffee"
    assert counter.sends() == []


def test_an_answer_no_pass_will_send_does_not_say_that_the_next_pass_sends_it(counter):
    counter, served = counter
    first, second = counter.asks(), counter.asks("milk?")
    brief = counter.kitchen.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace(f"Thread: {counter.THREAD}\n", ""))
    _, said = served.write({"numbers": [first], "words": "coffee"})
    assert said["closed"][0]["say"] == (
        f"Question {first} closed at 11:00 ET with its answer recorded and not yet sent, since "
        "alpha has no Thread: line in a brief or request: a pass sends it once one names its "
        "thread."
    )
    removed = {"alpha": {"at": et(POLLED), "by": "user"}}
    queue.removed_path(counter.state).write_text(json.dumps(removed))
    assert queue.removed_slugs(counter.state) == {"alpha"}
    _, said = served.write({"numbers": [second], "words": "oat milk"})
    assert said["closed"][0]["say"] == (
        f"Question {second} closed at 11:00 ET with its answer recorded, and it goes to no "
        "thread, since alpha was removed from the queue."
    )
    assert counter.sends() == []
