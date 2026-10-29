"""The T3 Code server, reached as an outside MCP client: the one transport every command shares.

`post` sends one request and `get_json` reads one page, and each says why it failed with no
URL beyond its path in the message (`T3Error`, `T3Refused`, `T3Dropped`). `Session` is one MCP
session at `<server>/mcp` with the bearer token that `jbus t3 login` keeps. What a command may
call through it is that command's own: jbus's `jbus.t3.Client` allows its eight tools.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from jsettings import Refused
from jsettings.store import read_json

PROTOCOL = "2025-06-18"


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


class Session:
    """One MCP session at `<server>/mcp`, with the bearer token kept at `token_path`. `_rpc`
    sends one JSON-RPC call and gives its result, and `_open` starts the session once."""

    def __init__(self, server: str, token_path: Path, *, timeout: float = 60) -> None:
        self.url = f"{server}/mcp"
        stored = read_json(token_path, {})
        self._bearer = (stored.get("token") or {}).get("access_token")
        if not self._bearer:
            raise Refused(f"refused: no token in {token_path}: run `jbus t3 login`")
        self._timeout = timeout
        self._session: str | None = None
        self._ids = 0

    def _rpc(self, method: str, params: dict[str, Any] | None, *, notify: bool = False) -> Any:
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
        if self._session:
            headers["mcp-session-id"] = self._session
            headers["mcp-protocol-version"] = PROTOCOL
        got, said = post(self.url, json.dumps(body).encode(), headers, self._timeout)
        self._session = got.get("mcp-session-id") or self._session
        if notify:
            return None
        text = said.decode()
        if "text/event-stream" in (got.get("content-type") or ""):
            replies = [json.loads(line[5:]) for line in text.splitlines() if line[:5] == "data:"]
        else:
            replies = [json.loads(text)] if text.strip() else []
        for reply in replies:
            if isinstance(reply, dict) and reply.get("id") == body["id"]:
                if "error" in reply:
                    raise T3Refused(f"{method}: {reply['error'].get('message', reply['error'])}")
                return reply.get("result")
        raise T3Error(f"{method}: the reply was lost")

    def _open(self) -> None:
        if self._session is None and self._ids == 0:
            self._rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "jbus", "version": "0.1.0"},
                },
            )
            self._rpc("notifications/initialized", None, notify=True)
