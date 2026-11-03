"""The tool table builds one jbus command line for each tool, from checked arguments, and
refuses any value that could be read as a flag or that the schema does not take."""

import pytest

from jbus_mcp import Refused, tools

FORBIDDEN = ("--rule", "--follows", "--as", "jmerge", "merge", "word", "remove", "hold", "apply")


def test_the_table_has_the_seven_tools_and_no_other():
    names = [one["name"] for one in tools.listed()]
    assert names == [
        "jbus_status",
        "jbus_digest",
        "jbus_feed",
        "jbus_queue_show",
        "jbus_queue_add",
        "jbus_queue_approve",
        "jbus_answer",
    ]
    reads = {one["name"] for one in tools.listed() if one["annotations"]["readOnlyHint"]}
    assert reads == {"jbus_status", "jbus_digest", "jbus_feed", "jbus_queue_show"}
    for one in tools.listed():
        assert one["inputSchema"]["additionalProperties"] is False


@pytest.mark.parametrize(
    ("name", "arguments", "argv", "stdin"),
    [
        ("jbus_status", {}, ("status",), None),
        (
            "jbus_digest",
            {"since": "2026-11-03"},
            ("digest", "--json", "--since", "2026-11-03"),
            None,
        ),
        ("jbus_digest", {}, ("digest", "--json"), None),
        (
            "jbus_feed",
            {"project": "jstack", "slug": "alpha", "since": "2026-11-03T15:00"},
            ("--project", "jstack", "events", "--slug", "alpha", "--since", "2026-11-03T15:00"),
            None,
        ),
        ("jbus_queue_show", {"project": "jstack"}, ("--project", "jstack", "queue", "show"), None),
        (
            "jbus_queue_show",
            {"project": "jstack", "all": True},
            ("--project", "jstack", "queue", "show", "--all"),
            None,
        ),
        (
            "jbus_queue_add",
            {"project": "jstack", "slug": "alpha", "priority": 2, "brief": "# Alpha\n"},
            ("--project", "jstack", "queue", "add", "alpha", "--priority", "2"),
            "# Alpha\n",
        ),
        (
            "jbus_queue_add",
            {
                "project": "jstack",
                "slug": "beta",
                "priority": 0,
                "depends": ["alpha", "gamma"],
                "brief": "# Beta\n",
            },
            ("--project", "jstack", "queue", "add", "beta", "--priority", "0"),
            "# Beta\n",
        ),
        (
            "jbus_queue_approve",
            {
                "project": "jstack",
                "slug": "alpha",
                "sha12": "52e43397dc8c",
                "message": "mcp:a-home/a-message",
            },
            (
                "--project",
                "jstack",
                "queue",
                "approve",
                "alpha",
                "--sha",
                "52e43397dc8c",
                "--message",
                "mcp:a-home/a-message",
            ),
            None,
        ),
        (
            "jbus_answer",
            {"project": "jstack", "number": 3, "message": "t1/m2", "keeps_default": False},
            ("--project", "jstack", "answer", "3", "--message", "t1/m2", "--differs"),
            None,
        ),
        (
            "jbus_answer",
            {"project": "jstack", "number": 3, "message": "t1/m2", "keeps_default": True},
            ("--project", "jstack", "answer", "3", "--message", "t1/m2", "--default"),
            None,
        ),
    ],
)
def test_each_tool_builds_its_one_command_line(name, arguments, argv, stdin):
    _, built = tools.call(name, arguments)
    if name == "jbus_queue_add" and "depends" in arguments:
        argv = (*argv, "--depends", "alpha,gamma")
    assert built.argv == argv
    assert built.stdin == stdin


def test_no_command_line_carries_a_forbidden_word():
    for one in tools.TOOLS:
        assert one.name not in FORBIDDEN
        for word in FORBIDDEN:
            assert word not in one.description.split()


@pytest.mark.parametrize(
    ("name", "arguments", "why"),
    [
        ("jbus_merge", {}, "no tool"),
        ("jbus_status", {"project": "jstack"}, "takes no project"),
        ("jbus_feed", {}, "needs project"),
        ("jbus_feed", {"project": "--all"}, "not of the form"),
        ("jbus_feed", {"project": "jstack", "slug": "-x"}, "not of the form"),
        ("jbus_feed", {"project": "jstack", "since": "yesterday"}, "not of the form"),
        ("jbus_queue_show", {"project": "jstack", "all": "yes"}, "true or false"),
        (
            "jbus_queue_add",
            {"project": "jstack", "slug": "a", "priority": True, "brief": "x"},
            "an integer",
        ),
        (
            "jbus_queue_add",
            {"project": "jstack", "slug": "a", "priority": 1, "brief": "   "},
            "empty",
        ),
        (
            "jbus_queue_add",
            {"project": "jstack", "slug": "a", "priority": 1, "brief": "x" * (tools.BRIEF + 1)},
            "longer than",
        ),
        (
            "jbus_queue_add",
            {"project": "jstack", "slug": "a", "priority": 1, "brief": "x", "depends": ["--rule"]},
            "not of the form",
        ),
        (
            "jbus_queue_approve",
            {"project": "jstack", "slug": "a", "sha12": "52e43397dc8c", "message": "--follows/x"},
            "not of the form",
        ),
        (
            "jbus_queue_approve",
            {"project": "jstack", "slug": "a", "sha12": "52E43397DC8C", "message": "t/m"},
            "not of the form",
        ),
        (
            "jbus_queue_approve",
            {
                "project": "jstack",
                "slug": "a",
                "sha12": "52e43397dc8c",
                "message": "t/m",
                "rule": "6",
            },
            "takes no rule",
        ),
        (
            "jbus_answer",
            {"project": "jstack", "number": 0, "message": "t/m", "keeps_default": True},
            "out of range",
        ),
    ],
)
def test_it_refuses_what_the_schema_does_not_take(name, arguments, why):
    with pytest.raises(Refused, match=why):
        tools.call(name, arguments)


def test_a_value_that_starts_with_a_dash_never_reaches_a_command_line():
    for pattern in (tools.PROJECT, tools.SLUG, tools.REF, tools.SHA12, tools.TIME):
        assert pattern.fullmatch("-x") is None
        assert pattern.fullmatch("--project") is None
