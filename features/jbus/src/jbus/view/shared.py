"""One build at a time of each answer the server builds, a cap on the builds that run at once,
and a bound on how long a request waits for one.

A build of `/stack.json`, of a project's state or of the feed's needs is seconds of Python, and
Python runs one thread's code at a time. So when each request built its own answer, requests that
came faster than a build ended each started one more, every build got slower, and the clients
gave up while the server went on building for them: the server stopped answering at all.

Now each answer has one build running at most, and `BUILDS` builds run at once across every
answer, since more only share the one thread Python runs. A request takes the answer of a build
that began after it came: where none runs, it starts one, and where one runs, it joins the next,
which starts once that one ends and which every request that comes meanwhile shares. A request
waits for its build at most `PATIENCE` seconds. Then it gets the last answer a build of the same
key gave, with that answer's own `at`, as `GitHub` gives its kept answer, and `Busy` only where no
build of the key has given one yet; the server says so on its standard error. What a build raises,
each request of it raises.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Hashable
from datetime import datetime
from typing import Any

from jbus.view import panels, state
from jbus.view.github import GitHub
from jbus.view.writes import Answer, said

PATIENCE = 6.0
"""Under the page's own wait for a read, 8 s, so the page hears an answer before it gives up."""


BUILDS = 2
"""The builds that run at once across every answer."""


class Busy(Exception):
    """The build a request waits on has not ended in the time a request waits, and no build of
    its answer has ended before."""


class _Run:
    def __init__(self, build: Callable[[], Any]) -> None:
        self.build = build
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None


class Shared:
    """The build running for each answer, and the one that starts after it."""

    def __init__(self, builds: int = BUILDS) -> None:
        self._lock = threading.Lock()
        self._builds = threading.Semaphore(builds)
        self._running: dict[Hashable, _Run] = {}
        self._next: dict[Hashable, _Run] = {}
        self._last: dict[Hashable, Any] = {}

    def get(self, key: Hashable, build: Callable[[], Any], patience: float = PATIENCE) -> Any:
        """The answer `key` names, from a build that began after this call, within `patience`
        seconds. Where it has not ended by then, the last answer a build of `key` gave, or `Busy`
        where none has; what the build raised where it failed."""
        with self._lock:
            if key in self._running:
                run = self._next.setdefault(key, _Run(build))
            else:
                run = self._running[key] = _Run(build)
                threading.Thread(target=self._build, args=(key, run), daemon=True).start()
        if not run.done.wait(patience):
            print(f"jbus view: {key} is still building after {patience:g} s", file=sys.stderr)
            with self._lock:
                if key in self._last:
                    return self._last[key]
            raise Busy
        if run.error is not None:
            raise run.error
        return run.value

    def _build(self, key: Hashable, run: _Run | None) -> None:
        """Run the build, then the next one where a request joined it, until none is left."""
        while run is not None:
            try:
                with self._builds:
                    run.value = run.build()
            except BaseException as error:
                run.error = error
            with self._lock:
                if run.error is None:
                    self._last[key] = run.value
                after = self._next.pop(key, None)
                if after is None:
                    self._running.pop(key, None)
                else:
                    self._running[key] = after
            run.done.set()
            run = after


class Built:
    """The answers of the view's `App` that a build of the state gives, each through `shared`."""

    sources: state.Sources
    clock: Callable[[], datetime]
    github: GitHub
    code: Any
    panels: tuple[panels.Panel, ...]
    shared: Shared
    patience: float

    def get(self, path: str, query: dict[str, list[str]]) -> Answer:
        """The answer to a `GET` (`_get`), or 503 where the build it needs has not given one in
        time and none has given one before."""
        try:
            return self._get(path, query)
        except Busy:
            return said(503, {"error": "the server is still building this answer, ask again"})

    def _get(self, path: str, query: dict[str, list[str]]) -> Answer:
        raise NotImplementedError

    def _shared(self, key: Hashable, build: Callable[[], Any]) -> Any:
        """The answer `key` names, from its one build at a time."""
        return self.shared.get(key, build, self.patience)

    def _needs(self, name: str) -> list[dict[str, Any]]:
        """What waits on the user in one project, for the feed (`state.needs`)."""

        def build() -> list[dict[str, Any]]:
            return state.needs(self.sources, name, self.clock(), self.github.runs, self.panels)

        return self._shared(("needs", name), build)

    def _read(self, name: str, panel: str | None) -> dict[str, Any] | None:
        """What `/state.json` holds for one project, or what one panel of it builds."""
        read = state.Read(
            self.sources,
            name,
            self.clock(),
            self.github.runs,
            self.code.said(),
            self.panels,
            merged=self.github.merged,
        )
        return read.asked(panel) if panel else read.answer()
