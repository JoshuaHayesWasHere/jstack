"""The one entry point, `jroles <role>`, which a thread runs before it launches a thread of
that role.

It reads the role map and prints the role's model selection as one JSON object, which the
launch takes as `modelSelection`. For `review` it prints one such line for each reviewer that
the map lists, in order, and each line is one launch. It prints nothing when the launch
inherits, which is when there is no file, no line for the role, or `inherit`. When it cannot
use the map, it says why on stderr and exits 0, since the launch inherits then too.

Each selection names the first instance of its pool with headroom in the ledger
(`jroles.pool`). For a pool of more than one instance, it says on stderr which instance it
chose and why. While every instance of a pool is capped, it prints nothing for any line of the
role, says so on stderr, and exits 75, and the launch waits for the first reset.

`jroles mirror [--check] [--instance <id>]` is not a role. It keeps each extra Claude home
that providers.json declares as a mirror of `~/.claude` (`jroles.mirror`).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from jroles import ROLES, Refused, mirror, pool


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["mirror"]:
        return mirror.main(argv[1:])
    parser = argparse.ArgumentParser(
        prog="jroles",
        description=__doc__.split("\n\n")[1],
        epilog="jroles mirror [--check] [--instance ID]: keep each extra Claude home a mirror",
    )
    parser.add_argument("role", choices=(*ROLES, "mirror"))
    role = parser.parse_args(argv).role
    try:
        routed = pool.routes(role, now or datetime.now(UTC))
    except Refused as refused:
        print(refused, file=sys.stderr)
        return 0
    capped = [one.choice.why for one in routed if one.choice.instance is None]
    if capped:
        print(f"jroles: {role} waits: {'; '.join(capped)}", file=sys.stderr)
        return pool.WAIT
    for one in routed:
        choice, instances = one.choice, one.selection.instances
        if len(instances) > 1 or choice.why:
            why = choice.why or f"the first of {','.join(instances)} with headroom"
            print(f"jroles: {role} on {choice.instance}: {why}", file=sys.stderr)
    for one in routed:
        print(json.dumps(one.as_json()))
    return 0
