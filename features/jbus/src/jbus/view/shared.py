"""One build at a time of each answer the server builds, and a bound on how long a request
waits for it.

A build of `/stack.json`, of a project's state or of the feed's needs is seconds of Python, and
Python runs one thread's code at a time. So when each request built its own answer, requests that
came faster than a build ended each started one more, every build got slower, and the clients
gave up while the server went on building for them: the server stopped answering at all.

Now a request joins the build of its answer that is running, or starts one in a thread of its own,
and waits for it at most `PATIENCE` seconds. A request still waiting then takes the last answer
that build gave, or `Busy` where there is none yet, and the build goes on for the next request.
So however many requests come, each answer has one build running at most.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable
from typing import Any

PATIENCE = 6.0
"""Under the page's own wait for a read, 8 s, so the page hears an answer before it gives up."""


class Busy(Exception):
    """The answer's first build has not ended in the time a request waits."""


class _Run:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None


class Shared:
    """The build running for each answer, and the last answer each build gave."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._kept: dict[Hashable, Any] = {}
        self._running: dict[Hashable, _Run] = {}

    def get(self, key: Hashable, build: Callable[[], Any], patience: float = PATIENCE) -> Any:
        """The answer `key` names: what the build running for it gives within `patience`
        seconds, or else the last answer built for it. Raise `Busy` where none was built yet,
        and what the build raised where it failed."""
        with self._lock:
            run = self._running.get(key)
            if run is None:
                run = self._running[key] = _Run()
                threading.Thread(target=self._build, args=(key, build, run), daemon=True).start()
        run.done.wait(patience)
        with self._lock:
            if run.done.is_set() and run.error is None:
                return run.value
            if key in self._kept:
                return self._kept[key]
        if run.error is not None:
            raise run.error
        raise Busy

    def _build(self, key: Hashable, build: Callable[[], Any], run: _Run) -> None:
        try:
            run.value = build()
        except BaseException as error:
            run.error = error
        with self._lock:
            if run.error is None:
                self._kept[key] = run.value
            self._running.pop(key, None)
        run.done.set()
