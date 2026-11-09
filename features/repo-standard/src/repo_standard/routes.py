"""`repo-standard routes --producer <cmd> --mock <cmd>`: the reference contract of a mock API.

Each command runs in a shell from where the contract runs, and prints the routes of its side as a
JSON list of `{"method": ..., "path": ...}`: the producer's are the real API's, and the mock's are
the routes the browser tests' mock answers. A path starts with `/`, and a segment `{name}` is a
path parameter. The contract fails on each mock route the producer lacks, naming it, and the
producer may serve routes the mock does not.

A mock route matches a producer route of the same method, upper-cased, and as many segments,
where a producer parameter matches any one segment and a mock parameter only a parameter: the
names of parameters differ across languages and do not count. A route that a shape cannot hold,
such as an empty method, a `{name...}` or `{$}` segment, or a path with a host, is refused: the
command that prints it writes the route the way the contract reads it.

It exits 0 when the producer serves every mock route, 1 when it lacks one, and 2 when a command
fails or prints anything else.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

PARAMETER = re.compile(r"^\{[A-Za-z_][\w]*\}$")
METHOD = re.compile(r"^[A-Z]+$")


class Unread(ValueError):
    """A command that failed, or printed something other than a list of routes."""


@dataclass(frozen=True)
class Route:
    """One route: its method and its segments, each a literal or None for a parameter."""

    method: str
    segments: tuple[str | None, ...]
    written: str

    def served_by(self, producer: Route) -> bool:
        return (
            self.method == producer.method
            and len(self.segments) == len(producer.segments)
            and all(
                theirs is None or (mine is not None and mine == theirs)
                for mine, theirs in zip(self.segments, producer.segments, strict=True)
            )
        )


def route(value: object, side: str) -> Route:
    """One printed route, refused when it is not a `{method, path}` the contract can compare."""
    if not isinstance(value, dict) or set(value) != {"method", "path"}:
        raise Unread(f"the {side} printed {json.dumps(value)}, not a {{method, path}}")
    method, path = value["method"], value["path"]
    if not isinstance(method, str) or not METHOD.match(method.upper()):
        raise Unread(f"the {side} printed the method {json.dumps(method)}, not one like GET")
    if not isinstance(path, str) or not path.startswith("/"):
        raise Unread(f"the {side} printed the path {json.dumps(path)}, not one from /")
    segments: list[str | None] = []
    for one in path.split("/")[1:]:
        if PARAMETER.match(one):
            segments.append(None)
        elif "{" in one or "}" in one:
            raise Unread(f"the {side} printed {path}, whose {one} is no {{name}} parameter")
        else:
            segments.append(one)
    return Route(method.upper(), tuple(segments), f"{method.upper()} {path}")


def routes(command: str, side: str) -> list[Route]:
    """The routes the command prints."""
    done = subprocess.run(["sh", "-c", command], capture_output=True, text=True)
    if done.returncode != 0:
        said = done.stderr.strip().splitlines()[-1:] or ["no error"]
        raise Unread(f"the {side} command `{command}` exited {done.returncode}: {said[0]}")
    try:
        printed = json.loads(done.stdout)
    except ValueError as error:
        raise Unread(f"the {side} command `{command}` printed no JSON: {error}") from error
    if not isinstance(printed, list):
        raise Unread(f"the {side} command `{command}` printed no list of routes")
    return [route(one, side) for one in printed]


def missing(producer: list[Route], mock: list[Route]) -> list[str]:
    """Each mock route no producer route serves, as the mock writes it."""
    return sorted(
        {one.written for one in mock if not any(one.served_by(real) for real in producer)}
    )


def check(producer: str, mock: str) -> tuple[list[str], int]:
    """The lines the contract prints, and its exit code."""
    try:
        real, mocked = routes(producer, "producer"), routes(mock, "mock")
    except Unread as unread:
        return [f"repo_standard routes: {unread}"], 2
    lacking = missing(real, mocked)
    if lacking:
        return [
            f"{one}: the mock answers it, and the producer has no such route" for one in lacking
        ], 1
    return [f"routes: the producer serves each of the mock's {len(mocked)} routes"], 0
