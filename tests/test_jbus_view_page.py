"""The page of `jbus view`, opened in a headless browser and counted, at the size of a desk's
screen, 1440 by 900, and of a phone's, 390 by 844.

Each test starts the real server over a made-up state directory, as `test_jbus_view.py`
does, and puts a small proxy in front of it. The proxy adds a probe to the page: it counts
the words on the first screen, opens every drawer, and writes what it found into the page,
which the browser then prints. The proxy can also stop passing requests on, which is how
the page meets a server that is gone, and it writes down each write the page makes before
it passes it on: a test may do something first, or have the write meet no server. The
browser opens no window under 500 wide, so for the phone the proxy gives it a page that
holds the real one in a frame of the phone's size.

These tests start a browser, so each run of it holds the machine's browser lock,
`~/.local/state/locks/browser.lock`, where that file's directory is there: one browser of
these tests is up at a time on the machine, however many runs there are. A test waits
`PATIENCE` seconds for it and then fails with a line that says so. It is a lock of their own
and not the heavy-suite lock, `heavy-suite.lock` beside it, so a run under `flock` on that
one waits on nothing it holds itself. With no `chromium` on `PATH` a desk skips them, and a
runner (GitHub Actions sets `GITHUB_ACTIONS` to true) fails every one: a check that passed
there would say the page was opened. `JSTACK_TEST_BROWSER` names another browser to open it
in. The check names Google Chrome on GitHub's runner, whose Chromium is a snapshot build that
now and then never starts its virtual time: the page runs on the clock and the browser never
prints it.

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
LOCK = Path.home() / ".local" / "state" / "locks" / "browser.lock"
PAGE = Path(view.__file__).with_name("page.html")
WORDS = 150
EVERY = 250
PATIENCE = 240
LAUNCH = 60
STOPPED = (124, 137)
BROWSES = 5
FONTS = Path(__file__).parent / "fixtures" / "jbus-view" / "fonts.conf"
pytestmark = pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)
DESK, PHONE = (1440, 900), (390, 844)
NARROWEST = 500
THUMB = 44
CARDS = ["jbus", "room", "threads", "CI checks on GitHub", "bus", "blind spots"]
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

    def __init__(self, upstream, at, task="", pick="", gates=None, probe=True, tap="", walk=None):
        self.upstream, self.dark, self.states = upstream, False, 0
        self.dark_after = None
        self.asked, self.stacks = [], 0
        self.alter = lambda nth, body: body
        self.refused = ()
        self.writes = []
        self.on_write = lambda nth: None
        asked = f"window.__task = {json.dumps(task)}; window.__pick = {json.dumps(pick)};"
        asked += f"window.__gates = {json.dumps(gates)}; window.__tap = {json.dumps(tap)};"
        asked += f"window.__walk = {json.dumps(walk)};"
        head = f"<script>window.__at = {at}; {asked}{PROBE}</script>"
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


@contextmanager
def heavy():
    """The machine's browser lock, held while a browser runs.

    It is the file `LOCK`, which only these tests take, so one of their browsers is up at
    a time. The run's caller may hold the heavy-suite lock: that is another file, and
    nothing here waits on it. It waits `PATIENCE` seconds for the lock and then fails the
    test with one line: a check that waits without end reads as one that hangs.
    """
    if not LOCK.parent.is_dir():
        yield
        return
    with open(LOCK, "a") as lock:
        until = time.monotonic() + PATIENCE
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > until:
                    pytest.fail(
                        f"{LOCK} was held for {PATIENCE} s: other runs of these tests had "
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
):
    """Open the page in the browser and give back what the probe found. The server is one
    started here over the scene, or the one that listens on `port`. The page is the scene's
    project, `#/demo`, or the `route` given, as `#/` for every project, and `fragment` is
    more of the address after it, as `theme=dark`. `alter` is given the count of
    each answer of `/stack.json` and its body, and gives back the body the page gets, and
    `tap` selects what the probe taps 3 s after the page loads, and `walk` is the steps the
    probe takes from 2.5 s on, one each 0.5 s, as `back` or `open:task:oat-bowl`. With
    `gates`, the
    probe answers them, and what it found has each write the page made under `writes`.
    `on_write` is called with the count of each write before it is passed on, and a write
    it answers `dark` for meets no server."""
    served = None if port else Served(scene)
    proxy = Proxy(port or served.port, at, task, pick, gates, tap=tap, walk=walk)
    proxy.on_write = on_write or proxy.on_write
    proxy.alter = alter or proxy.alter
    proxy.dark_after = dark_after
    fragment = (f"#/{scene.name}" if route is None else route) + (
        "&" + fragment.lstrip("#") if fragment else ""
    )
    url, window = address(proxy.port, screen, fragment)
    try:
        ran = browse(
            "--hide-scrollbars",
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
def one_browser_at_a_time():
    """The browser lock, held for the whole test: one wait for it, whatever it browses."""
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


def test_a_run_under_the_heavy_suite_lock_is_not_waited_on(tmp_path, monkeypatch):
    """The user's rule runs a suite of several workers under `flock` on the heavy-suite lock.
    The two locks are files of their own names in one directory, here a made-up one."""
    monkeypatch.setattr("test_jbus_view_page.LOCK", tmp_path / LOCK.name)
    monkeypatch.setattr("test_jbus_view_page.PATIENCE", 1)
    with open(tmp_path / "heavy-suite.lock", "a") as outer:
        fcntl.flock(outer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with heavy():
            pass


def test_two_runs_at_once_never_have_a_browser_each(tmp_path, monkeypatch):
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

    monkeypatch.setattr("test_jbus_view_page.LOCK", tmp_path / LOCK.name)
    monkeypatch.setattr(subprocess, "Popen", Browser)
    monkeypatch.setattr(os, "killpg", lambda group, sent: None)
    runs = [threading.Thread(target=run) for _ in range(2)]
    for one in runs:
        one.start()
    for one in runs:
        one.join()
    assert most == [1, 1]


def test_a_browser_that_never_finishes_is_stopped_with_every_process_it_started(
    tmp_path, monkeypatch
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


def test_a_browser_that_ignores_term_is_killed_and_named_too(tmp_path, monkeypatch):
    """`timeout` then kills its whole group, itself with it, and the run ends on a signal."""
    child = hanging(tmp_path, monkeypatch, "trap '' TERM\n")
    monkeypatch.setattr("test_jbus_view_page.LAUNCH", 2)
    started = time.monotonic()
    with pytest.raises(pytest.fail.Exception, match="the browser did not finish in 2 s"):
        browse("http://127.0.0.1:9/")
    assert time.monotonic() - started < 20
    time.sleep(0.5)
    assert not Path(f"/proc/{child.read_text().strip()}").exists()


def test_a_browser_stopped_from_outside_leaves_no_process_it_started(tmp_path, monkeypatch):
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
    monkeypatch.setattr("test_jbus_view_page.LOCK", tmp_path / LOCK.name)
    return child


def test_the_first_screen_has_three_bands_and_everything_on_it_opens_one_drawer(scene, tmp_path):
    seen = look(scene, tmp_path, task="oat-milk")
    opened = clean(seen)
    assert [(card["tag"], card["seen"]) for card in seen["cards"]] == [(tag, True) for tag in CARDS]
    assert [card["open"] for card in seen["cards"]] == [
        "pulse",
        "room",
        "threads",
        "checks",
        "bus",
        "blind",
    ]
    said = {card["tag"]: card["val"] for card in seen["cards"]}
    assert re.fullmatch(r"passing \d\d:\d\d", said["jbus"]), said["jbus"]
    assert said["CI checks on GitHub"] == "1 running oat-milk 0 waiting for a runner 0 failed"
    assert (said["room"], said["bus"], said["blind spots"]) == ("ok", "2 in outbox", "6")
    assert seen["count"] == "4 wait on you"
    assert [(tile["text"], tile["open"]) for tile in seen["tiles"]] == [
        ("1 at a gate 50m", "you:row"),
        ("1 need your word 12m", "you:hold"),
        ("1 to approve 0m", "you:approve"),
        ("1 gates 3h00", "you:gate"),
    ]
    assert [(lane["name"], lane["seen"]) for lane in seen["lanes"]] == [
        (lane, True) for lane in LANES
    ]
    assert [lane["open"] for lane in seen["lanes"]] == [
        "steps:queued",
        "steps:running",
        "steps:gate",
        "steps:result",
        "steps:review",
        "steps:findings",
        "steps:second",
        "steps:check",
        "steps:proof",
        "steps:rebase",
        "steps:hold",
        "merged",
    ]
    lanes = {lane["name"]: lane for lane in seen["lanes"]}
    assert {name: [token["slug"] for token in lane["tokens"]] for name, lane in lanes.items()} == {
        "Queued": ["tea-kettle", "tea-tray", "tea-cups"],
        "Running": ["jam-jar"],
        "Gate": ["jam-lid"],
        "Result": [],
        "Review": [],
        "Findings": [],
        "Second pass": ["oat-spoon"],
        "Check": ["oat-milk"],
        "Proof": [],
        "Rebase": ["oat-bowl"],
        "Needs you": ["oat-honey"],
        "Merged": [],
    }
    assert [dot["open"] for dot in lanes["Merged"]["dots"]] == ["task:rye-loaf"]
    assert lanes["Merged"]["count"] == 1
    tokens = {token["slug"]: token for lane in seen["lanes"] for token in lane["tokens"]}
    assert {slug: token["who"] for slug, token in tokens.items()} == {
        "tea-kettle": "user",
        "tea-tray": "bus",
        "tea-cups": "dep",
        "jam-jar": "crew",
        "jam-lid": "user",
        "oat-spoon": "rev",
        "oat-milk": "ci",
        "oat-bowl": "crew",
        "oat-honey": "user",
    }
    assert all(token["shape"] and token["seen"] for token in tokens.values())
    assert {token["wrap"] for token in tokens.values()} == {"tw"}
    assert (tokens["oat-bowl"]["long"], tokens["oat-bowl"]["again"]) == (True, False)
    assert (tokens["oat-milk"]["long"], tokens["oat-milk"]["again"]) == (False, True)
    assert (tokens["tea-tray"]["long"], tokens["tea-tray"]["again"]) == (False, False)
    once = set(seen["first"])
    assert {card["open"] for card in seen["cards"]} <= once
    assert {tile["open"] for tile in seen["tiles"]} | {"you"} <= once
    assert {lane["open"] for lane in seen["lanes"]} <= once
    assert {f"task:{slug}" for slug in tokens} | {"task:rye-loaf"} <= once
    assert once <= opened
    assert seen["body"] == "" and seen["banner"] == ""
    assert "#13 open" in seen["github"] and "in progress" in seen["github"]


def test_the_jbus_card_names_a_source_only_when_one_is_missing_stale_or_unreadable(scene, tmp_path):
    (scene.state / "queue.json").write_text("{not json")
    (scene.state / "main.json").unlink()
    (scene.state / "stall.json").unlink()
    seen = look(scene, tmp_path)
    opened = clean(seen)
    card = seen["cards"][0]
    assert re.fullmatch(
        r"passing \d\d:\d\d queue\.json unreadable, main\.json missing \+1 more", card["val"]
    ), card["val"]
    assert card["label"].endswith(
        ". queue.json is unreadable, main.json is missing, stall.json is missing"
    )
    assert (card["open"], "sources" in opened) == ("pulse", False)
    assert seen["cards"][-1]["val"] == "8"


def test_the_checks_card_says_what_runs_what_waits_for_a_runner_and_what_failed(scene, tmp_path):
    scene.github(
        runs=[
            ("rye-crust", "completed", "failure"),
            ("rye-crust", "completed", "timed_out", "lint"),
            ("kale-chip", "waiting", None),
            ("fig-jam", "completed", "failure"),
            ("fig-jam", "completed", "success"),
            ("oat-milk", "completed", "cancelled"),
            ("oat-milk", "in_progress", None),
            ("tea-tray", "in_progress", None),
            ("jam-lid", "queued", None),
        ]
    )
    seen = look(scene, tmp_path)
    clean(seen)
    card = {one["tag"]: one for one in seen["cards"]}["CI checks on GitHub"]
    assert card["val"] == (
        "2 running oat-milk, tea-tray 1 waiting for a runner jam-lid 1 failed rye-crust"
    )
    assert card["label"] == (
        "The repo's checks on GitHub: 2 running, 1 waiting for a runner, 1 failed"
    )
    drawer = {one["target"]: one for one in seen["opened"]}["checks"]
    assert drawer["title"] == "CI checks on GitHub"
    assert drawer["now"].startswith("NOW 2 running, 1 waiting for a runner, 1 failed A check is")


def test_the_first_screen_of_a_project_of_todays_size_is_no_more_than_150_words(scene, tmp_path):
    open_rows = lineup(scene, TODAY)
    assert len(open_rows) == 28
    seen = look(scene, tmp_path)
    opened = clean(seen)
    assert seen["font"] == 17.5
    assert seen["words"] <= WORDS, seen["words"]
    assert seen["bottom"] <= DESK[1]
    assert sum(len(lane["tokens"]) for lane in seen["lanes"]) == 28
    assert len(seen["lanes"][-1]["dots"]) == 30
    assert {f"task:{slug}" for slug in open_rows} <= set(seen["first"]) <= opened
    assert len(opened) >= 28 + 30 + 12 + 6


def test_the_overview_of_a_day_of_todays_size_is_no_more_than_250_words(scene, tmp_path):
    lineup(scene, TODAY)
    stacked(scene)
    seen = look(scene, tmp_path, route="#/")
    clean(seen)
    assert [row["project"] for row in seen["stack"]["rows"]] == ["demo", "larder", "pantry"]
    assert seen["words"] <= EVERY, seen["words"]
    assert all(row["seen"] for row in seen["stack"]["rows"])


def test_a_bare_link_shows_every_project_once_from_one_request_a_poll(scene, tmp_path):
    """The machine once, one wait band whose total is the sum of its rows, and a row for each
    project with only the steps that hold a task. The page asks `/stack.json` and nothing
    else, once a poll, and a poll that changed nothing draws nothing again."""
    stacked(scene)
    a_noticed(scene, ("tea-kettle", "new", 5, {}))
    seen = look(scene, tmp_path, route="#/", at=33000, budget=40000)
    assert clean(seen) == set()
    stack = seen["stack"]
    assert (stack["shown"], stack["title"], stack["none"]) == (True, "jbus: every project", "")
    assert [(card["tag"].lower(), card["seen"]) for card in stack["machine"]] == [
        ("jbus", True),
        ("room", True),
        ("runners", True),
        ("plan", True),
    ]
    assert [card["val"] for card in stack["machine"][1:]] == [
        "ok",
        "3 of 3 active",
        "5h 23% 7d 22%",
    ]
    assert [(row["project"], row["count"]) for row in stack["waits"]] == [
        ("demo", 4),
        ("larder", 0),
        ("pantry", 1),
    ]
    assert stack["total"] == "5 wait on you"
    assert int(stack["total"].split()[0]) == sum(row["count"] for row in stack["waits"])
    waits = {row["project"]: row for row in stack["waits"]}
    assert [token["text"] for token in waits["demo"]["tokens"]] == [
        "1 at a gate 50m",
        "1 need your word 12m",
        "1 to approve 0m",
        "1 gates 3h00",
        "1 noticed, not counted",
    ]
    assert [token["href"] for token in waits["demo"]["tokens"]][-2:] == [
        "#/demo/you/gate",
        "#/demo/noticed",
    ]
    assert all(token["tip"].startswith("demo: ") for token in waits["demo"]["tokens"])
    assert [token["tip"] for token in waits["pantry"]["tokens"]] == [
        "pantry: 1 at a gate, the oldest for 40m"
    ]
    assert (waits["larder"]["tokens"], waits["larder"]["quiet"]) == ([], "nothing waits on you")
    rows = {row["project"]: row for row in stack["rows"]}
    assert [row["project"] for row in stack["rows"]] == ["demo", "larder", "pantry"]
    assert all(row["seen"] and row["box"][2] >= 1300 for row in stack["rows"])
    assert rows["demo"]["head"] == "demo acme/demo, 9 open tasks, 1 merged today Open ›"
    assert rows["demo"]["chips"] == [
        "CI 1 running, 0 failed",
        "Bus 2 in outbox",
        "Threads 0 out",
        "Blind 1",
    ]
    assert [cell[0] for cell in rows["demo"]["cells"]] == [
        "3 Queued",
        "1 Running",
        "1 Gate",
        "1 Second pass",
        "1 Check",
        "1 Rebase",
        "1 Needs you",
        "1 Merged",
    ]
    assert rows["pantry"]["cells"] == [
        ["1 Running", "#/pantry/steps/running"],
        ["1 Gate", "#/pantry/steps/gate"],
        ["1 Merged", "#/pantry/merged"],
    ]
    assert (rows["larder"]["cells"], rows["larder"]["empty"]) == ([], "nothing open")
    assert rows["pantry"]["empty"] == ""
    assert [row["opens"] for row in stack["rows"]] == ["#/demo", "#/larder", "#/pantry"]
    assert seen["words"] <= EVERY, seen["words"]
    polls = [asked for asked in seen["asked"] if asked not in ("/", "/favicon.ico")]
    assert len(polls) == 3 and set(polls) == {"/stack.json"}
    drawn = [change["at"] for change in seen["changes"] if change["part"].startswith("rows:")]
    assert drawn and [one for one in seen["changes"] if one["at"] > max(drawn) + 1000] == []
    assert seen["marked"] == 1


def test_a_poll_draws_again_only_the_parts_whose_data_changed(scene, tmp_path):
    stacked(scene)

    def more(nth, body):
        if nth > 1:
            pantry = next(one for one in body["projects"] if one["name"] == "pantry")
            pantry["waits"] += 1
            pantry["waiting"]["approve"] = {"count": 1, "since": None}
        return body

    seen = look(scene, tmp_path, route="#/", at=20000, budget=25000, alter=more)
    clean(seen)
    first = max(one["at"] for one in seen["changes"] if one["part"].startswith("rows:"))
    later = {one["part"] for one in seen["changes"] if one["at"] > first + 1000}
    assert later == {"wtotal", "yrows:pantry"}
    assert seen["stack"]["total"] == "6 wait on you"


def test_a_row_opens_its_project_and_an_old_link_opens_it_too(scene, tmp_path):
    stacked(scene)
    seen = look(
        scene,
        tmp_path,
        route="#/",
        tap='#rows .proj[data-key="pantry"] .chips',
        at=6000,
        budget=9000,
    )
    clean(seen)
    assert seen["hash"] == "#/pantry"
    assert (seen["stack"]["shown"], seen["count"]) == (False, "1 wait on you")
    assert [lane["tokens"][0]["slug"] for lane in seen["lanes"] if lane["tokens"]] == [
        "fig-jam",
        "fig-tart",
    ]
    seen = look(scene, tmp_path, route="?project=pantry")
    clean(seen)
    assert (seen["hash"], seen["count"]) == ("#/pantry", "1 wait on you")
    assert "/stack.json" not in seen["asked"]


def test_a_link_to_a_project_that_is_not_there_says_so_and_reads_no_retired_one(scene, tmp_path):
    stacked(scene)
    seen = look(scene, tmp_path, route="#/hydra")
    assert seen["errors"] == [] and "gone" not in seen["body"]
    assert seen["stack"]["none"] == (
        "No project named hydra jbus looks after no project of that name: a retired project "
        "is not shown. Every project"
    )
    assert seen["first"] == [] and seen["cards"] == []
    seen = look(scene, tmp_path, route="#/")
    assert "hydra" not in json.dumps(seen["stack"])
    seen = look(scene, tmp_path, route="#/%E0")
    assert seen["errors"] == [] and seen["stack"]["none"].startswith("No project named %E0 ")


def test_on_a_phone_every_project_is_one_column_with_nothing_cut(scene, tmp_path):
    lineup(scene, TODAY)
    stacked(scene)
    seen = look(scene, tmp_path, route="#/", screen=PHONE)
    clean(seen, PHONE)
    assert seen["cut"] == []
    assert [row["project"] for row in seen["stack"]["rows"]] == ["demo", "larder", "pantry"]


def test_the_new_noticed_lines_are_a_count_in_the_wait_band_that_opens_their_panel(scene, tmp_path):
    lineup(scene, TODAY)
    a_noticed(
        scene,
        *((slug, "new", 5 + at, {}) for at, slug in enumerate(("tea-kettle", "jam-kettle"))),
        ("oat-kettle", "dropped", 400, {"why": "from before the list", "by": "jbus"}),
    )
    seen = look(scene, tmp_path)
    opened = clean(seen)
    assert (seen["tiles"][-1]["text"], seen["tiles"][-1]["open"]) == ("2 noticed", "noticed")
    assert "noticed" in opened
    drawer = {one["target"]: one for one in seen["opened"]}["noticed"]
    assert drawer["title"] == "2 new lines of 3, newest first"
    assert seen["words"] <= WORDS, seen["words"]

    a_noticed(scene, ("oat-kettle", "dropped", 400, {"why": "from before the list"}))
    seen = look(scene, tmp_path)
    assert [tile["open"] for tile in seen["tiles"] if tile["open"] == "noticed"] == []
    assert seen["words"] <= WORDS, seen["words"]


def test_forty_open_tasks_keep_what_matters_first_on_the_first_screen(scene, tmp_path):
    """What waits on the user, what is blocked and what is running are above the fold of the
    browser's own window, which is lower than the screen. The steps after them scroll."""
    open_rows = lineup(scene, FORTY)
    assert len(open_rows) == 40
    seen = look(scene, tmp_path, budget=9000)
    clean(seen)
    tokens = [token for lane in seen["lanes"] for token in lane["tokens"]]
    assert len(tokens) == 40
    assert seen["band"][1] + seen["band"][3] <= seen["high"]
    assert all(tile["seen"] for tile in seen["tiles"])
    first = {lane["name"]: lane for lane in seen["lanes"][:3]}
    assert list(first) == ["Queued", "Running", "Gate"]
    assert all(lane["box"][1] + lane["box"][3] <= seen["high"] for lane in first.values())
    assert [len(lane["tokens"]) for lane in first.values()] == [14, 8, 2]
    assert all(token["seen"] for lane in first.values() for token in lane["tokens"])
    assert sum(1 for token in first["Queued"]["tokens"] if token["mark"]) == 11
    assert seen["words"] <= 200, seen["words"]


def test_a_day_with_no_open_task_stays_on_one_screen_and_says_so(scene, tmp_path):
    assert lineup(scene, {}, merged=4, gates=0) == []
    seen = look(scene, tmp_path)
    clean(seen)
    assert seen["bottom"] <= DESK[1]
    assert seen["calm"] is True
    assert seen["count"] == "0 wait on you"
    assert [lane["count"] for lane in seen["lanes"]] == [0] * 11 + [4]
    assert seen["words"] <= WORDS, seen["words"]


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
    lanes = {lane["name"]: lane for lane in seen["lanes"]}
    tokens = {token["slug"]: token for lane in seen["lanes"] for token in lane["tokens"]}
    assert {"fig-pip", "fig-tree", "nut-oil"} & set(tokens) == set()
    assert "task:fig-pip" in [dot["open"] for dot in seen["lanes"][-1]["dots"]]
    marked = {slug: (one["blocked"], one["blocker"], one["blocks"]) for slug, one in tokens.items()}
    assert marked["nut-shell"] == ("findings", "task:nut-shell", "2")
    assert marked["nut-meat"] == ("nut-shell", "task:nut-shell", "1")
    ready, coming, later = lanes["Queued"]["lines"]
    assert (ready["name"], coming["name"], later["name"]) == ("Ready", "Next", "Later")
    assert [one[0] for one in ready["tokens"]] == ["fig-husk", "fig-seed", "fig-jam"]
    assert coming["tokens"] == [
        ["fig-fly", "fig-gone"],
        ["fig-leaf", "fig-seed"],
        ["fig-sap", "fig-tart", "+1"],
        ["fig-stem", "fig-pip"],
        ["nut-meat", "nut-shell"],
    ]
    assert later["waves"] == [[2, ["nut-oil"]]]
    assert tokens["fig-sap"]["label"] == (
        "fig-sap: Behind, waits for fig-tart to merge, waits on fig-tart and 1 more"
    )
    assert tokens["fig-seed"]["label"].endswith(", blocked by approval, 1 task waits behind it")
    assert seen["flow"]["chain"] == "3 deep, behind nut-shell (Findings)"
    way = seen["picked"]
    assert (way["picked"], way["up"], way["down"]) == (["fig-sap"], ["fig-tart"], [])
    assert way["said"] == (
        "fig-sap waits on 1 row here and on fig-pip (Merged), and 0 rows wait on it."
    )
    assert [(dot["open"], dot["label"]) for dot in later["dots"]] == [
        ("task:nut-oil", "nut-oil waits on nut-meat, in wave 2")
    ]
    assert marked["fig-seed"] == ("approval", "task:fig-seed", "1")
    assert marked["fig-stem"] == ("fig-pip", "task:fig-pip", "")
    assert marked["fig-sap"] == ("fig-tart", "task:fig-tart", "")
    assert marked["fig-fly"] == ("fig-gone", "task:fig-fly", "")
    assert marked["fig-root"][0] == marked["fig-stalk"][0] == "thread"
    assert marked["fig-tart"] == ("", "task:fig-tart", "1")
    assert all(one["mark"] == bool(one["blocked"]) for one in tokens.values())
    now = {one["target"].removeprefix("task:"): one["now"] for one in seen["opened"]}
    assert {f"task:{slug}" for slug in expected} <= opened
    tiles = {tile["open"]: tile["text"] for tile in seen["tiles"]}
    assert tiles["you:left"].startswith("2 left over")
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


def test_an_unknown_task_has_a_lane_of_its_own_and_a_pass_that_could_not_ask_marks_every_task(
    scene, tmp_path
):
    rows = json.loads((scene.state / "queue.json").read_text())
    scene.queue([*rows, row("yam-root", "pr", pr="#61", why="wait: another home's")])
    record = json.loads((scene.state_dir / "pass.json").read_text())
    scene.write("pass.json", record | {"silent": {scene.name: "GitHub"}}, scene.state_dir)
    past = int(ago(hours=1).timestamp())
    (scene.root / "limits").write_text(f"five_hour 23.0 {past}\nseven_day 22.0 {past}\n")
    seen = look(scene, tmp_path)
    opened = clean(seen)
    assert [lane["name"] for lane in seen["lanes"]] == ["Unknown", *LANES]
    lane = seen["lanes"][0]
    assert (lane["open"], lane["count"], lane["seen"]) == ("steps:unknown", 1, True)
    assert [(token["slug"], token["who"]) for token in lane["tokens"]] == [("yam-root", "unknown")]
    tokens = [token for lane in seen["lanes"] for token in lane["tokens"]]
    assert {token["border"] for token in tokens} == {"dashed"}
    assert {"steps:unknown", "task:yam-root", "room"} <= opened
    now = {one["target"]: one["now"] for one in seen["opened"]}
    assert now["task:yam-root"].startswith("NOW: UNKNOWN jmerge said: another home's"), now
    for token in tokens:
        said = now[token["open"]]
        assert "not confirmed since 2026-10-12 15:59 ET: GitHub did not answer." in said, said
    assert seen["meters"] == 4
    assert "limits" not in seen["cards"][0]["val"] + seen["cards"][0]["label"]
    assert seen["words"] <= WORDS, seen["words"]


def lines_of(seen):
    """The Queued lane as the probe read it: its tokens that show, and its three lines."""
    lane = seen["lanes"][0]
    assert lane["name"] == "Queued"
    return [token["slug"] for token in lane["tokens"] if token["shown"]], lane["lines"]


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_a_queue_of_five_rows_no_deeper_than_wave_one_is_one_line_as_before(
    scene, tmp_path, screen
):
    ready, coming = flowing(scene, FLOWS[5])
    seen = look(scene, tmp_path, budget=9000, screen=screen)
    clean(seen, screen)
    tokens, lines = lines_of(seen)
    assert (tokens, lines) == ([*ready, *coming], [])
    queued = {token["slug"]: token for token in seen["lanes"][0]["tokens"]}
    assert [(queued[slug]["blocked"], queued[slug]["mark"]) for slug in coming] == [
        ("tea-kettle", True),
        ("rye-kettle", True),
    ]
    assert seen["words"] <= WORDS, seen["words"]


@pytest.mark.parametrize(
    ("sizes", "lines"),
    [((4, 4), []), ((5, 4), ["Ready", "Next", "Later"]), ((2, 1, 1), ["Ready", "Next", "Later"])],
)
def test_the_lane_is_three_lines_past_eight_rows_or_past_wave_one(scene, tmp_path, sizes, lines):
    waves = flowing(scene, sizes)
    seen = look(scene, tmp_path, budget=9000)
    clean(seen)
    tokens, found = lines_of(seen)
    assert [one["name"] for one in found] == lines
    assert tokens == waves[0] + waves[1]
    assert [wave for one in found for wave in one["waves"]] == [
        [at + 2, wave] for at, wave in enumerate(waves[2:])
    ]


@pytest.mark.parametrize(
    ("rows", "shown", "more"),
    [(25, (6, 5), ([], [])), (60, (8, 8), ([["+12", "flow"]], [["+6", "flow"]]))],
)
def test_a_full_queue_is_three_lines_at_a_desk_and_a_row_in_later_costs_no_word(
    scene, tmp_path, rows, shown, more
):
    waves = flowing(scene, FLOWS[rows])
    seen = look(scene, tmp_path, budget=9000)
    opened = clean(seen)
    tokens, (ready, coming, later) = lines_of(seen)
    assert [(one["name"], one["count"]) for one in (ready, coming, later)] == [
        ("Ready", len(waves[0])),
        ("Next", len(waves[1])),
        ("Later", rows - len(waves[0]) - len(waves[1])),
    ]
    assert [one[0] for one in ready["tokens"]] == waves[0][: shown[0]]
    assert coming["tokens"][:4] == [
        [waves[1][0], "tea-kettle"],
        [waves[1][1], waves[0][1], "+1"],
        [waves[1][2], waves[0][2]],
        [waves[1][3], waves[0][3], "+1"],
    ]
    assert tokens == waves[0][: shown[0]] + waves[1][: shown[1]]
    assert (ready["more"], coming["more"], later["more"]) == (*more, [])
    assert later["waves"] == [[at + 2, wave] for at, wave in enumerate(waves[2:])]
    assert [(dot["open"], dot["words"]) for dot in later["dots"]] == [
        (f"task:{slug}", "") for wave in waves[2:] for slug in wave
    ]
    assert all(dot["label"].startswith(f"{dot['open'][5:]} waits on ") for dot in later["dots"])
    assert {"flow", *(dot["open"] for dot in later["dots"])} <= set(seen["first"]) <= opened
    assert seen["words"] <= WORDS, seen["words"]


@pytest.mark.parametrize(
    ("rows", "more", "button"),
    [
        (25, ("+1 more", None), "14 later, in 6 waves"),
        (60, ("+15 more", "+9 more"), "26 later, in 7 waves"),
    ],
)
def test_on_a_phone_a_full_queue_is_two_lists_cut_at_five_and_one_button_for_later(
    scene, tmp_path, rows, more, button
):
    waves = flowing(scene, FLOWS[rows])
    seen = look(scene, tmp_path, budget=9000, screen=PHONE)
    opened = clean(seen, PHONE)
    tokens, (ready, coming, later) = lines_of(seen)
    assert tokens == waves[0][:5] + waves[1][:5]
    assert (ready["more"], coming["more"]) == tuple([[one, "flow"]] if one else [] for one in more)
    assert (later["more"], later["waves"], later["dots"]) == ([[button, "flow"]], [], [])
    assert (ready["named"], coming["named"], later["named"]) == (True, True, False)
    assert "flow" in opened
    assert (seen["small"], seen["cut"]) == ([], [])
    assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []
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
    else:
        assert seen["filtered"] == {"tokens": 12, "dots": 14}


def test_a_pass_that_could_not_ask_marks_every_dot_and_every_row_of_the_flow(scene, tmp_path):
    flowing(scene, FLOWS[25])
    record = json.loads((scene.state_dir / "pass.json").read_text())
    scene.write("pass.json", record | {"silent": {scene.name: "GitHub"}}, scene.state_dir)
    seen = look(scene, tmp_path, budget=9000, pick="tea-ladle")
    clean(seen)
    _, (_, _, later) = lines_of(seen)
    assert len(later["dots"]) == 14
    assert {dot["border"] for dot in later["dots"]} == {"dashed"}
    assert all("not confirmed since " in dot["label"] for dot in later["dots"])
    assert seen["flow"]["borders"] == ["dashed"]
    assert len(seen["flow"]["labels"]) == 27
    assert all("not confirmed since " in label for label in seen["flow"]["labels"])


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_the_threads_card_counts_them_and_its_drawer_lists_each_by_role(scene, tmp_path, screen):
    """A task whose crewmate is at work has the mark on its token in whatever lane it is, and
    a hung one is said in its drawer with the times."""
    began = iso(ago(minutes=40))
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar", "hung", minutes=25, run_started=began, queued=2),
            out("crew: oat-milk"),
            out("crew: oat-bowl", "quiet", minutes=12),
            out("review: oat-spoon"),
            out("scout: look", "waiting", minutes=90, page=True),
            out("home: demo"),
            out("a thread he opened", "ended", "completed"),
        ],
        rows={
            "jam-jar": {"threads": 1, "thread_status": "running", "live": "hung"}
            | {"thread_updated": iso(ago(minutes=25))},
            "oat-milk": {"threads": 1, "thread_status": "running", "live": "moving"},
            "oat-bowl": {"threads": 1, "thread_status": "running", "live": "quiet"},
        },
    )
    seen = look(scene, tmp_path, budget=9000, screen=screen)
    opened = clean(seen, screen)
    card = {card["tag"]: card for card in seen["cards"]}["threads"]
    assert (card["val"], card["open"], card["seen"]) == ("6 out 1 quiet 1 hung", "threads", True)
    assert card["label"] == "Threads: 6 out, 1 quiet, 1 hung"
    lanes = {lane["name"]: lane["tokens"] for lane in seen["lanes"]}
    assert {token["slug"]: token["live"] for token in lanes["Running"]} == {"jam-jar": "hung"}
    assert {token["slug"]: token["live"] for token in lanes["Check"]} == {"oat-milk": "moving"}
    assert {token["slug"]: token["live"] for token in lanes["Rebase"]} == {"oat-bowl": "quiet"}
    assert {token["live"] for token in lanes["Queued"] + lanes["Gate"]} == {""}
    assert {"threads", "threads:crew", "threads:scout", "threads:reviewer"} <= opened
    drawers = {one["target"]: one for one in seen["opened"]}
    assert {target: drawers[target]["title"] for target in drawers if "threads" in target} == {
        "threads": "6 threads out",
        "threads:crew": "3 crews out",
        "threads:scout": "1 scout out",
        "threads:reviewer": "1 reviewer out",
    }
    assert drawers["threads"]["now"].startswith("AS THE LAST PASS SAW THEM 6 out, 1 quiet, 1 hung")
    assert drawers["threads:crew"]["now"].startswith("AS THE LAST PASS SAW THEM 3 out, 1 quiet, 1")
    assert drawers["threads:scout"]["said"].count("last wrote") == 1
    assert "it holds a page that waits on you" in drawers["threads:scout"]["said"]
    every = drawers["threads"]["said"]
    assert every.count("last wrote") == 7 and "2 runs wait behind it" in every
    assert "1 NOT SETTLED, WITH NO TURN UNDER WAY" in every
    assert re.search(
        r"Its thread is hung: it has written nothing since \d\d:\d\d, 25 min ago, "
        r"its turn started \d\d:\d\d, and 2 runs wait behind it\.",
        drawers["task:jam-jar"]["now"],
    ), drawers["task:jam-jar"]["now"]
    assert "Its thread is quiet: it has written nothing" in drawers["task:oat-bowl"]["now"]
    assert "Its thread is" not in drawers["task:oat-milk"]["now"]
    if screen == PHONE:
        assert (seen["small"], seen["cut"]) == ([], [])
        assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []
        assert {tuple(one["box"]) for one in seen["opened"]} == {(0, 0, *PHONE)}
    else:
        assert seen["words"] <= WORDS, seen["words"]


def test_a_pass_that_left_no_list_of_threads_shows_no_count(scene, tmp_path):
    scene.passed(20, threads=None)
    seen = look(scene, tmp_path)
    clean(seen)
    card = {card["tag"]: card for card in seen["cards"]}["threads"]
    assert (card["val"], card["label"]) == (
        "not known",
        "Threads: the last pass left no list of them",
    )
    drawer = {one["target"]: one for one in seen["opened"]}["threads"]
    assert drawer["title"] == "No count of threads out"
    assert drawer["now"].startswith("NOT KNOWN The last pass left no list")


def frozen(seen, since, said):
    """The page of a jbus that has stopped: the banner, and what is frozen and what live."""
    clean(seen)
    assert seen["body"] == "stopped"
    assert seen["banner"].startswith("jbus has not passed last pass ended " + since)
    assert said in seen["banner"]
    assert seen["halves"] == [
        ["frozen", ["the line", "the wait band", "the bus"]],
        ["live", ["Room", "CI checks", "gates", "GitHub"]],
    ]
    assert re.fullmatch(r"stopped \d\d:\d\d", seen["cards"][0]["val"]), seen["cards"][0]["val"]
    cards = {card["tag"]: (card["state"], card["border"]) for card in seen["cards"]}
    assert (cards["bus"], cards["room"], cards["CI checks on GitHub"]) == (
        ("frozen", "dashed"),
        ("live", "solid"),
        ("live", "solid"),
    )
    assert seen["line"] == "frozen"
    tokens = [token for lane in seen["lanes"] for token in lane["tokens"]]
    assert tokens and {token["border"] for token in tokens} == {"dashed"}
    tiles = {tile["open"]: (tile["state"], tile["border"]) for tile in seen["tiles"]}
    assert tiles == {
        "you:row": ("frozen", "dashed"),
        "you:hold": ("frozen", "dashed"),
        "you:approve": ("frozen", "dashed"),
        "you:gate": ("live", "solid"),
    }
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
    assert (seen["body"], seen["banner"], seen["halves"]) == ("", "", [])
    assert {card["state"] for card in seen["cards"]} == {""}
    assert {tile["state"] for tile in seen["tiles"]} == {""}
    tokens = [token for lane in seen["lanes"] for token in lane["tokens"]]
    assert {token["border"] for token in tokens} == {"solid"}


def test_with_the_server_gone_the_page_says_so_after_two_answers_missed(scene, tmp_path):
    seen = look(scene, tmp_path, at=20000, budget=24000, dark_after=1)
    assert (seen["body"], seen["banner"]) == ("", "")
    seen = look(scene, tmp_path, at=40000, budget=44000, dark_after=1, task="oat-milk")
    clean(seen)
    assert set(seen["body"].split()) == {"stopped", "gone"}
    assert seen["banner"].startswith("the view server does not answer last answer ")
    assert "2 answers missed" in seen["banner"]
    assert [state for state, _ in seen["halves"]] == ["frozen"]
    assert {card["state"] for card in seen["cards"] if card["state"]} == {"frozen"}
    assert {tile["state"] for tile in seen["tiles"]} == {"frozen"}
    assert "GitHub cannot be asked" in seen["github"]
    assert sum(len(lane["tokens"]) for lane in seen["lanes"]) == 9


def test_a_server_that_never_answered_is_said_too(scene, tmp_path):
    seen = look(scene, tmp_path, at=40000, budget=44000, dark_after=0)
    assert seen["errors"] == []
    assert set(seen["body"].split()) == {"stopped", "gone"}
    assert seen["banner"].startswith("the view server does not answer")
    assert seen["cards"] == []


def test_on_a_phone_the_page_is_one_column_and_every_target_takes_a_thumb(scene, tmp_path):
    open_rows = lineup(scene, TODAY)
    seen = look(scene, tmp_path, budget=9000, screen=PHONE)
    opened = clean(seen, PHONE)
    assert {f"task:{slug}" for slug in open_rows} <= opened
    left, top, wide, high = seen["strip"]
    assert (left, wide) == (10, 370) and high <= PHONE[1] // 4
    assert top < seen["band"][1] < seen["lanes"][0]["box"][1]
    assert all(card["seen"] and card["box"][3] >= THUMB for card in seen["cards"])
    assert {(lane["box"][0], lane["box"][2]) for lane in seen["lanes"]} == {(10, 370)}
    assert [lane["box"][1] for lane in seen["lanes"]] == sorted(
        lane["box"][1] for lane in seen["lanes"]
    )
    tokens = [token for lane in seen["lanes"] for token in lane["tokens"] if token["shown"]]
    assert len(tokens) == 26
    assert [line["more"] for line in seen["lanes"][0]["lines"]] == [
        [["+1 more", "flow"]],
        [["+1 more", "flow"]],
        [],
    ]
    assert {token["box"][0] for token in tokens} == {23}
    assert len({token["box"][1] for token in tokens}) == 26
    assert min(token["box"][3] for token in tokens) >= THUMB
    assert (seen["small"], seen["cut"]) == ([], [])
    assert {tuple(one["box"]) for one in seen["opened"]} == {(0, 0, *PHONE)}
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
    seen = look(scene, tmp_path, screen=PHONE)
    clean(seen, PHONE)
    assert seen["body"] == "stopped"
    assert seen["banner"].startswith("jbus has not passed last pass ended ")
    said = {card["tag"]: card["val"] for card in seen["cards"]}
    assert re.fullmatch(
        r"stopped \d\d:\d\d queue\.json unreadable, main\.json missing \+\d more", said["jbus"]
    ), said["jbus"]
    assert said["CI checks on GitHub"] == (
        "GitHub did not answer"
        if github == "down"
        else f"2 running {long}-one, {long}-two 1 waiting for a runner {long}-three "
        f"1 failed {long}-four"
    )
    assert (seen["bus"], seen["meters"]) == ([9, 3], 4)
    assert (seen["small"], seen["cut"]) == ([], [])
    assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []
    assert {tuple(one["box"]) for one in seen["opened"]} == {(0, 0, *PHONE)}


@pytest.mark.parametrize("screen", [DESK, PHONE])
@pytest.mark.parametrize(
    ("fragment", "dark"),
    [("#theme=light", False), ("#theme=dark", True), ("", False)],
)
def test_the_page_is_light_dark_or_as_the_browser_asks(scene, tmp_path, screen, fragment, dark):
    seen = look(scene, tmp_path, fragment=fragment, screen=screen)
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
        ["look", "open:words:approval:tea-cups", "esc", "esc", "forward", "arrow", "cancel"],
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


@pytest.mark.parametrize(
    ("route", "said"),
    [
        ("#/demo/task/no-such-task", "No task named no-such-task in demo"),
        ("#/demo/gate/999", "No gate named 999 in demo"),
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
    assert "by Exec" in task.partition("Approval on your word")[2]
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
    an option its thread recommends. The answer is their numbers."""
    (scene.home / "tasks").mkdir()
    (scene.home / "tasks" / "alpha.md").write_text("# alpha\nThread: mcp:crew-alpha\n")
    lines = PIPED.format(n="<n>", asked="tea or coffee?", status="open", slug="alpha")
    lines += "Context: the pot holds two cups\nOption: both (recommended): a second pot\n"
    first = questions.ask(scene.state, scene.home, "alpha", lines, ago(minutes=25))[0].number
    return [first, asks(scene, "milk?"), asks(scene, "sugar?")]


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
            "marks": ["taken as default"],
            "follows": "nothing changes",
        },
        {"name": "the other", "picked": False, "marks": [], "follows": "one more cup"},
        {
            "name": "both",
            "picked": False,
            "marks": ["the thread recommends"],
            "follows": "a second pot",
        },
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
    served = Served(scene)
    try:
        _, headers, page = served.ask("/")
    finally:
        served.close()
    scripts = [one.script.read_text() for one in panels.found()]
    for part in (PAGE.read_text(), *scripts):
        assert "://" not in part
        for loads in ("<link", "<img", "<iframe", "<object", "<embed", " src=", "@import", "url("):
            assert loads not in part, loads
    asks = ["/answer", "/panel/", "/stack.json", "/state.json", "/task/"]
    assert sorted(set(re.findall(r'ask\("(/[^"]*)"', page))) == asks
    assert "fetch(path," in page and page.count("fetch(") == 1
    assert page.count("<script") == 2 and all(script in page for script in scripts)
    assert "connect-src 'self'" in headers["Content-Security-Policy"]
    assert "default-src 'none'" in headers["Content-Security-Policy"]


def test_every_panel_is_opened_from_the_first_screen_or_from_a_drawer(scene, tmp_path):
    """The scene has a question jbus holds, which is what opens the drawer of a gate."""
    gated(scene)
    a_noticed(scene, ("alpha", "new", 5, {}))
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
    by = {"session": "s-1", "directory": f"/made/up/{queue.EXEC}"}
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
    opens it, and a count to the wait band. Nothing opens `lost`, and the drawer of `thrown`
    throws."""
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
        assert [card["tag"] for card in seen["cards"]] == CARDS
        assert seen["count"] == "4 wait on you"
        assert (seen["tiles"][-1]["text"], seen["tiles"][-1]["open"]) == ("1 sample", "sample")
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


def test_a_runner_that_is_not_active_is_said_on_the_checks_card(scene, tmp_path):
    scene.runners(
        ("actions-runner-a.service", "active", "running"),
        ("actions-runner-b.service", "inactive", "dead"),
    )
    seen = look(scene, tmp_path)
    clean(seen)
    card = {one["tag"]: one for one in seen["cards"]}["CI checks on GitHub"]
    assert card["val"].endswith("1 runner not active actions-runner-b inactive"), card["val"]
    served = Served(scene)
    try:
        drawer = shown(served.port, tmp_path, "checks")
    finally:
        served.close()
    assert "actions-runner-a.service active, running actions-runner-b.service inactive, dead" in (
        drawer
    ), drawer


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
