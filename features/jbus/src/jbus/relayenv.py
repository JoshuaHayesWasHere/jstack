"""The relay's env file and its settings, apart from the relay so that a reader of the file, such
as the install's probe (`jinstall.kinds.RelayKeys`), loads none of jbus's passes.

`env_file` reads the file as systemd's `EnvironmentFile=` does, and `settings` says whether the
relay would start on it (`jbus.relay`).
"""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER = "REPLACE_ME"
SERVICE = re.compile(r"[a-z0-9_]{1,128}")
SILENT_MINUTES = 90
"""Half an hour past jbus's hourly `refresh` (`leftover.REFRESH_MINUTES`), so a relay that hears
no body for that long knows jbus is silent."""


TARGETS = {"webhook": ("RELAY_WEBHOOK_URL", "RELAY_WEBHOOK_KEY")}
OLDER = {"RELAY_WEBHOOK_URL": "GROK_WEBHOOK_URL", "RELAY_WEBHOOK_KEY": "GROK_WEBHOOK_KEY"}
"""The older name of each of the webhook's keys, which the relay reads when the neutral one is
not set, so an env file written before the neutral names still starts it."""
VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PAGER = ("PAGER_HA_URL", "PAGER_HA_TOKEN", "PAGER_HA_SERVICE")


@dataclass(frozen=True)
class Target:
    name: str
    url: str
    key: str


class Refused(Exception):
    """The relay's settings are not usable, so the relay does not start."""


@dataclass(frozen=True)
class Settings:
    inbound: str
    targets: Mapping[str, Target]
    pager: Target
    port: int
    state: Path
    timeout: float
    retry: float
    dedup: float
    silent: float = SILENT_MINUTES


def _unusable(env: Mapping[str, str], key: str) -> str | None:
    if key not in env:
        return f"{key} is missing"
    if not env[key].strip():
        return f"{key} is empty"
    if PLACEHOLDER in env[key]:
        return f"{key} is {PLACEHOLDER}"
    return None


def env_file(path: Path) -> dict[str, str]:
    """Read the relay's env file as systemd's `EnvironmentFile=` reads it: one `KEY=value` a
    line, with quotes around the value left out. systemd skips a line whose key is not a
    variable name, such as `export KEY=value`, so this does too. A file that cannot be read is
    empty."""
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    found = {}
    for line in lines:
        key, equals, value = line.strip().partition("=")
        if equals and VARIABLE.fullmatch(key.strip()):
            found[key.strip()] = value.strip().strip("'\"")
    return found


def _named(env: Mapping[str, str]) -> dict[str, str]:
    """The environment with each neutral key of the webhook set from its older name, where only
    the older one is there."""
    return {**{new: env[old] for new, old in OLDER.items() if new not in env and old in env}, **env}


def settings(env: Mapping[str, str]) -> Settings:
    """Read the relay's settings from its environment. When a key is not usable, raise
    `Refused`, which names every such key and none of their values. A webhook key that only its
    older name sets is named by that name."""
    given, env = env, _named(env)

    def called(key: str) -> str:
        return OLDER[key] if key in OLDER and key not in given and OLDER[key] in given else key

    wrong = [why for why in [_unusable(env, "RELAY_INBOUND_KEY")] if why]
    for name, keys in [*TARGETS.items(), ("pager", PAGER)]:
        wrong += [
            f"target {name}: {why.replace(key, called(key))}"
            for key in keys
            if (why := _unusable(env, key))
        ]
    if wrong:
        raise Refused("; ".join(wrong))
    for name, url in [*((name, url) for name, (url, _) in TARGETS.items()), ("pager", PAGER[0])]:
        if urllib.parse.urlsplit(env[url].strip()).scheme not in ("http", "https"):
            raise Refused(f"target {name}: {called(url)} is not an http or https URL")
    base, token, service = (env[key].strip() for key in PAGER)
    if not SERVICE.fullmatch(service):
        raise Refused(f"target pager: {PAGER[2]} is not a notify service name")
    try:
        return Settings(
            inbound=env["RELAY_INBOUND_KEY"],
            targets={
                name: Target(name, env[url].strip(), env[key].strip())
                for name, (url, key) in TARGETS.items()
            },
            pager=Target("pager", f"{base.rstrip('/')}/api/services/notify/{service}", token),
            port=int(env.get("RELAY_PORT", "4390")),
            state=Path(env.get("RELAY_STATE", "~/.local/state/jbus-relay")).expanduser(),
            timeout=float(env.get("RELAY_TIMEOUT_SECONDS", "15")),
            retry=float(env.get("RELAY_RETRY_SECONDS", "300")),
            dedup=float(env.get("RELAY_DEDUP_SECONDS", "900")),
            silent=float(env.get("RELAY_SILENT_MINUTES", str(SILENT_MINUTES))),
        )
    except ValueError as error:
        numbers = "RELAY_PORT, RELAY_SILENT_MINUTES or a RELAY_*_SECONDS"
        raise Refused(f"{numbers}: {error}") from None
