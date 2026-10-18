"""The page of `jbus view`, opened in a headless browser and counted, at the size of a desk's
screen, 1440 by 900, and of a phone's, 390 by 844.

A view's first screen is held to `WORDS`, and every project's to `EVERY`. The shell around
it, the header and the sidebar, is counted apart and held to `SHELL`: the same on every view,
it grows by one name and one count for each project.

Each test starts the real server over a made-up state directory, as `test_jbus_view.py`
does, and puts a small proxy in front of it. The proxy adds a probe to the page: it counts
the words on the first screen, opens every drawer, and writes what it found into the page,
which the browser then prints. The proxy can also stop passing requests on, which is how
the page meets a server that is gone, and it writes down each write the page makes before
it passes it on: a test may do something first, or have the write meet no server. The
browser opens no window under 500 wide, so for the phone the proxy gives it a page that
holds the real one in a frame of the phone's size.

In place of the probe the proxy can add axe, `AXE`: the engine, vendored for these tests
alone in `fixtures/jbus-view/axe.min.js`, and `axe-run.js`, which runs it over the view and
over every drawer it opens, and measures the focus ring of everything a key reaches.

These tests start a browser, so the whole module is marked `browser`: `make check` leaves it
out, and `make check-browser` runs it, nightly and on a release. Each run of it holds the
machine's browser lock, `~/.local/state/locks/browser.lock`, where that file's directory is
there: one browser of these tests is up at a time on the machine, however many runs there are.
A test waits `PATIENCE` seconds for it and then fails with a line that says so. It is a lock of
their own and not the heavy-suite lock, `heavy-suite.lock` beside it, so a run under `flock` on
that one waits on nothing it holds itself. With no `chromium` on `PATH` a desk skips them, and
a runner (GitHub Actions sets `GITHUB_ACTIONS` to true) fails every one: a check that passed
there would say the page was opened. `JSTACK_TEST_BROWSER` names another browser to open it
in. The browser workflow names Google Chrome on GitHub's runner, whose Chromium is a snapshot
build that now and then never starts its virtual time: the page runs on the clock and the
browser never prints it.

Each browser has `LAUNCH` seconds. It runs under `timeout`, in a process group of its own,
which goes whole when it ends or when the test is stopped, and the test fails with a line
that says so: a browser that hangs costs its test that bound, and leaves nothing behind. A
test takes the lock once, waiting up to `PATIENCE` seconds, and browses up to `BROWSES`
times, so its own bound is above all of those, and theirs fail first, by name.

The page is drawn in Liberation Sans, as `FONTS` asks, which a desk and a runner both have: a
desk's own font and a runner's DejaVu Sans set the same words in lines of different widths.
"""

import contextlib
import fcntl
import html
import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import types
import urllib.parse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import jsettings
from jbus import questions, queue, view
from jbus.view import panels
from jbus.view.panels.usage import panel as usage
from test_jbus_view import (
    DRAWN,
    GATE,
    NAMES,
    NOW,
    PIPED,
    REPORTED,
    REQUEST,
    Process,
    Scene,
    Served,
    a_noticed,
    ago,
    asks,
    et,
    free_port,
    iso,
    item,
    kept,
    kinds,
    logged,
    out,
    requested,
    rounded,
    row,
    said_by_him,
    stacked,
    table,
)
from test_jbus_view import folder as panel

NAMED = os.environ.get("JSTACK_TEST_BROWSER", "")
CHROMIUM = (
    shutil.which(NAMED) if NAMED else shutil.which("chromium") or shutil.which("chromium-browser")
)
PAGE = Path(view.__file__).with_name("page.html")
WORDS = 150
EVERY = 250
SHELL = 30
PATIENCE = 240
LAUNCH = 60
STOPPED = (124, 137)
BROWSES = 5
FONTS = Path(__file__).parent / "fixtures" / "jbus-view" / "fonts.conf"
pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]
DESK, PHONE = (1440, 900), (390, 844)
NEEDS = 220
PHONE_NEEDS = 520
FONT = 'src: url("/font.woff2") format("woff2");'
NARROWEST = 500
THUMB = 44
MIDDLE = (900, 900)
LANES = [
    "Queued",
    "Running",
    "Gate",
    "Result",
    "Review",
    "Findings",
    "Second pass",
    "Check",
    "Proof",
    "Rebase",
    "Needs you",
    "Merged",
]
STEP_KEYS = [
    "queued",
    "running",
    "gate",
    "result",
    "review",
    "findings",
    "second",
    "check",
    "proof",
    "rebase",
    "hold",
    "merged",
]
FIRST = ("tea", "jam", "oat", "rye", "fig", "plum", "kale", "leek", "mint", "sage")
SECOND = ("kettle", "saucer", "ladle", "whisk", "platter", "skillet", "colander")
REASON = {
    "result": "no brief has a Result that names it",
    "review": "it has no review yet",
    "findings": "its findings are not handled: the Result has no Fixed line",
    "second": "its fix changed more than the findings named: the second pass is not written",
    "check": "check has not passed",
    "proof": "guarded (touches src/a.py), no proven safety fact at 0123456789ab (step 5)",
    "rebase": "it conflicts with its base",
}
TODAY = {
    "yours": 3,
    "blocked": 6,
    "free": 3,
    "running": 6,
    "gate": 1,
    "result": 1,
    "review": 2,
    "findings": 2,
    "second": 1,
    "check": 1,
    "proof": 1,
    "rebase": 1,
}
FORTY = TODAY | {"blocked": 8, "running": 8, "gate": 2, "result": 2, "review": 3, "findings": 3}
FORTY |= {"second": 2, "check": 2, "rebase": 2, "hold": 1}
FLOWS = {5: (3, 2), 25: (6, 5, 4, 3, 2, 2, 2, 1), 60: (20, 14, 8, 6, 4, 3, 2, 2, 1)}
PROBE = (Path(__file__).parent / "fixtures" / "jbus-view" / "probe.js").read_text()


def slugs():
    return (f"{first}-{second}" for second in SECOND for first in FIRST)


def lineup(scene, counts, merged=30, gates=6):
    """A day of the given size: so many rows on each step, so many merged today, so many
    open gates, and the list of what waits on the user that a pass would have left."""
    names = slugs()
    rows, log, listed, moves = [], [], [], []
    number = 100
    first = next(names)
    for kind, many in counts.items():
        for at in range(many):
            slug = first if (kind, at) == ("yours", 0) else next(names)
            old = et(ago(minutes=20 + 7 * at))
            if kind == "yours":
                rows.append(row(slug, approved="", why="not approved", since=old))
                listed.append(
                    item("approve", f"approve:{slug}", f"approve {slug}: jbus queue approve")
                )
            elif kind == "blocked":
                rows.append(row(slug, depends=[first], why=f"depends on {first}", since=old))
            elif kind == "free":
                rows.append(row(slug, why="no slot", since=old))
            elif kind == "running":
                rows.append(row(slug, "running", thread=f"mcp:{at}"))
                moves.append((slug, "launched", "running", 5 + 9 * at))
            elif kind == "gate":
                rows.append(row(slug, "gate", why="a gate the Chef has", since=old))
                line = f"gate {slug}: which way?"
                listed.append(item("row", f"row:{slug}", line, slug=slug, minutes=122))
            else:
                number += 1
                word = "hold" if kind == "hold" else "wait"
                reason = REASON.get(kind, "needs user, touches skills/crew/SKILL.md")
                rows.append(
                    row(slug, "pr", pr=f"#{number}", checks="passed", why=f"{word}: {reason}")
                )
                if at % 2:
                    log.append(logged(90 + at, word, number, reason))
                    log.append(logged(80 + at, "wait", number, "a check has not finished"))
                log.append(logged(10 + 25 * at, word, number, reason))
                if kind == "hold":
                    listed.append(
                        item("hold", f"#{number}", f"hold {number}: {reason}", number=number)
                    )
    for at in range(merged):
        slug = next(names)
        rows.append(row(slug, "merged", pr=f"#{at + 1}"))
        moves.append((slug, "pr", "merged", 3 + 11 * at))
    scene.queue(rows)
    scene.moves(*moves)
    scene.merge_log(*log, logged(1, "wait", 1, "check has not passed"))
    (scene.home / "gates.md").write_text(
        "\n".join(
            GATE.format(n=n + 1, asked=f"is it {n + 1}?", status="open", default="it is not")
            for n in range(gates)
        )
    )
    scene.waiting(listed)
    return [one["slug"] for one in rows if one["status"] != "merged"]


def flowing(scene, sizes):
    """A queue with so many rows in each wave, in the queue's order, behind a row at a gate
    and beside one that runs. The first row of wave 1 waits on the row at the gate. Every
    other row waits on the row of the wave before that has its place, and each second one
    on the next row of that wave too. It gives back the rows of each wave."""
    names = slugs()
    gate, runs = next(names), next(names)
    rows = [
        row(gate, "gate", why="a gate the Chef has", priority=0),
        row(runs, "running", thread="mcp:1", priority=0),
    ]
    waves = []
    for many in sizes:
        before, wave = (waves[-1] if waves else []), []
        for at in range(many):
            depends = [before[(at + more) % len(before)] for more in range(1 + at % 2) if before]
            if (len(waves), at) == (1, 0):
                depends = [gate]
            wave.append(next(names))
            rows.append(row(wave[-1], depends=list(dict.fromkeys(depends)), priority=len(rows)))
        waves.append(wave)
    scene.queue(rows)
    scene.moves((runs, "launched", "running", 5))
    scene.merge_log()
    scene.waiting([item("row", f"row:{gate}", f"gate {gate}: which way?", slug=gate, minutes=9)])
    return waves


class Proxy:
    """A door in front of the server that adds the probe to the page, and can go dark."""

    def __init__(
        self, upstream, at, task="", pick="", gates=None, probe=True, tap="", walk=None, script=""
    ):
        self.upstream, self.dark, self.states = upstream, False, 0
        self.dark_after = None
        self.asked, self.stacks = [], 0
        self.alter = lambda nth, body: body
        self.alter_state = lambda nth, body: body
        self.refused = ()
        self.writes = []
        self.on_write = lambda nth: None
        asked = f"window.__task = {json.dumps(task)}; window.__pick = {json.dumps(pick)};"
        asked += f"window.__gates = {json.dumps(gates)}; window.__tap = {json.dumps(tap)};"
        asked += f"window.__walk = {json.dumps(walk)};"
        head = f"<script>window.__at = {at}; {asked}{script or PROBE}</script>"
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                proxy.asked.append(self.path)
                if self.path.startswith("/state.json"):
                    proxy.states += 1
                    if proxy.dark_after is not None and proxy.states > proxy.dark_after:
                        proxy.dark = True
                if proxy.dark or self.path.startswith(proxy.refused or ("\0",)):
                    self.send_error(502)
                    return
                if self.path.startswith("/frame/"):
                    wide, high, inside = self.path.split("/")[2:5]
                    inside = html.escape("/" + urllib.parse.unquote(inside), quote=True)
                    size = f"width:{int(wide)}px;height:{int(high)}px"
                    body = f'<body style="margin:0"><iframe src="{inside}" style="border:0;{size}">'
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f"<!doctype html>{body}</iframe></body>".encode())
                    return
                link = http.client.HTTPConnection("127.0.0.1", upstream, timeout=30)
                link.request("GET", self.path, headers={"Host": f"127.0.0.1:{upstream}"})
                answer = link.getresponse()
                body = answer.read()
                link.close()
                if probe and self.path.split("#")[0].split("?")[0] == "/":
                    body = body.replace(b"<head>", b"<head>" + head.encode(), 1)
                if self.path == "/stack.json":
                    proxy.stacks += 1
                    body = json.dumps(proxy.alter(proxy.stacks, json.loads(body))).encode()
                if self.path.startswith("/state.json"):
                    body = json.dumps(proxy.alter_state(proxy.states, json.loads(body))).encode()
                self.send_response(answer.status)
                self.send_header("Content-Type", answer.getheader("Content-Type"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                """A write of the page: written down as the browser sent it, then passed on
                under the server's own name, as a page the server gave would send it."""
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                proxy.writes.append(
                    {
                        "path": self.path,
                        "origin": self.headers.get("Origin"),
                        "kind": self.headers.get("Content-Type"),
                        "body": json.loads(body),
                    }
                )
                if proxy.on_write(len(proxy.writes)) == "dark":
                    self.send_error(502)
                    return
                link = http.client.HTTPConnection("127.0.0.1", upstream, timeout=30)
                named = f"127.0.0.1:{upstream}"
                headers = {"Host": named, "Origin": f"http://{named}"}
                link.request("POST", self.path, body=body, headers=headers)
                answer = link.getresponse()
                said = answer.read()
                link.close()
                self.send_response(answer.status)
                self.send_header("Content-Type", answer.getheader("Content-Type"))
                self.send_header("Content-Length", str(len(said)))
                self.end_headers()
                self.wfile.write(said)

            def log_message(self, *args):
                return

        self.port = free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def browser_lock():
    """The browser lock of the home the run has: read when it is taken, so a test can give
    itself a home of its own."""
    return Path(os.environ["HOME"]) / ".local" / "state" / "locks" / "browser.lock"


@pytest.fixture
def own_home(tmp_path, monkeypatch):
    """A home of the test's own, with a locks directory, so its lock is nobody else's and it
    waits on no lock of the machine's."""
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    locks.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return locks


@contextmanager
def heavy():
    """The machine's browser lock, held while a browser runs.

    It is the file `browser_lock()`, which only these tests take, so one of their browsers is up at
    a time. The run's caller may hold the heavy-suite lock: that is another file, and
    nothing here waits on it. It waits `PATIENCE` seconds for the lock and then fails the
    test with one line: a check that waits without end reads as one that hangs.
    """
    held = browser_lock()
    if not held.parent.is_dir():
        yield
        return
    with open(held, "a") as lock:
        until = time.monotonic() + PATIENCE
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > until:
                    pytest.fail(
                        f"{held} was held for {PATIENCE} s: other runs of these tests had "
                        "a browser up all that time. Run it again."
                    )
                time.sleep(0.2)
        yield


def browse(*arguments):
    """Run the browser headless under the browser lock, and give back what it printed.

    Chromium binds a socket in a directory it makes under `TMPDIR`, and the path of a socket
    holds 107 characters. So the browser gets a short directory of its own, whatever `TMPDIR`
    the run has: a runner's is long.

    `timeout` gives the browser `LAUNCH` seconds and then stops it, and the test fails with
    a line that says so. The browser runs in a process group of its own, which goes whole when
    it ends, also when the test is stopped from outside: Python's own timeout, or
    pytest-timeout's, would stop one process and leave the ones it started.
    """
    command = [CHROMIUM, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom"]
    bounded = ["timeout", "--kill-after=5", str(LAUNCH), *command, *arguments]
    made = tempfile.TemporaryDirectory(prefix="jbus-view-", dir="/tmp", ignore_cleanup_errors=True)
    with made as short:
        env = {**os.environ, "TMPDIR": short, "FONTCONFIG_FILE": str(FONTS)}
        how = {"env": env, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
        with subprocess.Popen(bounded, start_new_session=True, **how) as browser:
            try:
                out, err = browser.communicate(timeout=LAUNCH + 30)
            finally:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(browser.pid, signal.SIGKILL)
    if browser.returncode in STOPPED or browser.returncode < 0:
        pytest.fail(f"the browser did not finish in {LAUNCH} s and was stopped: {err[-2000:]}")
    return subprocess.CompletedProcess(bounded, browser.returncode, out, err)


def address(port, screen, fragment=""):
    """Where the browser finds the page at this size, and the window it needs for it."""
    wide, high = screen
    if wide >= NARROWEST:
        return f"http://127.0.0.1:{port}/{fragment}", screen
    inside = urllib.parse.quote(fragment, safe="")
    return f"http://127.0.0.1:{port}/frame/{wide}/{high}/{inside}", (NARROWEST, high)


def look(
    scene,
    tmp_path,
    at=600,
    budget=6000,
    fragment="",
    task="",
    dark_after=None,
    screen=DESK,
    pick="",
    gates=None,
    on_write=None,
    port=None,
    route=None,
    alter=None,
    tap="",
    walk=None,
    alter_state=None,
    script="",
    system="light",
):
    """Open the page in the browser and give back what the probe found. The server is one
    started here over the scene, or the one that listens on `port`. The page is the scene's
    project, `#/demo`, or the `route` given, as `#/` for every project, and `fragment` is
    more of the address after it, as `theme=dark`. `alter` is given the count of
    each answer of `/stack.json` and its body, and gives back the body the page gets,
    `alter_state` the same for `/state.json`, and
    `tap` selects what the probe taps 3 s after the page loads, and `walk` is the steps the
    probe takes from 2.5 s on, one each 0.5 s, as `back` or `open:task:oat-bowl`. `system`
    is the scheme the browser asks for, `light` or `dark`. With
    `gates`, the
    probe answers them, and what it found has each write the page made under `writes`.
    `on_write` is called with the count of each write before it is passed on, and a write
    it answers `dark` for meets no server."""
    served = None if port else Served(scene)
    proxy = Proxy(port or served.port, at, task, pick, gates, tap=tap, walk=walk, script=script)
    proxy.on_write = on_write or proxy.on_write
    proxy.alter = alter or proxy.alter
    proxy.alter_state = alter_state or proxy.alter_state
    proxy.dark_after = dark_after
    fragment = (f"#/{scene.name}" if route is None else route) + (
        "&" + fragment.lstrip("#") if fragment else ""
    )
    url, window = address(proxy.port, screen, fragment)
    try:
        ran = browse(
            "--hide-scrollbars",
            *(["--force-dark-mode"] if system == "dark" else []),
            f"--user-data-dir={tmp_path / 'profile'}",
            f"--window-size={window[0]},{window[1]}",
            f"--virtual-time-budget={budget}",
            url,
        )
    finally:
        proxy.close()
        if served:
            served.close()
    found = re.search(r'<pre id="probe">(.*?)</pre>', ran.stdout, re.S)
    assert found, f"the probe wrote nothing: {ran.stdout[-2000:]} {ran.stderr[-2000:]}"
    said = json.loads(html.unescape(found[1]))
    return said | {"writes": proxy.writes, "at": proxy.port, "asked": proxy.asked}


def clean(seen, screen=DESK):
    """Nothing threw, nothing drew a value that is not there, nothing is wider than the
    screen, and every drawer opened."""
    assert seen["errors"] == []
    assert seen["nan"] is False
    bad = [one for one in seen["opened"] if not one["open"] or one["bad"] or one["errors"]]
    assert bad == []
    assert all(one["words"] > 3 for one in seen["opened"])
    assert seen["scrollWidth"] == seen["width"] == screen[0]
    return {one["target"] for one in seen["opened"]}


def unreached(seen, names):
    """The panels that nothing on the first screen and nothing in a drawer opens: no
    `data-open` the browser found names them."""
    opened = {one["target"].partition(":")[0] for one in seen["opened"]}
    return sorted(set(names) - opened)


@pytest.fixture(autouse=True)
def one_browser_at_a_time(request):
    """The browser lock, held for the whole test: one wait for it, whatever it browses. A test
    with a home of its own starts no real browser and takes its own lock."""
    if "own_home" in request.fixturenames:
        yield
        return
    with heavy():
        yield


@pytest.fixture(autouse=True)
def a_browser():
    """With no browser a desk skips the test, and a runner fails it. A browser named in
    `JSTACK_TEST_BROWSER` that is not there fails it anywhere."""
    if NAMED and not CHROMIUM:
        pytest.fail(f"JSTACK_TEST_BROWSER is {NAMED}, which is no program to open the page in")
    if CHROMIUM:
        return
    if os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail("no chromium on PATH to open the page in, and a runner skips no browser test")
    pytest.skip("no chromium on PATH to open the page in")


@pytest.fixture
def scene(tmp_path, monkeypatch):
    return Scene(tmp_path, monkeypatch)


def test_a_long_temporary_directory_does_not_fail_the_browser(scene, tmp_path, monkeypatch):
    """Chromium binds a socket in a directory it makes under TMPDIR, and the path of a socket
    holds 107 characters."""
    long = tmp_path / ("t" * max(1, 89 - len(str(tmp_path))))
    long.mkdir()
    assert len(str(long)) >= 90
    monkeypatch.setenv("TMPDIR", str(long))
    assert look(scene, tmp_path)["errors"] == []


def test_a_run_under_the_heavy_suite_lock_is_not_waited_on(own_home, monkeypatch):
    """The user's rule runs a suite of several workers under `flock` on the heavy-suite lock.
    The two locks are files of their own names in one directory, here a made-up one."""
    monkeypatch.setattr("test_jbus_view_page.PATIENCE", 1)
    with open(own_home / "heavy-suite.lock", "a") as outer:
        fcntl.flock(outer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with heavy():
            pass


def test_two_runs_at_once_never_have_a_browser_each(own_home, monkeypatch):
    """Each thread opens the lock's file anew, as each run of this file does."""
    inside, most, start = [], [], threading.Barrier(2)

    class Browser:
        pid, returncode = 0, 0

        def __init__(self, command, **how):
            pass

        def __enter__(self):
            inside.append(1)
            most.append(len(inside))
            return self

        def communicate(self, timeout):
            time.sleep(0.3)
            return "", ""

        def __exit__(self, *raised):
            inside.pop()

    def run():
        start.wait()
        with heavy():
            browse()

    monkeypatch.setattr(subprocess, "Popen", Browser)
    monkeypatch.setattr(os, "killpg", lambda group, sent: None)
    runs = [threading.Thread(target=run) for _ in range(2)]
    for one in runs:
        one.start()
    for one in runs:
        one.join()
    assert most == [1, 1]


def test_a_browser_that_never_finishes_is_stopped_with_every_process_it_started(
    own_home, tmp_path, monkeypatch
):
    """A browser that hangs, and a process it started that would outlive it, are both gone
    once the launch's bound is up: a hang costs the test that bound and no more, and leaves
    nothing behind."""
    child = hanging(tmp_path, monkeypatch)
    monkeypatch.setattr("test_jbus_view_page.LAUNCH", 2)
    started = time.monotonic()
    with pytest.raises(pytest.fail.Exception, match="the browser did not finish in 2 s"):
        browse("http://127.0.0.1:9/")
    assert time.monotonic() - started < 20
    time.sleep(0.5)
    assert not Path(f"/proc/{child.read_text().strip()}").exists()


def test_a_browser_that_ignores_term_is_killed_and_named_too(own_home, tmp_path, monkeypatch):
    """`timeout` then kills its whole group, itself with it, and the run ends on a signal."""
    child = hanging(tmp_path, monkeypatch, "trap '' TERM\n")
    monkeypatch.setattr("test_jbus_view_page.LAUNCH", 2)
    started = time.monotonic()
    with pytest.raises(pytest.fail.Exception, match="the browser did not finish in 2 s"):
        browse("http://127.0.0.1:9/")
    assert time.monotonic() - started < 20
    time.sleep(0.5)
    assert not Path(f"/proc/{child.read_text().strip()}").exists()


def test_a_browser_stopped_from_outside_leaves_no_process_it_started(
    own_home, tmp_path, monkeypatch
):
    """pytest-timeout stops a test with a signal: the browser and what it started go too."""
    child = hanging(tmp_path, monkeypatch)

    def stops(*caught):
        raise TimeoutError("stopped from outside")

    before = signal.signal(signal.SIGALRM, stops)
    bound = signal.getitimer(signal.ITIMER_REAL)
    signal.alarm(2)
    try:
        with pytest.raises(TimeoutError):
            browse("http://127.0.0.1:9/")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, before)
        signal.setitimer(signal.ITIMER_REAL, *bound)
    time.sleep(0.5)
    assert not Path(f"/proc/{child.read_text().strip()}").exists()


def hanging(tmp_path, monkeypatch, first=""):
    """A browser that never finishes, and starts a process that would outlive it: the file
    that holds that process's id. `first` is shell it runs before."""
    child = tmp_path / "child"
    hangs = tmp_path / "chromium"
    hangs.write_text(f"#!/bin/sh\n{first}sleep 300 &\necho $! > {child}\nexec sleep 300\n")
    hangs.chmod(0o755)
    monkeypatch.setattr("test_jbus_view_page.CHROMIUM", str(hangs))
    return child


def test_the_first_screen_of_a_project_of_todays_size_is_no_more_than_150_words(scene, tmp_path):
    """The screen is a desk's, as high as the Needs you queue, `NEEDS`, here with the four rows
    of the scene: In progress, with a row for each of the 28 open tasks, starts below it."""
    open_rows = lineup(scene, TODAY)
    assert len(open_rows) == 28
    screen = (DESK[0], DESK[1] + NEEDS)
    seen = look(scene, tmp_path, screen=screen)
    opened = clean(seen, screen)
    assert seen["font"] == 18
    assert seen["words"] <= WORDS, seen["words"]
    assert seen["shell"] <= SHELL, seen["shell"]
    assert len([row for row in seen["prog"] if row["slug"] in open_rows]) == 28
    assert set(seen["first"]) <= opened
    assert {f"task:{slug}" for slug in open_rows} <= opened
    assert len(opened) >= 28 + 6


def test_the_overview_of_a_day_of_todays_size_is_no_more_than_250_words(scene, tmp_path):
    lineup(scene, TODAY)
    stacked(scene)
    seen = look(scene, tmp_path, route="#/")
    clean(seen)
    assert [row["project"] for row in seen["stack"]["rows"]] == ["demo", "larder", "pantry"]
    assert seen["words"] <= EVERY, seen["words"]
    assert seen["shell"] <= SHELL, seen["shell"]
    assert all(row["seen"] for row in seen["stack"]["rows"])


def test_a_bare_link_shows_every_project_once_from_one_request_a_poll(scene, tmp_path):
    """The machine as one word, one Needs you queue across the projects, oldest first, and a
    row for each project: a name, a dot, what is broken, and two counts. The page asks
    `/stack.json` and nothing
    else, once a poll, and a poll that changed nothing draws nothing again."""
    stacked(scene)
    seen = look(scene, tmp_path, route="#/", at=33000, budget=40000)
    assert clean(seen) == set()
    stack = seen["stack"]
    assert (stack["shown"], stack["title"], stack["none"]) == (True, "All projects", "")
    assert seen["header"]["machine"]["text"] == "Machine ok"
    needs = seen["needs"]
    assert needs["head"] == "4 Needs you"
    assert [(one["key"], one["what"], one["acts"][0]["text"]) for one in needs["now"]] == [
        ("demo/row:jam-lid", "which lid?", "Fix brief"),
        ("pantry/row:fig-tart", "which tin?", "Fix brief"),
        ("demo/#14", "Pull request #14", "Review merge"),
        ("demo/approve:tea-kettle", "tea-kettle", "Approve launch"),
    ]
    assert [one["acts"][0]["href"] for one in needs["now"]] == [
        "#/demo/you/row/jam-lid",
        "#/pantry/you/row/fig-tart",
        "#/demo/you/hold/14",
        "#/demo/you/approve/tea-kettle",
    ]
    assert [one["meta"] for one in needs["now"]] == [
        "demo · waiting 50m",
        "pantry · waiting 40m",
        "demo · waiting 12m · merge to main",
        "demo · new · unblocks tea-cups",
    ]
    assert [(one["what"], one["acts"][0]["text"]) for one in needs["soon"]] == [
        ("tea or coffee?", "Answer")
    ]
    assert needs["filled"] == 0
    assert [row["project"] for row in stack["rows"]] == ["demo", "larder", "pantry"]
    assert all(row["seen"] for row in stack["rows"])
    assert [(row["name"], row["counts"]) for row in stack["rows"]] == [
        ("demo", ["9 open", "1 merged today"]),
        ("larder", ["0 open", "0 merged today"]),
        ("pantry", ["2 open", "1 merged today"]),
    ]
    assert stack["rows"][0]["why"] == "" and stack["rows"][1]["why"].startswith("CI not read")
    assert [row["href"] for row in stack["rows"]] == ["#/demo", "#/larder", "#/pantry"]
    assert seen["words"] <= EVERY, seen["words"]
    polls = [asked for asked in seen["asked"] if asked not in ("/", "/favicon.ico", "/font.woff2")]
    assert len(polls) == 3 and set(polls) == {"/stack.json"}
    drawn = [change["at"] for change in seen["changes"] if change["part"].startswith("rows:")]
    assert drawn and [one for one in seen["changes"] if one["at"] > max(drawn) + 1000] == []
    assert seen["marked"] == 1


def test_the_header_says_the_name_where_you_are_and_the_time_of_the_last_read(scene, tmp_path):
    stacked(scene)
    one = look(scene, tmp_path)
    every = look(scene, tmp_path, route="#/")
    for seen in (one, every):
        clean(seen)
        assert seen["header"]["brand"] == "jbus view"
        assert re.fullmatch(r"Updated \d\d:\d\d · live", seen["header"]["read"]), seen["header"]
        assert seen["header"]["box"][:3] == [0, 0, DESK[0]]
    assert one["header"]["crumbs"] == [["All", "#/", ""], ["demo", "#/demo", "page"]]
    assert every["header"]["crumbs"] == [["All projects", "#/", "page"]]


def sidebar(scene):
    """The scene of the sidebar: three projects, and larder's bus with wakes that failed."""
    stacked(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"]["larder"] = {"outbox": 0, "failed_wakes": 2, "last_error": "500"}
    scene.write("status.json", status, scene.state_dir)


@pytest.mark.parametrize("screen", [DESK, MIDDLE, PHONE])
@pytest.mark.parametrize("route", ["#/", "#/demo"])
def test_no_view_scrolls_sideways(scene, tmp_path, screen, route):
    """With a top-level webhook that holds events, nothing is wider than the screen."""
    lineup(scene, TODAY)
    sidebar(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"]["demo"] |= {"outbox": 12, "failed_wakes": 6}
    status["projects"]["demo"]["top_level"] = {"outbox": 10, "failed_wakes": 3, "last_error": "500"}
    scene.write("status.json", status, scene.state_dir)
    seen = look(scene, tmp_path, route=route, screen=screen)
    clean(seen, screen)
    assert seen["cut"] == []


def test_a_project_page_asks_its_state_each_poll_and_every_project_once_a_minute(scene, tmp_path):
    """The switcher names every project, so a project's page asks `/stack.json` too: once when
    it opens and then once a minute, beside its own `/state.json` each poll."""
    stacked(scene)
    seen = look(scene, tmp_path, at=63000, budget=70000)
    asked = [one.partition("?")[0] for one in seen["asked"]]
    assert (asked.count("/state.json"), asked.count("/stack.json")) == (5, 2)
    assert [one[0] for one in seen["header"]["pick"]] == ["", "demo", "larder", "pantry"]


def test_a_row_opens_its_project_and_an_old_link_opens_it_too(scene, tmp_path):
    stacked(scene)
    seen = look(
        scene,
        tmp_path,
        route="#/",
        tap='#rows a[href="#/pantry"]',
        at=6000,
        budget=9000,
    )
    clean(seen)
    assert seen["hash"] == "#/pantry"
    assert (seen["stack"]["shown"], seen["needs"]["head"]) == (False, "1 Needs you")
    assert {row["slug"] for row in seen["prog"]} == {"fig-jam", "fig-tart"}
    seen = look(scene, tmp_path, route="?project=pantry")
    clean(seen)
    assert (seen["hash"], seen["needs"]["head"]) == ("#/pantry", "1 Needs you")
    assert [asked.partition("?")[0] for asked in seen["asked"]].count("/stack.json") == 1


def test_a_link_to_no_project_draws_the_machine_with_its_own_word_on_jbus(scene, tmp_path):
    """No project's read is in hand there, so the machine is the one /stack.json read, and
    whether jbus passes is its word, whatever the page drew before."""
    stacked(scene)
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    seen = look(scene, tmp_path, route="#/hydra")
    assert seen["errors"] == []
    assert seen["header"]["machine"]["text"] == "jbus stopped"


def test_a_link_to_a_project_that_is_not_there_says_so_and_reads_no_retired_one(scene, tmp_path):
    stacked(scene)
    seen = look(scene, tmp_path, route="#/hydra")
    assert seen["errors"] == [] and "gone" not in seen["body"]
    assert seen["stack"]["none"] == (
        "No project named hydra jbus looks after no project of that name: a retired project "
        "is not shown. Every project"
    )
    assert seen["first"] == []
    seen = look(scene, tmp_path, route="#/")
    assert "hydra" not in json.dumps(seen["stack"])
    seen = look(scene, tmp_path, route="#/%E0")
    assert seen["errors"] == [] and seen["stack"]["none"].startswith("No project named %E0 ")


def test_a_drawer_says_one_state_and_the_line_names_what_blocks_a_task(scene, tmp_path):
    expected = kinds(scene)
    findings = "wait: its findings are not handled: the Result has no Fixed line"
    chain = [
        row("nut-shell", "pr", pr="#41", why=findings),
        row("nut-meat", depends=["nut-shell"], why="depends on nut-shell"),
        row("nut-oil", depends=["nut-meat"], why="depends on nut-meat"),
    ]
    chain[1]["approval"] = {
        "basis": "rule",
        "ref": "6",
        "words": "A follow-up needs no new approval.",
        "said_at": "",
        "said_in": "",
        "checked": True,
        "follows": "nut-shell",
        "ran_by": {"session": "a-session", "directory": "/home/user/repos/demo"},
        "ran_at": "2026-10-12 09:00 ET",
    }
    scene.queue(json.loads((scene.state / "queue.json").read_text()) + chain)
    seen = look(scene, tmp_path, pick="fig-sap")
    opened = clean(seen)
    drawers = {one["target"]: one["said"] for one in seen["opened"]}
    by_rule = (
        "rule 6, follow-up of nut-shell; run 2026-10-12 09:00 ET by the demo home; he did not "
        "speak of this row by rule 6"
    )
    assert by_rule in drawers["task:nut-meat"]
    assert "by rule" not in drawers["task:nut-shell"]
    rows = {row["slug"]: row for row in seen["prog"]}
    assert {"fig-pip", "fig-tree", "nut-oil"} & set(rows) == {"nut-oil"}
    assert (rows["nut-shell"]["state"], rows["nut-shell"]["open"]) == ("Findings", "task:nut-shell")
    assert rows["nut-meat"]["chips"] == ["behind nut-shell"]
    assert rows["fig-sap"]["chips"] == ["behind fig-tart"]
    assert seen["flow"]["chain"] == "3 deep, behind nut-shell (Findings)"
    way = seen["picked"]
    assert (way["picked"], way["up"], way["down"]) == (["fig-sap"], ["fig-tart"], [])
    assert way["said"] == (
        "fig-sap waits on 1 row here and on fig-pip (Merged), and 0 rows wait on it."
    )
    now = {one["target"].removeprefix("task:"): one["now"] for one in seen["opened"]}
    assert {f"task:{slug}" for slug in expected} <= opened
    assert [one["acts"][0]["text"] for one in seen["needs"]["now"]].count("Close it") == 2
    for slug, kind in expected.items():
        name = "Ended, not closed" if slug in ("fig-burr", "fig-rind") else NAMES[kind]
        assert now[slug].startswith(f"NOW: {name.upper()} "), now[slug]
        assert "This step" not in now[slug] and " or " not in now[slug], now[slug]
        assert "the row disagrees" not in now[slug], now[slug]
    assert "launch" not in now["fig-pip"] + now["fig-stalk"]
    assert "pull request #21 is merged" in now["fig-pip"]
    assert "waits for a slot" in now["fig-jam"]
    assert "Blocked by nut-shell Findings" in now["nut-meat"]
    assert "2 tasks wait behind it: nut-meat, nut-oil" in now["nut-shell"]
    assert "2 tasks wait behind it: fig-sap, fig-stem" in now["fig-pip"]
    assert "Blocked by fig-tart Running" in now["fig-sap"]
    assert "task:fig-pip" in seen["links"]
    assert seen["words"] <= WORDS, seen["words"]


@pytest.mark.parametrize(("screen", "columns"), [(DESK, 9), (PHONE, 1)])
def test_the_drawer_of_the_queue_as_a_flow_marks_the_way_of_the_row_picked(
    scene, tmp_path, screen, columns
):
    waves = flowing(scene, FLOWS[25])
    seen = look(scene, tmp_path, budget=9000, screen=screen, pick="tea-ladle")
    clean(seen, screen)
    drawer, picked = seen["flow"], seen["picked"]
    assert drawer["title"] == "The queue as a flow"
    assert drawer["chain"] == "8 deep, behind your gate on tea-kettle"
    assert drawer["columns"] == [
        ["OUT 2", ["jam-kettle", "tea-kettle"]],
        ["READY 6", waves[0]],
        ["NEXT 5", waves[1]],
        *([f"WAVE {at + 2} {len(wave)}", wave] for at, wave in enumerate(waves[2:])),
    ]
    assert drawer["lefts"] == columns
    assert drawer["borders"] == ["solid"]
    assert (drawer["picked"], drawer["up"], drawer["down"], drawer["dim"]) == ([], [], [], 0)
    assert drawer["said"] == "Pick a row to mark what it waits on and what waits on it."
    assert picked["picked"] == ["tea-ladle"]
    assert picked["up"] == ["tea-kettle", "mint-kettle", "rye-saucer", "leek-saucer"]
    assert picked["down"] == ["oat-ladle", "rye-ladle", "fig-ladle", "plum-ladle", "kale-ladle"]
    assert picked["dim"] == 27 - 10
    assert picked["said"] == "tea-ladle waits on 4 rows here, and 5 rows wait on it."
    assert seen["taps"] == [[], ["kale-ladle"], ["kale-ladle"], ["tea-ladle"]]
    assert picked["box"] == drawer["box"]
    if screen == PHONE:
        assert picked["box"] == [0, 0, *PHONE]


def a_day_of_threads(scene):
    """Every role at work: a crewmate that hung and one that ended an hour ago, a reviewer, a
    scout researching, one that reported and ended and one that ended with no Report, the
    home, and two to fold: a crewmate that ended before the day began, and a thread of no
    role."""
    requested(
        scene,
        look=REQUEST.format(slug="look"),
        tin=REPORTED.format(slug="tin", status="done"),
        cut=REQUEST.format(slug="cut"),
    )
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar", "hung", minutes=25, queued=2),
            out("crew: oat-milk", "ended", "completed", minutes=120),
            out("crew: oat-bowl", "ended", "completed", minutes=60 * 17),
            out("review: jam-jar"),
            out("scout: look", "waiting", minutes=90),
            out("scout: tin", "ended", "completed", minutes=30),
            out("scout: cut", "ended", "completed", minutes=40),
            out("home: demo"),
            out("a thread he opened", "ended", "completed"),
        ],
        rows={"jam-jar": {"threads": 2, "thread_status": "running", "live": "hung"}},
    )


def chips(seen_band):
    return [(rl, [(c["text"], c["open"], c["ended"]) for c in cs]) for rl, cs in seen_band["rows"]]


def test_a_thread_is_a_link_that_opens_cold_with_the_way_back_to_its_project(scene, tmp_path):
    a_day_of_threads(scene)
    (first,) = walked(scene, tmp_path, "#/demo/thread/scout/look", ["look"])
    assert (first["open"], first["hash"], first["title"]) == (
        True,
        "#/demo/thread/scout/look",
        "look",
    )
    assert first["crumbs"] == [
        ["All", "#/"],
        ["demo", "#/demo"],
        ["look", "#/demo/thread/scout/look"],
    ]


def frozen(seen, since, said):
    """The page of a jbus that has stopped: the banner, and what is frozen and what live."""
    clean(seen)
    assert seen["body"] == "stopped"
    assert seen["banner"].startswith("jbus has not passed last pass ended " + since)
    assert said in seen["banner"]
    assert seen["header"]["machine"] == {
        "text": "jbus stopped",
        "cls": "machw bad",
        "href": "#/demo/pulse",
    }
    assert seen["header"]["read"].startswith("Updated "), "jbus stopped, the server did not"
    drawers = {one["target"]: one for one in seen["opened"]}
    assert drawers["pulse"]["title"] == "jbus has not passed"
    assert (drawers["room"]["tags"], drawers["checks"]["tags"]) == (["live"], ["live"])
    assert drawers["bus"]["tags"] == ["frozen"]
    assert drawers["task:oat-milk"]["github"] == "live"
    assert "frozen" in drawers["task:oat-milk"]["tags"]
    assert "#13 open" in seen["github"]


def stamp(moment):
    return moment.astimezone().strftime("%H:%M:%S")


def test_a_timer_that_is_not_active_shows_the_banner_and_freezes_what_jbus_writes(scene, tmp_path):
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    seen = look(scene, tmp_path, task="oat-milk")
    said = "jbus.timer inactive (dead), jbus.service exit-code, exit 1"
    frozen(seen, stamp(ago(seconds=20)), said)


def test_a_last_pass_more_than_150_s_ago_shows_the_banner_too(scene, tmp_path):
    scene.passed(seconds_ago=400)
    seen = look(scene, tmp_path, task="oat-milk")
    frozen(
        seen, stamp(ago(seconds=400)), "jbus.timer active (waiting), jbus.service success, exit 0"
    )


def test_a_jbus_that_passes_shows_no_banner_and_nothing_frozen(scene, tmp_path):
    seen = look(scene, tmp_path)
    assert (seen["body"], seen["banner"]) == ("", "")
    assert seen["header"]["machine"]["text"] == "Machine ok"
    assert seen["header"]["stale"] is False


def test_with_the_server_gone_the_page_says_so_after_two_answers_missed(scene, tmp_path):
    seen = look(scene, tmp_path, at=20000, budget=24000, dark_after=1)
    assert (seen["body"], seen["banner"]) == ("", "")
    seen = look(scene, tmp_path, at=40000, budget=44000, dark_after=1, task="oat-milk")
    clean(seen)
    assert set(seen["body"].split()) == {"stopped", "gone"}
    assert seen["banner"].startswith("the view server does not answer last answer ")
    assert "2 answers missed" in seen["banner"]
    read = NOW.astimezone().strftime("%H:%M")
    assert seen["header"]["read"] == f"Stale since {read}", "the time of the last answer"
    assert seen["header"]["stale"] is True
    assert "GitHub cannot be asked" in seen["github"]
    assert len(seen["prog"]) == 9


def test_a_server_that_never_answered_is_said_too(scene, tmp_path):
    seen = look(scene, tmp_path, at=40000, budget=44000, dark_after=0)
    assert seen["errors"] == []
    assert set(seen["body"].split()) == {"stopped", "gone"}
    assert seen["banner"].startswith("the view server does not answer")


def test_on_a_phone_the_page_is_one_column_and_every_target_takes_a_thumb(scene, tmp_path):
    open_rows = lineup(scene, TODAY)
    screen = (PHONE[0], PHONE[1] + PHONE_NEEDS)
    seen = look(scene, tmp_path, budget=9000, screen=screen)
    opened = clean(seen, screen)
    assert {f"task:{slug}" for slug in open_rows} <= opened
    assert len(seen["prog"]) >= 28
    assert all(
        row["box"][0] >= 0 and row["box"][0] + row["box"][2] <= screen[0] for row in seen["prog"]
    )
    assert min(row["box"][3] for row in seen["prog"]) >= THUMB
    assert (seen["small"], seen["cut"]) == ([], [])
    assert {tuple(one["box"]) for one in seen["opened"]} == {(0, 0, *screen)}
    assert all(one["closed"] for one in seen["opened"])
    assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []


@pytest.mark.parametrize("github", ["names", "down"])
def test_on_a_phone_a_stopped_jbus_with_unwell_sources_and_long_checks_is_whole(
    scene, tmp_path, github
):
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    (scene.state / "queue.json").write_text("{not json")
    (scene.state / "main.json").unlink()
    (scene.state / "stall.json").unlink()
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["projects"][scene.name] |= {"failed_wakes": 3, "outbox": 9}
    scene.write("status.json", status, scene.state_dir)
    if github == "down":
        scene.script("gh", "exit 1\n")
    else:
        long = "a-branch-with-a-long-name-that-goes-on"
        scene.github(
            runs=[
                (f"{long}-one", "in_progress", None),
                (f"{long}-two", "in_progress", None),
                (f"{long}-three", "queued", None),
                (f"{long}-four", "completed", "failure"),
            ]
        )
    screen = (PHONE[0], PHONE[1] + PHONE_NEEDS)
    seen = look(scene, tmp_path, screen=screen)
    clean(seen, screen)
    assert seen["body"] == "stopped"
    assert seen["banner"].startswith("jbus has not passed last pass ended ")
    assert seen["header"]["machine"]["text"] == "jbus stopped"
    assert (seen["small"], seen["cut"]) == ([], [])
    assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []
    assert {tuple(one["box"]) for one in seen["opened"]} == {(0, 0, *screen)}


@pytest.mark.parametrize("screen", [DESK, PHONE])
@pytest.mark.parametrize(
    ("fragment", "system", "dark"),
    [
        ("#theme=light", "dark", False),
        ("#theme=dark", "light", True),
        ("", "light", False),
        ("", "dark", True),
    ],
)
def test_the_page_is_light_dark_or_as_the_browser_asks(
    scene, tmp_path, screen, fragment, system, dark
):
    seen = look(scene, tmp_path, fragment=fragment, screen=screen, system=system)
    red = int(re.match(r"rgb\((\d+)", seen["background"])[1])
    assert (red < 60) is dark, seen["background"]
    clean(seen, screen)


def test_a_drawer_is_opened_by_its_name_in_the_address_under_the_servers_own_policy(
    scene, tmp_path
):
    served = Served(scene)
    try:
        ran = browse(
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=3000",
            f"http://127.0.0.1:{served.port}/#/demo/task/oat-bowl",
        )
    finally:
        served.close()
    assert '<dialog class="drawer" id="drawer" aria-labelledby="dw-title" open="">' in ran.stdout
    said = html.unescape(re.sub(r"<[^>]+>", "", ran.stdout))
    assert "the rebase dropped 2 of main's lines" in said
    assert "#11 open" in said


def walked(scene, tmp_path, route, walk):
    """What the page showed after each step of `walk`, from `route` opened cold."""
    seen = look(scene, tmp_path, route=route, walk=walk, at=4000 + 500 * len(walk), budget=12000)
    assert seen["errors"] == []
    return seen["walked"]


TEA = "#/demo/task/tea-cups"
WORDS_AT = "#/demo/words/approval/tea-cups"


@pytest.mark.parametrize(
    ("route", "drawer"),
    [
        ("#/", ""),
        ("#/demo", ""),
        (TEA, "tea-cups"),
        (WORDS_AT, "things you said"),
        ("#/demo/you/gate", "things wait on you"),
        ("#/demo/steps/queued", "The steps, top to bottom"),
        ("#/demo&open=task:tea-cups", "tea-cups"),
    ],
)
def test_every_route_opens_cold_from_a_pasted_link(scene, tmp_path, route, drawer):
    """A view is a link: pasted in a new tab it opens on its own, with the drawer it names, and
    an old `&open=` link is rewritten to its route."""
    said_by_him(scene)
    (first,) = walked(scene, tmp_path, route, ["look"])
    assert first["open"] is bool(drawer)
    assert first["hash"] == ("#/demo/task/tea-cups" if "&open=" in route else route)
    if drawer:
        assert drawer in first["title"]
        assert first["crumbs"][:2] == [["All", "#/"], ["demo", "#/demo"]]
        assert first["crumbs"][2] == [first["title"], first["hash"]]
        assert first["back"] == "", "a drawer opened cold has nothing before it"
    elif route == "#/demo":
        assert first["crumbs"] == [["All", "#/"], ["demo", "#/demo"]]


def test_back_closes_a_drawer_forward_opens_it_and_esc_goes_back_one_layer(scene, tmp_path):
    said_by_him(scene)
    steps = walked(
        scene,
        tmp_path,
        TEA,
        ["look", "open:words:approval:tea-cups", "back", "forward", "esc", "esc"]
        + ["open:you", "back", "forward", "close"],
    )
    seen = [(one["step"], one["hash"], one["open"]) for one in steps]
    assert seen == [
        ("look", TEA, True),
        ("open:words:approval:tea-cups", WORDS_AT, True),
        ("back", TEA, True),
        ("forward", WORDS_AT, True),
        ("esc", TEA, True),
        ("esc", "#/demo", False),
        ("open:you", "#/demo/you", True),
        ("back", "#/demo", False),
        ("forward", "#/demo/you", True),
        ("close", "#/demo", False),
    ]
    task, words = steps[0]["title"], steps[1]["title"]
    assert task.startswith("tea-cups")
    assert [one["back"] for one in steps[:5]] == ["", f"← {task}", "", f"← {task}", ""]
    assert steps[1]["crumbs"] == [["All", "#/"], ["demo", "#/demo"], [words, WORDS_AT]]
    assert steps[0]["crumbs"] == [["All", "#/"], ["demo", "#/demo"], [task, TEA]]
    assert steps[4]["focus"] == "words:approval:tea-cups", "back on the button that opened it"


def test_the_arrow_and_the_breadcrumbs_lead_to_real_pages(scene, tmp_path):
    said_by_him(scene)
    steps = walked(
        scene,
        tmp_path,
        "#/demo",
        ["open:task:tea-cups", "open:words:approval:tea-cups", "arrow", "crumb:1", "back"]
        + ["open:task:tea-cups", "crumb:0"],
    )
    seen = [(one["step"], one["hash"], one["open"]) for one in steps]
    assert seen == [
        ("open:task:tea-cups", TEA, True),
        ("open:words:approval:tea-cups", WORDS_AT, True),
        ("arrow", TEA, True),
        ("crumb:1", "#/demo", False),
        ("back", TEA, True),
        ("open:task:tea-cups", TEA, True),
        ("crumb:0", "#/", False),
    ]
    assert steps[1]["back"] == f"← {steps[0]['title']}"


def test_a_way_back_through_an_entry_rewritten_since_lands_on_its_layer(scene, tmp_path):
    """Esc on a drawer a pasted link opened rewrites its entry to the page. Forward again, the
    arrow still goes back to that drawer, not to the page, and a drawer opened over another
    puts the focus on its own Close."""
    said_by_him(scene)
    steps = walked(
        scene,
        tmp_path,
        TEA,
        ["look", "open:words:approval:tea-cups", "esc", "esc", "forward", "arrow", "cancel"]
        + ["open:words:approval:tea-cups", "cancel-hard"],
    )
    seen = [(one["step"], one["hash"], one["open"]) for one in steps]
    assert seen == [
        ("look", TEA, True),
        ("open:words:approval:tea-cups", WORDS_AT, True),
        ("esc", TEA, True),
        ("esc", "#/demo", False),
        ("forward", WORDS_AT, True),
        ("arrow", TEA, True),
        ("cancel", "#/demo", False),
        ("open:words:approval:tea-cups", WORDS_AT, True),
        ("cancel-hard", "#/demo", False),
    ]
    assert steps[1]["focus"] == "dw-close"
    assert steps[4]["back"] == f"← {steps[0]['title']}"


def test_a_filter_in_a_drawer_redraws_it_in_place(scene, tmp_path):
    """The role filters of the threads drawer are no layers: Esc after two of them shuts it."""
    said_by_him(scene)
    steps = walked(
        scene,
        tmp_path,
        "#/demo",
        [
            "open:threads",
            'tap:#dw [data-open="threads:crew"]',
            'tap:#dw [data-open="threads:scout"]',
        ]
        + ["esc"],
    )
    seen = [(one["hash"], one["open"], one["back"]) for one in steps]
    assert seen == [
        ("#/demo/threads", True, ""),
        ("#/demo/threads/crew", True, ""),
        ("#/demo/threads/scout", True, ""),
        ("#/demo", False, ""),
    ]
    assert [one["focus"] for one in steps[1:3]] == ["threads:crew", "threads:scout"]


@pytest.mark.parametrize(
    ("route", "said"),
    [
        ("#/demo/task/no-such-task", "No task named no-such-task in demo"),
        ("#/demo/gate/999", "No gate named 999 in demo"),
        ("#/demo/thread/scout/no-tin", "No thread named scout no-tin in demo"),
        ("#/demo/nothing", "No drawer called nothing in demo"),
        ("#/nowhere/task/tea-cups", "No project named nowhere"),
    ],
)
def test_a_link_to_a_name_that_is_not_there_says_which(scene, tmp_path, route, said):
    said_by_him(scene)
    (first,) = walked(scene, tmp_path, route, ["look"])
    assert first["hash"] == route
    assert first["notice"].startswith(said), first["notice"]


def test_a_task_drawer_says_its_approval_in_a_line_that_opens_your_words_at_it(scene, tmp_path):
    said_by_him(scene)
    served = Served(scene)
    try:
        task = shown(served.port, tmp_path, "task:tea-cups")
        before = shown(served.port, tmp_path, "task:tea-tray")
        you = shown(served.port, tmp_path, "you")
        ran = browse(
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=3000",
            f"http://127.0.0.1:{served.port}/#/demo/words/approval/tea-cups",
        )
    finally:
        served.close()
    assert "Approval on your word, said " in task
    assert "by the elsewhere home" in task.partition("Approval on your word")[2]
    assert "Approval no record: approved before the record was kept" in before
    assert "The questions you answered, in Your words" in you
    drawer = ran.stdout.partition('id="drawer"')[2].partition("</dialog>")[0]
    hit = drawer.partition('<li class="hit">')[2].partition("</li>")[0]
    assert "tea-cups" in hit
    assert "go ahead with the kettle" in html.unescape(hit)
    said = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", drawer)))
    assert "1 questions you answered" in said
    assert "2 words sent down" in said
    assert "Not sent on yet: the home has no home-id." in said


def test_a_question_its_home_closed_is_drawn_as_closed_by_its_home_and_not_as_his_answer(
    scene, tmp_path
):
    said_by_him(scene)
    number = asks(scene, "which lid?", slug="jam-lid")
    with open(scene.home / "gates.md", "a") as gates:
        gates.write(
            "\n"
            + PIPED.format(n=number, asked="which lid?", status="answered: red", slug="jam-lid")
        )
    questions.closed_in_files(types.SimpleNamespace(home=scene.home, state=scene.state))
    served = Served(scene)
    try:
        ran = browse(
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=3000",
            f"http://127.0.0.1:{served.port}/#/demo/words/question/{number}",
        )
    finally:
        served.close()
    drawer = ran.stdout.partition('id="drawer"')[2].partition("</dialog>")[0]
    hit = drawer.partition('<li class="hit">')[2].partition("</li>")[0]
    said = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", hit)))
    assert "which lid?" in said
    assert 'Closed by its home "answered: red"' in said
    assert "Your answer" not in said
    assert "not the default" not in said


def gated(scene):
    """Three questions of one crewmate, each with its options, the first with a context and
    an option more. The answer is their numbers."""
    (scene.home / "tasks").mkdir()
    (scene.home / "tasks" / "alpha.md").write_text("# alpha\nThread: mcp:crew-alpha\n")
    lines = PIPED.format(n="<n>", asked="tea or coffee?", status="open", slug="alpha")
    lines += "Context: the pot holds two cups\nOption: both: a second pot\n"
    first = questions.ask(scene.state, scene.home, "alpha", lines, ago(minutes=25))[0].number
    return [first, asks(scene, "milk?"), asks(scene, "sugar?")]


def test_the_inline_accept_waits_ten_seconds_undo_stops_it_and_one_write_follows(scene, tmp_path):
    """A gate with a default and no hold is accepted from the queue: Undo in the 10 s window
    sends nothing, a second accept sends one write after the window, and the page shows the
    server's sentence. Nothing on the page or in the drawer is focused to start with."""
    tea, _, _ = gated(scene)
    walk = ["look", "tap:[data-accept]", "look", "tap:[data-undo]", *["look"] * 23]
    walk += ["tap:[data-accept]", *["look"] * 23]
    seen = look(scene, tmp_path, walk=walk, at=4000 + 500 * len(walk), budget=40000)
    assert seen["errors"] == []
    before, started, counting, undone, *_ = seen["walked"]
    assert before["focus"] == ""
    assert started["acc"].startswith("Accepting the default in") and started["acc"].endswith("Undo")
    assert counting["acc"] and undone["acc"] == ""
    assert seen["walked"][2 + 1 + 23]["acc"] == ""
    assert seen["walked"][-1]["acc"] == ""
    assert [one["body"] for one in seen["writes"]] == [{"numbers": [tea]}]
    assert seen["walked"][-1]["nsaid"], "the server's sentence is on the page"
    assert seen["needs"]["filled"] <= 1


def test_an_accept_still_counting_is_dropped_when_the_route_leaves_its_project(scene, tmp_path):
    """Going to another project hides the queue and its Undo, so the countdown ends there
    and no write follows."""
    gated(scene)
    walk = ["look", "tap:[data-accept]", "hash:#/nowhere", *["look"] * 25]
    seen = look(scene, tmp_path, walk=walk, at=4000 + 500 * len(walk), budget=40000)
    assert seen["errors"] == []
    assert seen["writes"] == []


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_a_gate_is_opened_and_answered_each_of_the_three_ways(scene, tmp_path, screen):
    tea, milk, sugar = gated(scene)
    ways = [
        {"number": tea},
        {"number": milk, "option": 1},
        {"number": sugar, "words": "half a spoon"},
    ]
    seen = look(scene, tmp_path, budget=14000, screen=screen, gates={"ways": ways})
    clean(seen, screen)
    assert seen["words"] <= WORDS, seen["words"]
    assert [(one["path"], one["kind"]) for one in seen["writes"]] == [
        ("/answer?project=demo", "application/json")
    ] * 3
    assert {one["origin"] for one in seen["writes"]} == {f"http://127.0.0.1:{seen['at']}"}
    assert [one["body"] for one in seen["writes"]] == [
        {"numbers": [tea], "option": "the first one"},
        {"numbers": [milk], "option": "the other"},
        {"numbers": [sugar], "option": "the first one", "words": "half a spoon"},
    ]
    if screen == PHONE:
        assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []
    assert {f"gate:{number}" for number in (tea, milk, sugar)} <= {
        one["target"] for one in seen["opened"]
    }
    accept, option, words = seen["answered"]
    opened = accept["opened"]
    assert opened["title"] == f"Question {tea}"
    assert opened["kv"] == ["Asked by", "Context", "Default taken", "Built on", "To undo"]
    for said in (
        "tea or coffee?",
        "Asked by crew alpha 25 min",
        "Context the pot holds two cups",
        "Default taken the first one",
        "Built on nothing",
        "To undo pick the other",
    ):
        assert said.lower() in opened["said"].lower(), said
    assert opened["cards"] == [
        {
            "name": "the first one",
            "picked": True,
            "marks": ["taken as default", "the thread recommends"],
            "follows": "nothing changes",
        },
        {"name": "the other", "picked": False, "marks": [], "follows": "one more cup"},
        {"name": "both", "picked": False, "marks": [], "follows": "a second pot"},
    ]
    assert opened["box"] is True
    assert opened["will"] == f"Nothing is sent. The default stands and question {tea} closes."
    assert opened["buttons"] == ["Accept the default"]
    assert option["opened"]["buttons"] == ["Accept the default"]
    assert option["opened"]["kv"] == ["Asked by", "Default taken", "Built on", "To undo"]
    assert [card["picked"] for card in option["before"]["cards"]] == [False, True]
    assert option["before"]["buttons"] == ["Send this option"]
    assert option["before"]["will"] == (
        'Goes at once to the crew thread of alpha: "the other", with how to undo the default: '
        "pick the other"
    )
    assert [card["picked"] for card in words["before"]["cards"]] == [True, False]
    assert words["before"]["buttons"] == ["Send my words"]
    assert words["before"]["will"].startswith(
        'Goes at once to the crew thread of alpha: "half a spoon"'
    )
    for one in seen["answered"]:
        for at in ("opened", "before", "after"):
            assert "deny" not in one[at]["said"].lower()
            assert one[at]["cut"] == [], (at, one[at]["cut"])
            if screen == PHONE:
                assert one[at]["small"] == [], (at, one[at]["small"])
                assert one[at]["drawer"] == [0, 0, *PHONE]
    assert accept["after"]["title"] == f"Question {tea}"
    assert (
        f"Question {tea} closed at 16:00 ET with its default, and nothing was sent."
        in (accept["after"]["said"])
    )
    assert accept["after"]["links"] == ["you:gate"]
    for one, number in ((option, milk), (words, sugar)):
        assert (
            f"Question {number} closed at 16:00 ET with its answer recorded and not yet sent, "
            "since no config at"
        ) in one["after"]["said"]
    assert seen["left"] == ["4"]
    records = kept(scene.state)
    assert [(records[n].answer.keeps, records[n].answer.words) for n in (tea, milk, sugar)] == [
        (True, "the first one"),
        (False, "the other"),
        (False, "half a spoon"),
    ]


def test_every_gate_that_can_be_answered_is_ticked_and_closed_in_one_write(scene, tmp_path):
    tea, milk, sugar = gated(scene)
    seen = look(scene, tmp_path, budget=12000, gates={"batch": True})
    clean(seen)
    found = seen["batch"]
    assert [(row["number"], row["tick"]) for row in found["rows"]] == [
        ("4", False),
        (str(tea), True),
        (str(milk), True),
        (str(sugar), True),
    ]
    gate, first, second, _ = found["rows"]
    assert "cannot be answered here" in gate["said"] and gate["opens"] == []
    assert first["options"] == ["the first one (taken)", "the other", "both"]
    assert (first["taken"], first["opens"]) == (["the first one (taken)"], [f"gate:{tea}"])
    assert second["options"] == ["the first one (taken)", "the other"]
    assert found["control"] == "Tick all 3 that can be answered here"
    assert (found["none"]["button"], found["none"]["off"]) == ("Accept the default for 0", True)
    assert found["ticked"] == [str(tea), str(milk), str(sugar)]
    assert found["all"] == {
        "line": f"Closes questions {tea}, {milk} and {sugar} with their defaults. "
        "Nothing is sent to any thread.",
        "button": "Accept the default for 3",
        "off": False,
    }
    assert [one["body"] for one in seen["writes"]] == [{"numbers": [tea, milk, sugar]}]
    assert found["after"]["title"] == "3 of 3 closed"
    for number in (tea, milk, sugar):
        assert f"Question {number} closed at 16:00 ET with its default" in found["after"]["said"]
    assert seen["left"] == ["4"]
    assert [one.answer.keeps for one in kept(scene.state).values()] == [True, True, True]


def test_a_question_with_no_options_on_record_opens_with_no_cards_and_says_so(scene, tmp_path):
    tea, milk, _ = gated(scene)
    file = questions.path(scene.state)
    old = json.loads(file.read_text())
    for one in old["records"]:
        del one["options"]
    file.write_text(json.dumps(old))
    ways = [{"number": tea}, {"number": milk, "words": "oat milk"}]
    seen = look(scene, tmp_path, budget=12000, gates={"ways": ways})
    clean(seen)
    accept, words = seen["answered"]
    assert accept["opened"]["cards"] == [] and accept["opened"]["box"] is True
    assert "None are on record for this gate." in accept["opened"]["said"]
    assert accept["opened"]["buttons"] == ["Accept the default"]
    assert words["before"]["buttons"] == ["Send my words"]
    assert [one["body"] for one in seen["writes"]] == [
        {"numbers": [tea]},
        {"numbers": [milk], "words": "oat milk"},
    ]
    records = kept(scene.state)
    assert [(records[n].answer.keeps, records[n].answer.words) for n in (tea, milk)] == [
        (True, "the first one"),
        (False, "oat milk"),
    ]


def test_a_write_that_is_refused_or_meets_no_server_is_said_in_the_drawer(scene, tmp_path):
    tea, milk, sugar = gated(scene)
    user = jsettings.load()

    def meanwhile(nth):
        if nth > 1:
            return "dark"
        said = {"by": "user", "at": et(NOW), "where": "a shell", "keeps": False, "user": user}
        questions.answer(scene.state, tea, "coffee", **said)

    ways = [{"number": tea}, {"number": milk, "option": 1}]
    gates = {"ways": ways, "batch": True}
    seen = look(scene, tmp_path, budget=16000, gates=gates, on_write=meanwhile)
    clean(seen)
    unknown = "The view server did not answer, so it is not known whether anything closed."
    refused, lost = seen["answered"]
    assert refused["after"]["title"] == f"Question {tea}"
    assert (
        f'Question {tea} was answered already, and nothing changed: "coffee", by user, '
        f"{et(NOW)}, in a shell (not the default)."
    ) in refused["after"]["said"]
    assert "Nothing changed." in refused["after"]["said"]
    assert lost["after"]["title"] == f"Question {milk}"
    assert unknown in lost["after"]["said"]
    assert lost["after"]["buttons"] == ["Send this option"]
    assert [card["picked"] for card in lost["after"]["cards"]] == [False, True]
    assert seen["batch"]["ticked"] == [str(milk), str(sugar)]
    assert unknown in seen["batch"]["after"]["said"]
    assert seen["batch"]["after"]["buttons"] == ["Accept the default for 2"]
    assert [one["body"] for one in seen["writes"]] == [
        {"numbers": [tea], "option": "the first one"},
        {"numbers": [milk], "option": "the other"},
        {"numbers": [milk, sugar]},
    ]
    assert seen["left"] == ["4", str(milk), str(sugar)]
    records = kept(scene.state)
    assert (records[tea].answer.words, records[milk].answer, records[sugar].answer) == (
        "coffee",
        None,
        None,
    )


def test_the_page_is_one_document_that_loads_nothing_and_asks_only_its_own_server(scene):
    """Nothing but its one font, from its own server."""
    served = Served(scene)
    try:
        _, headers, page = served.ask("/")
    finally:
        served.close()
    scripts = [one.script.read_text() for one in panels.found()]
    for part in (PAGE.read_text().replace(FONT, "", 1), *scripts):
        assert "://" not in part
        for loads in ("<link", "<img", "<iframe", "<object", "<embed", " src=", "@import", "url("):
            assert loads not in part, loads
    assert FONT in page
    asks = [
        "/answer",
        "/answer?project=",
        "/panel/",
        "/panel/steps.json?project=",
        "/stack.json",
        "/state.json",
        "/task/",
    ]
    assert sorted(set(re.findall(r'ask\("(/[^"]*)"', page))) == asks
    assert "fetch(path," in page and page.count("fetch(") == 1
    assert page.count("<script") == 2 and all(script in page for script in scripts)
    assert "connect-src 'self'" in headers["Content-Security-Policy"]
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert "font-src 'self'" in headers["Content-Security-Policy"]


def test_every_panel_is_opened_from_the_first_screen_or_from_a_drawer(scene, tmp_path):
    """The scene has a question jbus holds, which is what opens the drawer of a gate."""
    gated(scene)
    a_noticed(scene, ("alpha", "new", 5, {}))
    scene.passed(20, threads=[out("home: demo")])
    seen = look(scene, tmp_path)
    assert unreached(seen, [one.name for one in panels.found()]) == []


def shown(port, tmp_path, opens):
    """What the page says with the drawer `opens` names in its address open, as the browser
    has it once the page is still, or nothing where no drawer is open."""
    ran = browse(
        f"--user-data-dir={tmp_path / 'profile'}",
        "--virtual-time-budget=3000",
        f"http://127.0.0.1:{port}/#/demo/{opens.replace(':', '/')}",
    )
    open_ = '<dialog class="drawer" id="drawer" aria-labelledby="dw-title" open="">'
    if open_ not in ran.stdout:
        return ""
    said = ran.stdout.partition(open_)[2].partition("</dialog>")[0]
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", said))).strip()


def test_an_approval_by_a_pick_on_a_lavish_page_says_so_with_the_pages_file(scene, tmp_path):
    by = {"session": "s-1", "directory": "/made/up/elsewhere"}
    page = "/made/up/reports/grill-tea.html"
    made = queue.Approval(
        "page",
        "k1/e3",
        "1. Cups: as recommended",
        et(ago(minutes=20)),
        page,
        True,
        by,
        iso(ago(minutes=10)),
    )
    rows = table()
    rows[1] |= {"approved": made.line(), "approval": queue.held(made)}
    scene.queue(rows)
    served = Served(scene)
    try:
        task = shown(served.port, tmp_path, "task:tea-cups")
        words = shown(served.port, tmp_path, "words:approval:tea-cups")
    finally:
        served.close()
    assert "Approval on your pick on a Lavish page, " in task
    assert ", grill-tea.html, run " in task.partition("Approval on your pick")[2]
    assert "by page" in words
    assert "Your pick on a Lavish page, " in words
    assert "grill-tea.html. Run " in words
    assert page not in words


def test_a_folder_added_to_a_copy_of_the_package_opens_its_drawer_and_adds_its_lines(
    scene, tmp_path
):
    """Two folders are added to a copy of the package, and no other file of it is edited
    (`test_jbus_view.py` compares the trees). `sample` adds a line to the task drawer that
    opens it, and a count beside the Needs you queue. Nothing opens `lost`, and the drawer of
    `thrown` throws."""
    process = Process(scene)
    panel(process, "sample")
    panel(process, "lost", DRAWN + "panel({ drawer: drawn });\n")
    panel(process, "thrown", 'panel({ drawer: function () { throw new Error("no"); } });\n')
    scene.write("sample.json", {"lines": ["a first line", "a second line"]})
    try:
        process.start()
        seen = look(scene, tmp_path, port=process.port)
        clean(seen)
        assert unreached(seen, ["sample", "lost", "thrown"]) == ["lost", "thrown"]
        assert seen["needs"]["head"] == "3 Needs you"
        assert (seen["needs"]["extra"][-1]["text"], seen["needs"]["extra"][-1]["open"]) == (
            "1 sample",
            "sample",
        )
        assert seen["words"] <= WORDS
        said = shown(process.port, tmp_path, "sample")
        assert said.startswith("All › demo › 2 sample lines Sample 2 sample lines Close"), said
        assert "a first line a second line" in said and "could not be read" not in said
        assert "a sample line of oat-milk the sample" in shown(
            process.port, tmp_path, "task:oat-milk"
        )
        said = shown(process.port, tmp_path, "thrown")
        assert (
            said.startswith("All › demo › thrown Panel thrown Close")
            and "This panel could not be drawn." in said
        )
        (scene.state / "sample.json").unlink()
        said = shown(process.port, tmp_path, "sample")
        assert said.startswith("All › demo › 0 sample lines Sample 0 sample lines Close"), said
        assert said.endswith("missing sample.json could not be read.")
    finally:
        process.stop()


def test_a_task_drawer_says_its_rounds_in_one_line_that_opens_them(scene, tmp_path):
    """A round has a time where the event log has a `review` event of its head, and says no
    time is kept where it has none. A task whose brief cannot be read says that instead."""
    _, first, fixed = rounded(scene)
    served = Served(scene)
    try:
        task = shown(served.port, tmp_path, "task:oat-milk")
        drawer = shown(served.port, tmp_path, "rounds:oat-milk")
        other = shown(served.port, tmp_path, "rounds:oat-bowl")
    finally:
        served.close()
    assert "2 reviews, 1 rebase, 3 wakes" in task
    assert drawer.startswith(
        "All › demo › oat-milk Rounds oat-milk Close (Esc) Now 2 reviews, 1 rebase, 3 wakes"
    ), drawer
    at = ago(minutes=20).astimezone()
    when = f"{at:%H:%M}" if at.date() == NOW.astimezone().date() else f"{at:%m-%d %H:%M}"
    assert f"1st findings review of {first[:12]} 2 findings {when}" in drawer
    assert f"2nd clean review of {fixed[:12]} 0 findings no time kept" in drawer
    assert "second pass needed scoped review needed wakes 3 rebases 1" in drawer
    assert "0 reviews" not in other
    assert "not read it has no brief in its home or in jbus's copies." in other


def test_the_usage_line_of_a_task_says_not_known_when_its_ask_fails(scene, tmp_path, monkeypatch):
    """The task drawer's Usage line is filled by an ask of its own. A transcript that is not
    there is said, and an ask the server does not answer is said too, never left waiting."""
    monkeypatch.setattr(usage, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(usage, "_kept", {})
    served = Served(scene)
    proxy = Proxy(served.port, 600, probe=False)
    try:
        said = shown(proxy.port, tmp_path, "task:oat-milk")
        assert "Usage: not known: no transcript under " in said
        proxy.refused = ("/panel/usage.json",)
        said = shown(proxy.port, tmp_path / "again", "task:oat-milk")
        assert "Usage: not known: the view server did not answer" in said
    finally:
        proxy.close()
        served.close()


HOLDERS = ["user", "crew", "home", "rev", "ci", "bus", "dep", "ok", "scout", "other", "unknown"]
MARKS = ["long", "rep", "blk", "bn", "lv-moving", "lv-quiet", "lv-hung"]


@pytest.mark.parametrize(("route", "help"), [("#/demo", "#/demo/help"), ("#/", "#/help")])
def test_the_question_mark_key_opens_the_glossary_and_esc_goes_back(scene, tmp_path, route, help):
    lineup(scene, TODAY)
    walk = ["key:?:", "key:?:", "esc", "tap:#helpme", "look"]
    seen = look(scene, tmp_path, route=route, walk=walk, at=4000 + 500 * len(walk), budget=12000)
    assert seen["errors"] == []
    opened, twice, esc, tapped, _ = seen["walked"]
    assert (opened["hash"], opened["open"], opened["title"]) == (
        help,
        True,
        "Every term on the page",
    )
    assert twice["hash"] == help and twice["back"] == "", "a second ? opens no second glossary"
    assert (esc["hash"], esc["open"]) == (route, False)
    assert (tapped["hash"], tapped["open"]) == (help, True)


def test_a_link_to_the_glossary_opens_it_cold_over_every_project(scene, tmp_path):
    lineup(scene, TODAY)
    seen = look(scene, tmp_path, route="#/help", walk=["look"], at=4500, budget=12000)
    assert seen["errors"] == []
    (first,) = seen["walked"]
    assert (first["hash"], first["open"], first["title"]) == (
        "#/help",
        True,
        "Every term on the page",
    )
    assert first["crumbs"] == [["All", "#/"], ["Every term on the page", "#/help"]]
    assert "Step 2 of 12: a crewmate thread has the task" in first["said"], "notes come cold too"
    assert seen["stack"]["shown"], "the glossary is over every project"


def test_an_open_toggletip_stays_open_when_a_poll_draws_the_queue_again(scene, tmp_path):
    lineup(scene, TODAY)

    def more(nth, body):
        if nth > 1:
            body["needs"] = body["needs"][1:]
        return body

    walk = ['tap:#needs-h [data-tip="term:waits"]'] + ["look"] * 30
    seen = look(
        scene,
        tmp_path,
        route="#/",
        walk=walk,
        alter=more,
        at=4000 + 500 * len(walk),
        budget=24000,
    )
    assert seen["errors"] == []
    opened = seen["walked"][0]
    redrawn = [c["at"] for c in seen["changes"] if c["part"] == "needs-h"]
    assert redrawn and max(redrawn) > 2500, "the heading was drawn again after the tip opened"
    assert {step["tip"] for step in seen["walked"]} == {opened["tip"]}
    assert seen["walked"][-1]["expanded"] == ["term:waits"]


AXE = Path(__file__).parent / "fixtures" / "jbus-view"
AXE = (AXE / "axe.min.js").read_text() + "\n" + (AXE / "axe-run.js").read_text()


def every_kind(scene):
    """A day with something of each kind on it: today's line, two projects beside it, every
    role of thread at work, and three gates to answer."""
    lineup(scene, TODAY)
    stacked(scene)
    a_day_of_threads(scene)
    gated(scene)


def a_day(scene, day):
    """The scene of a day, and how long the page runs before axe does: `busy` is every kind,
    `stopped` a jbus whose timer is not active, so half the page is frozen, and `gone` a
    server that stopped answering after its first answer."""
    if day == "busy":
        every_kind(scene)
    if day == "stopped":
        scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    return {"at": 40000, "budget": 100000, "dark_after": 1} if day == "gone" else {"at": 3000}


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    ("route", "day", "screen"),
    [
        ("#/", "busy", DESK),
        ("#/demo", "busy", DESK),
        ("#/help", "busy", DESK),
        ("#/no-such-pot", "busy", DESK),
        ("#/", "stopped", DESK),
        ("#/demo", "stopped", DESK),
        ("#/", "gone", DESK),
        ("#/demo", "gone", DESK),
        ("#/", "busy", PHONE),
        ("#/demo", "busy", PHONE),
    ],
)
def test_axe_finds_no_serious_issue_in_any_view_or_drawer(
    scene, tmp_path, route, day, screen, theme
):
    """axe runs in the page over the view, then over every drawer the view or a drawer opens,
    at a desk and on a phone, where the sidebar is a row of chips. Each thing that takes the
    focus draws a ring when it has it."""
    when = {"budget": 60000, "screen": screen} | a_day(scene, day)
    seen = look(scene, tmp_path, route=route, fragment=f"theme={theme}", script=AXE, **when)
    assert seen["theme"] == theme
    assert seen["errors"] == []
    assert seen["violations"] == []
    assert seen["rings"] == []
    if (route, day) == ("#/demo", "busy"):
        kinds = {where.split(":")[0] for where in seen["looked"]}
        assert {"task", "gate", "you", "thread", "flow"} <= kinds


@pytest.mark.parametrize("route", ["#/", "#/demo"])
def test_the_first_tab_stop_is_a_skip_link_that_shows_when_focused_and_lands_on_the_view(
    scene, tmp_path, route
):
    every_kind(scene)
    seen = look(scene, tmp_path, route=route, script=AXE, at=3000, budget=60000)
    assert seen["skip"] == {
        "cls": "skip",
        "text": "Skip to the view",
        "href": "#main",
        "seen": True,
    }
    walk = ["tap:.skip", "look"]
    seen = look(scene, tmp_path, route=route, walk=walk, at=4000 + 500 * len(walk), budget=12000)
    assert seen["errors"] == []
    tapped, _ = seen["walked"]
    assert (tapped["hash"], tapped["open"], tapped["focus"]) == (route, False, "main")


def test_g_a_goes_to_every_project_and_g_p_to_each_next_one_in_turn(scene, tmp_path):
    every_kind(scene)
    walk = ["key:g:", "key:p:", "key:g:", "key:p:", "key:g:", "key:p:", "key:g:", "key:p:"]
    walk += ["key:g:", "key:a:", "key:p:", "key:a:", "key:?:", "key:g:", "key:a:", "look"]
    seen = look(scene, tmp_path, route="#/demo", walk=walk, at=4000 + 500 * len(walk), budget=20000)
    assert seen["errors"] == []
    hashes = [step["hash"] for step in seen["walked"]]
    assert hashes[1::2][:4] == ["#/larder", "#/pantry", "#/demo", "#/larder"]
    assert hashes[9] == "#/", "g a is All"
    assert hashes[11] == "#/", "p or a alone, with no g before it, does nothing"
    assert seen["walked"][12]["open"] and hashes[12] == "#/help"
    assert hashes[14] == "#/" and not seen["walked"][14]["open"], "g a from a drawer is All"


def test_no_key_fires_while_typing_in_a_field_and_esc_there_leaves_it_first(scene, tmp_path):
    number = gated(scene)[1]
    lineup(scene, TODAY)
    field = "#gwords"
    walk = [f"open:gate:{number}", f"key:g:{field}", f"key:a:{field}", f"key:g:{field}"]
    walk += [f"key:p:{field}", f"key:?:{field}", f"key:Escape:{field}", "esc"]
    seen = look(scene, tmp_path, walk=walk, at=4000 + 500 * len(walk), budget=16000)
    assert seen["errors"] == []
    gate = f"#/demo/gate/{number}"
    steps = seen["walked"]
    assert [step["hash"] for step in steps[:7]] == [gate] * 7
    assert all(step["open"] for step in steps[:7])
    assert steps[5]["title"] == steps[0]["title"], "? in a field opens no glossary"
    assert steps[6]["focus"] != "gwords", "the first Esc leaves the field and keeps the drawer"
    assert (steps[7]["hash"], steps[7]["open"]) == ("#/demo", False)


def test_a_tick_is_no_field_so_esc_on_it_goes_back_and_g_a_goes_to_every_project(scene, tmp_path):
    gated(scene)
    lineup(scene, TODAY)
    tick = "#dw [data-tick]"
    walk = ["open:you:gate", f"key:Escape:{tick}", "open:you:gate", f"key:g:{tick}", "key:a:"]
    seen = look(scene, tmp_path, walk=walk, at=4000 + 500 * len(walk), budget=14000)
    assert seen["errors"] == []
    opened, esc, _, _, keyed = seen["walked"]
    assert (opened["hash"], opened["open"]) == ("#/demo/you/gate", True)
    assert (esc["hash"], esc["open"]) == ("#/demo", False)
    assert (keyed["hash"], keyed["open"]) == ("#/", False)


@pytest.mark.parametrize(
    ("route", "hash", "title", "crumbs", "notice", "tap"),
    [
        ("#/", "#/", "", [["All projects", "#/"]], "", "#title .crumbs a[aria-current]"),
        (
            "#/demo",
            "#/demo",
            "",
            [["All", "#/"], ["demo", "#/demo"]],
            "",
            "#title .crumbs a[aria-current]",
        ),
        (
            "#/help",
            "#/help",
            "Every term on the page",
            [["All", "#/"], ["Every term on the page", "#/help"]],
            "",
            "#dw .crumbs a[aria-current]",
        ),
        (
            "#/%E0",
            "#/%E0",
            "",
            [["All", "#/"], ["%E0", "#/%25E0"]],
            "No project named %E0",
            "#title .crumbs a[aria-current]",
        ),
        (
            "?project=demo",
            "#/demo",
            "",
            [["All", "#/"], ["demo", "#/demo"]],
            "",
            "#title .crumbs a[aria-current]",
        ),
    ],
)
def test_an_address_read_and_written_again_names_the_same_view(
    scene, tmp_path, route, hash, title, crumbs, notice, tap
):
    """The page reads where it is from the address alone, and writes each link it draws from
    what it read: `#/` is every project, `#/<project>` one, `#/help` the glossary over every
    project, a part that is no name (`%E0`) a project kept as it was written, and an old
    `?project=` link is rewritten to its route. Followed, the link to where the page is
    names the same view again."""
    said_by_him(scene)
    first, again = walked(scene, tmp_path, route, ["look", f"tap:{tap}"])
    assert (first["hash"], first["title"], first["crumbs"]) == (hash, title, crumbs)
    assert first["notice"].startswith(notice), first["notice"]
    assert again["hash"] == crumbs[-1][1]
    assert (again["title"], again["crumbs"]) == (title, crumbs)
    assert again["notice"].startswith(notice), again["notice"]


def test_the_new_noticed_lines_are_a_count_beside_the_queue_that_opens_their_panel(scene, tmp_path):
    lineup(scene, TODAY)
    a_noticed(
        scene,
        *((slug, "new", 5 + at, {}) for at, slug in enumerate(("tea-kettle", "jam-kettle"))),
        ("oat-kettle", "dropped", 400, {"why": "from before the list", "by": "jbus"}),
    )
    seen = look(scene, tmp_path)
    opened = clean(seen)
    tile = seen["needs"]["extra"][-1]
    assert (tile["text"], tile["open"]) == ("2 noticed, not counted", "noticed")
    assert "term:noticed" in seen["tips"]
    assert not any("noticed" in one["what"] for one in seen["needs"]["now"] + seen["needs"]["soon"])
    assert "noticed" in opened
    drawer = {one["target"]: one for one in seen["opened"]}["noticed"]
    assert drawer["title"] == "2 new lines of 3, newest first"
    assert seen["words"] <= WORDS, seen["words"]

    a_noticed(scene, ("oat-kettle", "dropped", 400, {"why": "from before the list"}))
    seen = look(scene, tmp_path)
    assert seen["needs"]["extra"] == []
    assert seen["words"] <= WORDS, seen["words"]


def test_the_queue_says_noticed_is_not_counted_and_why(scene, tmp_path):
    lineup(scene, TODAY)
    a_noticed(
        scene, *((slug, "new", 5 + at, {}) for at, slug in enumerate(("tea-kettle", "jam-kettle")))
    )
    walk = ['tap:#nx [data-tip="term:noticed"]']
    seen = look(scene, tmp_path, walk=walk, at=4500, budget=12000)
    assert seen["errors"] == []
    assert [t["text"] for t in seen["needs"]["extra"]] == ["2 noticed, not counted"]
    assert seen["needs"]["head"] == "4 Needs you"
    (tapped,) = seen["walked"]
    assert tapped["tip"].startswith("Noticed, not counted")
    assert "wait on a home, not on you" in tapped["tip"]
