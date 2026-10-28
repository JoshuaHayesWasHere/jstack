"""These tests open the page of `jbus view` in a headless browser and count its words, at the
size of a desk's screen, 1440 by 900, and of a phone's, 390 by 844.

They limit a view's first screen to `WORDS` words, and the overview of every project to
`EVERY`. They count the shell around it, the header and the sidebar, on its own, and limit it
to `SHELL`. The shell is the same on every view, and it grows by one name and one count for
each project.

Each test starts the real server over a made-up state directory, as the tests of
`features/jbus/tests/view/` do, and puts a small proxy in front of it. The proxy adds a probe to
the page: it counts the words on the first screen, opens every drawer, and writes what it found
into the page, which the browser then prints. The proxy can also stop passing requests on. That
is how a test puts the page in front of a server that is gone. The proxy writes down each write
the page makes before it passes the write on. So a test may do something first, or keep the
write from reaching any server. It keeps the page's counts of what it opened, its posts to
`/usage`, apart from the writes, under `counted`. The browser opens no window under 500 pixels
wide. So for the phone, the proxy gives it a page that has the real one in a frame of the phone's
size.

In place of the probe, the proxy can add axe, `AXE`, which is two files. One is the engine,
vendored for these tests alone in `fixtures/jbus-view/axe.min.js`. The other is `axe-run.js`,
which runs the engine over the view and over every drawer it opens, and measures the focus ring
of everything a key reaches.

These tests start a browser, so each of their modules is marked `browser`: `make check` leaves
them out, and `make check-browser` runs them, nightly and on a release. Where the directory of
`~/.local/state/locks/browser.lock` exists, each run of them takes that file, the machine's
browser lock. So only one browser of these tests runs at a time on the machine, however many
runs there are.
A test waits `PATIENCE` seconds for the lock and then fails with a line that says so. The lock is
theirs alone, and it is not the heavy-suite lock, `heavy-suite.lock` beside it. So a run that has
the heavy-suite lock through `flock` never waits on a lock it already has. With no `chromium` on
`PATH`, a desk skips them and a runner fails every one. (GitHub Actions sets `GITHUB_ACTIONS` to
true on a runner.) A check that passed on a runner would claim that the browser opened the page
when no browser did. `JSTACK_TEST_BROWSER` names another browser to open it in. The browser
workflow names Google Chrome on GitHub's runner. The runner's Chromium is a snapshot build that
now and then never starts its virtual time. Then the page runs on the wall clock, and the
browser never prints it.

Each browser gets `LAUNCH` seconds. It runs under `timeout`, in a process group of its own,
and the whole group ends when the browser ends or when something stops the test. A browser
that runs out of time fails its test with a line that says so. A browser that hangs costs
its test that much time and leaves no process behind. A test takes the lock once, waiting
up to `PATIENCE` seconds, and browses up to `BROWSES` times. The test's own time limit is
longer than all of those, so they run out first, each with a line that names it.

The browser draws the page in Liberation Sans, as `FONTS` asks. Both a desk and a runner have
that font. A desk's own font and a runner's DejaVu Sans set the same words in lines of
different widths.
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
import urllib.parse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from jbus import questions, view
from jbus.view.writes import said
from test_jbus_kitchen import GATE as PIPED
from testing.paths import REPO
from view.scene import (
    REPORTED,
    REQUEST,
    Served,
    ago,
    asks,
    free_port,
    iso,
    out,
    requested,
)

NAMED = os.environ.get("JSTACK_TEST_BROWSER", "")


CHROMIUM = (
    shutil.which(NAMED) if NAMED else shutil.which("chromium") or shutil.which("chromium-browser")
)


WORDS = 150


PATIENCE = 240


LAUNCH = 60


STOPPED = (124, 137)


BROWSES = 5


FONTS = REPO / "features" / "jbus" / "tests" / "fixtures" / "jbus-view" / "fonts.conf"


DESK, PHONE = (1440, 900), (390, 844)


NARROWEST = 500


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


PROBE = (REPO / "features" / "jbus" / "tests" / "fixtures" / "jbus-view" / "probe.js").read_text()


class Proxy:
    """A proxy in front of the server that adds the probe to the page, and can stop passing
    requests on. What it adds to the head of the page is `head`, which a test may replace."""

    def __init__(
        self,
        upstream,
        at,
        task="",
        pick="",
        gates=None,
        probe=True,
        tap="",
        walk=None,
        script="",
        hops=False,
        at_port=None,
    ):
        self.upstream, self.dark, self.states = upstream, False, 0
        self.dark_after = None
        self.asked, self.stacks = [], 0
        self.alter = lambda nth, body: body
        self.alter_state = lambda nth, body: body
        self.refused = ()
        self.writes, self.counted = [], []
        self.on_write = lambda nth: None
        asked = f"window.__task = {json.dumps(task)}; window.__pick = {json.dumps(pick)};"
        asked += f"window.__gates = {json.dumps(gates)}; window.__tap = {json.dumps(tap)};"
        asked += f"window.__walk = {json.dumps(walk)}; window.__hops = {json.dumps(hops)};"
        self.head = f"<script>window.__at = {at}; {asked}{script or PROBE}</script>"
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
                    body = body.replace(b"<head>", b"<head>" + proxy.head.encode(), 1)
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
                """A write of the page. The proxy writes it down as the browser sent it. Then
                it passes the write on with the server's own address as its `Host` and
                `Origin`, the way the server's own page would send it."""
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                made = {
                    "path": self.path,
                    "origin": self.headers.get("Origin"),
                    "kind": self.headers.get("Content-Type"),
                    "body": json.loads(body),
                }
                if self.path == "/usage":
                    proxy.counted.append(made)
                else:
                    proxy.writes.append(made)
                if proxy.dark and self.path == "/usage":
                    self.send_error(502)
                    return
                if self.path != "/usage" and proxy.on_write(len(proxy.writes)) == "dark":
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

        self.port = at_port or free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def browser_lock():
    """The browser lock under the run's home. It reads the home when a test takes the lock,
    so a test can give itself a home of its own."""
    return Path(os.environ["HOME"]) / ".local" / "state" / "locks" / "browser.lock"


@contextmanager
def heavy():
    """The machine's browser lock, held while a browser runs.

    The lock is the file `browser_lock()` names. Only these tests take it, so only one of
    their browsers runs at a time. The run's caller may have the heavy-suite lock: that is
    another file, and nothing here waits on it. This waits `PATIENCE` seconds for the browser
    lock and then fails the test with one line, because a check that waits without end reads
    as one that hangs.
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


def browse(*arguments, dump=True):
    """Run the browser headless under the browser lock, and give back what it printed. With
    `dump` it prints the page as it is at the end of its time; without, the arguments say what
    it makes, such as `--screenshot`.

    Chromium binds a socket in a directory it makes under `TMPDIR`, and the path of a socket
    has at most 107 characters. So the browser gets a short directory of its own, whatever
    `TMPDIR` the run has, because a runner's is long.

    `timeout` gives the browser `LAUNCH` seconds and then stops it, and the test fails with
    a line that says so. The browser runs in a process group of its own, and the whole group
    ends when the browser ends, also when something outside stops the test. Python's own
    timeout, or pytest-timeout's, would stop one process and leave the ones it started.
    """
    command = [
        CHROMIUM,
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        *(["--dump-dom"] if dump else []),
    ]
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
    hops=False,
    at_port=None,
):
    """Open the page in the browser and give back what the probe found.

    The page comes from the server that listens on `port`, or else from a new server
    that this function starts over the scene. The
    page is the scene's project, `#/demo`, or the `route` given, such as `#/` for every
    project. `fragment` is more of the address after it, such as `theme=dark`. `alter` gets
    the count of each answer of `/stack.json` and its body, and gives back the body the page
    gets. `alter_state` does the same for `/state.json`. `tap` selects what the probe taps
    3 s after the page loads. `walk` is the steps the probe takes from 2.5 s on, one each
    0.5 s, such as `back` or `open:task:oat-bowl`. `system` is the scheme the browser asks
    for, `light` or `dark`. With `hops`, the probe taps each thing on the first screen once,
    each from the page as it opened, and what it found has what each tap opened under
    `hops`. The proxy listens on `at_port` where it is given, so two looks at one port are one
    origin to the browser, and the page keeps what it stored. With `gates`, the probe answers
    the gates, and what it found has each write the page made under `writes`, and each count it
    posted under `counted`. The proxy calls `on_write` with the count of each write before it
    passes the write on. A write for which `on_write` answers `dark` reaches no server."""
    served = None if port else Served(scene)
    proxy = Proxy(
        port or served.port,
        at,
        task,
        pick,
        gates,
        tap=tap,
        walk=walk,
        script=script,
        hops=hops,
        at_port=at_port,
    )
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
    return said | {
        "writes": proxy.writes,
        "counted": proxy.counted,
        "at": proxy.port,
        "asked": proxy.asked,
    }


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


def a_day_of_threads(scene):
    """Every role at work: a crewmate that hung, a crewmate that ended an hour ago, a
    reviewer, three scouts, and the home. One scout is researching, one reported and ended,
    and one ended with no Report. The page folds two more threads: a crewmate that ended
    before the day began, and a thread with no role."""
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


def child_homes(scene):
    """Two child homes of the scene's project beside its root, after `a_day_of_threads`. `ui`
    was made on 2026-10-09. The crewmate that hung works on its brief `jam-jar`, its own thread
    ended while a row of it is open, and jbus logged a stall of that row. `docs` was made the day
    after and has nothing open and nothing wrong. It gives back the slug of the row that
    stalled."""
    for name, made in (("ui", "2026-10-09"), ("docs", "2026-10-10")):
        (scene.home / name).mkdir()
        (scene.home / name / "home-id").write_text(f"mcp:{name}\n")
        goal = f"Goal ({made}, the user): the {name} of {scene.name}\n"
        (scene.home / name / "plan.md").write_text(f"# {scene.name}, {name}: plan\n\n{goal}")
    rows = json.loads((scene.state / "queue.json").read_text())
    stalled = next(one["slug"] for one in rows if one["status"] == "running")
    (scene.home / "tasks").mkdir(exist_ok=True)
    for slug in ("jam-jar", stalled):
        (scene.home / "tasks" / f"{slug}.md").write_text(f"# {slug}\nHome: ui\nTask: x\n")
    record = json.loads((scene.state_dir / "pass.json").read_text())
    listed = record["projects"][scene.name]["threads"]
    listed.append(out(f"home: {scene.name} ui", "ended", "completed", minutes=50, id="mcp:ui"))
    scene.write("pass.json", record, scene.state_dir)
    stall = {
        "at": iso(ago(minutes=2)),
        "event": "stall",
        "id": "00000000000000ff",
        "line": f"stall {stalled}: it has been on its step for 2 hours",
        "loud": "user",
        "slug": stalled,
        "text": "the text of the event, which no answer holds",
    }
    with (scene.state / "events.jsonl").open("a") as log:
        log.write(json.dumps(stall) + "\n")
    return stalled


MAP = (Path(__file__).parent / "map.js").read_text()


def mapped(scene, tmp_path, build, screen=DESK, **how):
    """What the probe of the homes map, `MAP`, found on `#/homes` of the scene that `build` makes,
    and `/stack.json` as the server gives it."""
    build(scene)
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        seen = look(
            scene, tmp_path, route="#/homes", script=MAP, screen=screen, port=served.port, **how
        )
    finally:
        served.close()
    return seen, stack


BOARDS = REPO / "features" / "jbus" / "tests" / "fixtures" / "jbus-view"


def board(rows):
    """The board JSON of the fixture `pipeline-<rows>.json`, as `/panel/pipeline.json` holds it."""
    return json.loads((BOARDS / f"pipeline-{rows}.json").read_text())


def boarded(patch, rows):
    """Make the server answer `/panel/pipeline.json` with `board(rows)`, and give it back.
    Call it before the server starts."""
    made = board(rows)
    real_get = view.App.get

    def get(app, path, query):
        return said(200, made) if path == "/panel/pipeline.json" else real_get(app, path, query)

    patch.setattr(view.App, "get", get)
    return made


def chips(seen_band):
    return [(rl, [(c["text"], c["open"], c["ended"]) for c in cs]) for rl, cs in seen_band["rows"]]


def walked(scene, tmp_path, route, walk):
    """What the page showed after each step of `walk`, with the page first opened at
    `route`."""
    seen = look(scene, tmp_path, route=route, walk=walk, at=4000 + 500 * len(walk), budget=12000)
    assert seen["errors"] == []
    return seen["walked"]


def gated(scene):
    """Three questions of one crewmate, each with its options, the first with a context and
    one more option. It returns the numbers of the three questions."""
    (scene.home / "tasks").mkdir(exist_ok=True)
    (scene.home / "tasks" / "alpha.md").write_text("# alpha\nThread: mcp:crew-alpha\n")
    lines = PIPED.format(n="<n>", asked="tea or coffee?", status="open", slug="alpha")
    lines += "Context: the pot holds two cups\nOption: both: a second pot\n"
    first = questions.ask(scene.state, scene.home, "alpha", lines, ago(minutes=25))[0].number
    return [first, asks(scene, "milk?"), asks(scene, "sugar?")]


def shown(port, tmp_path, opens):
    """What the page says when its address opens the drawer that `opens` names. The text is
    what the browser shows once the page stops changing, in a drawer or a wide one. It gives back
    nothing where no drawer is open."""
    ran = browse(
        f"--user-data-dir={tmp_path / 'profile'}",
        "--virtual-time-budget=3000",
        f"http://127.0.0.1:{port}/#/demo/{opens.replace(':', '/')}",
    )
    open_ = re.search(
        r'<dialog class="drawer(?: wide)?" id="drawer" aria-labelledby="dw-title" open="">',
        ran.stdout,
    )
    if not open_:
        return ""
    said = ran.stdout[open_.end() :].partition("</dialog>")[0]
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", said))).strip()


HOLDERS = ["user", "crew", "home", "rev", "ci", "bus", "dep", "ok", "scout", "other", "unknown"]


MARKS = ["long", "rep", "blk", "bn", "lv-moving", "lv-quiet", "lv-hung"]
