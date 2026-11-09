"""The download of the pinned tla2tools.jar: a fetch the server answers with a 5xx is tried again
after a wait, a jar that comes is kept in the cache once its sha256 is the pinned one, and a
download that never gets one raises NoTlc."""

import hashlib
import http.server
import threading

import pytest

from statechart_support import statechart_tools

JAR = b"PK\x03\x04 a stand-in for tla2tools.jar"


@pytest.fixture
def release(tmp_path, monkeypatch):
    """A server in place of GitHub's release download, whose answers are `answers` in turn,
    each an HTTP status (200 sends JAR), and the user's cache under tmp_path."""
    answers = []
    asked = []

    class Release(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            asked.append(self.path)
            status = answers.pop(0) if answers else 504
            self.send_response(status)
            body = JAR if status == 200 else b"Gateway Time-out"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Release)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    monkeypatch.setattr(statechart_tools, "TLA2TOOLS_URL", f"http://{host}:{port}/tla2tools.jar")
    monkeypatch.setattr(statechart_tools, "TLA2TOOLS_SHA256", hashlib.sha256(JAR).hexdigest())
    monkeypatch.setattr(statechart_tools, "DOWNLOAD_WAITS", (0, 0, 0))
    for name in ("TLA2TOOLS", "STATECHART_OFFLINE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("JAVA", "java")
    yield answers, asked
    server.shutdown()
    server.server_close()


def test_a_jar_after_two_gateway_timeouts_is_kept(release):
    answers, asked = release
    answers.extend([504, 504, 200])
    found = statechart_tools.find_tlc()
    assert found.jar == str(statechart_tools.cached_jar())
    assert statechart_tools.cached_jar().read_bytes() == JAR
    assert len(asked) == 3


def test_a_server_that_never_sends_the_jar_raises_no_tlc(release):
    answers, asked = release
    with pytest.raises(statechart_tools.NoTlc, match="504"):
        statechart_tools.find_tlc()
    assert not statechart_tools.cached_jar().exists()
    assert len(asked) == len(statechart_tools.DOWNLOAD_WAITS) + 1


def test_a_jar_of_another_sha256_is_not_kept(release, monkeypatch):
    answers, asked = release
    answers.append(200)
    monkeypatch.setattr(statechart_tools, "TLA2TOOLS_SHA256", "0" * 64)
    with pytest.raises(statechart_tools.NoTlc, match="not the pinned"):
        statechart_tools.find_tlc()
    assert not statechart_tools.cached_jar().exists()
    assert len(asked) == 1
