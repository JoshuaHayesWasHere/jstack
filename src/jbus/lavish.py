"""Lavish's own state file, read and never written.

Lavish keeps each review page's session in one file, `state.json` under `LAVISH_AXI_STATE_DIR`
or `~/.lavish-axi`: the sessions by their key, each with the page's `file` and its `chat`,
the entries sent on it. An entry is `{role, id, at, tag, text}`, and one whose role is `user`
is what the user sent from the page. No command of Lavish's is on every `PATH`, so jbus reads
the file: for a scout's page that may still wait on the user (`threads`), and for a pick the
user sent from a page, which an approval may rest on (`picked`).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbus import Refused, queue

if TYPE_CHECKING:
    import jsettings

USER = "user"


def path() -> Path:
    return (
        Path(os.environ.get("LAVISH_AXI_STATE_DIR") or Path.home() / ".lavish-axi") / "state.json"
    )


def _kept(where: Path) -> dict[str, Any]:
    """The sessions the file keeps, by key. A file that is not there, or does not parse, is
    `OSError` or `ValueError`."""
    state = json.loads(where.read_text())
    kept = state.get("sessions") if isinstance(state, dict) else None
    if not isinstance(kept, dict):
        raise ValueError(where)
    return {key: one for key, one in kept.items() if isinstance(one, dict)}


def sessions() -> list[dict[str, Any]]:
    """Each session Lavish keeps, or none where the file is not there or does not parse."""
    try:
        return list(_kept(path()).values())
    except (OSError, ValueError):
        return []


def picked(user: jsettings.Settings, ref: str) -> queue.Said:
    """The user's send `<session key>/<entry id>`, read from Lavish's state file now: its text
    on one line, its time in the user's zone, and the page's file.

    An entry whose role is not the user's is refused, and so is one the file does not have,
    with the one thing that is missing.
    """
    key, _, entry = ref.partition("/")
    if not key or not entry:
        raise Refused(f'refused: --page is "<session key>/<entry id>", not {ref}')
    where = path()
    try:
        kept = _kept(where)
    except FileNotFoundError:
        raise Refused(f"refused: Lavish keeps no state file at {where}") from None
    except (OSError, ValueError):
        raise Refused(f"refused: Lavish's state at {where} does not parse") from None
    found = kept.get(key)
    if found is None:
        raise Refused(f"refused: Lavish's state at {where} has no session {key}")
    chat = found.get("chat")
    sent = [one for one in chat if isinstance(one, dict)] if isinstance(chat, list) else []
    mine = [one for one in sent if one.get("id") == entry]
    if not mine:
        raise Refused(f"refused: session {key} has no chat entry {entry}")
    one = mine[-1]
    if one.get("role") != USER:
        role = one.get("role") or "none"
        raise Refused(
            f"refused: chat entry {ref} is not {user.user}'s own: Lavish has it as role {role}"
        )
    words = " ".join(str(one.get("text") or "").split())
    if not words:
        raise Refused(f"refused: chat entry {ref} has no words")
    try:
        at = datetime.fromisoformat(str(one["at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        raise Refused(f"refused: chat entry {ref} has no time Lavish kept") from None
    return queue.Said(words, user.stamp(at), str(found.get("file") or ""), True, ref)
