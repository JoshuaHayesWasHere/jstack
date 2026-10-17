"""The one entry point: `jroles <role>`, run by a thread before it launches one of that role.

It reads the role map and prints the role's model selection as one JSON object, which goes
into the launch as `modelSelection`. It prints nothing when the launch inherits: no file, no
line for the role, or `inherit`. A map it cannot use is said on stderr, and the launch
inherits then too, so it exits 0 for that.

It also reads `capped.json` in jbus's state directory (`jroles.failover`). While `claudeAgent`
is capped by a usage limit, a Claude selection that is on it goes out on
`claudeAgent_claude_prime`, and stderr says which instance it chose and why. While both are
capped it prints nothing, says so on stderr and exits 75: the launch waits for the reset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from jroles import ROLES, Refused, failover, read_map


def map_path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "jstack" / "roles"


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jroles", description=__doc__.split("\n\n")[1])
    parser.add_argument("role", choices=ROLES)
    role = parser.parse_args(argv).role
    path = map_path()
    try:
        text = path.read_text()
    except FileNotFoundError:
        return 0
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) else "it is not UTF-8"
        print(f"cannot read {path}: {reason}", file=sys.stderr)
        return 0
    try:
        selection = read_map(text, role)
    except Refused as refused:
        print(refused, file=sys.stderr)
        return 0
    if selection:
        choice, selection = failover.select(
            selection, failover.load(failover.path()), now or datetime.now(UTC)
        )
        if choice.why and choice.instance is None:
            print(f"jroles: {role} waits: {choice.why}", file=sys.stderr)
            return failover.WAIT
        if choice.why:
            print(f"jroles: {role} on {choice.instance}: {choice.why}", file=sys.stderr)
        print(json.dumps(selection.as_json()))
    return 0
