"""A home's status reply opens with the board's two headlines and ends with the board itself: its
link in jbus view and a picture of it, for the home's scope. The tests run the status step's block
as a home reads it, in one call with the block at the top and the block that finds this home, in a
made-up home directory whose repo is a project of a made-up jbus config, with the real `jbus` the
skill names. A stand-in view serves the board's JSON, and a stand-in `uv` answers `jbus view-shot`
as that verb does and hands every other call to the real `uv`."""

import http.server
import json
import os
import shutil
import socket
import subprocess
import threading

import pytest

from skill_blocks import git
from test_home_merge import uv_cache
from test_home_thread import block, finds_this_home, paths
from testing.layouts import assembled

LINK = "jbus link"
ROOT = "t-root"
SCOPED = "t-jview"

BOARD = {
    "at": "2026-10-26T08:06:00-04:00",
    "stages": [
        {"key": "crew", "name": "Crew", "count": 4, "still": 1, "oldest": None},
        {"key": "check", "name": "Checks", "count": 12, "still": 8, "oldest": None},
    ],
    "rows": [],
    "unplaced": [],
    "stuck": {"stage": "check", "still": 8, "count": 12},
    "longest_wait": {
        "slug": "mac-tree-spec-timeout",
        "project": "demo",
        "stage": "crew",
        "since": "2026-10-26T06:10:00-04:00",
        "cause": "waits on a test slot",
    },
    "longest": None,
}
HEADLINES = (
    "first: Most stuck: Checks, 8 of 12. Waiting longest: mac-tree-spec-timeout, Crew since"
    " 2026-10-26T06:10:00-04:00, waits on a test slot."
)

SHOT = """#!/bin/sh
case " $* " in
*" jbus view-shot "*)
    printf '%s\\n' "$*" >> "$SHOTS"
    if [ -n "$NO_VIEW" ]; then
        echo "no shot: jbus view is not running"
        exit 1
    fi
    while [ "$1" != --out ]; do shift; done
    printf '\\211PNG\\r\\n' > "$XDG_RUNTIME_DIR/$2"
    echo "$XDG_RUNTIME_DIR/$2"
    ;;
*) exec "$REAL_UV" "$@" ;;
esac
"""


class View(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/panel/board.json":
            self.send_error(404)
            return
        body = json.dumps(BOARD).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@pytest.fixture
def view():
    """The origin of a stand-in view that answers `/panel/board.json`."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), View)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def no_view():
    """The origin of a port nothing listens on."""
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    return f"http://127.0.0.1:{port}"


class Machine:
    """A home directory with the skills, `~/repos/demo` and its homes (the root one, and a scoped
    one, `jview`), jbus's config, which names `demo` when `kept` and only another repo when not,
    and a stand-in `uv` on the PATH."""

    def __init__(self, tmp_path, kept=True):
        self.home = tmp_path / "home"
        self.repo = self.home / "repos" / "demo"
        self.config = tmp_path / "config"
        self.runtime = tmp_path / "runtime"
        self.bin = tmp_path / "bin"
        self.shots = tmp_path / "shots"
        state = self.home / ".local" / "state" / "home" / "demo"
        for made in (self.repo, self.config, self.home / ".claude", state / "jview"):
            made.mkdir(parents=True)
        for made in (self.runtime, self.bin):
            made.mkdir()
        (state / "home-id").write_text(f"{ROOT}\n")
        (state / "jview" / "home-id").write_text(f"{SCOPED}\n")
        (state / "jview" / "plan.md").write_text("# plan\n")
        (self.home / ".claude" / "skills").symlink_to(assembled() / "skills")
        (self.bin / "uv").write_text(SHOT)
        (self.bin / "uv").chmod(0o755)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "one")
        name = "demo" if kept else "other"
        toml = self.config / "config.toml"
        toml.write_text(
            f'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "{name}"\n'
            f'checkout = "{self.home / "repos" / name}"\nprojectId = "p-{name}"\n'
            '\n[[project]]\nname = "third"\ncheckout = "/somewhere/third"\nprojectId = "p-3"\n'
        )
        toml.chmod(0o600)

    def status(self, origin, thread=ROOT, **more):
        env = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "JBUS_CONFIG_DIR": str(self.config),
            "JBUS_VIEW_ORIGINS": origin,
            "UV_CACHE_DIR": uv_cache(),
            "UV_OFFLINE": "1",
            "REAL_UV": shutil.which("uv"),
            "SHOTS": str(self.shots),
            "XDG_RUNTIME_DIR": str(self.runtime),
            **more,
        }
        script = f"{paths('home')}\n{finds_this_home(thread)}\n{block('home', LINK)}"
        done = subprocess.run(
            ["sh", "-c", script], cwd=self.repo, env=env, capture_output=True, text=True
        )
        assert (done.returncode, done.stderr) == (0, "")
        return done.stdout.splitlines()

    def asked(self):
        """What each `jbus view-shot` call was given, from its verb on."""
        said = self.shots.read_text().splitlines() if self.shots.exists() else []
        return [line.partition(" jbus ")[2] for line in said]


@pytest.mark.parametrize(
    ("thread", "route", "png"),
    [
        (ROOT, "#/", "jview-flow-demo-root.png"),
        (SCOPED, "#/?home=jview", "jview-flow-demo-jview.png"),
    ],
)
def test_a_status_reply_names_the_boards_headlines_and_ends_with_its_picture_and_link(
    tmp_path, view, thread, route, png
):
    machine = Machine(tmp_path)
    shot = machine.runtime / png
    assert machine.status(view, thread) == [HEADLINES, f"attach: {shot} 6", f"{view}/{route}"]
    assert shot.read_bytes().startswith(b"\x89PNG")
    assert machine.asked() == [f"view-shot {route} --out {png}"]


def test_with_no_view_running_the_reply_carries_the_link_alone(tmp_path, no_view):
    machine = Machine(tmp_path)
    assert machine.status(no_view, SCOPED, NO_VIEW="1") == [f"{no_view}/#/?home=jview"]
    assert len(machine.asked()) == 1


def test_a_repo_jbus_keeps_no_project_for_gets_no_link(tmp_path, view):
    machine = Machine(tmp_path, kept=False)
    assert machine.status(view) == ["no jview link: jbus has no page for demo"]
    assert machine.asked() == []
