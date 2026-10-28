"""One build at a time of each answer the server builds, and a bound on how long a request
waits for it.

A build of `/stack.json`, of a project's state or of the feed's needs is seconds of Python, and
Python runs one thread's code at a time. So when each request built its own answer, requests that
came faster than a build ended each started one more, every build got slower, and the clients
gave up while the server went on building for them: the server stopped answering at all.

Now each answer has one build running at most. A request takes the answer of a build that began
after it came, so no answer is older than its request: where none runs, it starts one, and where
one runs, it joins the next, which starts once that one ends and which every request that comes
meanwhile shares. A request waits for its build at most `PATIENCE` seconds, then gets `Busy`, and
the server says so on its standard error. What a build raises, each request of it raises.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Hashable
from typing import Any

PATIENCE = 6.0
"""Under the page's own wait for a read, 8 s, so the page hears an answer before it gives up."""


class Busy(Exception):
    """The build a request waits on has not ended in the time a request waits."""


class _Run:
    def __init__(self, build: Callable[[], Any]) -> None:
        self.build = build
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None


class Shared:
    """The build running for each answer, and the one that starts after it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: dict[Hashable, _Run] = {}
        self._next: dict[Hashable, _Run] = {}

    def get(self, key: Hashable, build: Callable[[], Any], patience: float = PATIENCE) -> Any:
        """The answer `key` names, from a build that began after this call, within `patience`
        seconds. Raise `Busy` where it has not ended by then, and what the build raised where it
        failed."""
        with self._lock:
            if key in self._running:
                run = self._next.setdefault(key, _Run(build))
            else:
                run = self._running[key] = _Run(build)
                threading.Thread(target=self._build, args=(key, run), daemon=True).start()
        if not run.done.wait(patience):
            print(f"jbus view: {key} is still building after {patience:g} s", file=sys.stderr)
            raise Busy
        if run.error is not None:
            raise run.error
        return run.value

    def _build(self, key: Hashable, run: _Run | None) -> None:
        """Run the build, then the next one where a request joined it, until none is left."""
        while run is not None:
            try:
                run.value = run.build()
            except BaseException as error:
                run.error = error
            with self._lock:
                after = self._next.pop(key, None)
                if after is None:
                    self._running.pop(key, None)
                else:
                    self._running[key] = after
            run.done.set()
            run = after
