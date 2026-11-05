"""The HTTP server: MCP's Streamable HTTP transport at `/mcp`, and the OAuth endpoints.

It listens on `127.0.0.1` only, at `PORT`, and cloudflared passes the public hostname's
requests on to it. Its routes:

- `POST /mcp`: one JSON-RPC message, with a live access token, answered as JSON. A notification
  gets 202. Without a live token it answers 401, with `WWW-Authenticate` naming the protected
  resource metadata, which is how claude.ai starts its sign-in. `GET /mcp` gets 405: the server
  sends nothing unasked.
- `GET /.well-known/oauth-protected-resource` (and the same under `/mcp`), and
  `GET /.well-known/oauth-authorization-server`: the metadata (`jbus_mcp.oauth`).
- `GET /authorize`: the sign-in page; `POST /authorize`: its form, with the sign-in code.
- `POST /token`: the token endpoint, form-encoded.
- `GET /healthz`: `{"ok": true}`.

It refuses a `Host` that is neither the public hostname nor its own loopback address, and a
request whose `Origin` is neither its own nor claude.ai's. Each tool call is checked against the
tool table, counted against the reads' or the writes' window, logged, and run by the runner
(`jbus_mcp.run`), which systemd starts as the user jbus runs as for each connection to its
socket.
"""

from __future__ import annotations

import html
import json
import os
import socket
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from jbus_mcp import Refused, limits, mcp, oauth, state_dir, tools

__all__ = ["PORT", "App", "Answer", "Settings", "settings", "serve"]

PORT = 4391
LOOPBACK = "127.0.0.1"
RUNNER = "/run/jbus-mcp/run.sock"
BODY = tools.BRIEF + 16384
CLAUDE = "https://claude.ai"
JSON, PAGE = "application/json", "text/html; charset=utf-8"
POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://claude.ai; "
    "base-uri 'none'; frame-ancestors 'none'"
)
READS, WRITES, SIGN_INS = (60, 60.0), (10, 60.0), (20, 60.0)
RUN_WAIT = 330


@dataclass(frozen=True)
class Answer:
    status: int
    body: bytes = b""
    kind: str = JSON
    headers: tuple[tuple[str, str], ...] = ()


def said(status: int, body: Any, *headers: tuple[str, str]) -> Answer:
    return Answer(status, json.dumps(body).encode(), JSON, headers)


@dataclass(frozen=True)
class Settings:
    """What the environment sets: the public origin, the port, and the runner's socket."""

    origin: str
    port: int = PORT
    runner: str = RUNNER


def settings(environ: Mapping[str, str] | None = None) -> Settings:
    """`JBUS_MCP_ORIGIN` (required, `https://<host>`), `JBUS_MCP_PORT` and `JBUS_MCP_RUNNER`,
    the runner's socket."""
    env = os.environ if environ is None else environ
    origin = env.get("JBUS_MCP_ORIGIN", "").rstrip("/")
    parts = urlsplit(origin)
    if parts.scheme != "https" or not parts.hostname or parts.path or parts.query:
        raise Refused("refused: JBUS_MCP_ORIGIN is the public origin, as https://<host>")
    try:
        port = int(env.get("JBUS_MCP_PORT") or PORT)
    except ValueError:
        raise Refused("refused: JBUS_MCP_PORT is a port") from None
    runner = env.get("JBUS_MCP_RUNNER") or RUNNER
    if not os.path.isabs(runner):
        raise Refused("refused: JBUS_MCP_RUNNER is the runner socket's absolute path")
    return Settings(origin, port, runner)


def runner_socket(path: str, wait: float = RUN_WAIT) -> Callable[[str], dict[str, Any]]:
    """The call that hands one request to the runner: it writes the request to the runner's
    socket, closes its side, and reads the runner's one JSON line. systemd starts one runner,
    as the user jbus runs as, for each connection (`deploy/jbus-mcp-run.socket`)."""

    def call(request: str) -> dict[str, Any]:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as made:
                made.settimeout(wait)
                made.connect(path)
                made.sendall(request.encode())
                made.shutdown(socket.SHUT_WR)
                chunks = []
                while chunk := made.recv(65536):
                    chunks.append(chunk)
        except OSError as error:
            return {"refused": f"the runner did not answer: {error}"}
        try:
            return json.loads(b"".join(chunks).decode().strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"refused": "the runner said nothing it could read"}

    return call


class App:
    """What the server does, apart from HTTP."""

    def __init__(
        self,
        origin: str,
        store: oauth.Store,
        log: limits.Log,
        runner: Callable[[str], dict[str, Any]],
        windows: Mapping[str, limits.Window] | None = None,
    ) -> None:
        self.origin, self.store, self.log, self.runner = origin, store, log, runner
        self.host = urlsplit(origin).netloc
        self.windows = windows or {
            "reads": limits.Window(*READS),
            "writes": limits.Window(*WRITES),
            "sign_ins": limits.Window(*SIGN_INS),
        }

    def tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """One `tools/call`: checked, counted, logged, and run by the runner."""
        kept = limits.redacted(arguments) if isinstance(arguments, Mapping) else {}
        try:
            tool, _ = tools.call(name, arguments)
        except Refused as error:
            self.log.write("call", tool=name, arguments=kept, outcome="refused", why=str(error))
            return _text(str(error), True)
        wait = self.windows["writes" if tool.writes else "reads"].take()
        if wait:
            self.log.write("call", tool=name, arguments=kept, outcome="limited")
            return _text(f"rate limited: try again in {wait:.0f} s", True)
        started = time.monotonic()
        said = self.runner(json.dumps({"tool": name, "arguments": dict(arguments)}))
        ms = round((time.monotonic() - started) * 1000)
        if "refused" in said:
            why = str(said["refused"])
            self.log.write("call", tool=name, arguments=kept, outcome="refused", why=why, ms=ms)
            return _text(why, True)
        code = said.get("code")
        outcome = "ok" if code == 0 else "failed"
        self.log.write("call", tool=name, arguments=kept, outcome=outcome, code=code, ms=ms)
        parts = [str(said.get("stdout") or "").rstrip()]
        if said.get("stderr"):
            parts.append(f"stderr:\n{str(said['stderr']).rstrip()}")
        if said.get("cut"):
            parts.append("(cut: the output was longer than the runner keeps)")
        if code != 0:
            parts.append(f"jbus exited {code}")
        return _text("\n\n".join(part for part in parts if part) or "(no output)", code != 0)

    def challenge(self) -> Answer:
        metadata = f"{self.origin}/.well-known/oauth-protected-resource"
        header = f'Bearer resource_metadata="{metadata}", scope="{oauth.SCOPE}"'
        return said(401, {"error": "invalid_token"}, ("WWW-Authenticate", header))

    def get(self, path: str, query: Mapping[str, str]) -> Answer:
        if path == "/healthz":
            return said(200, {"ok": True})
        if path in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            return said(200, oauth.protected_resource(self.origin))
        if path == "/.well-known/oauth-authorization-server":
            return said(200, oauth.authorization_server(self.origin))
        if path == "/authorize":
            try:
                asked = self.store.asked(query)
            except oauth.Failed as failed:
                return _page(400, failed.description)
            return _page(200, "", asked)
        if path == "/mcp":
            return said(405, {"error": "this server sends nothing unasked"}, ("Allow", "POST"))
        return said(404, {"error": "no such address"})

    def post(self, path: str, body: bytes, authorization: str, kind: str) -> Answer:
        if path == "/mcp":
            return self._mcp(body, authorization, kind)
        if path not in ("/authorize", "/token"):
            return said(404, {"error": "no such address"})
        if self.windows["sign_ins"].take():
            self.log.write("sign-in", step=path, outcome="limited")
            return said(429, {"error": "slow_down"}, ("Retry-After", "60"))
        form = {
            key: values[-1] for key, values in parse_qs(body.decode("utf-8", "replace")).items()
        }
        if path == "/authorize":
            return self._authorize(form)
        try:
            answer = self.store.token(form, authorization)
        except oauth.Failed as failed:
            self.log.write("sign-in", step="token", outcome=failed.error)
            extra = (("WWW-Authenticate", "Basic"),) if failed.status == 401 else ()
            return said(failed.status, failed.body(), *extra)
        self.log.write("sign-in", step="token", outcome="ok", grant=form.get("grant_type"))
        return said(200, answer, ("Pragma", "no-cache"))

    def _authorize(self, form: Mapping[str, str]) -> Answer:
        try:
            asked = self.store.asked(form)
        except oauth.Failed as failed:
            return _page(400, failed.description)
        try:
            back = self.store.grant(asked, form.get("sign_in_code", ""))
        except oauth.Failed as failed:
            self.log.write("sign-in", step="authorize", outcome="denied")
            return _page(403, failed.description, asked)
        self.log.write("sign-in", step="authorize", outcome="ok")
        return Answer(302, b"", PAGE, (("Location", back),))

    def _mcp(self, body: bytes, authorization: str, kind: str) -> Answer:
        if not self.store.allows(authorization):
            return self.challenge()
        if kind.split(";")[0].strip().lower() != JSON:
            return said(415, {"error": "a message is application/json"})
        try:
            message = json.loads(body)
        except ValueError:
            return said(400, mcp.error(None, mcp.PARSE, "the body is not JSON"))
        if isinstance(message, list):
            return said(400, mcp.error(None, mcp.INVALID, "send one message, not a batch"))
        response = mcp.answer(message, self.tool)
        return Answer(202) if response is None else said(200, response)


def _text(text: str, failed: bool) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": failed}


def _page(status: int, problem: str, asked: oauth.Asked | None = None) -> Answer:
    """The sign-in page: the form for the sign-in code, or only the problem where the request
    cannot go on."""
    shown = f'<p class="problem">{html.escape(problem)}</p>' if problem else ""
    form = ""
    if asked is not None:
        fields = {
            "client_id": asked.client_id,
            "redirect_uri": asked.redirect_uri,
            "response_type": "code",
            "state": asked.state,
            "code_challenge": asked.challenge,
            "code_challenge_method": "S256",
            "scope": asked.scope,
            "resource": asked.resource,
        }
        hidden = "".join(
            f'<input type="hidden" name="{key}" value="{html.escape(value)}">'
            for key, value in fields.items()
        )
        back = html.escape(urlsplit(asked.redirect_uri).hostname or "")
        form = (
            f"<p>A connector asks to use the jbus tools on this machine. It returns to "
            f"<strong>{back}</strong>.</p>"
            "<p>Make a sign-in code on the machine with <code>jbus-mcp code</code>, run as the "
            "server's user, and type it here.</p>"
            f'<form method="post" action="/authorize">{hidden}'
            '<label>Sign-in code <input name="sign_in_code" autocomplete="one-time-code" '
            'autofocus required></label> <button type="submit">Let it in</button></form>'
        )
    text = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>jbus-mcp sign-in</title><style>body{font:16px/1.5 system-ui,sans-serif;"
        "max-width:32rem;margin:2rem auto;padding:0 1rem}.problem{color:#b00020}"
        "input{font:inherit}</style></head><body><h1>jbus-mcp</h1>"
        f"{shown}{form}</body></html>"
    )
    return Answer(status, text.encode(), PAGE, (("Content-Security-Policy", POLICY),))


class Handler(BaseHTTPRequestHandler):
    server_version = "jbus-mcp"
    sys_version = ""

    @property
    def bound(self) -> Server:
        assert isinstance(self.server, Server)
        return self.server

    def _send(self, answer: Answer) -> None:
        self.send_response(answer.status)
        self.send_header("Content-Type", answer.kind)
        self.send_header("Content-Length", str(len(answer.body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in answer.headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(answer.body)

    def _allowed(self) -> Answer | None:
        app, host = self.bound.app, self.headers.get("Host", "").lower()
        own = {app.host.lower(), f"{LOOPBACK}:{self.bound.server_port}"}
        if host not in own:
            return said(403, {"error": "this is not the server's name"})
        origin = self.headers.get("Origin")
        if origin is not None and origin.lower() not in {app.origin.lower(), CLAUDE}:
            return said(403, {"error": "this origin may not call the server"})
        return None

    def _path(self) -> tuple[str, dict[str, str]]:
        path, _, query = self.path.partition("?")
        return path, {key: values[-1] for key, values in parse_qs(query).items()}

    def do_GET(self) -> None:
        refused = self._allowed()
        if refused:
            self._send(refused)
            return
        path, query = self._path()
        self._send(self._guard(lambda: self.bound.app.get(path, query)))

    def do_POST(self) -> None:
        refused = self._allowed()
        if refused:
            self._send(refused)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if not 0 <= length <= BODY:
            self._send(
                said(413 if length > BODY else 411, {"error": "a short body, with its length"})
            )
            return
        body = self.rfile.read(length)
        path, _ = self._path()
        key, kind = self.headers.get("Authorization", ""), self.headers.get("Content-Type", "")
        self._send(self._guard(lambda: self.bound.app.post(path, body, key, kind)))

    def _guard(self, answer: Callable[[], Answer]) -> Answer:
        try:
            return answer()
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return said(500, {"error": "the server could not answer"})

    def _not_allowed(self) -> None:
        self._send(said(405, {"error": "this address takes GET or POST"}, ("Allow", "GET, POST")))

    do_PUT = do_DELETE = do_PATCH = _not_allowed

    def log_message(self, format: str, *args: Any) -> None:
        return


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    app: App


def bind(app: App, port: int) -> Server:
    """A server for the app on `127.0.0.1`, at the port, or at a free one for port 0."""
    made = Server((LOOPBACK, port), Handler)
    made.app = app
    return made


def serve(given: Settings | None = None) -> int:
    """Serve until something stops the process."""
    chosen = given or settings()
    where = state_dir()
    app = App(
        chosen.origin,
        oauth.Store(where / oauth.FILE, chosen.origin),
        limits.Log(where / limits.FILE),
        runner_socket(chosen.runner),
    )
    made = bind(app, chosen.port)
    print(f"jbus-mcp: listening on {LOOPBACK}:{made.server_port} for {chosen.origin}", flush=True)
    try:
        made.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        made.server_close()
    return 0
