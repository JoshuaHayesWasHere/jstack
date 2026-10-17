"""The kitchen every jbus test runs in: one project with jbus set up for it, against a T3
Code server, a `gh`, a `jmerge`, a `notify-send` and a webhook that are faked. The server and
the webhook listen on a local port, the three commands are functions here, and scripts on
PATH for another process. Nothing reaches the network. The tests here are of the fakes: each
says the same called here and started as a command.
"""

import base64
import contextlib
import hashlib
import http.server
import inspect
import io
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
import traceback
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import jbus
from jbriefs import meaning
from jbus import cli, live, queue, t3, wake, word
from test_room import BIN, FRESH, IDLE, machine

REPO = Path(__file__).parent.parent
FIXTURE = json.loads((REPO / "tests/fixtures/t3/jbus-mcp.json").read_text())
NOW = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
KEY = "a-key-for-the-test"
TOKEN = "a-token-for-the-test"
PROJECT = "11111111-2222-3333-4444-555555555555"
READ = ("runs", "activeRunId", "pendingRequestCount", "read_items", "selection")
SELECTION = {
    "instanceId": "claudeAgent",
    "model": "claude-sonnet-5-5",
    "options": [{"id": "effort", "value": "high"}, {"id": "fastMode", "value": True}],
}
SAID, SAID_AT, RAN = "said-by-user", "2026-10-11 17:58 ET", "2026-10-12 11:00 ET"
SESSION = "a-home-session"
GO = f"his word, {SAID_AT} (time typed); run {RAN} by the demo home"


def iso(moment):
    return moment.isoformat().replace("+00:00", "Z")


class Server:
    """A local HTTP server on a free port, answering with `self.answer`."""

    def __init__(self):
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                owner.answer(self, b"")

            def do_POST(self):
                owner.answer(self, self.rfile.read(int(self.headers.get("content-length", 0))))

            def log_message(self, *_):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    @staticmethod
    def reply(handler, body, status=200, headers=()):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        handler.send_response(status)
        for name, value in (("content-type", "application/json"), *headers):
            handler.send_header(name, value)
        handler.send_header("content-length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)


class Webhook(Server):
    def __init__(self):
        self.posts, self.keys, self.sleep, self.status = [], [], 0, 200
        self.said, self.bodies = [], []
        super().__init__()

    def answer(self, handler, body):
        time.sleep(self.sleep)
        if self.status != 200:
            return self.reply(handler, {}, self.status)
        self.keys.append(handler.headers.get(wake.HEADER))
        taken = json.loads(body)
        self.bodies.append(taken)
        self.posts.append(taken.get("events"))
        self.said.append(taken["say"])
        self.reply(handler, {})


class T3(Server):
    """T3 Code's MCP endpoint and its sign-in, with the eight tools jbus calls."""

    def __init__(self):
        self.threads, self.launches, self.calls, self.lose, self.refuse = [], [], [], None, ""
        self.messages, self.refuse_send, self.lose_send = {}, False, False
        self.status, self.on_list, self.down, self.lose_read = 200, None, set(), False
        self.challenges, self.registered, self.at_work = {}, [], set()
        self.said = {}
        super().__init__()

    def thread(
        self,
        slug,
        status="running",
        *,
        age=timedelta(minutes=5),
        idle=None,
        project=PROJECT,
        **more,
    ):
        made = {
            "threadId": f"mcp:thread-{len(self.threads) + 1}",
            "projectId": project,
            "title": f"crew: {slug}",
            "status": status,
            "settled": False,
            "branch": slug,
            "createdAt": iso(NOW - age),
            "updatedAt": iso(NOW - (idle if idle is not None else timedelta(minutes=1))),
            **more,
        }
        if idle is None:
            self.at_work.add(made["threadId"])
        self.threads.append(made)
        return made

    def says(self, thread, message, text, **more):
        """A message of a thread, as T3 Code gives one read by its id: the user's own, typed
        in the app, unless `more` says another."""
        self.said[thread, message] = {
            "itemId": f"turn-item:message:{urllib.parse.quote(message, safe='')}",
            "messageId": message,
            "createdBy": "user",
            "creationSource": "web",
            "type": "user_message",
            "text": text,
            "updatedAt": iso(NOW - timedelta(minutes=30)),
            "title": "home: demo",
            **more,
        }

    def write(self, now):
        """A thread made with no `idle` is at work: while a turn of it is under way, it
        wrote a minute ago."""
        for thread in self.threads:
            if thread["threadId"] in self.at_work and thread["status"] in live.TURNING:
                thread["updatedAt"] = max(thread["updatedAt"], iso(now - timedelta(minutes=1)))

    def answer(self, handler, body):
        url = urllib.parse.urlsplit(handler.path)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if url.path == "/.well-known/oauth-authorization-server":
            meta = FIXTURE["authorization_server"]
            ends = {
                k: self.url + urllib.parse.urlsplit(v).path
                for k, v in meta.items()
                if k.endswith("_endpoint")
            }
            return self.reply(handler, {**meta, **ends})
        if url.path == "/oauth/mcp/register":
            self.registered.append(json.loads(body))
            return self.reply(handler, {**self.registered[-1], "client_id": "a-client"}, 201)
        if url.path == "/oauth/mcp/authorize":
            self.challenges["a-code"] = query["code_challenge"]
            back = urllib.parse.urlencode({"code": "a-code", "state": query["state"]})
            return self.reply(handler, b"", 302, [("location", f"{query['redirect_uri']}?{back}")])
        if url.path == "/oauth/mcp/token":
            form = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode()).items()}
            proof = hashlib.sha256(form["code_verifier"].encode()).digest()
            if (
                base64.urlsafe_b64encode(proof).rstrip(b"=").decode()
                != self.challenges[form["code"]]
            ):
                return self.reply(handler, {"error": "invalid_grant"}, 400)
            given = {**FIXTURE["token_response"], "access_token": TOKEN}
            return self.reply(handler, given)
        if handler.headers.get("authorization") != f"Bearer {TOKEN}":
            return self.reply(handler, {"error": "invalid_mcp_credential"}, 401)
        asked = json.loads(body)
        if "id" not in asked:
            return self.reply(handler, b"", 202)
        if self.status != 200 and asked.get("params", {}).get("name") == "t3_thread_launch":
            self.launches.append(asked["params"]["arguments"])
            return self.reply(handler, {"error": "the server fell over"}, self.status)
        result = self.result(asked)
        if result is None:
            handler.close_connection = True
            return handler.connection.shutdown(2)
        said = {"jsonrpc": "2.0", "id": asked["id"], "result": result}
        self.reply(handler, said, headers=[("mcp-session-id", "a-session")])

    def result(self, asked):
        if asked["method"] == "initialize":
            return {"protocolVersion": t3.PROTOCOL, "capabilities": {}, "serverInfo": {}}
        if asked["method"] == "tools/list":
            return {"tools": [*FIXTURE["tools"], {"name": "t3_thread_update", "inputSchema": {}}]}
        tool, given = asked["params"]["name"], asked["params"]["arguments"]
        self.calls.append((tool, given))
        if tool == "t3_thread_list":
            if self.on_list:
                self.on_list()
            if given["projectId"] in self.down:
                return None
            found = [t for t in self.threads if t.get("projectId", PROJECT) == given["projectId"]]
            found = [t for t in found if given.get("titleContains", "") in t["title"]]
            if given.get("settled") is not None:
                found = [t for t in found if t["settled"] == given["settled"]]
            if not given.get("includeSubagents"):
                found = [t for t in found if not t.get("parentThreadId")]
            listed = [
                {k: v for k, v in t.items() if k not in ("branch", "projectId", *READ)}
                for t in found
            ]
            made = {"projectId": given["projectId"], "threads": listed, "nextCursor": None}
        elif tool == "t3_thread_read":
            if self.lose_read:
                return None
            if given.get("itemId"):
                found = [
                    one
                    for (thread, _), one in self.said.items()
                    if (thread, one["itemId"]) == (given["threadId"], given["itemId"])
                ]
                if not any(thread == given["threadId"] for thread, _ in self.said):
                    return {"isError": True, "content": [{"type": "text", "text": "no thread"}]}
                start, cap = given.get("textOffset") or 0, given["maxCharsPerItem"]
                items = [
                    {
                        **{k: v for k, v in one.items() if k != "title"},
                        "text": one["text"][start : start + cap],
                        "nextTextOffset": start + cap if len(one["text"]) > start + cap else None,
                    }
                    for one in found
                ]
                title = next(
                    one["title"] for (t, _), one in self.said.items() if t == given["threadId"]
                )
                made = {"thread": {"threadId": given["threadId"], "title": title}, "items": items}
                return {"structuredContent": made, "content": []}
            (thread,) = [t for t in self.threads if t["threadId"] == given["threadId"]]
            said = {k: v for k, v in thread.items() if k != "runs"}
            made = {
                "thread": said,
                "recentRuns": thread.get("runs", []),
                "items": thread.get("read_items", []),
            }
        elif tool == "t3_thread_send":
            if self.lose_send:
                return None
            if self.refuse_send:
                return {"isError": True, "content": [{"type": "text", "text": "no"}]}
            self.messages.setdefault(given["clientRequestId"], given)
            for thread in self.threads:
                if thread["threadId"] == given["threadId"]:
                    thread["updatedAt"] = iso(datetime.now(UTC))
            made = {"threadId": given["threadId"], "status": "queued"}
        elif tool == "t3_thread_configuration":
            (thread,) = [t for t in self.threads if t["threadId"] == given["threadId"]]
            made = {
                "threadId": given["threadId"],
                "modelSelection": thread.get("selection") or SELECTION,
                "runtimeMode": "full-access",
            }
        elif tool == "t3_thread_configure":
            (thread,) = [t for t in self.threads if t["threadId"] == given["threadId"]]
            thread["selection"] = given["modelSelection"]
            made = {"threadId": given["threadId"], "modelSelection": given["modelSelection"]}
        elif tool == "link_pull_request":
            made = {"url": given["url"], "alreadyLinked": False}
        elif tool == "t3_thread_organize":
            (thread,) = [t for t in self.threads if t["threadId"] == given["threadId"]]
            if given["action"] == "archive":
                thread["archived"] = True
            else:
                thread["settled"] = given["action"] == "settle"
            made = {}
        else:
            self.launches.append(given)
            if self.refuse:
                return {"isError": True, "content": [{"type": "text", "text": self.refuse}]}
            if self.lose == "before":
                return None
            slug = given["title"].removeprefix("crew: ")
            thread = self.thread(slug, "preparing", project=given["projectId"])
            thread["branch"] = given["workspaceStrategy"]["branch"]
            if self.lose == "after":
                return None
            made = {"threadId": thread["threadId"]}
        return {"content": [{"type": "text", "text": json.dumps(made)}], "structuredContent": made}


def fake_gh(stub, args, cwd):
    """The `gh` of a kitchen, asked `args` in `cwd`: its exit code, stdout and stderr.

    `gh-down` is a GitHub that does not answer, and `gh-down-<checkout>` one that does not
    for that one project. A list is a window: a pull request marked `old` has fallen out of
    it, and `pr view` still finds it by its number, or ends as the real command does for one
    it cannot resolve. `head-now.json` is a head pushed since the list was given: only a
    view shows it. `run rerun` starts a run again and says nothing, or with `gh-no-rerun`
    fails. `api` gives a commit's check runs, its runs for a push, who owns the repo (with no
    `repo.json`, GitHub does not say), the commits, and a pull request's comments, line
    comments and reviews by the end of the path: asked for every page (`--paginate
    --slurp`), a list of pages, here two. A job is its own in `jobs.json`, by its id, and
    one step at the first attempt where it has none there, and its log is its own in
    `logs.json`, by its id, or not found. A commit asked for by its sha lists the files it
    changed, from `commit-files.json`.
    """
    with open(stub / "gh.log", "a") as log:
        log.write(" ".join(args) + "\n")
    if (stub / "gh-down").exists() or (stub / ("gh-down-" + cwd.name)).exists():
        return 1, "", ""
    if args[:2] == ["pr", "list"]:
        pulls = json.loads((stub / (args[args.index("--state") + 1] + ".json")).read_text())
        if "--head" in args:
            pulls = [p for p in pulls if p["headRefName"] == args[args.index("--head") + 1]]
        else:
            pulls = [p for p in pulls if not p.get("old")]
        said = json.dumps(pulls)
    elif args[:2] == ["pr", "view"]:
        every = [
            (state.upper(), p)
            for state in ("open", "merged")
            for p in json.loads((stub / (state + ".json")).read_text())
        ]
        found = [
            dict(p, state=state) for state, p in every if args[2] in (str(p["number"]), p["url"])
        ]
        if not found:
            return 1, "", "GraphQL: Could not resolve to a PullRequest with the number of 0.\n"
        pushed = stub / "head-now.json"
        now = json.loads(pushed.read_text()) if pushed.exists() else {}
        said = json.dumps(dict(found[0], **now.get(str(found[0]["number"]), {})))
    elif args[0] == "api" and "/check-runs" in args[1]:
        runs = json.loads((stub / "check-runs.json").read_text())
        said = json.dumps({"check_runs": runs.get(args[1].split("/")[-2], [])})
    elif args[0] == "api" and "/actions/runs?head_sha=" in args[1]:
        kept, sha = stub / "push-runs.json", args[1].split("head_sha=")[1].split("&")[0]
        pushed = json.loads(kept.read_text()) if kept.exists() else {}
        said = json.dumps(
            {"workflow_runs": pushed.get(sha, []) if "&event=push" in args[1] else []}
        )
    elif args[:2] == ["run", "rerun"]:
        if (stub / "gh-no-rerun").exists():
            return 1, "", "run cannot be rerun\n"
        said = ""
    elif args[0] == "api" and args[1] == "repos/{owner}/{repo}":
        said = (stub / "repo.json").read_text()
    elif args[0] == "api" and args[1].split("?")[0].endswith(("/comments", "/reviews")):
        kept, name = stub / "remarks.json", "/".join(args[1].split("?")[0].split("/")[-3:])
        if name.endswith("/reviews") and (stub / "gh-no-reviews").exists():
            return 1, "", ""
        said = (json.loads(kept.read_text()) if kept.exists() else {}).get(name, [])
        said = json.dumps([said[:1], said[1:]] if "--slurp" in args else said)
    elif args[0] == "api" and args[1].split("/")[-2] == "commits" and "?" not in args[1]:
        kept = stub / "commit-files.json"
        files = (json.loads(kept.read_text()) if kept.exists() else {}).get(args[1][-40:], [])
        said = json.dumps({"files": [{"filename": name} for name in files]})
    elif args[0] == "api" and args[1].endswith("/logs"):
        kept = stub / "logs.json"
        logs = json.loads(kept.read_text()) if kept.exists() else {}
        if args[1].split("/")[-2] not in logs:
            return 1, "", "gh: Not Found (HTTP 404)\n"
        said = logs[args[1].split("/")[-2]]
    elif args[0] == "api" and "/actions/jobs/" in args[1]:
        kept = stub / "jobs.json"
        job = (json.loads(kept.read_text()) if kept.exists() else {}).get(args[1].split("/")[-1])
        said = json.dumps(job or {"steps": [{"name": "make check"}], "run_attempt": 1})
    elif args[0] == "api":
        said = (stub / "commits.json").read_text()
    else:
        return 2, "", ""
    return 0, said + "\n", ""


def fake_jmerge(stub, args, cwd):
    """The `jmerge` of a kitchen, asked `args`: its exit code, stdout and stderr.

    `jmerge-dies` ends it as a `SystemExit` with a message ends the real command: the line
    on stderr, exit 1. An accept of a held pull request does nothing where the test wrote
    no `accept.txt`.
    """
    with open(stub / "jmerge.log", "a") as log:
        log.write(" ".join(args) + "\n")
    if args == ["--claims"]:
        if (stub / "claims-fail").exists():
            return 1, "", ""
        return 0, (stub / "claims.txt").read_text(), ""
    if (stub / "jmerge-dies").exists():
        return 1, "", (stub / "jmerge-dies").read_text() + "\n"
    if "--sweep" in args:
        return 0, (stub / "sweep.txt").read_text(), ""
    if "--accept" in args:
        said = stub / "accept.txt"
        return 0, said.read_text() if said.exists() else "", ""
    time.sleep(float((stub / "jmerge-sleep").read_text()))
    said = (stub / "jmerge.txt").read_text()
    if (stub / "jmerge-dies-late").exists():
        return 1, said, (stub / "jmerge-dies-late").read_text() + "\n"
    return 0, said, ""


def fake_notify(stub, args, cwd):
    """The `notify-send` of a kitchen: it keeps what it was asked to show."""
    with open(stub / "notify.log", "a") as log:
        log.write(" | ".join(args) + "\n")
    return 0, "", ""


FAKES = {"gh": fake_gh, "jmerge": fake_jmerge, "notify-send": fake_notify}
"""Each fake as a command on PATH is `SCRIPT`, for what starts it from another process: a
shell block of a skill, a `jbus` run as a command. It is the same function, alone."""


SCRIPT = """\
#!{python}
import json, sys, time
from pathlib import Path


{source}

code, out, err = {name}(Path({stub!r}), sys.argv[1:], Path.cwd())
sys.stdout.write(out)
sys.stderr.write(err)
sys.exit(code)
"""


def on_path(name):
    """The file a command's first word starts, found the way the system finds it."""
    if os.sep in name:
        return name
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if os.access(found := os.path.join(part, name), os.X_OK) and os.path.isfile(found):
            return found
    return ""


class Side:
    """A second project of a kitchen: its own checkout, state, `projectId` and webhook."""

    def __init__(self, kitchen, name):
        self.name, self.project, self.webhook = name, f"{name}-project-id", Webhook()
        self.checkout = kitchen.root / name
        self.home = kitchen.root / "home" / name
        self.state = kitchen.state_dir / name


class Kitchen:
    """One project with jbus set up for it: config, state, a main checkout, and the fakes.

    `second` adds another project to the same config, T3 Code server, `gh` and `jmerge`.
    """

    def __init__(self, tmp_path, monkeypatch):
        tmp_path.mkdir(exist_ok=True)
        self.root, self.t3, self.webhook = tmp_path, T3(), Webhook()
        self.stub = tmp_path / "stub"
        self.config_dir, self.state_dir = tmp_path / "config", tmp_path / "state"
        self.home = tmp_path / "home" / "demo"
        self.checkout = tmp_path / "demo"
        for made in (self.stub, self.config_dir, self.home / "tasks", self.home / "scouts"):
            made.mkdir(parents=True)
        self.state = self.state_dir / "demo"
        self.sides = []
        self.config()
        self.signed_in(timedelta(0))
        self.fakes = {}
        for name, fake in FAKES.items():
            script, text = (
                self.stub / name,
                SCRIPT.format(
                    python=sys.executable,
                    source=inspect.getsource(fake),
                    name=fake.__name__,
                    stub=str(self.stub),
                ),
            )
            script.write_text(text)
            script.chmod(0o755)
            self.fakes[str(script)] = fake, text
        self.started = subprocess.run
        monkeypatch.setattr(subprocess, "run", self.run)
        for name, text in (
            ("open.json", "[]"),
            ("merged.json", "[]"),
            ("commits.json", "[]"),
            ("check-runs.json", "{}"),
            ("claims.txt", ""),
            ("jmerge.txt", ""),
            ("sweep.txt", ""),
            ("jmerge-sleep", "0"),
        ):
            (self.stub / name).write_text(text)
        self.origin = tmp_path / "origin.git"
        self.repo(self.checkout, self.origin)
        path = (self.stub, tmp_path / "machine" / "stub", BIN, os.environ["PATH"])
        monkeypatch.setenv("PATH", os.pathsep.join(str(part) for part in path))
        monkeypatch.setenv("JBUS_CONFIG_DIR", str(self.config_dir))
        monkeypatch.setenv("JBUS_STATE_DIR", str(self.state_dir))
        monkeypatch.setenv("JBUS_HOME_DIR", str(tmp_path / "home"))
        monkeypatch.setenv("LAVISH_AXI_STATE_DIR", str(tmp_path / "lavish"))
        monkeypatch.chdir(self.checkout)
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION)
        monkeypatch.setattr(queue, "clock", lambda: NOW)
        self.monkeypatch = monkeypatch
        self.machine()

    def run(self, command, **how):
        """`subprocess.run` while the kitchen is there: one of its fakes is answered here.

        Starting a Python for each `gh` and `jmerge` of a pass was most of a test's time, so
        a command that PATH resolves to a fake as the kitchen wrote it is that fake's function,
        called. Anything else starts a process as before: `git`, a command that is missing,
        a fake a test wrote over or took off PATH, and a call that passes its own `env`,
        asks for `check`, or does not capture what is printed. A fake called here is not held
        to `timeout`, and one that ends on an exception ends as a Python does: the traceback
        on stderr, exit 1.
        """
        fake = None
        if isinstance(command, (list, tuple)) and how.get("capture_output"):
            if not how.keys() - {"capture_output", "cwd", "text", "timeout"}:
                path = on_path(str(command[0]))
                fake, written = self.fakes.get(path, (None, None))
                if fake and Path(path).read_text() != written:
                    fake = None
        if fake is None:
            return self.started(command, **how)
        try:
            code, out, err = fake(self.stub, list(command[1:]), Path(how.get("cwd") or Path.cwd()))
        except Exception:
            code, out, err = 1, "", traceback.format_exc()
        if not how.get("text"):
            out, err = out.encode(), err.encode()
        return subprocess.CompletedProcess(command, code, out, err)

    def machine(self, plan=FRESH, **readings):
        """The machine and the plan `jgauge room` reads: idle and under its limits, or as told."""
        env = machine(self.root / "machine", **{**IDLE, **readings}, plan=plan)
        self.monkeypatch.setenv("PROC", env["PROC"])
        self.monkeypatch.setenv("LIMITS", env["LIMITS"])
        self.monkeypatch.setenv("TMPFS", env["TMPFS"])
        return env["LIMITS"]

    def repo(self, checkout, origin):
        """A main checkout on `main`, with an origin that has that branch as its default."""
        self.git("init", "-q", "-b", "main", str(checkout), cwd=self.root)
        self.git("commit", "-q", "--allow-empty", "-m", "start", cwd=checkout)
        self.git("init", "-q", "--bare", "-b", "main", str(origin), cwd=self.root)
        self.git("remote", "add", "origin", str(origin), cwd=checkout)
        self.git("push", "-q", "origin", "main", cwd=checkout)
        self.git("fetch", "-q", "origin", cwd=checkout)
        self.git("remote", "set-head", "origin", "main", cwd=checkout)

    def second(self, name="other"):
        """Add a project to the config, after the ones it has. The answer is where it is.

        It writes the config with nothing else given, so `config` comes after it.
        """
        side = Side(self, name)
        (side.home / "tasks").mkdir(parents=True)
        self.repo(side.checkout, self.root / f"{name}-origin.git")
        self.sides.append(side)
        self.config()
        return side

    def close(self):
        self.t3.close()
        for webhook in (self.webhook, *(side.webhook for side in self.sides)):
            webhook.close()

    @staticmethod
    def write(path, text, mode=0o600):
        path.write_text(text)
        path.chmod(mode)

    def signed_in(self, ago, **token):
        """The token as `jbus t3 login` stores it, obtained `ago` before the tests' now."""
        stored = {
            "server": self.t3.url,
            "token": {"access_token": TOKEN, **token},
            "obtained_at": (NOW - ago).timestamp(),
        }
        self.write(self.config_dir / "t3.json", json.dumps(stored))

    def config(self, url=None, **top):
        top = {"dispatch": True, "max_running": 1, "runtimeMode": "full-access", **top}
        lines = [f"server = {json.dumps(self.t3.url)}"]
        for key, value in top.items():
            if isinstance(value, dict):
                value = "{ " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in value.items()) + " }"
                lines.append(f"{key} = {value}")
            else:
                lines.append(f"{key} = {json.dumps(value)}")
        lines += [
            "[[project]]",
            'name = "demo"',
            f"checkout = {json.dumps(str(self.checkout))}",
            'state = "demo"',
            f"projectId = {json.dumps(PROJECT)}",
            f"webhook_url = {json.dumps(self.webhook.url + '/wake' if url is None else url)}",
            f"webhook_key = {json.dumps(KEY)}",
        ]
        for side in self.sides:
            lines += [
                "[[project]]",
                f"name = {json.dumps(side.name)}",
                f"checkout = {json.dumps(str(side.checkout))}",
                f"projectId = {json.dumps(side.project)}",
                f"webhook_url = {json.dumps(side.webhook.url + '/wake')}",
                f"webhook_key = {json.dumps(KEY)}",
            ]
        self.write(self.config_dir / "config.toml", "\n".join(lines) + "\n")

    def git(self, *args, cwd=None):
        identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", *identity, *args], cwd=cwd or self.checkout, check=True)

    def set(self, name, value):
        (self.stub / name).write_text(value if isinstance(value, str) else json.dumps(value))

    def log(self, name):
        path = self.stub / f"{name}.log"
        return path.read_text().splitlines() if path.exists() else []

    def brief(self, slug, text="", kind="tasks"):
        path = self.home / kind / f"{slug}.md"
        path.write_text(f"# {slug}: a task\nWhere: `src/{slug}/`\n{text}")
        return path

    def lavish(self, **sessions):
        """What Lavish keeps of its sessions: each one's key, with its page and its status."""
        kept = {
            key: {"key": key, "file": str(file), "status": status, "pending_prompts": queued}
            for key, (file, status, *more) in sessions.items()
            for queued in [more[0] if more else 0]
        }
        (self.root / "lavish").mkdir(exist_ok=True)
        (self.root / "lavish" / "state.json").write_text(json.dumps({"sessions": kept}))

    def word(self, project="demo"):
        """The id of a word of the user's that the project keeps, typed and sent long ago: what
        a test's approval rests on."""
        state = self.state_dir / project
        if not any(one.id == SAID for one in word.load(state)):
            kept = word.Word(SAID, "go", "user", SAID_AT, iso(NOW), "mcp:a-home", iso(NOW))
            word._write(state, [*word.load(state), kept])
        return SAID

    def poll(self, now=NOW):
        self.t3.write(now)
        said = []
        assert cli.poll(jbus.load(), now, said.append) == 0
        return said

    def main(self, *argv, stdin=""):
        self.monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                code = cli.main(list(argv))
            except SystemExit as stopped:
                code = stopped.code
        return code, out.getvalue()

    def waiting(self):
        return jbus.read_json(self.state / "outbox.json", [])

    def marks(self):
        return jbus.read_json(self.state / "wake.json", {})

    def status(self):
        return json.loads((self.state_dir / "status.json").read_text())

    def events(self, kind=None):
        """Every event the project queued, oldest first, as the log has it: a quiet one is
        nowhere else."""
        every = wake.Box(self.state, jbus.load().project("demo")).log()
        return [e for e in every if kind is None or e["event"] == kind]

    def lines(self, kind=None):
        return [event["line"] for event in self.events(kind)]

    def forget(self):
        """Empty the outbox, the log and what the webhook got: what `events` gives starts here."""
        jbus.write_json(self.state / "outbox.json", [])
        (self.state / wake.LOG).unlink(missing_ok=True)
        self.webhook.posts.clear()

    def quiet(self):
        """A first pass, which records what is already so, and no event kept of it."""
        self.poll(NOW - timedelta(hours=1))
        self.forget()

    def merged(self, slug, number, sha, ago=timedelta(minutes=10), title=None):
        return {
            "number": number,
            "url": f"https://example.test/pull/{number}",
            "title": title or f"feat: {slug}",
            "headRefName": slug,
            "mergeCommit": {"oid": sha},
            "mergedAt": iso(NOW - ago),
        }

    def opened(self, slug, number, state="SUCCESS"):
        return {
            "number": number,
            "url": f"https://example.test/pull/{number}",
            "title": f"feat: {slug}",
            "headRefName": slug,
            "headRefOid": "c" * 40,
            "statusCheckRollup": [{"status": "COMPLETED", "conclusion": state}],
        }

    def commit(self, sha, message="a change", ago=timedelta(minutes=10)):
        return {"sha": sha, "commit": {"message": message, "committer": {"date": iso(NOW - ago)}}}


@pytest.mark.parametrize(
    ("command", "files"),
    [
        (["gh", "pr", "list", "--state", "open"], {}),
        (["gh", "pr", "list", "--state", "merged", "--head", "alpha"], {}),
        (["gh", "pr", "view", "7"], {}),
        (["gh", "pr", "view", "7"], {"head-now.json": '{"7": {"headRefOid": "d"}}'}),
        (["gh", "pr", "view", "0"], {}),
        (["gh", "api", "repos/o/r/commits/abc/check-runs"], {"check-runs.json": '{"abc": [1]}'}),
        (["gh", "api", "repos/{owner}/{repo}"], {}),
        (["gh", "api", "repos/o/r/pulls/7/reviews", "--slurp"], {}),
        (["gh", "api", "repos/o/r/commits"], {}),
        (["gh", "pr", "list", "--state", "open"], {"gh-down": ""}),
        (["gh", "something", "else"], {}),
        (["jmerge"], {"jmerge.txt": "wait 7 a line\n"}),
        (["jmerge"], {"jmerge.txt": "wait 7 a line\n", "jmerge-dies-late": "it ended"}),
        (["jmerge", "--claims"], {"claims.txt": "alpha src/a.py\n"}),
        (["jmerge", "--claims"], {"claims-fail": ""}),
        (["jmerge", "--sweep", "--check"], {"sweep.txt": "removable alpha\n"}),
        (["jmerge", "--sweep", "--check"], {"jmerge-dies": "jmerge: it broke"}),
        (["jmerge", "--accept", "7", "--check"], {}),
        (["notify-send", "jbus", "a line"], {}),
    ],
)
def test_a_fake_says_the_same_called_here_and_started_as_a_command(kitchen, command, files):
    """Of stderr the last line is compared: a traceback names the file it came from."""
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.set("merged.json", [kitchen.merged("alpha", 6, "a" * 40)])
    for name, text in files.items():
        kitchen.set(name, text)
    started = kitchen.started

    def never(*_, **__):
        raise AssertionError("the fake was started as a command")

    kitchen.monkeypatch.setattr(kitchen, "started", never)
    here = subprocess.run(command, cwd=kitchen.checkout, capture_output=True, text=True)
    there = started(command, cwd=kitchen.checkout, capture_output=True, text=True)
    assert (here.returncode, here.stdout, here.stderr.splitlines()[-1:]) == (
        there.returncode,
        there.stdout,
        there.stderr.splitlines()[-1:],
    )
    log = kitchen.log(command[0].removesuffix("-send"))
    assert len(log) == 2 and log[0] == log[1]


@pytest.mark.parametrize("down", ["gh-down-demo", "gh-down-other"])
@pytest.mark.parametrize("given", [True, False])
def test_a_fake_is_asked_in_the_directory_the_command_would_start_in(kitchen, down, given):
    """With no `cwd` given, that is the directory the test is in: the kitchen's checkout."""
    kitchen.set(down, "")
    how = {"cwd": kitchen.checkout} if given else {}
    command, started = ["gh", "pr", "list", "--state", "open"], kitchen.started
    kitchen.monkeypatch.setattr(kitchen, "started", None)
    here = subprocess.run(command, capture_output=True, text=True, **how)
    there = started(command, capture_output=True, text=True, **how)
    assert (here.returncode, here.stdout) == (there.returncode, there.stdout)
    assert here.returncode == (1 if down == "gh-down-demo" else 0)


def test_a_fake_asked_with_no_text_answers_in_bytes_as_the_command_does(kitchen):
    command, started = ["jmerge", "--sweep", "--check"], kitchen.started
    kitchen.set("jmerge-dies", "jmerge: it broke")
    kitchen.monkeypatch.setattr(kitchen, "started", None)
    here = subprocess.run(command, capture_output=True, timeout=5)
    there = started(command, capture_output=True, timeout=5)
    assert (here.returncode, here.stdout, here.stderr) == (1, b"", b"jmerge: it broke\n")
    assert (there.returncode, there.stdout, there.stderr) == (1, b"", b"jmerge: it broke\n")


@pytest.mark.parametrize("fake", FAKES.values())
def test_a_fake_uses_only_the_names_its_script_imports(fake):
    """The script is the function's source under `SCRIPT`'s imports, and nothing else."""

    def names(code):
        inner = [const for const in code.co_consts if inspect.iscode(const)]
        return set(code.co_names).union(*map(names, inner))

    imported = {"json", "sys", "time", "Path"}
    assert all(f"import {name}" in SCRIPT or f", {name}" in SCRIPT for name in imported)
    assert names(fake.__code__) & set(globals()) <= imported


def test_a_fake_a_test_wrote_over_or_took_off_path_is_started_as_a_command(kitchen):
    """Off PATH, the name is whatever the machine has: the kitchen hands it on."""
    (kitchen.stub / "gh").write_text("#!/bin/sh\necho its own\n")
    assert subprocess.run(["gh"], capture_output=True, text=True).stdout == "its own\n"
    (kitchen.stub / "jmerge").unlink()
    asked = []
    kitchen.monkeypatch.setattr(kitchen, "started", lambda command, **_: asked.append(command))
    subprocess.run(["jmerge"], capture_output=True, text=True)
    assert asked == [["jmerge"]]
    assert kitchen.log("gh") == [] and kitchen.log("jmerge") == []


RESULT = "\n## Result\nStatus: done\nBranch: alpha   Pull request: none\nLeft: none\n"
OPTIONS = (
    "Option: the first (default, recommended): nothing changes\nOption: the other: one thing more\n"
)
ASK = "## Gate <n>: which one?\nStatus: open\nDefault: the first\n" + OPTIONS


def complete(slug, more=""):
    """A brief with every field `jbus queue add` asks for, and `more` under them."""
    return (
        f'# {slug}: a task\nTask: "do {slug}"\nDone when:\n- it is done\n'
        f"Proves it: `make check`\nSize: S\nWhere: `src/{slug}/`\nDesign: none, a test\n"
        f"Pull request: open one when done\nReview: review\nPlaybook: feature\n{more}"
    )


def bound(kitchen, slug, project="demo"):
    """What an approval record holds of the brief stored now: its sha and its fingerprint."""
    text = (kitchen.state_dir / project / "briefs" / f"{slug}.md").read_text()
    made = jbus.queue.fingerprint(text)
    return {
        "brief_sha": jbus.queue.brief_sha(text),
        "scope": meaning.fingerprint(made),
        "meaning": made,
    }


def approved(kitchen, slug, priority=1):
    """A row of the queue with its brief, and the user's go for it."""
    text = complete(slug)
    assert kitchen.main("queue", "add", slug, "--priority", str(priority), stdin=text)[0] == 0
    assert go(kitchen, slug)[0] == 0


def go(kitchen, slug):
    sha = hashlib.sha256((kitchen.state / "briefs" / f"{slug}.md").read_bytes()).hexdigest()[:12]
    return kitchen.main("queue", "approve", slug, "--word", kitchen.word(), "--sha", sha)


GATE = textwrap.dedent("""\
    ## Gate {n}: {asked}
    Status: {status}
    Asked by: {slug}, thread mcp:a-thread
    Default: the first one
    Built on it: nothing
    Undo: pick the other
    Option: the first one (default, recommended): nothing changes
    Option: the other: one more cup
    """)


DAY = timedelta(days=1)
QUARTER_PAST_FIVE = datetime(2026, 10, 12, 21, 15, tzinfo=UTC)
PASS = timedelta(minutes=3)


def queued(kitchen, slug, text=None):
    """A row of the queue, approved, as the Chef adds one."""
    text = text or complete(slug)
    assert kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)[0] == 0
    sha = jbus.queue.brief_sha(text)[:12]
    go = ["queue", "approve", slug, "--word", kitchen.word(), "--sha", sha]
    assert kitchen.main(*go)[0] == 0


FOUND = "- warning src/alpha/a.py:3 the sum is off by one"


def review(verdict="findings", sent="not sent, no home", findings=FOUND):
    return (
        f"\n## Review\nVerdict: {verdict}\nHead: {'c' * 40}   Unchanged by the run: yes\n"
        f"Findings:\n{findings}\nDropped: 0\nSent to: {sent}\n"
    )


def sends(kitchen):
    return [given for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]


def settles(kitchen, action="settle"):
    return [
        given
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_organize" and given["action"] == action
    ]
