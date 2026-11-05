"""The refusals and the rarer paths: each malformed message, form, token request, header and
runner answer gets its own error, the log trims itself past its cap, and `serve` starts and
stops on its settings."""

import base64
import hashlib
import http.client
import io
import json
import shutil
import socket
import subprocess
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jbus_mcp import Refused, deploy, limits, mcp, oauth, run, server, state_dir, tools

ORIGIN = "https://jbus.example.test"
HOST = "jbus.example.test"
VERIFIER = "w" * 50
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def challenge():
    digest = hashlib.sha256(VERIFIER.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def ran(text):
    return {"code": 0, "stdout": "ok\n", "stderr": "", "cut": False}


class Up:
    def __init__(self, tmp_path, runner=ran, windows=None):
        self.store = oauth.Store(tmp_path / oauth.FILE, ORIGIN)
        self.log = limits.Log(tmp_path / limits.FILE)
        self.app = server.App(ORIGIN, self.store, self.log, runner, windows)
        self.http = server.bind(self.app, 0)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def raw(self, method, path, body=b"", headers=None, length=None):
        made = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=10)
        try:
            made.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            given = {"Host": HOST, **(headers or {})}
            if length is not None:
                given["Content-Length"] = length
            for name, value in given.items():
                made.putheader(name, value)
            made.endheaders(body or None)
            done = made.getresponse()
            return done.status, dict(done.getheaders()), done.read().decode()
        finally:
            made.close()

    def post(self, path, body, headers=None):
        data = body.encode() if isinstance(body, str) else body
        return self.raw("POST", path, data, headers, str(len(data)))

    def token(self):
        client_id, secret = self.store.make_client()
        asked = self.store.asked(
            {
                "client_id": client_id,
                "redirect_uri": oauth.CALLBACK,
                "response_type": "code",
                "code_challenge": challenge(),
                "code_challenge_method": "S256",
            }
        )
        back = self.store.grant(asked, self.store.make_code())
        code = back.split("code=")[1].split("&")[0]
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": oauth.CALLBACK,
            "code_verifier": VERIFIER,
            "client_id": client_id,
            "client_secret": secret,
        }
        return self.store.token(form)["access_token"]

    def call(self, token, name, arguments):
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        status, _, body = self.post("/mcp", json.dumps(message), headers)
        return status, json.loads(body)

    def close(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def up(tmp_path):
    made = Up(tmp_path)
    yield made
    made.close()


@pytest.mark.parametrize(
    ("message", "code", "why"),
    [
        ([], mcp.INVALID, "JSON-RPC 2.0"),
        ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, mcp.INVALID, "JSON-RPC 2.0"),
        ({"jsonrpc": "2.0", "id": 1}, mcp.INVALID, "names its method"),
        ({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": [1]}, mcp.PARAMS, "object"),
        ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}, mcp.PARAMS, "name"),
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "jbus_status", "arguments": [1]},
            },
            mcp.PARAMS,
            "object of arguments",
        ),
        ({"jsonrpc": "2.0", "id": 1, "method": "resources/list"}, mcp.METHOD, "no method"),
    ],
)
def test_mcp_answers_each_malformed_request_with_its_error(message, code, why):
    answered = mcp.answer(message, lambda name, arguments: pytest.fail("no call"))
    assert answered["error"]["code"] == code
    assert why in answered["error"]["message"]


def test_mcp_answers_a_ping_with_an_empty_result():
    answered = mcp.answer({"jsonrpc": "2.0", "id": 7, "method": "ping"}, None)
    assert answered == {"jsonrpc": "2.0", "id": 7, "result": {}}


@pytest.mark.parametrize(
    ("name", "arguments", "why"),
    [
        ("jbus_status", [1], "takes an object of arguments"),
        ("jbus_queue_show", {"project": 5}, "project is a string"),
        (
            "jbus_queue_add",
            {"project": "jstack", "slug": "a", "priority": 1, "brief": "# A\n", "depends": "b"},
            "depends is a list",
        ),
    ],
)
def test_the_tool_table_refuses_arguments_of_the_wrong_shape(name, arguments, why):
    with pytest.raises(Refused, match=why):
        tools.call(name, arguments)


def noon():
    return datetime(2026, 11, 5, 12, tzinfo=UTC)


def test_the_log_keeps_its_newest_half_past_its_cap(tmp_path):
    log = limits.Log(tmp_path / "log.jsonl", cap=600, clock=noon)
    assert log.lines() == []
    for number in range(20):
        log.write("call", number=number)
    kept = [one["number"] for one in log.lines()]
    assert kept[-1] == 19
    assert 0 not in kept
    assert (tmp_path / "log.jsonl").stat().st_size <= 600
    assert (tmp_path / "log.jsonl").stat().st_mode & 0o777 == 0o600


def test_a_window_counts_again_once_its_seconds_pass():
    now = [0.0]
    window = limits.Window(1, 10, lambda: now[0])
    assert window.take() == 0
    assert window.take() > 0
    now[0] = 10.0
    assert window.take() == 0


def test_the_state_dir_is_the_one_the_environment_names(monkeypatch, tmp_path):
    monkeypatch.delenv("JBUS_MCP_STATE", raising=False)
    monkeypatch.setenv("STATE_DIRECTORY", f"{tmp_path}/a:{tmp_path}/b")
    assert state_dir() == tmp_path / "a"
    monkeypatch.setenv("JBUS_MCP_STATE", str(tmp_path / "own"))
    assert state_dir() == tmp_path / "own"
    monkeypatch.delenv("JBUS_MCP_STATE")
    monkeypatch.delenv("STATE_DIRECTORY")
    assert state_dir() == Path("/var/lib/jbus-mcp")


def test_render_skips_a_folder_among_the_templates(tmp_path):
    source = tmp_path / "templates"
    (source / "inner").mkdir(parents=True)
    (source / "a.env").write_text("HOST=@HOST@\n", encoding="utf-8")
    given = deploy.values("alex", "mcp.example.org", ["app"], home="/home/alex")
    written = deploy.render(tmp_path / "out", given, source)
    assert [path.name for path in written] == ["a.env"]


def test_the_store_refuses_a_file_that_is_not_json(tmp_path):
    (tmp_path / oauth.FILE).write_text("{", encoding="utf-8")
    with pytest.raises(Refused, match="is not JSON"):
        oauth.Store(tmp_path / oauth.FILE, ORIGIN).allows("Bearer x")


@pytest.fixture
def granted(tmp_path):
    store = oauth.Store(tmp_path / oauth.FILE, ORIGIN)
    client_id, secret = store.make_client()
    asked = store.asked(
        {
            "client_id": client_id,
            "redirect_uri": oauth.CALLBACK,
            "response_type": "code",
            "code_challenge": challenge(),
            "code_challenge_method": "S256",
        }
    )
    back = store.grant(asked, store.make_code())
    code = back.split("code=")[1].split("&")[0]
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": oauth.CALLBACK,
        "code_verifier": VERIFIER,
        "client_id": client_id,
        "client_secret": secret,
    }
    return store, form


@pytest.mark.parametrize(
    ("over", "error"),
    [
        ({"redirect_uri": "https://claude.ai/elsewhere"}, "invalid_grant"),
        ({"resource": "https://other.test/mcp"}, "invalid_target"),
        ({"grant_type": "password"}, "unsupported_grant_type"),
    ],
)
def test_the_token_endpoint_refuses_a_grant_used_another_way(granted, over, error):
    store, form = granted
    with pytest.raises(oauth.Failed) as failed:
        store.token({**form, **over})
    assert failed.value.error == error
    assert failed.value.body()["error"] == error


def test_a_basic_header_that_is_not_base64_is_a_wrong_client(granted):
    store, form = granted
    bare = {key: value for key, value in form.items() if key not in ("client_id", "client_secret")}
    with pytest.raises(oauth.Failed) as failed:
        store.token(bare, "Basic !!not-base64!!")
    assert (failed.value.error, failed.value.status) == ("invalid_client", 401)


@pytest.mark.parametrize("header", ["", "Basic abc", "Bearer ", "token"])
def test_only_a_bearer_token_is_let_in(granted, header):
    store, _ = granted
    assert store.allows(header) is False


def test_the_runner_reports_a_jbus_that_cannot_start(tmp_path):
    def missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    config = run.Config("/nowhere/jbus", ["jstack"])
    said = run.execute(tools.call("jbus_status", {})[1], config, missing)
    assert said["code"] == 127
    assert "could not start" in said["stderr"]


def test_the_runner_refuses_a_request_past_its_size(tmp_path):
    path = tmp_path / "runner.json"
    path.write_text(json.dumps({"jbus": "/usr/bin/jbus", "projects": ["jstack"]}))
    out = io.StringIO()
    code = run.main(io.StringIO("x" * (run.REQUEST + 1)), out, path, subprocess.run)
    assert code == 2
    assert "at most" in json.loads(out.getvalue())["refused"]


def test_the_settings_refuse_a_port_that_is_not_a_number():
    with pytest.raises(Refused, match="JBUS_MCP_PORT"):
        server.settings({"JBUS_MCP_ORIGIN": ORIGIN, "JBUS_MCP_PORT": "http"})


def test_the_runner_socket_refuses_an_answer_it_cannot_read():
    short = tempfile.mkdtemp(prefix="jbus-mcp-", dir="/tmp")
    try:
        path = f"{short}/run.sock"
        listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listening.bind(path)
        listening.listen(1)

        def answer():
            connection, _ = listening.accept()
            with connection:
                while connection.recv(4096):
                    pass
                connection.sendall(b"not json\n")

        thread = threading.Thread(target=answer)
        thread.start()
        said = server.runner_socket(path, 5)("{}")
        thread.join()
        listening.close()
    finally:
        shutil.rmtree(short, ignore_errors=True)
    assert said == {"refused": "the runner said nothing it could read"}


def test_a_runner_refusal_stderr_and_cut_output_reach_the_result(tmp_path):
    answers = iter(
        [
            {"refused": "refused: jstack is not a project this runner serves"},
            {"code": 0, "stdout": "out\n", "stderr": "warned\n", "cut": True},
        ]
    )
    made = Up(tmp_path, lambda text: next(answers))
    try:
        token = made.token()
        _, refused = made.call(token, "jbus_status", {})
        assert refused["result"]["isError"] is True
        assert "not a project" in refused["result"]["content"][0]["text"]
        assert made.log.lines()[-1]["outcome"] == "refused"
        _, cut = made.call(token, "jbus_status", {})
        text = cut["result"]["content"][0]["text"]
        assert "stderr:\nwarned" in text
        assert "(cut:" in text
    finally:
        made.close()


def test_a_runner_that_breaks_is_a_500_and_not_a_dropped_connection(tmp_path):
    def breaks(text):
        raise RuntimeError("runner broke")

    made = Up(tmp_path, breaks)
    try:
        status, body = made.call(made.token(), "jbus_status", {})
        assert status == 500
        assert body == {"error": "the server could not answer"}
    finally:
        made.close()


@pytest.mark.parametrize(
    ("path", "body", "status", "shown"),
    [
        ("/nowhere", "", 404, "no such address"),
        ("/authorize", "client_id=nobody", 400, '<p class="problem">'),
        ("/token", "grant_type=authorization_code", 401, "invalid_client"),
    ],
)
def test_the_sign_in_endpoints_refuse_a_form_they_cannot_take(up, path, body, status, shown):
    got, headers, text = up.post(path, body, FORM)
    assert got == status
    assert shown in text
    if status == 401:
        assert headers["WWW-Authenticate"] == "Basic"


def test_a_sign_in_page_asked_for_wrongly_says_why(up):
    status, headers, page = up.raw("GET", "/authorize?client_id=nobody")
    assert status == 400
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert 'name="sign_in_code"' not in page


def test_the_sign_in_endpoints_are_rate_limited(tmp_path):
    windows = {
        "reads": limits.Window(5, 60),
        "writes": limits.Window(5, 60),
        "sign_ins": limits.Window(1, 60),
    }
    made = Up(tmp_path, windows=windows)
    try:
        assert made.post("/token", "", FORM)[0] == 401
        status, headers, _ = made.post("/token", "", FORM)
        assert (status, headers["Retry-After"]) == (429, "60")
        assert made.log.lines()[-1]["outcome"] == "limited"
    finally:
        made.close()


@pytest.mark.parametrize(
    ("headers", "length", "status"),
    [
        ({"Host": "evil.test"}, "0", 403),
        ({}, None, 411),
        ({}, "many", 411),
        ({}, "-1", 411),
        ({}, str(server.BODY + 1), 413),
    ],
)
def test_a_post_with_a_foreign_host_or_no_plain_length_is_refused(up, headers, length, status):
    assert up.raw("POST", "/mcp", b"", headers, length)[0] == status


def test_serve_binds_its_settings_and_closes_when_stopped(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JBUS_MCP_STATE", str(tmp_path))
    made = []

    class Stopped:
        server_port = 4555

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            made.append("closed")

    def bound(app, port):
        made.append((app.origin, port, app.store.path))
        return Stopped()

    monkeypatch.setattr(server, "bind", bound)
    chosen = server.Settings(ORIGIN, 4555, str(tmp_path / "run.sock"))
    assert server.serve(chosen) == 0
    assert made == [(ORIGIN, 4555, tmp_path / oauth.FILE), "closed"]
    assert f"listening on 127.0.0.1:4555 for {ORIGIN}" in capsys.readouterr().out


def test_a_basic_header_carries_the_client_as_base64(granted):
    store, form = granted
    pair = base64.b64encode(f"{form['client_id']}:{form['client_secret']}".encode()).decode()
    bare = {key: value for key, value in form.items() if key not in ("client_id", "client_secret")}
    assert store.token(bare, f"Basic {pair}")["token_type"] == "Bearer"
