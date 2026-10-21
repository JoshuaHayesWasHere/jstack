"""Each harness's layout: jstack's skills as that harness's agent reads them, assembled at
install time from the source into ${XDG_DATA_HOME:-~/.local/share}/jstack/harness/<harness>/.

The source is a checkout, or the tree a release's wheel carries (`jbriefs.skills.packaged`),
and the one thing read from it is its `skills.json`, which the generator writes from
`features/`: each skill, principle, playbook, template and hook, at its path in the source. A
layout holds every skill as `skills/<name>/`, flat, each file of its folder; every playbook as
`playbooks/<name>.md`; every principle as `principles/<name>.md`, a stub that points at it once
a principle is a skill; the templates; the hooks of that harness as `hooks/<file>`; a README;
and `source`, a link to the source itself, the way back from a skill to the checkout (its
`install.sh`, its git) or to the release. `skills/` and `templates/` are siblings, so a skill
that finds its templates through its own link, `realpath ~/.claude/skills/<name>/../../templates`,
finds them.

Each entry is a symlink to its file in the source, so an edit there is live with no install,
and a new file appears on the next one. A Markdown file whose relative links the layout would
break is written instead, rewritten (`links`): a target the layout holds is linked where the
layout puts it, and one it leaves out is its GitHub address. That file is stale once its
source changes. The README lists the skills and, for each, the terms it names that the harness
leaves out (`terms`).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from jinstall import links, terms
from jinstall.harnesses import Harness
from jinstall.kinds import Found
from jinstall.machine import Dropped, Machine

CATALOG = "skills.json"
PLUGIN = "plugin.json"
SHOWN = 1
NOT_THE_SKILL = frozenset(
    {"feature.json", "verify.md", "src", "tests", "docs", "evals", "templates", "hooks", "units"}
    | {"skills", "playbooks", "__pycache__"}
)
HEADER = (
    "<!-- assembled by jstack's install from {source}; do not edit: an install rewrites it -->\n"
)


@dataclass(frozen=True)
class Linked:
    """A symlink to `source`, a file of the source tree."""

    source: Path


@dataclass(frozen=True)
class Written:
    """A file the assembly writes: a rewritten Markdown file, a stub, the README."""

    content: bytes


Entry = Linked | Written


@dataclass(frozen=True)
class Assembled:
    """A layout as the source makes it: each entry by its path in the layout; each skill's
    terms the harness leaves out; and each link that dangles, as a fault."""

    entries: dict[str, Entry]
    flagged: dict[str, tuple[str, ...]] = field(default_factory=dict)
    faults: tuple[str, ...] = ()


def folder(machine: Machine, harness: Harness) -> Path:
    return machine.layout(harness.name)


def _catalog(source: Path) -> dict:
    return json.loads((source / CATALOG).read_text(encoding="utf-8"))


def catalog(source: Path) -> tuple[dict, ...]:
    """Every item of the source's `skills.json`."""
    return tuple(_catalog(source)["items"])


def hooks(source: Path) -> tuple[dict, ...]:
    """Every hook script of the source's `skills.json`, with the harnesses that run it."""
    return tuple(_catalog(source).get("hooks", ()))


def skills(source: Path) -> list[str]:
    """The name of every skill the layouts hold: each skill and each principle that is one."""
    return sorted(
        item["name"]
        for item in catalog(source)
        if item["kind"] in ("skill", "principle") and item["path"].endswith("/SKILL.md")
    )


def _skill_files(source: Path, skill: PurePosixPath) -> Iterator[PurePosixPath]:
    """Every file of the skill folder `skill`, as source paths, but what `NOT_THE_SKILL` names:
    a feature's other parts, and its playbooks, which the layout puts in playbooks/."""
    for path in sorted((source / skill).rglob("*")):
        parts = path.relative_to(source / skill).parts
        if parts[0] in NOT_THE_SKILL or any(p.startswith(".") or p == "__pycache__" for p in parts):
            continue
        if path.is_file():
            yield PurePosixPath(path.relative_to(source).as_posix())


def _placed(source: Path, harness: Harness) -> tuple[dict[str, str], dict[str, str], dict]:
    """Each source file the layout holds, by where it goes in it; each stub, by the principle
    skill it points at; and each skill's files, by its name."""
    placed: dict[str, str] = {}
    stubs: dict[str, str] = {}
    held: dict[str, list[str]] = {}
    for item in catalog(source):
        path, kind, name = PurePosixPath(item["path"]), item["kind"], item["name"]
        if kind in ("skill", "principle") and path.name == "SKILL.md":
            for one in _skill_files(source, path.parent):
                placed[str(one)] = f"skills/{name}/{one.relative_to(path.parent)}"
                held.setdefault(name, []).append(str(one))
            if kind == "principle":
                stubs[f"principles/{name}.md"] = name
        elif kind == "principle":
            placed[str(path)] = f"principles/{name}.md"
        elif kind == "playbook":
            placed[str(path)] = f"playbooks/{name}.md"
        else:
            placed[str(path)] = f"templates/{name}"
    for hook in hooks(source):
        if harness.name in hook["harnesses"]:
            placed[hook["path"]] = f"hooks/{hook['name']}"
    return placed, stubs, held


def _stub(name: str) -> bytes:
    read = f"[{name}](../skills/{name}/SKILL.md)"
    return f"# {name}\n\nThis principle is a skill: read {read}.\n".encode()


def _readme(source: Path, harness: Harness, flagged: dict[str, tuple[str, ...]]) -> bytes:
    said = {
        item["name"]: " ".join(item.get("description", "").split()).replace("|", "/")
        for item in catalog(source)
    }
    rows = "".join(
        f"| [{name}](skills/{name}/SKILL.md) | {said[name]} | {', '.join(lacks)} |\n"
        for name, lacks in ((name, flagged.get(name, ())) for name in skills(source))
    )
    return (
        f"{HEADER.format(source=source)}# jstack for {harness.title}\n\n"
        f"This folder is jstack as {harness.title} reads it. Each file is a link to its file in "
        f"{source}, so an edit there is live, and the next install adds a new skill. "
        f"`~/{harness.root}` links each skill here.\n\n"
        f"The last column names what a skill asks for that {harness.title} does not have.\n\n"
        f"| Skill | What it is for | What {harness.title} leaves out |\n|---|---|---|\n{rows}"
    ).encode()


def assemble(source: Path, harness: Harness) -> Assembled:
    """`harness`'s layout as the source at `source` makes it. Pure but for reading the source."""
    placed, stubs, held = _placed(source, harness)
    base = str(json.loads((source / PLUGIN).read_text(encoding="utf-8"))["repository"])
    entries: dict[str, Entry] = {}
    faults: list[str] = []
    for at, to in sorted(placed.items()):
        entries[to] = Linked(source / at)
        if not at.endswith(".md"):
            continue
        text = (source / at).read_text(encoding="utf-8")
        moved, dangling = links.rewrite(text, at, to, placed, source, base.rstrip("/"))
        faults += [f"{at} links to {href}, which is not in the tree" for href in dangling]
        if moved != text:
            entries[to] = Written(moved.encode())
    for stub, name in stubs.items():
        entries[stub] = Written(_stub(name))
    flagged = {
        name: tuple(
            sorted(set().union(*(terms.used(_text(source, f), harness.name) for f in files)))
        )
        for name, files in held.items()
    }
    flagged = {name: found for name, found in flagged.items() if found}
    entries["README.md"] = Written(_readme(source, harness, flagged))
    entries["source"] = Linked(source)
    return Assembled(entries, flagged, tuple(faults))


def _text(source: Path, path: str) -> str:
    return (source / path).read_text(encoding="utf-8") if path.endswith(".md") else ""


def _holds(path: Path, entry: Entry) -> bool:
    """Whether `path` is `entry`: the same link, or a file of the same bytes."""
    if isinstance(entry, Linked):
        return path.is_symlink() and os.readlink(path) == str(entry.source)
    try:
        return not path.is_symlink() and path.read_bytes() == entry.content
    except OSError:
        return False


def _found(at: Path) -> list[str]:
    """Every file and link under `at`, as paths in it, and no path under a linked folder."""
    found = []
    for top, folders, files in os.walk(at):
        here = Path(top)
        found += [here / one for one in files]
        found += [here / one for one in folders if (here / one).is_symlink()]
    return sorted(one.relative_to(at).as_posix() for one in found)


def stale(assembled: Assembled, at: Path) -> list[str]:
    """Each path of the layout at `at` that is not as `assembled` has it: an entry missing or
    different, and a file no entry makes."""
    wrong = [path for path, entry in assembled.entries.items() if not _holds(at / path, entry)]
    strays = [path for path in _found(at) if path not in assembled.entries]
    return sorted(wrong + strays)


@dataclass(frozen=True)
class Layout:
    """One harness's layout, as the source makes it.
    ok: every entry is there and nothing else; the detail counts the skills that name a term
      the harness leaves out. missing: no folder. old: `stale: <first path>, and <n> more`,
      or the first link that dangles, `<path> links to <href>, which is not in the tree`.
    put: write each stale entry by a rename, and remove each stray. A folder inside the layout
      is not in the install's record (`Machine.make_dirs`): drop prunes it. drop: remove each
      entry that is still as the install made it, and keep anything else."""

    harness: Harness

    def _assembled(self, machine: Machine) -> Assembled:
        return assemble(machine.source, self.harness)

    def probe(self, machine: Machine) -> Found:
        at = folder(machine, self.harness)
        try:
            assembled = self._assembled(machine)
        except (OSError, ValueError, KeyError) as error:
            return Found.old(f"the source cannot be read: {error}")
        if assembled.faults:
            return Found.old(_first(list(assembled.faults)))
        if not at.is_dir():
            return Found.missing()
        found = stale(assembled, at)
        if found:
            return Found.old(f"stale: {_first(found)}")
        flagged = len(assembled.flagged)
        return Found.ok(f"README.md: {flagged} name what it leaves out" if flagged else "")

    def due(self, machine: Machine) -> bool:
        return True

    def put(self, machine: Machine) -> None:
        at = folder(machine, self.harness)
        assembled = self._assembled(machine)
        machine.make_dirs(at)
        for path in stale(assembled, at):
            target = at / path
            entry = assembled.entries.get(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if entry is None or (isinstance(entry, Linked) and not target.is_symlink()):
                if target.is_symlink() or target.exists():
                    machine.unlink(target)
            if isinstance(entry, Linked):
                machine.link(target, entry.source)
            elif entry is not None:
                machine.write_text(target, entry.content.decode())
        _prune(at)

    def drop(self, machine: Machine) -> Dropped:
        at = folder(machine, self.harness)
        if not at.is_dir():
            return Dropped()
        try:
            entries = self._assembled(machine).entries
        except (OSError, ValueError, KeyError):
            entries = {}
        kept = 0
        for path in _found(at):
            entry = entries.get(path)
            if entry is not None and _holds(at / path, entry):
                machine.unlink(at / path)
            else:
                kept += 1
        _prune(at)
        if kept:
            return Dropped(kept=(f"layout {at} -> {kept} files the install did not make",))
        return Dropped(removed=(f"layout {at}",))


def _first(found: list[str]) -> str:
    more = len(found) - SHOWN
    return f"{', '.join(found[:SHOWN])}, and {more} more" if more > 0 else ", ".join(found)


def _prune(at: Path) -> None:
    """Remove each empty directory under `at`, deepest first: what a removed skill left."""
    for top, _, _ in os.walk(at, topdown=False):
        if Path(top) != at and not os.listdir(top):
            os.rmdir(top)
