"""The verbs, as loops over needs().

    python -m jinstall <checkout> [--check | --uninstall | --doctor | --setup]

Install and --check are one function with one branch, whether `put` is called between two
probes, so they cannot print different lines for one machine and a second install is a check. The
doctor probes the same kinds and prints through the same `say`, so it gives --check's answer
about every part both print. --setup walks the same list once, in order: it seeds each config
that is not there, puts each due Carried need, and says what is left for the user.
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from jinstall.kinds import Asks, Carried, Found, Seeded, State
from jinstall.machine import Machine, Moved, Refused
from jinstall.needs import Level, Need, needs

USAGE = "usage: install.sh [--check | --uninstall | --doctor | --setup]"


class Verb(Enum):
    INSTALL = ""
    CHECK = "--check"
    UNINSTALL = "--uninstall"
    DOCTOR = "--doctor"
    SETUP = "--setup"


@dataclass(frozen=True)
class Report:
    """What a verb leaves: the lines for stdout, a note for stderr, the exit code."""

    lines: tuple[str, ...]
    note: str
    code: int


def say(need: Need, found: Found) -> str:
    """The one place a line is made, for install, --check and --doctor:
    `<state> <level> <name>[ -> <detail>]`."""
    line = f"{found.state.value} {need.level.value} {need.name}"
    return f"{line} -> {found.detail}" if found.detail else line


def refused(machine: Machine, verb: str) -> Report | None:
    """A linked worktree under the account's own HOME: its links would move every live skill
    to it, so nothing is written from one."""
    if not machine.in_a_worktree_of_the_account():
        return None
    why = f"install.sh: {machine.checkout} is a linked worktree, and HOME is your own: "
    return Report((), f"{why}{verb} from the main checkout", 1)


def install(machine: Machine, write: bool) -> Report:
    """Each due Carried need: probe; when `write` and the answer is missing or a replaceable
    old, put and probe again; the line is the last probe's. Exit 1 when a line is not ok.
    A put that fails is caught: its reason goes to `note`, the loop goes on, and the second
    probe says what is true. With `write`, a linked worktree under the account's own HOME is
    refused before anything is probed: its links would move every live skill to it."""
    if write and (refusal := refused(machine, "install")):
        return refusal
    lines, notes, code = [], [], 0
    for need in needs(machine):
        kind = need.kind
        if not isinstance(kind, Carried) or not kind.due(machine):
            continue
        found = kind.probe(machine)
        if write and found.state is not State.OK and found.replaceable:
            try:
                kind.put(machine)
            except (OSError, Moved, Refused) as error:
                notes.append(f"install.sh: {need.name}: {error}")
            found = kind.probe(machine)
        if found.state is not State.OK:
            code = 1
        lines.append(say(need, found))
    return Report(tuple(lines), "\n".join(notes), code)


def setup(machine: Machine) -> Report:
    """Every need once, in order, one line each: `done <name>` for what this run wrote,
    `already <name>` for what was there, `needs you <name> -> <command>` for what is the user's.
    A Seeded need that is missing is written; a due Carried need that is not ok is put, as the
    install puts it. The jbus config comes before the units in the list, so a run that seeds it
    links the units too. A second run writes nothing. Exit 1 while a hard need is the user's."""
    if refusal := refused(machine, "set up"):
        return refusal
    lines, notes, code = [], [], 0
    for need in needs(machine):
        kind = need.kind
        if isinstance(kind, Carried) and not kind.due(machine):
            continue
        found = kind.probe(machine)
        if found.state is State.OK:
            lines.append(f"already {need.name}")
            continue
        mend = None
        if isinstance(kind, Seeded) and found.state is State.MISSING:
            mend = lambda kind=kind: machine.seed(kind.path, kind.text(machine), kind.mode)  # noqa: E731
        elif isinstance(kind, Carried) and found.replaceable:
            mend = lambda kind=kind: kind.put(machine)  # noqa: E731
        if mend is not None:
            try:
                mend()
            except (OSError, Moved, Refused) as error:
                notes.append(f"install.sh: {need.name}: {error}")
            found = kind.probe(machine)
            if found.state is State.OK:
                lines.append(f"done {need.name}")
                continue
        ask = kind.ask(machine) if isinstance(kind, Asks) else found.detail
        code |= need.level is Level.HARD
        lines.append(f"needs you {need.name} -> {ask or found.state.value}")
    return Report(tuple(lines), "\n".join(notes), code)


def uninstall(machine: Machine) -> Report:
    """Every Carried and Seeded need, due or not, backwards: drop. Then `machine.sweep()`. Lines are
    `removed <piece>` and `kept <piece> -> <why>`, and nothing for what is absent. Exit 1
    only when a piece of this checkout's could not be removed. A second run prints nothing."""
    lines, notes, code = [], [], 0
    kinds = [
        need.kind for need in reversed(needs(machine)) if isinstance(need.kind, (Carried, Seeded))
    ]
    for step in [*(lambda kind=kind: kind.drop(machine) for kind in kinds), machine.sweep]:
        try:
            dropped = step()
        except (OSError, Moved, Refused) as error:
            notes.append(f"install.sh: {error}")
            code = 1
            continue
        lines += [f"removed {piece}" for piece in dropped.removed]
        lines += [f"kept {piece}" for piece in dropped.kept]
    return Report(tuple(lines), "\n".join(notes), code)


def doctor(machine: Machine) -> Report:
    """Probe every need that is only probed and every due Carried need, and write nothing.
    The last line is `doctor: ok` or `doctor: not ok, <n> hard`. Exit 1 only when a hard need
    is not ok: an optional one never changes it."""
    lines, hard = [], 0
    for need in needs(machine):
        if isinstance(need.kind, Carried) and not need.kind.due(machine):
            continue
        found = need.kind.probe(machine)
        hard += found.state is not State.OK and need.level is Level.HARD
        lines.append(say(need, found))
    lines.append(f"doctor: not ok, {hard} hard" if hard else "doctor: ok")
    return Report(tuple(lines), "", 1 if hard else 0)


def parse(argv: Sequence[str]) -> tuple[Machine, Verb]:
    """`<checkout> [verb]`. Anything else: the usage line on stderr and SystemExit(2)."""
    verbs = {verb.value: verb for verb in Verb if verb is not Verb.INSTALL}
    if len(argv) not in (1, 2) or (argv[1:] and argv[1] not in verbs):
        print(USAGE, file=sys.stderr)
        raise SystemExit(2)
    return Machine.here(Path(argv[0])), verbs[argv[1]] if argv[1:] else Verb.INSTALL


def main(argv: Sequence[str] | None = None) -> int:
    machine, verb = parse(list(sys.argv[1:] if argv is None else argv))
    if verb is Verb.CHECK:
        report = install(machine, write=False)
    elif verb is Verb.DOCTOR:
        report = doctor(machine)
    elif verb is Verb.SETUP:
        with machine.alone():
            report = setup(machine)
    else:
        with machine.alone():
            report = uninstall(machine) if verb is Verb.UNINSTALL else install(machine, write=True)
    for line in report.lines:
        print(line)
    if report.note:
        print(report.note, file=sys.stderr)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
