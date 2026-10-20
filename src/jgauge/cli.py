from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from jgauge import sample, session, slot, transcript, waiters
from jgauge.transcript import TranscriptError

NO_ROOM = 75
LOOK_EVERY_SECONDS = 15.0


def _print(report: dict, style: str) -> int:
    print(json.dumps(report, indent=2) if style == "json" else session.render(report))
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    try:
        report = session.of_transcript(Path(args.transcript).expanduser())
    except TranscriptError as error:
        raise SystemExit(f"jgauge: transcript {error}") from error
    return _print(report, args.format)


def cmd_context(args: argparse.Namespace) -> int:
    try:
        found = transcript.calls(transcript.lines(Path(args.transcript).expanduser()))
    except TranscriptError as error:
        raise SystemExit(f"jgauge: transcript {error}") from error
    print(found[-1].input_side if found else 0)
    return 0


def _seconds(asked: str) -> float:
    try:
        seconds = float(asked)
    except ValueError:
        seconds = -1.0
    if not 0 <= seconds < float("inf"):
        raise argparse.ArgumentTypeError(f"{asked!r} is not a number of seconds, 0 or more")
    return seconds


def _interval(asked: str) -> float:
    seconds = _seconds(asked)
    if not seconds:
        raise argparse.ArgumentTypeError("a look every 0 seconds is a loop with no pause")
    return seconds


def _wait_for_room(look: list[str], limit: float, every: float, env: dict[str, str]) -> int:
    """Look until `room` says `go` or the limit passes, the last look at the limit itself.
    Print what the last look said, its notes too, and tell the two apart by the exit code."""
    until = time.monotonic() + limit
    while True:
        looked = subprocess.run(look, capture_output=True, text=True, env=env)
        said = (looked.stdout.splitlines() or ["wait: the room check said nothing"])[-1]
        left = until - time.monotonic()
        if said == "go" or left <= 0:
            break
        time.sleep(min(every, left))
    sys.stderr.write(looked.stderr)
    print(said)
    return 0 if said == "go" else NO_ROOM


def cmd_room(args: argparse.Namespace) -> int:
    look = ["sh", str(Path(__file__).with_name("room.sh"))]
    env = {**os.environ, "SKIP_LOAD": "1" if args.light else "0"}
    if args.instance:
        env["INSTANCE"] = args.instance
    if args.wait is None:
        return subprocess.run(look, env=env).returncode
    return _wait_for_room(look, args.wait, args.every, env)


def _since(asked: str) -> int:
    try:
        return sample.since(asked)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def cmd_sample(args: argparse.Namespace) -> int:
    log = sample.log_path()
    if not args.report:
        if args.since is not None or args.pressure is not None:
            args.usage("--since and --pressure go with --report")
        sample.take(log)
        return 0
    pressure = sample.PRESSURE_LINE if args.pressure is None else args.pressure
    print("\n".join(sample.report(log, args.since, pressure)))
    return 0


def _list_waiters() -> int:
    for one in waiters.read(slot.locks_dir()):
        woken = f", woken {one.woken}" if one.woken else ""
        print(f"{one.thread} {one.lane} since {one.since}{woken}: {shlex.join(one.command)}")
    return 0


def cmd_test_slot(args: argparse.Namespace) -> int:
    if args.waiters:
        return _list_waiters()
    command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if not command:
        args.usage("no command to run")
    if args.short:
        if args.slots is not None:
            args.usage("--short takes a slot of the short lane, and --slots counts the full lane")
        return slot.run(command, slot.short(), args.thread)
    try:
        slots = slot.count(args.slots)
    except slot.BadCount as error:
        args.usage(str(error))
    return slot.run(command, slot.full(slots), args.thread)


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="jgauge",
        description="What a thread cost in tokens, from its transcript."
        " And whether the machine and the plan have room for one more thread.",
    )
    commands = top.add_subparsers(dest="command", required=True, metavar="command")

    thread = commands.add_parser(
        "session", help="print what one thread cost, from its transcript alone"
    )
    thread.add_argument("transcript", help="the session's transcript, <project>/<session>.jsonl")
    thread.add_argument("--format", choices=("table", "json"), default="table")
    thread.set_defaults(run=cmd_session)

    context = commands.add_parser(
        "context", help="print how full a thread's context is: the input side of its last call"
    )
    context.add_argument("transcript", help="the session's transcript, <project>/<session>.jsonl")
    context.set_defaults(run=cmd_context)

    room = commands.add_parser(
        "room", help="print `go`, or `wait: ` and why: the check before a launch or a review run"
    )
    room.add_argument(
        "--wait",
        metavar="SECONDS",
        type=_seconds,
        help="look again until it is `go` or this long has passed, then print the last answer:"
        f" exit 0 on `go`, {NO_ROOM} on a `wait: `",
    )
    room.add_argument(
        "--every",
        metavar="SECONDS",
        type=_interval,
        default=LOOK_EVERY_SECONDS,
        help="with --wait, how long between two looks (default: %(default)g)",
    )
    room.add_argument(
        "--light",
        action="store_true",
        help="skip the load and CPU pressure readings, for a thread that adds almost no CPU,"
        " such as a review:"
        " memory, memory pressure, /tmp and the plan still hold it",
    )
    room.add_argument(
        "--instance",
        help="the provider instance whose plan limits to read, from the ledger (default:"
        " claudeAgent, the file LIMITS names)",
    )
    room.set_defaults(run=cmd_room)

    sampled = commands.add_parser(
        "sample",
        help="append one row of load and pressure to the log, or with --report count its rows",
        description="Append one row to the log (JGAUGE_LOAD_LOG, else"
        " ~/.local/state/jgauge/load.tsv): the time, the cores, /proc/loadavg, and some and full"
        " avg10 and avg60 of /proc/pressure/{cpu,memory,io}. Rows older than 30 days are dropped.",
    )
    sampled.add_argument(
        "--report",
        action="store_true",
        help="print the rows, their span, and how many had the 1-minute load at or over room's"
        " line while CPU pressure (some avg60) was under the pressure line",
    )
    sampled.add_argument(
        "--since",
        metavar="TIME",
        type=_since,
        help="with --report, count rows from this time: seconds since the epoch or an ISO date",
    )
    sampled.add_argument(
        "--pressure",
        metavar="LINE",
        type=float,
        help=f"with --report, the CPU pressure line (default: {sample.PRESSURE_LINE:g})",
    )
    sampled.set_defaults(run=cmd_sample, usage=sampled.error)

    held = commands.add_parser(
        "test-slot",
        help="run a command while holding one of N machine-wide test slots, waiting for one",
        usage="jgauge test-slot [--slots N | --short] [--thread ID | --waiters] -- command ...",
    )
    held.add_argument(
        "--slots", metavar="N", help=f"how many slots (default: TEST_SLOTS, else {slot.DEFAULT})"
    )
    held.add_argument(
        "--short",
        action="store_true",
        help=f"take one of the {slot.SHORT_SLOTS} slots of the short lane, which never waits on a"
        f" full suite, and stop the command at {slot.SHORT_LIMIT_SECONDS:g} s",
    )
    held.add_argument(
        "--thread",
        metavar="ID",
        default="",
        help="this thread's id: wait for no slot, and with every one taken register as a waiter"
        f" jbus wakes when one is free, and end {slot.WAITING}",
    )
    held.add_argument(
        "--waiters", action="store_true", help="print the threads that wait on a slot, and end"
    )
    held.add_argument("argv", nargs=argparse.REMAINDER, help="the command, after `--`")
    held.set_defaults(run=cmd_test_slot, usage=held.error)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    return args.run(args)
