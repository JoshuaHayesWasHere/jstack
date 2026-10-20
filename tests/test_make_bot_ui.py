"""`/make-bot-ui`: its `schedule_task` block is a call the tool takes, whose signature the
server it ships signs to, and that server, run as the skill runs it against a stand-in
webhook on 127.0.0.1, sends both key headers and the signature, tries once within its timeout,
logs a failed body, and binds 127.0.0.1 and the address it is given, never every address."""

import hashlib
import hmac
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from test_tool_calls import CALLS, errors

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "skills" / "make-bot-ui" / "scripts" / "bot_ui.py"
SPEC = importlib.util.spec_from_file_location("bot_ui", SCRIPT)
bot_ui = importlib.util.module_from_spec(SPEC)
sys.dont_write_bytecode, written = True, sys.dont_write_bytecode
SPEC.loader.exec_module(bot_ui)
sys.dont_write_bytecode = written


def the_call():
    (call,) = [call for call in CALLS if call.where.startswith("make-bot-ui:")]
    assert call.tool == "schedule_task"
    return call


def test_the_schedule_task_block_is_a_signed_webhook_bound_to_this_thread():
    call = the_call()
    given = call.given
    assert errors(call, given) == []
    schedule = given["schedule"]
    assert isinstance(schedule, dict), "schedule is an object, never JSON text"
    assert schedule["type"] == "webhook"
    assert given["bindToCurrentThread"] is True
    signature = schedule["signature"]
    assert "secret" not in signature and signature["secretRef"]
    assert signature["header"].lower() == bot_ui.SIGNATURE.lower()
    assert signature["prefix"] == bot_ui.PREFIX
    assert signature["encoding"] == "hex"
    assert "{{body.action}}" in given["prompt"]
    assert f"action is {bot_ui.PROBE['action']}, do nothing" in given["prompt"]


class StandIn:
    """A webhook on 127.0.0.1 that records each request, and answers as `answer` says:
    a status, or `slow` to answer after the server's timeout."""

    def __init__(self):
        self.seen = []
        self.answer = 200
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                stand_in.seen.append((self.headers, body))
                if stand_in.answer == "slow":
                    time.sleep(bot_ui.TIMEOUT + 3)
                    status = 200
                else:
                    status = stand_in.answer
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}/webhook/token-in-the-url"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def run(*args, **kwargs):
    return subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        **kwargs,
    )


def free_port():
    with socket.socket() as one:
        one.bind(("127.0.0.1", 0))
        return one.getsockname()[1]


def reaches(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
def stand_in():
    one = StandIn()
    yield one
    one.close()


@pytest.mark.timeout(60)
def test_the_server_posts_signed_once_in_time_logs_a_failure_and_binds_two_addresses(
    tmp_path, stand_in
):
    config = tmp_path / "ui" / "config.json"
    assert run("key", config).returncode == 0
    assert oct(config.stat().st_mode & 0o777) == "0o600"
    assert run("url", config, stand_in.url).returncode == 0
    key = json.loads(config.read_text())["key"]
    signature = the_call().given["schedule"]["signature"]

    page = tmp_path / "page"
    page.mkdir()
    (page / "index.html").write_text("<button>deploy</button>")
    port = free_port()
    assert run("serve", config, "--page", page, "--port", port, "--host", "0.0.0.0").returncode == 2
    assert not reaches("127.0.0.1", port)
    server = subprocess.Popen(
        ["uv", "run", "--script", str(SCRIPT), "serve", str(config), "--page", str(page)]
        + ["--port", str(port), "--host", "127.0.0.2"],
    )
    try:
        deadline = time.monotonic() + 10
        while not reaches("127.0.0.1", port) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert reaches("127.0.0.1", port) and reaches("127.0.0.2", port)
        assert not reaches("127.0.0.3", port), "it listens on every address"
        own = f"127.0.0.2:{port}"
        press = json.dumps({"action": "deploy"}).encode()
        foreign = urllib.request.Request(
            f"http://{own}/send", data=press, headers={"Origin": "http://evil.example"}
        )
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(foreign, timeout=5)
        assert refused.value.code == 403 and stand_in.seen == []
        ours = urllib.request.Request(
            f"http://{own}/send", data=press, headers={"Origin": f"http://{own}"}
        )
        with urllib.request.urlopen(ours, timeout=5) as answer:
            assert json.loads(answer.read()) == {"sent": True, "why": None}
    finally:
        server.terminate()
        server.wait()

    ((headers, body),) = stand_in.seen
    assert json.loads(body) == {"action": "deploy"}
    assert headers["Authorization"] == f"Bearer {key}"
    assert headers["X-Automation-Key"] == key
    digest = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    assert headers[signature["header"]] == signature["prefix"] + digest
    assert not (config.parent / bot_ui.FAILED).exists()

    stand_in.answer = 500
    probe = run("probe", config)
    assert probe.returncode == 1 and len(stand_in.seen) == 2
    stand_in.answer = "slow"
    started = time.monotonic()
    probe = run("probe", config)
    took = time.monotonic() - started
    assert probe.returncode == 1 and len(stand_in.seen) == 3
    assert bot_ui.TIMEOUT <= took < bot_ui.TIMEOUT + 2.5
    logged = [json.loads(line) for line in (config.parent / bot_ui.FAILED).read_text().splitlines()]
    assert [line["body"] for line in logged] == [bot_ui.PROBE, bot_ui.PROBE]
    assert logged[0]["why"] == "HTTP 500" and "timed out" in logged[1]["why"]
    text = (config.parent / bot_ui.FAILED).read_text()
    assert key not in text and stand_in.url not in text
    os.chmod(config, 0o644)
    assert run("probe", config).returncode == 2 and len(stand_in.seen) == 3
