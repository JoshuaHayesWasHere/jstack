from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import jroles
import jsettings
from jgauge import limits, runner, sample, session, sizes, slot, transcript, waiters
from jgauge.transcript import TranscriptError
from jroles import ledger, pool

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
    """Run `room` until it prints `go` or the time limit passes, and run it a last time at the
    limit itself. Print what the last run printed, with its notes. Exit with code 0 on `go`,
    and with the code `NO_ROOM` otherwise."""
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


def _pool(role: str) -> str:
    """The role's pools in the form `room.sh` reads from `POOL`: commas join the instances of a
    line, and a space separates one line from the next. The value is empty where the role
    inherits. It is also empty where `pool.selections` refuses the role map, and the function
    then prints a note on stderr: `room.sh` reads the built-in instance's file instead."""
    try:
        chosen = pool.selections(role)
    except jroles.Refused as refused:
        print(f"note: room reads {ledger.BUILT_IN}'s limits: {refused}", file=sys.stderr)
        return ""
    return " ".join(",".join(one.instances) for one in chosen)


def cmd_room(args: argparse.Namespace) -> int:
    look = ["sh", str(Path(__file__).with_name("room.sh"))]
    try:
        headroom = jsettings.load().headroom
    except jsettings.Invalid as error:
        raise SystemExit(f"jgauge: {error}") from error
    env = {**os.environ, "SKIP_LOAD": "1" if args.light else "0", "HEADROOM": f"{headroom:g}"}
    env["POOL"] = args.instance if args.instance is not None else _pool(args.role)
    if args.wait is None:
        return subprocess.run(look, env=env).returncode
    return _wait_for_room(look, args.wait, args.every, env)


def cmd_limits(args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    try:
        said = limits.check(now) if args.check else limits.run(now)
    except limits.Stale as why:
        raise SystemExit(f"jgauge: {why}") from None
    if said:
        print("\n".join(said))
    return 1 if args.check and said else 0


def _since(asked: str) -> int:
    try:
        return sample.since(asked)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def cmd_sample(args: argparse.Namespace) -> int:
    log = sample.log_path()
    if not args.report:
        if args.since is not None or args.until is not None or args.pressure is not None:
            args.usage("--since, --until and --pressure go with --report")
        sample.take(log)
        return 0
    pressure = sample.PRESSURE_LINE if args.pressure is None else args.pressure
    print("\n".join(sample.report(log, args.since, pressure, args.until)))
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
        try:
            lane = slot.short()
        except sizes.Refused as error:
            args.usage(str(error))
        return slot.run(command, lane, args.thread)
    try:
        slots = slot.count(args.slots)
    except slot.BadCount as error:
        args.usage(str(error))
    return slot.run(command, slot.full(slots), args.thread)


def _command(args: argparse.Namespace) -> str:
    command = sys.stdin.read()
    if not command.strip():
        args.usage("no command on stdin: put it in the step's here-document")
    return command


def cmd_check(args: argparse.Namespace) -> int:
    command = _command(args)
    try:
        slot.count(None)
    except slot.BadCount as error:
        args.usage(str(error))
    return runner.check(command, args.thread, args.wait)


def cmd_proof(args: argparse.Namespace) -> int:
    command = _command(args)
    try:
        slot.short()
    except sizes.Refused as error:
        args.usage(str(error))
    return runner.proof(command, Path(args.dir), args.kept, args.thread, args.wait)


def cmd_sizes(args: argparse.Namespace) -> int:
    """Print the three machine sizes as their callers get them. After the sizes, print room's
    lines."""
    jbus_config = Path(os.environ.get("JBUS_CONFIG_DIR") or Path.home() / ".config" / "jbus")
    try:
        found = sizes.every(jbus_config / "config.toml")
    except sizes.Refused as error:
        raise SystemExit(f"jgauge: {error}") from error
    for one in found:
        print(one.line())
    room = " ".join(f"{name}={sample.room_line(name)}" for name in sample.ROOM_LINES)
    print(f"room {room}  {sample.ROOM}")
    if os.environ.get("TEST_SLOTS") is not None:
        print(
            f"note: TEST_SLOTS={os.environ['TEST_SLOTS']} is set here and jbus.service does not"
            f" see it: set test_slots in {sizes.path()}"
        )
    return 0


def _waited(commands, name: str, about: str, lane: str, run) -> argparse.ArgumentParser:
    waited = commands.add_parser(
        name,
        help=about,
        description=f"{about[0].upper()}{about[1:]}. The run holds {lane} in a session of its"
        " own, so it outlives the call. A later call joins a run that is going, and gives the"
        " answer of one that ended between calls once. The answers are started, joined,"
        " checked, waiting (exit 76), stale (exit 75), done, running and lost, as"
        " features/jgauge/docs/jgauge.md lists them.",
    )
    waited.add_argument(
        "--thread",
        metavar="ID",
        default="",
        help="this thread's id: with every slot taken, register as a waiter jbus wakes, and end"
        f" {slot.WAITING}",
    )
    waited.add_argument(
        "--wait",
        metavar="SECONDS",
        type=_seconds,
        default=runner.WAIT_SECONDS,
        help="how long this call waits on the run before it says `running` (default: %(default)g)",
    )
    waited.set_defaults(run=run, usage=waited.error)
    return waited


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
    asked = room.add_mutually_exclusive_group()
    asked.add_argument(
        "--role",
        choices=jroles.ROLES,
        default="crew",
        help="the role whose pool's plan limits to read, from the role map and the ledger: wait"
        " only while every instance of a line's pool is full (default: %(default)s; a role"
        " with no pool reads claudeAgent's, the file LIMITS names)",
    )
    asked.add_argument(
        "--instance",
        help="the one provider instance whose plan limits to read, from the ledger, in place"
        " of a role's pool",
    )
    room.set_defaults(run=cmd_room)

    read = commands.add_parser(
        "limits",
        help="read each Claude account's five-hour and weekly use into the ledger, ahead of time",
        description="For each Claude home of ~/.config/jstack/providers.json, and ~/.claude"
        " where it names none, read the account's five-hour and weekly use from the usage"
        " endpoint with the home's own token while it has not expired, else from the answer"
        " Claude Code cached in its .claude.json while that is under 15 min old, and merge it"
        " into the instance's ledger file. A home neither answers for keeps its last lines and"
        " prints `stale <instance>: <why>`. No token is refreshed or printed, and neither file"
        " is written.",
    )
    read.add_argument(
        "--check",
        action="store_true",
        help="read nothing: print `stale <instance>: <why>` for each ledger file 15 min old or"
        " more, or missing, and exit 1 if there is one",
    )
    read.set_defaults(run=cmd_limits)

    sampled = commands.add_parser(
        "sample",
        help="append one row of load and pressure to the log, or with --report count its rows",
        description="Append one row to the log (JGAUGE_LOAD_LOG, else"
        " ~/.local/state/jgauge/load.tsv): the time, the cores, /proc/loadavg, and some and full"
        " avg10 and avg60 of /proc/pressure/{cpu,memory,io}. On macOS the load is sysctl's"
        " vm.loadavg and the pressure fields are empty. Rows older than 30 days are dropped.",
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
        "--until",
        metavar="TIME",
        type=_since,
        help="with --report, count rows before this time, as --since takes it",
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
        "--slots",
        metavar="N",
        help="how many slots (default: TEST_SLOTS, else test_slots in the machine file, else"
        " derived from the machine: `jgauge sizes` prints it)",
    )
    held.add_argument(
        "--short",
        action="store_true",
        help="take one of the slots of the short lane (short_slots in `jgauge sizes`), which"
        f" never waits on a full suite, and stop the command at {slot.SHORT_LIMIT_SECONDS:g} s",
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

    _waited(
        commands,
        "check",
        "start or join the check command, read from stdin, on this worktree under a test slot,"
        " and wait on it: the crew skill's one run of the check command",
        "a slot of the full lane",
        cmd_check,
    )
    proof = _waited(
        commands,
        "proof",
        "start or join a reviewer's proof, read from stdin, at the head kept at the start, and"
        " wait on it: the pr-review skill's proof",
        "a slot of the short lane",
        cmd_proof,
    )
    proof.add_argument(
        "--dir", required=True, help="the folder of the review's prompt, where the proof's files go"
    )
    proof.add_argument("--kept", required=True, help="the head kept at the start of the review")

    machine = commands.add_parser(
        "sizes",
        help="print the machine's sizes (test slots, short slots, crew cap), where each came"
        " from, and room's lines",
        description="Print test_slots, short_slots and max_running as their callers get them:"
        " from a flag or TEST_SLOTS, the local file (~/.config/jstack/machine.toml, or"
        " max_running in ~/.config/jbus/config.toml), else derived from the machine's cores and"
        " memory. Then room's lines, from features/jgauge/src/jgauge/room.sh."
        " features/jgauge/docs/limits.md lists every limit.",
    )
    machine.set_defaults(run=cmd_sizes)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    return args.run(args)
