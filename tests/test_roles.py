"""`jroles <role>` prints the model selection a launch of that role takes, from the role map.
It is run here as a thread runs it, against a map in a temporary config directory, and what
it prints is put into the skills' own launch blocks and held against the tool's schema."""

import json

import pytest

from jroles import ROLES
from jroles.cli import main
from test_tool_calls import LAUNCHES, errors

MAP = """# who runs on what
crew: codex gpt-5-codex
scout: claudeAgent claude-sonnet-5-5 claude-work

review: inherit
"""


@pytest.fixture
def roles(tmp_path, monkeypatch, capsys):
    """Run `jroles <role>` over a map, or over none: what it printed, on stdout and stderr."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def run(role, text=None):
        if text is not None:
            (tmp_path / "jstack").mkdir(exist_ok=True)
            (tmp_path / "jstack" / "roles").write_text(text)
        assert main([role]) == 0
        return capsys.readouterr()

    return run


def test_no_file_prints_nothing(roles):
    assert roles("crew") == ("", "")


def test_a_role_with_no_line_prints_nothing(roles):
    assert roles("home", MAP) == ("", "")


def test_an_expert_is_a_role_and_gets_what_the_map_gives_it_or_nothing(roles):
    assert roles("expert") == ("", "")
    assert roles("expert", MAP) == ("", "")
    assert roles("expert", MAP + "expert: inherit\n") == ("", "")
    given = MAP + "expert: grok grok-build\n"
    assert roles("expert", given) == ('{"provider": "grok", "model": "grok-build"}\n', "")
    assert roles("crew", given) == ('{"provider": "codex", "model": "gpt-5-codex"}\n', "")


def test_the_roles_are_the_four_threads_and_an_expert_and_no_other(roles):
    """A line for a role that is gone refuses the map, and the role cannot be asked for."""
    assert ROLES == ("crew", "scout", "review", "home", "expert")
    line = "orchestrator: claudeAgent claude-haiku-5-5"
    assert roles("crew", MAP + line + "\n") == ("", f"bad line 6: {line}\n")
    with pytest.raises(SystemExit):
        main(["orchestrator"])


def test_inherit_is_the_same_as_no_line(roles):
    assert roles("review", MAP) == ("", "")


def test_a_full_line_prints_the_selection_as_one_json_object(roles):
    assert roles("crew", MAP) == ('{"provider": "codex", "model": "gpt-5-codex"}\n', "")
    printed = roles("scout", MAP)
    assert printed.err == ""
    assert json.loads(printed.out) == {
        "provider": "claudeAgent",
        "model": "claude-sonnet-5-5",
        "instanceId": "claude-work",
        "options": [{"id": "effort", "value": "medium"}],
    }


@pytest.mark.parametrize(
    "line",
    [
        "crew codex gpt-5-codex",
        "crew: codex",
        "crew: codex gpt-5-codex an-instance more",
        "crew: inherit gpt-5-codex",
        "captain: codex gpt-5-codex",
    ],
)
def test_a_bad_line_is_said_on_stderr_and_no_role_gets_a_selection(roles, line):
    text = f"scout: grok grok-build\n# a comment\n{line}\n"
    for role in ("crew", "scout"):
        assert roles(role, text) == ("", f"bad line 3: {line}\n")


def test_a_role_named_twice_is_a_bad_line(roles):
    text = "crew: codex gpt-5-codex\ncrew: grok grok-build\n"
    assert roles("crew", text) == ("", "bad line 2: crew: grok grok-build\n")


def test_a_provider_that_is_not_one_of_the_three_is_refused(roles):
    text = "crew: cursor composer-2\nscout: grok grok-build\n"
    assert roles("crew", text) == ("", "refused crew: cursor is not Claude, Codex or Grok\n")
    assert roles("scout", text) == ('{"provider": "grok", "model": "grok-build"}\n', "")


def test_a_map_that_cannot_be_read_is_said_on_stderr_and_the_launch_inherits(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tmp_path / "jstack" / "roles"
    path.mkdir(parents=True)
    assert main(["crew"]) == 0
    assert capsys.readouterr() == ("", f"cannot read {path}: Is a directory\n")
    path.rmdir()
    path.write_bytes(b"crew: codex \xff\n")
    assert main(["crew"]) == 0
    assert capsys.readouterr() == ("", f"cannot read {path}: it is not UTF-8\n")
    path.unlink()
    path.parent.rmdir()
    path.parent.write_text("")
    assert main(["crew"]) == 0
    assert capsys.readouterr() == ("", f"cannot read {path}: Not a directory\n")


def test_with_no_xdg_config_home_the_map_is_under_the_home_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".config" / "jstack").mkdir(parents=True)
    (tmp_path / ".config" / "jstack" / "roles").write_text("home: grok grok-build\n")
    assert main(["home"]) == 0
    assert capsys.readouterr().out == '{"provider": "grok", "model": "grok-build"}\n'


@pytest.mark.parametrize("role", ["crew", "scout"])
def test_what_it_prints_is_a_model_selection_the_launch_tool_takes(roles, role):
    selection = json.loads(roles(role, MAP).out)
    twins = [call for call in LAUNCHES if "modelSelection" in call.given]
    assert twins
    for twin in twins:
        assert errors(twin, {**twin.given, "modelSelection": selection}) == []


@pytest.mark.parametrize(
    ("line", "effort"),
    [
        ("scout: claudeAgent claude-sonnet-5-5", "medium"),
        ("scout: claudeAgent claude-sonnet-5-5 effort=medium", "medium"),
        ("scout: claudeAgent claude-sonnet-5-5 effort=low", "low"),
        ("scout: claudeAgent claude-sonnet-5-5 claude-work effort=low", "low"),
    ],
)
def test_a_claude_selection_always_names_an_effort_of_medium_or_lower(roles, line, effort):
    """T3 Code launches a model with no effort option at its own default, which is high for
    Claude Sonnet 5.5: the selection names one, so the role map never raises a thread."""
    selection = json.loads(roles("scout", line + "\n").out)
    assert selection["options"] == [{"id": "effort", "value": effort}]


@pytest.mark.parametrize("level", ["high", "xhigh", "max", "ultracode", "ultrathink", ""])
def test_an_effort_above_medium_is_refused_and_the_launch_inherits(roles, level):
    text = f"scout: claudeAgent claude-opus-5-5 effort={level}\ncrew: grok grok-build\n"
    assert roles("scout", text) == ("", f"refused scout: effort={level} is not low or medium\n")
    assert roles("crew", text) == ('{"provider": "grok", "model": "grok-build"}\n', "")


def test_only_a_claude_line_names_an_effort_and_only_last(roles):
    assert roles("crew", "crew: codex gpt-5-codex effort=low\n") == (
        "",
        "refused crew: only a Claude line names an effort\n",
    )
    line = "crew: claudeAgent effort=low claude-opus-5-5"
    assert roles("crew", line + "\n") == ("", f"bad line 1: {line}\n")
    line = "crew: claudeAgent claude-opus-5-5 a b effort=low"
    assert roles("crew", line + "\n") == ("", f"bad line 1: {line}\n")
