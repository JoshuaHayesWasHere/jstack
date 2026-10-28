"""This module is the kitchen that every jbus test runs in: one project with jbus set up for it,
against fakes of a T3 Code server, `gh`, `jmerge` and `notify-send`. The server listens on a local
port, and keeps what each project's home thread was sent as wakes apart from its other messages
(`Wakes`). The three commands are functions
here, and scripts on PATH for another process. Nothing reaches the network.

The tests here test the fakes: each fake says the same whether this module calls it or a process
starts it as a command. One test sends through the fakes into a capped thread, and sees
`jbus.outbox` hold the message. The last test is of the repo that each kitchen copies from its
worker's template: a kitchen pushes to its own origin, and the template stays as the build left it.
"""

import base64
import contextlib
import fcntl
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
import repo_template
from jbriefs import meaning
from jbus import cli, live, queue, t3, wake, word
from jgauge import slot, waiters
from jroles import ledger
from repo_template import IDENTITY
from test_room import BIN, FRESH, IDLE, machine
from testing.paths import REPO

FIXTURE = json.loads((REPO / "features/jbus/tests/fixtures/t3/jbus-mcp.json").read_text())
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
HOME = "mcp:home-of-demo"
REFUSED = "the thread takes no messages"
GO = f"your word, {SAID_AT} (time typed); run {RAN} by the demo home"


def gone(thread, said):
    """Return T3 Code's answer, as it gives it today (2026-10-23), for a thread it no longer
    has: a read says the thread `is no longer available`, a send that it `was not found`."""
    failure = {"_tag": "OrchestratorMcpFailure", "code": "thread_not_found"}
    text = json.dumps({**failure, "message": f"Thread {thread} {said}."}, separators=(",", ":"))
    return {"isError": True, "content": [{"type": "text", "text": text}]}


def iso(moment):
    return moment.isoformat().replace("+00:00", "Z")


class Server:
    """`Server` is a local HTTP server on a free port, and it answers with `self.answer`."""

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


class Wakes:
    """`Wakes` is what one project's home thread took as wakes: each body's events, its chat lines
    and the body. A wake is a send whose retry key is `wake|<project>|...`, and the body is the
    JSON block of its message. While `refused` holds a reason, T3 Code refuses the project's wakes
    with it."""

    def __init__(self):
        self.refused = ""
        self.posts, self.said, self.bodies = [], [], []

    def took(self, message):
        body = json.loads(message.split("```json\n", 1)[1].split("\n```", 1)[0])
        self.bodies.append(body)
        self.posts.append(body.get("events"))
        self.said.append(body["say"])


class T3(Server):
    """`T3` fakes T3 Code's MCP endpoint and its sign-in, with the eight tools that jbus calls.
    A thread not in `threads` is gone to a read, and one in `forgot` is gone to a send."""

    def __init__(self):
        self.threads, self.launches, self.calls, self.lose, self.refuse = [], [], [], None, ""
        self.messages, self.refuse_send, self.lose_send = {}, False, False
        self.status, self.on_list, self.down, self.lose_read = 200, None, set(), False
        self.challenges, self.registered, self.at_work = {}, [], set()
        self.said, self.forgot, self.wakes, self.woken = {}, set(), {}, {}
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
        """Store a message of a thread as T3 Code returns it when jbus asks for that message by
        its id. It is the user's own message, typed in the app, unless `more` says otherwise."""
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
        """A thread made with no `idle` is at work. While one of its turns runs, its last write
        was a minute ago."""
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
            found = [t for t in found if not t.get("archived")]
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
            found = [t for t in self.threads if t["threadId"] == given["threadId"]]
            if not found:
                return gone(given["threadId"], "is no longer available")
            (thread,) = found
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
            if given["threadId"] in self.forgot:
                return gone(given["threadId"], "was not found")
            key = given["clientRequestId"]
            if key.startswith("wake|"):
                woken = self.wakes.setdefault(key.split("|")[1], Wakes())
                if woken.refused:
                    return {"isError": True, "content": [{"type": "text", "text": woken.refused}]}
                if key not in self.woken:
                    woken.took(given["message"])
                self.woken.setdefault(key, given)
            else:
                self.messages.setdefault(key, given)
            for thread in self.threads:
                if thread["threadId"] == given["threadId"]:
                    thread["updatedAt"] = iso(datetime.now(UTC))
            made = {"threadId": given["threadId"], "status": "queued"}
        elif tool == "t3_thread_configuration":
            found = [t for t in self.threads if t["threadId"] == given["threadId"]]
            if not found:
                return gone(given["threadId"], "is no longer available")
            (thread,) = found
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
            thread["title"] = given["title"]
            thread["branch"] = given["workspaceStrategy"].get("branch")
            if self.lose == "after":
                return None
            made = {"threadId": thread["threadId"]}
        return {"content": [{"type": "text", "text": json.dumps(made)}], "structuredContent": made}


def rate_limit(left, reset=NOW + timedelta(hours=1)):
    """What `gh api rate_limit` prints when both windows jbus spends have `left` calls."""
    reset = int(reset.timestamp())
    window = {"limit": 5000, "used": 5000 - left, "remaining": left, "reset": reset}
    return {"resources": {"core": window, "graphql": window}, "rate": window}


def fake_gh(stub, args, cwd):
    """Run the `gh` of a kitchen with `args` in `cwd`, and return its exit code, stdout and stderr.

    `gh-down` is a GitHub that does not answer, and `gh-down-<checkout>` is one that does not answer
    for that one project. `gh-view-down` is one that does not answer a `pr view`. Each of these
    files holds what `gh` says on stderr. `gh-code` is its exit code (1 when there is none), and
    `gh-out` is what it prints.

    A list gives only a window of recent pull requests. A pull request marked `old` is outside that
    window, and `pr view` still finds it by its number, or ends as the real command does for a
    number it cannot resolve. `head-now.json` is a head pushed since the list was given, and only a
    view shows it. `run rerun` starts a run again and says nothing, or fails when `gh-no-rerun` is
    there.

    `pr edit` changes nothing and says nothing: the log is its record. With `gh-edit-refused`
    there, it fails and says nothing.
    `api rate_limit` gives GitHub's API budget from `rate-limit.json`, or a full one.
    `api .../compare/<base>...<head>` gives the status `compare.json` keeps for `<base>...<head>`,
    or `diverged`.
    `api` picks its answer by the end of the path. It gives a commit's check runs, its runs for a
    push, who owns the repo (with no `repo.json`, GitHub does not say), the commits, and a pull
    request's comments, line comments and reviews. Asked for every page (`--paginate --slurp`), it
    gives a list of pages, here two, and for the runs, a run's jobs and a check run's annotations
    (none), one. A job comes from `jobs.json` by its id, or is one step at the
    first attempt where `jobs.json` has none for it. Its log comes from `logs.json` by its id, or is
    not found, and a log with an escape sequence in it is refused unless asked for with
    `--allow-escape-sequences`, as gh 2.102 does. A commit asked for by its sha lists the files it
    changed, from `commit-files.json`, and its parents and committer, from `commit-made.json`.
    The runs of the browser workflow are in `browser-runs.json`. The repo's workflows are in
    `workflows.json`, and the runs of each other workflow in `workflow-runs.json` by its id. A
    run's jobs come from `run-jobs.json` by the run's id, and the call fails where that entry is
    null.
    """
    with open(stub / "gh.log", "a") as log:
        log.write(" ".join(args) + "\n")
    down = [stub / "gh-down", stub / ("gh-down-" + cwd.name)]
    if args[:2] == ["pr", "view"]:
        down.append(stub / "gh-view-down")
    for failing in down:
        if failing.exists():
            code = (stub / "gh-code").read_text() if (stub / "gh-code").exists() else "1"
            out = (stub / "gh-out").read_text() if (stub / "gh-out").exists() else ""
            return int(code), out, failing.read_text()
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
    elif args[:2] == ["pr", "edit"]:
        if (stub / "gh-edit-refused").exists():
            return 1, "", ""
        said = ""
    elif args[0] == "api" and "/compare/" in args[1]:
        kept = stub / "compare.json"
        known = json.loads(kept.read_text()) if kept.exists() else {}
        said = json.dumps({"status": known.get(args[1].split("/compare/")[1], "diverged")})
    elif args[0] == "api" and args[1].split("?")[0].endswith("/annotations"):
        said = "[[]]" if "--slurp" in args else "[]"
    elif args[0] == "api" and "/check-runs" in args[1]:
        runs = json.loads((stub / "check-runs.json").read_text())
        ref = args[1].split("/commits/")[-1].removesuffix("/check-runs")
        said = json.dumps({"check_runs": runs.get(ref, [])})
    elif args[0] == "api" and "/actions/runs?per_page=" in args[1]:
        kept = stub / "runs.json"
        said = kept.read_text() if kept.exists() else json.dumps({"workflow_runs": []})
        said = json.dumps([json.loads(said)]) if "--slurp" in args else said
    elif args[0] == "api" and "/actions/runs?head_sha=" in args[1]:
        kept, sha = stub / "push-runs.json", args[1].split("head_sha=")[1].split("&")[0]
        listed = json.loads(kept.read_text()) if kept.exists() else {}
        listed = [{"event": "push", "head_branch": "main", **r} for r in listed.get(sha, [])]
        if "&event=push" in args[1]:
            listed = [r for r in listed if r["event"] == "push"]
        said = json.dumps({"workflow_runs": listed})
    elif args[:2] == ["run", "rerun"]:
        if (stub / "gh-no-rerun").exists():
            return 1, "", "run cannot be rerun\n"
        said = ""
    elif args[:2] == ["api", "rate_limit"]:
        kept = stub / "rate-limit.json"
        full = {"limit": 5000, "used": 0, "remaining": 5000, "reset": 1791824400}
        given = {"resources": {"core": full, "graphql": full}}
        said = kept.read_text() if kept.exists() else json.dumps(given)
    elif args[0] == "api" and args[1] == "repos/{owner}/{repo}":
        said = (stub / "repo.json").read_text()
    elif args[0] == "api" and args[1].split("?")[0].endswith(("/comments", "/reviews")):
        kept, name = stub / "remarks.json", "/".join(args[1].split("?")[0].split("/")[-3:])
        if name.endswith("/reviews") and (stub / "gh-no-reviews").exists():
            return 1, "", ""
        said = (json.loads(kept.read_text()) if kept.exists() else {}).get(name, [])
        said = json.dumps([said[:1], said[1:]] if "--slurp" in args else said)
    elif args[0] == "api" and args[1].split("/")[-2] == "commits" and "?" not in args[1]:
        kept, made = stub / "commit-files.json", stub / "commit-made.json"
        files = (json.loads(kept.read_text()) if kept.exists() else {}).get(args[1][-40:], [])
        how = (json.loads(made.read_text()) if made.exists() else {}).get(args[1][-40:], {})
        said = json.dumps({"files": [{"filename": name} for name in files], **how})
    elif args[0] == "api" and args[1].endswith("/logs"):
        kept = stub / "logs.json"
        logs = json.loads(kept.read_text()) if kept.exists() else {}
        if args[1].split("/")[-2] not in logs:
            return 1, "", "gh: Not Found (HTTP 404)\n"
        said = logs[args[1].split("/")[-2]]
        if "\x1b" in said and "--allow-escape-sequences" not in args:
            refused = "the response contains terminal escape sequences; pass "
            return 1, "", refused + "--allow-escape-sequences to output it anyway\n"
    elif args[0] == "api" and "/actions/jobs/" in args[1]:
        kept = stub / "jobs.json"
        job = (json.loads(kept.read_text()) if kept.exists() else {}).get(args[1].split("/")[-1])
        said = json.dumps(job or {"steps": [{"name": "make check"}], "run_attempt": 1})
    elif args[0] == "api" and args[1].split("?")[0].endswith("/actions/workflows"):
        kept = stub / "workflows.json"
        said = json.dumps({"workflows": json.loads(kept.read_text()) if kept.exists() else []})
    elif args[0] == "api" and "/actions/workflows/browser.yml/" in args[1]:
        kept = stub / "browser-runs.json"
        said = json.dumps({"workflow_runs": json.loads(kept.read_text()) if kept.exists() else []})
    elif args[0] == "api" and "/actions/workflows/" in args[1]:
        kept, flow = stub / "workflow-runs.json", args[1].split("/actions/workflows/")[1]
        every = json.loads(kept.read_text()) if kept.exists() else {}
        said = json.dumps({"workflow_runs": every.get(flow.split("/")[0], [])})
    elif (
        args[0] == "api" and "/actions/runs/" in args[1] and args[1].split("?")[0].endswith("/jobs")
    ):
        kept = stub / "run-jobs.json"
        every = json.loads(kept.read_text()) if kept.exists() else {}
        if every.get(args[1].split("/")[-2], []) is None:
            return 1, "", "gh: Bad Gateway (HTTP 502)\n"
        said = json.dumps({"jobs": every.get(args[1].split("/")[-2], [])})
        said = json.dumps([json.loads(said)]) if "--slurp" in args else said
    elif args[0] == "api":
        said = (stub / "commits.json").read_text()
    else:
        return 2, "", ""
    return 0, said + "\n", ""


def fake_jmerge(stub, args, cwd):
    """Run the `jmerge` of a kitchen with `args`, and return its exit code, stdout and stderr.

    `jmerge-dies` ends it the way a `SystemExit` with a message ends the real command: the line on
    stderr, and exit 1. `jmerge-says` ends it the way the real command ends when it cannot ask
    GitHub: the line on stdout, and exit 1. An accept of a held pull request does nothing where the
    test wrote no `accept.txt`. Each pass reads `--claims`, which changes nothing, so its runs go
    in `claims.log` and `jmerge.log` keeps the runs that may merge.
    """
    with open(stub / ("claims.log" if args == ["--claims"] else "jmerge.log"), "a") as log:
        log.write(" ".join(args) + "\n")
    if args == ["--claims"]:
        if (stub / "claims-fail").exists():
            return 1, "", ""
        return 0, (stub / "claims.txt").read_text(), ""
    if (stub / "jmerge-dies").exists():
        return 1, "", (stub / "jmerge-dies").read_text() + "\n"
    if (stub / "jmerge-says").exists():
        return 1, (stub / "jmerge-says").read_text() + "\n", ""
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
    """Run the `notify-send` of a kitchen, which keeps what it was asked to show."""
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
    """Return the file that a command's first word names, found on PATH the way the system finds
    it."""
    if os.sep in name:
        return name
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if os.access(found := os.path.join(part, name), os.X_OK) and os.path.isfile(found):
            return found
    return ""


class Side:
    """`Side` is a second project of a kitchen, with its own checkout, state, `projectId` and
    home thread."""

    def __init__(self, kitchen, name):
        self.name, self.project = name, f"{name}-project-id"
        self.checkout = kitchen.root / name
        self.home = kitchen.root / "home" / name
        self.state = kitchen.state_dir / name
        self.wakes = kitchen.t3.wakes.setdefault(name, Wakes())


class Kitchen:
    """`Kitchen` is one project with jbus set up for it: config, state, a main checkout, and the
    fakes.

    `second` adds another project to the same config, T3 Code server, `gh` and `jmerge`.

    Its repo is a copy of the worker's template (`repo_template`).
    """

    def __init__(self, tmp_path, monkeypatch):
        tmp_path.mkdir(exist_ok=True)
        self.root, self.t3 = tmp_path, T3()
        self.stub = tmp_path / "stub"
        self.config_dir, self.state_dir = tmp_path / "config", tmp_path / "state"
        self.home = tmp_path / "home" / "demo"
        self.checkout = tmp_path / "demo"
        for made in (self.stub, self.config_dir, self.home / "tasks", self.home / "scouts"):
            made.mkdir(parents=True)
        self.state = self.state_dir / "demo"
        self.wakes = self.t3.wakes.setdefault("demo", Wakes())
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
        monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(tmp_path / "locks"))
        monkeypatch.setenv("LAVISH_AXI_STATE_DIR", str(tmp_path / "lavish"))
        monkeypatch.chdir(self.checkout)
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION)
        monkeypatch.setattr(queue, "clock", lambda: NOW)
        self.monkeypatch = monkeypatch
        self.machine()

    def run(self, command, **how):
        """This function takes the place of `subprocess.run` while the kitchen exists, and answers a
        call to one of the kitchen's fakes itself.

        Starting a Python for each `gh` and `jmerge` of a pass took most of a test's time. So when
        PATH resolves a command to a fake as the kitchen wrote it, this calls that fake's function.
        Anything else starts a process as before: `git`, a command that is missing, a fake that a
        test wrote over or took off PATH, and a call that passes its own `env`, asks for `check`, or
        does not capture what is printed. A fake called here ignores `timeout`. One that ends on an
        exception ends as a Python does: the traceback on stderr, and exit 1.
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
        """Write the machine and the plan that `jgauge room` reads: idle and under its limits, or
        as told."""
        env = machine(self.root / "machine", **{**IDLE, **readings}, plan=plan)
        self.monkeypatch.setenv("PROC", env["PROC"])
        self.monkeypatch.setenv("LIMITS", env["LIMITS"])
        self.monkeypatch.setenv("TMPFS", env["TMPFS"])
        return env["LIMITS"]

    def repo(self, checkout, origin):
        """Make a main checkout on `main`, with an origin that has that branch as its default.

        It is a copy of the worker's template.
        """
        repo_template.copied(repo_template.templated(), checkout, origin)

    def second(self, name="other"):
        """Add a project to the config, after the projects it has, and return where the new project
        is.

        It writes the config with no other key given, so a test that needs other keys calls `config`
        after it.
        """
        side = Side(self, name)
        (side.home / "tasks").mkdir(parents=True)
        self.repo(side.checkout, self.root / f"{name}-origin.git")
        self.sides.append(side)
        self.config()
        return side

    def close(self):
        self.t3.close()

    @staticmethod
    def write(path, text, mode=0o600):
        path.write_text(text)
        path.chmod(mode)

    def signed_in(self, ago, **token):
        """Store the token as `jbus t3 login` stores it, with `obtained_at` set `ago` before the
        tests' now."""
        stored = {
            "server": self.t3.url,
            "token": {"access_token": TOKEN, **token},
            "obtained_at": (NOW - ago).timestamp(),
        }
        self.write(self.config_dir / "t3.json", json.dumps(stored))

    def config(self, own=(), **top):
        """Write the config. A top-level key given as None stays out of the file, and `own` is
        more lines for each project's own table. Wakes go to `home_thread` unless a test says
        otherwise, since no home of the kitchen has a home-id until a test writes one."""
        top = {
            "dispatch": True,
            "max_running": 1,
            "runtimeMode": "full-access",
            "home_thread": HOME,
            **top,
        }
        lines = [f"server = {json.dumps(self.t3.url)}"]
        for key, value in top.items():
            if value is None:
                continue
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
            *own,
        ]
        for side in self.sides:
            lines += [
                "[[project]]",
                f"name = {json.dumps(side.name)}",
                f"checkout = {json.dumps(str(side.checkout))}",
                f"projectId = {json.dumps(side.project)}",
                *own,
            ]
        self.write(self.config_dir / "config.toml", "\n".join(lines) + "\n")

    def git(self, *args, cwd=None):
        subprocess.run(["git", *IDENTITY, *args], cwd=cwd or self.checkout, check=True)

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
        """Write what Lavish keeps of its sessions: each one's key, with its page and its status."""
        kept = {
            key: {"key": key, "file": str(file), "status": status, "pending_prompts": queued}
            for key, (file, status, *more) in sessions.items()
            for queued in [more[0] if more else 0]
        }
        (self.root / "lavish").mkdir(exist_ok=True)
        (self.root / "lavish" / "state.json").write_text(json.dumps({"sessions": kept}))

    def word(self, project="demo"):
        """Return the id of a word of the user's that the project keeps. The user typed and sent
        the word long ago, and a test bases its approval on it."""
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
        return jbus.read_json(self.state / wake.HOME / "outbox.json", [])

    def marks(self):
        return jbus.read_json(self.state / wake.HOME / "wake.json", {})

    def status(self):
        return json.loads((self.state_dir / "status.json").read_text())

    def events(self, kind=None):
        """Return every event the project queued, oldest first, as the log has it. A quiet event
        is in the log and nowhere else."""
        every = wake.Box(self.state, jbus.load().project("demo")).log()
        return [e for e in every if kind is None or e["event"] == kind]

    def lines(self, kind=None):
        return [event["line"] for event in self.events(kind)]

    def forget(self):
        """Empty the outbox, the log and what the home thread took, so that `events` gives only
        what comes after."""
        jbus.write_json(self.state / wake.HOME / "outbox.json", [])
        (self.state / wake.LOG).unlink(missing_ok=True)
        self.wakes.posts.clear()

    def quiet(self):
        """Run a first pass, which records what is already so, and keep no event of it."""
        self.poll(NOW - timedelta(hours=1))
        self.forget()

    def merged(self, slug, number, sha, ago=timedelta(minutes=10), title=None):
        return {
            "number": number,
            "url": f"https://example.test/pull/{number}",
            "title": title or f"feat: {slug}",
            "headRefName": slug,
            "headRefOid": "d" * 40,
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
            "baseRefName": "main",
            "statusCheckRollup": [
                {"status": "COMPLETED" if state else "IN_PROGRESS", "conclusion": state}
            ],
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
        (["gh", "api", "repos/o/r/compare/a...b"], {"compare.json": '{"a...b": "ahead"}'}),
        (["gh", "pr", "edit", "7", "--base", "main"], {}),
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
    """The test compares only the last line of stderr, since a traceback names the file it came
    from."""
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
    name = "claims" if command == ["jmerge", "--claims"] else command[0].removesuffix("-send")
    log = kitchen.log(name)
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
    """When a test wrote over a fake or took it off PATH, the name is whatever command the
    machine has, and the kitchen starts that command."""
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


def test_an_answer_into_a_capped_thread_is_held_then_sent_once_after_the_reset(kitchen):
    """The answer to a question had no cap check of its own. A message into a thread whose
    instance is capped starts a turn that ends at once on the limit, so the outbox holds it under
    its key, writes the hold to `outbox.jsonl`, and the first pass after the reset sends it once."""
    crew = kitchen.t3.thread("alpha", "completed", idle=timedelta(minutes=30))
    kitchen.brief("alpha", f"Thread: {crew['threadId']}\n")
    kitchen.quiet()
    asked = GATE.format(n="<n>", asked="tea or coffee?", status="open", slug="alpha")
    assert kitchen.main("gate", "alpha", stdin=asked)[0] == 0
    said = ("--by", "user", "--at", "2026-10-12 11:30 ET", "--differs", "coffee")
    assert kitchen.main("answer", "1", *said)[0] == 0
    resets = NOW + timedelta(minutes=40)
    ledger.file_of("claudeAgent").write_text(f"five_hour 100 {int(resets.timestamp())}\n")

    def answers():
        return [one for one in sends(kitchen) if one["clientRequestId"] == "answer|alpha|1"]

    for minute in (10, 20):
        lines = kitchen.poll(NOW + timedelta(minutes=minute))
        assert answers() == []
        assert [one for one in lines if one.startswith("wait alpha: ") and "capped" in one]
    kitchen.poll(NOW + timedelta(minutes=41))
    kitchen.poll(NOW + timedelta(minutes=44))
    assert [one["threadId"] for one in answers()] == [crew["threadId"]]
    logged = (kitchen.state / "outbox.jsonl").read_text().splitlines()
    went = [json.loads(line) for line in logged]
    assert [
        (one["at"][:16], one["thread"], one["row"], one["template"], one["needs"], one["went"])
        for one in went
        if one["key"] == "answer|alpha|1"
    ] == [
        ("2026-10-12T15:10", crew["threadId"], "alpha", "answer", "act", "held"),
        ("2026-10-12T15:20", crew["threadId"], "alpha", "answer", "act", "held"),
        ("2026-10-12T15:41", crew["threadId"], "alpha", "answer", "act", "sent"),
    ]
    assert [one["rule"] for one in went if one["went"] == "held"][0].startswith("cap: ")


STALE = "wait 7 https://example.test/pull/7: main changed src/alpha/a.py after its check started"


def test_a_crew_that_waits_on_a_slot_while_main_moves_twice_is_told_to_rebase_once_after_its_wake(
    kitchen,
):
    """The census of jbus's messages found 91 sent to a crew that waited on a test slot or on its
    review: the crew wrote a line and ended, and a later message did the work. Here the crew of
    alpha waits on the short lane, every slot of it taken, while main moves twice under its pull
    request. The outbox holds the rebase message by its `slot` rule while the crew waits, and by
    its `busy` rule in the pass of the wake, which told the thread already, and while the woken
    turn runs. Once the crew took its
    slot and ended its turn, the next pass sends the one rebase message, and the row ends as it
    would have: the rebase key marked sent."""
    queued(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    (crew,) = kitchen.t3.threads
    crew["status"] = "completed"
    kitchen.t3.at_work.discard(crew["threadId"])
    brief = kitchen.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text() + review(verdict="clean", findings="none"))
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7), "mergeable": "MERGEABLE"}])
    locks = slot.locks_dir()
    locks.mkdir(parents=True, exist_ok=True)
    lane = slot.short()
    taken = []
    for n in range(1, lane.slots + 1):
        fd = os.open(locks / f"{lane.lock}.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        taken.append(fd)
    command = ["uv", "run", "pytest", "tests/test_alpha.py"]
    waiters.register(locks, crew["threadId"], "short", lane.slots, command, NOW)
    other = kitchen.root / "other"
    kitchen.git("clone", "-q", str(kitchen.origin), str(other), cwd=kitchen.root)
    try:
        for minute in (0, 3):
            kitchen.git("commit", "-q", "--allow-empty", "-m", "a merge", cwd=other)
            kitchen.git("push", "-q", "origin", "main", cwd=other)
            kitchen.set("jmerge.txt", STALE + "\n")
            kitchen.poll(NOW + timedelta(minutes=minute))
        for fd in taken:
            os.close(fd)
        taken.clear()
        kitchen.poll(NOW + timedelta(minutes=6))
        crew["status"] = "running"
        kitchen.poll(NOW + timedelta(minutes=9))
        waiters.drop(locks, crew["threadId"])
        crew["status"] = "completed"
        kitchen.poll(NOW + timedelta(minutes=12))
        kitchen.poll(NOW + timedelta(minutes=15))
    finally:
        for fd in taken:
            os.close(fd)
    to_crew = [one["clientRequestId"].split("|")[0] for one in sends(kitchen)]
    assert to_crew == ["slot-wake", "rebase"]
    assert "rebase|alpha|cccccccccccc" in jbus.read_json(kitchen.state / "sent.json", [])
    logged = [
        json.loads(line) for line in (kitchen.state / "outbox.jsonl").read_text().splitlines()
    ]
    rebase = [
        (one["at"][11:16], one["went"], one["rule"])
        for one in logged
        if one["template"] == "rebase"
    ]
    assert rebase == [
        ("15:00", "held", "slot"),
        ("15:03", "held", "slot"),
        ("15:06", "held", "busy"),
        ("15:09", "held", "busy"),
        ("15:12", "sent", ""),
    ]


def asking(question="which one?", default="the first"):
    """Return a gate of `features/home/templates/gates.md`, filled in, that asks `question` and
    has the two `OPTIONS`."""
    return (
        f"## Gate <n>: {question}\nStatus: open\nAsked by: alpha, thread mcp:a-thread\n"
        f"Default: {default}\nBuilt on it: nothing\nUndo: pick the other\n" + OPTIONS
    )


ASK = asking()


def complete(slug, more=""):
    """Return a brief with every field that `jbus queue add` asks for, and `more` under them."""
    return (
        f'# {slug}: a task\nTask: "do {slug}"\nDone when:\n- it is done\n'
        f"Proves it: `make check`\nSize: S\nWhere: `src/{slug}/`\nDesign: none, a test\n"
        'Decisions: "review it once", the user\'s word in a test\n'
        f"Pull request: open one when done\nReview: review\nPlaybook: feature\n{more}"
    )


def bound(kitchen, slug, project="demo"):
    """Return what an approval record holds of the brief stored now: its sha and its fingerprint."""
    text = (kitchen.state_dir / project / "briefs" / f"{slug}.md").read_text()
    made = jbus.queue.fingerprint(text)
    return {
        "brief_sha": jbus.queue.brief_sha(text),
        "scope": meaning.fingerprint(made),
        "meaning": made,
    }


def approved(kitchen, slug, priority=1):
    """Add a row of the queue with its brief, and the user's go for it."""
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


def said(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_each_kitchen_pushes_to_its_own_origin_and_the_template_stays_as_built(
    tmp_path, monkeypatch
):
    """Two kitchens push a commit each, and each sees only its own. After this test, and after every
    earlier test this worker ran, the template's origin stays at the commit the build made.
    """
    kitchen_template = repo_template.templated()
    assert said(kitchen_template.origin, "rev-parse", "main") == kitchen_template.main
    kitchens = {name: Kitchen(tmp_path / name, monkeypatch) for name in ("one", "two")}
    try:
        for name, made in kitchens.items():
            assert said(made.checkout, "config", "remote.origin.url") == str(made.origin)
            assert said(made.checkout, "symbolic-ref", "refs/remotes/origin/HEAD") == (
                "refs/remotes/origin/main"
            )
            (made.checkout / f"{name}.txt").write_text(name)
            made.git("add", f"{name}.txt")
            made.git("commit", "-q", "-m", name)
            made.git("push", "-q", "origin", "main")
        for name, made in kitchens.items():
            assert said(made.origin, "log", "--format=%s", "main").splitlines() == [name, "start"]
            assert said(made.checkout, "rev-parse", "origin/main") == said(
                made.origin, "rev-parse", "main"
            )
    finally:
        for made in kitchens.values():
            made.close()
    assert said(kitchen_template.origin, "rev-parse", "main") == kitchen_template.main
    assert said(kitchen_template.checkout, "rev-parse", "main") == kitchen_template.main
    assert said(kitchen_template.checkout, "config", "remote.origin.url") == str(
        kitchen_template.origin
    )


def test_building_the_template_starts_no_background_maintenance(tmp_path, monkeypatch):
    """git's auto maintenance runs detached after a commit or a push. In main's run 39629845242, it
    wrote and removed `objects/maintenance.lock` while the build copied the checkout.
    """
    trace = tmp_path / "trace"
    monkeypatch.setenv("GIT_TRACE2", str(trace))
    repo_template.built(tmp_path / "template")
    started = [line for line in trace.read_text().splitlines() if " start " in line]
    assert started
    assert not [line for line in started if "maintenance run" in line or " gc --auto" in line]


def test_a_lock_file_left_in_the_template_is_not_copied(tmp_path):
    """A lock file in the template, one a git process holds or one it left, stays behind."""
    template = repo_template.built(tmp_path / "template")
    for repo in (template.checkout / ".git", template.origin):
        (repo / "objects" / "maintenance.lock").write_text("")
    checkout, origin = tmp_path / "checkout", tmp_path / "origin.git"
    repo_template.copied(template, checkout, origin)
    assert said(checkout, "rev-parse", "main") == template.main
    assert not list(checkout.rglob("*.lock")) + list(origin.rglob("*.lock"))


def queued(kitchen, slug, text=None):
    """Add a row of the queue, approved, as the Chef adds one."""
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
    """Each message a pass sent a thread, but for the wakes of a home thread (`Wakes`)."""
    return [
        given
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send" and not given["clientRequestId"].startswith("wake|")
    ]


def settles(kitchen, action="settle"):
    return [
        given
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_organize" and given["action"] == action
    ]
