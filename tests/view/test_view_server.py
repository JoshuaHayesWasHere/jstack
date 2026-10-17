"""The server of `jbus view`: it starts on a free port, listens where it is told, answers
many requests at once, and starts again when its code changes."""

import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from jbus import cli, view
from view.scene import EVIL, IPV6, NOW, PANTRY, PROXIED, REPO, Served, asks, et, free_port, kept


def test_the_server_starts_on_a_free_port_over_a_temporary_state_directory(served):
    assert served.json("/healthz") == {"ok": True}
    assert served.doors.addresses() == [("127.0.0.1", served.port)]


def test_each_route_answers_and_anything_else_is_404(served):
    status, headers, page = served.ask("/")
    assert (status, headers["Content-Type"]) == (200, "text/html; charset=utf-8")
    assert "<title>jbus: the line</title>" in page
    state = served.json("/state.json?project=demo")
    assert (state["project"], state["projects"], state["repo"]) == ("demo", ["demo"], "acme/demo")
    digest = served.json("/digest.json?since=2026-10-12T00:00")
    assert digest["since"] == "2026-10-12T04:00:00+00:00"
    assert [one["slug"] for one in digest["projects"]["demo"]["merged"]] == ["rye-loaf"]
    assert served.json("/task/oat-milk/github?project=demo")["pull"]["number"] == 13
    assert served.json("/healthz") == {"ok": True}
    for path in ("/nothing", "/state.json/more", "/task/oat-milk", "/task/oat-milk/github/x"):
        assert served.ask(path)[0] == 404, path


def test_the_digest_at_the_address_is_what_jbus_digest_prints(served, scene, capsys, monkeypatch):
    (scene.root / "config").mkdir()
    config = scene.root / "config" / "config.toml"
    config.write_text(
        'server = "http://localhost:1"\n[[project]]\nname = "demo"\n'
        f'checkout = "{scene.root}"\nprojectId = "p"\n'
    )
    config.chmod(0o600)
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    assert cli.main(["digest", "--json", "--since", "2026-10-12T00:00"]) == 0
    printed = json.loads(capsys.readouterr().out)
    answered = served.json("/digest.json?since=2026-10-12T00:00")
    assert printed.pop("at") and answered.pop("at")
    assert printed["projects"]["demo"]["waiting"] and printed["status"]["pass"]["projects"]
    assert answered == printed


def test_jbus_digest_takes_the_expiry_from_the_token_file_where_there_is_one(
    scene, capsys, monkeypatch
):
    (scene.root / "config").mkdir()
    config = scene.root / "config" / "config.toml"
    config.write_text(
        'server = "http://localhost:1"\n[[project]]\nname = "demo"\n'
        f'checkout = "{scene.root}"\nprojectId = "p"\n'
    )
    token = scene.root / "config" / "t3.json"
    stored = {"token": {"access_token": "a", "expires_in": 3600}, "obtained_at": NOW.timestamp()}
    token.write_text(json.dumps(stored))
    config.chmod(0o600)
    token.chmod(0o600)
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    assert cli.main(["digest", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["token_expires"] == et(NOW + timedelta(hours=1))
    assert printed["status"]["token_expires"] == "2026-11-10 17:08 ET"
    token.unlink()
    assert cli.main(["digest", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["token_expires"] == "2026-11-10 17:08 ET"


def test_a_since_that_is_not_a_time_is_refused(served):
    status, _, body = served.ask("/digest.json?since=yesterday")
    assert (status, json.loads(body)) == (400, {"error": "since is not a time"})


def test_a_view_over_no_config_of_jbus_still_closes_the_question(scene, served):
    number = asks(scene)
    status, said = served.write({"numbers": [number], "words": "coffee"})
    (closed,) = said["closed"]
    assert (status, closed["sent"], closed["keeps"]) == (200, False, False)
    assert closed["why"] == f"no config at {scene.root / 'config' / 'config.toml'}"
    assert kept(scene.state)[number].answer.words == "coffee"


def test_a_host_header_that_is_not_the_servers_is_refused(scene):
    served = Served(scene, names=("kitchen.example.test",))
    try:
        assert served.ask("/healthz", host=f"localhost:{served.port}")[0] == 200
        assert served.ask("/healthz", host=f"kitchen.example.test:{served.port}")[0] == 200
        for host in ("evil.example.test", f"evil.example.test:{served.port}", "127.0.0.1:1", ""):
            assert served.ask("/state.json?project=demo", host=host)[0] == 403, host
    finally:
        served.close()


def test_no_answer_has_a_cors_header_and_none_may_be_stored(served):
    for path in (
        "/",
        "/state.json?project=demo",
        "/digest.json",
        "/task/oat-milk/github?project=demo",
        "/healthz",
        "/no",
    ):
        _, headers, _ = served.ask(path)
        assert headers["Cache-Control"] == "no-store", path
        assert [name for name in headers if name.lower().startswith("access-control")] == []
    _, headers, _ = served.ask("/state.json?project=demo", method="POST")
    assert headers["Cache-Control"] == "no-store"


def test_it_never_listens_on_every_address(scene):
    for everywhere in ("0.0.0.0", "::", "", "*"):
        with pytest.raises(view.Refused):
            view.Doors(scene.app(), free_port(), host=everywhere).open()


def test_it_listens_on_the_address_in_jbus_view_host_too(scene):
    served = Served(scene, host="127.0.0.2")
    try:
        assert served.doors.addresses() == [("127.0.0.1", served.port), ("127.0.0.2", served.port)]
        status, _, _ = served.ask("/healthz", host=f"127.0.0.2:{served.port}", to="127.0.0.2")
        assert status == 200
    finally:
        served.close()


def test_with_that_address_down_it_serves_loopback_and_tries_again(scene):
    port = free_port("127.0.0.2")
    taken = socket.socket()
    taken.bind(("127.0.0.2", port))
    taken.listen()
    served = Served(scene, host="127.0.0.2", retry=0.05, port=port)
    try:
        assert served.doors.addresses() == [("127.0.0.1", port)]
        assert served.json("/healthz") == {"ok": True}
        taken.close()
        until = time.monotonic() + 10
        while len(served.doors.addresses()) < 2 and time.monotonic() < until:
            time.sleep(0.02)
        assert served.doors.addresses() == [("127.0.0.1", port), ("127.0.0.2", port)]
        assert served.ask("/healthz", host=f"127.0.0.2:{port}", to="127.0.0.2")[0] == 200
    finally:
        taken.close()
        served.close()


def test_an_address_that_is_not_this_machines_leaves_loopback_serving(scene):
    served = Served(scene, host="192.0.2.1")
    try:
        assert served.doors.addresses() == [("127.0.0.1", served.port)]
        assert served.json("/healthz") == {"ok": True}
    finally:
        served.close()


def test_jbus_view_reads_its_address_and_names_from_the_environment(scene, monkeypatch):
    monkeypatch.setenv("JBUS_VIEW_HOST", "127.0.0.2")
    monkeypatch.setenv("JBUS_VIEW_NAMES", "kitchen.example.test, pantry.example.test")
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    port = free_port()
    doors = view.doors(port)
    try:
        assert doors.host == "127.0.0.2"
        assert doors.names == ("kitchen.example.test", "pantry.example.test")
        assert doors.app.sources.state_dir == scene.state_dir
        assert view.PORT == 4388
    finally:
        doors.close()


def test_jbus_view_reads_its_origins_from_the_environment(scene, monkeypatch):
    monkeypatch.setenv(
        "JBUS_VIEW_ORIGINS",
        f"HTTPS://{PROXIED}:443, ,http://{IPV6}:8080,https://{PANTRY}:0443,http://{EVIL}:08080",
    )
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    doors = view.doors(free_port())
    try:
        assert doors.origins == (
            f"https://{PROXIED}",
            f"http://{IPV6}:8080",
            f"https://{PANTRY}",
            f"http://{EVIL}:8080",
        )
    finally:
        doors.close()


@pytest.mark.parametrize(
    "origin",
    [
        PROXIED,
        f"ftp://{PROXIED}",
        f"https://{PROXIED}/",
        f"https://{PROXIED}/answer",
        f"https://{PROXIED}?a=b",
        f"https://me@{PROXIED}",
        f"https://{PROXIED}:0",
        f"https://{PROXIED}:65536",
        f"https://{PROXIED}:",
        "https://",
        f"https://*.{PANTRY}",
    ],
)
def test_an_origin_that_is_not_one_refuses_the_start(scene, monkeypatch, origin):
    monkeypatch.setenv("JBUS_VIEW_ORIGINS", f"https://{PANTRY},{origin}")
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    with pytest.raises(view.Refused, match="JBUS_VIEW_ORIGINS"):
        view.doors(free_port())


def test_the_verb_is_jbus_view_and_it_needs_no_config(scene, monkeypatch):
    opened = []

    class Stub:
        def __init__(self, port):
            opened.append(port)

        def serve(self):
            return 0

    monkeypatch.setattr(view, "doors", Stub)
    assert cli.main(["view", "--port", "4999"]) == 0
    assert cli.main(["view"]) == 0
    assert opened == [4999, 4388]
    assert not (scene.root / "config").exists()


def test_many_requests_at_once_each_get_an_answer(served):
    answers = []

    def ask():
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{served.port}/state.json?project=demo"
            ) as answer:
                answers.append(answer.status)
        except urllib.error.URLError as error:
            answers.append(str(error))

    threads = [threading.Thread(target=ask) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert answers == [200] * 12


def test_the_state_says_when_the_server_started_and_that_its_code_is_as_on_disk(served):
    before = datetime.now(UTC)
    code = served.json("/state.json?project=demo")["jbus"]["code"]
    assert sorted(code) == ["error", "stale", "started"]
    assert (code["stale"], code["error"]) == (False, "")
    assert datetime.fromisoformat(code["started"]) <= before


def test_a_file_the_server_runs_that_is_newer_on_disk_is_said(scene, tmp_path):
    loaded, beside = tmp_path / "pkg" / "loaded.py", tmp_path / "pkg" / "beside.txt"
    loaded.parent.mkdir()
    for file in (loaded, beside):
        file.write_text("")
    code = view.Code(root=tmp_path, beside=loaded.parent, loaded=lambda: [str(loaded), "/else.py"])
    assert code.said()["stale"] is False
    later = time.time() + 5
    os.utime(beside, (later, later))
    assert code.said()["stale"] is True
    os.utime(beside, (1, 1))
    assert code.said()["stale"] is False
    os.utime(loaded, (later, later))
    assert code.said()["stale"] is True
    loaded.unlink()
    assert code.said()["stale"] is True


def test_the_server_ends_with_the_status_its_unit_starts_again_when_its_code_changes(process):
    import configparser

    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.optionxform = str
    unit.read(REPO / "templates" / "jbus-view.service")
    process.start()
    assert process.code()["stale"] is False
    (process.src / "jbus" / "view" / "state.py").touch()
    ended = process.run.wait(timeout=20)
    assert ended == view.NEWER_CODE
    assert ended not in (0, 1)
    assert unit["Service"]["Restart"] == "always"
    assert unit["Service"]["RestartForceExitStatus"] == str(ended)
    assert unit["Service"]["SuccessExitStatus"] == str(ended)
    process.start()
    assert process.ask("/healthz") == {"ok": True}
    assert process.code()["stale"] is False


@pytest.mark.parametrize("broken", ["view/clean.py", "word.py"])
def test_code_that_does_not_start_keeps_the_server_and_ends_it_once_it_starts(process, broken):
    process.start()
    module = process.src / "jbus" / broken
    whole = module.read_text()
    module.write_text("def (:\n")
    process.until(lambda: process.code().get("error"))
    code = process.code()
    assert code["stale"] is True
    assert code["error"] == "the code on disk does not start: SyntaxError: invalid syntax"
    time.sleep(1)
    assert process.run.poll() is None
    assert process.ask("/healthz") == {"ok": True}
    module.write_text(whole)
    assert process.run.wait(timeout=20) == view.NEWER_CODE


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.TimeoutExpired("python", 60),
        FileNotFoundError(2, "No such file or directory"),
        subprocess.CompletedProcess([], 1, "", "ModuleNotFoundError: No module named 'new'\n"),
        subprocess.CompletedProcess([], -9, "", ""),
    ],
)
def test_code_that_did_not_start_is_tried_again_at_the_next_check(tmp_path, monkeypatch, outcome):
    loaded = tmp_path / "loaded.py"
    loaded.write_text("")
    code = view.Code(root=tmp_path, beside=tmp_path, loaded=lambda: [str(loaded)])
    later = time.time() + 5
    os.utime(loaded, (later, later))
    outcomes = [outcome, subprocess.CompletedProcess([], 0, "", "")]

    def run(*args, **kwargs):
        one = outcomes.pop(0)
        if isinstance(one, Exception):
            raise one
        return one

    monkeypatch.setattr(subprocess, "run", run)
    assert code.due() is False
    assert code.said()["error"].startswith("the code on disk does not start: ")
    assert code.due() is True
    assert code.said()["error"] == ""


def test_the_unit_restarts_on_failure_and_depends_on_no_unit_of_jbus():
    import configparser

    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.read(REPO / "templates" / "jbus-view.service")
    assert unit["Service"]["Restart"] == "always"
    assert unit["Service"]["ExecStart"] == "%h/.local/bin/jbus view"
    assert unit["Install"]["WantedBy"] == "default.target"
    named = " ".join(
        f"{key}={value}" for part in unit.sections() for key, value in unit[part].items()
    )
    assert "jbus.timer" not in named and "jbus.service" not in named
    for key in ("After", "Requires", "Wants", "BindsTo", "PartOf", "OnFailure"):
        assert key.lower() not in {name.lower() for name in unit["Unit"]}, key
