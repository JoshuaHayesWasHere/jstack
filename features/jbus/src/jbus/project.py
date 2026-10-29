"""`jbus project add`: add one more `[[project]]` table at the end of jbus's config.

The config may hold a key, so neither a person nor a skill writes the config. `add` reads the
file as text and writes it back with one table after its last byte. Every other table keeps
the same bytes. First `add` saves a copy of the file as it was, beside it, as
`config.toml.<time>.bak`, and both stay mode 600. The table has `name`, `checkout` and
`projectId`. A pass wakes the new project's home thread for what the user must act on.

The file must load as a pass loads it (`jbus.load`). `add` refuses a config that a pass
refuses, before it writes anything, with the line `jbus.load` gives.

`add` answers with one line, or raises `jbus.Refused` with one line. When a second run has the
same name, checkout and id, `add` refuses it with the line `HAS`, which a caller may read as
already done. It also refuses a name or a checkout that the config already has when any
other field differs. Its line names what the two share. No line holds the value of any key, not
even a value the caller gave, so a line of this command is safe in any log.

`add --scratch` writes a scratch home's table in place of a repo's: `name`, `kind =
"scratch"` and `projectId`, and no checkout, since it has no repo (`jbus.Scratch`). `add`
checks its name as it checks a repo's, against every project and every scratch home of the
config.

`jbus project bases <name> --add <branch>` names one more branch that `jmerge` merges the
project's pull requests into, beside the default branch: it writes the project's `merge_bases`
(`jbus.Project`) in that project's table alone, with the same copy and mode as `add`, and refuses a
write that would change any other key or table. `jbus project bases <name>` prints each branch the
table names, one a line, and nothing where it names none: the one way to read the key without
opening the file.

Each pass is a new `jbus poll` that loads the config, so the pass after `add` covers the new
project, and nobody restarts a unit.

`missing` finds the homes that `add` did not record: each folder of the homes' state root
that holds a home's `home-id` and is the home of no project of the config. A home adds its
repo at its start. `missing` names a home that started before that rule, or one that `add`
refused to add. The pass prints the list when it changes, and `jbus status` and the view's
machine row show it. A party's folder, `_<name>` (an expert's), is not the home of a repo,
and `missing` never names it. A folder that is a link to a project's home counts as that home.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path

import jbus
from jbus import verbs

HAS = "refused: the config already has this project"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
USAGE = "%(prog)s [-h] (--checkout CHECKOUT | --scratch) --project-id PROJECT_ID name"
"""Written out, since argparse wraps a usage this long differently from one Python to the next."""
ADDED = (
    "added: one [[project]] table, the file as it was is {backup}: "
    "the next pass works it, restart no unit"
)
BASE_ADDED = (
    "added: one merge base to the project's table, the file as it was is {backup}: "
    "the next pass works it, restart no unit"
)
BASE_HAS = "refused: the project already names that merge base"
NO_PROJECT = "refused: the config has no project of that name"
BASES = "merge_bases"
_HEADER = re.compile(r"\[")
_PROJECT = re.compile(r"\[\[\s*project\s*\]\]\s*(#.*)?$")
_BASES = re.compile(rf"{BASES}\s*=")


def _same(one: Path, other: Path) -> bool:
    return one.resolve() == other


def _private(path: Path, text: str) -> None:
    """Write `text` to `path`, mode 600, in one step, so a pass reads either the old file or
    the new one."""
    handle, made = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w") as file:
            file.write(text)
        os.chmod(made, 0o600)
        os.replace(made, path)
    except BaseException:
        Path(made).unlink(missing_ok=True)
        raise


def table(name: str, checkout: Path | None, project_id: str) -> str:
    """Return the lines of one project's table, as TOML, or of a scratch home's where
    `checkout` is None."""
    where = ("kind", jbus.SCRATCH) if checkout is None else ("checkout", str(checkout))
    pairs = (("name", name), where, ("projectId", project_id))
    return "[[project]]\n" + "".join(f"{key} = {json.dumps(value)}\n" for key, value in pairs)


def add(config_path: Path, name: str, checkout: str | None, project_id: str) -> str:
    """Add the project's table to the config at `config_path`, or a scratch home's where
    `checkout` is None. Return the answer, which is one line."""
    if config_path.name != "config.toml":
        raise jbus.Refused(f"refused: {config_path} is not a config.toml")
    config = jbus.load(config_path.parent)
    have, scratch = config.projects, config.scratch
    was = config_path.read_text()
    if not NAME.fullmatch(name):
        raise jbus.Refused(
            "refused: a project's name is letters, digits, dots, dashes and underscores"
        )
    if not project_id.strip():
        raise jbus.Refused("refused: --project-id is empty")
    where = None if checkout is None else Path(checkout).expanduser().resolve()
    if where is not None and not where.is_dir():
        raise jbus.Refused("refused: --checkout is not a directory")
    if where is None and jbus.Scratch(name, project_id.strip()) in scratch:
        raise jbus.Refused(HAS)
    if where is not None and any(
        (one.name, one.project_id) == (name, project_id.strip()) and _same(one.checkout, where)
        for one in have
    ):
        raise jbus.Refused(HAS)
    if any(name in (one.name, one.state) for one in have) or any(
        one.name == name for one in scratch
    ):
        raise jbus.Refused("refused: the config already has a project of that name")
    if where is not None and any(_same(one.checkout, where) for one in have):
        raise jbus.Refused("refused: the config already has a project with that checkout")
    gap = "" if not was or was.endswith("\n\n") else "\n" if was.endswith("\n") else "\n\n"
    now = was + gap + table(name, where, project_id.strip())
    tomllib.loads(now)
    backup = config_path.with_name(f"{config_path.name}.{datetime.now():%Y%m%d-%H%M%S-%f}.bak")
    _private(backup, was)
    _private(config_path, now)
    return ADDED.format(backup=backup)


def _project(config: jbus.Config, name: str) -> jbus.Project:
    found = next((one for one in config.projects if one.name == name), None)
    if found is None:
        raise jbus.Refused(NO_PROJECT)
    return found


def _with_bases(text: str, index: int, bases: tuple[str, ...]) -> str:
    """Return `text` with the `merge_bases` line of its `index`-th `[[project]]` table, put in
    place of the one it has, or after the table's last line that is not blank or a comment."""
    lines = text.splitlines(keepends=True)
    heads = [at for at, line in enumerate(lines) if _HEADER.match(line)]
    tables = [at for at in heads if _PROJECT.match(lines[at].rstrip("\n"))]
    start = tables[index]
    end = next((at for at in heads if at > start), len(lines))
    line = f"{BASES} = {json.dumps(list(bases))}\n"
    for at in range(start + 1, end):
        if _BASES.match(lines[at]):
            return "".join([*lines[:at], line, *lines[at + 1 :]])
    last = max(
        (at for at in range(start, end) if lines[at].strip() and not lines[at].startswith("#")),
    )
    if not lines[last].endswith("\n"):
        lines[last] += "\n"
    return "".join([*lines[: last + 1], line, *lines[last + 1 :]])


def add_base(config_path: Path, name: str, branch: str) -> str:
    """Name `branch` as one more merge base of the project `name`, in that project's table of
    the config at `config_path`. Return the answer, which is one line."""
    if config_path.name != "config.toml":
        raise jbus.Refused(f"refused: {config_path} is not a config.toml")
    one = _project(jbus.load(config_path.parent), name)
    if not jbus.branch(branch):
        raise jbus.Refused("refused: a merge base is a branch name, with no space and no ..")
    if branch in one.merge_bases:
        raise jbus.Refused(BASE_HAS)
    was = config_path.read_text()
    before = tomllib.loads(was)
    index = next(at for at, table in enumerate(before["project"]) if table["name"] == name)
    bases = (*one.merge_bases, branch)
    want = copy.deepcopy(before)
    want["project"][index][BASES] = list(bases)
    try:
        now = _with_bases(was, index, bases)
        written = tomllib.loads(now)
    except (IndexError, ValueError, tomllib.TOMLDecodeError):
        written = None
    if written != want:
        raise jbus.Refused(
            "refused: the project's table could not be written with that one key changed"
        )
    backup = config_path.with_name(f"{config_path.name}.{datetime.now():%Y%m%d-%H%M%S-%f}.bak")
    _private(backup, was)
    _private(config_path, now)
    return BASE_ADDED.format(backup=backup)


def bases(config: jbus.Config, name: str) -> tuple[str, ...]:
    """The merge bases the project `name` names, besides the default branch."""
    return _project(config, name).merge_bases


def missing(config: jbus.Config) -> list[str]:
    """Return the folders under the homes' state root that have a `home-id` and no project,
    by name."""
    homes = {config.home(one).resolve() for one in config.projects}
    homes |= {config.home(one.addressee()).resolve() for one in config.scratch}
    try:
        found = list(config.home_dir.iterdir())
    except OSError:
        return []
    named = []
    for folder in found:
        mark = folder / "home-id"
        if folder.name.startswith("_") or not folder.is_dir() or folder.resolve() in homes:
            continue
        try:
            if mark.is_file() and mark.read_text().strip():
                named.append(folder.name)
        except OSError:
            continue
    return sorted(named, key=str.lower)


def _add(args: argparse.Namespace, _: jbus.Config) -> int:
    path = jbus.config_dir() / "config.toml"
    if args.verb == "bases" and args.add is not None:
        print(add_base(path, args.name, args.add))
    elif args.verb == "bases":
        for one in bases(jbus.load(path.parent), args.name):
            print(one)
    else:
        print(add(path, args.name, args.checkout, args.project_id))
    return 0


def _listed(listed: argparse.ArgumentParser) -> None:
    listed_verbs = listed.add_subparsers(dest="verb", required=True)
    added = listed_verbs.add_parser(
        "add",
        help="add a project's table to the config",
        allow_abbrev=False,
        usage=USAGE,
    )
    added.add_argument("name", help="the home's directory name under the homes' state")
    where = added.add_mutually_exclusive_group(required=True)
    where.add_argument("--checkout", help="the path of the repo's main checkout")
    where.add_argument(
        "--scratch",
        action="store_true",
        help="a scratch home with no repo, in place of --checkout",
    )
    added.add_argument("--project-id", required=True, help="the T3 Code project's id")
    based = listed_verbs.add_parser(
        "bases",
        help="print each branch besides the default one that jmerge merges the project into, "
        "or name one more with --add",
        allow_abbrev=False,
    )
    based.add_argument("name", help="the project's name in the config")
    based.add_argument("--add", metavar="BRANCH", help="name one more branch, beside the others")


VERBS = (verbs.Verb("project", "the projects of the config", _listed, _add, config=False),)
