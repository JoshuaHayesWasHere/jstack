"""`jbus-mcp`: a remote MCP server that lets a claude.ai connector read jbus and queue work.

It runs on the machine jbus runs on, as a system user of its own that holds nothing of jbus's:
no state, no T3 Code sign-in and no bot key. It reaches jbus only through one socket, where
systemd starts the runner (`jbus_mcp.run`) as the user jbus runs as, once for each connection.
The runner reads one request and rebuilds the command line from the tool table
(`jbus_mcp.tools`) itself, so the server can ask for nothing the table does not have.

The server speaks MCP over Streamable HTTP on `127.0.0.1` (`jbus_mcp.server`), behind a
Cloudflare Tunnel, and is its own OAuth authorization server (`jbus_mcp.oauth`): one client,
made on the machine, and a sign-in that takes a one-time code made on the machine too. It logs
every call and rate-limits them (`jbus_mcp.limits`).
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["Refused", "state_dir"]

STATE = "JBUS_MCP_STATE"
SYSTEMD_STATE = "STATE_DIRECTORY"
DEFAULT_STATE = Path("/var/lib/jbus-mcp")


class Refused(Exception):
    """A request or a command that jbus-mcp will not carry out. Its text says why."""


def state_dir() -> Path:
    """The server's own state: `JBUS_MCP_STATE`, else the directory systemd's
    `StateDirectory=` made, else `/var/lib/jbus-mcp`."""
    given = os.environ.get(STATE) or os.environ.get(SYSTEMD_STATE, "").split(":")[0]
    return Path(given) if given else DEFAULT_STATE
