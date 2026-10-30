"""The provider inventory: the provider instances this machine runs, as T3 Code lists them in
the `providerInstances` of its own settings, `$T3CODE_HOME/userdata/settings.json` (`~/.t3` by
default). T3 owns the list, and jstack only reads it, in this module, for `jroles`, `jinstall`
and `jgauge limits`. An instance added in T3's settings is in the inventory from the next read.

`claude_instances` follows the same rule that `features/jgauge/hooks/limits.sh` follows to map a
Claude home to the instance whose ledger file the hook writes. A home maps to the first listed
Claude instance whose `config.homePath` is that home, and an instance that names no homePath has
`~/.claude` as its home. When no listed instance has `~/.claude`, that home maps to the
built-in `claudeAgent`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

BUILT_IN = "claudeAgent"


@dataclass(frozen=True)
class Instance:
    """One provider instance as T3 lists it in `providerInstances`, `{driver, enabled,
    config: {homePath?}}`. `home` is the homePath after the function expands `~` and strips
    the trailing `/`, or None when the instance has no homePath."""

    driver: str
    enabled: bool
    home: Path | None


def instances(value: object, home: Path) -> dict[str, Instance] | str:
    """The instances of a `providerInstances` object, or why it is not one. The function
    refuses a homePath that is not absolute after it expands `~`, since T3 would read such a
    path relative to its own cwd."""
    if not isinstance(value, dict):
        return "providerInstances is not an object of provider instances"
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


def path(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """T3 Code's settings file. `env` and `home` are this process's own environment and home
    unless a caller names another machine's."""
    env = os.environ if env is None else env
    return Path(env.get("T3CODE_HOME") or (home or Path.home()) / ".t3") / "userdata/settings.json"


def declared(path: Path, home: Path) -> dict[str, Instance] | str:
    """The instances T3's settings at `path` list, or why the function cannot read them. The
    function reads a missing file, or settings with no `providerInstances`, as `{}`: T3 then
    runs only its built-in instances."""
    try:
        settings = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, ValueError):
        return "it cannot be read as JSON"
    if not isinstance(settings, dict):
        return "it is not an object of settings"
    return instances(settings.get("providerInstances", {}), home)


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
