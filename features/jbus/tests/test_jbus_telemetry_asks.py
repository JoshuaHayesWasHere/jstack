"""What a message the user typed is about (`jbus.telemetry.asks.surface`), and the one label of it
the store keeps.

The texts are written for the test, each in the form of a kind of message the audit of
2026-11-09 counted by hand (`reports/po-audit-2.html` in the home), none copied from the user.
"""

import contextlib
from datetime import timedelta

import pytest

from jbus import telemetry
from jbus.telemetry import asks
from test_jbus_telemetry import NOW, T3, Machine, dump, word

SAID = {
    "sidebar": (
        "why does the sidebar still show that crew?",
        "the review thread is still open, why?",
        "why are three rows stalled?",
        "this home looks stuck, restart it",
        "jview says two crews are running but nothing moves",
    ),
    "merge": (
        "why has the pull request not merged yet?",
        "CI failed on the docs change again",
        "main is red, what broke it?",
        "why do the checks take 15 minutes?",
        "the PR for the parser has sat for an hour",
    ),
    "approval": (
        "go",
        "approve parser-fix (brief sha 0123456789ab)",
        "yes to question 12",
        '**"jstack question 40: default"**',
        "parser-fix: go",
    ),
    "status": (
        "status?",
        "what is left on the parser work?",
        "how are things going in the docs home?",
        "give me a progress report for today",
        "is everything moving as it should?",
    ),
    "routing": (
        "this row started in the wrong home",
        "which home owns the parser work?",
        "move this row to the docs home",
        "that should have run under a child home",
        "stop the crews that are not in jstack",
    ),
    "needs": (
        "what needs me?",
        "does anything need my input?",
        "anything else need me tonight?",
        "what is waiting on me?",
        "is something blocked on me?",
    ),
    "other": (
        "draw the build flow as a diagram",
        "rename the config key to timeout_s",
        'drop the "sidebar" wording from the readme',
        "why do these need me?",
        "write a scout brief for the font cache",
    ),
}
"""Five texts of each label, the last `other`s a mention in quotes and a question about what
needs the user, which `asks.label` leaves out on purpose."""


PLAIN = (
    "can you check the docs for typos",
    "go through the readme and tighten it",
    "#1 priority is the font cache",
    "we are moving the config to toml",
    "move it to the left of the chart",
    'fix the typo in "PR" on the page',
    "not approved, redo the brief",
)
"""Ordinary requests that use a surface's word in another sense, each `other`."""


@pytest.mark.parametrize("text", PLAIN)
def test_a_surface_word_in_another_sense_is_other(text):
    assert asks.surface(text) == "other"


@pytest.mark.parametrize(
    ("text", "label"), [(text, label) for label, texts in SAID.items() for text in texts]
)
def test_a_typed_text_is_labelled_with_the_surface_it_is_about(text, label):
    assert asks.surface(text) == label


def test_a_surface_past_the_first_head_characters_is_not_read():
    """The store reads only the first `HEAD` characters of a text, so the label is of those."""
    late = "draw the build flow " * (asks.HEAD // 20) + "why is the sidebar stale?"
    assert asks.surface(late) == "other"
    assert asks.surface(late[asks.HEAD :]) == "sidebar"


def test_surface_says_needs_exactly_where_the_asks_label_does():
    """The KPI "what needs me" reads `asks`, so the two labels never disagree on an ask."""
    for text in (text for texts in SAID.values() for text in texts):
        assert (asks.surface(text) == "needs") == (asks.label(text) == "needs"), text


@pytest.fixture
def machine(tmp_path, monkeypatch):
    return Machine(tmp_path, monkeypatch)


def test_the_store_keeps_the_surface_of_each_typed_message_and_no_word_of_it(machine):
    """A message the user typed keeps its surface; a command, an assistant's message and a word
    of `acts`, which keeps no text to read it from, keep none; no byte of the store is a text."""
    t3, home = T3(), "mcp:home-a"
    t3.thread(home, "alpha-id")
    texts = {
        "m-sidebar": SAID["sidebar"][0],
        "m-merge": SAID["merge"][0],
        "m-other": SAID["other"][0],
    }
    for minute, (key, text) in enumerate(texts.items()):
        t3.say(key, home, NOW + timedelta(minutes=minute), text=text)
    t3.say("m-command", home, NOW + timedelta(minutes=5), text="/crew why is CI red")
    t3.say("r-merge", home, NOW + timedelta(minutes=6), text=SAID["merge"][1], role="assistant")
    word(machine, "alpha", "w-said", NOW + timedelta(minutes=7), text=SAID["status"][0])
    machine.build()

    with contextlib.closing(machine.store()) as store:
        labels = store.execute("SELECT key, kind, surface FROM messages ORDER BY at").fetchall()
    assert labels == [
        ("m-sidebar", "text", "sidebar"),
        ("m-merge", "text", "merge"),
        ("m-other", "text", "other"),
        ("m-command", "command", None),
        ("r-merge", None, None),
        ("word:w-said", "text", None),
    ]
    for path in machine.state_dir.glob(f"{telemetry.FILE}*"):
        held = path.read_bytes()
        assert not [text for text in texts.values() if text.encode() in held]


def test_a_store_from_before_the_surfaces_gains_them_as_a_rebuild_has_them(machine):
    """A store built under the rules before `surface`, with no such column nor the later
    `command`, runs `jbus.telemetry.migrations.v016_message_surface` and `v021_message_command`,
    reads every message again and ends as a store built from nothing."""
    from jbus.telemetry import views

    t3, home = T3(), "mcp:home-a"
    t3.thread(home, "alpha-id")
    t3.say("m-merge", home, NOW, text=SAID["merge"][2])
    t3.say("m-approval", home, NOW + timedelta(minutes=1), text=SAID["approval"][1])
    word(machine, "alpha", "w-said", NOW + timedelta(minutes=2), text=SAID["sidebar"][1])
    machine.build()
    with contextlib.closing(machine.store()) as store:
        signed = store.execute("SELECT value FROM meta WHERE name = 'messages'").fetchone()[0]
        dropped = "".join(f"DROP VIEW {name};" for name, _ in reversed(views.VIEWS))
        store.executescript(
            f"{dropped}ALTER TABLE messages DROP COLUMN command_kind;"
            "ALTER TABLE messages DROP COLUMN command;"
            "ALTER TABLE messages DROP COLUMN surface;"
            f"DELETE FROM {telemetry.RAN} WHERE name IN "
            "('v016_message_surface', 'v021_message_command');"
        )
        store.execute(
            "UPDATE meta SET value = ? WHERE name = 'messages'",
            (f"{telemetry.messages.RULES - 1} " + signed.split(" ", 1)[1],),
        )
        store.commit()

    machine.build()

    code, out = machine.run("--rebuild", str(machine.root / "again.sqlite"))
    assert code == 0, out
    assert dump(machine.state_dir / telemetry.FILE) == dump(machine.root / "again.sqlite")
    with contextlib.closing(machine.store()) as store:
        labels = store.execute("SELECT key, surface FROM messages ORDER BY at").fetchall()
    assert labels == [("m-merge", "merge"), ("m-approval", "approval"), ("word:w-said", None)]
