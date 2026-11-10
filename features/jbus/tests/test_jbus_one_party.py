"""One party acts on a word of the user's, a bot-chat word carries the bot's message it answers,
and a hold is its party's (dup-work-fixes).

Five of the user's words since 10-22 were acted on by two parties, a shell with no session and the
root home, which queued duplicate rows, misread short replies and approved over a hold. The tests
replay those cases through the real command, the real view server and the faked T3 Code server
of `test_jbus_kitchen`: a shell is a directory with no session, and the home is the kitchen's
checkout with its session.
"""

import pytest

from jbus import acts, queue, word
from test_jbus_acts import CHAT, Route, bot_go
from test_jbus_kitchen import RAN, SESSION, sends
from test_jbus_queue import add, rows

ASKED = "Which of the KPIs with no instrument yet do you want first: Telemetry or cap spells?"
TELEMETRY = ("--evidence", "bot-chat:t107u/bf6bc991", "--words", "Telemetry", "--answers", ASKED)
HOME, MESSAGE = "mcp:a-home", "a-message-of-his"
REF = f"{HOME}/{MESSAGE}"
TM = ("tm-drift-s4", "tm-capped-spells", "tm-lab-records")


@pytest.fixture
def route(kitchen):
    made = Route(kitchen)
    yield made
    made.close()


@pytest.fixture(autouse=True)
def home_id(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")


def keep(kitchen, *argv):
    """Keep a word of the user's from the bot's chat, as the bot's helper did, and return its
    id."""
    code, out = kitchen.main("word", "--to", "demo", *argv)
    assert code == 0, out
    return out.strip().rsplit(" ", 1)[-1]


def shell(kitchen):
    """Run what follows as a shell with no session, in a directory of its own."""
    desk = kitchen.root / "tmp"
    desk.mkdir(exist_ok=True)
    kitchen.monkeypatch.chdir(desk)
    kitchen.monkeypatch.delenv(queue.SESSION, raising=False)
    return desk


def home(kitchen):
    """Run what follows as the home, its checkout and its session."""
    kitchen.monkeypatch.chdir(kitchen.checkout)
    kitchen.monkeypatch.setenv(queue.SESSION, SESSION)


def approve(kitchen, slug, *basis):
    argv = ("--project", "demo", "queue", "approve", slug, *basis)
    return kitchen.main(*argv)


def test_0803_a_shell_approves_tm_rows_on_a_word_and_the_homes_approve_on_it_is_refused(kitchen):
    for slug in TM:
        add(kitchen, slug, approve=False)
    said = keep(kitchen, *TELEMETRY)
    desk = shell(kitchen)
    assert approve(kitchen, "tm-drift-s4", "--word", said)[0] == 0
    assert approve(kitchen, "tm-capped-spells", "--word", said)[0] == 0
    home(kitchen)
    code, out = approve(kitchen, "tm-lab-records", "--word", said)
    refused = (
        f"refused: word {said} was acted on by a shell in {desk}: tm-capped-spells, tm-drift-s4"
    )
    assert (code, out) == (1, refused + "\n")
    assert rows(kitchen)["tm-lab-records"]["approved"] == ""
    (last,) = [one for one in acts.read(kitchen.state) if one["outcome"] == "refused"]
    assert (last["action"]["subject"], last["line"]) == ("tm-lab-records", refused)


def test_the_same_party_approves_a_second_row_on_its_own_word(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    said = keep(kitchen, *TELEMETRY)
    assert approve(kitchen, "alpha", "--word", said)[0] == 0
    assert approve(kitchen, "beta", "--word", said)[0] == 0
    assert all(rows(kitchen)[slug]["approval"]["ref"] == said for slug in ("alpha", "beta"))


def test_one_session_in_a_subfolder_is_the_same_party(kitchen):
    for slug in ("alpha", "beta", "gamma"):
        add(kitchen, slug, approve=False)
    said = keep(kitchen, *TELEMETRY)
    home(kitchen)
    assert approve(kitchen, "alpha", "--word", said)[0] == 0
    assert kitchen.main("queue", "hold", "beta")[0] == 0
    sub = kitchen.checkout / "sub"
    sub.mkdir()
    kitchen.monkeypatch.chdir(sub)
    assert approve(kitchen, "gamma", "--word", said)[0] == 0
    code, out = approve(kitchen, "beta", "--word", said)
    assert code == 0, out


def test_a_follow_up_rules_go_is_no_act_on_the_word(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    add(kitchen, "gamma", approve=False)
    said = keep(kitchen, *TELEMETRY)
    shell(kitchen)
    assert approve(kitchen, "alpha", "--word", said)[0] == 0
    home(kitchen)
    code, out = approve(kitchen, "beta", "--follows", "alpha")
    assert code == 0, out
    shell(kitchen)
    assert approve(kitchen, "gamma", "--word", said)[0] == 0


def test_a_t3_message_one_party_acted_on_is_not_acted_on_by_another(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "queue the missing")
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    desk = shell(kitchen)
    assert approve(kitchen, "alpha", "--message", REF)[0] == 0
    home(kitchen)
    code, out = approve(kitchen, "beta", "--message", REF)
    assert (code, out) == (1, f"refused: word {REF} was acted on by a shell in {desk}: alpha\n")
    assert rows(kitchen)["beta"]["approved"] == ""


def test_the_users_own_message_that_names_the_row_is_never_refused(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "go alpha and beta")
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    shell(kitchen)
    assert approve(kitchen, "alpha", "--message", REF)[0] == 0
    home(kitchen)
    code, out = approve(kitchen, "beta", "--message", REF)
    assert code == 0, out


def test_the_bots_go_on_its_chat_message_is_an_act_on_the_word_kept_for_it(kitchen, route):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    said = keep(kitchen, "--evidence", CHAT, "--words", "both of those", "--answers", ASKED)
    status, answer = bot_go(route, kitchen, "alpha")
    assert status == 200, answer
    code, out = approve(kitchen, "beta", "--word", said)
    assert (code, out) == (1, f"refused: word {said} was acted on by the bot: alpha\n")


def test_two_messages_in_one_bot_chat_are_two_words_each_with_its_own_party(kitchen):
    """On 2026-11-09 the user said two messages in one bot chat. A shell approved a row on the
    first, and every approve on the second was refused as acted on by that shell, since both
    words kept the chat's evidence. Each message is its own word: another party approves the
    second's rows, and the first is still the shell's alone."""
    rt, gs, ps = "rt-node-adapter", "gs-walk-under-part-lines", "proved-side-resume"
    for slug in (rt, gs, ps):
        add(kitchen, slug, approve=False)
    land = "ensure the currenlty briefed and in progress task land"
    chat = ("--evidence", "bot-chat:jstack-chef/t194u", "--answers", "a go waits")
    first = keep(kitchen, *chat, "--words", f"{land} [for: {rt}]")
    second = keep(kitchen, *chat, "--words", f"{land} [for: {gs}, {ps}]")
    assert first != second
    desk = shell(kitchen)
    assert approve(kitchen, rt, "--word", first)[0] == 0
    home(kitchen)
    code, out = approve(kitchen, gs, "--word", first)
    assert (code, out) == (1, f"refused: word {first} was acted on by a shell in {desk}: {rt}\n")
    for slug in (gs, ps):
        code, out = approve(kitchen, slug, "--word", second)
        assert code == 0, out
    table = rows(kitchen)
    assert [table[slug]["approval"]["ref"] for slug in (rt, gs, ps)] == [first, second, second]


def test_tm_drift_s4_held_by_the_home_is_not_approved_by_a_shell(kitchen):
    add(kitchen, "tm-drift-s4")
    held = f"held tm-drift-s4; run {RAN} by the demo home"
    assert kitchen.main("queue", "hold", "tm-drift-s4")[0] == 0
    (act,) = [one for one in acts.read(kitchen.state) if one["action"]["verb"] == "hold"]
    assert act["line"] == held
    shell(kitchen)
    code, out = approve(kitchen, "tm-drift-s4", "--word", kitchen.word())
    assert (code, out) == (
        1,
        f"refused: tm-drift-s4 is held, run {RAN} by the demo home, and a hold is its party's: "
        "the demo home approves it again, or user's own message or pick in T3 Code does\n",
    )
    row = rows(kitchen)["tm-drift-s4"]
    assert (row["held"], row["approved"]) == (True, "")


def test_a_hold_gives_way_to_the_users_own_message_and_to_its_own_party(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta")
    assert kitchen.main("queue", "hold", "alpha")[0] == 0
    assert kitchen.main("queue", "hold", "beta")[0] == 0
    kitchen.t3.says(HOME, MESSAGE, "start it again")
    shell(kitchen)
    assert approve(kitchen, "alpha", "--message", REF)[0] == 0
    home(kitchen)
    assert approve(kitchen, "beta", "--word", kitchen.word())[0] == 0
    assert not any(rows(kitchen)[slug].get("held") for slug in ("alpha", "beta"))
    assert not any("hold" in rows(kitchen)[slug] for slug in ("alpha", "beta"))


def test_a_bot_chat_word_carries_the_bots_message_it_answers_to_the_home(kitchen):
    said = keep(kitchen, *TELEMETRY)
    (one,) = [each for each in acts.read(kitchen.state) if each["id"] == said]
    assert (one["evidence"]["words"], one["evidence"]["answers"]) == ("Telemetry", ASKED)
    (sent,) = sends(kitchen)
    assert sent["message"].endswith(
        f"\n\nTelemetry\n\nThe bot's message these words answer: {ASKED}"
    )
    assert word.load(kitchen.state)[-1].answers == ASKED


def test_answers_goes_only_with_a_bot_chat_word(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "go")
    code, out = kitchen.main("word", "--to", "demo", "--message", REF, "--answers", ASKED)
    assert (code, out) == (1, word.ANSWERS_ALONE + "\n")
    assert word.load(kitchen.state) == []


def test_the_bots_word_carries_the_message_it_answers(kitchen, route):
    add(kitchen, "alpha", approve=False)
    body = {"action": "word", "words": "Telemetry", "answers": ASKED, "evidence": CHAT}
    status, answer = route.act(body)
    assert status == 200, answer
    assert answer["act"]["evidence"]["answers"] == ASKED
    (sent,) = sends(kitchen)
    assert "\n\nTelemetry\n\n" in sent["message"] and sent["message"].endswith(ASKED)
    assert route.act(body | {"answers": 3})[0] == 400
