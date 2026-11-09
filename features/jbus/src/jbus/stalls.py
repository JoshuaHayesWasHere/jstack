"""The stall spells `children` keeps in `stalls.json`, and the items of `jbus needs` they give.

`waiting` reads the items here and not from `children`, whose imports (`record`, then `owed`,
then `word`) come back to `waiting`: this module imports nothing of jbus's but its JSON reader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jbus import read_json

STALL = "home-stall"
FILE = "stalls.json"


def stalled(state: Path) -> list[dict[str, str]]:
    """The items of `waiting-on-user.json` for each home whose spell came to `asked`: a home jbus
    started again on a fresh thread that stalled again. Each is the user's, on `jbus needs`, and
    wakes no thread (`jbus.wakes.need_items`)."""
    kept: dict[str, Any] = read_json(state / FILE, {})
    return [
        {
            "kind": "stalled",
            "key": f"stalled:{name}",
            "line": f"{STALL} {name}: the home {name} is quiet with work out after jbus nudged it "
            f"twice and started it again on a fresh thread, since {spell.get('since', '')}",
            "slug": f"home-{name}",
        }
        for name, spell in sorted(kept.items())
        if isinstance(spell, dict) and spell.get("step") == "asked"
    ]
