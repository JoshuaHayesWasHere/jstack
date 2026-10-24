"""`jbus view` is one server that reads what the passes left. It prints no secret, and its one write
is the user's answer to a question.

Each test starts the real server on a free port over a temporary state directory, and asks
it over HTTP as a browser would. `gh` and `systemctl` are stand-ins on `PATH` that write
down how the test called them. A test of an answer that is sent runs the server over a kitchen
of `test_jbus_kitchen`, whose T3 Code is a stand-in too. Nothing reaches the network, and every name
here is made up.
"""

import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import daemons
import jsettings
from jbus import leftover, merge, noticed, questions, queue, view, word, work
from jbus.view import state as built
from jmerge import ready
from test_jbus_kitchen import GATE as PIPED
from testing.paths import REPO, sources

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)


GITHUB = "github.com"


PULL = f"https://{GITHUB}/acme/demo/pull/{{}}"


RUN = f"https://{GITHUB}/acme/demo/actions/runs/{{}}"


LINKS = (
    "https://example.test/hooks/T0/B0/plantedpath",
    f"https://{GITHUB}/other/place/pull/7",
    "http://example.test:8443/wake?k=plantedquery",
)


OPAQUE = "plantedopaquewordsnobodyshouldsee"


ASKED = "gate:#4:" + hashlib.sha256(b"tea or coffee?").hexdigest()[:8]


UNREAD = ("outboxonlywords", "configonlywords", "tokenfileonlywords")


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
    """The value that a pass would have judged this row to have when it wrote the row. A test
    gets it where the test names no value."""
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
    """A line of `work.json` for a row, as `work.entry` writes one. Its holder comes from
    `work.holder`, and it has what `leftover.json` says of the row."""
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
    """A queue with every way a row waits: the three ways a queued row waits, and the pull
    requests that `jmerge` waits on or holds back."""
    lost = "2 of main's lines in src/a.py"
    dropped = f"wait: {ready.DROPPED.format(lost=lost, head='0123456789ab')}"
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
        monkeypatch.delenv("JBUS_VIEW_ORIGINS", raising=False)
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
        self.lines("ci.jsonl", [])
        self.lines("ci-prs.jsonl", [])
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
        """The table, and `work.json` beside it, as the pass that wrote the table judged it.
        Each row's `value`, `who` and `facts` are what the test gives, or else what `judged`
        gives."""
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
        """`pass.json` and the status file beside it, for a last pass that ended
        `seconds_ago` seconds ago. That pass saw these threads as out, and saw each row as
        given here."""
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
        state and its sub state. Where the test gives none, three units run, as on this
        machine."""
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
        (self.proc / "pressure" / "cpu").write_text(
            "some avg10=0.00 avg60=4.20 avg300=0.00 total=1\n"
        )
        resets = int(time.time()) + 3600
        (self.root / "limits").write_text(
            f"five_hour {five_hour} {resets}\nseven_day 22.0 {resets}\n"
        )

    def github(self, runs=None, **pull):
        """What the stand-in `gh` answers: the runs and the one pull request. Each run is
        `(branch, status, conclusion)`, oldest first, with the workflow's name after them
        where it is not `check`."""
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
    """The server, running on a free port, and what it answers."""

    def __init__(self, scene, host=None, names=(), retry=60.0, port=None, origins=()):
        self.port = port or free_port()
        self.doors = view.Doors(
            scene.app(), self.port, host=host, names=names, origins=origins, retry=retry
        )
        self.doors.open()

    def ask(self, path, method="GET", host=None, to="127.0.0.1", headers=None, body=None):
        link = http.client.HTTPConnection(to, self.port, timeout=10)
        try:
            named = f"127.0.0.1:{self.port}" if host is None else host
            link.request(method, path, body=body, headers={"Host": named, **(headers or {})})
            answer = link.getresponse()
            return answer.status, dict(answer.getheaders()), answer.read().decode(errors="replace")
        finally:
            link.close()

    def write(self, body, origin=None, path=None, **how):
        """A write to the one project of the state directory, made as the server's own page
        makes it. With an origin given, the write comes from that origin, and `""` is a
        request with no `Origin` header. The answer is its status and what it said."""
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


def tasks(state):
    return {one["slug"]: one for one in state["tasks"]}


def stacked(scene):
    """Beside `demo`, two small made-up projects of the state directory. `pantry` is in a
    repo of its own. It has one task running, one at a gate and one merged today, and it also
    has a gate it asks and a noticed line. `larder` has an empty queue. Beside them are a
    directory with no queue, which is no project, and a retired project. jbus no longer looks
    after the retired project, and the view never reads it."""
    pantry, larder = scene.state_dir / "pantry", scene.state_dir / "larder"
    for made in (pantry, larder, scene.home_dir / "pantry", scene.home_dir / "larder"):
        made.mkdir()
    (scene.state_dir / "launches").mkdir()
    retired = scene.root / "jbus-retired" / "attic"
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


def asks(scene, asked="tea or coffee?", slug="alpha"):
    """A question piped to jbus, with two options. The answer is its number."""
    lines = PIPED.format(n="<n>", asked=asked, status="open", slug=slug)
    return questions.ask(scene.state, scene.home, slug, lines, NOW)[0].number


def kept(state):
    """Each record of the questions file, by its number."""
    return {one.number: one for one in questions.read(state)}


PROXIED, PANTRY, EVIL, IPV6 = (
    "jbus.home.example.test",
    "pantry.example.test",
    "evil.example.test",
    "[::1]",
)


def said_by_him(scene, answer="coffee, please", sent="go ahead with the kettle"):
    """Two questions, one of them answered; a word sent on and one that waits; and a row the
    user approved on the word that was sent. That row is beside the table's rows, which have
    only a typed string."""
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
    and a pull request on every step. `fig-pip` is a row that is wrong: it is queued, but
    the pass judged it merged. `fig-stem` waits behind it. `fig-pod` and `fig-tree` are
    finished and leave nothing. The tests limit the page's first screen to its word budget
    for this scene, so `quiet`, `closed` and `unknown` have scenes of their own."""
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


def out(title, live="moving", status="running", minutes=1, **more):
    """One thread as a pass leaves it in `pass.json`, which the thread last wrote `minutes`
    minutes ago."""
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


REQUEST = '# {slug}: what is in the {slug} tin\nRequest: "look in the tin"\n'


REPORTED = REQUEST + "\n## Report\nStatus: {status}\nAnswers:\n- it holds tea\n"


def requested(scene, **files):
    """A request under the home's `scouts/` for each slug, as its text."""
    (scene.home / "scouts").mkdir(exist_ok=True)
    for slug, text in files.items():
        (scene.home / "scouts" / f"{slug.replace('_', '-')}.md").write_text(text)


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
    """The real server as a process of its own: `jbus view` over a copy of the packages it
    runs. This process checks its code every 0.2 s, where `jbus view` otherwise checks every
    `view.CHECK` seconds. What the server prints to stderr goes to `said`, and a wait that fails
    ends with its last lines.
    It copies each folder the packages are in (`testing.paths.sources`), and `src` is the copy
    that has `jbus`."""

    def __init__(self, scene):
        self.port = free_port()
        folders = [folder.relative_to(REPO) for folder in sources()]
        copies = [scene.root / folder for folder in folders]
        for folder, copy in zip(folders, copies, strict=True):
            shutil.copytree(REPO / folder, copy, ignore=shutil.ignore_patterns("__pycache__"))
        self.src = next(copy for copy in copies if (copy / "jbus").is_dir())
        self.env = os.environ | {
            "PYTHONPATH": os.pathsep.join(map(str, copies)),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(scene.root),
            "JBUS_STATE_DIR": str(scene.state_dir),
            "JBUS_HOME_DIR": str(scene.home_dir),
        }
        self.said = scene.root / "view.err"
        self.run = None

    def start(self):
        with self.said.open("a") as said:
            self.run = daemons.start(
                [sys.executable, "-c", STARTS, str(self.port)],
                env=self.env,
                stdout=subprocess.DEVNULL,
                stderr=said,
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

    def err(self):
        return self.said.read_text()[-2000:]

    def until(self, holds, seconds=20):
        end = time.monotonic() + seconds
        while not holds():
            assert time.monotonic() < end, f"the server did not get there in time:\n{self.err()}"
            assert self.run.poll() is None, (
                f"the server ended with {self.run.returncode}:\n{self.err()}"
            )
            time.sleep(0.05)

    def stop(self):
        if self.run:
            daemons.stop(self.run)


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


def a_noticed(scene, *made):
    """Records of `noticed.json`, each `(slug, mark, minutes ago, more)`, as a pass and the
    two mark commands write them."""
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


ROOT, SHELF, RACK, OLD = "", "pantry-shelf", "spice-rack", "old-shelf"
HOMES = {
    "tea-kettle": None,
    "tea-tray": OLD,
    "jam-jar": SHELF,
    "jam-lid": SHELF,
    "oat-milk": RACK,
    "oat-honey": "mcp:rack",
}


def homed(scene):
    """The scene's homes: the root's `home-id`, two child homes and a retired scope, and a
    brief for each slug of `HOMES` in the home's `tasks/`, with a `Home:` line where one is
    named. The child home `spice-rack` also has a gate with no default, which waits on the
    user, and a scout of its own."""
    (scene.home / "home-id").write_text("mcp:root\n")
    for name in (SHELF, RACK, OLD):
        (scene.home / name).mkdir()
    (scene.home / SHELF / "home-id").write_text("mcp:shelf\n")
    (scene.home / RACK / "home-id").write_text("mcp:rack\n")
    (scene.home / OLD / "handoff.md").write_text("Status: retired\n")
    gate = GATE.format(n=30, asked="which jar for the cloves?", status="open", default="")
    (scene.home / RACK / "gates.md").write_text(gate)
    for kind, slug, home in (
        *(("tasks", slug, home) for slug, home in HOMES.items()),
        ("scouts", "look", RACK),
    ):
        (scene.home / kind).mkdir(exist_ok=True)
        line = f"Home: {home}\n" if home else ""
        (scene.home / kind / f"{slug}.md").write_text(f"# {slug}: a made-up task\n{line}Task: x\n")
    scene.passed(
        20,
        threads=[
            out("crew: jam-jar"),
            out("review: oat-milk"),
            out("scout: look", "waiting"),
            out("crew: tea-cups"),
            out("home: demo", id="mcp:root"),
            out("home: demo pantry-shelf", id="mcp:shelf"),
            out("a thread he opened"),
        ],
    )
