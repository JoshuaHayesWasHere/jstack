"""The runner: the border between the server and jbus. systemd starts it as the user jbus runs
as, once for each connection to its socket, with the connection as its stdin and stdout
(`deploy/jbus-mcp-run.socket`). The server can reach jbus no other way.

It reads one request on stdin, `{"tool": <name>, "arguments": {...}}`, rebuilds the command line
from the tool table (`jbus_mcp.tools.call`), checks the project against its own config, runs
jbus with that command line and no shell, and prints one JSON line: the exit code, stdout and
stderr, each cut at `OUTPUT` bytes. The server's request carries no command line of its own,
so a server that is not what it should be can still run only what the table builds.

Its config is a JSON file that only root can write, `/etc/jbus-mcp/runner.json` by default:

    {"jbus": "/home/<user>/.local/bin/jbus", "projects": ["jstack"], "timeout": 60,
     "path": "/home/<user>/.local/bin:/usr/local/bin:/usr/bin"}

`jbus` is the absolute path of the command, `projects` the projects a request may name, and
`path` the `PATH` jbus runs with. The runner reads no environment variable of its own, and
passes jbus only `KEPT` of the environment systemd gave it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

from jbus_mcp import Refused, tools

__all__ = ["CONFIG", "OUTPUT", "Config", "load", "main", "request"]

CONFIG = Path("/etc/jbus-mcp/runner.json")
OUTPUT = 262144
REQUEST = tools.BRIEF + 8192
TIMEOUT = 60
LIMIT = 300
KEPT = ("HOME", "USER", "LOGNAME", "PATH", "LANG", "TZ", "XDG_RUNTIME_DIR")


class Config:
    """What the runner reads from its config file."""

    def __init__(
        self, jbus: str, projects: Sequence[str], timeout: int = TIMEOUT, path: str = ""
    ) -> None:
        self.jbus, self.projects, self.timeout = jbus, frozenset(projects), timeout
        self.path = path


def load(path: Path) -> Config:
    """Read and check the runner's config. It refuses a relative `jbus`, a project that is not
    a name, and a timeout out of range."""
    try:
        given = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Refused(f"refused: the runner's config {path} cannot be read: {error}") from None
    jbus, projects = given.get("jbus"), given.get("projects")
    timeout, search = given.get("timeout", TIMEOUT), given.get("path", "")
    if not isinstance(jbus, str) or not os.path.isabs(jbus):
        raise Refused(f"refused: {path}: jbus is the command's absolute path")
    if not isinstance(projects, list) or not all(
        isinstance(one, str) and tools.PROJECT.fullmatch(one) for one in projects
    ):
        raise Refused(f"refused: {path}: projects is a list of project names")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 0 < timeout <= LIMIT:
        raise Refused(f"refused: {path}: timeout is seconds, 1 to {LIMIT}")
    if not isinstance(search, str) or (
        search and not all(os.path.isabs(one) for one in search.split(":"))
    ):
        raise Refused(f"refused: {path}: path is absolute directories split by colons")
    return Config(jbus, projects, timeout, search)


def request(text: str, config: Config) -> tools.Call:
    """The command line one request builds, or a refusal: a request that is not one tool and
    its arguments, a tool the table does not have, or a project the config does not name."""
    try:
        asked = json.loads(text)
    except ValueError:
        raise Refused("refused: a request is one JSON object") from None
    if not isinstance(asked, dict) or set(asked) - {"tool", "arguments"}:
        raise Refused("refused: a request is {tool, arguments}")
    _, built = tools.call(asked.get("tool", ""), asked.get("arguments") or {})
    project = (asked.get("arguments") or {}).get("project")
    if project is not None and project not in config.projects:
        raise Refused(f"refused: {project} is not a project this runner serves")
    return built


def _cut(text: str) -> tuple[str, bool]:
    raw = text.encode("utf-8", "replace")
    if len(raw) <= OUTPUT:
        return text, False
    return raw[:OUTPUT].decode("utf-8", "ignore"), True


def execute(
    built: tools.Call, config: Config, run: Callable[..., Any] = subprocess.run
) -> dict[str, Any]:
    """Run jbus with the built command line, with no shell, in the user's home, and return
    what it printed."""
    env = {key: os.environ[key] for key in KEPT if key in os.environ}
    if config.path:
        env["PATH"] = config.path
    try:
        done = run(
            [config.jbus, *built.argv],
            input=built.stdin if built.stdin is not None else "",
            capture_output=True,
            text=True,
            timeout=config.timeout,
            cwd=env.get("HOME") or "/",
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"code": 124, "stdout": "", "stderr": f"jbus ran past {config.timeout} s"}
    except OSError as error:
        return {"code": 127, "stdout": "", "stderr": f"jbus could not start: {error}"}
    stdout, cut_out = _cut(done.stdout or "")
    stderr, cut_err = _cut(done.stderr or "")
    return {"code": done.returncode, "stdout": stdout, "stderr": stderr, "cut": cut_out or cut_err}


def main(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    config_path: Path | None = None,
    run: Callable[..., Any] = subprocess.run,
) -> int:
    """Read one request, run it, print one JSON line. A refusal prints `{"refused": <why>}`
    and exits 2."""
    given, out = stdin or sys.stdin, stdout or sys.stdout
    path = config_path or CONFIG
    try:
        config = load(path)
        text = given.read(REQUEST + 1)
        if len(text) > REQUEST:
            raise Refused(f"refused: a request is at most {REQUEST} characters")
        built = request(text, config)
    except Refused as error:
        out.write(json.dumps({"refused": str(error)}) + "\n")
        return 2
    out.write(json.dumps(execute(built, config, run)) + "\n")
    return 0
