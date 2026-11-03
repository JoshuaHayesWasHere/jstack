"""The runner reads one request, rebuilds its command line from the tool table, checks the
project against its own config, and runs jbus with no shell."""

import io
import json
import subprocess
import sys

import pytest

from jbus_mcp import Refused, run


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "runner.json"
    path.write_text(
        json.dumps({"jbus": "/usr/bin/jbus", "projects": ["jstack"], "path": "/usr/bin"}),
        encoding="utf-8",
    )
    return path


def runs(stdin, config, fake):
    out = io.StringIO()
    code = run.main(io.StringIO(stdin), out, config, fake)
    return code, json.loads(out.getvalue())


def test_it_runs_the_command_line_the_table_builds(config):
    seen = {}

    def fake(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, "row added\n", "")

    asked = {
        "tool": "jbus_queue_add",
        "arguments": {"project": "jstack", "slug": "alpha", "priority": 1, "brief": "# Alpha\n"},
    }
    code, said = runs(json.dumps(asked), config, fake)
    assert code == 0
    assert said == {"code": 0, "stdout": "row added\n", "stderr": "", "cut": False}
    assert seen["argv"] == [
        "/usr/bin/jbus",
        "--project",
        "jstack",
        "queue",
        "add",
        "alpha",
        "--priority",
        "1",
    ]
    assert seen["input"] == "# Alpha\n"
    assert seen["env"]["PATH"] == "/usr/bin"
    assert "shell" not in seen


@pytest.mark.parametrize(
    ("request_text", "why"),
    [
        ("not json", "one JSON object"),
        (json.dumps({"tool": "jbus_status", "argv": ["merge"]}), "{tool, arguments}"),
        (json.dumps({"tool": "jmerge", "arguments": {}}), "no tool"),
        (
            json.dumps({"tool": "jbus_queue_show", "arguments": {"project": "infra"}}),
            "not a project this runner serves",
        ),
    ],
)
def test_it_refuses_a_request_it_does_not_build(config, request_text, why):
    def fake(argv, **kwargs):
        raise AssertionError("ran")

    code, said = runs(request_text, config, fake)
    assert code == 2
    assert why in said["refused"]


@pytest.mark.parametrize(
    ("given", "why"),
    [
        ({"jbus": "jbus", "projects": []}, "absolute path"),
        ({"jbus": "/usr/bin/jbus", "projects": ["-x"]}, "project names"),
        ({"jbus": "/usr/bin/jbus", "projects": [], "timeout": 0}, "timeout"),
        ({"jbus": "/usr/bin/jbus", "projects": [], "path": "bin"}, "absolute directories"),
    ],
)
def test_it_refuses_a_config_it_cannot_trust(tmp_path, given, why):
    path = tmp_path / "runner.json"
    path.write_text(json.dumps(given), encoding="utf-8")
    with pytest.raises(Refused, match=why):
        run.load(path)


def test_it_cuts_long_output_and_reports_a_timeout(config):
    loaded = run.load(config)

    def long(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "x" * (run.OUTPUT + 10), "")

    said = run.execute(run.request(json.dumps({"tool": "jbus_status"}), loaded), loaded, long)
    assert said["cut"] is True
    assert len(said["stdout"]) == run.OUTPUT

    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 1)

    said = run.execute(run.request(json.dumps({"tool": "jbus_status"}), loaded), loaded, slow)
    assert said["code"] == 124


def test_it_runs_a_real_command_with_no_shell(tmp_path):
    fake = tmp_path / "jbus"
    fake.write_text(
        f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    path = tmp_path / "runner.json"
    path.write_text(json.dumps({"jbus": str(fake), "projects": ["jstack"]}), encoding="utf-8")
    asked = {"tool": "jbus_feed", "arguments": {"project": "jstack", "slug": "a;rm"}}
    code, said = runs(json.dumps(asked), path, subprocess.run)
    assert code == 2
    asked["arguments"]["slug"] = "alpha"
    code, said = runs(json.dumps(asked), path, subprocess.run)
    assert code == 0
    assert json.loads(said["stdout"]) == ["--project", "jstack", "events", "--slug", "alpha"]


INJECTED = [
    ("jbus_feed", {"project": "jstack", "slug": "alpha --rule 6"}),
    ("jbus_feed", {"project": "jstack", "slug": "--follows"}),
    ("jbus_feed", {"project": "--as"}),
    ("jbus_feed", {"project": "jstack", "slug": "alpha; jmerge --accept"}),
    ("jbus_feed", {"project": "jstack", "slug": "$(id)"}),
    ("jbus_feed", {"project": "jstack", "slug": "`id`"}),
    ("jbus_feed", {"project": "jstack", "slug": "alpha\n--rule"}),
    ("jbus_feed", {"project": "jstack", "slug": "alpha\n"}),
    ("jbus_feed", {"project": "jstack", "slug": "alpha\x00"}),
    ("jbus_feed", {"project": "jstack", "since": "２０２６-11-03"}),
    ("jbus_feed", {"project": "jstack", "since": "2026-11-03 --as user"}),
    ("jbus_feed", {"project": "../infra"}),
    ("jbus_feed", {"project": "jstack/../infra"}),
    ("jbus_feed", {"project": "jstack.."}),
    ("jbus_feed", {"project": "/etc/passwd"}),
    ("jbus_feed", {"project": "jstack", "as": "user"}),
    ("jbus_queue_show", {"project": "jstack", "all": True, "follows": "alpha"}),
    (
        "jbus_queue_approve",
        {"project": "jstack", "slug": "a", "sha12": "52e43397dc8c", "message": "t/m --as user"},
    ),
    (
        "jbus_queue_approve",
        {"project": "jstack", "slug": "a", "sha12": "52e43397dc8c", "message": "t/m", "rule": "6"},
    ),
    (
        "jbus_queue_approve",
        {"project": "jstack", "slug": "a", "sha12": "52e43397dc8c", "message": "t/../m"},
    ),
    (
        "jbus_queue_add",
        {"project": "jstack", "slug": "a", "priority": 1, "brief": "x", "depends": ["a,--rule"]},
    ),
    ("jbus_queue_add", {"project": "jstack", "slug": "a", "priority": 1, "brief": "x\x00y"}),
    (
        "jbus_answer",
        {"project": "jstack", "number": "3 --as user", "message": "t/m", "keeps_default": True},
    ),
]


@pytest.mark.parametrize(("tool", "arguments"), INJECTED)
def test_the_runner_runs_nothing_for_an_injected_argument(config, tool, arguments):
    def fake(argv, **kwargs):
        raise AssertionError(f"ran {argv}")

    code, said = runs(json.dumps({"tool": tool, "arguments": arguments}), config, fake)
    assert code == 2
    assert said["refused"].startswith("refused:")


def test_the_last_check_refuses_a_flag_or_word_the_table_does_not_have():
    from jbus_mcp import tools

    for argv in (("queue", "approve", "a", "--follows", "b"), ("--as", "user", "status"), ("a b",)):
        with pytest.raises(Refused):
            tools.vet(tools.Call(argv))
    assert tools.vet(tools.Call(("--project", "jstack", "queue", "show"))).argv[-1] == "show"
