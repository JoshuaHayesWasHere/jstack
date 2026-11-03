"""The tool table: each tool the connector offers, its input schema, and the one jbus command
line it runs. The server lists the tools from here, and the runner rebuilds the command line
from here, so the two cannot drift apart.

Every value that reaches a command line is checked against a pattern that cannot start with a
`-`, so no value is read as a flag. The table has no tool for `--rule`, `--follows`, `--as`,
`jmerge`, a merge or a message sent to T3 Code: those are not in it to be asked for.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from jbus_mcp import Refused

__all__ = ["BRIEF", "FLAGS", "TOOLS", "Call", "Tool", "call", "listed", "vet"]

PROJECT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
SLUG = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")
SHA12 = re.compile(r"[0-9a-f]{12}")
REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,127}/[A-Za-z0-9][A-Za-z0-9:._-]{0,127}")
TIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}(?::[0-9]{2})?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?"
)
BRIEF = 65536
DEPENDS = 16
PRIORITY = 10000
FLAGS = frozenset(
    {"--project", "--since", "--slug", "--json", "--all", "--priority", "--depends", "--sha"}
    | {"--message", "--default", "--differs"}
)
WORD = re.compile(r"[A-Za-z0-9:._,/+-]{1,512}")


@dataclass(frozen=True)
class Call:
    """One jbus command line: its arguments after `jbus`, and its stdin, or None."""

    argv: tuple[str, ...]
    stdin: str | None = None


@dataclass(frozen=True)
class Tool:
    """One tool: its name, what the model reads of it, its input schema, whether it changes
    jbus's state, and how it builds its command line from checked arguments."""

    name: str
    title: str
    description: str
    properties: Mapping[str, Any]
    required: tuple[str, ...]
    writes: bool
    build: Callable[[Mapping[str, Any]], Call]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": dict(self.properties),
            "required": list(self.required),
            "additionalProperties": False,
        }

    def listed(self) -> dict[str, Any]:
        """The tool as MCP's `tools/list` gives it."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.schema(),
            "annotations": {
                "title": self.title,
                "readOnlyHint": not self.writes,
                "destructiveHint": False,
                "idempotentHint": not self.writes,
                "openWorldHint": False,
            },
        }


def _text(pattern: re.Pattern[str], what: str) -> dict[str, Any]:
    return {"type": "string", "pattern": f"^{pattern.pattern}$", "description": what}


_PROJECT = _text(PROJECT, "The project's name in jbus's config, such as jstack.")
_SLUG = _text(SLUG, "The row's slug.")
_REF = _text(
    REF,
    "The user's own message in T3 Code that says yes, as <thread id>/<message id>. jbus reads it "
    "from T3 Code itself and refuses a message that is not the user's.",
)
_SINCE = _text(TIME, "An ISO 8601 day or time, such as 2026-11-03 or 2026-11-03T15:00.")


def _given(arguments: Mapping[str, Any], tool: Tool) -> Mapping[str, Any]:
    """The arguments, checked against the tool's schema: no key it does not name, every key it
    requires, and each value of its type and pattern."""
    if not isinstance(arguments, Mapping):
        raise Refused(f"refused: {tool.name} takes an object of arguments")
    unknown = sorted(set(arguments) - set(tool.properties))
    if unknown:
        raise Refused(f"refused: {tool.name} takes no {', '.join(unknown)}")
    missing = [key for key in tool.required if key not in arguments]
    if missing:
        raise Refused(f"refused: {tool.name} needs {', '.join(missing)}")
    for key, value in arguments.items():
        _check(tool.name, key, value, tool.properties[key])
    return arguments


def _check(tool: str, key: str, value: Any, rule: Mapping[str, Any]) -> None:
    kind = rule["type"]
    if kind == "string":
        if not isinstance(value, str):
            raise Refused(f"refused: {tool}: {key} is a string")
        if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
            raise Refused(f"refused: {tool}: {key} is not of the form {rule['pattern']}")
        if len(value) > rule.get("maxLength", 256):
            raise Refused(f"refused: {tool}: {key} is longer than {rule.get('maxLength', 256)}")
        if "minLength" in rule and len(value.strip()) < rule["minLength"]:
            raise Refused(f"refused: {tool}: {key} is empty")
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise Refused(f"refused: {tool}: {key} is an integer")
        if not rule.get("minimum", 0) <= value <= rule.get("maximum", PRIORITY):
            raise Refused(f"refused: {tool}: {key} is out of range")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise Refused(f"refused: {tool}: {key} is true or false")
    elif kind == "array":
        if not isinstance(value, list) or len(value) > rule.get("maxItems", DEPENDS):
            raise Refused(f"refused: {tool}: {key} is a list of at most {DEPENDS}")
        for one in value:
            _check(tool, key, one, rule["items"])


def _project(arguments: Mapping[str, Any]) -> tuple[str, ...]:
    return ("--project", arguments["project"])


def _since(arguments: Mapping[str, Any]) -> tuple[str, ...]:
    return ("--since", arguments["since"]) if "since" in arguments else ()


def _status(arguments: Mapping[str, Any]) -> Call:
    return Call(("status",))


def _digest(arguments: Mapping[str, Any]) -> Call:
    return Call(("digest", "--json", *_since(arguments)))


def _feed(arguments: Mapping[str, Any]) -> Call:
    slug = ("--slug", arguments["slug"]) if "slug" in arguments else ()
    return Call((*_project(arguments), "events", *slug, *_since(arguments)))


def _show(arguments: Mapping[str, Any]) -> Call:
    every = ("--all",) if arguments.get("all") else ()
    return Call((*_project(arguments), "queue", "show", *every))


def _add(arguments: Mapping[str, Any]) -> Call:
    depends = arguments.get("depends") or []
    after = ("--depends", ",".join(depends)) if depends else ()
    priority = ("--priority", str(arguments["priority"]))
    line = (*_project(arguments), "queue", "add", arguments["slug"], *priority, *after)
    return Call(line, arguments["brief"])


def _approve(arguments: Mapping[str, Any]) -> Call:
    row = (arguments["slug"], "--sha", arguments["sha12"], "--message", arguments["message"])
    return Call((*_project(arguments), "queue", "approve", *row))


def _answer(arguments: Mapping[str, Any]) -> Call:
    keeps = "--default" if arguments["keeps_default"] else "--differs"
    said = ("--message", arguments["message"], keeps)
    return Call((*_project(arguments), "answer", str(arguments["number"]), *said))


TOOLS: tuple[Tool, ...] = (
    Tool(
        "jbus_status",
        "jbus status",
        "What jbus's last pass left: the status file and the record of the pass. Reads only.",
        {},
        (),
        False,
        _status,
    ),
    Tool(
        "jbus_digest",
        "jbus digest",
        "What waits on the user and what moved, over every project, as JSON. Reads only.",
        {"since": _SINCE},
        (),
        False,
        _digest,
    ),
    Tool(
        "jbus_feed",
        "jbus feed",
        "One project's event log as JSON, one event a line, oldest first, from jbus events. "
        "Give since to keep the events at or after a time, and slug to keep one row's. "
        "Reads only.",
        {"project": _PROJECT, "slug": _SLUG, "since": _SINCE},
        ("project",),
        False,
        _feed,
    ),
    Tool(
        "jbus_queue_show",
        "jbus queue show",
        "One project's queue table as Markdown, with what waits on the user above it. all adds the "
        "finished rows. Reads only.",
        {"project": _PROJECT, "all": {"type": "boolean", "description": "Every row."}},
        ("project",),
        False,
        _show,
    ),
    Tool(
        "jbus_queue_add",
        "jbus queue add",
        "Adds a row to one project's queue with its brief, as jbus queue add does. It "
        "approves nothing: the row waits for the user's go.",
        {
            "project": _PROJECT,
            "slug": _SLUG,
            "priority": {
                "type": "integer",
                "minimum": 0,
                "maximum": PRIORITY,
                "description": "An integer, lower first.",
            },
            "depends": {
                "type": "array",
                "items": _SLUG,
                "maxItems": DEPENDS,
                "description": "Slugs that must merge before this row launches.",
            },
            "brief": {
                "type": "string",
                "minLength": 1,
                "maxLength": BRIEF,
                "description": "The brief's full text.",
            },
        },
        ("project", "slug", "priority", "brief"),
        True,
        _add,
    ),
    Tool(
        "jbus_queue_approve",
        "jbus queue approve",
        "Records the user's go for the brief they were shown, on their own message in T3 "
        "Code, as jbus queue approve --sha --message does. A brief that holds for a door "
        "parks a gate for the user instead of approving.",
        {
            "project": _PROJECT,
            "slug": _SLUG,
            "sha12": _text(SHA12, "The first 12 of the sha256 of the brief the user was shown."),
            "message": _REF,
        },
        ("project", "slug", "sha12", "message"),
        True,
        _approve,
    ),
    Tool(
        "jbus_answer",
        "jbus answer",
        "Closes a question with the user's answer, on their own message in T3 Code, as jbus answer "
        "--message does. keeps_default says whether the answer is the default the thread took.",
        {
            "project": _PROJECT,
            "number": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000000,
                "description": "The question's number.",
            },
            "message": _REF,
            "keeps_default": {
                "type": "boolean",
                "description": "True when the answer is the default, false when it differs.",
            },
        },
        ("project", "number", "message", "keeps_default"),
        True,
        _answer,
    ),
)

_BY_NAME = {tool.name: tool for tool in TOOLS}


def listed() -> list[dict[str, Any]]:
    """Every tool, as MCP's `tools/list` gives them."""
    return [tool.listed() for tool in TOOLS]


def call(name: str, arguments: Mapping[str, Any] | None) -> tuple[Tool, Call]:
    """The tool of that name and the command line its checked arguments build. It refuses a
    tool the table does not have, and arguments its schema does not take."""
    tool = _BY_NAME.get(name) if isinstance(name, str) else None
    if tool is None:
        raise Refused(f"refused: no tool {name!r}")
    given = _given(arguments if arguments is not None else {}, tool)
    return tool, vet(tool.build(given))


def vet(built: Call) -> Call:
    """The command line, checked once more as a whole, whatever built it: every flag is one of
    `FLAGS`, and every word is plain printable ASCII of `WORD`, with no space, quote, shell
    character or line break. Only the brief, on stdin, holds free text."""
    for word in built.argv:
        if word.startswith("-") and word not in FLAGS:
            raise Refused(f"refused: {word} is no flag of the tool table")
        if not WORD.fullmatch(word) or ".." in word:
            raise Refused(f"refused: {word!r} is not a plain word")
    if built.stdin is not None and "\x00" in built.stdin:
        raise Refused("refused: a brief holds no NUL")
    return built
