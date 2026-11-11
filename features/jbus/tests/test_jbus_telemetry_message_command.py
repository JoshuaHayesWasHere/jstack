"""The command a user's message opens with, and whether it is a door or a skill
(`jbus.telemetry.messages.command`), as the store keeps them: labels only, no word of the text."""

import contextlib
from datetime import timedelta

from jbus import telemetry
from test_jbus_telemetry import NOW, T3, Machine, word

TEXTS = {
    "m-door": "/home parser-fix go",
    "m-door-codex": "$scout why the parser is slow",
    "m-skill": "/ketchup what landed overnight",
    "m-skill-codex": "$principle-attack-the-premise the queue is too long",
    "m-tagged": "<command-message>sharpen</command-message>\n<command-name>/sharpen</command-name>",
    "m-builtin": "/compact keep the brief",
    "m-nameless": "<command-message></command-message> and then words",
    "m-text": "why is the parser slow?",
}


def test_each_typed_message_keeps_the_command_it_opens_with_and_whether_it_is_a_door(
    tmp_path, monkeypatch
):
    """A message that opens with a door keeps it as `door`, one that opens with a skill as
    `skill`, whether typed as `/name` or `$name`; a command's tags that name none keep no command;
    a text, an assistant's message and a word keep none; and no byte of the store is a text."""
    machine = Machine(tmp_path, monkeypatch)
    t3, home = T3(), "mcp:home-a"
    t3.thread(home, "alpha-id")
    for minute, (key, text) in enumerate(TEXTS.items()):
        t3.say(key, home, NOW + timedelta(minutes=minute), text=text)
    t3.say("r-door", home, NOW + timedelta(minutes=10), text="/home again", role="assistant")
    word(machine, "alpha", "w-said", NOW + timedelta(minutes=11), text="/scout the parser")
    machine.build()

    with contextlib.closing(machine.store()) as store:
        labels = store.execute(
            "SELECT key, kind, command, command_kind FROM messages ORDER BY at"
        ).fetchall()
    assert labels == [
        ("m-door", "command", "/home", "door"),
        ("m-door-codex", "command", "/scout", "door"),
        ("m-skill", "command", "/ketchup", "skill"),
        ("m-skill-codex", "command", "/principle-attack-the-premise", "skill"),
        ("m-tagged", "command", "/sharpen", "skill"),
        ("m-builtin", "command", "/compact", "builtin"),
        ("m-nameless", "command", None, None),
        ("m-text", "text", None, None),
        ("r-door", None, None, None),
        ("word:w-said", "text", None, None),
    ]
    for path in machine.state_dir.glob(f"{telemetry.FILE}*"):
        held = path.read_bytes()
        assert not [text for text in TEXTS.values() if text.encode() in held]
