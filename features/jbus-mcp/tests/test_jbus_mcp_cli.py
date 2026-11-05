"""`jbus-mcp`'s verbs: `serve` and `run` hand over to the server and the runner, `render` writes
a machine's deploy files from a checkout's root, `log` prints the newest lines, and `client`,
`code` and `revoke` change the sign-in store only when a person types them, not an agent."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from jbus_mcp import cli, limits, oauth, run, server

REPO = Path(__file__).resolve().parents[3]
READ_SET = ("features/jbus-mcp/deploy/",)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("JBUS_MCP_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("JBUS_MCP_ORIGIN", "https://jbus.example.test")
    monkeypatch.delenv(cli.AGENT, raising=False)
    return tmp_path / "state"


def test_serve_and_run_hand_over_to_the_server_and_the_runner(monkeypatch):
    monkeypatch.setattr(server, "serve", lambda: 3)
    monkeypatch.setattr(run, "main", lambda: 4)
    assert cli.main(["serve"]) == 3
    assert cli.main(["run"]) == 4


def test_render_writes_the_deploy_files_from_a_checkout_s_root(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(REPO)
    out = tmp_path / "out"
    argv = ["render", "--user", "alex", "--home", "/home/alex", "--host", "mcp.example.org"]
    assert cli.main([*argv, "--project", "app", "--out", str(out)]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert sorted(Path(one).name for one in printed) == sorted(
        path.name for path in (REPO / "features/jbus-mcp/deploy").iterdir()
    )
    assert "User=alex" in (out / "jbus-mcp-run@.service").read_text(encoding="utf-8")


def test_render_prints_its_refusal_and_exits_1(tmp_path, capsys):
    argv = ["render", "--user", "Alex Doe", "--host", "mcp.example.org", "--project", "app"]
    assert cli.main([*argv, "--out", str(tmp_path / "out")]) == 1
    assert "is not a user name" in capsys.readouterr().out


def test_log_prints_the_newest_lines(state, capsys):
    log = limits.Log(state / limits.FILE)
    for number in range(3):
        log.write("call", number=number)
    assert cli.main(["log", "--lines", "2"]) == 0
    printed = [json.loads(one)["number"] for one in capsys.readouterr().out.splitlines()]
    assert printed == [1, 2]


def test_client_code_and_revoke_change_the_store(state, capsys):
    assert cli.main(["client"]) == 0
    assert "client secret, shown this once" in capsys.readouterr().out
    assert cli.main(["code"]) == 0
    assert "sign-in code, good for 10 minutes" in capsys.readouterr().out
    assert cli.main(["revoke"]) == 0
    assert "every connector signs in again" in capsys.readouterr().out
    assert (state / oauth.FILE).exists()


@pytest.mark.parametrize("verb", ["client", "code", "revoke"])
def test_an_agent_cannot_make_a_client_a_code_or_a_revoke(state, monkeypatch, capsys, verb):
    monkeypatch.setenv(cli.AGENT, "a-session")
    assert cli.main([verb]) == 1
    assert "it is the user's to run" in capsys.readouterr().out
    assert not (state / oauth.FILE).exists()


def test_python_m_jbus_mcp_runs_the_same_entry_point(state, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["jbus-mcp", "log"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("jbus_mcp.__main__", run_name="__main__")
    assert stopped.value.code == 0
    assert capsys.readouterr().out == ""
