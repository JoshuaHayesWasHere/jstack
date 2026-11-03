"""A brief's `Waived: <the Done when line>, <thread>/<message>` line lets a pull request whose
review says the brief is not met merge only on a word jbus checked (`jbus.port.Port.heard`): the
user's own message in T3 Code, read by the check `jbus queue approve --message` reads a word with,
or a word the bot gave over `POST /act`. A crew's or a home's own message, and a word of the
bot's that a home typed, waive nothing, and neither does a word that does not name the row, or
names it and does not say it waives the line the `Waived:` line quotes. The
tests run the real port against the faked T3 Code server of `test_jbus_kitchen`."""

from datetime import timedelta

import pytest

from jbriefs.meets import Waiver
from jbus import acts, party, port
from test_jbus_kitchen import NOW, iso

HOME, MESSAGE = "mcp:a-home", "a-message-of-his"
REF = f"{HOME}/{MESSAGE}"


DOCS = "the docs say it"


def heard(kitchen, ref, slug="alpha", named=DOCS):
    return port.Port().heard(kitchen.checkout, Waiver(2, ref, named), slug)


def test_the_users_own_message_that_names_the_row_waives(kitchen):
    kitchen.t3.says(HOME, MESSAGE, 'waive "the docs say it" for alpha, they ship next week')
    assert heard(kitchen, REF) == ""


@pytest.mark.parametrize(
    "more",
    [
        {"createdBy": "agent", "creationSource": "mcp"},
        {"type": "assistant_message", "createdBy": "agent", "creationSource": "provider"},
    ],
    ids=["a crew's or a home's message", "an agent's reply"],
)
def test_a_message_that_is_not_the_users_own_waives_nothing(kitchen, more):
    kitchen.t3.says(HOME, MESSAGE, "waive the docs say it for alpha", **more)
    assert heard(kitchen, REF).startswith(f"refused: message {REF} is not user's own")


def test_the_users_message_about_another_row_waives_nothing(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "waive the docs say it for beta")
    assert heard(kitchen, REF) == (
        f'refused: the word {REF} ("waive the docs say it for beta") does not name alpha'
    )


@pytest.mark.parametrize(
    "words",
    [
        "go on alpha",
        "waive the tests line for alpha",
        "do not waive anything for alpha, the docs say it",
        "do not waive the docs say it for alpha",
    ],
    ids=[
        "its go, which waives nothing",
        "a waiver of another line",
        "a waive that is not of the line",
        "a waive it says not to",
    ],
)
def test_the_users_message_about_the_row_that_does_not_waive_the_line_waives_nothing(
    kitchen, words
):
    kitchen.t3.says(HOME, MESSAGE, words)
    assert heard(kitchen, REF) == f'refused: the word {REF} ("{words}") does not waive "{DOCS}"'


def keep(kitchen, kind, route, ref, words):
    said = party.Evidence("bot-chat", ref, words, iso(NOW - timedelta(minutes=5)))
    who = party.Party(kind, route)
    made = party.Act(f"w-{kind}", iso(NOW), who, party.Action("word", ""), said, "done", "kept")
    acts._write(kitchen.state, made)


def test_the_bots_word_over_post_act_waives_and_one_a_home_typed_for_it_does_not(kitchen):
    chat = "joshbot/voice:call-1"
    keep(kitchen, "bot", "bot", chat, "alpha: waive the docs say it")
    assert heard(kitchen, chat) == ""
    typed = "joshbot/voice:call-2"
    keep(kitchen, "home", "cli", typed, "alpha: waive the docs say it")
    assert heard(kitchen, typed).startswith(f"refused: T3 Code gave no message {typed}")
