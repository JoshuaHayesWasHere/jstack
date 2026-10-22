"""Read Lavish's own state file, and never write it.

Lavish keeps each review page's session in one file, `state.json` under `LAVISH_AXI_STATE_DIR`
or `~/.lavish-axi`. The file holds the sessions by their key. Each session has the page's
`file` and its `chat`, the entries sent on that page. An entry is `{role, id, at, tag, text}`,
and an entry whose role is `user` is what the user sent from the page. No command of Lavish's
is on every `PATH`, so jbus reads the file itself. jbus reads the file for two things: a
scout's page that may still wait on the user (`threads`), and a pick that the user sent from
a page, which an approval may depend on (`picked`).
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
    """Return the sessions the file keeps, by key. Raise `OSError` when the file does not
    exist, and `ValueError` when it does not parse."""
    state = json.loads(where.read_text())
    kept = state.get("sessions") if isinstance(state, dict) else None
    if not isinstance(kept, dict):
        raise ValueError(where)
    return {key: one for key, one in kept.items() if isinstance(one, dict)}


def sessions() -> list[dict[str, Any]]:
    """Return each session Lavish keeps, or none when the file does not exist or does not
    parse."""
    try:
        return list(_kept(path()).values())
    except (OSError, ValueError):
        return []


def picked(user: jsettings.Settings, ref: str) -> queue.Said:
    """Read the entry `<session key>/<entry id>` that the user sent, in Lavish's state file
    as it is now. Return its text on one line, its time in the user's zone, and the page's
    file.

    The function refuses an entry whose role is not the user's, and an entry that the file
    does not have. The refusal names the one thing that is missing.
    """
    key, _, entry = ref.partition("/")
    if not key or not entry:
        raise Refused(f'refused: --page is "<session key>/<entry id>", not {ref}')
    where = path()
    try:
        kept = _kept(where)
    except FileNotFoundError:
        raise Refused(f"refused: Lavish keeps no state file at {where}") from None
    except OSError:
        raise Refused(f"refused: Lavish's state at {where} cannot be read") from None
    except ValueError:
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
    page = str(found.get("file") or "")
    if not page:
        raise Refused(f"refused: session {key} keeps no page file")
    return queue.Said(words, user.stamp(at), page, True, ref)
