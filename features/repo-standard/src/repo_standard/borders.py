"""The layout's borders, read from a repo's config and its manifests, not from code.

A feature is a folder of the config's `features` folder, and owns that folder and every path in it.
Its `feature.json` validates against the schema the config's `manifest-schema` names, and names its
folder. The repo owns the paths its `owners` globs match, each group of globs by its name. The
guard finds:

- a feature folder with no manifest, or one that breaks the schema or names another folder;
- a tracked path with no owner, or with two;
- a tracked path outside each folder of `layout` and each path the repo owns;
- with `--base`, a diff that touches two features or more with no `cross-cutting` label.

Each is a warning GitHub reads as an annotation. Under `--hard` a warning fails the guard.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repo_standard import schema
from repo_standard.config import Config, Refused
from repo_standard.tree import Fault, Unreadable, matches

MANIFEST = "feature.json"


def features(root: Path, config: Config, paths: list[str]) -> tuple[set[str], list[Fault]]:
    """The folders of the config's `features` folder, each of which owns its files, and each fault
    of their manifests: missing, not JSON, breaking the schema, or naming another folder."""
    split = [path.split("/") for path in paths]
    folders = {parts[1] for parts in split if parts[0] == config.features and len(parts) > 2}
    try:
        rules = schema.load(root / config.part("manifest-schema"))
    except (OSError, ValueError) as error:
        raise Refused(f"cannot read the manifest schema: {error}") from error
    faults = []
    for name in sorted(folders):
        where = f"{config.features}/{name}/{MANIFEST}"
        try:
            manifest = json.loads((root / where).read_text(encoding="utf-8"))
        except FileNotFoundError:
            faults.append(Fault(f"{config.features}/{name}", None, f"has no {MANIFEST}"))
            continue
        except json.JSONDecodeError as error:
            at = f"line {error.lineno}, column {error.colno}"
            faults.append(Fault(where, None, f"is not JSON, at {at}"))
            continue
        wrong = schema.validate(manifest, rules)
        if not wrong and manifest.get("name") != name:
            wrong = [f"/name: names {manifest.get('name')!r}, not its folder {name!r}"]
        faults += [Fault(where, None, one) for one in wrong]
    return folders, faults


def owners(path: str, config: Config, named: set[str]) -> list[str]:
    """Who owns `path`: the feature whose folder holds it, and each group of the repo's globs."""
    found = []
    top, _, rest = path.partition("/")
    if top == config.features and "/" in rest and rest.split("/")[0] in named:
        found.append(rest.split("/")[0])
    return found + [group for group, globs in config.owners.items() if matches(path, globs)]


def ownership(config: Config, paths: list[str], named: set[str]) -> list[Fault]:
    faults = []
    for path in paths:
        found = owners(path, config, named)
        if not found:
            faults.append(Fault(path, None, "no owner"))
        elif len(found) > 1:
            faults.append(Fault(path, None, f"owned twice, by {', '.join(found)}"))
        if not path.startswith(config.layout) and not any(
            matches(path, globs) for globs in config.owners.values()
        ):
            top, _, rest = path.partition("/")
            where = f"under {top}/" if rest else "at the root"
            fault = f"a file {where}, outside {', '.join(config.layout)} and the repo's own paths"
            faults.append(Fault(path, None, fault))
    return faults


def crossing(config: Config, changed: list[str], named: set[str], labels: set[str]) -> list[Fault]:
    """The diff's first changed path, when it touches more than one feature with no label."""
    touched: dict[str, str] = {}
    for path in changed:
        for owner in owners(path, config, named):
            if owner in named:
                touched.setdefault(owner, path)
    if len(touched) < 2 or config.cross_cutting in labels:
        return []
    why = f"the diff touches {len(touched)} features, {', '.join(sorted(touched))}"
    why += f": split it, or label it {config.cross_cutting}"
    return [Fault(next(iter(touched.values())), None, why)]


def diff(root: Path, base: str) -> list[str]:
    command = ["git", "-C", str(root), "diff", "--name-only", "--no-renames", "-z"]
    listed = subprocess.run([*command, f"{base}...HEAD"], capture_output=True, text=True)
    if listed.returncode != 0:
        raise Unreadable(f"git cannot diff from {base}: {listed.stderr.strip()}")
    return [one for one in listed.stdout.split("\0") if one]


def check(
    root: Path, config: Config, paths: list[str], base: str | None = None, labels: str = ""
) -> list[Fault]:
    """Every fault of the borders in the tree at `root`, and in its diff from `base`."""
    named, faults = features(root, config, paths)
    faults += ownership(config, paths, named)
    if base:
        wanted = {one.strip() for one in labels.split(",") if one.strip()}
        faults += crossing(config, diff(root, base), named, wanted)
    return faults


def annotation(fault: Fault) -> str:
    """A fault as a warning GitHub reads, with its property and its message escaped."""

    def escape(text: str, more: bool) -> str:
        text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return text.replace(":", "%3A").replace(",", "%2C") if more else text

    return f"::warning file={escape(fault.path, True)}::{escape(fault.why, False)}"
