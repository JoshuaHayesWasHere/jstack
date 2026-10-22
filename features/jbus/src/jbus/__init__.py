"""jbus: one scheduled script with no model does what a home did by rote.

This module is the shared model: the config, its projects, and the paths under the state
directory. Every other module takes a `Config` or a `Project` and reads no path by itself.

A level of loudness and one kind of event had one person's name until the name became a
setting (`jsettings.Settings`). `NAMED_AFTER` holds those two by the names they have now.
In those old names jbus wrote the person's name, in lower case, where it now writes `user`.
`old_names` is the map from every old name to the name it has now. `current_level` reads a
level through it, and `current_kind` reads a kind of event through it. A third level, `chef`,
started a POST for an event that asked nothing of the user. An event of that level is `quiet`
now, and jbus reads it as `quiet`.

`IGNORED` is the keys of a project's table that nothing reads any more. `load` still loads a
config that has one, and `Config.ignored` names each such key, so that each pass can name
it until the user removes it. A webhook URL and key in any top-level table, whether jbus reads
that table or nothing reads it any more, are secret while they are in the file.
`Config.tabled` holds them, and only `secrets` reads them there.

A `webhook_url` and `webhook_key` above the first `[[project]]` are `Config.webhook`, the top-level
webhook. It receives the events of every project: jbus posts it each event, for the user of each
project. Every project that has neither key of its own also uses it as its pair. A project with both
keys of its own uses them as they are. jbus posts the project's events to that pair as well as to
the top-level one (`wake.Box`), and only once where the two pairs are the same. `load` refuses a
project with only one of the two keys, because half a pair beside the top-level one would post with
the wrong key. The top-level pair is secret whether a project uses it or not.

A `blocking_url` and `blocking_key` above the first `[[project]]` are `Config.blocking`, the second
target: the webhook of what blocks (`waiting.blocking`), which jbus-relay sends on to several
places. jbus posts no event to it. It posts only each blocking item when the item opens, each
reminder, and each refresh (`wake.Box.blocking`). `load` refuses half of that pair as it refuses
half of the other, and both are secret.

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

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import jsettings
from jgauge import sizes

Loud = Literal["user", "quiet"]
LEVELS: tuple[Loud, ...] = ("user", "quiet")
NAMED_AFTER = ("user", "waiting-on-user")
WAS = {"chef": "quiet"}
IGNORED = ("loud",)
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


class Refused(Exception):
    """`Refused` means jbus will not start, or will not run a verb. The message is the one line
    to print."""


@dataclass(frozen=True)
class Project:
    """A `Project` is one repo that jbus looks after, with the webhook where jbus posts what the
    user must act on: its own pair, or the config's top-level one when it has none.

    `migrations` is the directory, from the checkout's root, where the repo keeps its
    migrations. It is empty where the repo has none. `migration_names` says how the repo names a
    migration. With `numbered`, a name looks like `0004_insulin`, and the migration takes its
    number when it lands. With `timestamped`, two names cannot collide. `jmerge` reads both."""

    name: str
    checkout: Path
    state: str
    project_id: str
    webhook_url: str
    webhook_key: str
    migrations: str = ""
    migration_names: str = NUMBERED


@dataclass(frozen=True)
class Scratch:
    """A `Scratch` is a scratch home: a name, and the T3 Code project its threads run in. It
    has no repo, so it has no checkout, no webhook and no migrations. It pushes nothing,
    opens no pull request and launches no crew."""

    name: str
    project_id: str

    def addressee(self) -> Project:
        """Return the home as `word` addresses it: a `Project` with no checkout. It is
        for the `wake.Pass` that `word.keep`, `word.deliver` and `word.line` take, and for
        nothing else. Its state and its home are `<name>`, as a repo's are."""
        return Project(self.name, Path(os.devnull), self.name, self.project_id, "", "")


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
    ignored: tuple[str, ...] = ()
    tabled: tuple[Hook, ...] = ()
    webhook: Hook = ("", "")
    blocking: Hook = ("", "")
    scratch: tuple[Scratch, ...] = ()

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

    def addressee(self, name: str | None) -> Project:
        """Return the home a word is for: a repo project by its name, or a scratch home's
        addressee."""
        for one in self.scratch:
            if one.name == name:
                return one.addressee()
        return self.project(name)

    def secrets(self) -> tuple[str, ...]:
        """Return every string that must not leave this machine in a list, a digest or a line:
        what `secrets` returns for each webhook, and the stored token's `CREDENTIALS`. The
        token's other strings, such as `Bearer` and its scope, are not secret."""
        stored = read_json(self.token_path, {})
        token = stored.get("token") if isinstance(stored, dict) else None
        strings = [token.get(name) for name in CREDENTIALS] if isinstance(token, dict) else []
        return secrets(*self.hooks(), *strings)

    def hooks(self) -> list[Project | Hook]:
        """Return every webhook URL and key the config file holds, whether jbus reads them or
        not."""
        return [*self.projects, self.webhook, self.blocking, *self.tabled]

    def state(self, project: Project) -> Path:
        """Return where jbus keeps this project's queue, outbox, launches and what it has
        sent."""
        return self.state_dir / project.name

    def home(self, project: Project) -> Path:
        """Return the home's state directory for the project's repo: its briefs, requests and
        gates."""
        return self.home_dir / project.state


def old_names() -> dict[str, str]:
    """Return each name that changed, with the name it has now. The old names are those of `WAS`,
    and each name of `NAMED_AFTER` spelled with the user's name from the settings, as jbus wrote it
    then. A name that is a level now, as `user` is with the default settings, is not an old name.
    This function reads the settings file, so a caller with many names to read calls it once and
    passes the map to the two functions below."""
    try:
        name = jsettings.load().user.lower()
    except jsettings.Invalid:
        name = jsettings.DEFAULTS.user
    named = {now.replace(jsettings.DEFAULTS.user, name): now for now in NAMED_AFTER}
    return {was: now for was, now in (named | WAS).items() if was not in (*LEVELS, now)}


def current_level(name: str, names: dict[str, str]) -> str:
    """Return a level by the name it has now. `names` is `old_names`."""
    now = names.get(name, name)
    return now if now in LEVELS else name


def current_kind(name: str, names: dict[str, str]) -> str:
    """Return a kind of event by the name it has now. `names` is `old_names`.

    `wake.Box` reads the outbox, the keys of what it sent, and the log through this function.
    Nothing writes an old name any more. This function maps no old name of a level to a kind,
    because a key of `sent.json` may begin with any word, the user's name among them. A module that
    looks one key up in `sent.json` reads the file as it is, since no such module looks up a kind
    that changed.
    """
    now = names.get(name, name)
    return name if now in LEVELS else now


def config_dir() -> Path:
    return Path(os.environ.get("JBUS_CONFIG_DIR") or Path.home() / ".config" / "jbus")


def private(path: Path) -> None:
    """Refuse a file that holds a key or a token and that group or others can read."""
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise Refused(f"refused: {path} is mode {mode:03o}, readable by others: chmod 600 it")


def _ignored(raw: dict[str, Any]) -> tuple[str, ...]:
    """Return each key of `IGNORED` a project still has, by name, whatever its value is."""
    found = ((key, one["name"]) for one in raw.get("project", []) for key in IGNORED if key in one)
    return tuple(f"{key} of project {name}" for key, name in found)


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


def _tabled(raw: dict[str, Any]) -> tuple[Hook, ...]:
    """Return the webhook URL and key of each top-level table that has one. Each is secret,
    whether jbus reads the table or not."""
    tables = (table for table in raw.values() if isinstance(table, dict))
    found = ((table.get("webhook_url"), table.get("webhook_key")) for table in tables)
    return tuple((str(url or ""), str(key or "")) for url, key in found if url or key)


PAIR = ("webhook_url", "webhook_key")
BLOCKING = ("blocking_url", "blocking_key")


def _missing(table: dict[str, Any], pair: tuple[str, str] = PAIR) -> str | None:
    """When the table has one key of its pair and not the other, return the missing key.
    Otherwise return None. A URL with
    an empty key counts as a missing key, since it would post with no key. An empty URL beside
    a key is not a webhook, and `load` accepts it."""
    url, key = pair
    present = [name for name in pair if name in table]
    if len(present) == 1:
        return next(name for name in pair if name not in table)
    if present and table[url] and not table[key]:
        return key
    return None


def _pair(table: dict[str, Any], default: Hook, pair: tuple[str, str] = PAIR) -> Hook:
    """Return the table's URL and key, or `default` when it has neither. `_missing` has already
    refused half a pair."""
    if not any(name in table for name in pair):
        return default
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
    for pair in (PAIR, BLOCKING):
        if missing := _missing(raw, pair):
            raise Refused(
                f"refused: {path} has no top-level {missing} beside the other: "
                "give it both, or neither"
            )
    webhook = _pair(raw, ("", ""))
    blocking = _pair(raw, ("", ""), BLOCKING)
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
            if missing := _missing(entry):
                raise Refused(
                    f"refused: project {entry['name']} has no {missing} of its own beside the "
                    "other: give it both, or neither to take the top-level pair"
                )
            url, key = _pair(entry, webhook)
            migrations, names = _migrations(entry)
            projects.append(
                Project(
                    name=str(entry["name"]),
                    checkout=Path(str(entry["checkout"])).expanduser(),
                    state=str(entry.get("state") or entry["name"]),
                    project_id=str(entry["projectId"]),
                    webhook_url=url,
                    webhook_key=key,
                    migrations=migrations,
                    migration_names=names,
                )
            )
        server = str(raw["server"]).rstrip("/")
        ignored = _ignored(raw)
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
    home = Path.home()
    return Config(
        server=server,
        runtime_mode=raw.get("runtimeMode") or None,
        dispatch=bool(raw.get("dispatch", True)),
        max_running=cap.value,
        warn_days=int(raw.get("warn_days", 5)),
        wake_alert=int(raw.get("wake_alert", 12)),
        room_passes=int(raw.get("room_passes", 10)),
        projects=tuple(projects),
        config_dir=directory,
        state_dir=Path(os.environ.get("JBUS_STATE_DIR") or home / ".local" / "state" / "jbus"),
        home_dir=Path(os.environ.get("JBUS_HOME_DIR") or home / ".local" / "state" / "home"),
        user=user,
        ignored=ignored,
        tabled=_tabled(raw),
        webhook=webhook,
        blocking=blocking,
        scratch=tuple(scratch),
    )


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def secrets(*found: Project | Hook | Any, part: int = URL_PART) -> tuple[str, ...]:
    """Return the secret strings of each webhook and of each other string given, the longest
    first.

    A webhook's whole URL and its whole key are secret. So are the URL's host, path and query,
    except a part shorter than `part`, since taking `/` out of a text hides nothing. For an error
    that quotes the URL, the caller passes a `part` of 2, so a part of two characters counts too.
    """
    whole: set[str] = set()
    parts: set[str] = set()
    for one in found:
        if isinstance(one, Project | tuple):
            address, key = one if isinstance(one, tuple) else (one.webhook_url, one.webhook_key)
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


def write_json(path: Path, value: Any, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(handle, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
        os.fsync(handle)
    finally:
        os.close(handle)
    os.chmod(temporary, mode)
    os.replace(temporary, path)
