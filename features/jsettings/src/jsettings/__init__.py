"""jsettings: who jstack works for, in which time zone, and how full an account may get before
a new launch goes to another account. Every command reads these settings the same way.

The settings are in one file, `${XDG_CONFIG_HOME:-~/.config}/jstack/config.toml`, beside the
role map. It has seven keys, and each is optional:

- `user`: the name of the one person who accepts a hold and approves a launch. The commands
  print this name for that person. The default is `user`.
- `timezone`: an IANA name, such as `America/New_York`, for every time that a command prints or
  reads. The default is the machine's own zone.
- `timezone_label`: the word after such a time. The default is the zone's abbreviation for
  that time.
- `headroom`: the share of a usage window, in percent, at which jroles counts a provider
  instance as full for a new launch, and sends the launch to the next instance of its pool. The
  default is 90. A move off a running thread still waits for a real cap, 100.
- `retry_cap`: how many fixes a home queues for one blocker before it stops and raises the
  blocker to the user as a decision (`jbus.blockers`). A whole number of 1 or more. The default
  is 2.
- `go`: how a row gets the user's go without a word for each row. `entry`, the default: the user
  gives a plan entry its go once (`jbus plan go`), and jbus approves each row filed under that
  entry while the go holds. `silence`: a home parks its own pick for a new row as a gate whose
  default is `approve`, and jbus approves the row when the gate closes on that default
  (`jbus.questions`).
- `go_quiet_minutes`: how long such a gate waits for an answer before it closes on its default.
  A whole number of 1 or more. The default is 30.

With no file, every key has its default, and nothing in this module writes the file. `load` is
the one reader. It returns the `Settings`, or raises `Invalid` with the one line that says why
it cannot use a file that is there.

The module also holds the small rules that every package of jstack shares, since it is the one
package that imports none of the others: where jstack's config is (`config_home`), how a moment is
stored and read back (`stamp`, `when`), the form of a thread's id (`thread_id`), and a JSON list
of records that threads change under a lock (`LockedList`).
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import tomllib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

KEYS = (
    "user",
    "timezone",
    "timezone_label",
    "headroom",
    "retry_cap",
    "go",
    "go_quiet_minutes",
)
NAMES = KEYS[:3]
HEADROOM = 90
RETRY_CAP = 2
ENTRY, SILENCE = "entry", "silence"
GOES = (ENTRY, SILENCE)
GO_QUIET_MINUTES = 30
_NAME = re.compile(r"[^\s,]+")
_AT = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (\S+)")
PREFIX = "mcp:"


def config_home(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """`${XDG_CONFIG_HOME:-~/.config}/jstack`, where jstack's config files are. `env` and `home`
    are this process's own environment and home unless a caller names another machine's."""
    env = os.environ if env is None else env
    return Path(env.get("XDG_CONFIG_HOME") or (home or Path.home()) / ".config") / "jstack"


def stamp(moment: datetime, *, z: bool = False) -> str:
    """The moment in UTC to the second, as a file stores it: `2026-10-27T15:25:17+00:00`, or
    ending `Z` with `z`. A file keeps the one form it has always written."""
    said = moment.astimezone(UTC).isoformat(timespec="seconds")
    return said.replace("+00:00", "Z") if z else said


def when(text: str) -> datetime:
    """The moment that a stored time names, in either form `stamp` writes and in GitHub's."""
    return datetime.fromisoformat(text)


def thread_id(text: str) -> str:
    """The thread's id in T3 Code's form: the prefix `mcp:`, then the id."""
    return text if not text or text.startswith(PREFIX) else PREFIX + text


@dataclass(frozen=True)
class LockedList[T]:
    """A JSON list of records, the file `name` in a directory, which threads change under the lock
    file `lock` beside it. Each change replaces the whole file with a rename, so a reader never
    sees half a list. `parse` makes the records of the file's list, and may raise `ValueError`,
    `TypeError` or `KeyError` on one it cannot read: a file that cannot be read is no records.
    A record is a dataclass with a `since` and an `id`, which order the list."""

    name: str
    lock: str
    parse: Callable[[Any], list[T]]

    def there(self, at: Path) -> bool:
        return (at / self.name).exists()

    @contextmanager
    def held(self, at: Path) -> Iterator[None]:
        at.mkdir(parents=True, exist_ok=True)
        fd = os.open(at / self.lock, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def peek(self, at: Path) -> list[T]:
        """The records, read with no lock, for a reader that must not make the lock file."""
        try:
            return self.parse(json.loads((at / self.name).read_text()))
        except (OSError, ValueError, TypeError, KeyError):
            return []

    def read(self, at: Path) -> list[T]:
        """Every record, the oldest first."""
        with self.held(at):
            return sorted(self.peek(at), key=lambda one: (one.since, one.id))

    def change(self, at: Path, how: Callable[[list[T]], list[T]]) -> None:
        """Replace the records with what `how` makes of them, and write the file only when that
        differs."""
        with self.held(at):
            was = self.peek(at)
            now = how(was)
            if now != was:
                temp = at / f".{self.name}.{os.getpid()}"
                temp.write_text(json.dumps([asdict(one) for one in now], indent=2) + "\n")
                os.replace(temp, at / self.name)


class Invalid(ValueError):
    """The config file is there, and `load` cannot use it. The message is the one line to
    print."""


@dataclass(frozen=True)
class Settings:
    """`zone` is None for the machine's own zone, and `label` is empty when the word is the
    zone's own abbreviation."""

    user: str = "user"
    zone: ZoneInfo | None = None
    label: str = ""
    headroom: float = HEADROOM
    retry_cap: int = RETRY_CAP
    go: str = ENTRY
    go_quiet_minutes: int = GO_QUIET_MINUTES

    def local(self, moment: datetime) -> datetime:
        """The moment in the zone. The method reads a moment with no zone of its own as a
        time in this zone."""
        if self.zone is None:
            return moment.astimezone()
        return moment.astimezone(self.zone) if moment.tzinfo else moment.replace(tzinfo=self.zone)

    def word(self, moment: datetime) -> str:
        """The word after a time: the label, or the zone's abbreviation for that moment."""
        return self.label or self.local(moment).tzname() or "UTC"

    def day(self, moment: datetime) -> str:
        return self.local(moment).date().isoformat()

    def clock(self, moment: datetime) -> str:
        return f"{self.local(moment):%H:%M} {self.word(moment)}"

    def stamp(self, moment: datetime) -> str:
        return f"{self.local(moment):%Y-%m-%d %H:%M} {self.word(moment)}"

    def _said(self, at: str) -> tuple[datetime | None, str]:
        """The time that an `--at` names and the word after it, or no time when it names
        none."""
        found = _AT.fullmatch(at)
        try:
            return (
                (datetime.strptime(found[1], "%Y-%m-%d %H:%M"), found[2]) if found else (None, "")
            )
        except ValueError:
            return None, ""

    def form(self, at: str = "") -> str:
        """The form of an `--at`, with the zone's word for the time that this `--at` names.
        When `--at` names no time, the word is the zone's word for now. So the refusal message
        shows a word that `takes` accepts."""
        return f"<YYYY-MM-DD HH:MM {self.word(self._said(at)[0] or datetime.now())}>"

    def takes(self, at: str) -> bool:
        """Whether `--at` is a time as `stamp` writes it, with the zone's word for that time.

        An hour that occurs twice when the clocks go back has two words, and `takes` accepts
        either.
        """
        said, word = self._said(at)
        if said is None:
            return False
        return word in {self.word(said), self.word(said.replace(fold=1))}


DEFAULTS = Settings()


def path() -> Path:
    return config_home() / "config.toml"


def load(file: Path | None = None) -> Settings:
    """The settings of the file, or the defaults when there is no file."""
    file = file or path()
    try:
        raw = tomllib.loads(file.read_text())
    except FileNotFoundError:
        return DEFAULTS
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) else "it is not UTF-8"
        raise Invalid(f"cannot read {file}: {reason}") from error
    except tomllib.TOMLDecodeError as error:
        raise Invalid(f"{file} does not parse: {error}") from error
    unknown = [key for key in raw if key not in KEYS]
    if unknown:
        raise Invalid(f"{file} has the key {unknown[0]}, not one of {', '.join(KEYS)}")
    for key in NAMES:
        if key in raw and not (isinstance(raw[key], str) and _NAME.fullmatch(raw[key])):
            raise Invalid(f"{file} has a {key} that is not one word with no comma")
    headroom = raw.get("headroom", HEADROOM)
    if (
        isinstance(headroom, bool)
        or not isinstance(headroom, int | float)
        or not 0 < headroom <= 100
    ):
        raise Invalid(f"{file} has a headroom that is not a percent over 0 and up to 100")
    cap = raw.get("retry_cap", RETRY_CAP)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise Invalid(f"{file} has a retry_cap that is not a whole number of 1 or more")
    go = raw.get("go", ENTRY)
    if go not in GOES:
        raise Invalid(f'{file} has a go that is not "{ENTRY}" or "{SILENCE}"')
    quiet = raw.get("go_quiet_minutes", GO_QUIET_MINUTES)
    if isinstance(quiet, bool) or not isinstance(quiet, int) or quiet < 1:
        raise Invalid(f"{file} has a go_quiet_minutes that is not a whole number of 1 or more")
    zone = None
    if "timezone" in raw:
        try:
            zone = ZoneInfo(raw["timezone"])
        except (KeyError, ValueError, OSError) as error:
            if not available_timezones():
                raise Invalid(
                    f"{file} has the timezone {raw['timezone']}, and this Python has no time "
                    "zone database to find it in: the system has none and tzdata is not installed"
                ) from error
            raise Invalid(f"{file} has the timezone {raw['timezone']}, not an IANA name") from error
    label = raw.get("timezone_label", "")
    return Settings(raw.get("user", "user"), zone, label, headroom, cap, go, quiet)
