"""`jbus-mcp render`: the deploy files of one machine, made from the templates in `deploy/`.

The templates name no machine, user or host. Each value a machine sets is a placeholder,
`@NAME@`, and `render` writes a copy of every template with each placeholder filled in, to a
folder of its own. It installs nothing and starts nothing: the install steps of
`docs/jbus-mcp.md` copy what it wrote, by hand, as root.
"""

from __future__ import annotations

import json
import os
import pwd
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from jbus_mcp import Refused, tools

__all__ = ["PLACEHOLDER", "PREFIX", "PYTHON", "TEMPLATES", "Values", "render", "values"]

TEMPLATES = Path("features/jbus-mcp/deploy")
"""Where the templates are in a checkout, relative to its root, where `render` runs."""
PREFIX = "/opt/jbus-mcp"
PYTHON = "/usr/bin/python3"
PORT = 4391
PLACEHOLDER = re.compile(r"@[A-Z_]+@")
USER = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
HOST = re.compile(r"(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
ABSOLUTE = re.compile(r"/[A-Za-z0-9._/-]*")
EXECUTABLE = 0o755
PLAIN = 0o644


@dataclass(frozen=True)
class Values:
    """What one machine fills in: the user jbus runs as and that user's home, the public
    hostname, the projects a request may name, the server's loopback port, the folder of the
    code's root-owned copy, and the Python that runs it."""

    user: str
    home: str
    host: str
    projects: tuple[str, ...]
    port: int = PORT
    prefix: str = PREFIX
    python: str = PYTHON

    def table(self) -> dict[str, str]:
        return {
            "@JBUS_USER@": self.user,
            "@JBUS_HOME@": self.home,
            "@HOST@": self.host,
            "@PROJECTS@": json.dumps(list(self.projects)),
            "@PORT@": str(self.port),
            "@PREFIX@": self.prefix,
            "@PYTHON@": self.python,
        }


def _home(user: str) -> str:
    try:
        return pwd.getpwnam(user).pw_dir
    except KeyError:
        why = f"refused: no user {user} on this machine: name its home with --home"
        raise Refused(why) from None


def values(
    user: str,
    host: str,
    projects: Sequence[str],
    home: str | None = None,
    port: int = PORT,
    prefix: str = PREFIX,
    python: str = PYTHON,
) -> Values:
    """Check each value, and look up the user's home when none is given. Every path is
    absolute and plain, so no value can carry a space, a quote or a second line into a unit."""
    if not USER.fullmatch(user):
        raise Refused(f"refused: {user!r} is not a user name")
    if not HOST.fullmatch(host):
        raise Refused(f"refused: {host!r} is not a hostname, such as jbus-mcp.example.com")
    if not projects or not all(tools.PROJECT.fullmatch(one) for one in projects):
        raise Refused("refused: name each project the connector may name, one --project each")
    if isinstance(port, bool) or not 1024 <= port <= 65535:
        raise Refused(f"refused: {port} is not a port from 1024 to 65535")
    chosen = home if home is not None else _home(user)
    for name, path in (("home", chosen), ("prefix", prefix), ("python", python)):
        if not ABSOLUTE.fullmatch(path) or ".." in path.split("/"):
            raise Refused(f"refused: --{name} {path!r} is not a plain absolute path")
    return Values(user, chosen.rstrip("/") or "/", host, tuple(projects), port, prefix, python)


def render(out: Path, given: Values, source: Path = TEMPLATES) -> list[Path]:
    """Write each template of `source` to `out`, a folder that is new or empty, with every
    placeholder filled in, and return what it wrote. It refuses a placeholder it does not know,
    so no file is written with one left in."""
    if not source.is_dir():
        raise Refused(f"refused: no templates at {source}: run render from a checkout's root")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise Refused(f"refused: {out} is not a new or empty folder")
    table = given.table()
    made = {}
    for template in sorted(source.iterdir()):
        if not template.is_file():
            continue
        text = template.read_text(encoding="utf-8")
        filled = PLACEHOLDER.sub(lambda found: table.get(found[0], found[0]), text)
        if left := sorted(set(PLACEHOLDER.findall(filled))):
            why = f"refused: {template.name} has {', '.join(left)}, which render does not fill"
            raise Refused(why)
        made[template.name] = (filled, os.access(template, os.X_OK))
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (filled, executable) in made.items():
        path = out / name
        path.write_text(filled, encoding="utf-8")
        path.chmod(EXECUTABLE if executable else PLAIN)
        written.append(path)
    return written
