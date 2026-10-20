"""The one entry point: `jroles <role>`, run by a thread before it launches one of that role.

It reads the role map and prints the role's model selection as one JSON object, which goes
into the launch as `modelSelection`. It prints nothing when the launch inherits: no file, no
line for the role, or `inherit`. A map it cannot use is said on stderr, and the launch
inherits then too, so it exits 0 for that.

The selection is on the first instance of the role's pool with headroom in the ledger
(`jroles.pool`). For a pool of more than one, stderr says which instance it chose and why.
While every instance of the pool is capped it prints nothing, says so on stderr and exits 75:
the launch waits for the first reset.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from jroles import ROLES, Refused, pool


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jroles", description=__doc__.split("\n\n")[1])
    parser.add_argument("role", choices=ROLES)
    role = parser.parse_args(argv).role
    try:
        routed = pool.route(role, now or datetime.now(UTC))
    except Refused as refused:
        print(refused, file=sys.stderr)
        return 0
    if routed is None:
        return 0
    choice, instances = routed.choice, routed.selection.instances
    if choice.instance is None:
        print(f"jroles: {role} waits: {choice.why}", file=sys.stderr)
        return pool.WAIT
    if len(instances) > 1 or choice.why:
        why = choice.why or f"the first of {','.join(instances)} with headroom"
        print(f"jroles: {role} on {choice.instance}: {why}", file=sys.stderr)
    print(json.dumps(routed.as_json()))
    return 0
