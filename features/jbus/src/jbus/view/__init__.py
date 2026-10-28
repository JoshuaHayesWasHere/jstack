"""`jbus view`: one small server that shows the bus as the line. It takes two writes: the
user's answer to a question, and the user's go for a work item.

It is one process on the standard library's `http.server`, on one port, `PORT`. It always
listens on `127.0.0.1`. When `JBUS_VIEW_HOST` is set, it listens on that address too: an
address of this machine, such as its tailnet one, never every address. While that address is
down, the server serves `127.0.0.1` and tries the address again every `RETRY` seconds.

The routes that read are `routes()`, all `GET`:

- `/`: the page, which sends its requests to the server and nobody else. On every request
  the server joins `page.html`, beside this file, with the script of each panel,
  `panels/<name>/panel.js` (`page`). A bare link to the page shows every project at once,
  from `/stack.json`, and `#/<project>` shows one project, from `/state.json`;
- `/stack.json`: the machine's state, given once, and a summary of each project
  (`state.stack`). The
  server runs the machine's checks once for it, however many projects there are, and asks
  GitHub for the runs of every repo at once;
- `/state.json?project=<project>`: the state of one project (`state.Read.answer`): the
  frame, and what each panel of the first screen builds;
- `/panel/<name>.json?project=<project>`: what one panel builds, for each folder of
  `panels/` (`panels`). With no project, a panel that is `alone` gives what its `stack` builds
  across every project (`App._across`);
- `/feed?project=<project>&after=<id>&wait=<s>`: what `jbus feed` prints, the project's events
  and acts after a cursor, or a reset with what waits on the user, long polled (`feeds`);
- `/digest.json?since=`: what `jbus digest --json` prints (`digest.build`);
- `/task/<slug>/github`: a task's pull request and its checks (`github.GitHub.pull`);
- `/healthz`: `{"ok": true}`.

The two writes are `WRITES`, `POST /answer` and `POST /approve`. Each acts on the one project
that `?project=` names. A write that names no project, or one the state directory does not
have, gets 404. A panel may take writes of its own, `POST /panel/<panel>/<write>`, held to the
same checks (`panels`). One more write, `POST /usage`, names no project: it keeps an event of the
page, the view opened, a route, an item opened or an action taken (`usage`). `jbus view usage`
counts them, and `jbus view pace` gives the median seconds to each first action, week on week.

The body of `/answer` is JSON. Its `numbers` are the questions to close. When it closes one
question only, it also has the name of the `option` picked and the user's own `words`. The
server closes each number through `questions.answer`, as the user of the settings, at the
server's clock, in `WHERE`. That function's rules decide who may answer, and they let a
question be answered once. The server has no copy of them. An answer keeps the default when
it has no words and its option is the default that the thread took, or when it has no
option at all. The server reads which option is the default from the question's record, never from
the page. More than one number is a batch, and a batch only takes defaults. The server
sends an answer that does not keep the default to the thread that asked, once, in the same
request (`questions.carry`). Where the user's answer does not reach that thread, the
server closes the record all the same. The server's reply says why, and the next pass sends
the user's answer. The server returns `closed` and
`refused`. Each is a list with one entry for each number, and each entry has one sentence,
`say`. It refuses a question that was
answered before, and gives that question's `first` answer. The status is 200 where a
question closed and 409 where none did.

The body of `APPROVE`, `POST /approve`, is JSON with two fields: `item`, the item's id, and
`seen_event`, the item's last line as the page showed it. The server decides none of it, and
calls `jbus.item.approve`, whose rules are the only ones. It passes the user of the settings as
the one who approves, and the view as the place, said at the server's clock. The server refuses
a go whose `seen_event` is not the item's last line, and returns the line that came after it.
So a second POST of the same go gets 409, and the server writes nothing. Any other refusal is
409 too, and an item the project does not have is 404. The server returns `at`, the `item`, one
sentence, `say`, and the item's `state` and `last_event`. Those two are what the record has
after the write, or after the refusal.

Any other path is 404, and any other method is 405. A request whose `Host` header is not one
of the server's own names is 403. The server's own names are these, each at the server's
port: its two addresses, `localhost`, and each name in `JBUS_VIEW_NAMES`. The host of each
origin in `JBUS_VIEW_ORIGINS` is one too, with the scheme's default port or no port. Such
an origin, as `https://<host name>`, belongs to a proxy that passes the `Host` header on.
At the start, the server refuses an origin unless it is `http://` or `https://` followed by
a host and an optional port (`origin`). Either write is 403 too unless its `Origin` header
is the server's own address, and so is a count. For one of the server's names, the own address is
`http://<Host>`, with the name that the `Host` header gives. For the host of an origin, the
own address is exactly that origin. So
only the server's own page can write. No answer has a CORS header. The server sends each
answer with `no-store`, so no browser or proxy may store it. There is no sign-in. Anyone
who reaches the port may answer and approve, as any shell of this machine may with
`jbus answer` and `jbus item approve`.

To read, the server reads no config of jbus and no secret. `reader` is the `Config` the
server builds the digest with. Its config directory is `os.devnull`, which has no file
under it. Its projects are the ones the state directory names. The one file of settings
the server reads is jstack's own (`jsettings`). From it the server takes two things. The
first is the user's time zone, which the server gives to a time that has no zone. The
second is the user's name, which the server gives each answer and go. Only a write that
has an answer or a word to send loads jbus's config and the stored sign-in to T3 Code,
as a pass does. Neither is in any answer: the server takes the config's secrets out of what
T3 Code said (`jbus.redact`). A slug in an address must be a slug of the queue.
`jbus.view.clean` says what an answer may contain.

The server runs the code that is on disk, and says which code it runs (`Code`). Every
`CHECK` seconds it looks at the files it runs: the modules it has loaded from its own
checkout, and the files beside this one. It skips the page and the panels' scripts, since it
reads those on every request. Where one file is newer than the server's start, the server
tries the code on disk with `python -c STARTS` as a child process. The child imports the
module that `jbus view` starts through. That module loads this package too, and every
panel (`state.keys`). So a panel that does not load counts as code that does not start, and
so does a panel that gives a key another panel gives. The server loads the panels once,
when it starts (`App`). A folder that has become a panel since then, or stopped being one,
counts as newer code on disk. Where the new code starts, the server ends with `NEWER_CODE`,
so that the unit starts it again. Where it does not start, the server keeps serving, and
`/state.json` says so. The server then runs the trial again at each check, because its
result can change for a reason other than the newer files, such as a module nobody has
loaded yet.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import jbus
import jsettings
from jbus import Refused, digest, record, stop, verbs
from jbus.bind import NoLookup
from jbus.view import feeds, panels, shot, state, usage
from jbus.view.clean import ANY, clean, keep
from jbus.view.github import GitHub
from jbus.view.state import Sources
from jbus.view.writes import (
    ACT,
    APPROVE,
    HTML,
    NOT_FOUND,
    WRITES,
    Answer,
    Writes,
    reader,
    said,
)

__all__ = ["CHECK", "PORT", "App", "Code", "Doors", "Refused", "Sources", "doors"]

PORT = 4388
NEWER_CODE = 75
LOOPBACK = "127.0.0.1"
RETRY = 60.0
CHECK = 30.0
TRIAL = 60
PAGE = Path(__file__).with_name("page.html")
FONT = Path(__file__).with_name("font.woff2")
ROOT = Path(__file__).parents[2]
STARTS = "import jbus.cli, jbus.view.state; jbus.view.state.keys()"
MARK = "PANEL_SCRIPTS;"
FIXED = (
    "/",
    "/font.woff2",
    "/stack.json",
    "/feed",
    "/state.json",
    "/digest.json",
    "/task/<slug>/github",
    "/healthz",
)
BODY = 65536
POSTS = (*WRITES, ACT, usage.USAGE)


def posted(path: str) -> bool:
    """Whether a path takes a POST: one of `POSTS`, or a panel's write (`panels.WRITE`)."""
    return path in POSTS or panels.WRITE.fullmatch(path) is not None


POLICY = (
    "default-src 'none'; font-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
DEFAULT = {"http": "80", "https": "443"}
_ORIGIN = re.compile(r"(https?)://([a-z0-9-]+(?:\.[a-z0-9-]+)*|\[[0-9a-f:.]+\])(?::([0-9]{1,5}))?")
_TASK = re.compile(r"/task/([a-z0-9][a-z0-9._-]*)/github")
_PANEL = re.compile(rf"/panel/({panels.NAME.pattern})\.json")
_CHECK = {"name": None, "state": None, "started": None, "completed": None}
_SEEN = {
    "threads": None,
    "thread_status": None,
    "thread_updated": None,
    "live": None,
    "gone": None,
    "checks": None,
    "check": _CHECK,
}
_THREAD = {key: None for key in record.THREAD}
_WAITS = {
    key: None
    for key in (
        "kind",
        "key",
        "line",
        "since",
        "slug",
        "number",
        "question",
        "default",
        "home",
        "url",
    )
} | {"unblocks": [None]}
_HOOK = {
    "failed_wakes": None,
    "last_error": None,
    "outbox": None,
    "sign_in": None,
    "sweep": None,
}
DIGEST = {
    "at": None,
    "since": None,
    "token_expires": None,
    "projects": {
        ANY: {
            "rows": [{column: None for column in digest.COLUMNS} | {"depends": [None]}],
            "merged": [{"slug": None, "pr": None, "at": None}],
            "done": [{"slug": None, "at": None}],
            "pulls": [{"number": None, "slug": None, "url": None, "waits": None}],
            "by_rule": [{"slug": None, "rule": None, "follows": None, "at": None}],
            "waiting": [_WAITS],
            "routine": [{"at": None, "event": None, "slug": None, "line": None}],
            "sweep": None,
            "stops": {
                "open": [{column: None for column in stop.SHOWN}],
                "outside": {ANY: None},
            },
        }
    },
    "status": {
        "last_pass": None,
        "token_expires": None,
        "projects": {ANY: _HOOK},
        "streaks": {ANY: {"key": None, "count": None, "since": None, "alerted": None}},
        "homes_off_bus": [None],
        "pass": {
            "started": None,
            "ended": None,
            "seconds": None,
            "projects": {ANY: {"seen": None, "rows": {ANY: _SEEN}, "threads": [_THREAD]}},
        },
    },
}


def routes(found: tuple[panels.Panel, ...] | None = None) -> tuple[str, ...]:
    """Every address the server answers: the fixed ones, and one for each panel's folder."""
    found = panels.found() if found is None else found
    return (*FIXED, *(f"/panel/{panel.name}.json" for panel in found))


def page(found: tuple[panels.Panel, ...]) -> bytes:
    """The page, one document: `page.html` with each panel's script in place of `MARK`.

    Each script runs in a function of its own, which gets `panel` as its argument: the one
    call that says what the panel draws. The panel's name is its folder's name, and its
    `panel.py` says whether the panel is on the first screen, so a script names neither.
    """
    scripts = ""
    for panel in found:
        script = panel.script.read_text().replace("</script", "<\\/script")
        named = f"panels({json.dumps(panel.name)}, {json.dumps(panel.first)})"
        scripts += "(function (panel) {\n" + script + "\n})(" + named + ");\n"
    return PAGE.read_text().replace(MARK, scripts, 1).encode()


def _loaded() -> list[str]:
    """The file of each module this process has loaded."""
    return [
        file for module in list(sys.modules.values()) if (file := getattr(module, "__file__", None))
    ]


class Code:
    """Which code serves requests: when the server started, and what on disk is newer than that.

    It looks at the files that the server runs and reads only once. Those are each module the server
    has loaded from under `root`, which is its checkout, and each file in `beside`, which is
    the directory of this package. It leaves out the page. A file that is gone counts as
    newer. `panels` is the names of the panels the server loaded. The folders of `beside`'s
    `panels/` that are panels now may differ from those names. When they differ, the directory
    of the panels counts as newer. For example, they differ once someone writes the second
    file of a new folder. It does not look at the `panel.py` of a folder that is not a panel yet.
    """

    def __init__(
        self,
        root: Path = ROOT,
        beside: Path = PAGE.parent,
        loaded: Callable[[], Iterable[str]] = _loaded,
        panels: tuple[str, ...] | None = None,
    ) -> None:
        self.root, self.beside, self.loaded, self.panels = root, beside, loaded, panels
        self.started = time.time()
        self.error = ""

    def newer(self) -> frozenset[tuple[Path, int]]:
        """Each file the server runs whose copy on disk is newer than the server's start, with
        the file's time."""
        files = {Path(file) for file in self.loaded()}
        files = {file for file in files if file.is_relative_to(self.root)}
        try:
            files |= {file for file in self.beside.iterdir() if file.is_file() and file != PAGE}
        except OSError:
            pass
        found = set()
        if self.panels is not None and panels.names(self.beside / "panels") != self.panels:
            found.add((self.beside / "panels", 0))
        for file in files:
            try:
                changed = file.stat().st_mtime_ns
            except OSError:
                changed = 0
            if not changed or changed > self.started * 1e9:
                found.add((file, changed))
        return frozenset(found)

    def said(self) -> dict[str, Any]:
        return {"started": self.started, "stale": bool(self.newer()), "error": self.error}

    def _trial(self) -> str:
        """Why the code on disk does not start, or nothing where it starts. To try it, a child of
        this interpreter imports the module that `jbus view` starts through. The child writes
        nothing."""
        try:
            tried = subprocess.run(
                [sys.executable, "-c", STARTS],
                capture_output=True,
                text=True,
                timeout=TRIAL,
                env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired:
            return f"its import did not end in {TRIAL} s"
        except OSError as error:
            return f"{sys.executable} could not be run: {error.strerror}"
        if tried.returncode == 0:
            return ""
        return (tried.stderr.strip().splitlines() or [f"exit status {tried.returncode}"])[-1]

    def due(self) -> bool:
        """Whether the server should end now: a file it runs is newer, and the code on disk
        starts. While a file is newer, the server tries the code at every check."""
        newer = bool(self.newer())
        why = self._trial() if newer else ""
        self.error = f"the code on disk does not start: {why}" if why else ""
        return newer and not why


class App(Writes):
    """What the server answers to a `GET` and to its two writes, on either address.

    The app's panels are the panel folders that exist when it starts. It loads each of them
    once. When two panels give the same key, the app does not start. The app reads only a
    panel's script again on every request.
    `config` loads jbus's config, and only a write that has an answer to send calls it."""

    def __init__(
        self,
        sources: Sources,
        clock: Callable[[], datetime] | None = None,
        config: Callable[[], jbus.Config] = jbus.load,
    ) -> None:
        self.sources = sources
        self.clock = clock or (lambda: datetime.now(UTC))
        self.config = config
        self.panels = panels.found()
        state.keys(self.panels)
        self.code = Code(panels=tuple(panel.name for panel in self.panels))
        self.github = GitHub(self.clock)

    def _project(self, query: dict[str, list[str]]) -> str | None:
        """The project an address names with `?project=`, or None where it names no project,
        or names one the state directory does not have."""
        asked = query.get("project", [""])[-1]
        return asked if asked and asked in state.projects(self.sources) else None

    def _stack(self) -> dict[str, Any]:
        """What `/stack.json` contains. The server asks for the runs of every repo at once, each
        in a thread of its own, so no repo waits on another's `gh`. The summaries then use the
        kept answers."""
        names = state.projects(self.sources)
        repos = sorted({state.repo(self.sources, name) for name in names} - {""})
        with ThreadPoolExecutor(max_workers=max(1, len(repos))) as pool:
            asked = dict(zip(repos, pool.map(self.github.runs, repos), strict=True))

        def runs(repo: str):
            return asked.get(repo) or self.github.runs(repo)

        built = state.stack(self.sources, self.clock(), runs, self.code.said(), self.panels, names)
        return clean(built, tuple(repos))

    def _across(self, name: str) -> dict[str, Any] | None:
        """What `/panel/<name>.json` with no project holds for a panel that is `alone`: what its
        `stack` gives across every project, cut to its shape, and how each project's sources it
        names are now. Its `answer` is the frame alone. None for any other name."""
        panel = next((one for one in self.panels if one.name == name and one.alone), None)
        if panel is None:
            return None
        now, code, names = self.clock(), self.code.said(), state.projects(self.sources)
        shared: dict[Any, Any] = {}
        runs = self.github.runs
        base = state.Read(self.sources, "", now, runs, code, self.panels, shared)
        reads = [
            state.Read(
                *(self.sources, one, now, runs, code, self.panels, shared),
                merged=self.github.merged,
                landed=self.github.landed,
            )
            for one in names
        ]
        built = {
            "at": state.iso(now),
            "panel": name,
            "data": keep(panel.data.stack(base, reads, {"at": state.iso(now)}), panel.shape),
            "sources": [
                one | {"project": read.name} for read in reads for one in read.read_by(panel)
            ],
        }
        return clean(built, tuple(sorted({state.repo(self.sources, one) for one in names} - {""})))

    def get(self, path: str, query: dict[str, list[str]]) -> Answer:
        if path == "/":
            return Answer(200, page(self.panels), HTML)
        if path == "/font.woff2":
            return Answer(200, FONT.read_bytes(), "font/woff2")
        if path == "/healthz":
            return said(200, {"ok": True})
        if path == "/stack.json":
            return said(200, self._stack())
        if path == "/feed":
            return feeds.answer(self.sources, query, self.clock, self.github.runs, self.panels)
        if path == "/digest.json":
            try:
                since = digest.since(query.get("since", [""])[-1] or None, self.sources.user)
            except ValueError:
                return said(400, {"error": "since is not a time"})
            config = reader(self.sources)
            built = keep(digest.build(config, since, self.clock()), DIGEST)
            repos = tuple(state.repo(self.sources, project.name) for project in config.projects)
            return said(200, clean(built, repos))
        task, panel = _TASK.fullmatch(path), _PANEL.fullmatch(path)
        if panel and not query.get("project", [""])[-1]:
            built = self._across(panel[1])
            return NOT_FOUND if built is None else said(200, built)
        name = self._project(query)
        if name is None or not (task or panel or path == "/state.json"):
            return NOT_FOUND
        repo = state.repo(self.sources, name)
        if not task:
            read = state.Read(
                self.sources,
                name,
                self.clock(),
                self.github.runs,
                self.code.said(),
                self.panels,
                merged=self.github.merged,
                landed=self.github.landed,
            )
            built = read.asked(panel[1]) if panel else read.answer()
            return NOT_FOUND if built is None else said(200, clean(built, (repo,)))
        pulls = state.pulls(self.sources, name)
        if task[1] not in pulls:
            return NOT_FOUND
        return said(200, clean(self.github.pull(repo, task[1], pulls[task[1]]), (repo,)))

    def _count(self, body: bytes) -> Answer:
        """One event of the page (`usage`), written from names the server has."""
        drawers = (panel.name for panel in self.panels)
        try:
            one = usage.line(body, drawers, state.projects(self.sources), self.clock())
        except Refused as error:
            return said(400, {"error": str(error).removeprefix("refused: ")})
        self.sources.state_dir.mkdir(parents=True, exist_ok=True)
        usage.append(self.sources.state_dir / usage.FILE, one, self.clock())
        return said(200, {"counted": True})

    def post(
        self, path: str, query: dict[str, list[str]], body: bytes, authorization: str = ""
    ) -> Answer:
        """One of the writes: an answer, a go, or a count of what the page opened, or the bot's
        act, which no page sends, so it has no `Origin` to check and its key is its one test."""
        if path == usage.USAGE:
            return self._count(body)
        name = self._project(query)
        if path == ACT:
            return self.act(name, body, authorization) if name else NOT_FOUND
        named = panels.WRITE.fullmatch(path)
        if named and name:
            take = next((p.writes for p in self.panels if p.name == named[1]), {}).get(named[2])
            return take(self, name, body) if take else NOT_FOUND
        if path not in WRITES or not name:
            return NOT_FOUND
        if path == APPROVE:
            return self._approve(name, body)
        return self._answer(name, body)


class Handler(BaseHTTPRequestHandler):
    server_version = "jbus-view"
    sys_version = ""

    def _send(self, answer: Answer, allow: str = "") -> None:
        self.send_response(answer.status)
        self.send_header("Content-Type", answer.kind)
        self.send_header("Content-Length", str(len(answer.body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if answer.kind == HTML:
            self.send_header("Content-Security-Policy", POLICY)
        if allow:
            self.send_header("Allow", allow)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(answer.body)

    def _own(self) -> frozenset[str]:
        """The origins the server's own page has under the `Host` header, or none where that
        header is not one of the server's. For one of the server's names at its port, the
        origin is `http://<Host>`. Each origin of `JBUS_VIEW_ORIGINS` that is
        `<scheme>://<Host>` is one too, whether or not the Host has the scheme's default
        port."""
        host = self.headers.get("Host", "").lower()
        name, _, port = host.rpartition(":")
        named = port == str(self.server.server_port) and name.strip("[]") in self.server.names
        might = {f"{scheme}://{host.removesuffix(f':{at}')}" for scheme, at in DEFAULT.items()}
        return self.server.origins & might | ({f"http://{host}"} if named else set())

    def _known(self) -> bool:
        """Whether the `Host` header is one of this server's names, at its port, or the host
        of one of its origins."""
        return bool(self._own())

    def do_GET(self) -> None:
        if not self._known():
            self._send(said(403, {"error": "this is not the server's name"}))
            return
        path, _, query = self.path.partition("?")
        try:
            answer = self.server.app.get(path, parse_qs(query))
        except Exception:
            traceback.print_exc(file=sys.stderr)
            answer = said(500, {"error": "the server could not answer"})
        self._send(answer)

    def do_POST(self) -> None:
        path, _, query = self.path.partition("?")
        if not posted(path):
            self._refuse()
            return
        if not self._known():
            self._send(said(403, {"error": "this is not the server's name"}))
            return
        if path != ACT and self.headers.get("Origin", "").lower() not in self._own():
            self._send(said(403, {"error": "only the server's own page writes"}))
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if not 0 <= length <= BODY:
            self._send(said(400, {"error": "a write has a body, and a short one"}))
            return
        try:
            body = self.rfile.read(length)
            key = self.headers.get("Authorization", "")
            answer = self.server.app.post(path, parse_qs(query), body, key)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            answer = said(500, {"error": "the server could not answer"})
        self._send(answer)

    def _refuse(self) -> None:
        only = "POST" if posted(self.path.partition("?")[0]) else "GET"
        self._send(said(405, {"error": f"this address only takes {only}"}), allow=only)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("do_"):
            return self._refuse
        raise AttributeError(name)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self._send(said(code, {"error": message or "the request could not be read"}))

    def log_message(self, format: str, *args: Any) -> None:
        return


class Door(NoLookup, ThreadingHTTPServer):
    """A listener that binds without asking DNS for a name of its address (`jbus.bind`)."""

    daemon_threads = True
    allow_reuse_address = True
    app: App
    names: frozenset[str]
    origins: frozenset[str]


class Door6(Door):
    address_family = socket.AF_INET6


class Doors:
    """The server's one or two listeners, on one port, and the thread that tries the second
    address again.

    Every `check` seconds `serve` looks whether the code on disk is newer, and ends if so."""

    def __init__(
        self,
        app: App,
        port: int = PORT,
        host: str | None = None,
        names: tuple[str, ...] = (),
        origins: tuple[str, ...] = (),
        retry: float = RETRY,
        check: float = CHECK,
    ) -> None:
        self.app, self.port, self.host, self.names, self.retry = app, port, host, names, retry
        self.origins, self.check = origins, check
        self._open: list[Door] = []
        self._closed = threading.Event()
        self._lock = threading.Lock()

    def _door(self, address: str) -> Door:
        kind = Door6 if ipaddress.ip_address(address).version == 6 else Door
        door = kind((address, self.port), Handler)
        door.app = self.app
        door.names = frozenset({LOOPBACK, "localhost", *(self.host or LOOPBACK,), *self.names})
        door.origins = frozenset(self.origins)
        threading.Thread(target=door.serve_forever, args=(0.05,), daemon=True).start()
        return door

    def _second(self) -> bool:
        """Open the second address. False where it cannot be opened now."""
        with self._lock:
            if self._closed.is_set():
                return True
            try:
                self._open.append(self._door(self.host))
            except OSError:
                return False
        return True

    def _again(self) -> None:
        while not self._closed.wait(self.retry):
            if self._second():
                print(f"jbus view: listening on {self.host}:{self.port} too", flush=True)
                return

    def open(self) -> None:
        """Open `127.0.0.1`, and the second address when there is one. Opening `127.0.0.1` must
        succeed."""
        if self.host is not None:
            try:
                everywhere = ipaddress.ip_address(self.host).is_unspecified
            except ValueError:
                raise Refused(f"refused: JBUS_VIEW_HOST {self.host!r} is not an address") from None
            if everywhere:
                raise Refused(f"refused: JBUS_VIEW_HOST {self.host} is every address, name one")
        try:
            self._open.append(self._door(LOOPBACK))
        except OSError as error:
            raise Refused(f"refused: {LOOPBACK}:{self.port} cannot be opened: {error}") from error
        if self.host in (None, LOOPBACK):
            return
        if not self._second():
            print(
                f"jbus view: {self.host}:{self.port} cannot be opened, serving {LOOPBACK} "
                f"and trying again every {self.retry:g} s",
                flush=True,
            )
            threading.Thread(target=self._again, daemon=True).start()

    def addresses(self) -> list[tuple[str, int]]:
        with self._lock:
            return [door.server_address[:2] for door in self._open]

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            for door in self._open:
                door.shutdown()
                door.server_close()
            self._open.clear()

    def serve(self) -> int:
        """Open the listeners and serve until something stops the process. The server also ends
        when the code on disk is newer than the running code and a trial of that code starts.
        It then ends with `NEWER_CODE`."""
        self.open()
        for address, port in self.addresses():
            print(f"jbus view: listening on {address}:{port}", flush=True)
        try:
            while not self._closed.wait(self.check):
                if self.app.code.due():
                    print("jbus view: the code on disk is newer and starts, ending", flush=True)
                    self.close()
                    return NEWER_CODE
        except KeyboardInterrupt:
            self.close()
        return 0


def origin(text: str) -> str:
    """One origin of `JBUS_VIEW_ORIGINS`, as a browser sends it: `http://` or `https://`, a
    host, and a port only where it is not the scheme's default. It refuses anything else."""
    found = _ORIGIN.fullmatch(text.lower())
    port = int(found[3] or DEFAULT[found[1]]) if found else 0
    if not 0 < port < 65536:
        raise Refused(f"refused: JBUS_VIEW_ORIGINS {text!r} is not an origin, as https://<host>")
    scheme, host = found[1], found[2]
    return f"{scheme}://{host}" if str(port) == DEFAULT[scheme] else f"{scheme}://{host}:{port}"


def _sources() -> Sources:
    """The state directories `jbus` itself uses, and the user of jstack's settings."""
    home = Path.home()
    try:
        user = jsettings.load()
    except jsettings.Invalid as error:
        raise Refused(f"refused: {error}") from error
    return Sources(
        state_dir=jbus.state_dir(),
        home_dir=Path(os.environ.get("JBUS_HOME_DIR") or home / ".local" / "state" / "home"),
        user=user,
    )


def doors(port: int = PORT) -> Doors:
    """The server the environment sets up: `JBUS_VIEW_HOST`, `JBUS_VIEW_NAMES` and
    `JBUS_VIEW_ORIGINS`, over the state directories `jbus` itself uses."""
    sources = _sources()
    names = tuple(name.strip() for name in os.environ.get("JBUS_VIEW_NAMES", "").split(","))
    origins = (one.strip() for one in os.environ.get("JBUS_VIEW_ORIGINS", "").split(","))
    return Doors(
        App(sources),
        port,
        host=os.environ.get("JBUS_VIEW_HOST") or None,
        names=tuple(name.lower() for name in names if name),
        origins=tuple(origin(one) for one in origins if one),
    )


def _port(shown: argparse.ArgumentParser) -> None:
    shown.add_argument(
        "what",
        nargs="?",
        choices=("usage", "pace"),
        help="with usage, count each event the page kept; with pace, give the median seconds "
        "from page load to each first action, this week against last",
    )
    shown.add_argument("--port", type=int, default=PORT, help="the one port it listens on")
    usage.arguments(shown)


def _run(args: argparse.Namespace) -> int:
    """Serve the page, or with `usage` or `pace`, print what it kept."""
    if args.what != "usage" and args.since:
        raise Refused("refused: --since is for jbus view usage")
    if args.what is None:
        return doors(args.port).serve()
    sources = _sources()
    path, now = sources.state_dir / usage.FILE, datetime.now(UTC)
    if args.what == "pace":
        return usage.pace(path, sources.user, now)
    return usage.report(path, sources.user, now, args)


VERBS = (
    verbs.Verb(
        "view",
        "serve the bus as a page, read-only",
        _port,
        lambda args, _: _run(args),
        abbrev=False,
        config=False,
    ),
    verbs.Verb(
        "view-shot",
        "write a PNG of one route of jbus view",
        shot.arguments,
        lambda args, _: shot.run(args),
        config=False,
    ),
)
