"""`jbus view` is one server over what the passes left. It prints no secret, and its one write
is the user's answer to a question.

Each test starts the real server on a free port over a temporary state directory, and asks
it over HTTP as a browser would. `gh` and `systemctl` are stand-ins on `PATH` that write
down how they were called. A test of an answer that is sent runs the server over a kitchen
of `test_jbus_kitchen`, whose T3 Code is a stand-in too. Nothing reaches the network, and every name
here is made up.
"""

import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import jbus
import jsettings
from jbus import cli, leftover, merge, noticed, questions, queue, record, view, word, work
from jbus.view import panels
from jbus.view import state as built
from jbus.view.panels.checks import panel as checks_panel
from jbus.view.panels.room import panel as room_panel
from jbus.view.state import waves
from jmerge import ready
from test_jbus_kitchen import GATE as PIPED
from test_jbus_kitchen import NOW as POLLED
from test_jbus_kitchen import Kitchen, complete

REPO = Path(__file__).parent.parent
NOW = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)
GITHUB = "github.com"
PULL = f"https://{GITHUB}/acme/demo/pull/{{}}"
RUN = f"https://{GITHUB}/acme/demo/actions/runs/{{}}"
SHAPED = (
    "ghp_" + "Q7" * 18,
    "github_pat_" + "Zx9" * 10,
    "xoxb-2211-3344-" + "kLm" * 6,
    "sk-" + "pLanTed" * 5,
    "eyJ" + "hbGci" * 4 + ".eyJ" + "zdWIi" * 4 + ".sIgNaTuRe77",
    "AKIA" + "QWERTYUIOPASDFGH",
)
LINKS = (
    "https://example.test/hooks/T0/B0/plantedpath",
    f"https://{GITHUB}/other/place/pull/7",
    "http://example.test:8443/wake?k=plantedquery",
)
OPAQUE = "plantedopaquewordsnobodyshouldsee"
ASKED = "gate:#4:" + hashlib.sha256(b"tea or coffee?").hexdigest()[:8]
UNREAD = ("outboxonlywords", "configonlywords", "tokenfileonlywords")
PLANTED = (*SHAPED, *LINKS, OPAQUE, *UNREAD, "plantedpath", "plantedquery")
TIMER = """Id=jbus.timer
ActiveState={active}
SubState={sub}
UnitFileState=enabled
LastTriggerUSec=Mon 2026-10-12 15:59:40 EDT

Id=jbus.service
ActiveState={service}
SubState=dead
Result={result}
ExecMainStatus={code}
"""
GATE = """## Gate {n}: {asked}
Status: {status}
Asked by: home, thread none
Default: {default}
Built on it: plan.md {n}
Undo: n/a
"""


def iso(moment):
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def et(moment):
    """A time as a pass stamps it, in the zone and with the word every test runs with."""
    return jsettings.load().stamp(moment)


def ago(**how):
    return NOW - timedelta(**how)


def row(slug, status="queued", **more):
    return {
        "slug": slug,
        "priority": 1,
        "depends": [],
        "approved": "2026-10-12 09:00 ET by user",
        "brief_sha": "ab" * 32,
        "status": status,
        "thread": "",
        "pr": "",
        "checks": "",
        "updated": et(ago(minutes=5)),
        "why": "",
        "since": "",
    } | more


WORK = ("value", "who", "facts", "confirmed")


def value_of(one):
    """The value a pass that wrote this row would have judged it, where a test names none."""
    status, why = one.get("status", "queued"), one.get("why", "")
    if status == "queued":
        if not one.get("approved") or why.startswith("brief changed"):
            return "unapproved"
        return "behind" if one.get("depends") else "ready"
    if status == "pr":
        return merge.step(why) or "unknown"
    if status == "left":
        return "closed" if "is not open and not merged" in why else "leftover"
    if status == "merged":
        return "leftover" if why else "merged"
    said = {"launched": "launching", "running": "working", "gate": "asking", "done": "done"}
    return said.get(
        status, {"failed": "lost", "stale": "lost", "waiting": "waiting"}.get(status, "unknown")
    )


def judge_row(one, state=None):
    """A line of `work.json` for a row, as `work.entry` writes one, with its holder from
    `work.holder` and what `leftover.json` says of it."""
    value = one.get("value") or value_of(one)
    pattern = work.BY_VALUE[value]
    facts = {"pull": "merged" if one.get("status") == "merged" else "none"} | one.get("facts", {})
    made = work.Facts(
        work.Row.FREE,
        work.Thread(facts.get("thread", "none")),
        work.Launch(facts.get("launch", "none")),
        work.Written.NONE,
        work.Pull(facts["pull"]),
        work.Question.NONE,
        work.Answered.BOTH,
    )
    judged = work.State(value, pattern.who, pattern.waits, True, made)
    held = leftover.read(state).get(one["slug"]) if state is not None else None
    home = bool(held and not held.busy and not leftover.his(held, NOW))
    line = work.entry(
        judged,
        work.holder(judged, home=home and "who" not in one),
        key=one["slug"],
        kind="row",
        slug=one["slug"],
        thread=one.get("thread", ""),
        pr=one.get("pr", ""),
    )
    return (
        line
        | {"confirmed": one.get("confirmed", True), "facts": facts}
        | ({"who": one["who"]} if "who" in one else {})
    )


def table():
    """A queue with every way a row waits: the three ways a queued row does, and the
    pull requests that `jmerge` waits on or holds."""
    dropped = (
        "wait: the rebase dropped 2 of main's lines in src/a.py with no Dropped on rebase line"
    )
    moved = "wait: the rebase changed the content after its review; scoped review of a..b c..d"
    old = et(ago(minutes=50))
    return [
        row("tea-kettle", approved="", why="not approved", since=old),
        row("tea-cups", depends=["tea-kettle"], why="depends on tea-kettle", since=old),
        row("tea-tray", why="no slot", since=et(ago(minutes=2))),
        row("jam-jar", "running", thread="mcp:0000"),
        row("jam-lid", "gate", why="a gate the Chef has", since=old),
        row("oat-bowl", "pr", pr="#11", checks="passed", why=dropped, since=old),
        row("oat-spoon", "pr", pr="#12", checks="passed", why=moved, since=old),
        row("oat-milk", "pr", pr="#13", checks="pending", why="wait: check has not passed"),
        row("oat-honey", "pr", pr="#14", why="hold: needs user, touches skills/crew/SKILL.md"),
        row("rye-loaf", "merged", pr="#9"),
    ]


def logged(minutes, word, number, reason):
    stamp = et(ago(minutes=minutes)).removesuffix(" ET")
    return f"{stamp} {word} {number} {PULL.format(number)}: {reason}"


class Scene:
    """A machine as the passes left it: the state directory, the home's, and the stand-ins."""

    def __init__(self, root, monkeypatch, name="demo"):
        self.root, self.name, self.now = root, name, NOW
        self.state_dir, self.home_dir = root / "state", root / "home"
        self.state, self.home = self.state_dir / name, self.home_dir / name
        self.bin, self.proc = root / "bin", root / "proc"
        for made in (self.state, self.home, self.bin, self.proc / "pressure", root / "tmp"):
            made.mkdir(parents=True)
        self.calls = root / "gh.calls"
        self.calls.write_text("")
        self.script(
            "gh",
            f'printf "%s\\n" "$*" >> {self.calls}\n'
            'case "$2" in\n'
            f"*actions/runs*) cat {root}/runs.json ;;\n"
            f"*check-runs*) cat {root}/check-runs.json ;;\n"
            f"*pulls/*) cat {root}/pull.json ;;\n"
            "*) exit 1 ;;\nesac\n",
        )
        self.script(
            "systemctl",
            'case "$2" in\n'
            f'list-units) printf "%s\\n" "$*" >> {root}/systemctl.calls\n'
            f"  cat {root}/runners.json ;;\n"
            f"*) cat {root}/systemctl.txt ;;\nesac\n",
        )
        self.script("nproc", "echo 8\n")
        self.script(
            "df",
            'printf "Filesystem Inodes IUsed IFree IUse%% Mounted\\nt 1000 100 900 10%% /\\n"\n',
        )
        monkeypatch.setenv("PATH", f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("JBUS_CONFIG_DIR", str(root / "config"))
        monkeypatch.delenv("JBUS_VIEW_HOST", raising=False)
        monkeypatch.delenv("JBUS_VIEW_NAMES", raising=False)
        self.timer()
        self.runners()
        self.machine()
        self.queue(table())
        self.passed(seconds_ago=20)
        self.write("main.json", {"at": iso(ago(minutes=30)), "main": "c0ffee" * 6 + "abcd"})
        self.write("checks.json", {"aa" * 20: "green", "bb" * 20: "green", "cc" * 20: "red"})
        self.write("stall.json", {})
        self.write("wake.json", {"began": True, "last_error": "", "posted": NOW.timestamp() - 90})
        self.write("sent.json", ["result|jam-jar|tasks 1", "merged|rye-loaf|9", "gate|jam-lid|g"])
        self.write("outbox.json", [{"line": UNREAD[0]}])
        self.waiting(
            [
                item("gate", ASKED, "gate 4: tea or coffee?", hours=3, number="4"),
                item("row", "row:jam-lid", "gate jam-lid: which lid?", minutes=50, slug="jam-lid"),
                item("approve", "approve:tea-kettle", "approve tea-kettle: jbus queue approve"),
                item("hold", "#14", "hold 14: needs user", minutes=12, number=14),
            ]
        )
        self.moves(("rye-loaf", "pr", "merged", 40), ("jam-jar", "launched", "running", 35))
        self.events(
            ("merged", "user", "rye-loaf", "merged 9 rye-loaf", 40),
            ("result", "chef", "jam-jar", "result jam-jar: Status: done", 30),
            ("queue", "quiet", "", "queue demo: the table changed", 1),
        )
        self.merge_log(
            logged(55, "wait", 11, "check has not passed"),
            logged(50, "wait", 11, "the rebase dropped 2 of main's lines in src/a.py"),
            logged(45, "wait", 13, "check has not passed"),
            logged(44, "wait", 13, "it has no review yet"),
            logged(4, "wait", 13, "check has not passed"),
            logged(41, "merged", 9, "rye-loaf"),
        )
        (self.home / "gates.md").write_text(
            GATE.format(n=4, asked="tea or coffee?", status="open", default="tea")
            + "\n"
            + GATE.format(n=5, asked="one lump or two?", status="answered: two", default="one")
        )
        self.github()

    def script(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def write(self, name, value, where=None):
        (where or self.state).joinpath(name).write_text(json.dumps(value))

    def lines(self, name, records):
        self.state.joinpath(name).write_text("".join(json.dumps(one) + "\n" for one in records))

    def queue(self, rows, judged=True):
        """The table, and `work.json` beside it as the pass that wrote the table judged it:
        a row's `value`, `who` and `facts`, where a test gives them, or what `judged` gives."""
        made = [{k: v for k, v in one.items() if k not in WORK} for one in rows]
        path, table = self.state / "work.json", self.state / "queue.json"
        was = {one["slug"]: one for one in json.loads(table.read_text())} if table.exists() else {}
        self.write("queue.json", made)
        if judged:
            kept = json.loads(path.read_text())["work"] if path.exists() else []
            before = {one["key"]: one for one in kept}
            lines = [
                before[one["slug"]]
                if one["slug"] in before and was.get(one["slug"]) == one
                else judge_row(one, self.state)
                for one in rows
            ]
            self.write("work.json", {"at": iso(NOW), "answered": "both", "work": lines})

    def waiting(self, items):
        self.write("waiting-on-user.json", items)

    def moves(self, *moves):
        self.lines(
            "transitions.jsonl",
            [
                {"slug": slug, "from": was, "to": to, "at": iso(ago(minutes=minutes))}
                for slug, was, to, minutes in moves
            ],
        )

    def events(self, *events):
        self.lines(
            "events.jsonl",
            [
                {
                    "at": iso(ago(minutes=minutes)),
                    "event": kind,
                    "id": f"{at:016x}",
                    "line": line,
                    "loud": loud,
                    "slug": slug,
                    "text": "the text of the event, which no answer holds",
                }
                for at, (kind, loud, slug, line, minutes) in enumerate(events)
            ],
        )

    def merge_log(self, *lines):
        (self.home / "merge.log").write_text("".join(line + "\n" for line in lines))
        last = {line.split()[3]: line.split(" ", 2)[2] for line in lines}
        self.write("merge.log.last", last, self.home)

    def passed(self, seconds_ago, running=False, threads=(), rows=None):
        """The last pass ended this long ago: `pass.json`, and the status file beside it.
        It saw these threads out, and this of each row."""
        ended = ago(seconds=seconds_ago)
        record = {
            "started": iso(ended - timedelta(seconds=21)).replace("+00:00", "Z"),
            "ended": None if running else iso(ended).replace("+00:00", "Z"),
            "seconds": None if running else 21.0,
            "projects": {
                self.name: {"seen": iso(ended), "rows": rows or {}}
                | ({} if threads is None else {"threads": list(threads)})
            },
        }
        self.write("pass.json", record, self.state_dir)
        status = {
            "last_pass": et(ended),
            "token_expires": "2026-11-10 17:08 ET",
            "streaks": {},
            "projects": {
                self.name: {
                    "failed_wakes": 0,
                    "last_error": "",
                    "outbox": 2,
                    "sign_in": "",
                    "sweep": "2026-10-12: 3 to remove",
                }
            },
        }
        self.write("status.json", status, self.state_dir)

    def timer(self, active="active", sub="waiting", result="success", code=0, service="inactive"):
        said = TIMER.format(active=active, sub=sub, result=result, code=code, service=service)
        (self.root / "systemctl.txt").write_text(said)

    def runners(self, *units):
        """What `systemctl list-units` lists of the runners: each unit as its name, its active
        state and its sub state. Three that run, as this machine has, where none is given."""
        units = units or tuple((f"actions-runner-{n}.service", "active", "running") for n in "abc")
        listed = [
            {
                "unit": unit,
                "load": "loaded",
                "active": active,
                "sub": sub,
                "description": "a runner",
            }
            for unit, active, sub in units
        ]
        self.write("runners.json", listed, self.root)

    def machine(self, load="2.50 2.00 1.50 3/900 1234", five_hour=23.0):
        (self.proc / "loadavg").write_text(load + "\n")
        (self.proc / "meminfo").write_text("MemTotal: 32000000 kB\nMemAvailable: 16000000 kB\n")
        (self.proc / "pressure" / "memory").write_text(
            "some avg10=0.00 avg60=0.50 avg300=0.00 total=1\n"
        )
        resets = int(time.time()) + 3600
        (self.root / "limits").write_text(
            f"five_hour {five_hour} {resets}\nseven_day 22.0 {resets}\n"
        )

    def github(self, runs=None, **pull):
        """What the stand-in `gh` answers: the runs, as `(branch, status, conclusion)` from
        the oldest, with the workflow's name after them where it is not `check`, and the one
        pull request."""
        runs = [
            {
                "id": 500 + at,
                "head_branch": branch,
                "status": status,
                "conclusion": conclusion,
                "created_at": iso(ago(minutes=30 - at)),
                "run_started_at": iso(ago(minutes=29 - at)),
                "updated_at": iso(ago(minutes=27 - at)),
                "html_url": RUN.format(500 + at),
                "name": name[0] if name else "check",
            }
            for at, (branch, status, conclusion, *name) in enumerate(
                runs
                or [
                    ("oat-bowl", "completed", "success"),
                    ("oat-milk", "completed", "failure"),
                    ("oat-milk", "in_progress", None),
                ]
            )
        ]
        self.write("runs.json", {"total_count": 3, "workflow_runs": runs}, self.root)
        self.write(
            "pull.json",
            {
                "number": 13,
                "state": "open",
                "merged": False,
                "mergeable": True,
                "mergeable_state": "blocked",
                "updated_at": iso(ago(minutes=3)),
                "html_url": PULL.format(13),
                "head": {"sha": "d00d" * 10, "ref": "oat-milk"},
                "title": "a title",
                "body": "a body, which no answer holds",
            }
            | pull,
            self.root,
        )
        check = {
            "name": "check",
            "status": "in_progress",
            "conclusion": None,
            "started_at": iso(ago(minutes=2)),
            "completed_at": None,
            "html_url": RUN.format(502) + "/job/9",
        }
        self.write("check-runs.json", {"total_count": 1, "check_runs": [check]}, self.root)

    def asked(self):
        """Each call of the stand-in `gh`, as its arguments."""
        return self.calls.read_text().splitlines()

    def app(self):
        return view.App(
            view.Sources(
                state_dir=self.state_dir,
                home_dir=self.home_dir,
                proc=self.proc,
                limits=self.root / "limits",
                tmp=self.root / "tmp",
                user=jsettings.load(),
            ),
            clock=lambda: self.now,
        )


def item(kind, key, line, slug="", number=None, **since):
    found = {"kind": kind, "key": key, "line": line, "since": iso(ago(**since) if since else NOW)}
    return found | ({"slug": slug} if slug else {}) | ({"number": number} if number else {})


def free_port(host="127.0.0.1"):
    with socket.socket() as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


class Served:
    """The server, open on a free port, and what it answers."""

    def __init__(self, scene, host=None, names=(), retry=60.0, port=None):
        self.port = port or free_port()
        self.doors = view.Doors(scene.app(), self.port, host=host, names=names, retry=retry)
        self.doors.open()

    def ask(self, path, method="GET", host=None, to="127.0.0.1", headers=None, body=None):
        link = http.client.HTTPConnection(to, self.port, timeout=10)
        try:
            named = f"127.0.0.1:{self.port}" if host is None else host
            link.request(method, path, body=body, headers={"Host": named, **(headers or {})})
            answer = link.getresponse()
            return answer.status, dict(answer.getheaders()), answer.read().decode()
        finally:
            link.close()

    def write(self, body, origin=None, path=None, **how):
        """A write as the server's own page makes it, to the one project of the state
        directory, or from the origin given: `""` is a request with no `Origin` header. The
        answer is its status and what it said."""
        if path is None:
            path = "/answer?project=" + built.projects(self.doors.app.sources)[0]
        origin = f"http://127.0.0.1:{self.port}" if origin is None else origin
        headers = {"Content-Type": "application/json"} | ({"Origin": origin} if origin else {})
        sent = body if isinstance(body, str) else json.dumps(body)
        status, _, said = self.ask(path, "POST", headers=headers, body=sent, **how)
        return status, json.loads(said)

    def json(self, path):
        status, _, body = self.ask(path)
        assert status == 200, body
        return json.loads(body)

    def close(self):
        self.doors.close()


@pytest.fixture
def scene(tmp_path, monkeypatch):
    return Scene(tmp_path, monkeypatch)


@pytest.fixture
def served(scene):
    made = Served(scene)
    yield made
    made.close()


def tasks(state):
    return {one["slug"]: one for one in state["tasks"]}


def test_the_server_starts_on_a_free_port_over_a_temporary_state_directory(served):
    assert served.json("/healthz") == {"ok": True}
    assert served.doors.addresses() == [("127.0.0.1", served.port)]


def test_each_route_answers_and_anything_else_is_404(served):
    status, headers, page = served.ask("/")
    assert (status, headers["Content-Type"]) == (200, "text/html; charset=utf-8")
    assert "<title>jbus: the line</title>" in page
    state = served.json("/state.json?project=demo")
    assert (state["project"], state["projects"], state["repo"]) == ("demo", ["demo"], "acme/demo")
    digest = served.json("/digest.json?since=2026-10-12T00:00")
    assert digest["since"] == "2026-10-12T04:00:00+00:00"
    assert [one["slug"] for one in digest["projects"]["demo"]["merged"]] == ["rye-loaf"]
    assert served.json("/task/oat-milk/github?project=demo")["pull"]["number"] == 13
    assert served.json("/healthz") == {"ok": True}
    for path in ("/nothing", "/state.json/more", "/task/oat-milk", "/task/oat-milk/github/x"):
        assert served.ask(path)[0] == 404, path


def test_the_digest_at_the_address_is_what_jbus_digest_prints(served, scene, capsys, monkeypatch):
    (scene.root / "config").mkdir()
    config = scene.root / "config" / "config.toml"
    config.write_text(
        'server = "http://localhost:1"\n[[project]]\nname = "demo"\n'
        f'checkout = "{scene.root}"\nprojectId = "p"\n'
    )
    config.chmod(0o600)
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    assert cli.main(["digest", "--json", "--since", "2026-10-12T00:00"]) == 0
    printed = json.loads(capsys.readouterr().out)
    answered = served.json("/digest.json?since=2026-10-12T00:00")
    assert printed.pop("at") and answered.pop("at")
    assert printed["projects"]["demo"]["waiting"] and printed["status"]["pass"]["projects"]
    assert answered == printed


def test_jbus_digest_takes_the_expiry_from_the_token_file_where_there_is_one(
    scene, capsys, monkeypatch
):
    (scene.root / "config").mkdir()
    config = scene.root / "config" / "config.toml"
    config.write_text(
        'server = "http://localhost:1"\n[[project]]\nname = "demo"\n'
        f'checkout = "{scene.root}"\nprojectId = "p"\n'
    )
    token = scene.root / "config" / "t3.json"
    stored = {"token": {"access_token": "a", "expires_in": 3600}, "obtained_at": NOW.timestamp()}
    token.write_text(json.dumps(stored))
    config.chmod(0o600)
    token.chmod(0o600)
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    assert cli.main(["digest", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["token_expires"] == et(NOW + timedelta(hours=1))
    assert printed["status"]["token_expires"] == "2026-11-10 17:08 ET"
    token.unlink()
    assert cli.main(["digest", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["token_expires"] == "2026-11-10 17:08 ET"


def test_a_since_that_is_not_a_time_is_refused(served):
    status, _, body = served.ask("/digest.json?since=yesterday")
    assert (status, json.loads(body)) == (400, {"error": "since is not a time"})


def stacked(scene):
    """Beside `demo`, two projects of the state directory, made up small: `pantry`, with
    one task running, one at a gate and one merged today, a gate it asks and a noticed line,
    in a repo of its own, and `larder`, whose queue is empty. Beside them a directory with
    no queue, which is no project, and a retired project, which jbus no longer looks after
    and the view never reads."""
    pantry, larder = scene.state_dir / "pantry", scene.state_dir / "larder"
    for made in (pantry, larder, scene.home_dir / "pantry", scene.home_dir / "larder"):
        made.mkdir()
    (scene.state_dir / "launches").mkdir()
    retired = scene.root / "jbus-retired" / "hydra"
    retired.mkdir(parents=True)
    (retired / "queue.json").write_text(json.dumps([row("old-pot", "running")]))
    rows = [
        row("fig-jam", "running", thread="mcp:fig"),
        row("fig-tart", "gate", why="a gate the Chef has", since=et(ago(minutes=40))),
        row("fig-roll", "merged", pr="#3"),
    ]
    (pantry / "queue.json").write_text(json.dumps(rows))
    lines = [judge_row(one, pantry) for one in rows]
    (pantry / "work.json").write_text(json.dumps({"at": iso(NOW), "work": lines}))
    gate = item("row", "row:fig-tart", "gate fig-tart: which tin?", minutes=40, slug="fig-tart")
    (pantry / "waiting-on-user.json").write_text(json.dumps([gate]))
    moved = {"slug": "fig-roll", "from": "pr", "to": "merged", "at": iso(ago(minutes=9))}
    (pantry / "transitions.jsonl").write_text(json.dumps(moved) + "\n")
    stamp = et(ago(minutes=8)).removesuffix(" ET")
    (scene.home_dir / "pantry" / "merge.log").write_text(
        f"{stamp} wait 4 https://{GITHUB}/acme/pantry/pull/4: check has not passed\n"
    )
    (larder / "queue.json").write_text("[]")
    return retired


def test_the_stack_is_the_machine_once_and_a_summary_of_each_project(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    a_noticed(scene, ("tea-kettle", "new", 5, {}), ("jam-jar", "dropped", 9, {}))
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    assert stack["at"] == iso(NOW)
    assert [one["key"] for one in stack["steps"]] == [
        *(one["key"] for one in demo["steps"]),
        "unknown",
    ]
    assert list(stack["machine"]) == ["jbus", "room", "runners", "runners_read", "unwell"]
    assert stack["machine"]["unwell"] == []
    assert stack["machine"]["jbus"]["stopped"] is False
    assert stack["machine"]["jbus"]["status"] == {
        "last_pass": demo["jbus"]["status"]["last_pass"],
        "token_expires": demo["jbus"]["status"]["token_expires"],
        "streaks": {},
        "homes_off_bus": [],
    }
    same = {key: one for key, one in demo["room"].items() if key != "tmp"}
    assert {key: one for key, one in stack["machine"]["room"].items() if key != "tmp"} == same
    assert stack["machine"]["runners"] == demo["checks"]["runners"]
    assert [one["name"] for one in stack["projects"]] == ["demo", "larder", "pantry"]
    by = {one["name"]: one for one in stack["projects"]}
    assert by["larder"]["health"]["blind"] == 1
    assert by["larder"] == {
        "name": "larder",
        "repo": "",
        "waits": 0,
        "waiting": {},
        "noticed": 0,
        "open": 0,
        "steps": {},
        "merged": 0,
        "threads": None,
        "health": {
            "checks": {"running": 0, "waiting": 0, "failed": 0, "error": "the repo is not known"},
            "bus": {"outbox": 0, "failed_wakes": 0, "last_error": ""},
            "threads": None,
            "blind": 1,
            "unwell": [
                {"name": name, "state": "missing"}
                for name in (
                    "work.json",
                    "waiting-on-user.json",
                    "transitions.jsonl",
                    "events.jsonl",
                    "main.json",
                    "checks.json",
                    "stall.json",
                    "wake.json",
                    "sent.json",
                    "merge.log",
                )
            ]
            + [{"name": "GitHub", "state": "unreadable"}],
        },
    }
    pantry = by["pantry"]
    assert (pantry["repo"], pantry["waits"], pantry["noticed"]) == ("acme/pantry", 1, 0)
    assert pantry["waiting"] == {"row": {"count": 1, "since": iso(ago(minutes=40))}}
    assert (pantry["open"], pantry["steps"], pantry["merged"]) == (2, {"running": 1, "gate": 1}, 1)
    assert pantry["health"]["checks"] == {"running": 1, "waiting": 0, "failed": 0, "error": ""}
    shown = by["demo"]
    assert (shown["repo"], shown["waits"], shown["noticed"]) == ("acme/demo", 4, 1)
    assert {kind: one["count"] for kind, one in shown["waiting"].items()} == dict.fromkeys(
        ("gate", "row", "approve", "hold"), 1
    )
    assert shown["waits"] == len(demo["waiting"])
    steps = [one["step"] for one in demo["tasks"]]
    assert shown["steps"] == {key: steps.count(key) for key in built.STEP if key in steps}
    assert shown["steps"] == {
        "queued": 3,
        "running": 1,
        "gate": 1,
        "second": 1,
        "check": 1,
        "rebase": 1,
        "hold": 1,
    }
    assert (shown["open"], shown["merged"]) == (9, len(demo["merged"]))
    assert shown["health"]["bus"] == {"outbox": 2, "failed_wakes": 0, "last_error": ""}
    assert shown["health"]["threads"] == 0
    assert "hydra" not in json.dumps(stack)


def test_the_homes_off_the_bus_are_the_machines_and_on_no_projects_row(tmp_path, monkeypatch):
    """The homes the last pass found with no project are on the machine, as names, and a name
    that is no string is left out."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status["homes_off_bus"] = ["firstmate", "LittleRamPantries", {"name": "not a name"}]
    scene.write("status.json", status, scene.state_dir)
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    off = ["firstmate", "LittleRamPantries"]
    assert stack["machine"]["jbus"]["status"]["homes_off_bus"] == off
    assert demo["jbus"]["status"]["homes_off_bus"] == off
    assert all("homes_off_bus" not in json.dumps(one) for one in stack["projects"])


def test_a_fault_of_the_machine_is_said_once_on_the_machine_and_on_no_projects_row(
    tmp_path, monkeypatch
):
    """The room check does not run and `status.json` cannot be read: the machine says both,
    each project's page still lists them, and no row of the overview counts them."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    room = scene.bin / "room.sh"
    room.write_text("LOAD=85\nMEMORY=6\nPRESSURE=10\nSLOTS=85\nCUSHION=85\nexit 3\n")
    monkeypatch.setattr(room_panel, "ROOM", room)
    (scene.state_dir / "status.json").write_text("{not json")
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    assert stack["machine"]["room"]["answer"] == "unknown"
    assert stack["machine"]["unwell"] == [{"name": "status.json", "state": "unreadable"}]
    assert "the room check did not run" in [one["line"] for one in demo["blind"]]
    assert {"name": "status.json", "by": "jbus"} | {"state": "unreadable"} in [
        {key: one[key] for key in ("name", "by", "state")} for one in demo["sources"]
    ]
    by = {one["name"]: one["health"] for one in stack["projects"]}
    assert (by["demo"]["blind"], by["demo"]["unwell"]) == (1, [])
    assert by["larder"]["blind"] == 1
    assert all(
        "status.json" not in [one["name"] for one in health["unwell"]] for health in by.values()
    )


def test_the_stack_runs_the_machines_checks_once_however_many_projects(tmp_path, monkeypatch):
    """systemd, the room script and the runner units are asked once for an answer of
    `/stack.json`, with three projects as with one, and the runs of GitHub once for each
    repo, then kept: a second answer within the minute asks GitHub nothing."""
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    calls = scene.root / "machine.calls"
    scene.script(
        "systemctl",
        f'printf "systemctl %s\\n" "$2" >> {calls}\n'
        'case "$2" in\n'
        f"list-units) cat {scene.root}/runners.json ;;\n"
        f"*) cat {scene.root}/systemctl.txt ;;\nesac\n",
    )
    room = scene.bin / "room.sh"
    limits = "LOAD=85\nMEMORY=6\nPRESSURE=10\nSLOTS=85\nCUSHION=85\n"
    room.write_text(f'{limits}echo room >> {calls}\necho "go: there is room"\n')
    monkeypatch.setattr(room_panel, "ROOM", room)
    served = Served(scene)
    try:
        served.json("/stack.json")
        assert sorted(calls.read_text().splitlines()) == [
            "room",
            "systemctl list-units",
            "systemctl show",
        ]
        runs = [one for one in scene.asked() if "actions/runs" in one]
        assert sorted(runs) == [
            "api repos/acme/demo/actions/runs?per_page=40",
            "api repos/acme/pantry/actions/runs?per_page=40",
        ]
        calls.write_text("")
        served.json("/stack.json")
        assert len(calls.read_text().splitlines()) == 3
        assert len([one for one in scene.asked() if "actions/runs" in one]) == 2
    finally:
        served.close()


def test_the_checks_are_told_apart_once_by_the_server_for_the_card_and_the_overview():
    def run(branch, state, name="check"):
        return {"branch": branch, "state": state, "name": name}

    runs = [
        run("a", "failure"),
        run("a", "success"),
        run("b", "failure"),
        run("b", "timed_out", "lint"),
        run("c", "in_progress"),
        run("d", "queued"),
        run("d", "requested", "lint"),
    ]
    assert checks_panel.tally(runs) == {"running": [4], "waiting": [5, 6], "failed": [2]}


def test_a_retired_project_is_never_read_and_a_link_to_it_finds_nothing(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    retired = stacked(scene)
    (retired / "queue.json").chmod(0)
    served = Served(scene)
    try:
        assert "hydra" not in served.ask("/stack.json")[2]
        assert served.ask("/state.json?project=hydra")[0] == 404
        assert served.ask("/state.json?project=../jbus-retired/hydra")[0] == 404
    finally:
        served.close()
        (retired / "queue.json").chmod(0o644)


def test_an_answer_names_its_project_and_goes_to_that_projects_state_alone(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    number = asks(scene)
    pantry = scene.state_dir / "pantry"
    served = Served(scene)
    try:
        for path in ("/answer", "/answer?project=", "/answer?project=hydra"):
            assert served.write({"numbers": [number]}, path=path)[0] == 404
        assert kept(scene.state)[number].answer is None
        assert served.write({"numbers": [number]}, path="/answer?project=pantry")[0] == 409
        assert not questions.path(pantry).exists()
        status, said = served.write({"numbers": [number]}, path="/answer?project=demo")
        assert (status, [one["number"] for one in said["closed"]]) == (200, [number])
        assert kept(scene.state)[number].answer is not None
    finally:
        served.close()


def test_another_method_is_405(served):
    for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "BREW"):
        status, headers, _ = served.ask("/state.json?project=demo", method=method)
        assert (method, status, headers.get("Allow")) == (method, 405, "GET")


def asks(scene, asked="tea or coffee?", slug="alpha"):
    """A question piped to jbus, with two options. The answer is its number."""
    lines = PIPED.format(n="<n>", asked=asked, status="open", slug=slug)
    return questions.ask(scene.state, scene.home, slug, lines, NOW)[0].number


def kept(state):
    """Each record of the questions file, by its number."""
    return {one.number: one for one in questions.read(state)}


def test_the_one_write_is_post_answer_and_every_other_method_of_it_is_405(scene, served):
    number = asks(scene)
    for method in ("PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
        status, headers, _ = served.ask("/answer", method=method)
        assert (method, status, headers.get("Allow")) == (method, 405, "POST")
    assert served.ask("/answer")[0] == 404
    assert served.write({"numbers": [number]}, path="/state.json?project=demo")[0] == 405
    assert kept(scene.state)[number].answer is None
    status, said = served.write({"numbers": [number]})
    assert (status, [one["number"] for one in said["closed"]]) == (200, [number])


@pytest.mark.parametrize("origin", ["http://example.test", "http://127.0.0.1:1", "null", ""])
def test_a_write_from_another_origin_or_from_none_is_403_and_changes_nothing(scene, served, origin):
    number = asks(scene)
    before = questions.path(scene.state).read_bytes()
    status, said = served.write({"numbers": [number]}, origin=origin)
    assert (status, said) == (403, {"error": "only the server's own page writes"})
    assert questions.path(scene.state).read_bytes() == before


def test_a_write_is_held_to_the_host_check_and_takes_the_origin_of_each_name(scene):
    number = asks(scene)
    served = Served(scene, names=("kitchen.example.test",))
    try:
        evil = f"evil.example.test:{served.port}"
        status, said = served.write({"numbers": [number]}, origin=f"http://{evil}", host=evil)
        assert (status, said) == (403, {"error": "this is not the server's name"})
        assert kept(scene.state)[number].answer is None
        name = f"kitchen.example.test:{served.port}"
        status, _ = served.write({"numbers": [number]}, origin=f"http://{name}", host=name)
        assert status == 200
    finally:
        served.close()


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        {},
        {"numbers": []},
        {"numbers": "1"},
        {"numbers": [True]},
        {"numbers": ["1"]},
        {"numbers": [1, 1]},
        {"numbers": [1], "option": 3},
        {"numbers": [1], "words": ["tea"]},
    ],
)
def test_a_write_that_is_not_the_shape_is_400_and_changes_nothing(scene, served, body):
    number = asks(scene)
    if isinstance(body, dict) and body.get("numbers"):
        body = body | {
            "numbers": [number if n == 1 and n is not True else n for n in body["numbers"]]
        }
    assert served.write(body)[0] == 400
    assert kept(scene.state)[number].answer is None


def test_a_batch_with_an_option_or_words_is_refused_whole(scene, served):
    first, second = asks(scene), asks(scene, "milk?")
    for more in ({"option": "the other"}, {"words": "oat milk"}):
        status, said = served.write({"numbers": [first, second], **more})
        assert (status, said) == (
            400,
            {"error": "a batch only takes defaults: answer that one by itself"},
        )
    assert [one.answer for one in kept(scene.state).values()] == [None, None]


def test_a_second_write_to_a_question_is_refused_with_the_first_answer(scene, served):
    number = asks(scene)
    assert served.write({"numbers": [number]})[0] == 200
    status, said = served.write({"numbers": [number], "words": "coffee after all"})
    first = f'"the first one", by user, {et(NOW)}, in jbus view (the default stands)'
    assert (status, said["closed"]) == (409, [])
    (refused,) = said["refused"]
    assert refused["say"] == (
        f"Question {number} was answered already, and nothing changed: {first}."
    )
    assert (refused["first"]["words"], refused["first"]["keeps"]) == ("the first one", True)
    assert refused["first"]["line"] == first
    assert kept(scene.state)[number].answer.words == "the first one"


def test_three_are_closed_in_one_request_and_one_answered_already_is_said_by_number(scene, served):
    numbers = [asks(scene, asked) for asked in ("tea?", "milk?", "sugar?")]
    served.write({"numbers": [numbers[1]], "words": "oat milk"})
    status, said = served.write({"numbers": numbers})
    assert status == 200
    assert [(one["number"], one["keeps"], one["sent"]) for one in said["closed"]] == [
        (numbers[0], True, False),
        (numbers[2], True, False),
    ]
    assert said["closed"][0]["say"] == (
        f"Question {numbers[0]} closed at {jsettings.load().clock(NOW)} with its default, "
        "and nothing was sent."
    )
    (refused,) = said["refused"]
    assert (refused["number"], refused["first"]["words"]) == (numbers[1], "oat milk")
    assert refused["say"].startswith(f"Question {numbers[1]} was answered already")
    records = kept(scene.state)
    assert [records[n].answer.keeps for n in numbers] == [True, False, True]


def test_a_question_with_no_options_on_record_takes_the_default_and_his_words(scene, served):
    numbers = [asks(scene, asked) for asked in ("tea?", "milk?")]
    file = questions.path(scene.state)
    old = json.loads(file.read_text())
    for one in old["records"]:
        del one["options"], one["context"]
    file.write_text(json.dumps(old))
    (shown, _) = [
        one for one in served.json("/state.json?project=demo")["waiting"] if one["answerable"]
    ]
    assert (shown["options"], shown["default"]) == ([], "the first one")
    status, said = served.write({"numbers": [numbers[0]]})
    assert (status, said["closed"][0]["keeps"]) == (200, True)
    status, said = served.write({"numbers": [numbers[1]], "words": " oat  milk "})
    assert (status, said["closed"][0]["keeps"]) == (200, False)
    status, said = served.write({"numbers": [numbers[0]], "option": "the other"})
    assert status == 409
    records = kept(scene.state)
    assert [records[n].answer.words for n in numbers] == ["the first one", "oat milk"]


def test_an_option_the_question_does_not_have_closes_nothing(scene, served):
    number = asks(scene)
    status, said = served.write({"numbers": [number], "option": "a third"})
    assert (status, said["closed"]) == (409, [])
    assert said["refused"] == [
        {
            "number": number,
            "say": f"Question {number} has no option of that name, and nothing changed.",
            "first": None,
        }
    ]
    assert kept(scene.state)[number].answer is None


def test_a_gate_that_lives_only_in_a_homes_file_is_listed_and_cannot_be_answered(scene, served):
    (gate,) = [
        one for one in served.json("/state.json?project=demo")["waiting"] if one["kind"] == "gate"
    ]
    assert (gate["number"], gate["question"], gate["answerable"]) == ("4", "tea or coffee?", False)
    assert (gate["options"], gate["thread"], gate["role"]) == ([], "", "")
    before = (scene.home / "gates.md").read_bytes()
    status, said = served.write({"numbers": [4]})
    assert (status, said["closed"]) == (409, [])
    assert said["refused"][0]["say"] == "Question 4 did not close: no question 4, open: none."
    assert (scene.home / "gates.md").read_bytes() == before


def test_the_state_gives_each_open_question_what_its_gate_wrote_and_who_asked(scene, served):
    (scene.home / "tasks").mkdir()
    (scene.home / "scouts").mkdir()
    (scene.home / "tasks" / "alpha.md").write_text("# alpha\nThread: mcp:crew-alpha\n")
    (scene.home / "scouts" / "survey.md").write_text("# survey\nThread: mcp:scout-1\n")
    scene.passed(seconds_ago=20, threads=[{"id": "mcp:scout-1", "role": "home"}])
    lines = PIPED.format(n="<n>", asked="tea or coffee?", status="open", slug="alpha")
    lines += "Context: the pot holds two cups\nOption: both (recommended): a second pot\n"
    number = questions.ask(scene.state, scene.home, "alpha", lines, ago(minutes=25))[0].number
    asks(scene, "milk?", slug="survey")
    asks(scene, "sugar?", slug="expert-sage")
    shown = {one["question"]: one for one in served.json("/state.json?project=demo")["waiting"]}
    one = shown["tea or coffee?"]
    assert (one["number"], one["answerable"], one["since"]) == (
        str(number),
        True,
        iso(ago(minutes=25)),
    )
    assert (one["context"], one["default"]) == ("the pot holds two cups", "the first one")
    assert (one["built_on"], one["undo"]) == ("nothing", "pick the other")
    assert (one["role"], one["slug"], one["thread"]) == ("crew", "alpha", "mcp:crew-alpha")
    assert one["options"] == [
        {
            "name": "the first one",
            "follows": "nothing changes",
            "default": True,
            "recommended": False,
        },
        {"name": "the other", "follows": "one more cup", "default": False, "recommended": False},
        {"name": "both", "follows": "a second pot", "default": False, "recommended": True},
    ]
    assert (shown["milk?"]["role"], shown["milk?"]["thread"]) == ("home", "mcp:scout-1")
    assert (shown["sugar?"]["role"], shown["sugar?"]["thread"]) == ("", "")
    assert shown["milk?"]["context"] == ""


def said_by_him(scene, answer="coffee, please", sent="go ahead with the kettle"):
    """Two questions, one of them answered; a word sent on and one that waits; and a row
    approved on the word sent, beside the table's rows, which hold only a typed string."""
    user = jsettings.load()
    asks(scene, "milk?")
    number = asks(scene, "which pot?")
    questions.answer(
        scene.state,
        number,
        answer,
        by=user.user,
        at=et(ago(minutes=30)),
        where="Sous Chef",
        keeps=False,
        user=user,
    )
    went = word.Word(
        "a1b2c3d4e5f6",
        sent,
        user.user,
        et(ago(minutes=20)),
        iso(ago(minutes=19)),
        thread="mcp:home",
        sent_at=iso(ago(minutes=18)),
        ref="mcp:sous/m1",
        said_in="Sous Chef",
        checked=True,
    )
    waits = word.Word(
        "f6e5d4c3b2a1",
        "hold the lids",
        user.user,
        et(ago(minutes=5)),
        iso(ago(minutes=5)),
        waits="the home has no home-id",
    )
    scene.write(word.NAME, [asdict(went), asdict(waits)])
    by = {"session": "s-1", "directory": "/made/up/elsewhere"}
    made = queue.Approval(
        "word", went.id, went.words, went.at, "Sous Chef", True, by, iso(ago(minutes=10))
    )
    rows = table()
    rows[1] |= {"approved": made.line(), "approval": queue.held(made)}
    scene.queue(rows)
    return number


def test_the_words_panel_lists_his_answers_his_words_and_each_approval_newest_first(scene, served):
    number = said_by_him(scene)
    state = served.json("/state.json?project=demo")
    said = state["words"]
    typed = sorted(one["slug"] for one in table() if one["approved"] and one["slug"] != "tea-cups")
    assert [one["key"] for one in said] == [
        "word:f6e5d4c3b2a1",
        "approval:tea-cups",
        "word:a1b2c3d4e5f6",
        f"question:{number}",
        *(f"approval:{slug}" for slug in typed),
    ]
    entry = {one["key"]: one for one in said}
    answered = entry[f"question:{number}"]
    assert {key: answered[key] for key in ("question", "default", "words", "by", "at")} == {
        "question": "which pot?",
        "default": "the first one",
        "words": "coffee, please",
        "by": jsettings.load().user,
        "at": iso(ago(minutes=30)),
    }
    assert (answered["keeps"], answered["where"], answered["slug"]) == (False, "Sous Chef", "alpha")
    went, waits = entry["word:a1b2c3d4e5f6"], entry["word:f6e5d4c3b2a1"]
    assert (went["kept_at"], went["sent_at"]) == (iso(ago(minutes=19)), iso(ago(minutes=18)))
    assert (waits["sent_at"], waits["waits"]) == (None, "the home has no home-id")
    approved = entry["approval:tea-cups"]
    assert {key: approved[key] for key in ("basis", "rests", "words", "who", "ran_at")} == {
        "basis": "word",
        "rests": "word:a1b2c3d4e5f6",
        "words": "go ahead with the kettle",
        "who": "the elsewhere home",
        "ran_at": iso(ago(minutes=10)),
    }
    assert approved["said_at"] == iso(ago(minutes=20))
    before = entry["approval:tea-tray"]
    assert (before["line"], before["words"], before["at"]) == (
        "no record: approved before the record was kept",
        "2026-10-12 09:00 ET by user",
        None,
    )
    assert "approval:tea-kettle" not in entry
    assert [one for one in said if one.get("question") == "milk?"] == []
    assert served.json("/panel/words.json?project=demo")["data"] == {"words": said}
    names = {one["name"]: one["state"] for one in state["sources"]}
    assert (names["questions.json"], names["words.json"]) == ("ok", "ok")


def test_a_question_its_home_closed_in_gates_md_is_said_to_be_closed_by_its_home(scene, served):
    said_by_him(scene)
    number = asks(scene, "which lid?", slug="jam-lid")
    with open(scene.home / "gates.md", "a") as gates:
        gates.write(
            "\n"
            + PIPED.format(n=number, asked="which lid?", status="answered: red", slug="jam-lid")
        )
    questions.closed_in_files(types.SimpleNamespace(home=scene.home, state=scene.state))
    entry = {one["key"]: one for one in served.json("/state.json?project=demo")["words"]}
    closed = entry[f"question:{number}"]
    assert (closed["home"], closed["words"], closed["where"]) == (True, "answered: red", "")
    assert (closed["by"], closed["at"]) == ("", None)
    assert [one["home"] for one in entry.values() if one["kind"] == "answer"] == [False, True]


def test_an_answered_question_is_on_no_waiting_list_and_the_open_one_still_is(scene, served):
    number = said_by_him(scene)
    waiting = served.json("/state.json?project=demo")["waiting"]
    asked = [one["question"] for one in waiting if one["kind"] == "gate"]
    assert "milk?" in asked
    assert "which pot?" not in [one["question"] for one in waiting]
    assert str(number) not in [one["number"] for one in waiting]


def test_a_words_file_that_does_not_parse_is_said_and_the_rest_is_listed(scene, served):
    number = said_by_him(scene)
    (scene.state / word.NAME).write_text("{not json")
    state = served.json("/state.json?project=demo")
    assert {one["name"]: one["state"] for one in state["sources"]}["words.json"] == "unreadable"
    assert f"question:{number}" in [one["key"] for one in state["words"]]
    assert [one for one in state["words"] if one["kind"] == "word"] == []


def test_a_token_planted_in_his_answer_his_word_and_an_approval_is_in_no_answer(scene, served):
    planted = "ghp_" + "Wq4" * 12
    said_by_him(scene, answer=f"yes, and {planted}", sent=f"go with {planted}")
    paths = [
        "/",
        "/state.json?project=demo",
        "/digest.json",
        "/task/tea-cups/github?project=demo",
        *view.routes(),
    ]
    held = {}
    for path in paths:
        _, headers, body = served.ask(path)
        held[path] = planted in body + json.dumps(headers)
    assert held == dict.fromkeys(paths, False)
    said = json.dumps(served.json("/panel/words.json?project=demo"))
    assert said.count("[redacted]") == 3


class Counter:
    """A kitchen of `test_jbus_kitchen`, with the view over its state: jbus's config and its sign-in
    are the kitchen's, and T3 Code is the kitchen's stand-in."""

    THREAD = "mcp:crew-alpha"

    def __init__(self, tmp_path, monkeypatch):
        self.kitchen = Kitchen(tmp_path, monkeypatch)
        self.kitchen.brief("alpha", f"Thread: {self.THREAD}\n")
        self.kitchen.quiet()
        self.state = self.kitchen.state
        if not (self.state / "queue.json").exists():
            (self.state / "queue.json").write_text("[]")
        self.t3 = self.kitchen.t3

    def app(self):
        sources = view.Sources(
            state_dir=self.kitchen.state_dir,
            home_dir=self.kitchen.root / "home",
            user=jsettings.load(),
        )
        return view.App(sources, clock=lambda: POLLED)

    def asks(self, asked="tea or coffee?"):
        lines = PIPED.format(n="<n>", asked=asked, status="open", slug="alpha")
        code, said = self.kitchen.main("gate", "alpha", stdin=lines)
        assert code == 0, said
        return int(said.split()[-1])

    def sends(self):
        """Each message the stand-in for T3 Code was asked to send, taken or not."""
        return [given for tool, given in self.t3.calls if tool == "t3_thread_send"]

    def passes(self, many=2):
        for at in range(many):
            self.kitchen.poll(POLLED + timedelta(minutes=10 * (at + 1)))


@pytest.fixture
def counter(tmp_path, monkeypatch):
    made = Counter(tmp_path, monkeypatch)
    served = Served(made)
    yield made, served
    served.close()
    made.kitchen.close()


def test_the_default_taken_closes_the_question_through_jbus_and_sends_nothing(counter):
    counter, served = counter
    number = counter.asks()
    status, said = served.write({"numbers": [number]})
    assert status == 200 and said["refused"] == []
    assert said["closed"] == [
        {
            "number": number,
            "slug": "alpha",
            "keeps": True,
            "words": "the first one",
            "sent": False,
            "why": "",
            "thread": "",
            "role": "crew",
            "say": f"Question {number} closed at 11:00 ET with its default, and nothing was sent.",
        }
    ]
    given = kept(counter.state)[number].answer
    assert (given.keeps, given.by, given.at, given.where) == (
        True,
        "user",
        et(POLLED),
        "jbus view",
    )
    assert (given.words, given.told, given.closed_by) == ("the first one", "", "jbus answer")
    counter.passes()
    assert counter.sends() == []


@pytest.mark.parametrize(
    "more, words",
    [
        ({"option": "the other"}, "the other"),
        ({"option": "the other", "words": " and  a biscuit "}, "the other. and a biscuit"),
        ({"words": "neither, water"}, "neither, water"),
        ({"option": "the first one", "words": "but only half a cup"}, "but only half a cup"),
    ],
)
def test_another_option_or_his_words_go_once_to_the_thread_that_asked_in_the_same_request(
    counter, more, words
):
    counter, served = counter
    number = counter.asks()
    status, said = served.write({"numbers": [number], **more})
    (closed,) = said["closed"]
    assert (status, closed["keeps"], closed["sent"], closed["words"]) == (200, False, True, words)
    assert (closed["thread"], closed["why"]) == (counter.THREAD, "")
    assert closed["say"] == (
        f"Question {number} closed at 11:00 ET, and its answer went to the crew thread of alpha."
    )
    (sent,) = counter.sends()
    assert (sent["threadId"], sent["mode"], sent["clientRequestId"]) == (
        counter.THREAD,
        "queue",
        f"answer|alpha|{number}",
    )
    assert sent["message"] == (
        f"jbus: user answered question {number} (tea or coffee?), and the answer is not the "
        f'default you took (the first one). The words, {et(POLLED)}: "{words}". Undo: pick the '
        "other. Built on the default: nothing. Take the default back, do what the answer says, "
        "and add one line to the last Result or Report saying what you changed. Then end your "
        "turn."
    )
    given = kept(counter.state)[number].answer
    assert (given.keeps, given.words, bool(given.told)) == (False, words, True)
    counter.passes()
    assert len(counter.sends()) == 1
    assert counter.kitchen.lines("note") == [
        f"note alpha: told its thread the answer to question {number}"
    ]


@pytest.mark.parametrize(
    "fails, why",
    [
        ("refuse_send", "T3 Code refused it (t3_thread_send: no)"),
        (
            "lose_send",
            "T3 Code did not answer (T3 Code at /mcp could not be reached: Remote end closed "
            "connection without response)",
        ),
    ],
)
def test_an_answer_t3_code_does_not_take_is_recorded_and_the_next_pass_sends_it(
    counter, fails, why
):
    counter, served = counter
    number = counter.asks()
    setattr(counter.t3, fails, True)
    status, said = served.write({"numbers": [number], "option": "the other"})
    (closed,) = said["closed"]
    assert (status, closed["keeps"], closed["sent"], closed["thread"]) == (200, False, False, "")
    assert closed["why"] == why
    assert closed["say"] == (
        f"Question {number} closed at 11:00 ET with its answer recorded and not yet sent, "
        f"since {why}: the next pass sends it."
    )
    given = kept(counter.state)[number].answer
    assert (given.words, given.keeps, given.told) == ("the other", False, "")
    assert counter.t3.messages == {}
    setattr(counter.t3, fails, False)
    before = len(counter.sends())
    counter.passes(1)
    assert len(counter.sends()) == before + 1
    assert list(counter.t3.messages) == [f"answer|alpha|{number}"]
    counter.passes(1)
    assert len(counter.sends()) == before + 1
    assert kept(counter.state)[number].answer.told


def test_an_answer_with_no_sign_in_is_recorded_and_says_why(counter):
    counter, door = counter
    number = counter.asks()
    token = counter.kitchen.config_dir / "t3.json"
    token.unlink()
    status, said = door.write({"numbers": [number], "words": "coffee"})
    assert (status, said["closed"][0]["sent"]) == (200, False)
    assert said["closed"][0]["why"] == f"no token in {token}: run `jbus t3 login`"
    assert kept(counter.state)[number].answer.words == "coffee"
    assert counter.sends() == []


def test_an_answer_no_pass_will_send_does_not_say_that_the_next_pass_sends_it(counter):
    counter, served = counter
    first, second = counter.asks(), counter.asks("milk?")
    brief = counter.kitchen.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text().replace(f"Thread: {counter.THREAD}\n", ""))
    _, said = served.write({"numbers": [first], "words": "coffee"})
    assert said["closed"][0]["say"] == (
        f"Question {first} closed at 11:00 ET with its answer recorded and not yet sent, since "
        "alpha has no Thread: line in a brief or request: a pass sends it once one names its "
        "thread."
    )
    removed = {"alpha": {"at": et(POLLED), "by": "user"}}
    queue.removed_path(counter.state).write_text(json.dumps(removed))
    assert queue.removed_slugs(counter.state) == {"alpha"}
    _, said = served.write({"numbers": [second], "words": "oat milk"})
    assert said["closed"][0]["say"] == (
        f"Question {second} closed at 11:00 ET with its answer recorded, and it goes to no "
        "thread, since alpha was removed from the queue."
    )
    assert counter.sends() == []


def test_a_view_over_no_config_of_jbus_still_closes_the_question(scene, served):
    number = asks(scene)
    status, said = served.write({"numbers": [number], "words": "coffee"})
    (closed,) = said["closed"]
    assert (status, closed["sent"], closed["keeps"]) == (200, False, False)
    assert closed["why"] == f"no config at {scene.root / 'config' / 'config.toml'}"
    assert kept(scene.state)[number].answer.words == "coffee"


def test_a_host_header_that_is_not_the_servers_is_refused(scene):
    served = Served(scene, names=("kitchen.example.test",))
    try:
        assert served.ask("/healthz", host=f"localhost:{served.port}")[0] == 200
        assert served.ask("/healthz", host=f"kitchen.example.test:{served.port}")[0] == 200
        for host in ("evil.example.test", f"evil.example.test:{served.port}", "127.0.0.1:1", ""):
            assert served.ask("/state.json?project=demo", host=host)[0] == 403, host
    finally:
        served.close()


def test_no_answer_has_a_cors_header_and_none_may_be_stored(served):
    for path in (
        "/",
        "/state.json?project=demo",
        "/digest.json",
        "/task/oat-milk/github?project=demo",
        "/healthz",
        "/no",
    ):
        _, headers, _ = served.ask(path)
        assert headers["Cache-Control"] == "no-store", path
        assert [name for name in headers if name.lower().startswith("access-control")] == []
    _, headers, _ = served.ask("/state.json?project=demo", method="POST")
    assert headers["Cache-Control"] == "no-store"


def test_it_never_listens_on_every_address(scene):
    for everywhere in ("0.0.0.0", "::", "", "*"):
        with pytest.raises(view.Refused):
            view.Doors(scene.app(), free_port(), host=everywhere).open()


def test_it_listens_on_the_address_in_jbus_view_host_too(scene):
    served = Served(scene, host="127.0.0.2")
    try:
        assert served.doors.addresses() == [("127.0.0.1", served.port), ("127.0.0.2", served.port)]
        status, _, _ = served.ask("/healthz", host=f"127.0.0.2:{served.port}", to="127.0.0.2")
        assert status == 200
    finally:
        served.close()


def test_with_that_address_down_it_serves_loopback_and_tries_again(scene):
    port = free_port("127.0.0.2")
    taken = socket.socket()
    taken.bind(("127.0.0.2", port))
    taken.listen()
    served = Served(scene, host="127.0.0.2", retry=0.05, port=port)
    try:
        assert served.doors.addresses() == [("127.0.0.1", port)]
        assert served.json("/healthz") == {"ok": True}
        taken.close()
        until = time.monotonic() + 10
        while len(served.doors.addresses()) < 2 and time.monotonic() < until:
            time.sleep(0.02)
        assert served.doors.addresses() == [("127.0.0.1", port), ("127.0.0.2", port)]
        assert served.ask("/healthz", host=f"127.0.0.2:{port}", to="127.0.0.2")[0] == 200
    finally:
        taken.close()
        served.close()


def test_an_address_that_is_not_this_machines_leaves_loopback_serving(scene):
    served = Served(scene, host="192.0.2.1")
    try:
        assert served.doors.addresses() == [("127.0.0.1", served.port)]
        assert served.json("/healthz") == {"ok": True}
    finally:
        served.close()


def test_jbus_view_reads_its_address_and_names_from_the_environment(scene, monkeypatch):
    monkeypatch.setenv("JBUS_VIEW_HOST", "127.0.0.2")
    monkeypatch.setenv("JBUS_VIEW_NAMES", "kitchen.example.test, pantry.example.test")
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    port = free_port()
    doors = view.doors(port)
    try:
        assert doors.host == "127.0.0.2"
        assert doors.names == ("kitchen.example.test", "pantry.example.test")
        assert doors.app.sources.state_dir == scene.state_dir
        assert view.PORT == 4388
    finally:
        doors.close()


def test_the_verb_is_jbus_view_and_it_needs_no_config(scene, monkeypatch):
    opened = []

    class Stub:
        def __init__(self, port):
            opened.append(port)

        def serve(self):
            return 0

    monkeypatch.setattr(view, "doors", Stub)
    assert cli.main(["view", "--port", "4999"]) == 0
    assert cli.main(["view"]) == 0
    assert opened == [4999, 4388]
    assert not (scene.root / "config").exists()


def test_a_queued_row_is_yours_blocked_or_waiting_for_jbus(served):
    found = tasks(served.json("/state.json?project=demo"))
    assert {slug: (found[slug]["step"], found[slug]["who"]) for slug in found if "tea" in slug} == {
        "tea-kettle": ("queued", "user"),
        "tea-cups": ("queued", "dep"),
        "tea-tray": ("queued", "bus"),
    }
    assert found["tea-cups"]["depends"] == [{"slug": "tea-kettle", "state": "queued"}]
    assert found["tea-kettle"]["state"]["say"] == "nobody has approved it"


def test_the_two_rebase_reasons_are_the_rebase_step_and_the_second_pass(served):
    found = tasks(served.json("/state.json?project=demo"))
    assert (found["oat-bowl"]["step"], found["oat-bowl"]["who"]) == ("rebase", "crew")
    assert (found["oat-spoon"]["step"], found["oat-spoon"]["who"]) == ("second", "rev")
    assert found["oat-bowl"]["state"]["say"].startswith("the rebase dropped 2 of main's lines")
    assert found["oat-spoon"]["state"]["say"].startswith("the rebase changed the content after its")


@pytest.mark.parametrize(
    ("why", "step"),
    [
        ("wait: no brief has a Result that names it", "result"),
        ("wait: it has no review yet", "review"),
        ("wait: its findings are not handled: the Result has no Fixed line", "findings"),
        (
            "wait: its fix changed more than the findings named: the second pass is not written",
            "second",
        ),
        (
            "wait: guarded (touches src/a.py), the rebase changed the patch after its review",
            "second",
        ),
        ("wait: a check has not finished", "check"),
        (
            "wait: main changed a.py after its check started at 20:48 ET; it needs a fresh check",
            "check",
        ),
        ("wait: guarded (touches src/a.py), no proven safety fact at 0123456789ab (x)", "proof"),
        (
            "wait: guarded (touches a), main changed b after its check started; it needs a rebase",
            "rebase",
        ),
        ("wait: it conflicts with its base", "rebase"),
        ("hold: needs user, the rebase dropped 1 of main's lines in src/a.py", "hold"),
        ("wait: its brief says Review: none, so it needs the user's word", "hold"),
        ("wait: a reason nobody has printed before", "unknown"),
        ("", "unknown"),
    ],
)
def test_a_reason_of_jmerge_puts_a_pull_request_on_its_step(scene, served, why, step):
    scene.queue([row("oat-bowl", "pr", pr="#11", checks="passed", why=why)])
    assert tasks(served.json("/state.json?project=demo"))["oat-bowl"]["step"] == step


def test_the_line_has_twelve_steps_and_every_open_row_is_on_one(served):
    state = served.json("/state.json?project=demo")
    assert [one["key"] for one in state["steps"]] == [
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
    found = tasks(state)
    assert sorted(found) == sorted(one["slug"] for one in table() if one["status"] != "merged")
    assert {one["step"] for one in found.values()} <= {one["key"] for one in state["steps"]}
    assert (found["jam-jar"]["step"], found["jam-lid"]["step"]) == ("running", "gate")
    assert (found["oat-milk"]["step"], found["oat-honey"]["step"]) == ("check", "hold")
    assert [(one["slug"], one["pr"]) for one in state["merged"]] == [("rye-loaf", "#9")]


def test_a_task_says_since_when_it_is_on_its_step_and_how_often_it_came_back(served):
    found = tasks(served.json("/state.json?project=demo"))
    assert found["oat-milk"]["since"] == iso(ago(minutes=4))
    assert found["oat-milk"]["visits"] == 2
    assert [one["step"] for one in found["oat-milk"]["history"]] == ["check", "review", "check"]
    assert (found["oat-bowl"]["since"], found["oat-bowl"]["visits"]) == (iso(ago(minutes=50)), 1)
    assert found["jam-jar"]["since"] == iso(ago(minutes=35))
    assert found["tea-kettle"]["since"] == iso(ago(minutes=50))


NAMES = {value: work.BY_VALUE[value].name for value in work.VALUES}
JMERGE = {
    "result": "no brief has a Result that names it",
    "review": "it has no review yet",
    "findings": "its findings are not handled: the Result has no Fixed line",
    "second": "the rebase changed the content after its review; scoped review of a..b c..d",
    "check": "a check has not finished",
    "proof": "guarded (touches src/a.py), no proven safety fact at 0123456789ab (step 5)",
    "rebase": "it conflicts with its base",
    "hold": "needs user, touches skills/crew/SKILL.md",
}


def kinds(scene):
    """One row of most values, as the last pass judged it: a row of every status a row has,
    and a pull request on every step. `fig-pip` is a row that is wrong, queued while the pass
    judged it merged, and `fig-stem` waits behind it. `fig-pod` and `fig-tree` are finished
    and leave nothing. The page's first screen holds the scene to its word budget, so
    `quiet`, `closed` and `unknown` have scenes of their own."""
    pulls = [
        row(
            f"fig-{step}",
            "pr",
            pr=f"#{31 + at}",
            why=f"{'hold' if step == 'hold' else 'wait'}: {said}",
        )
        for at, (step, said) in enumerate(JMERGE.items())
    ]
    scene.queue(
        [
            row("fig-seed", approved="", why="not approved"),
            row("fig-leaf", depends=["fig-seed"], why="depends on fig-seed"),
            row("fig-jam", why="no slot"),
            row("fig-bud", "launched", thread="mcp:7"),
            row("fig-tart", "running", thread="mcp:1"),
            row("fig-dew", "waiting", thread="mcp:8"),
            row("fig-wasp", "gate", why="a gate the Chef has"),
            *pulls,
            row("fig-tree", "merged", pr="#20"),
            row(
                "fig-pip",
                depends=["fig-tree"],
                pr="#21",
                thread="mcp:2",
                since=et(ago(minutes=30)),
                value="merged",
            ),
            row("fig-moth", "gate", why="a gate the Chef has", thread="mcp:3"),
            row("fig-stalk", "failed", thread="mcp:4", facts={"thread": "failed"}),
            row("fig-root", thread="mcp:5", value="lost", facts={"thread": "settled"}),
            row("fig-twig", "stale", thread="mcp:6", value="hung"),
            row("fig-husk", approved="", why="not approved", thread="mcp:9"),
            row("fig-stem", depends=["fig-pip"], why="depends on fig-pip"),
            row("fig-sap", depends=["fig-pip", "fig-tart"], why="depends on fig-pip, fig-tart"),
            row("fig-fly", depends=["fig-gone"], why="depends on fig-gone"),
            row("fig-pod", "done", thread="mcp:10"),
            row("fig-vine", "left", why="left: a page is still to write", thread="mcp:11"),
            row("fig-rind", "merged", pr="#19", why="a tag is still to push", thread="mcp:12"),
            row("fig-burr", "left", why="status: paused", thread="mcp:13"),
        ]
    )
    (scene.home / "tasks").mkdir(exist_ok=True)
    said = "## Result\nStatus: done\nLeft: a page is still to write\n"
    (scene.home / "tasks" / "fig-vine.md").write_text(f"# fig-vine\n\n{said}")
    (scene.home / "tasks" / "fig-burr.md").write_text("# fig-burr\n\n## Result\nStatus: paused\n")
    scene.waiting(
        [
            item("row", "row:fig-wasp", "gate fig-wasp: which way?", slug="fig-wasp"),
            item("row", "row:fig-moth", "gate fig-moth: which light?", slug="fig-moth"),
            item(
                "left",
                "left:fig-vine",
                "left fig-vine: left: a page is still to write",
                slug="fig-vine",
            ),
            item("left", "left:fig-burr", "left fig-burr: status: paused", slug="fig-burr"),
        ]
    )
    scene.merge_log(logged(40, "wait", 32, "it has no review yet"))
    scene.events(("jmerge", "chef", "fig-pip", "merged 21 fig-pip", 30))
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record["projects"][scene.name]["threads"] = [out("review: fig-review")]
    scene.write("pass.json", record, scene.state_dir)
    return {f"fig-{step}": step for step in JMERGE} | {
        "fig-seed": "unapproved",
        "fig-leaf": "behind",
        "fig-jam": "ready",
        "fig-bud": "launching",
        "fig-tart": "working",
        "fig-dew": "waiting",
        "fig-wasp": "asking",
        "fig-pip": "merged",
        "fig-moth": "asking",
        "fig-stalk": "lost",
        "fig-root": "lost",
        "fig-twig": "hung",
        "fig-husk": "unapproved",
        "fig-stem": "behind",
        "fig-sap": "behind",
        "fig-vine": "leftover",
        "fig-burr": "leftover",
        "fig-rind": "leftover",
        "fig-fly": "behind",
    }


def test_each_kind_of_row_is_in_one_state_with_one_reason_and_names_no_other(scene, served):
    expected = kinds(scene)
    rows = json.loads((scene.state / "queue.json").read_text())
    assert {one["status"] for one in rows} == set(queue.STATUSES)
    assert set(expected.values()) == set(work.VALUES) - {
        "removed",
        "done",
        "closed",
        "quiet",
        "unknown",
    }
    state = served.json("/state.json?project=demo")
    found = {one["slug"]: one for one in state["tasks"] + state["ended"]}
    assert {slug: one["state"]["kind"] for slug, one in found.items()} == expected
    unclosed = {"fig-burr", "fig-rind"}
    for slug, one in found.items():
        said, kind = one["state"], expected[slug]
        assert said["name"] == ("Ended, not closed" if slug in unclosed else NAMES[kind])
        assert said["say"] and said["waits"], slug
        assert one["reason"] == said["say"]
        spoken = said["waits"]
        if kind in JMERGE:
            assert said["say"] == JMERGE[kind]
        else:
            spoken += " " + said["say"]
        others = [name for name in NAMES.values() if name not in (said["name"], NAMES[kind])]
        if kind in ("leftover", "closed"):
            others = [name for name in others if name not in ("Merged", "Done")]
        named = [name for name in others if re.search(rf"\b{name}\b", spoken, re.I)]
        assert named == [], (slug, spoken)
    assert found["fig-leaf"]["state"]["waits"] == "fig-seed to merge"
    assert found["fig-jam"]["state"]["waits"] == "a slot"
    assert found["fig-seed"]["state"]["waits"] == found["fig-husk"]["state"]["waits"]
    assert found["fig-husk"]["state"]["waits"] == "your approval"
    assert found["fig-stalk"]["state"]["say"] == "its thread ended early and wrote nothing back"
    assert found["fig-root"]["state"]["say"] == "its thread was settled and wrote nothing"
    assert found["fig-root"]["state"]["waits"].startswith("your word on what is left")
    burr = found["fig-burr"]["state"]
    assert burr["say"] == (
        "it ended with no pull request, and its brief does not say the work is finished: "
        "status: paused"
    )
    assert (burr["waits"], burr["row"]) == ("your word on how it ends", "")
    assert "done" not in burr["say"]


def test_the_tasks_of_state_json_hold_exactly_the_states_of_work_json(scene, served):
    kinds(scene)
    judged = json.loads((scene.state / "work.json").read_text())["work"]
    state = served.json("/state.json?project=demo")
    drawn = {
        one["slug"]: (one["state"]["kind"], one["who"], one["step"])
        for one in state["tasks"] + state["ended"]
    }
    over = {"fig-pod", "fig-tree"}
    assert drawn == {
        one["slug"]: (one["value"], one["who"], one["lane"] or "unknown")
        for one in judged
        if one["slug"] not in over
    }
    rows = {
        one["slug"]: one["status"] for one in json.loads((scene.state / "queue.json").read_text())
    }
    assert rows["fig-pip"] == "queued" and drawn["fig-pip"][0] == "merged"
    assert [one["slug"] for one in state["ended"]] == ["fig-pip"]


def test_a_quiet_thread_and_a_closed_pull_request_are_drawn_as_the_pass_judged_them(scene, served):
    closed = "pull request #18 is not open and not merged"
    scene.queue(
        [
            row("fig-calm", "running", thread="mcp:14", value="quiet"),
            row("fig-shut", "left", pr="#18", why=closed, thread="mcp:15"),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    calm, shut = found["fig-calm"], found["fig-shut"]
    assert (calm["state"]["name"], calm["step"], calm["who"]) == ("Quiet", "running", "crew")
    assert calm["state"]["say"] == "its thread has written nothing for a while"
    assert (shut["state"]["kind"], shut["state"]["name"], shut["step"]) == (
        "closed",
        "Closed",
        "gate",
    )
    assert shut["state"]["say"] == (
        "its thread ended and its pull request #18 is not merged: " + closed
    )
    assert shut["state"]["waits"] == "your word on how it ends"


def test_a_row_work_json_does_not_have_is_unknown_and_says_what_its_row_says(scene, served):
    scene.queue([row("oat-bowl", "running", thread="mcp:0000")], judged=False)
    scene.write("work.json", {"at": iso(NOW), "answered": "both", "work": []})
    bowl = tasks(served.json("/state.json?project=demo"))["oat-bowl"]
    assert (bowl["state"]["kind"], bowl["step"], bowl["who"]) == ("unknown", "unknown", "unknown")
    assert bowl["state"]["say"] == "the last pass did not judge it: work.json does not have it"
    assert bowl["state"]["row"] == "the row says running, approved"


def test_a_task_the_last_pass_did_not_confirm_says_so(scene, served):
    scene.queue([row("oat-bowl", "running", thread="mcp:0000", confirmed=False)])
    bowl = tasks(served.json("/state.json?project=demo"))["oat-bowl"]
    assert bowl["state"]["kind"] == "working"
    assert bowl["unconfirmed"]["line"] == built.NOT_CONFIRMED


def test_a_task_behind_a_row_the_pass_judged_merged_is_still_behind_it_as_jbus_holds_it(
    scene, served
):
    kinds(scene)
    state = served.json("/state.json?project=demo")
    found = {one["slug"]: one for one in state["tasks"] + state["ended"]}
    stem, sap, fly = found["fig-stem"], found["fig-sap"], found["fig-fly"]
    assert stem["state"]["say"] == "fig-pip comes first"
    assert stem["state"]["waits"] == "jbus to see that fig-pip is through"
    assert stem["depends"] == [{"slug": "fig-pip", "state": "merged, and its row says queued"}]
    assert stem["blocked"] == {"by": "fig-pip", "what": "fig-pip", "state": "Merged"}
    assert sap["blockers"] == ["fig-tart", "fig-pip"]
    assert sap["state"]["waits"] == "fig-tart to merge"
    assert sap["blocked"] == {"by": "fig-tart", "what": "fig-tart", "state": "Running"}
    assert fly["blocked"] == {"by": "", "what": "fig-gone", "state": "not in the queue"}
    assert found["fig-pip"]["behind"] == ["fig-sap", "fig-stem"]


def test_a_task_that_is_merged_or_finished_is_not_on_the_line_and_a_lost_one_is(scene, served):
    kinds(scene)
    state = served.json("/state.json?project=demo")
    open_work = tasks(state)
    assert {"fig-pip", "fig-tree", "fig-pod"} & set(open_work) == set()
    assert {"fig-moth", "fig-vine"} <= set(open_work)
    assert sorted(one["slug"] for one in state["ended"]) == ["fig-pip"]
    held = {
        slug: (one["step"], one["who"])
        for slug, one in open_work.items()
        if one["state"]["kind"] in ("lost", "hung")
    }
    assert held == {
        "fig-root": ("running", "user"),
        "fig-stalk": ("running", "user"),
        "fig-twig": ("running", "user"),
    }
    vine = open_work["fig-vine"]
    assert (vine["state"]["kind"], vine["step"], vine["who"]) == ("leftover", "gate", "user")
    assert open_work["fig-twig"]["blocked"] == {"by": "", "what": "thread", "state": ""}
    assert open_work["fig-leaf"]["who"] == "dep" and open_work["fig-jam"]["who"] == "bus"


def test_a_fix_whose_scoped_review_is_not_written_is_on_the_second_pass(scene, served):
    """jv-work-state's case of 2026-10-14: its pull request sat in the Unknown lane on this
    reason, which `jmerge` gave and no rule named."""
    why = "wait: its fix is not reviewed: the scoped review of it is not written"
    scene.queue([row("jv-work-state", "pr", pr="#431", checks="passed", why=why)])
    task = tasks(served.json("/state.json?project=demo"))["jv-work-state"]
    assert (task["step"], task["who"]) == ("second", "rev")
    assert task["state"]["say"] == why.removeprefix("wait: ")


def test_a_reason_of_jmerge_that_no_pattern_matches_is_unknown_and_on_a_lane_of_its_own(
    scene, served
):
    scene.queue([row("oat-bowl", "pr", pr="#11", checks="passed", why="wait: another home's")])
    state = served.json("/state.json?project=demo")
    bowl = tasks(state)["oat-bowl"]
    assert (bowl["state"]["kind"], bowl["state"]["name"]) == ("unknown", "Unknown")
    assert bowl["state"]["say"] == "jmerge said: another home's"
    assert (bowl["step"], bowl["who"]) == ("unknown", "unknown")
    assert bowl["step"] not in {one["key"] for one in state["steps"]}
    assert (state["unknown"]["key"], state["unknown"]["name"]) == ("unknown", "Unknown")
    assert (bowl["state"]["waits"], bowl["state"]["row"]) == ("what the view cannot tell", "")
    scene.queue([row("oat-bowl", "pr", pr="#11")])
    said = tasks(served.json("/state.json?project=demo"))["oat-bowl"]["state"]
    assert (said["kind"], said["say"]) == ("unknown", "jmerge has said nothing of it yet")


def test_a_pass_that_could_not_ask_says_which_source_and_the_view_says_it_of_every_task(
    tmp_path, monkeypatch
):
    kitchen = Kitchen(tmp_path, monkeypatch)
    try:
        for slug in ("alpha", "beta"):
            text = complete(slug)
            assert kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)[0] == 0
        kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=2))
        sources = view.Sources(
            state_dir=kitchen.state_dir, home_dir=kitchen.home.parent, user=jsettings.load()
        )

        def told(minutes):
            now = POLLED + timedelta(minutes=minutes)
            kitchen.poll(now)
            record = json.loads((kitchen.state_dir / "pass.json").read_text())
            state = built.build(sources, "demo", now, lambda repo: {"runs": [], "at": None})
            assert sorted(one["slug"] for one in state["tasks"]) == ["alpha", "beta"]
            lines = {one["unconfirmed"] and one["unconfirmed"]["line"] for one in state["tasks"]}
            return record.get("silent"), lines, [one["line"] for one in state["blind"]]

        assert told(0)[:2] == ({}, {None})
        (kitchen.stub / "gh-down").touch()
        silent, lines, blind = told(1)
        assert silent == {"demo": "GitHub"}
        assert lines == {"not confirmed since 2026-10-12 11:00 ET: GitHub did not answer"}
        assert "2 tasks are not confirmed since 2026-10-12 11:00 ET: GitHub did not answer" in blind
        (kitchen.stub / "gh-down").unlink()
        token = (kitchen.config_dir / "t3.json").read_text()
        (kitchen.config_dir / "t3.json").unlink()
        silent, lines, _ = told(2)
        assert silent == {"demo": "T3 Code"}
        assert lines == {"not confirmed since 2026-10-12 11:00 ET: T3 Code did not answer"}
        kitchen.write(kitchen.config_dir / "t3.json", token)
        silent, lines, blind = told(3)
        assert (silent, lines) == ({}, {None})
        assert [line for line in blind if "not confirmed" in line] == []
    finally:
        kitchen.close()


def test_one_task_that_is_not_confirmed_is_said_as_one(scene, served):
    scene.queue([row("oat-bowl", "running", thread="mcp:0000")])
    record = json.loads((scene.state_dir / "pass.json").read_text())
    scene.write("pass.json", record | {"silent": {scene.name: "T3 Code"}}, scene.state_dir)
    blind = [one["line"] for one in served.json("/state.json?project=demo")["blind"]]
    assert "1 task is not confirmed since 2026-10-12 15:59 ET: T3 Code did not answer" in blind


def test_a_pass_that_starts_keeps_what_the_last_one_said_did_not_answer(tmp_path, monkeypatch):
    kitchen = Kitchen(tmp_path, monkeypatch)
    try:
        (kitchen.stub / "gh-down").touch()
        kitchen.poll()
        record.Record(jbus.load(), POLLED + timedelta(minutes=1)).start()
        written = json.loads((kitchen.state_dir / "pass.json").read_text())
        assert (written["ended"], written["silent"]) == (None, {"demo": "GitHub"})
        record.Record(jbus.load(), POLLED + timedelta(minutes=2)).end({}, {})
        written = json.loads((kitchen.state_dir / "pass.json").read_text())
        assert (bool(written["ended"]), written["silent"]) == (True, {"demo": "GitHub"})
        record.Record(jbus.load(), POLLED + timedelta(minutes=3)).end({"demo": {}}, {})
        assert json.loads((kitchen.state_dir / "pass.json").read_text())["silent"] == {}
    finally:
        kitchen.close()


def test_the_limits_file_is_a_source_and_a_limit_whose_reset_is_past_is_unknown(scene, served):
    path = scene.root / "limits"
    state = served.json("/state.json?project=demo")
    source = {one["name"]: one for one in state["sources"]}["limits"]
    assert (source["by"], source["state"]) == ("session", "ok")
    assert source["at"] == built.iso(datetime.fromtimestamp(path.stat().st_mtime, UTC))
    assert state["room"]["plan"]["five_hour"]["used"] == 23.0
    past, ahead = int(ago(hours=1).timestamp()), int((NOW + timedelta(days=3)).timestamp())
    path.write_text(f"five_hour 23.0 {past}\nseven_day 22.0 {ahead}\n")
    written = ago(hours=6).timestamp()
    os.utime(path, (written, written))
    state = served.json("/state.json?project=demo")
    plan = state["room"]["plan"]
    assert plan["five_hour"] == {
        "used": None,
        "resets": iso(ago(hours=1)),
        "written": iso(ago(hours=6)),
        "say": f"unknown, last written {et(ago(hours=6))}",
    }
    assert "23" not in json.dumps(plan["five_hour"]) and "%" not in json.dumps(plan)
    assert (plan["seven_day"]["used"], plan["seven_day"]["say"]) == (22.0, "")
    source = {one["name"]: one for one in state["sources"]}["limits"]
    assert (source["state"], source["at"]) == ("stale", iso(ago(hours=6)))
    line = f"the plan's five-hour limit is unknown, last written {et(ago(hours=6))}"
    assert {"line": line, "open": "room"} in state["blind"]
    path.unlink()
    state = served.json("/state.json?project=demo")
    assert state["room"]["plan"] == {}
    assert {one["name"]: one["state"] for one in state["sources"]}["limits"] == "missing"
    assert [one for one in state["blind"] if "could not be read" in one["line"]] == []


def test_the_page_says_what_it_still_cannot_say(served):
    blind = [one["line"] for one in served.json("/state.json?project=demo")["blind"]]
    spots = [spot for panel in panels.found() for spot in panel.not_kept]
    never = [spot.line for spot in sorted(spots, key=lambda spot: spot.rank)]
    assert never and never == blind[-len(never) :]
    assert "the step a task of unknown state is on is not guessed" in blind
    assert (
        "the plan's use since the limits file was last written is not known: "
        "only a session's status line writes it"
    ) in blind
    assert (
        "a pass that raised, or could not read its queue, is not said on a task: "
        "only T3 Code and GitHub are"
    ) in blind


OPEN = ("leaf", "bark", "sap")
NOTE = "the style pass over the four pages of the guide, " + "page by page, " * 30 + "to the end"


def leftovers(scene):
    """Two tasks that are finished and left a note, and one that is stuck. `plum-jam` merged
    and its brief has the note whole, where the row has it cut as a pass cuts it.
    `plum-pit` ended with no pull request, `plum-skin` is queued over a thread that failed,
    and `plum-stem` left a note in a Result that says it is paused. `plum-leaf` is done and
    its Result names no branch, `plum-bark` has a note and no brief to read, and `plum-sap`
    is done with a note and a pull request that did not merge."""
    cut = "left: " + NOTE[:95] + "[cut]"
    scene.queue(
        [
            row("plum-jam", "merged", pr="#51", why=cut, thread="mcp:21"),
            row("plum-pit", "left", why="left: the stones are not sorted", thread="mcp:22"),
            row("plum-skin", thread="mcp:23", value="lost", facts={"thread": "failed"}),
            row("plum-stem", "left", why="left: the stem is half cut", thread="mcp:24"),
            row("plum-leaf", "left", why="its Result has no Branch line", thread="mcp:25"),
            row("plum-bark", "left", why="left: the bark is not off", thread="mcp:26"),
            row("plum-sap", "left", pr="#52", why="left: the sap is not drawn", thread="mcp:27"),
        ]
    )
    (scene.home / "tasks").mkdir(exist_ok=True)
    for slug, status, note in (
        ("plum-pit", "done", "the stones are not sorted"),
        ("plum-stem", "paused", "the stem is half cut"),
        ("plum-leaf", "done", "none"),
        ("plum-sap", "done", "the sap is not drawn"),
    ):
        said = f"## Result\nStatus: {status}\nLeft: {note}\n"
        (scene.home / "tasks" / f"{slug}.md").write_text(f"# {slug}\n\n{said}")
    result = f"## Result\nStatus: done\nLeft: {NOTE}\nBranch: {PULL.format(51)}\n"
    (scene.home / "tasks" / "plum-jam.md").write_text(f"# plum-jam\nTask: jam\n\n{result}")
    scene.waiting(
        [
            item("left", "left:plum-jam", f"left plum-jam: {cut}", slug="plum-jam"),
            item("left", "left:plum-pit", "left plum-pit: left: the stones", slug="plum-pit"),
            item("left", "left:plum-stem", "left plum-stem: left: the stem", slug="plum-stem"),
            *(item("left", f"left:plum-{one}", "left", slug=f"plum-{one}") for one in OPEN),
        ]
    )
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record["projects"][scene.name]["rows"] = {
        "plum-skin": {"threads": 1, "thread_status": "failed", "thread_updated": iso(NOW)}
    }
    scene.write("pass.json", record, scene.state_dir)


def test_a_merged_task_that_left_a_note_is_done_and_waits_only_for_a_word_on_the_note(
    scene, served
):
    leftovers(scene)
    assert len(NOTE) > 300
    jam = tasks(served.json("/state.json?project=demo"))["plum-jam"]
    said = jam["state"]
    assert (said["kind"], said["name"]) == ("leftover", "Ended, with a leftover")
    assert "lost" not in json.dumps(jam).lower()
    assert said["say"].startswith("its pull request #51 is merged and the work is done. ")
    assert f"Its crewmate left a note of something it did not do: {NOTE}. " in said["say"]
    assert "[cut]" not in said["say"]
    assert said["say"].endswith(
        "Either of two things ends it: a new task for what was left, "
        "a Left: none line in its brief once you say the rest is not wanted"
    )
    assert (said["waits"], said["row"]) == ("your word on that note", "")
    assert (jam["step"], jam["who"], jam["blocked"]) == ("gate", "user", None)


def test_a_task_that_ended_with_no_pull_request_and_a_note_is_done_too(scene, served):
    leftovers(scene)
    found = tasks(served.json("/state.json?project=demo"))
    said = found["plum-pit"]["state"]
    assert (said["kind"], said["waits"]) == ("leftover", "your word on that note")
    assert said["say"].startswith("it ended with no pull request and the work is done. ")
    assert "left a note of something it did not do: the stones are not sorted. " in said["say"]
    assert found["plum-skin"]["state"]["name"] == "Lost"
    stem = found["plum-stem"]["state"]
    assert (stem["kind"], stem["name"]) == ("leftover", "Ended, not closed")
    assert stem["say"] == (
        "it ended with no pull request, and its brief does not say the work is finished. "
        "Its crewmate left a note: the stem is half cut"
    )
    assert stem["waits"] == "your word on how it ends"
    assert [slug for slug, one in found.items() if one["state"]["kind"] == "lost"] == ["plum-skin"]


def test_a_row_that_ended_says_its_brief_is_not_finished_only_where_a_status_says_so(scene, served):
    leftovers(scene)
    found = tasks(served.json("/state.json?project=demo"))
    said = {one: found[f"plum-{one}"]["state"] for one in OPEN}
    assert {one["name"] for one in said.values()} == {"Ended, not closed"}
    assert said["leaf"]["say"] == "it ended with no pull request: its Result has no Branch line"
    assert said["bark"]["say"] == (
        "it ended with no pull request. Its crewmate left a note: the bark is not off"
    )
    assert said["sap"]["say"] == (
        "its thread ended and its pull request #52 is not merged. "
        "Its crewmate left a note: the sap is not drawn"
    )


def test_a_note_longer_than_the_view_keeps_is_cut_and_the_sentence_keeps_its_end(scene, served):
    leftovers(scene)
    brief = scene.home / "tasks" / "plum-jam.md"
    brief.write_text(brief.read_text().replace(NOTE, "long " * 2000))
    say = tasks(served.json("/state.json?project=demo"))["plum-jam"]["state"]["say"]
    assert say.endswith("once you say the rest is not wanted") and len(say) < 5000


def test_the_waiting_list_words_a_leftover_as_the_drawer_does(scene, served):
    leftovers(scene)
    state = served.json("/state.json?project=demo")
    found = tasks(state)
    lines = {one["slug"]: one["line"] for one in state["waiting"] if one["kind"] == "left"}
    assert lines == {
        slug: found[slug]["state"]["say"]
        for slug in ("plum-jam", "plum-pit", "plum-stem", *(f"plum-{one}" for one in OPEN))
    }
    assert lines["plum-jam"].startswith("its pull request #51 is merged and the work is done")
    assert NOTE in lines["plum-jam"]


def test_a_chain_of_three_names_each_blocker_and_the_first_blocks_two(scene, served):
    findings = "wait: its findings are not handled: the Result has no Fixed line"
    scene.queue(
        [
            row("nut-shell", "pr", pr="#41", why=findings),
            row("nut-meat", depends=["nut-shell"], why="depends on nut-shell"),
            row("nut-oil", depends=["nut-meat"], why="depends on nut-meat"),
            row("nut-husk", approved="", why="not approved"),
            row("nut-bowl", "running", thread="mcp:1"),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    assert found["nut-shell"]["blocked"] == {"by": "", "what": "findings", "state": ""}
    assert found["nut-meat"]["blocked"] == {
        "by": "nut-shell",
        "what": "nut-shell",
        "state": "Findings",
    }
    assert found["nut-oil"]["blocked"] == {"by": "nut-meat", "what": "nut-meat", "state": "Behind"}
    assert found["nut-shell"]["behind"] == ["nut-meat", "nut-oil"]
    assert found["nut-husk"]["blocked"] == {"by": "", "what": "approval", "state": ""}
    assert found["nut-bowl"]["blocked"] is None
    assert {slug: one["blocks"] for slug, one in found.items()} == {
        "nut-shell": 2,
        "nut-meat": 1,
        "nut-oil": 0,
        "nut-husk": 0,
        "nut-bowl": 0,
    }


def test_each_queued_row_has_a_wave_and_the_one_row_it_waits_on_last(scene, served):
    """A chain of four, `pea-soup` behind three rows, and `pea-vine` behind a row that is out.
    `pea-mash` waits on two rows of one wave, and `pea-pod` is the first of them in the queue.
    `pea-husk` is not approved, and `pea-salt` is behind a row that merged."""
    scene.queue(
        [
            row("pea-pod", "gate", why="a gate the Chef has", priority=0),
            row("pea-one"),
            row("pea-two", depends=["pea-one"]),
            row("pea-three", depends=["pea-two"]),
            row("pea-four", depends=["pea-three"]),
            row("pea-soup", depends=["pea-one", "pea-three", "pea-two"]),
            row("pea-vine", depends=["pea-pod"]),
            row("pea-mash", depends=["pea-one", "pea-pod"]),
            row("pea-husk", approved="", why="not approved", depends=["pea-two"]),
            row("pea-done", "merged", pr="#61"),
            row("pea-salt", depends=["pea-done"]),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    assert {slug: (one["wave"], one["waits_on"]) for slug, one in found.items()} == {
        "pea-pod": (None, ""),
        "pea-one": (0, ""),
        "pea-two": (1, "pea-one"),
        "pea-three": (2, "pea-two"),
        "pea-four": (3, "pea-three"),
        "pea-soup": (3, "pea-three"),
        "pea-vine": (1, "pea-pod"),
        "pea-mash": (1, "pea-pod"),
        "pea-husk": (2, "pea-two"),
        "pea-salt": (0, ""),
    }
    assert found["pea-husk"]["state"]["kind"] == "unapproved"
    assert found["pea-husk"]["blocked"] == {"by": "", "what": "approval", "state": ""}


def test_rows_that_depend_on_each_other_still_get_a_wave():
    assert waves(["a", "b", "c"], {"a": ["b"], "b": ["a"], "c": ["gone"]}) == {
        "a": (2, "b"),
        "b": (1, "a"),
        "c": (1, "gone"),
    }


def test_the_wait_band_is_the_list_the_pass_left_with_the_gates_read_now(scene, served):
    waiting = served.json("/state.json?project=demo")["waiting"]
    assert [(one["kind"], one["line"]) for one in waiting] == [
        ("gate", "gate 4: tea or coffee?"),
        ("row", "gate jam-lid: which lid?"),
        ("approve", "approve tea-kettle: jbus queue approve"),
        ("hold", "hold 14: needs user"),
    ]
    assert waiting[0]["since"] == iso(ago(hours=3))
    assert (waiting[0]["question"], waiting[0]["default"]) == ("tea or coffee?", "tea")
    with open(scene.home / "gates.md", "a") as gates:
        gates.write("\n" + GATE.format(n=6, asked="milk?", status="open", default="no"))
    waiting = served.json("/state.json?project=demo")["waiting"]
    assert [one["line"] for one in waiting if one["kind"] == "gate"] == [
        "gate 4: tea or coffee?",
        "gate 6: milk?",
    ]
    assert waiting[1]["since"] is None


def test_jbus_is_passing_while_the_timer_is_active_and_a_pass_ended_lately(served):
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (False, "")
    assert jbus["last_end"] == iso(ago(seconds=20))
    assert jbus["said"] == "jbus.timer active (waiting), jbus.service success, exit 0"


def test_jbus_has_stopped_when_the_timer_is_not_active(scene, served):
    scene.timer(active="inactive", sub="dead", result="exit-code", code=1)
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (True, "the timer is not active")
    assert jbus["said"] == "jbus.timer inactive (dead), jbus.service exit-code, exit 1"
    assert jbus["last_end"] == iso(ago(seconds=20))


def test_jbus_has_stopped_when_the_last_pass_ended_more_than_150_s_ago(scene, served):
    scene.passed(seconds_ago=150)
    assert served.json("/state.json?project=demo")["jbus"]["stopped"] is False
    scene.passed(seconds_ago=151)
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (True, "no pass in the last 150 s")
    assert jbus["last_end"] == iso(ago(seconds=151))


def test_a_pass_that_is_running_is_no_stop_and_one_that_hangs_is(scene, served):
    scene.passed(seconds_ago=-10, running=True)
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["pass"]["running"]) == (False, True)
    scene.now = NOW + timedelta(seconds=200)
    assert served.json("/state.json?project=demo")["jbus"]["stopped"] is True


def test_a_pass_that_systemd_says_is_running_is_no_stop_however_long_it_takes(scene, served):
    scene.passed(seconds_ago=-10, running=True)
    scene.now = NOW + timedelta(seconds=200)
    scene.timer(service="activating")
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (False, "")


def test_a_pass_that_starts_and_dies_each_minute_has_stopped(scene, served):
    scene.passed(seconds_ago=400)
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record |= {"started": iso(ago(seconds=5)).replace("+00:00", "Z"), "ended": None}
    scene.write("pass.json", record, scene.state_dir)
    jbus = served.json("/state.json?project=demo")["jbus"]
    assert (jbus["stopped"], jbus["why"]) == (True, "no pass in the last 150 s")
    assert jbus["last_end"] == iso(ago(seconds=400).replace(second=0))


def test_what_jbus_wrote_is_frozen_and_what_the_server_reads_is_live(served):
    sources = {one["name"]: one["by"] for one in served.json("/state.json?project=demo")["sources"]}
    assert {name for name, by in sources.items() if by == "server"} == {
        "jbus.timer",
        "gates.md",
        "scouts/",
        "GitHub",
        "runner units",
        "the machine",
        "~/.claude/projects",
    }
    assert {"queue.json", "waiting-on-user.json", "status.json", "pass.json"} <= {
        name for name, by in sources.items() if by == "jbus"
    }


def test_the_room_is_the_one_answer_jgauge_room_gives(scene, served):
    room = served.json("/state.json?project=demo")["room"]
    assert (room["answer"], room["why"], room["load"][0]) == ("go", "", 2.5)
    assert room["plan"]["five_hour"]["used"] == 23.0
    assert room["limits"] == {"load": 85, "memory": 6, "pressure": 10, "slots": 85, "plan": 85}
    scene.machine(five_hour=91.0)
    room = served.json("/state.json?project=demo")["room"]
    assert room["answer"] == "wait"
    assert room["why"].startswith("the five-hour limit is 91.0% used, at or over 85%")


def test_github_is_asked_for_the_checks_card_once_a_minute(scene, served):
    for _ in range(5):
        state = served.json("/state.json?project=demo")
    assert scene.asked() == ["api repos/acme/demo/actions/runs?per_page=40"]
    assert [(run["branch"], run["state"]) for run in state["checks"]["runs"]] == [
        ("oat-bowl", "success"),
        ("oat-milk", "failure"),
        ("oat-milk", "in_progress"),
    ]
    assert state["checks"]["runs"][0]["url"] == RUN.format(500)
    scene.now = NOW + timedelta(seconds=59)
    served.json("/state.json?project=demo")
    assert len(scene.asked()) == 1
    scene.now = NOW + timedelta(seconds=61)
    served.json("/state.json?project=demo")
    assert scene.asked() == ["api repos/acme/demo/actions/runs?per_page=40"] * 2


def test_github_is_asked_for_a_pull_request_only_when_its_drawer_opens(scene, served):
    served.json("/state.json?project=demo")
    scene.calls.write_text("")
    for _ in range(3):
        found = served.json("/task/oat-milk/github?project=demo")
    assert scene.asked() == [
        "api repos/acme/demo/pulls/13",
        "api repos/acme/demo/commits/" + "d00d" * 10 + "/check-runs",
    ]
    assert found["pull"] == {
        "number": 13,
        "state": "open",
        "merged": False,
        "mergeable": True,
        "mergeable_state": "blocked",
        "head": "d00d" * 10,
        "updated": iso(ago(minutes=3)),
        "url": PULL.format(13),
    }
    assert [(one["name"], one["state"]) for one in found["checks"]] == [("check", "in_progress")]
    scene.now = NOW + timedelta(seconds=31)
    served.json("/task/oat-milk/github?project=demo")
    assert len(scene.asked()) == 4


def test_a_slow_github_holds_no_other_request_and_none_for_long(scene, served):
    served.json("/state.json?project=demo")
    served.doors.app.github.patience = 0.2
    asks = (scene.bin / "gh").read_text().removeprefix("#!/bin/sh\n")
    scene.script("gh", "sleep 0.7\n" + asks)
    began = time.monotonic()
    drawer = threading.Thread(target=served.json, args=("/task/oat-milk/github?project=demo",))
    drawer.start()
    time.sleep(0.05)
    state = served.json("/state.json?project=demo")
    assert time.monotonic() - began < 1.0
    assert len(state["checks"]["runs"]) == 3
    drawer.join()
    waiting = served.json("/task/oat-milk/github?project=demo")
    assert (waiting["pull"], waiting["error"]) == (None, "GitHub has not answered yet")
    scene.now = NOW + timedelta(seconds=61)
    stale = served.json("/state.json?project=demo")
    assert time.monotonic() - began < 1.2
    assert (len(stale["checks"]["runs"]), stale["checks"]["error"]) == (3, "")
    time.sleep(1.7)
    assert served.json("/task/oat-milk/github?project=demo")["pull"]["number"] == 13


def test_a_task_with_no_pull_request_asks_github_nothing(scene, served):
    served.json("/state.json?project=demo")
    scene.calls.write_text("")
    assert served.json("/task/jam-jar/github?project=demo") == {
        "slug": "jam-jar",
        "pull": None,
        "checks": [],
    }
    assert scene.asked() == []


def test_a_slug_the_queue_does_not_have_is_404_and_asks_nothing(scene, served):
    served.json("/state.json?project=demo")
    scene.calls.write_text("")
    for slug in ("nobody", "..", "oat-milk%2F..", "%2e%2e", "13", "oat-milk/../jam-jar"):
        assert served.ask(f"/task/{slug}/github?project=demo")[0] == 404, slug
    assert scene.asked() == []


def test_github_is_only_ever_read(scene, served):
    served.json("/state.json?project=demo")
    for slug in ("oat-bowl", "oat-spoon", "oat-milk", "oat-honey"):
        served.json(f"/task/{slug}/github?project=demo")
    assert scene.asked()
    for call in scene.asked():
        words = call.split()
        assert words[0] == "api" and len(words) == 2, call
        assert words[1].startswith("repos/acme/demo/"), call


def test_a_github_that_does_not_answer_is_said_and_the_page_still_gets_its_state(scene, served):
    scene.script("gh", "exit 1\n")
    state = served.json("/state.json?project=demo")
    assert (state["checks"]["runs"], state["checks"]["error"]) == ([], "GitHub did not answer")
    assert served.json("/task/oat-milk/github?project=demo")["error"] == "GitHub did not answer"
    assert len(state["tasks"]) == 9


def plant(scene):
    """A fake secret in every source the server reads, and in the three it must never read."""
    shaped = " ".join(SHAPED)
    links = " ".join(LINKS)
    leak = f"{shaped} {links} key={OPAQUE} Authorization: Bearer {OPAQUE}"
    hidden = {"webhook_url": LINKS[0], "webhook_key": OPAQUE, "note": OPAQUE}
    rows = [one | hidden | {"why": f"{one['why']} {leak}"} for one in table()]
    scene.queue(rows)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status |= hidden
    status["projects"]["demo"] |= hidden | {"last_error": leak, "sign_in": leak, "sweep": leak}
    status["streaks"] = {"pass": {"count": 3, "why": leak} | hidden}
    scene.write("status.json", status, scene.state_dir)
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record |= hidden
    record["projects"]["demo"] |= hidden
    record["projects"]["demo"]["rows"] = {"oat-milk": {"checks": leak, "check": hidden} | hidden}
    scene.write("pass.json", record, scene.state_dir)
    scene.write("main.json", {"at": iso(NOW), "main": leak} | hidden)
    scene.write("checks.json", {leak: "green", OPAQUE: OPAQUE})
    scene.write("stall.json", {leak: {"line": leak} | hidden})
    scene.write("wake.json", {"began": True, "last_error": leak, "posted": 1.0} | hidden)
    scene.write("sent.json", [f"result|{OPAQUE}|{leak}", leak])
    scene.waiting(
        [
            item("row", "row:jam-lid", f"gate jam-lid: {leak}", slug="jam-lid") | hidden,
            item("hold", "#14", leak, number=14) | {"url": LINKS[1]} | hidden,
        ]
    )
    scene.lines(
        "transitions.jsonl", [{"slug": "rye-loaf", "to": "merged", "at": iso(NOW)} | hidden]
    )
    scene.lines(
        "events.jsonl",
        [
            {
                "at": iso(NOW),
                "event": "gate",
                "id": "1",
                "line": leak,
                "loud": "user",
                "slug": "jam-lid",
            }
            | {"text": OPAQUE}
            | hidden
        ],
    )
    scene.merge_log(logged(3, "wait", 13, leak), f"2026-10-12 15:00 kept {OPAQUE}: {leak}")
    (scene.home / "gates.md").write_text(GATE.format(n=4, asked=leak, status="open", default=leak))
    said = TIMER.format(active=leak, sub=leak, result=leak, code=leak, service=leak)
    (scene.root / "systemctl.txt").write_text(said)
    (scene.root / "limits").write_text(f"five_hour 23.0 1 {OPAQUE}\n{leak}\n")
    scene.github(title=leak, body=leak, mergeable_state=leak, token=OPAQUE, html_url=LINKS[1])
    runs = json.loads((scene.root / "runs.json").read_text())
    runs["workflow_runs"][0] |= hidden | {"head_branch": leak, "html_url": LINKS[0], "name": leak}
    scene.write("runs.json", runs, scene.root)
    scene.write("outbox.json", [{"line": UNREAD[0]}])
    (scene.root / "config").mkdir(exist_ok=True)
    (scene.root / "config" / "config.toml").write_text(f'webhook_key = "{UNREAD[1]}"\n')
    (scene.root / "config" / "t3.json").write_text(
        json.dumps({"token": {"access_token": UNREAD[2]}})
    )


def test_a_fake_secret_planted_in_every_source_is_in_no_answer(scene, served):
    plant(scene)
    paths = [
        "/",
        "/state.json?project=demo",
        "/state.json?project=demo",
        "/digest.json",
        "/healthz",
        "/nothing",
    ]
    paths += [f"/task/{one['slug']}/github" for one in table()]
    paths += view.routes()[len(view.FIXED) :]
    paths += [
        "/digest.json?since=2026-10-01",
        f"/task/{OPAQUE}/github?project=demo",
        "/state.json?project=nobody",
    ]
    held = {}
    for path in paths:
        _, headers, body = served.ask(path)
        said = body + json.dumps(headers)
        held[path] = [secret for secret in PLANTED if secret in said]
    assert held == {path: [] for path in paths}
    state = served.json("/state.json?project=demo")
    assert "[redacted]" in json.dumps(state)
    assert len(state["tasks"]) == 10


def test_a_link_to_a_pull_request_or_a_run_of_this_repo_is_kept(scene, served):
    line = f"see {PULL.format(13)} and {RUN.format(502)}, not {LINKS[1]} or {LINKS[0]}."
    scene.events(("result", "chef", "oat-milk", line, 1))
    said = served.json("/state.json?project=demo")["bus"]["events"][-1]["line"]
    assert said == f"see {PULL.format(13)} and {RUN.format(502)}, not [link] or [link]."


def test_a_word_that_only_holds_the_shape_of_a_key_leaves_whole(scene, served):
    slug = "task-drawer-shows-the-github-part"
    line = "result refresh-token: Status: done, see risk-register-of-the-whole-kitchen"
    scene.queue([row(slug, "running"), row("disk-usage-of-the-pantry-shelves-again", "running")])
    scene.events(("result", "chef", slug, line, 1))
    state = served.json("/state.json?project=demo")
    assert [one["slug"] for one in state["tasks"]] == [
        "disk-usage-of-the-pantry-shelves-again",
        slug,
    ]
    assert state["bus"]["events"][-1] == {
        "at": iso(ago(minutes=1)),
        "kind": "result",
        "loud": "quiet",
        "slug": slug,
        "line": line,
    }
    assert served.ask(f"/task/{slug}/github?project=demo")[0] == 200
    kept = "X-Automation-Key: " + "h7Kq" * 6
    scene.events(("note", "quiet", "", f"{kept} and my-token = hunter2hunter2", 1))
    said = served.json("/state.json?project=demo")["bus"]["events"][-1]["line"]
    assert said == "X-Automation-Key: [redacted] and my-token = [redacted]"


def test_the_files_that_hold_secrets_are_never_opened(scene, served, monkeypatch):
    plant(scene)
    opened = []
    real = Path.read_text

    def spy(path, *args, **kwargs):
        opened.append(str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    for path in ("/state.json?project=demo", "/digest.json", "/task/oat-milk/github?project=demo"):
        served.json(path)
    assert opened
    assert [name for name in opened if "outbox.json" in name or "/config/" in name] == []
    assert [name for name in opened if name.startswith(str(scene.root)) and "t3.json" in name] == []


def test_the_server_writes_nothing(scene, served):
    def tree():
        found = {}
        for top in (scene.state_dir, scene.home_dir):
            for path in sorted(top.rglob("*")):
                found[str(path)] = (path.stat().st_mtime_ns, path.is_file() and path.read_bytes())
        return found

    before = tree()
    for path in ("/", "/digest.json", "/task/oat-milk/github?project=demo", *view.routes()):
        served.ask(path)
    assert tree() == before


def test_a_source_that_is_missing_or_does_not_parse_is_said_and_nothing_raises(scene, served):
    (scene.state / "queue.json").write_text("{not json")
    (scene.state / "events.jsonl").write_text("not a line\n[]\n")
    for name in ("main.json", "checks.json", "waiting-on-user.json", "transitions.jsonl"):
        (scene.state / name).unlink()
    (scene.home / "merge.log").unlink()
    (scene.state_dir / "pass.json").write_text("[]")
    state = served.json("/state.json?project=demo")
    sources = {one["name"]: one["state"] for one in state["sources"]}
    assert (sources["queue.json"], sources["main.json"], sources["status.json"]) == (
        "unreadable",
        "missing",
        "ok",
    )
    assert (sources["pass.json"], sources["merge.log"]) == ("unreadable", "missing")
    assert (state["tasks"], state["waiting"][0]["kind"]) == ([], "gate")
    assert (state["jbus"]["stopped"], state["jbus"]["pass"]["ended"]) == (False, None)
    (scene.state_dir / "status.json").unlink()
    assert served.json("/state.json?project=demo")["jbus"]["stopped"] is True
    assert {"line": "queue.json could not be read", "open": "pulse"} in state["blind"]
    assert {"line": "main.json could not be read", "open": "pulse"} in state["blind"]
    assert served.ask("/digest.json")[0] == 200


def test_a_long_pass_that_is_passing_names_no_source(scene, served):
    scene.passed(seconds_ago=-10, running=True)
    scene.now = NOW + timedelta(seconds=200)
    scene.timer(service="activating")
    started, before = ago(seconds=0).timestamp(), ago(seconds=60).timestamp()
    os.utime(scene.state_dir / "pass.json", (started, started))
    os.utime(scene.state_dir / "status.json", (before, before))
    state = served.json("/state.json?project=demo")
    assert state["jbus"]["stopped"] is False
    assert {one["name"]: one["state"] for one in state["sources"] if one["state"] != "ok"} == {}


def test_a_home_with_no_gates_file_and_a_passing_jbus_names_no_source(scene, served):
    (scene.home / "gates.md").unlink()
    state = served.json("/state.json?project=demo")
    assert state["jbus"]["stopped"] is False
    assert {one["name"]: one["state"] for one in state["sources"] if one["state"] != "ok"} == {}
    assert [one for one in state["blind"] if "gates.md" in one["line"]] == []


def test_only_an_old_answer_of_github_is_stale(scene, served):
    state = served.json("/state.json?project=demo")
    assert {one["state"] for one in state["sources"]} == {"ok"}
    old = ago(seconds=400).timestamp()
    for path in (scene.state_dir / "status.json", scene.state_dir / "pass.json"):
        os.utime(path, (old, old))
    os.utime(scene.state / "main.json", (old, old))
    served.doors.app.github.patience = 0.05
    asks = (scene.bin / "gh").read_text().removeprefix("#!/bin/sh\n")
    scene.script("gh", "sleep 0.5\n" + asks)
    scene.now = NOW + timedelta(seconds=200)
    state = served.json("/state.json?project=demo")
    assert {one["name"]: one["state"] for one in state["sources"] if one["state"] != "ok"} == {
        "GitHub": "stale",
    }
    assert [one for one in state["blind"] if "could not be read" in one["line"]] == []


def test_a_state_directory_with_no_project_answers_with_none(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    for path in sorted(scene.state_dir.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        assert stack["projects"] == []
        assert stack["machine"]["jbus"]["stopped"] is True
        for path in ("/state.json", "/state.json?project=demo", "/panel/pulse.json"):
            assert served.ask(path)[0] == 404
        assert served.ask("/")[0] == 200
    finally:
        served.close()


def test_a_second_project_is_asked_for_by_name(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    other = scene.state_dir / "pantry"
    other.mkdir()
    (other / "queue.json").write_text(json.dumps([row("fig-jam", "running")]))
    (scene.state_dir / "launches").mkdir()
    served = Served(scene)
    try:
        assert served.json("/state.json?project=demo")["projects"] == ["demo", "pantry"]
        found = served.json("/state.json?project=pantry")
        assert (found["project"], [one["slug"] for one in found["tasks"]]) == (
            "pantry",
            ["fig-jam"],
        )
        assert served.ask("/state.json?project=launches")[0] == 404
        assert served.ask("/task/fig-jam/github?project=pantry")[0] == 200
        assert served.ask("/task/fig-jam/github")[0] == 404
    finally:
        served.close()


def out(title, live="moving", status="running", minutes=1, **more):
    """One thread as a pass leaves it in `pass.json`, which last wrote so long ago."""
    role, _, slug = title.partition(": ")
    known = {"crew": "crew", "review": "reviewer", "scout": "scout", "home": "home"}
    return {
        "id": f"mcp:{title}",
        "title": title,
        "role": known.get(role, "other") if slug else "other",
        "slug": slug.removesuffix(", second pass") if role in known else "",
        "status": status,
        "createdAt": iso(ago(hours=1)).replace("+00:00", "Z"),
        "updatedAt": iso(ago(seconds=30)).replace("+00:00", "Z"),
        "items": 9,
        "wrote": iso(ago(minutes=minutes)).replace("+00:00", "Z"),
        "live": live,
        "silent": minutes,
        "run": "run-1",
        "run_started": None,
        "queued": 0,
        "pending": 0,
        "page": False,
    } | more


def test_the_state_has_every_thread_out_and_each_task_its_threads_liveness(scene, served):
    began = iso(ago(minutes=40))
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar", "hung", minutes=25, run_started=began, queued=2),
            out("review: oat-milk, second pass", "quiet", minutes=12),
            out("scout: look", "waiting", minutes=90, page=True),
            out("home: demo"),
            out("a thread he opened", "ended", "completed"),
            out("crew: odd", "a word nobody named", secret=OPAQUE),
        ],
        rows={"jam-jar": {"threads": 1, "thread_status": "running", "live": "hung"}},
    )
    state = served.json("/state.json?project=demo")
    assert [(t["title"], t["role"], t["slug"], t["live"], t["out"]) for t in state["threads"]] == [
        ("crew: jam-jar", "crew", "jam-jar", "hung", True),
        ("review: oat-milk, second pass", "reviewer", "oat-milk", "quiet", True),
        ("scout: look", "scout", "look", "waiting", True),
        ("home: demo", "home", "demo", "moving", True),
        ("a thread he opened", "other", "", "ended", False),
        ("crew: odd", "crew", "odd", "unknown", True),
    ]
    assert state["threads"][0] == {
        "today": True,
        "title": "crew: jam-jar",
        "role": "crew",
        "slug": "jam-jar",
        "status": "running",
        "live": "hung",
        "out": True,
        "created": iso(ago(hours=1)),
        "updated": iso(ago(minutes=25)),
        "run_started": began,
        "queued": 2,
        "pending": 0,
        "page": False,
    }
    seen = tasks(state)["jam-jar"]["seen"]
    assert (seen["live"], seen["run_started"], seen["queued"]) == ("hung", began, 2)
    assert seen["wrote"] == iso(ago(minutes=25))
    assert tasks(state)["oat-milk"]["seen"]["live"] == ""
    scene.passed(
        20,
        threads=[out("crew: jam-jar", "hung", run_started=began, queued=2), out("crew: jam-jar")],
        rows={"jam-jar": {"threads": 2, "thread_status": None, "live": None}},
    )
    seen = tasks(served.json("/state.json?project=demo"))["jam-jar"]["seen"]
    assert (seen["live"], seen["wrote"], seen["queued"]) == ("", None, 0)
    assert "the threads that are out" not in json.dumps(state["blind"])


REQUEST = '# {slug}: what is in the {slug} tin\nRequest: "look in the tin"\n'
REPORTED = REQUEST + "\n## Report\nStatus: {status}\nAnswers:\n- it holds tea\n"


def requested(scene, **files):
    """A request under the home's `scouts/` for each slug, as its text."""
    (scene.home / "scouts").mkdir(exist_ok=True)
    for slug, text in files.items():
        (scene.home / "scouts" / f"{slug.replace('_', '-')}.md").write_text(text)


def test_each_scouts_request_says_researching_reported_or_blocked(scene, served):
    """The one source the view reads that jbus does not write: a scout's request, for its
    last `## Report` and the `Status:` line under it. Only `done` is reported: a last Report
    that says not done is said as not done, whatever an earlier one said. A Report with a gate
    in it still has its Status line, and a request that is not there is said as missing, never
    as none."""
    requested(
        scene,
        tea_tin=REQUEST.format(slug="tea-tin"),
        jam_tin=REPORTED.format(slug="jam-tin", status="done"),
        oat_tin=REPORTED.format(slug="oat-tin", status="blocked (the tin is welded shut)"),
        rye_tin=REPORTED.format(slug="rye-tin", status="not done") + "\n## Report\nStatus: done\n",
        kale_tin=REPORTED.format(slug="kale-tin", status="done")
        + "\n## Report\nStatus: not done\n",
        fig_tin=REQUEST.format(slug="fig-tin")
        + "\n## Report\nStatus: blocked\nAnswers:\n- half\n## Gate 2: open the tin?\n"
        + "Status: open\n",
    )
    scene.passed(
        20,
        threads=[
            out(f"scout: {slug}", "ended" if slug == "jam-tin" else "moving")
            for slug in (
                "tea-tin",
                "jam-tin",
                "oat-tin",
                "rye-tin",
                "kale-tin",
                "fig-tin",
                "no-tin",
            )
        ]
        + [out("crew: tea-tin")],
    )
    state = served.json("/state.json?project=demo")
    said = {(t["role"], t["slug"]): t.get("request") for t in state["threads"]}
    asks = "{}: what is in the {} tin"
    assert said == {
        ("scout", "tea-tin"): {
            "state": "researching",
            "status": "",
            "asks": asks.format("tea-tin", "tea-tin"),
        },
        ("scout", "jam-tin"): {
            "state": "reported",
            "status": "done",
            "asks": asks.format("jam-tin", "jam-tin"),
        },
        ("scout", "oat-tin"): {
            "state": "blocked",
            "status": "blocked (the tin is welded shut)",
            "asks": asks.format("oat-tin", "oat-tin"),
        },
        ("scout", "rye-tin"): {
            "state": "reported",
            "status": "done",
            "asks": asks.format("rye-tin", "rye-tin"),
        },
        ("scout", "kale-tin"): {
            "state": "not done",
            "status": "not done",
            "asks": asks.format("kale-tin", "kale-tin"),
        },
        ("scout", "fig-tin"): {
            "state": "blocked",
            "status": "blocked",
            "asks": asks.format("fig-tin", "fig-tin"),
        },
        ("scout", "no-tin"): {"state": "missing", "status": "", "asks": ""},
        ("crew", "tea-tin"): None,
    }
    assert {"name": "scouts/", "by": "server", "state": "ok"} in [
        {key: one[key] for key in ("name", "by", "state")} for one in state["sources"]
    ]


def test_a_thread_that_ended_before_the_users_day_began_is_not_of_today(scene, served):
    """The user's day starts at midnight in the user's zone: 04:00 UTC on this day."""
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar"),
            out("crew: oat-milk", "ended", "completed", minutes=60 * 15),
            out("crew: oat-bowl", "ended", "completed", minutes=60 * 17),
            out("review: oat-bowl", "waiting", minutes=60 * 17),
        ],
    )
    state = served.json("/state.json?project=demo")
    assert [(t["title"], t["out"], t["today"]) for t in state["threads"]] == [
        ("crew: jam-jar", True, True),
        ("crew: oat-milk", False, True),
        ("crew: oat-bowl", False, False),
        ("review: oat-bowl", True, True),
    ]


def test_the_stack_has_each_projects_threads_and_none_where_its_pass_left_no_list(
    tmp_path, monkeypatch
):
    scene = Scene(tmp_path, monkeypatch)
    stacked(scene)
    requested(scene, look=REQUEST.format(slug="look"))
    scene.passed(20, threads=[out("crew: jam-jar"), out("scout: look", "quiet", minutes=12)])
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    by = {one["name"]: one for one in stack["projects"]}
    assert by["demo"]["threads"] == demo["threads"]
    assert [(t["slug"], t["live"], t.get("request", {}).get("state")) for t in demo["threads"]] == [
        ("jam-jar", "moving", None),
        ("look", "quiet", "researching"),
    ]
    assert (by["larder"]["threads"], by["pantry"]["threads"]) == (None, None)
    assert by["demo"]["health"]["threads"] == 2


def test_a_pass_that_left_no_list_of_threads_is_a_blind_spot_and_no_count_of_none(scene, served):
    scene.passed(20, threads=None)
    state = served.json("/state.json?project=demo")
    assert state["threads"] is None
    assert {
        "line": "the threads that are out are not known: the last pass left no list of them",
        "open": "threads",
    } in state["blind"]


def test_a_launched_row_whose_thread_is_gone_and_wrote_nothing_is_lost(scene, served):
    gone = {"thread": "none", "launch": "launched"}
    scene.queue(
        [
            row("fig-gone", "launched", thread="mcp:1", value="lost", facts=gone),
            row("fig-new", "launched", thread="mcp:3"),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    said = found["fig-gone"]["state"]
    assert (said["kind"], said["name"]) == ("lost", "Lost")
    assert said["say"] == "its thread is gone and wrote nothing"
    assert (found["fig-gone"]["step"], found["fig-gone"]["who"]) == ("running", "user")
    assert found["fig-new"]["state"]["kind"] == "launching"


@pytest.mark.parametrize(
    ("minutes", "threads", "says"),
    [
        (10, [], "no reviewer has started"),
        (10, [out("crew: fig-read"), out("review: fig-other")], "no reviewer has started"),
        (9, [], "it has no review yet"),
        (40, [out("review: fig-read")], "it has no review yet"),
        (40, [out("review: fig-read, second pass", "ended", "completed")], "it has no review yet"),
        (40, None, "it has no review yet"),
        (40, [], "its review has no verdict"),
    ],
)
def test_a_pull_request_ten_minutes_on_review_with_no_reviewer_listed_says_so(
    scene, served, minutes, threads, says
):
    reason = says if says.startswith("it") else "it has no review yet"
    scene.queue([row("fig-read", "pr", pr="#31", why=f"wait: {reason}")])
    scene.merge_log(logged(minutes, "wait", 31, reason))
    scene.passed(20, threads=threads)
    task = tasks(served.json("/state.json?project=demo"))["fig-read"]
    assert (task["step"], task["state"]["say"]) == ("review", says)
    waits = "its crewmate to start a reviewer" if says.startswith("no reviewer") else "its reviewer"
    assert task["state"]["waits"] == waits


def test_many_requests_at_once_each_get_an_answer(served):
    answers = []

    def ask():
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{served.port}/state.json?project=demo"
            ) as answer:
                answers.append(answer.status)
        except urllib.error.URLError as error:
            answers.append(str(error))

    threads = [threading.Thread(target=ask) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert answers == [200] * 12


STARTS = """import sys
from jbus import cli, view
real = view.doors


def doors(port):
    made = real(port)
    made.check = 0.2
    return made


view.doors = doors
raise SystemExit(cli.main(["view", "--port", sys.argv[1]]))
"""


class Process:
    """The real server as a process of its own, `jbus view` over a copy of the packages it
    runs, with the check every 0.2 s where the server has it every `view.CHECK` seconds."""

    def __init__(self, scene):
        self.src, self.port = scene.root / "src", free_port()
        shutil.copytree(REPO / "src", self.src, ignore=shutil.ignore_patterns("__pycache__"))
        self.env = os.environ | {
            "PYTHONPATH": str(self.src),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(scene.root),
            "JBUS_STATE_DIR": str(scene.state_dir),
            "JBUS_HOME_DIR": str(scene.home_dir),
        }
        self.run = None

    def start(self):
        self.run = subprocess.Popen(
            [sys.executable, "-c", STARTS, str(self.port)],
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.until(lambda: self.ask("/healthz") == {"ok": True})

    def ask(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as said:
                return json.loads(said.read())
        except (OSError, ValueError):
            return None

    def code(self):
        return (self.ask("/state.json?project=demo") or {}).get("jbus", {}).get("code", {})

    def until(self, holds, seconds=20):
        end = time.monotonic() + seconds
        while not holds():
            assert time.monotonic() < end, "the server did not get there in time"
            assert self.run.poll() is None, f"the server ended with {self.run.returncode}"
            time.sleep(0.05)

    def stop(self):
        if self.run and self.run.poll() is None:
            self.run.kill()
            self.run.wait()


@pytest.fixture
def process(scene):
    made = Process(scene)
    yield made
    made.stop()


def test_the_state_says_when_the_server_started_and_that_its_code_is_as_on_disk(served):
    before = datetime.now(UTC)
    code = served.json("/state.json?project=demo")["jbus"]["code"]
    assert sorted(code) == ["error", "stale", "started"]
    assert (code["stale"], code["error"]) == (False, "")
    assert datetime.fromisoformat(code["started"]) <= before


def test_a_file_the_server_runs_that_is_newer_on_disk_is_said(scene, tmp_path):
    loaded, beside = tmp_path / "pkg" / "loaded.py", tmp_path / "pkg" / "beside.txt"
    loaded.parent.mkdir()
    for file in (loaded, beside):
        file.write_text("")
    code = view.Code(root=tmp_path, beside=loaded.parent, loaded=lambda: [str(loaded), "/else.py"])
    assert code.said()["stale"] is False
    later = time.time() + 5
    os.utime(beside, (later, later))
    assert code.said()["stale"] is True
    os.utime(beside, (1, 1))
    assert code.said()["stale"] is False
    os.utime(loaded, (later, later))
    assert code.said()["stale"] is True
    loaded.unlink()
    assert code.said()["stale"] is True


def test_the_server_ends_with_status_0_when_its_code_changes_and_starts_again(process):
    process.start()
    assert process.code()["stale"] is False
    (process.src / "jbus" / "view" / "state.py").touch()
    assert process.run.wait(timeout=20) == 0
    process.start()
    assert process.ask("/healthz") == {"ok": True}
    assert process.code()["stale"] is False


@pytest.mark.parametrize("broken", ["view/clean.py", "word.py"])
def test_code_that_does_not_start_keeps_the_server_and_ends_it_once_it_starts(process, broken):
    process.start()
    module = process.src / "jbus" / broken
    whole = module.read_text()
    module.write_text("def (:\n")
    process.until(lambda: process.code().get("error"))
    code = process.code()
    assert code["stale"] is True
    assert code["error"] == "the code on disk does not start: SyntaxError: invalid syntax"
    time.sleep(1)
    assert process.run.poll() is None
    assert process.ask("/healthz") == {"ok": True}
    module.write_text(whole)
    assert process.run.wait(timeout=20) == 0


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.TimeoutExpired("python", 60),
        FileNotFoundError(2, "No such file or directory"),
        subprocess.CompletedProcess([], 1, "", "ModuleNotFoundError: No module named 'new'\n"),
        subprocess.CompletedProcess([], -9, "", ""),
    ],
)
def test_code_that_did_not_start_is_tried_again_at_the_next_check(tmp_path, monkeypatch, outcome):
    loaded = tmp_path / "loaded.py"
    loaded.write_text("")
    code = view.Code(root=tmp_path, beside=tmp_path, loaded=lambda: [str(loaded)])
    later = time.time() + 5
    os.utime(loaded, (later, later))
    outcomes = [outcome, subprocess.CompletedProcess([], 0, "", "")]

    def run(*args, **kwargs):
        one = outcomes.pop(0)
        if isinstance(one, Exception):
            raise one
        return one

    monkeypatch.setattr(subprocess, "run", run)
    assert code.due() is False
    assert code.said()["error"].startswith("the code on disk does not start: ")
    assert code.due() is True
    assert code.said()["error"] == ""


def test_the_unit_restarts_on_failure_and_depends_on_no_unit_of_jbus():
    import configparser

    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.read(REPO / "templates" / "jbus-view.service")
    assert unit["Service"]["Restart"] == "always"
    assert unit["Service"]["ExecStart"] == "%h/.local/bin/jbus view"
    assert unit["Install"]["WantedBy"] == "default.target"
    named = " ".join(
        f"{key}={value}" for part in unit.sections() for key, value in unit[part].items()
    )
    assert "jbus.timer" not in named and "jbus.service" not in named
    for key in ("After", "Requires", "Wants", "BindsTo", "PartOf", "OnFailure"):
        assert key.lower() not in {name.lower() for name in unit["Unit"]}, key


PANELS = ["blind", "bus", "checks", "flow", "merged", "pulse", "room", "rounds", "steps", "task"]
PANELS.append("threads")
PANELS.append("you")
POLICY = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
BEFORE = "edd7c43d"
SAMPLE = '''"""A sample panel: the lines of one file of its own, asked for when its drawer opens."""

from jbus.view.state import kept

SHAPE = {"count": None, "lines": [None]}
SOURCES = (kept("sample.json", lambda read: read.table("sample.json")),)


def build(read):
    lines = (read.table("sample.json") or {}).get("lines", [])
    return {"count": len(lines), "lines": lines, "more": "a key its shape does not have"}
'''
DRAWN = """function drawn(arg, d) {
  var lines = d.lines.map(function (l) { return "<li>" + esc(l) + "</li>"; }).join("");
  return head("Sample", d.count + " sample lines") + '<ul class="clean rows">' + lines + "</ul>";
}
"""
LINKED = (
    DRAWN
    + """panel({
  title: "Sample",
  drawer: drawn,
  adds: {
    task: function (t) {
      return "a sample line of " + esc(t.slug) + " " + openBtn("sample", "the sample");
    },
    you: function () { return { n: 1, label: "sample" }; }
  }
});
"""
)


def folder(process, name, script=LINKED, data=SAMPLE):
    """Add a panel to the copy of the package: one folder with the two files."""
    made = process.src / "jbus" / "view" / "panels" / name
    made.mkdir()
    (made / "panel.py").write_text(data)
    (made / "panel.js").write_text(script)
    return made


def differs(copy, real=REPO / "src"):
    """Each file of the copy that the checkout does not have as it is, from the copy's top."""
    found = []
    for path in sorted(copy.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        there = real / path.relative_to(copy)
        if not there.is_file() or there.read_bytes() != path.read_bytes():
            found.append(str(path.relative_to(copy)))
    return found


def test_a_panel_is_one_folder_of_two_files_and_the_rest_is_built_from_the_folders(served):
    folders = sorted(
        one.name for one in panels.HERE.iterdir() if one.is_dir() and one.name != "__pycache__"
    )
    assert set(PANELS) <= set(folders)
    for name in folders:
        files = sorted(one.name for one in (panels.HERE / name).iterdir())
        assert [one for one in files if one != "__pycache__"] == ["panel.js", "panel.py"], name
    found = panels.found()
    assert [panel.name for panel in found] == folders
    state = served.json("/state.json?project=demo")
    shaped = {key for panel in found if panel.first for key in panel.shape}
    assert set(state) == set(built.keys()) == {*built.FRAME, *shaped}
    first = [one for one in found if one.first]
    assert len(built.keys()) == len(built.FRAME) + sum(len(one.shape) for one in first)
    assert view.routes() == (*view.FIXED, *(f"/panel/{name}.json" for name in folders))
    named = {source.name for panel in found for source in panel.sources}
    assert {one["name"] for one in state["sources"]} == named
    assert {one["by"] for one in state["sources"]} == {"jbus", "server", "session"}
    frame = (panels.HERE.parent / "page.html").read_text()
    assert frame.count(view.MARK) == 1
    assert [name for name in folders if f'kind === "{name}"' in frame] == []
    _, _, page = served.ask("/")
    assert view.MARK not in page
    for panel in found:
        assert panel.script.read_text() in page, panel.name
        assert f'(panels("{panel.name}", {json.dumps(panel.first)}));' in page


def test_a_key_that_two_panels_give_is_refused():
    def panel(name, first, *keys):
        data = types.SimpleNamespace(FIRST=first, SHAPE=dict.fromkeys(keys))
        return panels.Panel(name, data, Path("panel.js"))

    with pytest.raises(ValueError, match="the panel one and the panel two both give the key a"):
        built.keys((panel("one", True, "a"), panel("two", True, "b", "a")))
    with pytest.raises(ValueError, match="the frame and the panel one both give the key repo"):
        built.keys((panel("one", True, "repo"),))
    asked = built.keys((panel("one", True, "a"), panel("two", False, "a", "repo")))
    assert asked == (*built.FRAME, "a")


def test_each_panel_answers_at_an_address_of_its_own_with_what_it_gives_the_state(served):
    state = served.json("/state.json?project=demo")
    for panel in panels.found():
        said = served.json(f"/panel/{panel.name}.json?project=demo")
        assert sorted(said) == ["at", "data", "panel", "sources"]
        assert (said["panel"], said["at"]) == (panel.name, state["at"])
        assert set(said["data"]) == set(panel.shape)
        live = {"room"} if panel.name == "room" else set()
        for key in set(panel.shape) - live:
            if panel.first:
                assert said["data"][key] == state[key], key
            else:
                assert key not in state, key
        names = {source.name for source in panel.sources}
        assert said["sources"] == [one for one in state["sources"] if one["name"] in names]
    for path in (
        "/panel/nothing.json?project=demo",
        "/panel/pulse",
        "/panel/pulse.json/x",
        "/panel/Pulse.json",
    ):
        assert served.ask(path)[0] == 404, path
    assert served.ask("/panel/pulse.json?project=nobody")[0] == 404
    assert served.json("/panel/pulse.json?project=demo")["panel"] == "pulse"


def test_the_policy_of_the_page_is_the_string_it_was_at_the_commit_before(served):
    """The page has every panel's script inline, so the policy allows no script from a server.
    `POLICY` here is the string of the commit `BEFORE`, copied, and that copy is the test. A
    checkout with no history, as a runner's, has no more. Where git has the commit, the copy
    is held to the file as it was there."""
    assert view.POLICY == POLICY
    assert served.ask("/")[1]["Content-Security-Policy"] == POLICY
    was = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BEFORE}:src/jbus/view/__init__.py"],
        capture_output=True,
        text=True,
    )
    if was.returncode == 0:
        there = re.search(r"^POLICY = \(\n(.*?)\n\)$", was.stdout, re.S | re.M)
        assert "".join(line.strip().strip('"') for line in there[1].splitlines()) == POLICY


def raw(process, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{process.port}{path}", timeout=10) as said:
        return dict(said.headers), said.read().decode()


def test_a_folder_added_to_a_copy_of_the_package_is_a_panel_and_no_other_file_is_edited(
    scene, process
):
    folder(process, "sample")
    assert differs(process.src) == [
        "jbus/view/panels/sample/panel.js",
        "jbus/view/panels/sample/panel.py",
    ]
    scene.write("sample.json", {"lines": ["one", f"see {LINKS[0]}"]})
    process.start()
    said = process.ask("/panel/sample.json?project=demo")
    assert (said["panel"], said["data"]) == ("sample", {"count": 2, "lines": ["one", "see [link]"]})
    assert [(one["name"], one["by"], one["state"]) for one in said["sources"]] == [
        ("sample.json", "jbus", "ok")
    ]
    state = process.ask("/state.json?project=demo")
    assert "count" not in state and "lines" not in state
    assert state["sources"][-1]["name"] == "sample.json"
    assert [one for one in state["blind"] if "sample" in one["line"]] == []
    headers, page = raw(process, "/")
    assert headers["Content-Security-Policy"] == POLICY
    assert LINKED in page and '(panels("sample", false));' in page
    script = process.src / "jbus" / "view" / "panels" / "sample" / "panel.js"
    script.write_text(LINKED.replace('"Sample"', '"A sample, edited"'))
    assert '"A sample, edited"' in raw(process, "/")[1]
    assert process.run.poll() is None and process.code()["stale"] is False
    (scene.state / "sample.json").unlink()
    said = process.ask("/panel/sample.json?project=demo")
    assert said["data"] == {"count": 0, "lines": []}
    assert [one["state"] for one in said["sources"]] == ["missing"]
    spot = {"line": "sample.json could not be read", "open": "sample"}
    assert spot in process.ask("/state.json?project=demo")["blind"]


def test_a_folder_added_under_a_running_server_is_served_once_it_loads(scene, process):
    """The server loads its panels when it starts. A folder added later is code on disk that
    is newer: one that does not load keeps the server as it is, which says so, and one that
    loads ends it, for the start that serves it."""
    process.start()
    made = folder(process, "sample", data="raise ValueError('a panel that does not load')\n")
    process.until(lambda: process.code().get("error"))
    assert process.code()["error"].startswith("the code on disk does not start: ValueError")
    assert process.ask("/panel/sample.json?project=demo") is None
    assert process.ask("/panel/pulse.json?project=demo")["panel"] == "pulse"
    assert "sample" not in raw(process, "/")[1]
    (made / "panel.py").write_text(SAMPLE)
    assert process.run.wait(timeout=20) == 0
    process.start()
    assert process.ask("/panel/sample.json?project=demo")["panel"] == "sample"


def test_a_panel_asked_for_by_itself_looks_at_its_own_sources_and_no_other(scene, served):
    scene.script("systemctl", f"echo asked >> {scene.root}/systemctl.calls\n")
    served.json("/panel/merged.json?project=demo")
    assert not (scene.root / "systemctl.calls").exists()
    assert scene.asked() == []
    served.json("/panel/pulse.json?project=demo")
    assert (scene.root / "systemctl.calls").exists()


def test_a_folder_whose_second_file_is_written_after_the_first_is_still_served(scene, process):
    """A folder is a panel once it holds both files. A check that sees the first alone
    keeps the server as it is, and the second file ends it, for the start that serves it."""
    process.start()
    made = process.src / "jbus" / "view" / "panels" / "sample"
    made.mkdir()
    (made / "panel.py").write_text(SAMPLE)
    time.sleep(1)
    assert process.run.poll() is None
    assert process.ask("/panel/sample.json?project=demo") is None
    assert process.code()["stale"] is False
    (made / "panel.js").write_text(LINKED)
    assert process.run.wait(timeout=20) == 0
    process.start()
    assert process.ask("/panel/sample.json?project=demo")["panel"] == "sample"
    assert process.code()["stale"] is False


ROUNDED = """# oat-milk: a made-up task
Task: a task
Review: review

## Result
Status: done
Branch: oat-milk, {pull}
Reviewer: mcp:0001
Woke on the review's findings: fixed two.
Woken by the check passing.
Finding: fixed, one
Finding: not fixed, two, because three
Fixed: {fixed}
Second pass: needed since {first}, the fix changed more than the findings named
Scoped review: needed since {first}, the fix changed src/a.py
Scoped reviewer: mcp:0002, of {fixed}
Scoped review: none, nothing was pushed for the findings
Rebase: patch unchanged, before {first}, head {fixed}
Woke: a message from jbus.
Not a wake: Woke in the middle of a line counts for nothing.

## Review
Verdict: findings
Head: {first}   Unchanged by the review: yes
Findings:
- warning src/a.py:1 one
- info src/a.py:2 two
Dropped: 0

## Review
Verdict: clean
Head: {fixed}
Second pass: of the whole diff, as the last line says
Findings:
- none
"""


def rounded(scene, slug="oat-milk"):
    """A brief with two reviews in the home, and a `review` event for the first only."""
    first, fixed = "1a" * 20, "2b" * 20
    brief = ROUNDED.format(pull=PULL.format(13), first=first, fixed=fixed)
    (scene.home / "tasks").mkdir(exist_ok=True)
    (scene.home / "tasks" / f"{slug}.md").write_text(brief)
    review = brief.split("## Review")[1]
    scene.lines(
        "events.jsonl",
        [
            {
                "at": iso(ago(minutes=20)),
                "event": "review",
                "id": "00000000000000aa",
                "line": f"review {slug}: findings",
                "loud": "chef",
                "slug": slug,
                "text": "## Review" + review,
            }
        ],
    )
    return brief, first, fixed


def test_the_rounds_of_a_brief_are_its_review_sections_as_jmerge_reads_them(scene, served):
    brief, first, fixed = rounded(scene)
    said = {one["slug"]: one for one in served.json("/state.json?project=demo")["rounds"]}
    assert said["oat-milk"] == {
        "slug": "oat-milk",
        "read": True,
        "why": "",
        "reviews": [
            {"verdict": "findings", "head": first, "findings": 2, "at": iso(ago(minutes=20))},
            {"verdict": "clean", "head": fixed, "findings": 0, "at": None},
        ],
        "second": True,
        "scoped": True,
        "woke": 3,
        "rebases": 1,
    }
    merged = ready.said_of(brief)
    assert [(one.verdict, one.head, one.found) for one in merged.rounds] == [
        (one["verdict"], one["head"], one["findings"]) for one in said["oat-milk"]["reviews"]
    ]
    assert merged.found == 2 and merged.reviewed == fixed and merged.verdict == "clean"
    assert (
        served.json("/panel/rounds.json?project=demo")["data"]["rounds"]
        == served.json("/state.json?project=demo")["rounds"]
    )


def test_a_brief_that_cannot_be_read_says_so_and_counts_nothing(scene, served):
    rounded(scene, "oat-bowl")
    (scene.home / "tasks" / "oat-bowl.md").chmod(0)
    said = {one["slug"]: one for one in served.json("/state.json?project=demo")["rounds"]}
    if os.access(scene.home / "tasks" / "oat-bowl.md", os.R_OK):
        pytest.skip("this user reads a file of mode 0")
    assert said["oat-bowl"] == {
        "slug": "oat-bowl",
        "read": False,
        "why": "its brief could not be read: Permission denied",
        "reviews": [],
    }
    assert said["oat-milk"] == {
        "slug": "oat-milk",
        "read": False,
        "why": "it has no brief in its home or in jbus's copies",
        "reviews": [],
    }


def test_the_checks_list_each_runner_and_a_stopped_one_is_no_blind_spot(scene, served):
    scene.runners(
        ("actions-runner-a.service", "active", "running"),
        ("actions-runner-b.service", "inactive", "dead"),
    )
    state = served.json("/state.json?project=demo")
    assert state["checks"]["runners"] == [
        {"unit": "actions-runner-a.service", "active": "active", "sub": "running"},
        {"unit": "actions-runner-b.service", "active": "inactive", "sub": "dead"},
    ]
    assert state["checks"]["runners_read"] is True
    assert [one for one in state["blind"] if "runner" in one["line"]] == []
    listed = {one["name"]: one for one in state["sources"]}["runner units"]
    assert (listed["by"], listed["state"]) == ("server", "ok")
    calls = (scene.root / "systemctl.calls").read_text().splitlines()
    assert calls and set(calls) == {
        "--user list-units actions-runner-* --all --output=json --no-pager"
    }


def a_noticed(scene, *made):
    """Records of `noticed.json`, each `(slug, mark, minutes ago, more)`, as a pass and the
    two marks write them."""
    records = []
    for slug, mark, minutes, more in made:
        said = f"{slug} saw a thing"
        records.append(
            {
                "key": noticed.key(slug, said),
                "slug": slug,
                "kind": "tasks",
                "section": "Result",
                "label": "Noticed",
                "text": said,
                "seen_at": iso(ago(minutes=minutes)),
                "mark": mark,
                "row": "",
                "why": "",
                "by": "",
                "at": "",
                **more,
            }
        )
    scene.write(noticed.NAME, {"records": records})
    return [one["key"] for one in records]


def test_the_noticed_panel_lists_each_line_newest_first_with_its_mark(scene, served):
    old, taken, fresh = a_noticed(
        scene,
        ("tea-tray", "dropped", 300, {"why": "from before the list", "by": "jbus"}),
        ("jam-jar", "taken", 60, {"row": "fix-jar", "by": "home", "at": "2026-10-12 10:58 ET"}),
        ("oat-milk", "new", 5, {}),
    )
    said = served.json("/state.json?project=demo")["noticed"]
    assert [one["key"] for one in said] == [fresh, taken, old]
    assert {key: said[1][key] for key in ("slug", "mark", "row", "by", "seen_at", "text")} == {
        "slug": "jam-jar",
        "mark": "taken",
        "row": "fix-jar",
        "by": "home",
        "seen_at": iso(ago(minutes=60)),
        "text": "jam-jar saw a thing",
    }
    assert said[2]["why"] == "from before the list"
    assert served.json("/state.json?project=demo")["noticed_older"] == 0
    assert served.json("/panel/noticed.json?project=demo")["data"] == {
        "noticed": said,
        "noticed_older": 0,
    }
    many = [(f"old-{n:02}", "dropped", 500 + n, {"why": "from before the list"}) for n in range(30)]
    a_noticed(scene, ("oat-milk", "new", 5, {}), *many)
    state = served.json("/state.json?project=demo")
    assert [one["slug"] for one in state["noticed"]] == [
        "oat-milk",
        *(f"old-{n:02}" for n in range(20)),
    ]
    assert state["noticed_older"] == 10
    (scene.state / noticed.NAME).write_text("{not json")
    state = served.json("/state.json?project=demo")
    assert state["noticed"] == []
    assert {one["name"]: one["state"] for one in state["sources"]}[noticed.NAME] == "unreadable"
