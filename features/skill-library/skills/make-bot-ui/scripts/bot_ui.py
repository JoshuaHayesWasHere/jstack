# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""A bot UI's server: it serves one page, and passes each press of a button on to a T3 Code
webhook task, so that the browser never holds the webhook's URL or its key.

The URL and the key are in one JSON file, `{"url": ..., "key": ...}`, at mode 600, and in no
other place. Each POST to the webhook carries the key twice, `Authorization: Bearer <key>` and
`X-Automation-Key: <key>`, as `jbus` posts the Chef, and the HMAC-SHA256 of the body under the
key in `SIGNATURE`, which the task's `signature` checks. It is one try with a timeout of
`TIMEOUT` seconds: a POST that fails is appended to `failed.jsonl` beside the config, with the
URL and the key taken out of the reason, and the page is told it failed.

It always listens on `127.0.0.1`, and on `--host` too when that is given: an address of this
machine, as its tailnet one, never every address, as `jbus view` does. A request whose `Host`
is not one of the server's own names is 403, and a POST whose `Origin` is not `http://<Host>`
is 403, so only the server's own page can press a button.

    bot_ui.py key <config>              write a config with a new random key, url empty
    bot_ui.py show-key <config>         print the key, to pipe into `clip`
    bot_ui.py url <config> <url>        put the webhook URL in the config
    bot_ui.py probe <config>            POST {"action": "probe"} once, which the task ignores
    bot_ui.py serve <config> --page <dir> --port <n> [--host <ip>] [--name <host name>]...
"""

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socketserver
import stat
import sys
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOOPBACK = "127.0.0.1"
TIMEOUT = 8.0
SIGNATURE = "X-Signature-256"
PREFIX = "sha256="
PROBE = {"action": "probe"}
FAILED = "failed.jsonl"
LIMIT = 64 * 1024


class Refused(Exception):
    """A config, an address or a request this server will not take."""


class Server(ThreadingHTTPServer):
    """A `ThreadingHTTPServer` that binds without asking DNS for a name of its address.

    `HTTPServer.server_bind` calls `socket.getfqdn` before it listens, and a resolver slow to
    answer for `127.0.0.2` kept that address from listening for seconds after `127.0.0.1` did.
    """

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def load(config: Path) -> dict:
    """The config, refused unless it is a file at mode 600 with a key."""
    try:
        mode = stat.S_IMODE(config.stat().st_mode)
    except FileNotFoundError:
        raise Refused(f"refused: {config} does not exist, run `key` first") from None
    if mode != 0o600:
        raise Refused(f"refused: {config} is mode {mode:o}, it must be 600")
    data = json.loads(config.read_text())
    if not data.get("key"):
        raise Refused(f"refused: {config} has no key")
    return data


def save(config: Path, data: dict) -> None:
    config.parent.mkdir(parents=True, exist_ok=True)
    written = config.with_name(f".{config.name}.{os.getpid()}")
    descriptor = os.open(written, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        json.dump(data, file)
    os.replace(written, config)


def sign(key: str, body: bytes) -> str:
    return PREFIX + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def post(config: Path, payload: dict) -> str | None:
    """POST `payload` to the webhook once. None when it was taken, else why it was not, which
    is also appended to the failure log with the body."""
    data = load(config)
    url, key = data.get("url") or "", data["key"]
    body = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "X-Automation-Key": key,
            SIGNATURE: sign(key, body),
            "User-Agent": "bot-ui",
        },
    )
    try:
        if not url:
            raise Refused("the config has no url")
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            if 200 <= answer.status < 300:
                return None
            why = f"HTTP {answer.status}"
    except urllib.error.HTTPError as error:
        why = f"HTTP {error.code}"
    except Exception as error:
        why = str(getattr(error, "reason", error)) or type(error).__name__
    if url:
        why = why.replace(url, "<url>")
    why = why.replace(key, "<key>")
    line = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "why": why, "body": payload}
    with open(config.parent / FAILED, "a") as log:
        log.write(json.dumps(line) + "\n")
    return why


def handler(config: Path, page: Path, names: frozenset[str]) -> type:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(page), **kwargs)

        def _ours(self) -> bool:
            if (self.headers.get("Host") or "").lower() not in names:
                self.send_error(HTTPStatus.FORBIDDEN, "not this server's name")
                return False
            return True

        def do_GET(self):
            if self._ours():
                super().do_GET()

        def do_HEAD(self):
            if self._ours():
                super().do_HEAD()

        def do_POST(self):
            if not self._ours():
                return
            if self.path != "/send":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
                self.send_error(HTTPStatus.FORBIDDEN, "only this server's page may send")
                return
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= LIMIT:
                self.send_error(HTTPStatus.BAD_REQUEST, "a body of one JSON object")
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except ValueError:
                payload = None
            if not isinstance(payload, dict):
                self.send_error(HTTPStatus.BAD_REQUEST, "a body of one JSON object")
                return
            why = post(config, payload)
            answer = json.dumps({"sent": why is None, "why": why}).encode()
            self.send_response(HTTPStatus.OK if why is None else HTTPStatus.BAD_GATEWAY)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)

    return Handler


def addresses(host: str | None) -> list[str]:
    """`127.0.0.1`, and `host` when it is another address of this machine: never every one."""
    if host is None or host == LOOPBACK:
        return [LOOPBACK]
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise Refused(f"refused: --host {host!r} is not an address") from None
    if address.is_unspecified:
        raise Refused(f"refused: --host {host} is every address, name one")
    return [LOOPBACK, host]


def serve(config: Path, page: Path, port: int, host: str | None, names: list[str]) -> None:
    load(config)
    bound = addresses(host)
    known = {f"{name}:{port}" for name in [*bound, "localhost", *names]}
    servers = [Server((one, port), handler(config, page, frozenset(known))) for one in bound]
    for server in servers:
        print(f"bot ui: listening on {server.server_address[0]}:{port}", flush=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("key", "show-key", "url", "probe", "serve"):
        one = verbs.add_parser(verb)
        one.add_argument("config", type=Path)
        if verb == "url":
            one.add_argument("url")
        if verb == "serve":
            one.add_argument("--page", type=Path, required=True)
            one.add_argument("--port", type=int, required=True)
            one.add_argument("--host")
            one.add_argument("--name", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.verb == "key":
            if args.config.exists():
                raise Refused(f"refused: {args.config} exists, its key stays")
            save(args.config, {"url": "", "key": secrets.token_urlsafe(32)})
        elif args.verb == "show-key":
            sys.stdout.write(load(args.config)["key"])
        elif args.verb == "url":
            save(args.config, {**load(args.config), "url": args.url})
        elif args.verb == "probe":
            why = post(args.config, PROBE)
            print("probe: taken" if why is None else f"probe: not taken, {why}")
            return 0 if why is None else 1
        else:
            serve(args.config, args.page, args.port, args.host, args.name)
    except Refused as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
