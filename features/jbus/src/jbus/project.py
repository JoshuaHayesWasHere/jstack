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

`jbus project close <name>` puts a project away until `jbus project open <name>` brings it back. It
writes `closed = "<day>"` into that project's table alone, as `bases --add` writes, and `load` then
keeps the project out of `Config.projects`: no pass, `word --all`, needs line or chore reaches it.
`close` also puts it away in T3 Code: it archives each thread of the project that is not archived
yet, the home's among them, switches off each of its scheduled tasks that is on, and archives the T3
Code project whose workspace root is the project's checkout, so the project leaves T3 Code's
sidebar. A T3 Code project archived already stays as it is. It refuses while a row of the project is
out or one of its crews, reviewers or scouts is in a turn, and names each. It holds the pass's lock,
so no pass launches between its check and its write. Queued, held and finished rows, questions,
gates, plans, worktrees, branches and `home-id` stay as they are.

`closed.json`, in the project's state, is what `close` changed in T3 Code, by id: the threads, the
home threads among them, the tasks, and the T3 Code `project` where `close` archived it. `close`
writes it before it changes anything, adds the day just before the config write, and writes the
config last. `open` switches those tasks back on, unarchives the T3 Code project (only the one
`close` archived), then the home threads only (a crew's thread stays put away), takes the line out
of the config, and deletes `closed.json` last. So a run cut off at any step is finished by the next
run, and a run with nothing left to do says so and changes nothing. The view reads the day in
`closed.json`, since it reads no config.

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
from jbriefs.home import ids, scopes
from jbus import live, queue, roles, t3, verbs

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
CLOSED = "closed"
RECORD = "closed.json"
OUT = ("launched", "running", "waiting", "pr")
"""The rows `close` waits on: each has a crew at work, or a pull request jbus still merges."""
AT_WORK = ("crew", "reviewer", "scout")
_HEADER = re.compile(r"\[")
_PROJECT = re.compile(r"\[\[\s*project\s*\]\]\s*(#.*)?$")


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
    have, scratch = (*config.projects, *config.closed), config.scratch
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
    found = next((one for one in (*config.projects, *config.closed) if one.name == name), None)
    if found is None:
        raise jbus.Refused(NO_PROJECT)
    return found


def _with_key(text: str, index: int, key: str, value: object) -> str:
    """Return `text` with the `key` line of its `index`-th `[[project]]` table put in place of
    the one it has, or after the table's last line that is not blank or a comment. A `value` of
    None takes the line out."""
    lines = text.splitlines(keepends=True)
    heads = [at for at, line in enumerate(lines) if _HEADER.match(line)]
    tables = [at for at in heads if _PROJECT.match(lines[at].rstrip("\n"))]
    start = tables[index]
    end = next((at for at in heads if at > start), len(lines))
    line = [] if value is None else [f"{key} = {json.dumps(value)}\n"]
    for at in range(start + 1, end):
        if re.match(rf"{re.escape(key)}\s*=", lines[at]):
            return "".join([*lines[:at], *line, *lines[at + 1 :]])
    last = max(
        (at for at in range(start, end) if lines[at].strip() and not lines[at].startswith("#")),
    )
    if not lines[last].endswith("\n"):
        lines[last] += "\n"
    return "".join([*lines[: last + 1], *line, *lines[last + 1 :]])


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
    backup = _set(config_path, name, BASES, [*one.merge_bases, branch])
    return BASE_ADDED.format(backup=backup)


def bases(config: jbus.Config, name: str) -> tuple[str, ...]:
    """The merge bases the project `name` names, besides the default branch."""
    return _project(config, name).merge_bases


def _rewritten(was: str, name: str, key: str, value: object) -> str:
    """Return the config text `was` with `value` as the `key` of the project `name`'s table, or
    the key taken out where `value` is None, and nothing else changed. Refuse a text in which
    that one change cannot be written."""
    before = tomllib.loads(was)
    index = next(at for at, table in enumerate(before["project"]) if table["name"] == name)
    want = copy.deepcopy(before)
    if value is None:
        want["project"][index].pop(key, None)
    else:
        want["project"][index][key] = value
    try:
        now = _with_key(was, index, key, value)
        written = tomllib.loads(now)
    except (IndexError, ValueError, tomllib.TOMLDecodeError):
        now, written = "", None
    if written != want:
        raise jbus.Refused(
            "refused: the project's table could not be written with that one key changed"
        )
    return now


def _set(config_path: Path, name: str, key: str, value: object) -> Path:
    """Write `value` as the `key` of the project `name`'s table (`_rewritten`). Save the file as
    it was beside it first, and return where."""
    was = config_path.read_text()
    now = _rewritten(was, name, key, value)
    backup = config_path.with_name(f"{config_path.name}.{datetime.now():%Y%m%d-%H%M%S-%f}.bak")
    _private(backup, was)
    _private(config_path, now)
    return backup


def missing(config: jbus.Config) -> list[str]:
    """Return the folders under the homes' state root that have a `home-id` and no project,
    by name."""
    homes = {config.home(one).resolve() for one in (*config.projects, *config.closed)}
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


def _client(config: jbus.Config, client: t3.Client | None) -> t3.Client:
    return client if client is not None else t3.Client(config.server, config.token_path)


def _homes(config: jbus.Config, one: jbus.Project) -> set[str]:
    """The thread in each `home-id` of the project's home, the root's and every scope's."""
    home = config.home(one)
    return {ids(home)[0], *(now for _, now, _ in scopes(home))} - {""}


def _t3_project(client: t3.Client, one: jbus.Project) -> dict | None:
    """The T3 Code project whose workspace root is the project's checkout, the one with the
    project's id where several are, or None where T3 Code has none."""
    found, cursor = [], 0
    for _ in range(20):
        said = client.call("t3_project_list", {"limit": 100, "cursor": cursor})
        found += said.get("projects", [])
        cursor = said.get("nextCursor")
        if not isinstance(cursor, int) or not cursor:
            break
    home = one.checkout.resolve()
    mine = [
        each
        for each in found
        if each.get("workspaceRoot")
        and not each.get("deletedAt")
        and Path(each["workspaceRoot"]).resolve() == home
    ]
    return next((each for each in mine if each.get("id") == one.project_id), next(iter(mine), None))


def _at_work(state: Path, listed: list[dict]) -> list[str]:
    """Each row of the project that is out, and each crew, reviewer or scout thread in a turn."""
    rows = queue.load(state)
    found = [f"row {row['slug']} is {row['status']}" for row in rows if row.get("status") in OUT]
    for thread in listed:
        role, _ = roles.role_of(str(thread.get("title") or ""))
        if role in AT_WORK and thread.get("status") in live.TURNING:
            found.append(f"{role} thread {thread['threadId']} is {thread['status']}")
    return found


def close(
    config_path: Path, name: str, client: t3.Client | None = None, now: datetime | None = None
) -> str:
    """Close the project `name`: put its threads and scheduled tasks away in T3 Code, record
    which in `closed.json`, and write the day into its table. Return the answer, one line."""
    config = jbus.load(config_path.parent)
    with jbus.locked(config.state_dir, config.lock_path.name):
        config = jbus.load(config_path.parent)
        one = _project(config, name)
        if one.closed:
            return f"already closed: {name} has been closed since {one.closed}, nothing changed"
        day = config.user.local(now or datetime.now().astimezone()).date().isoformat()
        _rewritten(config_path.read_text(), name, CLOSED, day)
        state, client = config.state(one), _client(config, client)
        listed = t3.listed(client, one.project_id)
        if busy := _at_work(state, listed):
            raise jbus.Refused(f"refused: {name} still has work out: {'; '.join(busy)}")
        threads = {thread["threadId"] for thread in listed}
        tasks = {
            task["scheduledTaskId"]
            for task in client.call("list_scheduled_tasks", {"projectId": one.project_id}).get(
                "tasks", []
            )
            if task.get("enabled") and task.get("projectId") == one.project_id
        }
        path = state / RECORD
        kept = jbus.read_json(path, {})
        found = _t3_project(client, one)
        shown = found if found and not found.get("archivedAt") else None
        mine = kept.get("project") or (shown or {}).get("id")
        record = {
            "threads": sorted({*kept.get("threads", []), *threads}),
            "homes": sorted({*kept.get("homes", []), *(_homes(config, one) & threads)}),
            "tasks": sorted({*kept.get("tasks", []), *tasks}),
            **({"project": mine} if mine else {}),
        }
        jbus.write_json(path, record, mode=0o600)
        for task in sorted(tasks):
            client.call("schedule_task", {"scheduledTaskId": task, "enabled": False})
        for thread in sorted(threads):
            client.call("t3_thread_organize", {"action": "archive", "threadId": thread})
        if mine and shown and shown["id"] == mine:
            client.call("t3_project_update", {"projectId": mine, "archived": True})
        jbus.write_json(path, {**record, CLOSED: day}, mode=0o600)
        backup = _set(config_path, name, CLOSED, day)
    sidebar = (
        "its T3 Code project archived"
        if mine
        else "its T3 Code project was archived already"
        if found
        else "T3 Code has no project at its checkout"
    )
    return (
        f"closed: {name}, {len(record['threads'])} threads archived and "
        f"{len(record['tasks'])} scheduled tasks off, {sidebar}, the file as it was is "
        f"{backup}: jbus project open {name} brings it back"
    )


def reopen(config_path: Path, name: str, client: t3.Client | None = None) -> str:
    """Open the closed project `name` again: switch back on the tasks `close` switched off,
    unarchive the T3 Code project and the home threads it archived, take the day out of its table,
    and delete `closed.json`. Return the answer, one line."""
    config = jbus.load(config_path.parent)
    with jbus.locked(config.state_dir, config.lock_path.name):
        config = jbus.load(config_path.parent)
        one = _project(config, name)
        path = config.state(one) / RECORD
        if not one.closed and not path.exists():
            return f"already open: {name} is open, nothing changed"
        if one.closed:
            _rewritten(config_path.read_text(), name, CLOSED, None)
        record, client = jbus.read_json(path, {}), _client(config, client)
        for task in record.get("tasks", []):
            _unless_gone(client, "schedule_task", {"scheduledTaskId": task, "enabled": True})
        if record.get("project"):
            asked = {"projectId": record["project"], "archived": False}
            _unless_gone(client, "t3_project_update", asked)
        for home in record.get("homes", []):
            read = _unless_gone(client, "t3_thread_read", {"threadId": home, "limit": 1})
            if read and (read.get("thread") or {}).get("archived"):
                client.call("t3_thread_organize", {"action": "unarchive", "threadId": home})
        if one.closed:
            _set(config_path, name, CLOSED, None)
        path.unlink(missing_ok=True)
    return (
        f"opened: {name}, {len(record.get('tasks', []))} scheduled tasks on and "
        f"{'its T3 Code project and ' if record.get('project') else ''}its home threads back: "
        "the next pass works it, restart no unit"
    )


def _unless_gone(client: t3.Client, tool: str, arguments: dict) -> dict | None:
    """Call the tool, and return None where T3 Code no longer has what it names."""
    try:
        return client.call(tool, arguments)
    except t3.T3Refused as error:
        if t3.GONE.search(str(error)):
            return None
        raise


def _add(args: argparse.Namespace, _: jbus.Config) -> int:
    path = jbus.config_dir() / "config.toml"
    if args.verb == "close":
        print(close(path, args.name))
    elif args.verb == "open":
        print(reopen(path, args.name))
    elif args.verb == "bases" and args.add is not None:
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
    for verb, said in (
        ("close", "put the project away: no pass, word or task reaches it until open"),
        ("open", "bring a closed project back as it was"),
    ):
        listed_verbs.add_parser(verb, help=said, allow_abbrev=False).add_argument(
            "name", help="the project's name in the config"
        )


VERBS = (verbs.Verb("project", "the projects of the config", _listed, _add, config=False),)
