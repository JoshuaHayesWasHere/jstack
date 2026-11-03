"""MCP's JSON-RPC messages, for a server that has tools and nothing else.

`answer` takes one parsed message and returns the response, or None for a notification. It
knows `initialize`, `ping`, `tools/list` and `tools/call`, and leaves what a tool does to the
`call` it is given.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from jbus_mcp import tools

__all__ = ["INSTRUCTIONS", "VERSIONS", "answer", "error"]

VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
NAME = "jbus-mcp"
VERSION = "0.1.0"
INSTRUCTIONS = (
    "These tools read jbus on Yelena and queue work for the user. Reads are free to use. "
    "jbus_queue_add only queues a row. jbus_queue_approve and jbus_answer need the user's own "
    "message in T3 Code, by its thread and message id, and jbus reads that message itself: never "
    "make one up, and ask the user for it. Nothing here merges, launches by itself or sends a "
    "message to a thread."
)
PARSE, INVALID, METHOD, PARAMS = -32700, -32600, -32601, -32602

Call = Callable[[str, Mapping[str, Any]], dict[str, Any]]


def error(id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _result(id: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "result": dict(result)}


def _initialize(params: Mapping[str, Any]) -> dict[str, Any]:
    asked = params.get("protocolVersion")
    return {
        "protocolVersion": asked if asked in VERSIONS else VERSIONS[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": NAME, "title": "jbus on Yelena", "version": VERSION},
        "instructions": INSTRUCTIONS,
    }


def answer(message: Any, call: Call) -> dict[str, Any] | None:
    """The response to one message, or None where the message is a notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return error(None, INVALID, "a message is one JSON-RPC 2.0 object")
    method, id = message.get("method"), message.get("id")
    if "id" not in message:
        return None
    if not isinstance(method, str):
        return error(id, INVALID, "a request names its method")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return error(id, PARAMS, "params is an object")
    if method == "initialize":
        return _result(id, _initialize(params))
    if method == "ping":
        return _result(id, {})
    if method == "tools/list":
        return _result(id, {"tools": tools.listed()})
    if method == "tools/call":
        name, arguments = params.get("name"), params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return error(id, PARAMS, "tools/call takes a name and an object of arguments")
        return _result(id, call(name, arguments))
    return error(id, METHOD, f"no method {method}")
