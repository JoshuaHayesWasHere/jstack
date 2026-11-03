"""A bot-chat word carries the bot's message it answers to the home's start (dup-work-fixes P2).

"Telemetry" from the bot's chat answered the bot's list of KPIs with no instrument yet, which the
home never saw, and the home read it as another record. The root home runs the home skill's own
block that prints what jbus carried to its thread, as `test_gates` runs it, against the real
`jbus` in the kitchen: the line holds the words and the bot's message they answer.
"""

import pytest

from test_gates import ROOT, Home

ASKED = "Which of the KPIs with no instrument yet do you want first: Telemetry or cap spells?"
CHAT = ("--evidence", "bot-chat:t107u/bf6bc991", "--words", "Telemetry")


@pytest.fixture
def home(tmp_path, monkeypatch):
    made = Home(tmp_path, monkeypatch)
    (made.dir / "home-id").write_text(f"{ROOT}\n")
    yield made
    made.kitchen.close()


def test_the_homes_start_shows_a_bot_chat_word_with_the_message_it_answers(home):
    assert home.kitchen.main("word", "--to", "demo", *CHAT, "--answers", ASKED)[0] == 0
    shown = home.word(ROOT)
    assert shown.startswith("user, ") and shown.endswith(f": Telemetry (answers: {ASKED})")


def test_a_bot_chat_word_with_no_answers_shows_its_words_alone(home):
    assert home.kitchen.main("word", "--to", "demo", *CHAT)[0] == 0
    assert home.word(ROOT).endswith(": Telemetry")
