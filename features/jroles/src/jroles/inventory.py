"""The provider inventory, `${XDG_CONFIG_HOME:-~/.config}/jstack/providers.json`, which lists
the provider instances this machine runs, in T3 Code's `providerInstances` shape. infra's
install links the file. jstack only reads it, in this module, for both `jinstall` and
`jgauge limits`.

`claude_instances` follows the same rule that `features/jgauge/hooks/limits.sh` follows to map a
Claude home to the instance whose ledger file the hook writes. A home maps to the first declared
Claude instance whose `config.homePath` is that home, and an instance that names no homePath has
`~/.claude` as its home. When no declared instance has `~/.claude`, that home maps to the
built-in `claudeAgent`.
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
    shape, `{driver, enabled, config: {homePath?}}`. `home` is the homePath after the function
    expands `~` and strips the trailing `/`, or None when the instance has no homePath."""

    driver: str
    enabled: bool
    home: Path | None


def instances(value: object, home: Path) -> dict[str, Instance] | str:
    """The instances of a `providerInstances` object, or why it is not one. The function
    refuses a homePath that is not absolute after it expands `~`, since T3 would read such a
    path relative to its own cwd."""
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
    """The inventory at `path`, or why the function cannot read it. The function reads a
    missing file as `{}`."""
    try:
        return instances(json.loads(path.read_text()), home)
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, ValueError):
        return "it cannot be read as JSON"


def claude_instances(declared: dict[str, Instance], home: Path) -> dict[str, Path]:
    """Each Claude instance mapped to its home, by the rule in the module's docstring, with
    one instance for each home."""
    found: dict[Path, str] = {}
    for name, each in declared.items():
        if each.driver == BUILT_IN:
            found.setdefault(each.home or home / ".claude", name)
    if BUILT_IN not in found.values():
        found.setdefault(home / ".claude", BUILT_IN)
    return {name: where for where, name in found.items()}
