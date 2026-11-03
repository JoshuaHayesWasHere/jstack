"""How a source of the store reads its records out of its file (`records.Source.records`): a log
line by line, and a snapshot by the JSON shape it is written in."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from typing import Any

Row = dict[str, Any]


def json_lines(text: str) -> Iterator[Row]:
    """Each line of a JSON-lines file that is an object, in order."""
    for line in text.splitlines():
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if isinstance(one, dict):
            yield one


def questions(text: str) -> Iterable[Row]:
    """The records of `questions.json`, the objects of its `records` list."""
    held = json.loads(text)
    found = held.get("records", []) if isinstance(held, dict) else []
    return [one for one in found if isinstance(one, dict)]


def listed(text: str) -> Iterable[Row]:
    """The records of a snapshot that is one JSON list of them, as `queue.json` is."""
    held = json.loads(text)
    return [one for one in held if isinstance(one, dict)] if isinstance(held, list) else []


def keyed(name: str) -> Callable[[str], Iterable[Row]]:
    """The records of a snapshot that is one JSON object of records by key, each with its key
    as the field `name`: `merged.json` by slug, `word-sends.json` by word, `reverts.json` by red
    tip."""

    def records(text: str) -> Iterable[Row]:
        held = json.loads(text)
        if not isinstance(held, dict):
            return []
        return [{**one, name: key} for key, one in held.items() if isinstance(one, dict)]

    return records
