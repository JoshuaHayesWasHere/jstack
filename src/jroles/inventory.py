"""The provider inventory, `${XDG_CONFIG_HOME:-~/.config}/jstack/providers.json`: the provider
instances this machine runs, in T3 Code's `providerInstances` shape. infra's install links it;
jstack only reads it, here, for `jinstall` and `jgauge limits` alike.

`claude_instances` is the rule `hooks/limits.sh` keeps from a Claude home to the instance whose
ledger file it writes: the first declared Claude instance whose `config.homePath` is that home
(`~/.claude` where it names none), and the built-in `claudeAgent` for `~/.claude` where no
declared instance is there.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

BUILT_IN = "claudeAgent"


@dataclass(frozen=True)
class Instance:
    """One provider instance as the inventory declares it, in T3's own `providerInstances`
    shape: `{driver, enabled, config: {homePath?}}`. `home` is the homePath with `~` expanded
    and no trailing `/`, None for none."""

    driver: str
    enabled: bool
    home: Path | None


def instances(value: object, home: Path) -> dict[str, Instance] | str:
    """The instances of a `providerInstances` object, or why it is not one. A homePath that
    is not absolute once `~` is expanded is refused: T3 would read it from its own cwd."""
    if not isinstance(value, dict):
        return "it is not an object of provider instances"
    found = {}
    for name, each in value.items():
        if not isinstance(each, dict) or not isinstance(each.get("driver"), str):
            return f"{name} has no driver"
        enabled, config = each.get("enabled", True), each.get("config", {})
        if not isinstance(enabled, bool) or not isinstance(config, dict):
            return f"{name}'s enabled or config is not T3's shape"
        path = config.get("homePath")
        if path is not None and not isinstance(path, str):
            return f"{name}'s homePath is not a path"
        where = None
        if path:
            where = Path(str(home) + path[1:] if path == "~" or path.startswith("~/") else path)
            if not where.is_absolute():
                return f"{name}'s homePath {path} is not absolute"
        found[name] = Instance(each["driver"], enabled, where)
    return found


def path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "jstack" / "providers.json"


def declared(path: Path, home: Path) -> dict[str, Instance] | str:
    """The inventory at `path`, or why it cannot be taken. A missing file is `{}`."""
    try:
        return instances(json.loads(path.read_text()), home)
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, ValueError):
        return "it cannot be read as JSON"


def claude_instances(declared: dict[str, Instance], home: Path) -> dict[str, Path]:
    """Each Claude home and the instance it is read as, by the rule of the module: the instance
    to its home, one instance a home."""
    found: dict[Path, str] = {}
    for name, each in declared.items():
        if each.driver == BUILT_IN:
            found.setdefault(each.home or home / ".claude", name)
    if BUILT_IN not in found.values():
        found.setdefault(home / ".claude", BUILT_IN)
    return {name: where for where, name in found.items()}
