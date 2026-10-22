"""Sous Chef's decisions on a card come back on the relay's `POST /item`, with the relay's
key: `{project, item, verb, words, by, message, seen_event}` on a card (`jbus.cards.card`),
decided as `jbus item approve` or `jbus item steer` decides it, from `chat` (`decide`). It is
by Sous Chef, as itself, or by the user, with the chat message it was said in and the words
quoted from it, which nothing reads back and which are kept with `checked: false`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import jbus
from jbus import cards, item, steer, wake

Body = dict[str, Any]

SOUS_CHEF = "Sous Chef"
DECISIONS = tuple(cards.ACTIONS.values())
TEXT = ("project", "item", "verb", "by", "seen_event")


def decide(body: Body, now: datetime | None = None) -> tuple[int, Body]:
    """A decision from Sous Chef's chat on a card, `POST /item`, as `jbus item approve` or
    `jbus item steer` decides it, `where: chat`. The answer is the HTTP status and its body.

    `verb` is one of the card's actions: `approve`, `message`, or `hold`, which the card's
    button confirms. `seen_event` is the card's `id`, and the line it names must still be the
    item's last, so a card acted on twice moves the item once. `by` is Sous Chef, which steers
    as itself and approves nothing, or the user, with `message`, the chat message's id or
    link, and `words`, the words quoted from it: those are kept unchecked (`steer.chat`), and
    an approval from chat is taken only for a routine item they name. Anyone else is 403, and
    a decision jbus refuses is 409 with its sentence, as is a verb the item's card does not
    offer now (`cards.actions`): a review item, a merge, a secret or the config, is decided in
    the view and takes no message or hold from chat either.
    """
    wrong = [key for key in TEXT if not isinstance(body.get(key), str) or not body[key].strip()]
    wrong += [key for key in ("words", "message") if not isinstance(body.get(key, ""), str)]
    if wrong:
        return 400, {"refused": f"refused: {', '.join(wrong)} must be text"}
    if body["verb"] not in DECISIONS:
        return 400, {"refused": f"refused: verb is one of {', '.join(DECISIONS)}"}
    try:
        config = jbus.load()
    except jbus.Refused as error:
        return 503, {"refused": str(error)}
    try:
        project = config.project(body["project"])
    except jbus.Refused as error:
        return 404, {"refused": str(error)}
    by, words, message = body["by"], body.get("words", ""), body.get("message", "")
    user = config.user
    if by == user.user:
        if not message.strip() or not words.strip():
            return 403, {
                "refused": f"refused: a decision by {user.user} names the chat message it was "
                "said in and quotes the words"
            }
        basis: steer.Basis | None = steer.chat(message, words, user, now or datetime.now(UTC))
    elif by == SOUS_CHEF:
        basis = None
    else:
        return 403, {"refused": f"refused: a decision from chat is by {SOUS_CHEF} or {user.user}"}
    seen = body["seen_event"].removeprefix(f"{project.name}.")
    state = config.state(project)
    found = item.items(state).get(body["item"])
    if found is not None:
        found = item.judged(state, found)
        if body["verb"] not in cards.actions(found):
            link = cards.view_link(project.name, found.id)
            what = "a review item" if found.risk is item.Risk.REVIEW else str(found.state)
            return 409, {
                "refused": f"refused: {found.id} is {what}, and its card offers no "
                f"{body['verb']} from chat: decide it in the view, {link}"
            }
    box = wake.Box(state, project)
    where = item.Where.CHAT
    try:
        if body["verb"] == cards.ACTIONS[item.Verb.APPROVE]:
            made = steer.approve(
                state,
                box,
                body["item"],
                by=by,
                where=where,
                words=words,
                seen=seen,
                user=user,
                project=project.name,
                basis=basis,
            )
        else:
            made = steer.steer(
                state,
                box,
                body["item"],
                body["verb"],
                words,
                seen,
                by,
                where,
                True,
                user=user,
                basis=basis,
            )
    except jbus.Refused as error:
        return 409, {"refused": str(error)}
    return 200, {"id": made["id"], "item": made["item"], "line": made["line"]}
