"""A `Session` is fresh, open or closed, and sends no call without a session id unless open.

The server here is a small MCP server on a local port that answers as T3 Code does: a call
with no session id it knows gets HTTP 400, and it can drop the connection (ECONNRESET) on an
initialize. Each test drives the session the way jbus's `Client` does: `_open`, then `_rpc`.
"""

import contextlib
import json
import socket
import struct
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jsettings.t3 import Session, T3Dropped


class Server(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.drops = 0
        self.live: set[str] = set()
        self.seen: list[tuple[str, str | None]] = []
        self.ended: list[str | None] = []

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *_):
        pass

    def finish(self):
        with contextlib.suppress(OSError, ValueError):
            super().finish()

    def do_DELETE(self):
        session = self.headers.get("mcp-session-id")
        self.server.ended.append(session)
        self.server.live.discard(session or "")
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        asked = json.loads(self.rfile.read(int(self.headers["content-length"])))
        session = self.headers.get("mcp-session-id")
        self.server.seen.append((asked["method"], session))
        if asked["method"] == "initialize":
            if self.server.drops:
                self.server.drops -= 1
                self.connection.setsockopt(
                    socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                )
                self.close_connection = True
                self.connection.close()
                return None
            session = f"session-{uuid.uuid4().hex[:8]}"
            self.server.live.add(session)
        elif session not in self.server.live:
            return self.reply(400, b"Bad Request: No valid session ID provided", session)
        if "id" not in asked:
            return self.reply(202, b"", session)
        said = {"jsonrpc": "2.0", "id": asked["id"], "result": {"tools": []}}
        return self.reply(200, json.dumps(said).encode(), session)

    def reply(self, code, body, session):
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        if session:
            self.send_header("mcp-session-id", session)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    made = Server()
    threading.Thread(target=made.serve_forever, daemon=True).start()
    yield made
    made.shutdown()
    made.server_close()


@pytest.fixture
def session(server, tmp_path):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"token": {"access_token": "a-token"}}))
    made = Session(server.url, token, timeout=5)
    yield made
    made.close()


def call(session):
    session._open()
    return session._rpc("tools/list", {})


def test_an_initialize_that_dropped_is_sent_again_on_the_next_call(server, session):
    server.drops = 1
    with pytest.raises(T3Dropped):
        call(session)
    assert call(session) == {"tools": []}
    methods = [method for method, _ in server.seen]
    assert methods == ["initialize", "initialize", "notifications/initialized", "tools/list"]
    opened = server.seen[-1][1]
    assert opened in server.live
    assert all(sent == opened for method, sent in server.seen if method != "initialize")


def test_a_call_after_close_opens_a_new_session(server, session):
    call(session)
    first = server.seen[-1][1]
    session.close()
    assert server.ended == [first]
    assert call(session) == {"tools": []}
    second = server.seen[-1][1]
    assert second in server.live and second != first
    assert [method for method, _ in server.seen].count("initialize") == 2
