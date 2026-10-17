"""`jbus view`: one small server that shows the bus as the line, and takes one write, the
user's answer to a question.

It is one process on the standard library's `http.server`, on one port, `PORT`. It always
listens on `127.0.0.1`, and on the address in `JBUS_VIEW_HOST` too when that is set: an
address of this machine, as its tailnet one, never every address. With that address down
it serves `127.0.0.1` and tries the address again every `RETRY` seconds.

The routes that read are `routes()`, all `GET`:

- `/`: the page, which asks the server and nobody else. It is `page.html` beside this
  file with the script of each panel in it, `panels/<name>/panel.js`, joined on every
  request (`page`). A bare link to it shows every project at once, from `/stack.json`, and
  `#/<project>` one project, from `/state.json`;
- `/stack.json`: the machine once, and a summary of each project (`state.stack`). The
  machine's checks run once for it, however many projects there are, and the runs of
  GitHub are asked for each repo at once;
- `/state.json?project=<project>`: the state of one project (`state.Read.answer`): the
  frame, and what each panel of the first screen builds;
- `/panel/<name>.json?project=<project>`: what one panel builds, for each folder of
  `panels/` (`panels`);
- `/digest.json?since=`: what `jbus digest --json` prints (`digest.build`);
- `/task/<slug>/github`: a task's pull request and its checks (`github.GitHub.pull`);
- `/healthz`: `{"ok": true}`.

The one write is `WRITE`, `POST /answer`, of the one project `?project=` names: a write
that names none, or one the state directory does not have, is 404. Its
body is JSON: `numbers`, the questions to close, and for one question alone the `option`
picked, by its name, and the user's own `words`. Each number is closed through
`questions.answer`, by the user of the settings, at the server's clock, in `WHERE`: who may
answer and that a question is answered once are that function's rules, and the server has
no copy of them. An answer keeps the default when it has no words and its option is the
default that was taken, or none: so says the record, never the page. More than one number
is a batch, and a batch only takes defaults. An answer that does not keep the default is
sent in the same request (`questions.carry`), once, to the thread that asked. Where it
does not go, the record is closed all the same, the answer says why, and the next pass
sends it. What comes back is `closed` and `refused`, each a list by number with one
sentence, `say`: a question answered before is refused with its `first` answer. The status
is 200 where a question closed and 409 where none did.

Anything else is 404, another method 405, and a request whose `Host` header is not one of
the server's own names is 403: the two addresses, `localhost`, and each name in
`JBUS_VIEW_NAMES`, at the server's port, and the host of each origin in `JBUS_VIEW_ORIGINS`,
with the scheme's default port or none. That is a proxy's origin, as
`https://<host name>`, for a proxy that passes the `Host` header on: an origin
that is not `http://` or `https://`, a host and an optional port is refused at the start
(`origin`). A write is 403 too unless its `Origin` header is the server's own address, the
one its `Host` header names, `http://<Host>`, or for the host of an origin that origin
exactly: only the server's own page writes. No answer has a CORS header, and none may be
stored. There is no sign-in: who reaches the port is who may answer, as any shell of this
machine may with `jbus answer`.

To read, it reads no config of jbus and no secret. `reader` is the `Config` the digest is
built with: its config directory is `os.devnull`, under which there is no file, and its
projects are the ones the state directory names. The one file of settings it reads is
jstack's own (`jsettings`): the user's time zone, which a time with no zone is in, and the
user's name, which an answer is given by. Only a write that has an answer to send loads
jbus's config and the stored sign-in to T3 Code, as a pass does, and neither is in any
answer: what T3 Code said has the config's secrets taken out (`jbus.redact`). A slug in an
address must be a slug of the queue. What an answer may hold is in `jbus.view.clean`.

It runs the code that is on disk, and says which code it runs (`Code`). Every `CHECK`
seconds it looks at the files it runs: the modules it has loaded from its own checkout, and
the files beside this one, but for the page and the panels' scripts, which are read on
every request. Where one is
newer than the server's start it tries the code on disk, `python -c STARTS` as a child:
the module `jbus view` starts through, which loads this package too, and every panel
(`state.keys`), so a panel that does not load, or gives a key another gives, is code that
does not start. The server loads the panels once, when it starts (`App`), and a folder
that becomes a panel or stops being one since is code on disk that is newer. Where that
starts it ends with status 0, for the unit to start it again. Where it does not, the server
keeps serving, `/state.json` says so, and the trial is run again at each check: what it
says rests on more than the files that are newer, as a module nobody has loaded yet.
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
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import jbus
import jsettings
from jbus import Refused, digest, questions, record, t3, verbs, wake
from jbus.view import panels, state
from jbus.view.clean import ANY, clean, keep
from jbus.view.github import GitHub
from jbus.view.state import Sources

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
    "/state.json",
    "/digest.json",
    "/task/<slug>/github",
    "/healthz",
)
WRITE = "/answer"
WHERE = "jbus view"
BODY = 65536
BATCH = 200
SEND = 15.0
HTML, JSON = "text/html; charset=utf-8", "application/json"
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
_WEBHOOK = {"failed_wakes": None, "last_error": None, "outbox": None}
_HOOK = {
    **_WEBHOOK,
    "top_level": _WEBHOOK,
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
            "sweep": None,
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


@dataclass(frozen=True)
class Answer:
    status: int
    body: bytes
    kind: str = JSON


def said(status: int, value: Any) -> Answer:
    return Answer(status, (json.dumps(value, sort_keys=True) + "\n").encode())


NOT_FOUND = said(404, {"error": "not found"})


def routes(found: tuple[panels.Panel, ...] | None = None) -> tuple[str, ...]:
    """Every address the server answers: the fixed ones, and one for each panel's folder."""
    found = panels.found() if found is None else found
    return (*FIXED, *(f"/panel/{panel.name}.json" for panel in found))


def page(found: tuple[panels.Panel, ...]) -> bytes:
    """The page, one document: `page.html` with each panel's script where `MARK` is.

    Each script runs in a function of its own, which is given `panel`: the one call that
    says what the panel draws. The folder's name is the panel's, and whether it is on the
    first screen is what its `panel.py` says, so a script names neither.
    """
    scripts = ""
    for panel in found:
        script = panel.script.read_text().replace("</script", "<\\/script")
        named = f"panels({json.dumps(panel.name)}, {json.dumps(panel.first)})"
        scripts += "(function (panel) {\n" + script + "\n})(" + named + ");\n"
    return PAGE.read_text().replace(MARK, scripts, 1).encode()


def reader(sources: Sources) -> jbus.Config:
    """A `Config` for what only reads the state: the projects the state directory names,
    no server, no webhook, and no config directory."""
    nowhere = Path(os.devnull)
    return jbus.Config(
        server="",
        runtime_mode=None,
        dispatch=False,
        max_running=0,
        warn_days=0,
        wake_alert=0,
        room_passes=0,
        projects=tuple(
            jbus.Project(name, nowhere, name, "", "", "") for name in state.projects(sources)
        ),
        config_dir=nowhere,
        state_dir=sources.state_dir,
        home_dir=sources.home_dir,
        user=sources.user,
    )


def _loaded() -> list[str]:
    """The file of each module this process has loaded."""
    return [
        file for module in list(sys.modules.values()) if (file := getattr(module, "__file__", None))
    ]


class Code:
    """Which code answers: when the server started, and what on disk is newer than that.

    The files it looks at are the ones the server runs and reads once: each module it has
    loaded from under `root`, its checkout, and each file in `beside`, the directory of
    this package, but for the page. One that is gone counts as newer. `panels` is the names
    of the panels the server loaded: where the folders of `beside`'s `panels/` that are
    panels now are not those, as once the second file of a new folder is written, the
    directory of the panels counts as newer. A `panel.py` of a folder that is no panel yet
    is not.
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
        """Each file the server runs that is newer on disk than its start, with its time."""
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
        """Why the code on disk does not start, or nothing where it does: one import of what
        `jbus view` starts through, by a child of this interpreter, which writes nothing."""
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
        """Whether the server is to end now: a file it runs is newer, and the code on disk
        starts. While a file is newer the code is tried at every check."""
        newer = bool(self.newer())
        why = self._trial() if newer else ""
        self.error = f"the code on disk does not start: {why}" if why else ""
        return newer and not why


class App:
    """What the server answers to a `GET` and to its one write, whatever door it came in by.

    The panels are the folders there are when it starts, each loaded once, and a key two of
    them give stops the start. Only a panel's script is read again on every request.
    `config` loads jbus's config. It is called only by a write that has an answer to send."""

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
        """The project an address names with `?project=`, or None where it names none, or one
        the state directory does not have."""
        asked = query.get("project", [""])[-1]
        return asked if asked and asked in state.projects(self.sources) else None

    def _stack(self) -> dict[str, Any]:
        """What `/stack.json` holds. The runs of each repo are asked at once, each in a thread
        of its own, so no repo waits on another's `gh`: the summaries then take what is kept."""
        names = state.projects(self.sources)
        repos = sorted({state.repo(self.sources, name) for name in names} - {""})
        with ThreadPoolExecutor(max_workers=max(1, len(repos))) as pool:
            asked = dict(zip(repos, pool.map(self.github.runs, repos), strict=True))

        def runs(repo: str):
            return asked.get(repo) or self.github.runs(repo)

        built = state.stack(self.sources, self.clock(), runs, self.code.said(), self.panels, names)
        return clean(built, tuple(repos))

    def get(self, path: str, query: dict[str, list[str]]) -> Answer:
        if path == "/":
            return Answer(200, page(self.panels), HTML)
        if path == "/font.woff2":
            return Answer(200, FONT.read_bytes(), "font/woff2")
        if path == "/healthz":
            return said(200, {"ok": True})
        if path == "/stack.json":
            return said(200, self._stack())
        if path == "/digest.json":
            try:
                since = digest.since(query.get("since", [""])[-1] or None, self.sources.user)
            except ValueError:
                return said(400, {"error": "since is not a time"})
            config = reader(self.sources)
            built = keep(digest.build(config, since, self.clock()), DIGEST)
            repos = tuple(state.repo(self.sources, project.name) for project in config.projects)
            return said(200, clean(built, repos))
        name = self._project(query)
        task, panel = _TASK.fullmatch(path), _PANEL.fullmatch(path)
        if name is None or not (task or panel or path == "/state.json"):
            return NOT_FOUND
        repo = state.repo(self.sources, name)
        if not task:
            read = state.Read(
                self.sources, name, self.clock(), self.github.runs, self.code.said(), self.panels
            )
            built = read.asked(panel[1]) if panel else read.answer()
            return NOT_FOUND if built is None else said(200, clean(built, (repo,)))
        pulls = state.pulls(self.sources, name)
        if task[1] not in pulls:
            return NOT_FOUND
        return said(200, clean(self.github.pull(repo, task[1], pulls[task[1]]), (repo,)))

    def _carry(self, name: str, closed: questions.Question, now: datetime) -> tuple[bool, str, str]:
        """Send one answer that differs to the thread that asked, as a pass would. The
        answer is whether it went, and where it did not, why, with no secret in it, and
        what sends it later: nothing does for a slug that was removed from the queue."""
        pass_ = "the next pass sends it"
        hidden: tuple[str, ...] = ()
        try:
            config = replace(
                self.config(), state_dir=self.sources.state_dir, home_dir=self.sources.home_dir
            )
            hidden = config.secrets()
            run = wake.Pass(config, config.project(name), now, say=lambda line: None)
            client = t3.Client(config.server, config.token_path, timeout=SEND)
            went = questions.carry(run, client, closed)
        except (Refused, OSError) as error:
            return False, jbus.redact(str(error).removeprefix("refused: "), hidden), pass_
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            return False, f"the send failed ({type(error).__name__})", pass_
        if went.told:
            return True, "", ""
        if not went.message:
            return False, f"{closed.slug} was removed from the queue", ""
        if not went.thread:
            why = f"{closed.slug} has no Thread: line in a brief or request"
            return False, why, "a pass sends it once one names its thread"
        how = "T3 Code refused it" if went.refused else "T3 Code did not answer"
        return False, jbus.redact(f"{how} ({went.error})", hidden), pass_

    def _close(
        self, name: str, number: int, option: str, words: str, now: datetime
    ) -> tuple[bool, dict[str, Any]]:
        """Close one question. The answer is whether it closed, and what the page is told."""
        user, state_dir = self.sources.user, self.sources.state(name)
        held = {one.number: one for one in questions.load(state_dir)}
        one = held.get(number)
        options = one.options if one else ()
        picked = [each for each in options if state.text(each.name) == option]
        if one and option and not picked:
            say = f"Question {number} has no option of that name, and nothing changed."
            return False, {"number": number, "say": say, "first": None}
        keeps = not words and (not picked or picked[0].default)
        taken = [each.name for each in options if each.default] + ([one.default] if one else [])
        if keeps:
            given = next((word for word in taken if word.strip()), "the default")
        else:
            named = [] if not picked or (picked[0].default and words) else [picked[0].name]
            given = ". ".join([*named, *([words] if words else [])])
        try:
            closed = questions.answer(
                state_dir,
                number,
                given,
                by=user.user,
                at=user.stamp(now),
                where=WHERE,
                keeps=keeps,
                user=user,
            )
        except Refused as error:
            first = one.answer if one else None
            first = first or next(
                (q.answer for q in questions.load(state_dir) if q.number == number), None
            )
            say = (
                f"Question {number} was answered already, and nothing changed: {first.line()}."
                if first
                else f"Question {number} did not close: {str(error).removeprefix('refused: ')}."
            )
            kept = {**asdict(first), "line": first.line()} if first else None
            return False, {"number": number, "say": say, "first": kept}
        home = self.sources.home(name)
        thread, role = state.asker(home, closed.slug, state.threads_seen(self.sources, name))
        whose = f"the {role} thread of {closed.slug}" if role else f"the thread of {closed.slug}"
        at = user.clock(now)
        sent, why, later = (False, "", "") if keeps else self._carry(name, closed, now)
        if keeps:
            say = f"Question {number} closed at {at} with its default, and nothing was sent."
        elif sent:
            say = f"Question {number} closed at {at}, and its answer went to {whose}."
        elif later:
            say = (
                f"Question {number} closed at {at} with its answer recorded and not yet sent, "
                f"since {why}: {later}."
            )
        else:
            say = (
                f"Question {number} closed at {at} with its answer recorded, and it goes to "
                f"no thread, since {why}."
            )
        return True, {
            "number": number,
            "slug": closed.slug,
            "keeps": keeps,
            "words": closed.answer.words,
            "sent": sent,
            "why": why,
            "thread": thread if sent else "",
            "role": role,
            "say": say,
        }

    def post(self, path: str, query: dict[str, list[str]], body: bytes) -> Answer:
        """The one write: close each question the body numbers with the user's answer."""
        name = self._project(query)
        if path != WRITE or not name:
            return NOT_FOUND
        try:
            asked = json.loads(body)
            numbers, option, words = asked["numbers"], asked.get("option"), asked.get("words")
            shaped = (
                isinstance(numbers, list)
                and 0 < len(numbers) <= BATCH
                and all(isinstance(n, int) and not isinstance(n, bool) for n in numbers)
                and len(set(numbers)) == len(numbers)
                and (option is None or isinstance(option, str))
                and (words is None or isinstance(words, str))
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            shaped = False
        if not shaped:
            return said(400, {"error": "a write is the numbers to close, an option and words"})
        option, words = option or "", " ".join((words or "").split())
        if len(numbers) > 1 and (option or words):
            return said(400, {"error": "a batch only takes defaults: answer that one by itself"})
        now = self.clock()
        closed, refused = [], []
        for number in numbers:
            went, told = self._close(name, number, option, words, now)
            (closed if went else refused).append(told)
        answer = {"at": state.iso(now), "closed": closed, "refused": refused}
        return said(200 if closed else 409, clean(answer, (state.repo(self.sources, name),)))


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
        """The origins the server's own page has under the `Host` header, none where it is
        not the server's: `http://<Host>` for one of its names at its port, and each origin
        of `JBUS_VIEW_ORIGINS` that is `<scheme>://<Host>`, the scheme's default port in the
        Host or not."""
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
        if path != WRITE:
            self._refuse()
            return
        if not self._known():
            self._send(said(403, {"error": "this is not the server's name"}))
            return
        if self.headers.get("Origin", "").lower() not in self._own():
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
            answer = self.server.app.post(path, parse_qs(query), self.rfile.read(length))
        except Exception:
            traceback.print_exc(file=sys.stderr)
            answer = said(500, {"error": "the server could not answer"})
        self._send(answer)

    def _refuse(self) -> None:
        only = "POST" if self.path.partition("?")[0] == WRITE else "GET"
        self._send(said(405, {"error": f"this address only takes {only}"}), allow=only)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("do_"):
            return self._refuse
        raise AttributeError(name)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self._send(said(code, {"error": message or "the request could not be read"}))

    def log_message(self, format: str, *args: Any) -> None:
        return


class Door(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    app: App
    names: frozenset[str]
    origins: frozenset[str]


class Door6(Door):
    address_family = socket.AF_INET6


class Doors:
    """The server's one or two listeners, on one port, and the thread that tries again.

    `serve` looks every `check` seconds whether the code on disk is newer, and ends."""

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
        """Open `127.0.0.1`, which must open, and the second address when there is one."""
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
        """Open the doors and serve until the process is stopped, or until the code on disk
        is newer than the code that serves and starts: then it ends with `NEWER_CODE`, which
        jbus-view.service starts again."""
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
    host, and a port only where it is not the scheme's default. Anything else is refused."""
    found = _ORIGIN.fullmatch(text.lower())
    port = int(found[3] or DEFAULT[found[1]]) if found else 0
    if not 0 < port < 65536:
        raise Refused(f"refused: JBUS_VIEW_ORIGINS {text!r} is not an origin, as https://<host>")
    scheme, host = found[1], found[2]
    return f"{scheme}://{host}" if str(port) == DEFAULT[scheme] else f"{scheme}://{host}:{port}"


def doors(port: int = PORT) -> Doors:
    """The server as the environment asks for it: `JBUS_VIEW_HOST`, `JBUS_VIEW_NAMES` and
    `JBUS_VIEW_ORIGINS`, over the state directories `jbus` itself uses."""
    home = Path.home()
    try:
        user = jsettings.load()
    except jsettings.Invalid as error:
        raise Refused(f"refused: {error}") from error
    sources = Sources(
        state_dir=Path(os.environ.get("JBUS_STATE_DIR") or home / ".local" / "state" / "jbus"),
        home_dir=Path(os.environ.get("JBUS_HOME_DIR") or home / ".local" / "state" / "home"),
        user=user,
    )
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
    shown.add_argument("--port", type=int, default=PORT, help="the one port it listens on")


VERBS = (
    verbs.Verb(
        "view",
        "serve the bus as a page, read-only",
        _port,
        lambda args, _: doors(args.port).serve(),
        abbrev=False,
        config=False,
    ),
)
