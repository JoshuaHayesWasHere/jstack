"""The T3 Code server, reached as an outside MCP client: the one transport every command shares.

`post` sends one request and `get_json` reads one page, and each says why it failed with no
URL beyond its path in the message (`T3Error`, `T3Refused`, `T3Dropped`). `Session` is one MCP
session at `<server>/mcp` with the bearer token that `jbus t3 login` keeps. What a command may
call through it is that command's own: jbus's `jbus.t3.Client` allows its eight tools. `expiry`
says when the token that `jbus t3 login` keeps runs out.
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

from jsettings import Refused
from jsettings.store import read_json

PROTOCOL = "2025-06-18"
LIFETIME = 30 * 24 * 60 * 60


class T3Error(Exception):
    """The server gave no answer: jbus could not reach it, or its reply was lost."""


class T3Refused(T3Error):
    """The server answered no, and made nothing."""


class T3Dropped(T3Error):
    """The connection dropped (ECONNRESET) before the server gave any reply."""


def _at(url: str) -> str:
    """Name the server by its path only, since no message from jbus carries a URL."""
    return f"T3 Code at {urllib.parse.urlsplit(url).path}"


def post(url: str, body: bytes, headers: dict[str, str], timeout: float) -> tuple[Any, Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return reply.headers, reply.read()
    except urllib.error.HTTPError as error:
        said = error.read().decode(errors="replace")[:200]
        kind = T3Refused if 400 <= error.code < 500 else T3Error
        raise kind(f"{_at(url)} answered {error.code}: {said}") from error
    except (OSError, ValueError) as error:
        reset = isinstance(error, ConnectionResetError) or isinstance(
            getattr(error, "reason", None), ConnectionResetError
        )
        kind = T3Dropped if reset else T3Error
        raise kind(f"{_at(url)} could not be reached: {error}") from error


def get_json(url: str, timeout: float = 8) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as reply:
            return json.loads(reply.read())
    except (OSError, ValueError) as error:
        raise T3Error(f"{_at(url)} could not be read: {error}") from error


@dataclass(frozen=True)
class Open:
    """The session the server opened, by its `mcp-session-id`."""

    session: str


FRESH: Final = "fresh"
CLOSED: Final = "closed"
State = Literal["fresh", "closed"] | Open


class Session:
    """One MCP session at `<server>/mcp`, with the bearer token kept at `token_path`.

    Its state is fresh, `Open` or closed, and only `Open` holds a session id. `_open` opens the
    session unless it is open, and `_rpc` sends one call in it, opening it first. A fresh or
    closed session sends nothing but an initialize, so an initialize that failed, or a `close`,
    costs the next call one initialize and no more.
    """

    def __init__(self, server: str, token_path: Path, *, timeout: float = 60) -> None:
        self.url = f"{server}/mcp"
        stored = read_json(token_path, {})
        self._bearer = (stored.get("token") or {}).get("access_token")
        if not self._bearer:
            raise Refused(f"refused: no token in {token_path}: run `jbus t3 login`")
        self._timeout = timeout
        self._state: State = FRESH
        self._ids = 0

    def _send(
        self, method: str, params: dict[str, Any] | None, session: str | None, *, notify: bool
    ) -> tuple[Any, Any]:
        """Post one JSON-RPC message, in `session` or, for an initialize, in none. Give the
        reply's headers and its result."""
        self._ids += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            body["id"] = self._ids
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "authorization": f"Bearer {self._bearer}",
        }
        if session is not None:
            headers["mcp-session-id"] = session
            headers["mcp-protocol-version"] = PROTOCOL
        got, said = post(self.url, json.dumps(body).encode(), headers, self._timeout)
        if notify:
            return got, None
        text = said.decode()
        if "text/event-stream" in (got.get("content-type") or ""):
            replies = [json.loads(line[5:]) for line in text.splitlines() if line[:5] == "data:"]
        else:
            replies = [json.loads(text)] if text.strip() else []
        for reply in replies:
            if isinstance(reply, dict) and reply.get("id") == body["id"]:
                if "error" in reply:
                    raise T3Refused(f"{method}: {reply['error'].get('message', reply['error'])}")
                return got, reply.get("result")
        raise T3Error(f"{method}: the reply was lost")

    def _open(self) -> str:
        """Give the open session's id, opening a new session first unless one is open."""
        if isinstance(self._state, Open):
            return self._state.session
        hello = {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "jbus", "version": "0.1.0"},
        }
        got, _ = self._send("initialize", hello, None, notify=False)
        session = got.get("mcp-session-id")
        if not session:
            raise T3Error("initialize: the server opened no session")
        self._send("notifications/initialized", None, session, notify=True)
        self._state = Open(session)
        return session

    def _rpc(self, method: str, params: dict[str, Any] | None) -> Any:
        """Send one call in the open session, opening it first, and give its result."""
        return self._send(method, params, self._open(), notify=False)[1]

    def close(self) -> None:
        """End the session at the server, which otherwise keeps it. A session the server cannot
        end now is left to it: `close` does not raise. A later call opens a new session."""
        state, self._state = self._state, CLOSED
        if not isinstance(state, Open):
            return
        headers = {
            "authorization": f"Bearer {self._bearer}",
            "mcp-session-id": state.session,
            "mcp-protocol-version": PROTOCOL,
        }
        request = urllib.request.Request(self.url, headers=headers, method="DELETE")
        with contextlib.suppress(OSError, ValueError):
            urllib.request.urlopen(request, timeout=self._timeout).close()


def _seconds(value: Any) -> float | None:
    real = isinstance(value, int | float) and not isinstance(value, bool)
    return float(value) if real and value > 0 else None


def expiry(token_path: Path) -> datetime | None:
    """Return when the stored token runs out, or None when no token is stored.

    The token was obtained at `obtained_at`. For a token stored before jbus recorded that time,
    `expiry` takes the time that the token's file was last written. The token lasts its own
    `expires_in` seconds, or `LIFETIME` when it has no `expires_in`. `expiry` does not read the
    token itself.
    """
    stored = read_json(token_path, {})
    token = stored.get("token") if isinstance(stored, dict) else None
    if not isinstance(token, dict) or not token.get("access_token"):
        return None
    obtained = _seconds(stored.get("obtained_at"))
    if obtained is None:
        try:
            obtained = token_path.stat().st_mtime
        except OSError:
            return None
    return datetime.fromtimestamp(obtained + (_seconds(token.get("expires_in")) or LIFETIME), UTC)
