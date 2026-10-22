"""`jbus project add`: add one more `[[project]]` table at the end of jbus's config.

The config holds a webhook's key, so neither a person nor a skill writes it. `add` reads the
file as text and writes it back with one table after its last byte. Every other table keeps
the same bytes. First `add` saves a copy of the file as it was, beside it, as
`config.toml.<time>.bak`, and both stay mode 600. The table has `name`, `checkout` and
`projectId`, and no webhook. The new project uses the `webhook_url` and `webhook_key` at the
top of the config when the config has them. With none there, a pass POSTs nothing for it.

The file must load as a pass loads it (`jbus.load`). `add` refuses a config that a pass
refuses, before it writes anything, with the line `jbus.load` gives.

`add` answers with one line, or raises `jbus.Refused` with one line. It refuses a second run
with the same name, checkout and id with the line `HAS`, which a caller may read as already
done. It also refuses a name or a checkout that the config already has with any other field
different, and its line names what the two share. No line holds the value of any key, the
values the caller gave included, so a line of this command is safe in any log.

`add --scratch` writes a scratch home's table in place of a repo's: `name`, `kind =
"scratch"` and `projectId`, and no checkout, since it has no repo (`jbus.Scratch`). `add`
checks its name as it checks a repo's, against every project and every scratch home of the
config.

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
    print(add(jbus.config_dir() / "config.toml", args.name, args.checkout, args.project_id))
    return 0


def _listed(listed: argparse.ArgumentParser) -> None:
    listed_verbs = listed.add_subparsers(dest="verb", required=True)
    added = listed_verbs.add_parser(
        "add",
        help="add a project's table to the config, with no webhook",
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


VERBS = (verbs.Verb("project", "the projects of the config", _listed, _add, config=False),)
