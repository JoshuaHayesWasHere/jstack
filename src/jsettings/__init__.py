"""jsettings: who jstack works for, in which time zone, and how full an account may get before a
launch passes it by, read the same way by every command.

One file, `${XDG_CONFIG_HOME:-~/.config}/jstack/config.toml`, beside the role map, with four
keys, each optional:

- `user`: the one name that accepts a hold and approves a launch, and the name printed for
  whoever that is. Default `user`.
- `timezone`: an IANA name, as `America/New_York` is, for every time printed and taken.
  Default the machine's own zone.
- `timezone_label`: the word after such a time. Default what the zone prints for that time.
- `headroom`: the share of a usage window, in percent, at which a new launch counts a provider
  instance as full and goes to the next of its pool. Default 90. A move off a running thread
  still waits for a real cap, 100.

With no file every key has its default, and nothing here writes the file. `load` is the one
reader: it gives the `Settings`, or raises `Invalid` with the one line that says why a file
that is there cannot be used.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

KEYS = ("user", "timezone", "timezone_label", "headroom")
NAMES = KEYS[:3]
HEADROOM = 90
_NAME = re.compile(r"[^\s,]+")
_AT = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (\S+)")


class Invalid(ValueError):
    """The config file is there and cannot be used. The message is the one line to print."""


@dataclass(frozen=True)
class Settings:
    """`zone` is None for the machine's own zone, and `label` is empty for what the zone prints."""

    user: str = "user"
    zone: ZoneInfo | None = None
    label: str = ""
    headroom: float = HEADROOM

    def local(self, moment: datetime) -> datetime:
        """The moment in the zone. One with no zone of its own is taken as a time there."""
        if self.zone is None:
            return moment.astimezone()
        return moment.astimezone(self.zone) if moment.tzinfo else moment.replace(tzinfo=self.zone)

    def word(self, moment: datetime) -> str:
        """The word after a time: the label, or what the zone prints for that moment."""
        return self.label or self.local(moment).tzname() or "UTC"

    def day(self, moment: datetime) -> str:
        return self.local(moment).date().isoformat()

    def clock(self, moment: datetime) -> str:
        return f"{self.local(moment):%H:%M} {self.word(moment)}"

    def stamp(self, moment: datetime) -> str:
        return f"{self.local(moment):%Y-%m-%d %H:%M} {self.word(moment)}"

    def _said(self, at: str) -> tuple[datetime | None, str]:
        """The time an `--at` names and the word after it, or no time where it names none."""
        found = _AT.fullmatch(at)
        try:
            return (
                (datetime.strptime(found[1], "%Y-%m-%d %H:%M"), found[2]) if found else (None, "")
            )
        except ValueError:
            return None, ""

    def form(self, at: str = "") -> str:
        """How `--at` is written, with the word the zone has at the time this `--at` names, or
        now where it names none: the word a refusal asks for is one `takes` takes."""
        return f"<YYYY-MM-DD HH:MM {self.word(self._said(at)[0] or datetime.now())}>"

    def takes(self, at: str) -> bool:
        """Whether `--at` is a time as `stamp` writes it, with the word the zone has then.

        An hour the clocks go through twice has two words, and either is taken.
        """
        said, word = self._said(at)
        if said is None:
            return False
        return word in {self.word(said), self.word(said.replace(fold=1))}


DEFAULTS = Settings()


def path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "jstack" / "config.toml"


def load(file: Path | None = None) -> Settings:
    """The settings of the file, or the defaults where there is no file."""
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
    return Settings(raw.get("user", "user"), zone, raw.get("timezone_label", ""), headroom)
