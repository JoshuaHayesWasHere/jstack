"""The view's `/feed` route: the page `jbus feed` prints for one project, after the cursor
`after`, long polled for up to `wait` seconds (`jbus.feed`). The wait holds only the request's
own thread of the server, and the needs come from the server's one build of them at a time
(`jbus.view.shared`)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jbus import cursor
from jbus.view import state
from jbus.view.clean import clean
from jbus.view.writes import NOT_FOUND, Answer, said


def answer(
    sources: state.Sources,
    query: dict[str, list[str]],
    needs: Callable[[str], list[dict[str, Any]]],
) -> Answer:
    """The answer to `/feed?project=<name>`: 404 for a project the state does not have, 400 for
    a wait that is not one, and otherwise the page, with what waits on the user from `needs`."""
    name = query.get("project", [""])[-1]
    if name not in state.projects(sources):
        return NOT_FOUND
    try:
        waits = cursor.seconds(query.get("wait", ["0"])[-1] or "0")
    except ValueError as error:
        return said(400, {"error": str(error)})

    after = query.get("after", [""])[-1]
    page = cursor.wait(sources.state(name), name, after, waits, lambda: needs(name))
    return said(200, clean(page, (state.repo(sources, name),)))
