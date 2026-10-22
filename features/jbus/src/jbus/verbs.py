"""Each feature's module declares the verbs of the command that belong to that feature.

A module declares what it adds to `jbus` at its top level, as `VERBS = (Verb(...),)`. A `Verb`
holds the name typed after `jbus`, the line `jbus --help` gives it, a function that adds its
arguments to its parser, and the function that runs it. `declared` imports every module of
jbus and gathers the verbs, and `jbus.cli.main` builds its parsers from what `declared`
returns. So a new verb is a `Verb` in a new module, with no line anywhere else. When two
modules declare the same name, importing `jbus.cli` raises a `ValueError` that names both.

A module declares a step of a pass the same way, as `STEPS = (Step(...),)`. A `Step` holds the slot
of `jbus.cli.first_half` or `jbus.cli.second_half` it runs in, its rank in that slot, its name, the
function that runs it, and what the pass must have for it to run. `ranked` gathers the steps and
orders each slot's steps by rank. Each half runs a slot's steps at that slot's place in the half. So
a new step is a `Step` in its feature's module, with no line in `jbus.cli`. `jbus steps` prints the
order. When two modules declare the same rank in one slot, importing `jbus.cli` raises a
`ValueError` that names both.

A chore is work for the machine as a whole: it runs once a pass and for no project. A module
declares it as `CHORES = (Chore(...),)`, with its rank, its name, and the function that runs
it. That function takes the config, the T3 Code client or None, the pass's time and its
`say`. `chores` gathers the chores by rank, and `jbus.cli.poll` runs each one after the
launches, inside `guarded` under the chore's name. The chores are the sign-in reminder and
the sending of the scratch homes' words. A scratch home is no project of a pass. When two
modules declare the same rank, `chores` raises a `ValueError`.

`project` and `here` are the two ways a verb finds the project it is for.

This module imports none of jbus's features, so that each of them can import it.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jbus

FIRST = (
    "poll",
    "alarm",
    "status",
    "events",
    "digest",
    "view",
    "word",
    "queue",
    "plan",
    "gate",
    "answer",
    "done",
    "project",
    "t3",
)


@dataclass(frozen=True)
class Verb:
    """One verb. `run` takes what was parsed and the config, and returns the exit code.

    `abbrev` lets the user type an option short, as `--he` for `--help`. It is on by default,
    as argparse has it, and off for the verbs that turned it off before verbs were declared.
    `config` is off for a verb that reads no config, and the command then runs it with None
    in the config's place.
    """

    name: str
    help: str
    arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace, jbus.Config], int]
    abbrev: bool = True
    config: bool = True


NEEDS = ("sight", "client", "world", "rows")
SLOTS = {
    "before-watch": ("first in the pass, before merge.merge", ("client",)),
    "tellers": ("after watch.look", ("sight", "client", "world")),
    "after-expedite": ("after expedite.tell, before dispatch.turns", ("sight", "client", "world")),
    "derive": ("after the launches, first in the second half", NEEDS),
    "after-derive": ("after derive", NEEDS),
    "close": ("after after-derive, before alert.flush, the last of a pass", NEEDS),
}


@dataclass(frozen=True)
class Step:
    """One step of a pass. `run` takes the pass's `jbus.cli.Half`.

    `rank` orders the steps of one slot, in steps of 10. `needs` is what the pass must have
    for the step to run, out of `NEEDS`:

    - `sight`: a `removed.json` that parses, which a blind pass does not have.
    - `client`: a sign-in to T3 Code.
    - `world`: the answers of T3 Code and GitHub.
    - `rows`: the judged rows of a queue that parses (`Half.states`), which only the second
      half has.

    The pass skips a step whose needs it does not have.
    """

    slot: str
    rank: int
    name: str
    run: Callable[[Any], None]
    needs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Chore:
    """One chore of a pass: the machine's own work, run once a pass after the launches."""

    rank: int
    name: str
    run: Callable[[jbus.Config, Any, Any, Callable[[str], None]], None]


def chores(paths: Iterable[str]) -> tuple[Chore, ...]:
    """Return every chore the modules under `paths` declare, by rank."""
    found: dict[int, tuple[Chore, str]] = {}
    for module in pkgutil.iter_modules(paths, f"{jbus.__name__}."):
        if module.name.endswith(".__main__"):
            continue
        for chore in getattr(importlib.import_module(module.name), "CHORES", ()):
            if chore.rank in found:
                raise ValueError(
                    f"chore {chore.rank} is declared in {found[chore.rank][1]} and in {module.name}"
                )
            found[chore.rank] = chore, module.name
    return tuple(found[rank][0] for rank in sorted(found))


def nothing(parser: argparse.ArgumentParser) -> None:
    """Add no arguments to the parser of a verb that takes none."""


def declared(paths: Iterable[str]) -> dict[str, Verb]:
    """Return every verb the modules under `paths` declare, by its name, in the order
    `jbus --help` lists them. The verbs of `FIRST` come first, in their order there, which is
    the order they had when one function listed them all. Every other verb follows by its
    name. No new verb goes into `FIRST`.

    A folder declares its verbs in its `__init__`. `__main__` runs the command, and
    `declared` does not import it.
    """
    found: dict[str, Verb] = {}
    by: dict[str, str] = {}
    for module in pkgutil.iter_modules(paths, f"{jbus.__name__}."):
        if module.name.endswith(".__main__"):
            continue
        for verb in getattr(importlib.import_module(module.name), "VERBS", ()):
            if verb.name in by:
                raise ValueError(f"{verb.name} is declared in {by[verb.name]} and in {module.name}")
            found[verb.name], by[verb.name] = verb, module.name
    return {name: found[name] for name in (*(one for one in FIRST if one in found), *sorted(found))}


def ranked(paths: Iterable[str]) -> dict[str, tuple[Step, ...]]:
    """Return every step the modules under `paths` declare, by its slot in the order of
    `SLOTS`, and within a slot by rank.

    `ranked` raises a `ValueError` that names the module for a slot that is not one of
    `SLOTS`, for a rank another module took in the same slot, and for a need the step's slot
    cannot supply. What a slot supplies is the second item of its pair in `SLOTS`. The first
    slot runs before the pass knows whether it is blind or what T3 Code and GitHub said, so it
    supplies `client` alone."""
    found: dict[tuple[str, int], tuple[Step, str]] = {}
    for module in pkgutil.iter_modules(paths, f"{jbus.__name__}."):
        if module.name.endswith(".__main__"):
            continue
        for step in getattr(importlib.import_module(module.name), "STEPS", ()):
            if step.slot not in SLOTS:
                raise ValueError(f"{step.name} in {module.name}: there is no slot {step.slot}")
            odd = [need for need in step.needs if need not in SLOTS[step.slot][1]]
            if odd:
                raise ValueError(
                    f"{step.name} in {module.name}: {step.slot} cannot supply {', '.join(odd)}"
                )
            at = (step.slot, step.rank)
            if at in found:
                raise ValueError(
                    f"{step.slot} {step.rank} is declared in {found[at][1]} and in {module.name}"
                )
            found[at] = step, module.name
    return {slot: tuple(found[at][0] for at in sorted(found) if at[0] == slot) for slot in SLOTS}


def project(config: jbus.Config, name: str | None) -> jbus.Project:
    """Return the named project, the only project, or the one whose repo this directory is
    in."""
    if name is None and len(config.projects) > 1:
        asked = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
        )
        repo = Path(asked.stdout.strip()).parent.name if asked.returncode == 0 else ""
        for one in config.projects:
            if one.state == repo:
                return one
    return config.project(name)


def here(config: jbus.Config, name: str | None) -> jbus.Project:
    """Return the project a thread acts for: the named one, or the one whose repo this is.

    Every repo uses the crew and scout skills, so `here` refuses a gate from a repo the config
    does not name, rather than send it as another project's gate.
    """
    if name is not None:
        return config.project(name)
    asked = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    repo = Path(asked.stdout.strip()).parent.name if asked.returncode == 0 else ""
    for one in config.projects:
        if one.state == repo:
            return one
    raise jbus.Refused(f"refused: no project for this repo ({repo or 'not a repo'})")


def parser(found: dict[str, Verb], description: str | None) -> argparse.ArgumentParser:
    """Build the parser of `jbus`, with a parser for each verb `declared` found."""
    made = argparse.ArgumentParser(prog="jbus", description=description, allow_abbrev=False)
    made.add_argument("--project", help="the project's name in the config, when it has several")
    commands = made.add_subparsers(dest="command", required=True)
    for verb in found.values():
        verb.arguments(commands.add_parser(verb.name, help=verb.help, allow_abbrev=verb.abbrev))
    made.usage = usage(made)
    return made


def words_left(args: argparse.Namespace, extra: list[str]) -> list[str]:
    """Return the user's words that Python 3.12.3's argparse left over, and what is left
    after them.

    A verb's `words` follow its number and its options. The argparse of 3.12.3 fills `words`
    with nothing when it reads the number, and hands the words back unparsed. Later 3.12
    releases and 3.13 read them as words. So when `words` came back empty, every plain string
    left over is a word, and so is everything after `--`."""
    if getattr(args, "words", None) != [] or not extra:
        return extra
    words: list[str] = []
    left: list[str] = []
    after = False
    for given in extra:
        if after or not given.startswith("-"):
            words.append(given)
        elif given == "--":
            after = True
        else:
            left.append(given)
    args.words = words
    return left


def usage(parser: argparse.ArgumentParser) -> str:
    """Return the parser's own usage as Python 3.13 and later print it. Python 3.12 puts the
    ` ...` after the verbs on a line of its own."""
    usage = parser.format_usage().removeprefix("usage: ").rstrip("\n")
    return re.sub(r"\n *\.\.\.$", " ...", usage)


def _steps(args: argparse.Namespace, config: jbus.Config | None) -> int:
    """`jbus steps`: print each step of a pass, in the order it runs, with its needs."""
    for slot, steps in ranked(jbus.__path__).items():
        for step in steps:
            needs = f" ({', '.join(step.needs)})" if step.needs else ""
            print(f"{slot} {step.rank} {step.name}{needs}")
    return 0


VERBS = (
    Verb("steps", "print the steps of a pass in the order they run", nothing, _steps, config=False),
)
