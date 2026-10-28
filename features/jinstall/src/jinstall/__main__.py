"""The verbs, as loops over needs().

    python -m jinstall <checkout> [--check | --uninstall | --doctor | --setup | --repo [<path>]]

is what `install.sh` runs in a checkout. `jinstall [<verb>]` (`cli`) is the command a release
installs.

Install and --check are one function, which branches once: install calls `put` between two
probes, and --check does not. So they cannot print different lines for one machine, and a second
install is a check. The doctor probes the same kinds and prints through the same `say`, so it
gives --check's answer for every part that both print. --setup walks the same list once, in
order. It seeds each config that is not there, puts each due Carried need, and says what is left
for the user. --repo sets one more repo up: it adds the repo to the machine's list and puts the
git hooks of that repo alone, through the same loop as install.
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from jinstall.kinds import Asks, Carried, Found, Seeded, State
from jinstall.machine import Machine, Moved, Refused
from jinstall.needs import Level, Need, needs
from jinstall.repos import GitHook, main_checkout

USAGE = "usage: install.sh [--check | --uninstall | --doctor | --setup | --repo [<path>]]"


class Verb(Enum):
    INSTALL = ""
    CHECK = "--check"
    UNINSTALL = "--uninstall"
    DOCTOR = "--doctor"
    SETUP = "--setup"
    REPO = "--repo"


@dataclass(frozen=True)
class Report:
    """What a verb returns: the lines for stdout, a note for stderr, and the exit code."""

    lines: tuple[str, ...]
    note: str
    code: int


def say(need: Need, found: Found) -> str:
    """The line for one need, `<state> <level> <name>[ -> <detail>]`. Install, --check and
    --doctor make every line here and nowhere else."""
    line = f"{found.state.value} {need.level.value} {need.name}"
    return f"{line} -> {found.detail}" if found.detail else line


def refused(machine: Machine, verb: str) -> Report | None:
    """The refusal for a linked worktree under the account's own HOME, or None for any other
    checkout. The install writes nothing from such a worktree, because the install's links would
    point every live skill at the worktree."""
    if not machine.in_a_worktree_of_the_account():
        return None
    why = f"install.sh: {machine.checkout} is a linked worktree, and HOME is your own: "
    return Report((), f"{why}{verb} from the main checkout", 1)


def install(machine: Machine, write: bool, repo: Path | None = None) -> Report:
    """Probe each due Carried need. With `write`, put the need and probe it again when the
    probe answers missing, or answers an old that is replaceable. Each line gives the answer
    of the last probe, and the exit code is 1 when a line is not ok. A repo's own git hook in
    a repo that is not jstack's is the exception (`yours`): its line says so, and it leaves
    the exit code as it is, since no install can put that hook.

    When a put fails, the loop catches the failure, adds its reason to `note`, and goes on.
    The second probe then reports the actual state. With `write`, the function refuses a
    linked worktree under the account's own HOME before it probes anything, since the
    install's links would point every live skill at that worktree.

    With `repo`, it walks only the git hooks of that repo."""
    if write and (refusal := refused(machine, "install")):
        return refusal
    lines, notes, code = [], [], 0
    for need in needs(machine):
        kind = need.kind
        if not isinstance(kind, Carried) or not kind.due(machine):
            continue
        if repo is not None and not (isinstance(kind, GitHook) and kind.repo == repo):
            continue
        found = kind.probe(machine)
        if write and found.state is not State.OK and found.replaceable:
            try:
                if said := kind.put(machine):
                    notes += [f"install.sh: {need.name}: {line}" for line in said.splitlines()]
            except (OSError, Moved, Refused) as error:
                notes.append(f"install.sh: {need.name}: {error}")
            found = kind.probe(machine)
        if found.state is not State.OK and not yours(need, found):
            code = 1
        lines.append(say(need, found))
    return Report(tuple(lines), "\n".join(notes), code)


def yours(need: Need, found: Found) -> bool:
    """Whether the line is an optional git hook that is the repo's own: one the install never
    writes over."""
    return need.level is Level.OPTIONAL and isinstance(need.kind, GitHook) and not found.replaceable


def setup(machine: Machine) -> Report:
    """Walk every need once, in order, and print one line for each. The line is `done <name>`
    for what this run wrote, `already <name>` for what was there, and
    `needs you <name> -> <command>` for each step that is left for the user. An optional
    need that is missing is a layer the user has not set up, and its line is the doctor's,
    `missing optional <name> -> <command>`. A repo's own git hook (`yours`) gets that line too:
    the repo runs without jstack's hook, and no step of the user's is owed.

    Setup writes a Seeded need that is missing, and puts a due Carried need that is not ok, as
    the install puts it. The jbus config comes before the units in the list, so a run that
    seeds it links the units too. A second run writes nothing. The exit code is 1 while a hard
    need is left for the user."""
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
        seeds = isinstance(kind, Seeded) and found.state is State.MISSING
        puts = isinstance(kind, Carried) and found.replaceable
        if seeds or puts:
            try:
                if seeds:
                    machine.seed(kind.path, kind.text(machine), kind.mode)
                elif said := kind.put(machine):
                    notes += [f"install.sh: {need.name}: {line}" for line in said.splitlines()]
            except (OSError, Moved, Refused) as error:
                notes.append(f"install.sh: {need.name}: {error}")
            found = kind.probe(machine)
            if found.state is State.OK:
                lines.append(f"done {need.name}")
                continue
        ask = kind.ask(machine) if isinstance(kind, Asks) else found.detail
        code |= need.level is Level.HARD
        layer = need.level is Level.OPTIONAL and found.state is State.MISSING
        said = "missing optional" if layer or yours(need, found) else "needs you"
        lines.append(f"{said} {need.name} -> {ask or found.state.value}")
    return Report(tuple(lines), "\n".join(notes), code)


def set_up_repo(machine: Machine, path: Path) -> Report:
    """`--repo`: add the repo at `path` to the machine's list, by its main checkout, and put
    each of its git hooks. The lines are install's lines for those hooks, and the exit code is
    1 when one is not ok, such as a hook of the repo's own."""
    if refusal := refused(machine, "set a repo up"):
        return refusal
    repo = main_checkout(machine, path)
    if repo is None:
        return Report((), f"install.sh: {path} is no git repository", 1)
    machine.add_repo(repo)
    report = install(machine, write=True, repo=repo)
    if not report.lines:
        why = f"install.sh: {repo} gets no git hook: it is outside HOME, and HOME is not your own"
        return Report((), "\n".join(filter(None, (report.note, why))), 1)
    left = any(not line.startswith(f"{State.OK.value} ") for line in report.lines)
    return Report(report.lines, report.note, 1 if left else report.code)


def uninstall(machine: Machine) -> Report:
    """Drop every Carried and Seeded need, due or not, in reverse order, then forget the list
    of repos and run `machine.sweep()`. The lines are `removed <piece>` and
    `kept <piece> -> <why>`, and there is none for what is absent. The exit code is 1 only when
    uninstall could not remove a piece that belongs to this checkout. A second run prints
    nothing."""
    lines, notes, code = [], [], 0
    kinds = [
        need.kind for need in reversed(needs(machine)) if isinstance(need.kind, (Carried, Seeded))
    ]
    steps = [lambda kind=kind: kind.drop(machine) for kind in kinds]
    for step in [*steps, machine.forget_repos, machine.sweep]:
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
    """Probe every need that the install only probes, and every due Carried need, and write
    nothing.
    The last line is `doctor: ok` or `doctor: not ok, <n> hard`. The exit code is 1 only when
    a hard need is not ok: an optional need never changes it."""
    lines, hard = [], 0
    for need in needs(machine):
        if isinstance(need.kind, Carried) and not need.kind.due(machine):
            continue
        found = need.kind.probe(machine)
        hard += found.state is not State.OK and need.level is Level.HARD
        lines.append(say(need, found))
    lines.append(f"doctor: not ok, {hard} hard" if hard else "doctor: ok")
    return Report(tuple(lines), "", 1 if hard else 0)


def parse(argv: Sequence[str]) -> tuple[Machine, Verb, Path | None]:
    """The machine, the verb and the repo of `<checkout> [verb]` or
    `<checkout> --repo [<path>]`. The repo is the path, or the working directory, for --repo,
    and None for any other verb. For any other arguments, the function prints the usage line
    on stderr and raises SystemExit(2)."""
    verbs = {verb.value: verb for verb in Verb if verb is not Verb.INSTALL}
    repo = argv[1:2] == [Verb.REPO.value] and len(argv) in (2, 3)
    if not repo and (len(argv) not in (1, 2) or (argv[1:] and argv[1] not in verbs)):
        print(USAGE, file=sys.stderr)
        raise SystemExit(2)
    verb = verbs[argv[1]] if argv[1:] else Verb.INSTALL
    path = Path(argv[2] if argv[2:] else ".").absolute() if repo else None
    return Machine.here(Path(argv[0])), verb, path


def act(machine: Machine, verb: Verb, repo: Path | None = None) -> int:
    """Run `verb` on `machine`, print its report, and return its exit code. `repo` is the
    path --repo sets up."""
    if verb is Verb.REPO:
        with machine.alone():
            report = set_up_repo(machine, repo or Path.cwd())
    elif verb is Verb.CHECK:
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


def main(argv: Sequence[str] | None = None) -> int:
    return act(*parse(list(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    sys.exit(main())
