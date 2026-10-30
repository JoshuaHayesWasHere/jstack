"""jbus talks to the T3 Code server as an outside MCP client, with the sign-in and seven tools.

`login` registers jbus with the server, sends the user to the server's approval page, keeps the
token that the server issues, and records when the server issued it (`jsettings.t3.expiry` says
when that token runs out). `Client` then calls the tools in `TOOLS` at `<server>/mcp`, and no
other tool: a test scans this package for any other tool name.

Three of the seven tools change a thread, and `Client.call` allows each of them in one form
only (`_held`):

- `t3_thread_organize`, to settle or archive a thread that the call names.
- `t3_thread_configure`, to move a thread that a brief or a home names to another instance of
  its role's pool, with its model and options as they were (`jbus.failover`). With only a
  `threadId` it changes nothing and reads the thread's selection, which any thread may have.
- `t3_thread_send`, as a queued message with a retry key, to a thread that the sender adds to
  `recipients`. Every such message goes through `jbus.outbox.send`, which adds its thread, holds
  a message to a capped thread, and logs each send and hold.

`Client.message` reads one message by its id, with `t3_thread_read`. T3 Code gives who wrote
the message, its text and its time, and that is why jbus counts the user's word as checked.
`Client.item` reads any item of a thread by its id the same way, such as a question box
(`jbus.boxes`).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jroles
import jsettings
from jbus import Config, Refused, queue, verbs, write_json
from jbus.bind import NoLookup
from jroles import pool
from jsettings.t3 import PROTOCOL as PROTOCOL
from jsettings.t3 import Session, get_json, post
from jsettings.t3 import T3Dropped as T3Dropped
from jsettings.t3 import T3Error as T3Error
from jsettings.t3 import T3Refused as T3Refused

TOOLS = (
    "t3_thread_configure",
    "t3_thread_launch",
    "t3_thread_list",
    "t3_thread_read",
    "t3_thread_send",
    "link_pull_request",
    "t3_thread_organize",
)
SCOPE = "orchestration:read orchestration:operate"
CHARS = 50000
GONE = re.compile(
    r"not[ _]found|no longer available|no such|unknown thread|does not exist|no thread", re.I
)


class Listener(NoLookup, http.server.HTTPServer):
    """The `HTTPServer` `login` waits on for the browser's callback, which binds without asking
    DNS for a name of 127.0.0.1 (`jbus.bind`)."""


def login(server: str, token_path: Path, *, wait: float = 600, say=print) -> dict[str, Any]:
    """Sign in once. The user approves in the browser, and `login` stores the token and never
    prints it."""
    meta = get_json(f"{server}/.well-known/oauth-authorization-server")
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(16)
    got: dict[str, str] = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urllib.parse.urlsplit(self.path)
            if url.path == "/callback":
                got.update({k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()})
            self.send_response(200 if url.path == "/callback" else 404)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"jbus is signed in. This tab can be closed.\n")

        def log_message(self, *_: Any) -> None:
            pass

    listener = Listener(("127.0.0.1", 0), Callback)
    try:
        redirect = f"http://127.0.0.1:{listener.server_address[1]}/callback"
        _, said = post(
            meta.get("registration_endpoint") or f"{server}/oauth/mcp/register",
            json.dumps(
                {
                    "client_name": "jbus",
                    "redirect_uris": [redirect],
                    "grant_types": ["authorization_code"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                    "scope": SCOPE,
                }
            ).encode(),
            {"content-type": "application/json"},
            8,
        )
        client = json.loads(said)
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": client["client_id"],
                "redirect_uri": redirect,
                "scope": SCOPE,
                "state": state,
                "code_challenge": challenge.rstrip(b"=").decode(),
                "code_challenge_method": "S256",
                "resource": f"{server}/mcp",
            }
        )
        url = f"{meta['authorization_endpoint']}?{query}"
        say(f"approve jbus in the browser, with a code from `t3 auth pairing create`:\n{url}")
        webbrowser.open(url)
        deadline = time.monotonic() + wait
        while "code" not in got and "error" not in got:
            listener.timeout = deadline - time.monotonic()
            if listener.timeout <= 0:
                raise Refused(f"refused: no approval came back within {wait:.0f} s")
            listener.handle_request()
    finally:
        listener.server_close()
    if got.get("error") or got.get("state") != state:
        raise Refused(f"refused: the approval came back as {got.get('error') or 'a wrong state'}")
    _, said = post(
        meta["token_endpoint"],
        urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": got["code"],
                "redirect_uri": redirect,
                "client_id": client["client_id"],
                "code_verifier": verifier,
                "resource": f"{server}/mcp",
            }
        ).encode(),
        {"content-type": "application/x-www-form-urlencoded"},
        8,
    )
    token = json.loads(said)
    if not token.get("access_token"):
        raise Refused("refused: the token endpoint gave no access_token")
    stored = {"server": server, "client": client, "token": token, "obtained_at": time.time()}
    write_json(token_path, stored, mode=0o600)
    return token


@dataclass(frozen=True)
class Message:
    """A `Message` is one message of a thread, as T3 Code stores it. `title` is the thread's title.
    `kind` is the item's `type`, `by` is its `createdBy` and `source` is its `creationSource`. A
    message that an agent or jbus sent into a thread is a `user_message` too, by `agent`."""

    thread: str
    id: str
    title: str
    kind: str
    by: str
    source: str
    text: str
    at: datetime

    @property
    def own(self) -> bool:
        """Say whether the user wrote the message: a user message that no agent sent."""
        return self.kind == "user_message" and self.by == "user"


class Client(Session):
    """A `Client` is one MCP session at `<server>/mcp` (`jsettings.t3.Session`). `call` is the
    only way jbus reaches a tool."""

    def __init__(self, server: str, token_path: Path, *, timeout: float = 60) -> None:
        super().__init__(server, token_path, timeout=timeout)
        self.recipients: frozenset[str] = frozenset()
        self.moves: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {}

    def tools(self) -> list[dict[str, Any]]:
        self._open()
        return [tool for tool in self._rpc("tools/list", {})["tools"] if tool["name"] in TOOLS]

    def _held(self, tool: str, arguments: dict[str, Any]) -> str:
        """For a call that changes a thread, return why jbus does not make it, or nothing when
        jbus does make it."""
        if tool == "t3_thread_organize":
            if set(arguments) != {"action", "threadId"} or arguments["action"] not in (
                "settle",
                "archive",
            ):
                return "is only called to settle or archive a thread it names"
            if not arguments["threadId"]:
                return "names no thread to settle or archive"
        if tool == "t3_thread_configure":
            if set(arguments) == {"threadId"}:
                return "" if arguments["threadId"] else "names no thread to read"
            if set(arguments) != {"threadId", "modelSelection"}:
                return "is only called to read a thread, or with a thread and a model selection"
            if arguments["threadId"] not in self.recipients:
                return f"to {arguments['threadId']}: no brief has it on a Thread: line"
            was, instances = self.moves.get(arguments["threadId"], ({}, ()))
            chosen = arguments["modelSelection"]
            if not isinstance(chosen, dict) or chosen.get("instanceId") not in instances:
                return "is only called to move a thread to an instance of its role's pool"
            if {**chosen, "instanceId": None} != {**was, "instanceId": None}:
                return "changes only the instance: the model and the options stay as they were"
        if tool == "t3_thread_send":
            if set(arguments) != {"threadId", "message", "mode", "clientRequestId"}:
                return "is only called with a thread, a message, a mode and a retry key"
            if arguments["mode"] != "queue" or not arguments["clientRequestId"]:
                return "is only called with mode queue and a retry key"
            if arguments["threadId"] not in self.recipients:
                return f"to {arguments['threadId']}: no brief has it on a Thread: line"
        return ""

    def item(
        self, thread: str, item: str, key: str = "itemId", value: str = "", view: str = ""
    ) -> tuple[dict[str, Any], str, str]:
        """Return the item of the thread whose `key` is `value` (its `itemId` is `item` by
        default), read by `item` in `view`, with its whole text and the thread's title. Raise
        `T3Refused` when the thread does not have it."""
        asked = {"threadId": thread, "itemId": item, "maxCharsPerItem": CHARS}
        if view:
            asked["view"] = view
        text, offset = "", 0
        while True:
            read = self.call("t3_thread_read", {**asked, "textOffset": offset} if offset else asked)
            found = [one for one in read.get("items") or [] if one.get(key) == (value or item)]
            if not found:
                raise T3Refused(f"t3_thread_read: thread {thread} has no item {value or item}")
            text += found[0].get("text") or ""
            further = found[0].get("nextTextOffset")
            if not isinstance(further, int) or further <= offset:
                break
            offset = further
        return found[0], text, str((read.get("thread") or {}).get("title") or "")

    def message(self, thread: str, message: str) -> Message:
        """Return the message of the thread with that id, with its whole text. Raise
        `T3Refused` when the thread does not have the message, or the message has no time."""
        item = f"turn-item:message:{urllib.parse.quote(message, safe='')}"
        try:
            one, text, title = self.item(thread, item, "messageId", message)
        except T3Refused as error:
            raise T3Refused(f"t3_thread_read: thread {thread} has no message {message}") from error
        try:
            at = jsettings.when(str(one.get("updatedAt")))
        except ValueError as error:
            raise T3Refused(f"t3_thread_read: message {message} has no time") from error
        return Message(
            thread=thread,
            id=message,
            title=title,
            kind=str(one.get("type") or ""),
            by=str(one.get("createdBy") or ""),
            source=str(one.get("creationSource") or ""),
            text=text,
            at=at if at.tzinfo else at.replace(tzinfo=UTC),
        )

    def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        if tool not in TOOLS:
            raise Refused(f"refused: jbus does not call {tool}")
        held = self._held(tool, arguments)
        if held:
            raise Refused(f"refused: {tool} {held}")
        self._open()
        result = self._rpc("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            said = " ".join(part.get("text", "") for part in result.get("content", []))
            raise T3Refused(f"{tool}: {said[:300]}")
        if "structuredContent" in result:
            return result["structuredContent"]
        for part in result.get("content", []):
            if part.get("type") == "text":
                try:
                    return json.loads(part["text"])
                except ValueError:
                    return {"text": part["text"]}
        return {}


def listed(client: Client, project_id: str, **asked: Any) -> list[dict[str, Any]]:
    """Return every thread of the project that `t3_thread_list` gives for `asked`, page by page,
    up to 20 pages of 100."""
    found, cursor = [], None
    for _ in range(20):
        more = {"cursor": cursor} if cursor else {}
        said = client.call(
            "t3_thread_list", {"projectId": project_id, "limit": 100, **asked, **more}
        )
        found += said.get("threads", [])
        cursor = said.get("nextCursor")
        if not cursor:
            break
    return found


def heard(config: Config, ref: str) -> queue.Said:
    """Read the user's own message `<thread id>/<message id>` from T3 Code now, and return
    its text on one line, its time in the user's zone, and the title of its thread.

    A message that an agent or jbus sent into a thread is not the user's, and `heard` refuses
    it. It also refuses a message that T3 Code does not return.
    """
    thread, _, message = ref.partition("/")
    if not thread or not message:
        raise Refused(f'refused: --message is "<thread id>/<message id>", not {ref}')
    try:
        found = Client(config.server, config.token_path).message(thread, message)
    except T3Error as error:
        raise Refused(f"refused: T3 Code gave no message {ref} ({error})") from error
    if not found.own:
        wrote = f"{found.kind} by {found.by}" + (f", from {found.source}" if found.source else "")
        raise Refused(
            f"refused: message {ref} is not {config.user.user}'s own: T3 Code has it as a {wrote}"
        )
    words = " ".join(found.text.split())
    if not words:
        raise Refused(f"refused: message {ref} has no words")
    return queue.Said(words, config.user.stamp(found.at), found.title, True, ref)


def typed(args: argparse.Namespace, config: Config, verb: str) -> queue.Said | None:
    """Return where the user's words for `jbus word` and `jbus answer` came from: the message
    jbus read, or None for words typed with `--by` and `--at`. `typed` refuses the words when
    the command gives both forms, or neither."""
    given = args.by is not None or args.at is not None or bool(args.words)
    if args.message is not None and not given:
        return heard(config, args.message)
    if args.message is not None or args.by is None or args.at is None or not args.words:
        raise Refused(
            f"refused: {verb} takes --message <thread id>/<message id>, or --by and --at "
            "with the words, and not both"
        )
    return None


def _t3(args: argparse.Namespace, config: Config) -> int:
    if args.verb == "login":
        login(config.server, config.token_path, wait=args.wait)
        print(f"signed in: the token is in {config.token_path}")
        return 0
    project = verbs.project(config, args.project)
    client = Client(config.server, config.token_path)
    arguments = {
        "projectId": project.project_id,
        "title": "jbus: launch test",
        "message": "say hello and stop",
        "workspaceStrategy": {
            "type": "worktree",
            "baseRef": "main",
            "branch": f"jbus-launch-test-{int(time.time())}",
            "startFromOrigin": True,
        },
    }
    if config.runtime_mode:
        arguments["runtimeMode"] = config.runtime_mode
    try:
        (routed,) = pool.routes("crew", datetime.now(UTC)) or (None,)
    except jroles.Refused as error:
        raise Refused(str(error)) from error
    if routed and routed.choice.instance is None:
        print(f"no launch: {routed.choice.why}")
        return pool.WAIT
    if routed:
        arguments["modelSelection"] = routed.as_json()
    made = client.call("t3_thread_launch", arguments)
    print(made.get("threadId") or made)
    return 0


def _sign(sign: argparse.ArgumentParser) -> None:
    sign.add_argument("verb", choices=["login", "launch-test"])
    sign.add_argument("--wait", type=float, default=600, help="seconds to wait for the approval")


VERBS = (verbs.Verb("t3", "the sign-in to the T3 Code server, and one test launch", _sign, _t3),)
