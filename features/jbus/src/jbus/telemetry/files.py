"""How the text of a record file becomes its records, each a JSON object (`records.Source`).

A log is JSON lines, and a line that is not an object is skipped (`json_lines`). A snapshot is
one JSON document, and each reader here takes the objects out of its own shape: a record that is
not an object is skipped, and a document of another shape gives none.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any


def json_lines(text: str) -> Iterator[dict[str, Any]]:
    """Each line of a JSON-lines file that is an object, in order."""
    for line in text.splitlines():
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if isinstance(one, dict):
            yield one


def questions(text: str) -> Iterable[dict[str, Any]]:
    """Each record of `questions.json`, under its `records`."""
    held = json.loads(text)
    found = held.get("records", []) if isinstance(held, dict) else []
    return [one for one in found if isinstance(one, dict)]


def queue(text: str) -> Iterable[dict[str, Any]]:
    """Each row of `queue.json`, a list."""
    held = json.loads(text)
    return [one for one in held if isinstance(one, dict)] if isinstance(held, list) else []


def merged(text: str) -> Iterable[dict[str, Any]]:
    """Each pull request of `merged.json`, with the slug it is held under."""
    held = json.loads(text)
    if not isinstance(held, dict):
        return []
    return [{**pull, "slug": slug} for slug, pull in held.items() if isinstance(pull, dict)]


def sends(text: str) -> Iterable[dict[str, Any]]:
    """Each send of `word-sends.json`, with the id of the word it is held under."""
    held = json.loads(text)
    if not isinstance(held, dict):
        return []
    return [{**sent, "id": word} for word, sent in held.items() if isinstance(sent, dict)]
