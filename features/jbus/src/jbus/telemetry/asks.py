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

What a typed text is about is a second label, its `surface`, which the store keeps of a T3 Code
message of kind `text` alone (`messages.surface`): an act keeps no text past its read, so a word
has none. It is `needs` exactly where `label` says `needs`, so the two never disagree on an ask.
Otherwise the text is read as `label` reads it, its outer bold, quotes and full stop trimmed (a
pasted `**"approve <slug>"**.`), with each mention in double quotes or backticks and each link's
target (an attached image, a quoted reply) left out, and the first of `SURFACES` whose pattern
matches names it. `approval` is tried first, as it reads only the start of a message, where an
answer's word is: "go, and the sidebar is stuck" is an answer that mentions the sidebar.

- `approval`: a message that starts with an answer: "approve" (not "not approved"), "go" (not
  "go through"), "yes", "waive", "lgtm",
  "question 12", "<slug>: go" or "<slug> default", "merge it" or "deploy to prod", a slug alone
  after "remove", "close", "stop" or "rework", an option letter, or "my pick" anywhere. It misses
  an answer that starts otherwise ("you can continue", "clear tmp", "a pick, and also...").
- `sidebar`: "sidebar", "jview", "still open", "stalled", "stale", "stuck", "settled", "quiet",
  "piled up", "not closed", or a short "continue" or "restart". It misses a screenshot of the
  sidebar sent with no such word ("ask me?"), and it takes "stuck" or "stale" said of anything.
- `merge`: "PR", "pull request", "#12", "merge", "CI" (not "ci cd", a home's name), "checks",
  "main is red", "rebase", "macos", "test slots", "bottleneck". It takes every message that
  names a pull request, a new piece of work as much as a complaint.
- `routing`: "wrong home", "which home", a child, root or scoped home, "move this ... to",
  "not in jstack". It takes a request to start a scoped home, and misses "stop this work".
- `status`: "status", "progress", "ketchup", "in flight", "what is left" or "next", "how are
  things going", "is everything moving", "up to date", "what did ... find". It misses most status
  questions, which are asked in words of their own ("can I reboot now?").

Each pattern is a fact of the words, not a judgment of friction: a message about a surface is
counted whether it complains or asks for work. On a held-out 100 of the 624 messages the audit
of 2026-11-09 labelled by hand (scout 2), `surface` agreed with the hand label on 68 of them:
approval 31 of 37, merge 4 of 5, sidebar 9 of 13, status 3 of 11, routing 1 of 2, needs 3 of 4,
other 17 of 28. The scout gave a surface only to a friction message, so a new piece of work about
a pull request is `merge` here and `other` there. The scorecard shows only what agreed on 80% or
more (`jbus.telemetry.measures`).
"""

from __future__ import annotations

import re
from typing import Literal

Asks = Literal["needs", "other"]
Surface = Literal["needs", "approval", "sidebar", "merge", "routing", "status", "other"]
HEAD = 400
"""How much of a text the user typed is read for its labels, this one and `messages.kind`."""

NEEDS = re.compile(
    r"(?<![\"'“‘`(])\b(?:what|anyth\w*|something)(?:'s|\s+is)?(?:\s+else)?\s+"
    r"(?:needs?|requires?|waiting\s+on|waits\s+on|blocked\s+on)\s+(?:me|my)\b"
)
"""An ask of what needs the user, in the lower-cased text with its white space made single."""


_QUOTED = re.compile(r'"[^"]*"|“[^”]*”|`[^`]*`|(?<=\])\([^)\s]*\)?')
"""A mention in double quotes or backticks, which names a surface and is no ask about it, and
the target of a link, such as an attached image's or a quoted reply's."""
_PASTED = re.compile(r'[*\s]*["“`](.*)["”`][*\s.!]*')
"""A whole message the user pasted as exact words, in a pair of quotes, maybe in bold and with a
full stop after them; the words inside are its group."""
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)+"

SURFACES: tuple[tuple[Surface, re.Pattern[str]], ...] = (
    (
        "approval",
        re.compile(
            r"^(?!not\b|never\b)(?:[\w-]+\s+)?approve[ds]?\b"
            r"|^go\b(?!\s+(?:through|over|back|to|into|and)\b)|^(?:yes|yep|yeah|lgtm|waive)\b"
            r"|^(?:[\w-]+\s+)?questions?\s+\d+"
            rf"|^(?:[\w-]+\s+)?{_SLUG}:?\s+(?:go|default)$"
            r"|^(?:merge|deploy|ship|start|build|queue|publish)\s+"
            r"(?:it|them|#?\d+|to\s+prod|by\s+hand)\b"
            rf"|^(?:merge|go)$|^(?:remove|close|stop|rework)\s+{_SLUG}$"
            r"|^(?:option\s+)?[a-d](?:[.,:)]|$)|\bmy pick\b"
        ),
    ),
    (
        "sidebar",
        re.compile(
            r"\bside\s?bar\b|\bjview\b|\bstill\s+(?:open|running|showing|there|in\s+my)\b"
            r"|\bstall(?:ed|s|ing)?\b|\bstale\b|\bstuck\b|\b(?:un)?settled\b|\bquiet\b(?!\s+(?:mode|hours))"
            r"|\bpiled?\s+up\b|\blooks?\s+(?:open|idle)\b|\bnot\s+(?:get\s+)?closed\b"
            r"|^(?:continue|restart|resume)\b.{0,30}$"
        ),
    ),
    (
        "merge",
        re.compile(
            r"\bprs?\b|\bpull\s+requests?\b|/pull/\d|#\d{2,}|\bmerg(?:e|ed|es|ing)\b|\bjmerge\b"
            r"|\bci\b(?!\s*/?\s*cd\b)|\bmac\s?os\b|\b\d+\s+of\s+\d+\s+(?:\w+\s+){0,2}failing\b"
            r"|\bchecks\b|\bcheck\s+(?:runs?|takes?|fail\w*|is\s+red)\b"
            r"|\bmain\s+(?:is\s+|still\s+)*(?:red|broken|not\s+fixed)"
            r"|\bred\s+main\b|\brebas(?:e|ed|ing)\b|\btest\s+slots?\b|\bbottleneck"
        ),
    ),
    (
        "routing",
        re.compile(
            r"\b(?:wrong|which|right)\s+home\b|\b(?:child|root|sub|scoped)[ -]?homes?\b"
            r"|\buncategori[sz]ed\s+(?:home|scope)\b|\bunder\s+(?:the\s+)?root\b(?!\s+(?:dir|folder|of))"
            r"|\bmove\s+(?:this|that|these|them|it)(?:\s+\w+)?\s+(?:to|into|under)\b.{0,30}\b(?:home|scope)\b"
            r"|\b(?:not\s+in|outside\s+of)\s+jstack\b"
        ),
    ),
    (
        "status",
        re.compile(
            r"\bstatus\b(?!\s+(?:line|bar|code|field|column))|\bprogress\b(?!\s+bar)|\bketchup\b|\bcatch\s+me\s+up\b|\bin\s+flight\b"
            r"|\bwhat(?:'s|\s+is|\s+else\s+is)?\s+"
            r"(?:left|next|happening|on\s+the\s+docket|landed)\b"
            r"|\bhow(?:'s|\s+is|\s+are)\s+(?:it|things|we)\s+(?:going|doing)\b"
            r"|\b(?:is|are)\s+(?:it|things|everything|flow|we)\s+(?:still\s+)?(?:moving|flowing)\b"
            r"|\b(?:everything|things|flow|work)\s+(?:is\s+|are\s+)?(?:\w+\s+)?(?:moving|flowing)\b"
            r"|\bwhere\s+are\s+we\b|\bup\s+to\s+date\b|\bwhat\s+can\s+we\s+learn\b"
            r"|\bwhat\s+did\b.{0,40}\bfind\b"
        ),
    ),
)
"""Each surface but `needs` and `other` with its pattern, in the order they are tried."""


def _said(text: str | None) -> str:
    """The first `HEAD` characters of a text, in lower case with its white space made single."""
    return " ".join((text or "")[:HEAD].split()).lower()


def label(text: str | None) -> Asks:
    """What a typed text asks, by its first `HEAD` characters: `needs` where it asks what needs
    the user, else `other`."""
    return "needs" if NEEDS.search(_said(text)) else "other"


def surface(text: str | None) -> Surface:
    """What a typed text is about, by its first `HEAD` characters: `needs` where `label` says
    so, else the first surface of `SURFACES` whose pattern it matches, with a mention in quotes
    or backticks left out, else `other`."""
    if label(text) == "needs":
        return "needs"
    said = _said(text)
    pasted = _PASTED.fullmatch(said)
    said = _QUOTED.sub(" ", pasted[1] if pasted else said.strip("* .!"))
    return next((name for name, pattern in SURFACES if pattern.search(said)), "other")
