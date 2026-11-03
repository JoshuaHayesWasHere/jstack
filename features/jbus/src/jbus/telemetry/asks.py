"""What a message the user typed asks, as the one label the store keeps of it: `needs` where it
asks what needs the user, `other` where it does not.

The label is worked out of the text as jbus reads it, a T3 Code message (`messages`) or a word
said through the bots' chat or the view (`records`' `acts`), and only the label is kept. The
rule is one pattern (`NEEDS`) over the text in lower case with its runs of white space made one
space: "what", "anything" (and its typos, "anythign") or "something", maybe with "else", then
"need", "needs", "requires", "is waiting on", "waits on" or "blocked on", then "me" or "my".
So "what needs me?", "does anything need me?", "anything else need me?" and "what needs my
input?" ask it. Over the 1,314 messages the user typed by 2026-11-03 it matched 32, each one an
ask of what needs the user, read by hand.

What it leaves out, on purpose: a question about something that needs the user ("why do these
need me?", "why do 7 items need me"), a statement ("none of them need me"), a mention in quotes,
backticks or parentheses (`reduce the "what needs me" questions`, ``the `what needs me` KPI``,
"(what needs me) is the KPI"), and a message that is not plain text (`messages.kind`): a slash
command, whose text is a skill's or a brief's, an answer to a question box, or a resume. What it
misses:

- an ask in other words ("is there anything for me?", "status?", "what's next for me"),
- an ask past the first `HEAD` characters of a long message (none by 2026-11-03),
- an ask to a bot that jbus answers without recording it as a word, which is no message here,
- and a message T3 Code no longer holds when the rules last changed, which keeps no label.

A change to the rule raises `messages.RULES`, so every message is read again, and appends a
migration that clears the cursors of `acts`, as `migrations.v007_asks` and
`migrations.v010_asks_marks` do, so every word is too.
"""

from __future__ import annotations

import re
from typing import Literal

Asks = Literal["needs", "other"]
HEAD = 400
"""How much of a text the user typed is read for its labels, this one and `messages.kind`."""

NEEDS = re.compile(
    r"(?<![\"'“‘`(])\b(?:what|anyth\w*|something)(?:'s|\s+is)?(?:\s+else)?\s+"
    r"(?:needs?|requires?|waiting\s+on|waits\s+on|blocked\s+on)\s+(?:me|my)\b"
)
"""An ask of what needs the user, in the lower-cased text with its white space made single."""


def label(text: str | None) -> Asks:
    """What a typed text asks, by its first `HEAD` characters: `needs` where it asks what needs
    the user, else `other`."""
    said = " ".join((text or "")[:HEAD].split()).lower()
    return "needs" if NEEDS.search(said) else "other"
