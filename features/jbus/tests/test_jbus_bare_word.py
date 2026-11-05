"""A bare bot-chat word, one that keeps no bot's message it answers and names no row by its slug,
is refused where it is carried, at `jbus word`, and where it is acted on, at a home's approve
(word-guard-bare-botchat).

On 11-03 the words t130u and t126u reached the root home as "Telemetry"-like replies with
nothing beside them, and the home guessed what they meant and queued and approved rows of its
own. The tests drive the real `jbus word`, the bot's own route `POST /act`, and `jbus queue
approve`, and make a bare word the one way it can still be there: kept before the route refused
one (word-guard-act-route).
"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

import jbus
from jbus import acts, party, passes, queue, word
from test_jbus_acts import CHAT, Route
from test_jbus_kitchen import sends
from test_jbus_one_party import ASKED, HOME, MESSAGE, REF, approve, home, keep, shell
from test_jbus_queue import add, rows

BARE = ("--evidence", "bot-chat:t130u/f6022e47", "--words", "Telemetry")
VOICE = ("--evidence", "bot-chat:t136u/voice:call-1", "--words", "go on that")


@pytest.fixture
def route(kitchen):
    made = Route(kitchen)
    yield made
    made.close()


@pytest.fixture(autouse=True)
def home_id(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")


def words(kitchen):
    return [one for one in acts.read(kitchen.state) if one["action"]["verb"] == "word"]


def test_jbus_word_refuses_a_bare_bot_chat_word_and_keeps_and_sends_nothing(kitchen):
    add(kitchen, "alpha", approve=False)
    code, out = kitchen.main("word", "--to", "demo", *BARE)
    assert code == 1, out
    assert (code, out) == (1, word.BARE_WORD + "\n")
    assert out.startswith("refused: ") and out.count("\n") == 1
    assert "--answers" in out and "[for: <slug>]" in out
    assert words(kitchen) == [] and sends(kitchen) == []


def test_jbus_word_refuses_a_bot_chat_word_that_names_only_a_slug_no_row_has(kitchen):
    add(kitchen, "ci-speed-race-1", approve=False)
    code, out = kitchen.main(
        "word", "--to", "demo", "--evidence", CHAT, "--words", "go [for: ci-speed-race]"
    )
    assert code == 1, out
    assert (code, out) == (1, word.BARE_WORD + "\n")
    assert words(kitchen) == [] and sends(kitchen) == []


def test_a_bot_chat_word_with_answers_is_kept_and_sent(kitchen):
    said = keep(kitchen, *BARE, "--answers", ASKED)
    (one,) = words(kitchen)
    assert (one["id"], one["evidence"]["answers"]) == (said, ASKED)
    (sent,) = sends(kitchen)
    assert sent["threadId"] == "home-1" and sent["message"].endswith(ASKED)


def test_a_bot_chat_word_that_names_a_row_is_kept_and_sent(kitchen):
    add(kitchen, "alpha", approve=False)
    said = keep(kitchen, "--evidence", CHAT, "--words", "Telemetry [for: alpha]")
    (one,) = words(kitchen)
    assert (one["id"], one["evidence"]["answers"]) == (said, "")
    (sent,) = sends(kitchen)
    assert sent["message"].endswith("\n\nTelemetry [for: alpha]")


def test_a_voice_word_with_answers_is_kept_and_sent(kitchen):
    said = keep(kitchen, *VOICE, "--answers", ASKED)
    (one,) = words(kitchen)
    assert (one["id"], one["evidence"]["ref"]) == (said, "t136u/voice:call-1")
    assert len(sends(kitchen)) == 1


def test_the_users_own_t3_message_needs_no_answers_and_no_slug(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "Telemetry")
    said = keep(kitchen, "--message", REF)
    (one,) = words(kitchen)
    assert (one["id"], one["evidence"]["source"]) == (said, "t3-message")
    assert len(sends(kitchen)) == 1


def bot_word(route, words, **more):
    """A word of the user's kept by the bot's own route."""
    status, said = route.act({"action": "word", "words": words, "evidence": CHAT} | more)
    assert status == 200, said
    return said["act"]["id"]


def recorded(words):
    """A bare word the bot's route kept before it refused one, kept as that route kept it."""
    config = jbus.load()
    now = datetime.now(UTC)
    run = passes.Pass(config, config.project("demo"), now, lambda _: None)
    chat = party.chat(CHAT)
    heard = replace(
        chat, words=words, said_at=config.user.stamp(now), said_in=f"bot-chat {chat.ref}"
    )
    return word.keep(run, party.BOT, heard).id


def test_the_bots_route_refuses_a_bare_word_and_keeps_and_sends_nothing(kitchen, route):
    add(kitchen, "alpha", approve=False)
    for words in ("Telemetry", "go [for: alph]"):
        body = {"action": "word", "words": words, "evidence": CHAT}
        assert route.act(body) == (409, {"error": word.BARE_WORD})
        assert route.act(body | {"answers": "   "}) == (409, {"error": word.BARE_WORD})
    assert acts.read(kitchen.state) == [] and word.load(kitchen.state) == []
    assert sends(kitchen) == []


def test_the_bots_route_keeps_and_sends_a_word_with_answers(kitchen, route):
    add(kitchen, "alpha", approve=False)
    said = bot_word(route, "Telemetry", answers=ASKED)
    (one,) = words(kitchen)
    assert (one["id"], one["evidence"]["answers"]) == (said, ASKED)
    (sent,) = sends(kitchen)
    assert sent["threadId"] == "home-1" and sent["message"].endswith(ASKED)


def test_the_bots_route_keeps_and_sends_a_word_that_names_a_row(kitchen, route):
    add(kitchen, "alpha", approve=False)
    said = bot_word(route, "Telemetry [for: alpha]")
    (one,) = words(kitchen)
    assert (one["id"], one["evidence"]["answers"]) == (said, "")
    (sent,) = sends(kitchen)
    assert sent["message"].endswith("\n\nTelemetry [for: alpha]")


def test_the_homes_approve_on_a_bare_bot_chat_word_is_refused(kitchen):
    add(kitchen, "gap-telemetry", approve=False)
    said = recorded("Telemetry")
    home(kitchen)
    code, out = approve(kitchen, "gap-telemetry", "--word", said)
    assert code == 1, out
    refused = queue.BARE.format(ref=said, slug="gap-telemetry", user="user")
    assert (code, out) == (1, refused + "\n")
    assert "gap-telemetry" in out and "through the bot" in out
    assert rows(kitchen)["gap-telemetry"]["approved"] == ""
    (last,) = [one for one in acts.read(kitchen.state) if one["outcome"] == "refused"]
    assert (last["action"]["subject"], last["line"]) == ("gap-telemetry", refused)


def test_the_homes_approve_on_a_word_naming_another_row_is_refused(kitchen, route):
    add(kitchen, "ci-speed-race-1", approve=False)
    add(kitchen, "ci-speed-race-2", approve=False)
    said = bot_word(route, "yes [for: ci-speed-race-1]")
    home(kitchen)
    assert approve(kitchen, "ci-speed-race-1", "--word", said)[0] == 0
    code, out = approve(kitchen, "ci-speed-race-2", "--word", said)
    assert code == 1, out
    assert (code, out) == (
        1,
        queue.BARE.format(ref=said, slug="ci-speed-race-2", user="user") + "\n",
    )
    assert rows(kitchen)["ci-speed-race-2"]["approved"] == ""


def test_the_homes_approve_holds_on_a_bot_chat_word_with_answers_or_naming_the_row(kitchen, route):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    answered = bot_word(route, "Telemetry", answers=ASKED)
    named = bot_word(route, "go [for: beta]")
    home(kitchen)
    code, out = approve(kitchen, "alpha", "--word", answered)
    assert code == 0, out
    code, out = approve(kitchen, "beta", "--word", named)
    assert code == 0, out
    assert rows(kitchen)["alpha"]["approval"]["ref"] == answered
    assert rows(kitchen)["beta"]["approval"]["ref"] == named


def test_a_shell_approving_on_a_bare_word_is_not_newly_refused(kitchen):
    add(kitchen, "alpha", approve=False)
    said = recorded("Telemetry")
    shell(kitchen)
    code, out = approve(kitchen, "alpha", "--word", said)
    assert code == 0, out
    assert rows(kitchen)["alpha"]["approval"]["ref"] == said


def test_a_row_already_approved_on_a_bare_word_is_left_as_it_is(kitchen):
    add(kitchen, "alpha", approve=False)
    said = recorded("Telemetry")
    shell(kitchen)
    assert approve(kitchen, "alpha", "--word", said)[0] == 0
    was = rows(kitchen)["alpha"]
    home(kitchen)
    code, out = approve(kitchen, "alpha", "--word", said)
    assert code == 0 and out.startswith(f"{queue.ALREADY} alpha"), out
    assert rows(kitchen)["alpha"] == was
