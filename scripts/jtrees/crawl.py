"""`crawl(root) -> Tree`: every feature of `features/`, read once and checked.

A feature is a folder of `features/` with a `feature.json`, a `SKILL.md`, or both. Its
manifest must hold to `schemas/feature.schema.json` and name its folder, and each path it
declares must be a file. Skills, principles, playbooks and templates are found where they
are now and where they will be after a move (`SPOTS`), and each is the item of the one
feature that owns its path. `plugin.json` must hold to the vendored agent-plugins schema and
carry pyproject's version. Every fault found is raised at once, in one `Invalid`.
"""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from jtrees import frontmatter, schema
from jtrees.model import FEATURES, MANIFEST, Feature, Hook, Item, Kind, Tree, pattern

FEATURE_SCHEMA = "schemas/feature.schema.json"
PLUGIN = "plugin.json"
PLUGIN_SCHEMA = "schemas/agent-plugins-1.0.0.plugin.schema.json"
PRINCIPLE = "principle-"
SKILL = "SKILL.md"

# The paths no feature owns: the repo's own build, CI, generator, lints and tests, and the entry
# points a user or a harness looks for where they are (INFRA); and the shared files the
# generator writes or a later unit deletes (SHARED-DELETE). Kept here and not in a manifest,
# since a feature owns its folder and nothing else. Each row outside lint-borders.py's LAYOUT is
# a path that may stay outside it.
REPO_OWNERS: dict[str, tuple[str, ...]] = {
    "INFRA": (
        ".github/**",
        ".gitignore",
        "LICENSE",
        "SECURITY.md",
        "THIRD_PARTY.md",
        "Makefile",
        "pyproject.toml",
        "uv.lock",
        "plugin.json",
        "schemas/**",
        "scripts/generate-jstack-trees.py",
        "scripts/jtrees/**",
        "scripts/lint-borders.py",
        "scripts/check-jstack-docs.py",
        "scripts/green_tree.py",
        "scripts/fresh-host.sh",
        "scripts/select_tests.py",
        "scripts/hot_files.py",
        "conftest.py",
        "testing/**",
        "install.sh",
        ".claude/skills/verify-jstack/SKILL.md",
        ".claude/skills/verify-jstack/features/ci-check.md",
        ".cursor/skills/verify-main-red/SKILL.md",
    ),
    "SHARED-DELETE": (
        "README.md",
        "CATALOG.md",
        "skills.json",
        ".cursor/skills/verify-jstack",
    ),
}

# Where each kind of item is found: (kind, glob from the repo root, how its name is read).
# The repo-root globs are the shim, until the files move into their feature.
SPOTS: tuple[tuple[Kind, str, str], ...] = (
    ("skill", "skills/*/SKILL.md", "folder"),
    ("skill", f"{FEATURES}/*/SKILL.md", "folder"),
    ("skill", f"{FEATURES}/*/skills/*/SKILL.md", "folder"),
    ("playbook", "playbooks/*.md", "stem"),
    ("playbook", f"{FEATURES}/*/playbooks/*.md", "stem"),
    ("playbook", f"{FEATURES}/*/skills/*/playbooks/*.md", "stem"),
    ("template", "templates/**/*", "templates"),
    ("template", f"{FEATURES}/*/templates/**/*", "templates"),
)


class Invalid(Exception):
    """The tree cannot be generated from: each fault, as `<path>: <why>`, printed after
    `prefix`."""

    def __init__(self, faults: list[str], prefix: str = "invalid: ") -> None:
        super().__init__("\n".join(faults))
        self.faults = faults
        self.prefix = prefix


def _json(path: Path, faults: list[str], root: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        faults.append(f"{path.relative_to(root)}: {error}")
        return None


def _declared(root: Path, folder: str, path: str) -> str:
    """A path a manifest declares, from the repo root: in the feature's folder once it is
    there, else where it is now."""
    moved = f"{folder}/{path}"
    return moved if (root / moved).exists() else path


def _feature(root: Path, folder: Path, rules: dict[str, Any], faults: list[str]) -> Feature | None:
    name = folder.name
    where = f"{FEATURES}/{name}/{MANIFEST}"
    manifest: dict[str, Any] = {}
    if (folder / MANIFEST).is_file():
        manifest = _json(folder / MANIFEST, faults, root) or {}
        bad = schema.validate(manifest, rules)
        faults += [f"{where}: {fault}" for fault in bad]
        if bad:
            return None
        if manifest["name"] != name:
            faults.append(f"{where}: names {manifest['name']!r}, not its folder {name!r}")
            return None
    elif (folder / SKILL).is_file():
        front = frontmatter.parse((folder / SKILL).read_text(encoding="utf-8"))
        manifest = {"name": name, "description": str(front.get("description", ""))}
    else:
        faults.append(f"{FEATURES}/{name}: has neither {MANIFEST} nor {SKILL}")
        return None
    at = f"{FEATURES}/{name}"

    def placed(path: str) -> str:
        found = _declared(root, at, path)
        if not (root / found).exists():
            faults.append(f"{where}: declares {path}, which is neither in {at}/ nor at the root")
        return found

    hooks = tuple(
        Hook(
            one["event"],
            placed(one["script"]),
            tuple(one["harnesses"]),
            one.get("matcher", ""),
            one.get("refuses", False),
        )
        for one in manifest.get("hooks", ())
    )
    return Feature(
        name=name,
        description=manifest["description"],
        packages=tuple(placed(one) for one in manifest.get("packages", ())),
        commands=tuple(sorted(manifest.get("commands", {}).items())),
        docs=tuple(placed(one) for one in manifest.get("docs", ())),
        hooks=hooks,
        status_line=placed(manifest["statusLine"]["script"]) if "statusLine" in manifest else "",
        git_hooks=tuple(
            (one["name"], placed(one["script"])) for one in manifest.get("gitHooks", ())
        ),
        nameable=tuple(manifest.get("nameable", ())),
    )


def _items(root: Path, tree: Tree, faults: list[str]) -> tuple[Item, ...]:
    found: dict[tuple[str, str], Item] = {}
    for spot, glob, naming in SPOTS:
        for path in sorted(root.glob(glob)):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(root).as_posix()
            kind: Kind = spot
            if naming == "folder":
                name = path.parent.name
            elif naming == "stem":
                name = path.stem
            else:
                parts = path.relative_to(root).parts
                name = "/".join(parts[parts.index("templates") + 1 :])
            text = path.read_text(encoding="utf-8") if path.suffix == ".md" else ""
            description = ""
            if kind == "skill":
                try:
                    front = frontmatter.parse(text)
                except frontmatter.Refused as refused:
                    faults.append(f"{relative}: frontmatter has {refused}")
                    continue
                if front.get("name") != name:
                    faults.append(
                        f"{relative}: its frontmatter names {front.get('name')!r}, not {name!r}"
                    )
                description = str(front.get("description", ""))
                if name.startswith(PRINCIPLE):
                    kind = "principle"
            owners = [one for one in tree.owners(relative) if one not in REPO_OWNERS]
            if len(owners) != 1:
                faults.append(f"{relative}: is a {kind} with {len(owners)} feature owners {owners}")
                continue
            feature = tree.feature(owners[0])
            nameable = kind == "playbook" and name in feature.nameable
            item = Item(name, kind, relative, feature.name, description, nameable)
            if (kind, name) in found:
                faults.append(f"{relative}: the {kind} {name} is also {found[kind, name].path}")
                continue
            found[kind, name] = item
    for feature in tree.features:
        for name in feature.nameable:
            if ("playbook", name) not in found or found["playbook", name].feature != feature.name:
                faults.append(
                    f"{FEATURES}/{feature.name}/{MANIFEST}: nameable {name} is no playbook it owns"
                )
    return tuple(sorted(found.values(), key=lambda one: (one.kind, one.name)))


def _plugin(root: Path, faults: list[str]) -> None:
    plugin = _json(root / PLUGIN, faults, root)
    rules = _json(root / PLUGIN_SCHEMA, faults, root)
    if plugin is None or rules is None:
        return
    faults += [f"{PLUGIN}: {fault}" for fault in schema.validate(plugin, rules)]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if plugin.get("version") != version:
        faults.append(f"{PLUGIN}: version {plugin.get('version')!r} is not pyproject's {version!r}")


def crawl(root: Path) -> Tree:
    """The tree at `root`, checked; `Invalid` with every fault where it does not hold."""
    faults: list[str] = []
    rules = _json(root / FEATURE_SCHEMA, faults, root)
    if rules is None:
        raise Invalid(faults)
    features = []
    for folder in sorted((root / FEATURES).iterdir()) if (root / FEATURES).is_dir() else ():
        if folder.is_dir():
            feature = _feature(root, folder, rules, faults)
            if feature is not None:
                features.append(feature)
    repo = tuple((name, tuple(pattern(one) for one in rows)) for name, rows in REPO_OWNERS.items())
    tree = Tree(root, tuple(features), (), repo)
    tree = Tree(root, tree.features, _items(root, tree, faults), repo)
    _plugin(root, faults)
    if faults:
        raise Invalid(faults)
    return tree


def tracked(root: Path) -> list[str]:
    """Every path git tracks at `root`, with what is added and not yet committed."""
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    )
    return sorted(
        {one for one in listed.stdout.decode().split("\0") if one and (root / one).exists()}
    )


def borders(tree: Tree, paths: list[str]) -> tuple[list[str], dict[str, tuple[str, ...]]]:
    """The paths with no owner, and those with more than one, by their owners."""
    unowned, twice = [], {}
    for path in paths:
        owners = tree.owners(path)
        if not owners:
            unowned.append(path)
        elif len(owners) > 1:
            twice[path] = owners
    return unowned, twice
