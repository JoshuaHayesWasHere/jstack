"""The server over real HTTP on loopback: the metadata, the 401 that starts claude.ai's
sign-in, the sign-in page and its code, the token, and MCP's tools, each logged and counted."""

import base64
import hashlib
import json
import threading
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from jbus_mcp import Refused, limits, oauth, server

ORIGIN = "https://jbus.example.test"
VERIFIER = "z" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPEN = urllib.request.build_opener(NoRedirect)


class Running:
    def __init__(self, tmp_path, runner, windows=None):
        self.asked = []

        def recorded(text):
            self.asked.append(json.loads(text))
            return runner(text)

        self.store = oauth.Store(tmp_path / oauth.FILE, ORIGIN)
        self.log = limits.Log(tmp_path / limits.FILE)
        self.app = server.App(ORIGIN, self.store, self.log, recorded, windows)
        self.http = server.bind(self.app, 0)
        self.base = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def send(self, method, path, body=None, headers=None, host=None):
        given = {"Host": host or "jbus.example.test", **(headers or {})}
        data = body.encode() if isinstance(body, str) else body
        request = urllib.request.Request(self.base + path, data, given, method=method)
        try:
            with OPEN.open(request, timeout=10) as done:
                return done.status, dict(done.headers), done.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read().decode()

    def mcp(self, message, token):
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        return self.send("POST", "/mcp", json.dumps(message), headers)

    def sign_in(self):
        client_id, secret = self.store.make_client()
        query = {
            "client_id": client_id,
            "redirect_uri": oauth.CALLBACK,
            "response_type": "code",
            "state": "st",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
        }
        status, headers, page = self.send("GET", "/authorize?" + urlencode(query))
        assert status == 200
        assert "claude.ai" in page
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        form = {**query, "sign_in_code": self.store.make_code()}
        status, headers, _ = self.send(
            "POST",
            "/authorize",
            urlencode(form),
            {"Content-Type": "application/x-www-form-urlencoded", "Origin": ORIGIN},
        )
        assert status == 302
        back = parse_qs(urlsplit(headers["Location"]).query)
        token_form = {
            "grant_type": "authorization_code",
            "code": back["code"][0],
            "redirect_uri": oauth.CALLBACK,
            "code_verifier": VERIFIER,
            "client_id": client_id,
            "client_secret": secret,
        }
        status, headers, body = self.send(
            "POST",
            "/token",
            urlencode(token_form),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        return json.loads(body)["access_token"]

    def close(self):
        self.http.shutdown()
        self.http.server_close()


def ran(text):
    return {"code": 0, "stdout": f"ran {json.loads(text)['tool']}\n", "stderr": "", "cut": False}


@pytest.fixture
def running(tmp_path):
    made = Running(tmp_path, ran)
    yield made
    made.close()


def test_an_unsigned_call_gets_the_401_that_starts_the_sign_in(running):
    status, headers, _ = running.mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, "x")
    assert status == 401
    assert headers["WWW-Authenticate"] == (
        f'Bearer resource_metadata="{ORIGIN}/.well-known/oauth-protected-resource", scope="jbus"'
    )
    status, _, body = running.send("GET", "/.well-known/oauth-protected-resource")
    assert json.loads(body)["resource"] == f"{ORIGIN}/mcp"
    status, _, body = running.send("GET", "/.well-known/oauth-authorization-server")
    assert json.loads(body)["token_endpoint"] == f"{ORIGIN}/token"


def test_a_signed_in_connector_lists_and_calls_the_tools(running):
    token = running.sign_in()
    status, _, body = running.mcp(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        token,
    )
    assert status == 200
    assert json.loads(body)["result"]["protocolVersion"] == "2025-06-18"
    status, _, body = running.mcp({"jsonrpc": "2.0", "method": "notifications/initialized"}, token)
    assert (status, body) == (202, "")
    status, _, body = running.mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, token)
    assert len(json.loads(body)["result"]["tools"]) == 7
    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "jbus_queue_add",
            "arguments": {"project": "jstack", "slug": "alpha", "priority": 1, "brief": "# A\n"},
        },
    }
    status, _, body = running.mcp(call, token)
    result = json.loads(body)["result"]
    assert result == {"content": [{"type": "text", "text": "ran jbus_queue_add"}], "isError": False}
    assert running.asked[-1]["arguments"]["brief"] == "# A\n"
    logged = [one for one in running.log.lines() if one["kind"] == "call"]
    assert logged[-1]["outcome"] == "ok"
    assert logged[-1]["arguments"]["brief"]["chars"] == 4
    assert "# A" not in (running.log.path).read_text(encoding="utf-8")


def test_a_refused_tool_never_reaches_the_runner(running):
    token = running.sign_in()
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "jbus_queue_approve", "arguments": {"project": "jstack", "slug": "-x"}},
    }
    _, _, body = running.mcp(call, token)
    assert json.loads(body)["result"]["isError"] is True
    assert running.asked == []
    assert running.log.lines()[-1]["outcome"] == "refused"


def test_writes_are_rate_limited(tmp_path):
    windows = {
        "reads": limits.Window(5, 60),
        "writes": limits.Window(1, 60),
        "sign_ins": limits.Window(20, 60),
    }
    made = Running(tmp_path, ran, windows)
    try:
        token = made.sign_in()
        call = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "jbus_answer",
                "arguments": {
                    "project": "jstack",
                    "number": 2,
                    "message": "t/m",
                    "keeps_default": True,
                },
            },
        }
        first = json.loads(made.mcp(call, token)[2])["result"]
        second = json.loads(made.mcp(call, token)[2])["result"]
        assert first["isError"] is False
        assert second["isError"] is True
        assert "rate limited" in second["content"][0]["text"]
        assert len(made.asked) == 1
    finally:
        made.close()


def test_a_failing_jbus_is_an_error_result_with_its_output(tmp_path):
    def failing(text):
        return {"code": 1, "stdout": "refused: no such row", "stderr": "", "cut": False}

    made = Running(tmp_path, failing)
    try:
        token = made.sign_in()
        call = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "jbus_status", "arguments": {}},
        }
        result = json.loads(made.mcp(call, token)[2])["result"]
        assert result["isError"] is True
        assert "refused: no such row" in result["content"][0]["text"]
        assert "jbus exited 1" in result["content"][0]["text"]
    finally:
        made.close()


def test_a_wrong_sign_in_code_shows_the_page_again(running):
    client_id, _ = running.store.make_client()
    running.store.make_code()
    form = {
        "client_id": client_id,
        "redirect_uri": oauth.CALLBACK,
        "response_type": "code",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "sign_in_code": "AAAA-AAAA",
    }
    status, _, page = running.send(
        "POST", "/authorize", urlencode(form), {"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert status == 403
    assert "not the sign-in code" in page
    assert 'name="sign_in_code"' in page


@pytest.mark.parametrize(
    ("method", "path", "headers", "host", "status"),
    [
        ("GET", "/healthz", {}, "evil.test", 403),
        ("GET", "/healthz", {"Origin": "https://evil.test"}, None, 403),
        ("GET", "/mcp", {}, None, 405),
        ("DELETE", "/mcp", {}, None, 405),
        ("GET", "/nothing", {}, None, 404),
    ],
)
def test_it_refuses_what_is_not_its_own(running, method, path, headers, host, status):
    assert running.send(method, path, None, headers, host)[0] == status


def test_loopback_is_its_own_name_too(running):
    host = f"127.0.0.1:{running.http.server_port}"
    assert running.send("GET", "/healthz", host=host)[0] == 200


def test_a_batch_and_a_body_that_is_not_json_are_refused(running):
    token = running.sign_in()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    assert running.send("POST", "/mcp", "[]", headers)[0] == 400
    assert running.send("POST", "/mcp", "{", headers)[0] == 400
    headers["Content-Type"] = "text/plain"
    assert running.send("POST", "/mcp", "{}", headers)[0] == 415


@pytest.mark.parametrize(
    ("environ", "why"),
    [
        ({}, "JBUS_MCP_ORIGIN"),
        ({"JBUS_MCP_ORIGIN": "http://x.test"}, "JBUS_MCP_ORIGIN"),
        ({"JBUS_MCP_ORIGIN": ORIGIN + "/mcp"}, "JBUS_MCP_ORIGIN"),
        ({"JBUS_MCP_ORIGIN": ORIGIN, "JBUS_MCP_RUNNER": "run.sock"}, "absolute"),
    ],
)
def test_the_settings_refuse_what_cannot_serve(environ, why):
    with pytest.raises(Refused, match=why):
        server.settings(environ)


def test_the_settings_take_the_environment():
    made = server.settings({"JBUS_MCP_ORIGIN": ORIGIN + "/"})
    assert made == server.Settings(ORIGIN, server.PORT, server.RUNNER)


def test_the_runner_socket_carries_one_request_and_its_answer(tmp_path):
    import socket

    path = str(tmp_path / "run.sock")
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listening.bind(path)
    listening.listen(1)
    heard = []

    def answer():
        connection, _ = listening.accept()
        with connection:
            chunks = []
            while chunk := connection.recv(4096):
                chunks.append(chunk)
            heard.append(json.loads(b"".join(chunks)))
            connection.sendall(b'{"code": 0, "stdout": "ok", "stderr": ""}\n')

    thread = threading.Thread(target=answer)
    thread.start()
    said = server.runner_socket(path, 5)(json.dumps({"tool": "jbus_status"}))
    thread.join()
    listening.close()
    assert heard == [{"tool": "jbus_status"}]
    assert said["stdout"] == "ok"
    assert "refused" in server.runner_socket(str(tmp_path / "none.sock"), 1)("{}")
