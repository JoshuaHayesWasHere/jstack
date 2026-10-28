"""The view's `/feed` route: the page `jbus feed` prints for one project, after the cursor
`after`, long polled for up to `wait` seconds (`jbus.feed`). The wait holds only the request's
own thread of the server."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from jbus import feed
from jbus.view import panels, state
from jbus.view.clean import clean
from jbus.view.writes import NOT_FOUND, Answer, said


def answer(
    sources: state.Sources,
    query: dict[str, list[str]],
    clock: Callable[[], datetime],
    runs: Callable[[str], dict[str, Any]],
    found: tuple[panels.Panel, ...],
) -> Answer:
    """The answer to `/feed?project=<name>`: 404 for a project the state does not have, 400 for
    a wait that is not one, and otherwise the page."""
    name = query.get("project", [""])[-1]
    if name not in state.projects(sources):
        return NOT_FOUND
    try:
        waits = feed.seconds(query.get("wait", ["0"])[-1] or "0")
    except ValueError as error:
        return said(400, {"error": str(error)})

    def needs() -> list[dict[str, Any]]:
        return state.needs(sources, name, clock(), runs, found)

    after = query.get("after", [""])[-1]
    page = feed.wait(sources.state(name), name, after, waits, needs)
    return said(200, clean(page, (state.repo(sources, name),)))
