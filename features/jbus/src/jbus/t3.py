"""jbus talks to the T3 Code server as an outside MCP client, with the sign-in and twelve tools.

`login` registers jbus with the server, sends the user to the server's approval page, keeps the
token that the server issues, and records when the server issued it (`jsettings.t3.expiry` says
when that token runs out). `Client` then calls the tools in `TOOLS` at `<server>/mcp`, and no
other tool: a test scans this package for any other tool name.

Five of the twelve tools can change a thread, a task or a project, and `Client.call` allows each of
them only in the forms below (`_held`):

- `t3_thread_organize`, to settle or archive a thread that the call names, and to unarchive one
  (`jbus project open`, for the home threads `jbus project close` archived).
- `schedule_task`, only to switch a scheduled task that the call names off or on, with
  `enabled` and nothing else (`jbus project close` and `open`). `list_scheduled_tasks` only reads.
- `t3_project_update`, only to archive or unarchive a project that the call names, with
  `archived` and nothing else (`jbus project close` and `open`, so a closed project leaves T3
  Code's sidebar). `t3_project_list` only reads.
- `t3_thread_configure`, to move a thread that a brief or a home names to another instance of
  its role's pool, with its model and options as they were (`jbus.failover`). With only a
  `threadId` it changes nothing and reads the thread's selection, which any thread may have.
- `t3_thread_send`, as a queued message with a retry key, to a thread that the sender adds to
  `recipients`. Every such message goes through `jbus.outbox.send`, which adds its thread, holds
  a message to a capped thread, and logs each send and hold. A message whose key names a template
  of `STEERS` goes in mode `auto` instead, and only so: into a turn the thread already runs, as a
  steer, since `outbox`'s `idle` rule holds it while the thread runs none.

`orchestrator_capabilities` only reads: which provider instances T3 Code can run, and why not
where it cannot, such as an instance that is signed out (`jbus.failover`).

`Client.message` reads one message by its id, with `t3_thread_read`. T3 Code gives who wrote
the message, its text and its time, and that is why jbus counts the user's word as checked.
`Client.item` reads any item of a thread by its id the same way, such as a question box
(`jbus.boxes`).

`home_ask` reads the ask a plain reply of the user's answers: the last message a home wrote in its
own thread before that reply (`Client.asked_before`). `asks` is the rule of what such an ask is
about for a door: the ask names this door, by the row's slug or its gate's number, and no other
open door, so a plain "yes" binds to one door and never to two (`jbus.acts`). `asked_of` cuts an
ask into the part each row owns, from its name to the next row named, and `jbus waive` reads the
lines a row's part names. `names` reads an item named in the forms a person writes.

A tool of `TOOLS` that T3 Code stops serving fails only where jbus calls it, so each pass compares
the two, with one `tools/list`, in a chore (`contract`). Each tool it no longer serves is an
incident of the machine's (`jbus.alert`), under the key `t3-tool <tool>`, told once when it starts
and once when it ends. A list that did not come says nothing of any tool, either way.
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
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jroles
import jsettings
from jbriefs.home import scopes, thread_of
from jbus import Config, Refused, alert, queue, verbs, write_json
from jbus.bind import NoLookup
from jroles import pool
from jsettings.t3 import PROTOCOL as PROTOCOL
from jsettings.t3 import Session, get_json, post
from jsettings.t3 import T3Dropped as T3Dropped
from jsettings.t3 import T3Error as T3Error
from jsettings.t3 import T3Refused as T3Refused

STEERS = frozenset({"reload"})
"""The templates whose message goes only into a turn its thread already runs, as a steer, in mode
`auto`: the key of each starts with its template. `outbox`'s `idle` rule holds them while the
thread runs none. The notice of `jbus.reload` is one."""
TOOLS = (
    "t3_thread_configure",
    "t3_thread_launch",
    "t3_thread_list",
    "t3_thread_read",
    "t3_thread_send",
    "link_pull_request",
    "t3_thread_organize",
    "orchestrator_capabilities",
    "list_scheduled_tasks",
    "schedule_task",
    "t3_project_list",
    "t3_project_update",
)
MISSING = "t3-tool "
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

        def log_message(self, format: str, *args: Any) -> None:
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
    position: int = -1

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
        """For a call to a tool that can change a thread, a task or a project, return why jbus does
        not make it, or nothing when jbus does make it."""
        if tool == "t3_thread_organize":
            if set(arguments) != {"action", "threadId"} or arguments["action"] not in (
                "settle",
                "archive",
                "unarchive",
            ):
                return "is only called to settle, archive or unarchive a thread it names"
            if not arguments["threadId"]:
                return "names no thread to settle, archive or unarchive"
        if tool == "schedule_task":
            if set(arguments) != {"scheduledTaskId", "enabled"} or not isinstance(
                arguments["enabled"], bool
            ):
                return "is only called to switch a task it names off or on"
            if not arguments["scheduledTaskId"]:
                return "names no task to switch off or on"
        if tool == "t3_project_update":
            if set(arguments) != {"projectId", "archived"} or not isinstance(
                arguments["archived"], bool
            ):
                return "is only called to archive or unarchive a project it names"
            if not arguments["projectId"]:
                return "names no project to archive or unarchive"
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
            key = arguments["clientRequestId"]
            steer = str(key).split("|")[0] in STEERS
            if not key or arguments["mode"] != ("auto" if steer else "queue"):
                return "is only called with mode queue and a retry key, or auto for a steer"
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
        return _message(thread, message, one, text, title)

    def asked_before(self, thread: str, position: int) -> Message | None:
        """Return the last message an agent wrote in the thread before the item at `position`,
        its assistant message, with its whole text, or None where none comes before it. It reads
        the thread's messages in a window that ends at `position` and widens until it finds one,
        or reaches the thread's start, so a long thread is not read whole."""
        span = 256
        while True:
            start = position - span
            after: int | None = start if start >= 0 else None
            before: list[dict[str, Any]] = []
            while True:
                asked: dict[str, Any] = {
                    "threadId": thread,
                    "view": "messages",
                    "limit": 100,
                    "maxCharsPerItem": 1,
                }
                if after is not None:
                    asked["afterPosition"] = after
                read = self.call("t3_thread_read", asked) or {}
                items = read.get("items") or []
                before += [one for one in items if int(one.get("position", position)) < position]
                further = read.get("nextPosition")
                done = not read.get("hasMore") or not isinstance(further, int)
                if done or further >= position or (after is not None and further <= after):
                    break
                after = further
            mine = [one for one in before if one.get("type") == "assistant_message"]
            if mine:
                last = mine[-1]
                one, text, title = self.item(thread, str(last.get("itemId") or ""))
                return _message(thread, str(last.get("messageId") or ""), one, text, title)
            if start < 0:
                return None
            span *= 4

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


def _message(thread: str, message: str, one: dict[str, Any], text: str, title: str) -> Message:
    """The `Message` of the item `one` of the thread, whose whole text is `text`. Raise
    `T3Refused` for one with no time."""
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
        position=int(one.get("position", -1)),
    )


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
    """Read the user's own message `<thread id>/<message id>` from T3 Code now (`own`), and
    return its text on one line, its time in the user's zone, and the title of its thread."""
    found = own(config, ref)
    words = " ".join(found.text.split())
    return queue.Said(words, config.user.stamp(found.at), found.title, True, ref)


def own(config: Config, ref: str) -> Message:
    """Read the user's own message `<thread id>/<message id>` from T3 Code now, and return it.

    A message that an agent or jbus sent into a thread is not the user's, and `own` refuses
    it. It also refuses a message that T3 Code does not return, and one with no words.
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
    if not found.text.split():
        raise Refused(f"refused: message {ref} has no words")
    return found


def homes(home: Path) -> set[str]:
    """The threads of the homes of a project whose root home is `home`: the root's and each
    scope's that has one now."""
    return {one for one in (thread_of(home), *(thread_of(s) for s, _, _ in scopes(home))) if one}


def home_ask(config: Config, home: Path, project: str, ref: str) -> tuple[Message, Message]:
    """Return the user's own message `ref` (`own`) and the ask it answers: the last message the
    home wrote in that thread before it. Refused where the thread is no home's of the project, or
    where nothing of the home's comes before the message."""
    thread = ref.partition("/")[0]
    if thread not in homes(home):
        raise Refused(f"refused: {thread} is no home's thread of {project}")
    said = own(config, ref)
    try:
        ask = Client(config.server, config.token_path).asked_before(thread, said.position)
    except T3Error as error:
        raise Refused(f"refused: T3 Code gave no message before {ref} ({error})") from error
    if ask is None:
        raise Refused(f"refused: no message of the home comes before {ref}")
    return said, ask


def asked_of(text: str, slug: str, others: frozenset[str] = frozenset()) -> list[str]:
    """The parts of a home's ask `text` that are about the row `slug`: each runs from a place it
    names the slug to the next place it names another row of `others`, so an ask about two rows
    says of each only what follows its name. None where the ask does not name the slug."""
    return _parts(text, {_row(slug)}, {_row(one) for one in others})


def names(text: str, slug: str, numbers: Collection[int]) -> bool:
    """Whether `text` names the row `slug` or one of its gates `numbers`, in the forms a person
    writes (`_row`, `_question`)."""
    lowered = text.lower()
    return any(re.search(one, lowered) for one in (_row(slug), *map(_question, numbers)))


def asks(
    text: str, slug: str, numbers: Collection[int], doors: Mapping[str, Collection[int]]
) -> bool:
    """Whether a home's ask `text` is about this door: the row `slug`, or one of its open gates
    `numbers`, whether or not it names other open doors too. `doors` holds each row's slug with
    its open door gates. The ask names a gate by its number, and a row by its slug, which stands
    for each of its open gates the ask does not name by number. So "question 250 stays held;
    question 251: may it go?" names both doors, and a plain reply to it opens each of them: a
    home asks about a door it does not want opened in a message of its own."""
    lowered = text.lower()
    gates = {*doors.get(slug, ()), *numbers}
    named: set[str | int] = {one for one in gates if re.search(_question(one), lowered)}
    if not named and re.search(_row(slug), lowered):
        named = set[str | int](gates or [slug])
    return bool(named & (set(numbers) or {slug}))


def _near(word: str) -> str:
    """A pattern for `word` and each word one edit from it: a letter left out, added, changed,
    or two side by side swapped, so `quetsion` is `question`."""
    near = {word}
    for at in range(len(word) + 1):
        near.add(f"{word[:at]}[a-z]{word[at:]}")
        near.add(f"{word[:at]}{word[at + 1 :]}")
        near.add(f"{word[:at]}[a-z]{word[at + 1 :]}")
        near.add(f"{word[:at]}{word[at + 1 : at + 2]}{word[at : at + 1]}{word[at + 2 :]}")
    return "(?:" + "|".join(sorted(near - {""}, key=len, reverse=True)) + ")"


_GATE = rf"(?:\b(?:{_near('question')}s?|gate)\s*#?\s*|\bq\s*|#)"
"""What comes before a gate's number where a person names it: `question 15` and its slips,
`gate 15`, `q15`, `Q 15` or `#15`, and a list after one of them, `questions 14 and 15`."""

_LISTED = r"(?:\d+(?:\s*(?:,|&|/|\band\b|\bor\b)\s*)+#?)*"
"""The numbers listed before a gate's own, as `14, ` or `14 and ` in `questions 14 and 15`."""


def _row(slug: str) -> str:
    """A slug as a word of its own, with a space or a run of them for any of its hyphens."""
    spelled = r"[-\s]+".join(map(re.escape, slug.split("-")))
    return queue._SLUG_IN.format(spelled)


def _question(number: int) -> str:
    return rf"{_GATE}{_LISTED}{number}(?![\w-]|\.\d)"


def _parts(text: str, mine: set[str], theirs: set[str]) -> list[str]:
    """The parts of `text` from each place a pattern of `mine` matches it, lowered, to the next
    place one of `theirs` does."""
    lowered = text.lower()
    marks = sorted(
        (found.start(), pattern in mine)
        for pattern in mine | theirs
        for found in re.finditer(pattern, lowered)
    )
    return [
        text[start : next((at for at, own in marks[place + 1 :] if not own), len(text))]
        for place, (start, own) in enumerate(marks)
        if own
    ]


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


def contract(
    config: Config, client: Client | None, now: datetime, say: Callable[[str], None]
) -> None:
    """Open the alert of each tool of `TOOLS` that T3 Code does not serve, end the alert of each
    it serves again, and end with no line the alert of a tool jbus no longer names."""
    if client is None:
        return
    try:
        served = {tool["name"] for tool in client.tools()}
    except (T3Error, ValueError, KeyError, TypeError) as error:
        say(f"wait: T3 Code's tools not known: {alert.why(error, config)}")
        return
    state = config.state_dir
    for key in alert.streaks(state):
        if key.startswith(MISSING) and key.removeprefix(MISSING) not in TOOLS:
            alert.retire(state, key)
    for tool in TOOLS:
        key = MISSING + tool
        if tool in served:
            line = alert.closed(config, key, f"T3 Code serves {tool} again")
        else:
            why = f"T3 Code no longer serves {tool}, a tool jbus calls: what calls it fails"
            line = alert.opened(config, key, why, now=now)
        if line:
            say(line)


def _t3(args: argparse.Namespace, config: Config) -> int:
    if args.verb == "login":
        login(config.server, config.token_path, wait=args.wait)
        print(f"signed in: the token is in {config.token_path}")
        return 0
    project = verbs.project(config, args.project)
    client = Client(config.server, config.token_path)
    arguments: dict[str, Any] = {
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
CHORES = (verbs.Chore(40, "the tools T3 Code serves", contract),)
