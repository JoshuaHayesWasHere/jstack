"""The one entry point, `jroles <role>`, which a thread runs before it launches a thread of
that role.

It reads the role map and prints the role's model selection as one JSON object, which the
launch takes as `modelSelection`. For `review` it prints one such line for each reviewer that
the map lists, in order, and the thread makes one launch for each line. It prints nothing when
the new thread inherits the model of the thread that launches it. That happens when there is
no file, no line for the role, or a line that says `inherit`. When it cannot use the map, it
says why on stderr and exits 0, since the new thread inherits then too.

Each selection names the first instance of its pool with headroom in the ledger
(`jroles.pool`). For a pool of more than one instance, it says on stderr which instance it
chose and why. While every instance of a pool is capped, it prints nothing for any line of the
role, says so on stderr, and exits 75. The launch then waits for the first reset. With
`--thread <id>` it also registers that thread as a waiter until that reset (`jroles.waits`), and a
pass of `jbus poll` after it wakes the thread once. A run with `--thread` that finds headroom takes
the thread out of the waiters.

`jroles mirror [--check] [--instance <id>]` is not a role. For each extra Claude home that
T3's settings list, it makes that home a mirror of `~/.claude` (`jroles.mirror`).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from jroles import ROLES, Refused, mirror, pool, waits


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
    parser.add_argument("--thread", default="", help="register this thread to wake at the reset")
    args = parser.parse_args(argv)
    role, now = args.role, now or datetime.now(UTC)
    try:
        routed = pool.routes(role, now)
    except Refused as refused:
        print(refused, file=sys.stderr)
        return 0
    capped = [one.choice.why for one in routed if one.choice.instance is None]
    if capped:
        print(f"jroles: {role} waits: {'; '.join(capped)}", file=sys.stderr)
        resets = [one.choice.until for one in routed if one.choice.until is not None]
        if args.thread and resets:
            wait = waits.register(waits.where(), args.thread, role, min(resets), now)
            said = f"{wait.thread} is registered as a waiter; jbus wakes it after {wait.until}"
            print(f"jroles: {said}", file=sys.stderr)
        return pool.WAIT
    if args.thread:
        waits.drop(waits.where(), args.thread, role)
    for one in routed:
        choice, instances = one.choice, one.selection.instances
        if len(instances) > 1 or choice.why:
            why = choice.why or f"the first of {','.join(instances)} with headroom"
            print(f"jroles: {role} on {choice.instance}: {why}", file=sys.stderr)
    for one in routed:
        print(json.dumps(one.as_json()))
    return 0
