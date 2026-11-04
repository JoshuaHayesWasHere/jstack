"""The connector is off by default: jstack's install puts nothing of it on a machine, nothing
serves without the config a machine's root writes, and the deploy files are templates that
name no machine until `jbus-mcp render` fills them in."""

import json
import tomllib
from pathlib import Path

import pytest

from jbus_mcp import Refused, deploy, mcp, run, server
from jinstall import layout
from jinstall.harnesses import HARNESSES
from jinstall.kinds import unit_templates

FEATURE = Path(__file__).resolve().parents[1]
REPO = FEATURE.parents[1]


def given(**changed):
    chosen = {"user": "alex", "host": "mcp.example.org", "projects": ["app"], "home": "/home/alex"}
    return deploy.values(**{**chosen, **changed})


def test_the_install_links_no_unit_and_lays_out_no_file_of_the_feature():
    assert [name for name in unit_templates(REPO) if "jbus-mcp" in name] == []
    for harness in HARNESSES:
        laid = repr(layout.assemble(REPO, harness))
        assert "features/jbus-mcp" not in laid, harness.name


def test_the_jstack_tool_has_no_jbus_mcp_command():
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    points = [project["scripts"], *project.get("entry-points", {}).values()]
    assert [name for group in points for name, at in group.items() if "jbus_mcp" in at] == []


def test_the_server_refuses_to_serve_without_its_public_origin():
    with pytest.raises(Refused, match="JBUS_MCP_ORIGIN"):
        server.settings({})


def test_the_runner_refuses_every_request_without_its_config(tmp_path):
    with pytest.raises(Refused, match="cannot be read"):
        run.load(tmp_path / "runner.json")


def test_the_server_names_no_machine_to_claude():
    shown = mcp.answer({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, None)
    assert shown["result"]["serverInfo"]["title"] == "jbus"


def test_every_value_a_machine_sets_in_the_templates_is_a_placeholder():
    text = "".join(path.read_text(encoding="utf-8") for path in deploy.TEMPLATES.iterdir())
    assert set(deploy.PLACEHOLDER.findall(text)) <= set(given().table())
    for fixed in ("/home/", "example.com", "4391", "/opt/", "/usr/bin/python3"):
        assert fixed not in text, fixed


def test_render_fills_every_placeholder_and_keeps_the_launcher_executable(tmp_path):
    written = deploy.render(tmp_path / "out", given(projects=["app", "jstack"], port=4500))
    texts = {path.name: path.read_text(encoding="utf-8") for path in written}
    assert set(texts) == {path.name for path in deploy.TEMPLATES.iterdir()}
    assert not deploy.PLACEHOLDER.search("".join(texts.values()))
    assert json.loads(texts["runner.json"]) == {
        "jbus": "/home/alex/.local/bin/jbus",
        "projects": ["app", "jstack"],
        "timeout": 60,
        "path": "/home/alex/.local/bin:/usr/local/bin:/usr/bin",
    }
    assert "User=alex\n" in texts["jbus-mcp-run@.service"]
    assert "JBUS_MCP_ORIGIN=https://mcp.example.org\nJBUS_MCP_PORT=4500\n" in texts["jbus-mcp.env"]
    started = "ExecStart=/usr/bin/python3 -I /opt/jbus-mcp/jbus-mcp serve\n"
    assert started in texts["jbus-mcp.service"]
    assert texts["jbus-mcp"].startswith("#!/usr/bin/python3 -I\n")
    assert (tmp_path / "out" / "jbus-mcp").stat().st_mode & 0o777 == deploy.EXECUTABLE
    assert (tmp_path / "out" / "runner.json").stat().st_mode & 0o777 == deploy.PLAIN


def test_the_runner_reads_the_config_render_wrote(tmp_path):
    deploy.render(tmp_path / "out", given())
    assert run.load(tmp_path / "out" / "runner.json").projects == frozenset({"app"})


@pytest.mark.parametrize(
    "changed",
    [
        {"user": "Alex Doe"},
        {"user": "alex\nUser=root"},
        {"host": "https://mcp.example.org"},
        {"host": "mcp.example.org/x"},
        {"host": "localhost"},
        {"projects": []},
        {"projects": ["../etc"]},
        {"port": 80},
        {"port": True},
        {"home": "home/alex"},
        {"home": "/home/alex/../root"},
        {"prefix": "/opt/jbus mcp"},
        {"python": "/usr/bin/python3\nExecStartPre=/bin/sh"},
    ],
)
def test_render_refuses_a_value_that_is_not_plain(changed):
    with pytest.raises(Refused):
        given(**changed)


def test_render_writes_only_to_a_new_or_empty_folder(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "kept").write_text("mine", encoding="utf-8")
    with pytest.raises(Refused, match="new or empty"):
        deploy.render(tmp_path / "out", given())
    assert [path.name for path in (tmp_path / "out").iterdir()] == ["kept"]


def test_render_writes_nothing_when_a_template_has_a_placeholder_it_does_not_know(tmp_path):
    source = tmp_path / "templates"
    source.mkdir()
    (source / "a.env").write_text("A=@HOST@\nB=@UNKNOWN@\n", encoding="utf-8")
    with pytest.raises(Refused, match="@UNKNOWN@"):
        deploy.render(tmp_path / "out", given(), source)
    assert not (tmp_path / "out").exists()


def test_render_looks_up_the_home_of_a_user_it_is_not_given():
    with pytest.raises(Refused, match="--home"):
        deploy.values("no-such-user-here", "mcp.example.org", ["app"])
