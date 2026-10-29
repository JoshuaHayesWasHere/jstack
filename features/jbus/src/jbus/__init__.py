"""jbus: one scheduled script with no model does what a home did by rote.

This module is the shared model: the config, its projects, and the paths under the state
directory. Every other module takes a `Config` or a `Project` and reads no path by itself.

A home hears jbus by one path, the one list of open items (`jbus.wakes`), each with an owner.
`Config.owner` is the one rule that turns an owner into the project whose home gets the item. An
`infra` above the first `[[project]]` names the project that gets what the machine owns, `infra`
when it is not set. A `home_thread` there is `Config.home_thread`: the thread that gets a
project's wakes when the project's home has none.

A `blocking_url` and `blocking_key` above the first `[[project]]` are `Config.blocking`, the second
target: the address of what blocks (`waiting.blocking`), which jbus-relay sends on to several
places. jbus posts no event to it. It posts only each blocking item when the item opens, each
reminder, and each refresh (`wake.Box.blocking`). `load` refuses half of that pair, and both are
secret.

A `[view]` table is `Config.view`, the addresses `jbus view` is reached at beyond 127.0.0.1: the
`host` it listens on too, the `names` a request may use, and the `origins` of a proxy in front of
it. The view reads no config, so the install writes them into `jbus-view.service`'s drop-in.

A `[[project]]` table whose `kind` is `scratch` is not a repo. It is a scratch home, for throwaway
questions and drafts, bound to T3 Code's "No project" by its `projectId`. `load` is the one place
that turns a table into a project. It sorts a scratch table into `Config.scratch` and never into
`Config.projects`, so no step that takes a `Project` (the queue, `jmerge`, the sweep, CI, the
readers, the snapshot) ever gets one. A name belongs to one home across both lists. `load` refuses a
scratch table whose name is a project's name, or the name a project keeps its state under. It also
refuses a repo table that comes after a scratch home of the same name.

`END_TURN` is the ending of every message to a crew, and of the message that continues or
wakes a reviewer. When a turn ends while its own check or a reviewer's proof still runs,
nothing wakes the thread once that run ends. Then the push, the Result, the pull request or
the Review that the turn was to make never comes. So the message says to wait for that run
in the turn, whenever the run started.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import jsettings
from jgauge import sizes
from jsettings import Refused as Refused
from jsettings.paths import RealDir as RealDir
from jsettings.paths import homes_dir
from jsettings.paths import jbus_config_dir as config_dir
from jsettings.paths import jbus_state_dir as state_dir
from jsettings.store import locked as locked
from jsettings.store import read_dict as read_dict
from jsettings.store import read_json as read_json
from jsettings.store import write_json as write_json

Loud = Literal["user", "quiet"]
LEVELS: tuple[Loud, ...] = ("user", "quiet")
NUMBERED = "numbered"
REPO, SCRATCH = "repo", "scratch"
TIMESTAMPED = "timestamped"
Hook = tuple[str, str]
REDACTED = "[redacted]"
URL_PART = 8
CREDENTIALS = ("access_token", "refresh_token", "id_token")
END_TURN = (
    "End your turn only once no check or proof you started runs in your worktree: wait for "
    "one that runs, in this turn."
)


@dataclass(frozen=True)
class Project:
    """A `Project` is one repo that jbus looks after.

    `migrations` is the directory, from the checkout's root, where the repo keeps its
    migrations. It is empty where the repo has none. `migration_names` says how the repo names a
    migration. With `numbered`, a name looks like `0004_insulin`, and the migration takes its
    number when it lands. With `timestamped`, two names cannot collide. `jmerge` reads both.

    `ci_report` is whether `jbus-ci.timer` writes the project's week of CI (`jbus ci --each`).
    It is off unless the project's table says `ci_report = true`.

    `generated` names each file of the repo that a command writes, as `<file> -> <command>`, for
    `jmerge --remake`. It is empty where the table names none, and `jmerge` then makes `uv.lock`
    by `uv lock`."""

    name: str
    checkout: Path
    state: str
    project_id: str
    migrations: str = ""
    migration_names: str = NUMBERED
    ci_report: bool = False
    generated: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scratch:
    """A `Scratch` is a scratch home: a name, and the T3 Code project its threads run in. It
    has no repo, so it has no checkout and no migrations. It pushes nothing,
    opens no pull request and launches no crew."""

    name: str
    project_id: str

    def addressee(self) -> Project:
        """Return the home as `word` addresses it: a `Project` with no checkout. It is
        for the `passes.Pass` that `word.keep`, `word.deliver` and `word.line` take, and for
        nothing else. Its state and its home are `<name>`, as a repo's are."""
        return Project(self.name, Path(os.devnull), self.name, self.project_id)


MAX_PER_HOME, MAX_PER_PROJECT = 6, 24
INFRA = "infra"
"""The crews a pass lets one home and one project have out, where the config sets no
`max_per_home` or `max_per_project`. `max_running` is the third cap, for the whole machine."""


def _cap(raw: dict[str, Any], key: str, default: int, path: Path) -> int:
    """Return the config's count for a launch cap, or its default when the config has none."""
    written = raw.get(key, default)
    if type(written) is not int or written < 1:
        raise Refused(f"refused: {key} in {path} is {written!r}, and it is 1 or more")
    return written


@dataclass(frozen=True)
class View:
    """The `[view]` table: what `JBUS_VIEW_HOST`, `JBUS_VIEW_NAMES` and `JBUS_VIEW_ORIGINS` say
    to `jbus view` (`jbus.view.doors`), each empty where the table leaves it out."""

    host: str = ""
    names: tuple[str, ...] = ()
    origins: tuple[str, ...] = ()

    def environment(self) -> dict[str, str]:
        """Each variable of the view the table sets, by name."""
        said = {
            "JBUS_VIEW_HOST": self.host,
            "JBUS_VIEW_NAMES": ",".join(self.names),
            "JBUS_VIEW_ORIGINS": ",".join(self.origins),
        }
        return {name: value for name, value in said.items() if value}


def _view(raw: dict[str, Any], path: Path) -> View:
    """The `[view]` table of the config, refused where it has another key, a `host` that is not
    a string, or `names` or `origins` that are not lists of strings."""
    table = raw.get("view", {})
    lists = ("names", "origins")
    if (
        not isinstance(table, dict)
        or set(table) - {"host", *lists}
        or not isinstance(table.get("host", ""), str)
        or not all(
            isinstance(table.get(key, []), list)
            and all(isinstance(one, str) for one in table.get(key, []))
            for key in lists
        )
    ):
        raise Refused(
            f'refused: {path} has a [view] that is not host = "<address>", '
            'names = ["<name>"] and origins = ["https://<host>"]'
        )
    return View(
        table.get("host", ""), tuple(table.get("names", [])), tuple(table.get("origins", []))
    )


@dataclass(frozen=True)
class Config:
    server: str
    runtime_mode: str | None
    dispatch: bool
    max_running: int
    warn_days: int
    wake_alert: int
    room_passes: int
    projects: tuple[Project, ...]
    config_dir: Path
    state_dir: Path
    home_dir: Path
    user: jsettings.Settings
    max_per_home: int = MAX_PER_HOME
    max_per_project: int = MAX_PER_PROJECT
    blocking: Hook = ("", "")
    scratch: tuple[Scratch, ...] = ()
    home_thread: str = ""
    infra: str = INFRA
    view: View = View()

    @property
    def token_path(self) -> Path:
        return self.config_dir / "t3.json"

    @property
    def lock_path(self) -> Path:
        return self.state_dir / "lock"

    @property
    def status_path(self) -> Path:
        return self.state_dir / "status.json"

    @property
    def pass_path(self) -> Path:
        return self.state_dir / "pass.json"

    @property
    def stop_path(self) -> Path:
        return self.state_dir / "stop"

    def project(self, name: str | None) -> Project:
        if name is None and len(self.projects) == 1:
            return self.projects[0]
        for project in self.projects:
            if project.name == name:
                return project
        names = ", ".join(project.name for project in self.projects) or "none"
        raise Refused(f"refused: no project {name or '(name one with --project)'}, have {names}")

    def owner(self, name: str) -> Project | None:
        """Return the project whose home gets what `name` owns: the project of that name, or for
        the machine (no name) and for a name no project has, the infra project. Never every
        project, and None only for a config with no infra project."""
        for wanted in (name, self.infra):
            for project in self.projects:
                if wanted and project.name == wanted:
                    return project
        return None

    def addressee(self, name: str | None) -> Project:
        """Return the home a word is for: a repo project by its name, or a scratch home's
        addressee."""
        for one in self.scratch:
            if one.name == name:
                return one.addressee()
        return self.project(name)

    def secrets(self) -> tuple[str, ...]:
        """Return every string that must not leave this machine in a list, a digest or a line:
        what `secrets` returns for the second target, and the stored token's `CREDENTIALS`. The
        token's other strings, such as `Bearer` and its scope, are not secret."""
        stored = read_json(self.token_path, {})
        token = stored.get("token") if isinstance(stored, dict) else None
        strings = [token.get(name) for name in CREDENTIALS] if isinstance(token, dict) else []
        return secrets(self.blocking, *strings)

    def state(self, project: Project) -> Path:
        """Return where jbus keeps this project's queue, outbox, launches and what it has
        sent."""
        return self.state_dir / project.name

    def home(self, project: Project) -> Path:
        """Return the home's state directory for the project's repo: its briefs, requests and
        gates."""
        return self.home_dir / project.state


def private(path: Path) -> None:
    """Refuse a file that holds a key or a token and that group or others can read."""
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise Refused(f"refused: {path} is mode {mode:03o}, readable by others: chmod 600 it")


def _migrations(entry: dict[str, Any]) -> tuple[str, str]:
    """Return the directory a project keeps its migrations in, relative to its checkout and
    with no `..` in it, and how the project names them. Refuse anything else: for a directory
    outside the checkout, `jmerge` would read the default branch in the wrong place."""
    directory = entry.get("migrations", "")
    names = entry.get("migration_names", NUMBERED)
    parts = str(directory).strip("/").split("/") if directory else []
    if not isinstance(directory, str) or str(directory).startswith("/") or ".." in parts:
        raise Refused(
            f"refused: project {entry['name']} has migrations = {directory!r}: "
            "give a directory inside the checkout, such as db/migrations"
        )
    if names not in (NUMBERED, TIMESTAMPED):
        raise Refused(
            f"refused: project {entry['name']} has migration_names = {names!r}: "
            f"give {NUMBERED} or {TIMESTAMPED}"
        )
    return "/".join(parts), str(names)


BLOCKING = ("blocking_url", "blocking_key")


def _missing(table: dict[str, Any], pair: tuple[str, str]) -> str | None:
    """When the table has one key of its pair and not the other, return the missing key.
    Otherwise return None. A URL with an empty key counts as a missing key, since it would post
    with no key. An empty URL beside a key is no address, and `load` accepts it."""
    url, key = pair
    present = [name for name in pair if name in table]
    if len(present) == 1:
        return next(name for name in pair if name not in table)
    if present and table[url] and not table[key]:
        return key
    return None


def _pair(table: dict[str, Any], pair: tuple[str, str]) -> Hook:
    """Return the table's URL and key, or two empty strings when it has neither. `_missing` has
    already refused half a pair."""
    if not any(name in table for name in pair):
        return "", ""
    return str(table[pair[0]]), str(table[pair[1]])


def load(directory: Path | None = None) -> Config:
    directory = directory or config_dir()
    path = directory / "config.toml"
    if not path.is_file():
        raise Refused(f"refused: no config at {path}")
    private(path)
    token = directory / "t3.json"
    if token.is_file():
        private(token)
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as error:
        raise Refused(f"refused: {path} does not parse: {error}") from error
    if missing := _missing(raw, BLOCKING):
        raise Refused(
            f"refused: {path} has no top-level {missing} beside the other: give it both, or neither"
        )
    blocking = _pair(raw, BLOCKING)
    view = _view(raw, path)
    try:
        projects, scratch = [], []
        for entry in raw.get("project", []):
            kind = entry.get("kind", REPO)
            if kind not in (REPO, SCRATCH):
                raise Refused(
                    f"refused: project {entry['name']} has kind = {kind!r}: "
                    f"give {REPO}, {SCRATCH}, or leave it out for {REPO}"
                )
            name, state = str(entry["name"]), str(entry.get("state") or entry["name"])
            homes = {one.name for one in scratch}
            if kind == SCRATCH:
                homes |= {held for one in projects for held in (one.name, one.state)}
            if homes & {name, state}:
                raise Refused(
                    f"refused: {path} has a scratch home and another project named {name}"
                )
            if kind == SCRATCH:
                scratch.append(Scratch(name, str(entry["projectId"])))
                continue
            migrations, names = _migrations(entry)
            if not isinstance(entry.get("ci_report", False), bool):
                raise Refused(
                    f"refused: project {entry['name']} has a ci_report that is not true or false"
                )
            generated = entry.get("generated", [])
            if not isinstance(generated, list) or not all(
                isinstance(one, str) and " -> " in one for one in generated
            ):
                raise Refused(
                    f"refused: project {entry['name']} has a generated that is not a list of "
                    '"<file> -> <command>"'
                )
            projects.append(
                Project(
                    name=str(entry["name"]),
                    checkout=Path(str(entry["checkout"])).expanduser(),
                    state=str(entry.get("state") or entry["name"]),
                    project_id=str(entry["projectId"]),
                    migrations=migrations,
                    migration_names=names,
                    ci_report=entry.get("ci_report", False),
                    generated=tuple(generated),
                )
            )
        server = str(raw["server"]).rstrip("/")
    except (KeyError, TypeError) as error:
        raise Refused(f"refused: {path} lacks the key {error}") from error
    try:
        user = jsettings.load()
    except jsettings.Invalid as error:
        raise Refused(f"refused: {error}") from error
    try:
        cap = sizes.resolve(sizes.Name.MAX_RUNNING, written=raw.get("max_running"), written_in=path)
    except sizes.Refused as error:
        raise Refused(f"refused: {error}") from error
    return Config(
        server=server,
        runtime_mode=raw.get("runtimeMode") or None,
        dispatch=bool(raw.get("dispatch", True)),
        max_running=cap.value,
        max_per_home=_cap(raw, "max_per_home", MAX_PER_HOME, path),
        max_per_project=_cap(raw, "max_per_project", MAX_PER_PROJECT, path),
        warn_days=int(raw.get("warn_days", 5)),
        wake_alert=int(raw.get("wake_alert", 12)),
        room_passes=int(raw.get("room_passes", 10)),
        projects=tuple(projects),
        config_dir=directory,
        state_dir=state_dir(),
        home_dir=homes_dir(),
        user=user,
        blocking=blocking,
        scratch=tuple(scratch),
        home_thread=str(raw.get("home_thread") or ""),
        infra=str(raw.get("infra") or INFRA),
        view=view,
    )


def secrets(*found: Hook | Any, part: int = URL_PART) -> tuple[str, ...]:
    """Return the secret strings of each pair of an address and its key, and of each other string
    given, the longest first.

    An address's whole URL and its whole key are secret. So are the URL's host, path and query,
    except a part shorter than `part`, since taking `/` out of a text hides nothing. For an error
    that quotes the URL, the caller passes a `part` of 2, so a part of two characters counts too.
    """
    whole: set[str] = set()
    parts: set[str] = set()
    for one in found:
        if isinstance(one, tuple):
            address, key = one
            url = urlsplit(address)
            whole |= {address, key}
            parts |= {url.netloc, url.path, url.query}
        elif isinstance(one, str):
            whole.add(one)
    kept = {one for one in whole if one} | {one for one in parts if len(one) >= part}
    return tuple(sorted(kept, key=len, reverse=True))


def redact(value: Any, secret: tuple[str, ...], mark: str = REDACTED) -> Any:
    """Return the value with each secret in each of its strings replaced, in lists and dicts
    too."""
    if isinstance(value, str):
        for one in secret:
            value = value.replace(one, mark)
        return value
    if isinstance(value, list):
        return [redact(one, secret, mark) for one in value]
    if isinstance(value, dict):
        return {key: redact(one, secret, mark) for key, one in value.items()}
    return value
