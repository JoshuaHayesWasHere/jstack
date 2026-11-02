"""`jgauge limits`: each Claude account's five-hour and weekly use. The command reads it ahead
of time into the ledger (`jroles.ledger`), so a launch can skip an account before the account
is capped.

The accounts are the Claude homes of T3's provider instances (`jroles.inventory`), and the
command treats each home as an instance. For each home it reads the first of these sources that
answers:

1. `GET https://api.anthropic.com/api/oauth/usage` with the home's own access token, from
   `<home>/.credentials.json`, while that token has not expired. Claude Code makes the same
   call for `/usage`. `JGAUGE_USAGE_URL` names another address, for a test.
2. The answer Claude Code cached in the home's `.claude.json` (`~/.claude.json` for `~/.claude`),
   `cachedUsageUtilization`, while it is younger than `jroles.ledger.FRESH` and belongs to the
   account signed in there.

The command never refreshes, writes or prints a token, and it never writes either file. A
refresh token rotates on each refresh, so a refresh here would conflict with the sessions signed
in with that token. When no source answers for a home, the command writes nothing for it and
prints `stale <instance>: <why>`. The home's last line then stays, so a launch never reads a
capped account as free. When the command reads a home, it sets the time of the home's ledger
file to now, even when no line changed. With that, `--check` can tell an idle account apart from
a reader that stopped running.

An endpoint that answers 429 changes no line of the ledger, in either direction: the last good
value stays, and nothing marks the account free or capped on a guess. The command keeps a retry
time in `<ledger file>.retry` (the answer's `Retry-After`, or `RETRY`) and does not ask the endpoint
again before it. The file also says that the last read of a home failed, for any reason, and a good
answer from the endpoint removes it. `unread` is what `jbus.outbox` asks of that: the ledger's
reading is out of date only while such a file stands and the ledger is older than
`jroles.ledger.FRESH`.

The endpoint returns a slightly different reset on each call (21:29:59.74, then 21:30:00.31).
The command floors it to the second, as the other writers do, and the ledger's merge takes
resets a few minutes apart as one window. A window that is null or has no reset is not open: the
command writes no line for it, keeps the other window's reading, and says so. An account resting
between sessions answers `five_hour: null`, with `seven_day` as usual, and that is a reading.
An answer with no such key at all is not one, and its `stale` line names the keys it has.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path

from jroles import inventory, ledger

URL = "https://api.anthropic.com/api/oauth/usage"
BETA = "oauth-2025-04-20"
RETRY = timedelta(minutes=10)
TIMEOUT_SECONDS = 10
NOT_OPEN = "the answer gives it null, as it does until a session opens it"


@dataclass(frozen=True)
class Home:
    """A Claude home, and the instance whose ledger file `jgauge limits` writes for it."""

    instance: str
    path: Path

    def credentials(self) -> Path:
        return self.path / ".credentials.json"

    def config(self) -> Path:
        """Where Claude Code keeps this home's `.claude.json`. For the home Claude Code uses when
        `CLAUDE_CONFIG_DIR` is not set, the file is beside `~/.claude`, not in it."""
        if self.path == Path.home() / ".claude":
            return Path.home() / ".claude.json"
        return self.path / ".claude.json"


class Stale(Exception):
    """No source of a home answered. The message gives one reason for each source."""


class Refused(ValueError):
    """The endpoint answered 429. `until` is when it may be asked again."""

    def __init__(self, until: datetime) -> None:
        super().__init__(f"the usage endpoint answered 429, asked again at {until.isoformat()}")
        self.until = until


def homes(home: Path | None = None) -> list[Home]:
    """Each Claude home of the inventory, or the built-in one where the inventory lists
    none. Raises `Stale` with the reason when the inventory cannot be read."""
    home = home or Path.home()
    found = inventory.declared(inventory.path(), home)
    if isinstance(found, str):
        raise Stale(f"{inventory.path()}: {found}")
    return [Home(name, where) for name, where in inventory.claude_instances(found, home).items()]


def _json(file: Path) -> dict:
    try:
        found = json.loads(file.read_text())
    except FileNotFoundError as error:
        raise ValueError(f"no {file}") from error
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"{file} cannot be read as JSON") from error
    if not isinstance(found, dict):
        raise ValueError(f"{file} is not an object")
    return found


def records(instance: str, usage: object) -> list[ledger.Record]:
    """The ledger's lines for a usage answer. The answer has the shape that the endpoint
    returns and that Claude Code caches, `{five_hour: {utilization, resets_at}, ...}`, where a
    window no session has opened is null and has no line. Raises ValueError for an answer not in
    that shape, which names the answer's keys and none of its values."""
    if not isinstance(usage, Mapping):
        raise ValueError("the answer is not an object")
    found = []
    for window in ledger.WINDOWS:
        if window not in usage:
            keys = ", ".join(sorted(str(key) for key in usage)) or "nothing"
            raise ValueError(f"the answer has no {window}: it has {keys}")
        each = usage[window]
        if each is None:
            continue
        if not isinstance(each, Mapping):
            raise ValueError(f"the {window} is not an object")
        used, resets = each.get("utilization"), each.get("resets_at")
        if isinstance(used, bool) or not isinstance(used, int | float) or used < 0:
            raise ValueError(f"the {window} utilization is not a share")
        if resets is None:
            continue
        try:
            at = datetime.fromisoformat(str(resets))
        except ValueError as error:
            raise ValueError(f"the {window} reset is not a time") from error
        found.append(ledger.Record(instance, window, round(float(used), 2), int(at.timestamp())))
    return found


Fetch = Callable[[str, str], object]


def _waits(error: urllib.error.HTTPError) -> timedelta:
    """How long a 429 asks us to wait: its `Retry-After` in seconds, or `RETRY`."""
    said = str((error.headers or {}).get("Retry-After") or "")
    return timedelta(seconds=int(said)) if said.isdecimal() else RETRY


def retry_file(instance: str) -> Path:
    file = ledger.file_of(instance)
    return file.with_name(f"{file.name}.retry")


def retry_at(instance: str) -> datetime | None:
    """When the endpoint may be asked again for this instance, or None where no time is kept."""
    try:
        return datetime.fromtimestamp(int(retry_file(instance).read_text().split()[0]), UTC)
    except (OSError, ValueError, IndexError):
        return None


def _keep_retry(instance: str, until: datetime) -> None:
    file = retry_file(instance)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(f"{int(until.timestamp())}\n")


def unread(instance: str, now: datetime) -> str:
    """Why the instance's ledger is out of date, or nothing while its reading stands: its last read
    failed and the ledger has not been read for `ledger.FRESH`. An instance `jgauge limits` does
    not read has no retry file, so its ledger is never out of date by this."""
    if not retry_file(instance).exists():
        return ""
    return ledger.stale(ledger.file_of(instance), now) or ""


def fetch(url: str, token: str) -> object:
    """The endpoint's answer, as JSON. The function sends the token in the header and nowhere
    else."""
    asked = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": BETA,
            "User-Agent": "jgauge",
        },
    )
    with urllib.request.urlopen(asked, timeout=TIMEOUT_SECONDS) as answer:
        return json.loads(answer.read())


def from_endpoint(home: Home, now: datetime, get: Fetch) -> list[ledger.Record]:
    oauth = _json(home.credentials()).get("claudeAiOauth")
    if not isinstance(oauth, Mapping) or not isinstance(oauth.get("accessToken"), str):
        raise ValueError(f"{home.credentials()} has no access token")
    expires = oauth.get("expiresAt")
    if not isinstance(expires, int | float) or expires / 1000 <= now.timestamp():
        raise ValueError("its token has expired, and is never refreshed here")
    wait = retry_at(home.instance)
    if wait and wait > now:
        raise ValueError(f"the usage endpoint answered 429, asked again at {wait.isoformat()}")
    url = os.environ.get("JGAUGE_USAGE_URL") or URL
    try:
        usage = get(url, oauth["accessToken"])
    except urllib.error.HTTPError as error:
        if error.code == HTTPStatus.TOO_MANY_REQUESTS:
            refused = Refused(now + _waits(error))
            _keep_retry(home.instance, refused.until)
            raise refused from None
        raise ValueError(f"the usage endpoint answered {error.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ValueError(f"the usage endpoint did not answer: {type(error).__name__}") from None
    return records(home.instance, usage)


def from_cache(home: Home, now: datetime) -> list[ledger.Record]:
    config = _json(home.config())
    cached = config.get("cachedUsageUtilization")
    if not isinstance(cached, Mapping):
        raise ValueError(f"{home.config()} has no cached usage")
    account = (config.get("oauthAccount") or {}).get("accountUuid")
    if not account or cached.get("accountUuid") != account:
        raise ValueError("its cached usage is of another account")
    fetched = cached.get("fetchedAtMs")
    if not isinstance(fetched, int | float):
        raise ValueError("its cached usage has no time")
    age = now - datetime.fromtimestamp(fetched / 1000, UTC)
    if not timedelta(0) <= age < ledger.FRESH:
        raise ValueError(f"its cached usage is {age.total_seconds() / 60:.0f} min old")
    return records(home.instance, cached.get("utilization"))


def read(home: Home, now: datetime, get: Fetch = fetch) -> tuple[str, list[ledger.Record]]:
    """The source that answered for `home`, and its lines. Raises `Stale` when no source
    answered."""
    reasons = []
    for name, source in (
        ("endpoint", lambda: from_endpoint(home, now, get)),
        ("cache", lambda: from_cache(home, now)),
    ):
        try:
            return name, source()
        except ValueError as error:
            reasons.append(f"{name}: {error}")
    raise Stale("; ".join(reasons))


def keep(home: Home, found: list[ledger.Record], now: datetime, source: str = "") -> Path:
    """Merge the lines into the home's file, make the file where there is none, and set its
    time to now. The endpoint's own answer also ends the home's retry time."""
    file = ledger.file_of(home.instance)
    for record in found:
        ledger.write(record, read=source == "endpoint")
    if source == "endpoint":
        retry_file(home.instance).unlink(missing_ok=True)
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()
    os.utime(file, (now.timestamp(), now.timestamp()))
    return file


def run(now: datetime, get: Fetch = fetch) -> list[str]:
    """Read every home and return a line for each: `<instance> <source> <file>` for a home
    that the command read, and `stale <instance>: <why>` for a home that it could not read."""
    said = []
    for home in homes():
        try:
            source, found = read(home, now, get)
        except Stale as why:
            if not retry_file(home.instance).exists():
                _keep_retry(home.instance, now)
            said.append(f"stale {home.instance}: {why}")
            continue
        try:
            file = keep(home, found, now, source)
        except OSError as error:
            said.append(f"stale {home.instance}: its ledger cannot be written: {error.strerror}")
            continue
        shares = ", ".join(f"{one.window} {one.used:g}%" for one in found) or "no window open"
        if found:
            open_now = {one.window for one in found}
            shut = (window for window in ledger.WINDOWS if window not in open_now)
            shares = ", ".join([shares, *(f"{window} not open: {NOT_OPEN}" for window in shut)])
        said.append(f"{home.instance} from the {source}: {shares}, into {file}")
    return said


def renewed(home: Home, since: datetime, now: datetime) -> bool:
    """Say whether the home was signed in again after `since`: its credentials were written after
    that and their token has not expired. It reads the expiry and no token."""
    try:
        oauth = _json(home.credentials()).get("claudeAiOauth")
        written = home.credentials().stat().st_mtime
    except (ValueError, OSError):
        return False
    expires = oauth.get("expiresAt") if isinstance(oauth, Mapping) else None
    if not isinstance(expires, int | float):
        return False
    return written > since.timestamp() and expires / 1000 > now.timestamp()


def check(now: datetime) -> list[str]:
    """`stale <instance>: <why>` for each home whose ledger file is not fresh."""
    said = []
    for home in homes():
        why = ledger.stale(ledger.file_of(home.instance), now)
        if why:
            said.append(f"stale {home.instance}: {why}")
    return said
