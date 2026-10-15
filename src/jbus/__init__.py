"""jbus: what a home did by rote, done by one scheduled script with no model.

This module is the shared model: the config, its projects, and the paths under the state
directory. Every other module takes a `Config` or a `Project` and reads no path by itself.

A level of loudness and one kind of event were named after one person until the name became
a setting (`jsettings.Settings`). `NAMED_AFTER` is those two by the names they have now, and
each was written with that setting's name, in lower case, where `user` is. `old_names` is the
map from every old name to the one it has now: `current_level` reads a level through it and
`current_kind` a kind of event. A
third level, `chef`, started a POST for what asked nothing of the user: what was of that
level is `quiet` now, and is read so.

`IGNORED` is the keys of a project's table that nothing reads any more. A config that still
has one loads, and `Config.ignored` names each, so that a pass can say so until it is removed.

A `webhook_url` and `webhook_key` above the first `[[project]]` are `Config.webhook`, the
top-level webhook: the monitor of every project, posted each event for the user of each one,
and the pair of every project that has neither key of its own. A project with both keys of
its own keeps them whole, and is posted its events there as well (`wake.Box`): once, where the
two pairs are the same. One with only one of the two keys is refused: half a pair beside the
top-level one would post with the wrong key. The top-level pair is secret whether a project
takes it or not.

A `blocking_url` and `blocking_key` above the first `[[project]]` are `Config.blocking`, the
second target: the webhook of what blocks (`waiting.blocking`), which jbus-relay fans out.
It is posted no event, only each item that blocks as it opens, each reminder and each
refresh (`wake.Box.blocking`). Half of that pair is refused as half of the other is, and
both are secret.
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

Loud = Literal["user", "quiet"]
LEVELS: tuple[Loud, ...] = ("user", "quiet")
NAMED_AFTER = ("user", "waiting-on-user")
WAS = {"chef": "quiet"}
IGNORED = ("loud",)
Hook = tuple[str, str]
REDACTED = "[redacted]"
URL_PART = 8
CREDENTIALS = ("access_token", "refresh_token", "id_token")


class Refused(Exception):
    """jbus will not start, or will not run a verb. The message is the one line to print."""


@dataclass(frozen=True)
class Project:
    """One repo jbus looks after, and the webhook that is posted what the user must act on:
    its own pair, or the config's top-level one when it has none."""

    name: str
    checkout: Path
    state: str
    project_id: str
    webhook_url: str
    webhook_key: str


@dataclass(frozen=True)
class Config:
    server: str
    runtime_mode: str | None
    model_selection: dict[str, Any] | None
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
    webhook: Hook = ("", "")
    blocking: Hook = ("", "")

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

    def secrets(self) -> tuple[str, ...]:
        """Every string that must not leave this machine in a list, a digest or a line:
        what `secrets` gives for each webhook, and the stored token's `CREDENTIALS`. Its
        other strings, as `Bearer` and its scope, are no secret."""
        stored = read_json(self.token_path, {})
        token = stored.get("token") if isinstance(stored, dict) else None
        strings = [token.get(name) for name in CREDENTIALS] if isinstance(token, dict) else []
        return secrets(*self.hooks(), *strings)

    def hooks(self) -> list[Project | Hook]:
        """Every webhook URL and key the config file holds, taken by a project or not."""
        return [*self.projects, self.webhook, self.blocking]

    def state(self, project: Project) -> Path:
        """Where jbus keeps this project's queue, outbox, launches and what it has sent."""
        return self.state_dir / project.name

    def home(self, project: Project) -> Path:
        """The home's state directory of the project's repo: its briefs, requests and gates."""
        return self.home_dir / project.state


def old_names() -> dict[str, str]:
    """Each name that changed, with the one it has now: `WAS`, and each of `NAMED_AFTER` as it
    was written under the user's name of the settings. A name that is a level of now, as
    `user` is with the default settings, is no old name. It reads the settings file, so a
    caller with many names to read asks once and gives the map to the two below."""
    try:
        name = jsettings.load().user.lower()
    except jsettings.Invalid:
        name = jsettings.DEFAULTS.user
    named = {now.replace(jsettings.DEFAULTS.user, name): now for now in NAMED_AFTER}
    return {was: now for was, now in (named | WAS).items() if was not in (*LEVELS, now)}


def current_level(name: str, names: dict[str, str]) -> str:
    """A level by the name it has now. `names` is `old_names`."""
    now = names.get(name, name)
    return now if now in LEVELS else name


def current_kind(name: str, names: dict[str, str]) -> str:
    """A kind of event by the name it has now. `names` is `old_names`.

    `wake.Box` reads the outbox, the keys of what was sent and the log through here, and
    nothing writes an old name. The name a level had is no kind: a key of `sent.json` may
    begin with any word, the user's name among them.
    A module that looks one key up in `sent.json` reads the file as it is: none looks up a kind that
    changed.
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
    """Each key of `IGNORED` a project still has, by name, whatever its value is."""
    found = ((key, one["name"]) for one in raw.get("project", []) for key in IGNORED if key in one)
    return tuple(f"{key} of project {name}" for key, name in found)


PAIR = ("webhook_url", "webhook_key")
BLOCKING = ("blocking_url", "blocking_key")


def _missing(table: dict[str, Any], pair: tuple[str, str] = PAIR) -> str | None:
    """The key of the table's pair that is missing beside the other, or None. A URL with an
    empty key counts as a key missing: it would post with no key. An empty URL beside a key
    is no webhook, and loads."""
    url, key = pair
    present = [name for name in pair if name in table]
    if len(present) == 1:
        return next(name for name in pair if name not in table)
    if present and table[url] and not table[key]:
        return key
    return None


def _pair(table: dict[str, Any], default: Hook, pair: tuple[str, str] = PAIR) -> Hook:
    """The table's URL and key, or `default` when it has neither. `_missing` has refused
    half a pair first."""
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
        projects = []
        for entry in raw.get("project", []):
            if missing := _missing(entry):
                raise Refused(
                    f"refused: project {entry['name']} has no {missing} of its own beside the "
                    "other: give it both, or neither to take the top-level pair"
                )
            url, key = _pair(entry, webhook)
            projects.append(
                Project(
                    name=str(entry["name"]),
                    checkout=Path(str(entry["checkout"])).expanduser(),
                    state=str(entry.get("state") or entry["name"]),
                    project_id=str(entry["projectId"]),
                    webhook_url=url,
                    webhook_key=key,
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
    home = Path.home()
    return Config(
        server=server,
        runtime_mode=raw.get("runtimeMode") or None,
        model_selection=dict(raw["modelSelection"]) if raw.get("modelSelection") else None,
        dispatch=bool(raw.get("dispatch", True)),
        max_running=int(raw.get("max_running", 1)),
        warn_days=int(raw.get("warn_days", 5)),
        wake_alert=int(raw.get("wake_alert", 12)),
        room_passes=int(raw.get("room_passes", 10)),
        projects=tuple(projects),
        config_dir=directory,
        state_dir=Path(os.environ.get("JBUS_STATE_DIR") or home / ".local" / "state" / "jbus"),
        home_dir=Path(os.environ.get("JBUS_HOME_DIR") or home / ".local" / "state" / "home"),
        user=user,
        ignored=ignored,
        webhook=webhook,
        blocking=blocking,
    )


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def secrets(*found: Project | Hook | Any, part: int = URL_PART) -> tuple[str, ...]:
    """What is secret of each webhook, and each other string given, the longest first.

    A webhook's URL and its key are secret whole. So are the URL's host, path and query,
    but for one shorter than `part`: taking `/` out of a text says nothing. An error that
    quotes the URL is another matter, and there a part of two characters counts.
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
    """The value with each secret in each of its strings replaced, lists and dicts included."""
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
