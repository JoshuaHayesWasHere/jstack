"""A brief's `Waived: <the Done when line>, <thread>/<message>` line lets a pull request whose
review says the brief is not met merge only on a word jbus checked (`jbus.port.Port.heard`): the
user's own message in T3 Code, read by the check `jbus queue approve --message` reads a word with,
or a word the bot gave over `POST /act`. A crew's or a home's own message, and a word of the
bot's that a home typed, waive nothing, and neither does a word that does not name the row, or
names it and does not say it waives the line the `Waived:` line quotes. The
tests run the real port against the faked T3 Code server of `test_jbus_kitchen`."""

from datetime import timedelta

import pytest

from jbriefs import meets
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


# `jbus waive`: the home binds the user's plain reply to the rows and lines it asked about.

ASKER = "mcp:" + "-".join("a" * size for size in (8, 4, 4, 4, 12))
LINES = ("the command runs", "the docs say it", "the tests pass")
BRIEF = "Done when:\n" + "".join(f"- {one}\n" for one in LINES) + "Size: S\n"
ASK = "alpha's review says lines 2 and 3 are not met. Waive them?"


@pytest.fixture
def home(kitchen):
    (kitchen.home / "home-id").write_text(f"{ASKER}\n")
    kitchen.brief("alpha", BRIEF)
    return kitchen


def asks(kitchen, message, text, thread=ASKER):
    kitchen.t3.says(
        thread,
        message,
        text,
        type="assistant_message",
        createdBy="agent",
        creationSource="provider",
    )


def waive(kitchen, message, *lines, thread=ASKER):
    return kitchen.main(
        "waive", "alpha", *lines, "--to", "demo", "--message", f"{thread}/{message}"
    )


def brief(kitchen):
    return (kitchen.home / "tasks" / "alpha.md").read_text()


def test_the_users_plain_reply_to_the_homes_ask_waives_the_lines_it_named(home):
    asks(home, "ask", ASK)
    home.t3.says(ASKER, "yes", "yes clear them")
    code, out = waive(home, "yes", "2", "3")
    assert (code, out) == (0, f"waived alpha: lines 2, 3, on {ASKER}/yes\n")
    text = brief(home)
    assert f"Waived: the docs say it, {ASKER}/yes\n" in text
    assert f"Waived: the tests pass, {ASKER}/yes\n" in text
    found = meets.waivers(text)
    assert [one.number for one in found] == [2, 3]
    assert [port.Port().heard(home.checkout, one, "alpha") for one in found] == ["", ""]
    assert port.Port().heard(home.checkout, Waiver(1, f"{ASKER}/yes", LINES[0]), "alpha") != ""
    assert waive(home, "yes", "2", "3")[0] == 0
    assert brief(home) == text


def test_a_message_that_is_not_the_users_own_waives_nothing_by_waive(home):
    asks(home, "ask", ASK)
    home.t3.says(ASKER, "yes", "yes clear them", createdBy="agent", creationSource="mcp")
    code, out = waive(home, "yes", "2")
    assert (code, out.startswith(f"refused: message {ASKER}/yes is not user's own")) == (1, True)
    assert "Waived:" not in brief(home)


def test_a_message_said_before_the_homes_ask_waives_nothing(home):
    home.t3.says(ASKER, "yes", "yes clear them")
    asks(home, "ask", ASK)
    code, out = waive(home, "yes", "2")
    assert code == 1
    assert out.startswith(f"refused: no message of the home comes before {ASKER}/yes")
    assert "Waived:" not in brief(home)


@pytest.mark.parametrize(
    ("ask", "lines", "missing"),
    [
        ("beta's review says lines 2 and 3 are not met. Waive them?", ("2",), "alpha"),
        (ASK, ("1", "2"), "line 1"),
    ],
    ids=["another row", "another line"],
)
def test_a_home_ask_that_did_not_name_the_row_and_its_lines_waives_nothing(
    home, ask, lines, missing
):
    asks(home, "ask", ask)
    home.t3.says(ASKER, "yes", "yes clear them")
    code, out = waive(home, "yes", *lines)
    assert code == 1
    assert out.startswith(f"refused: the home's message before {ASKER}/yes does not name {missing}")
    assert "Waived:" not in brief(home)


def test_a_reply_in_a_thread_that_is_no_homes_waives_nothing(home):
    other = "mcp:" + "-".join("b" * size for size in (8, 4, 4, 4, 12))
    asks(home, "ask", ASK, thread=other)
    home.t3.says(other, "yes", "yes clear them")
    code, out = waive(home, "yes", "2", thread=other)
    assert (code, out.startswith(f"refused: {other} is no home's thread of demo")) == (1, True)
    assert "Waived:" not in brief(home)
