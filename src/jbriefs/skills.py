"""The skills a brief names on its `Skills:` line: each name resolved to the one file it
loads, and each held to the artifact a Result owes for it.

This is the one resolver. `jbus queue add` refuses a name it does not resolve
(`parse.CHECKS`) when a row is first queued, the crew and scout skills load the files it
names (`jbriefs --skills`), and `jmerge` holds a pull request whose Results leave a named
skill with no artifact (`jmerge.ready.short_of`).

The names are listed in `skills.json` at the repo root, which
`scripts/generate-jstack-trees.py` writes from `features/` and the files they own, and nothing
else edits: `make check` fails when it is stale. A name is a skill or a principle, and its
canonical form is the skill's directory or the principle's file name: `architect`,
`principle-model-the-domain`. The file is also what any reader outside this repo (another
provider, another machine) takes the set from.

The names are pstack's, so that a name in a brief resolves the same way in Grok Bot, which
pstack drives, and in T3, which jstack drives. Three kinds of alias resolve. An entry's
`pstack_name`, where pstack's name for it differs, is that entry. A principle's name before
it took pstack's prefix, `model-the-domain`, is that principle. A pstack skill that jstack
keeps as a playbook, one its feature marks `nameable`, is that playbook. Any other spelling,
a path, a `/` in front or a capital letter, is no name, and so is a pstack skill jstack did
not take (`poteto-mode`, and the `Not taken:` line of `THIRD_PARTY.md`).

`skills.json` also lists every playbook and template, and `where(kind, name)` is the one way
the runtime finds any of these files: no module reads a path of the checkout from its own
place in it. A release has no checkout: its wheel carries the source tree beside the
packages' environment, `skills.json` with it, and `root()` is that tree.

`features/skill-library/templates/skill-artifacts.md` says what each one leaves under
`Skills run:` in a Result: one item, `- <name>: <the artifact>`, its further lines indented.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

CATALOG = "skills.json"
MARKER = "pyproject.toml"
PACKAGED = "share/jstack"
NAMEABLE = ("skill", "principle")
ALIAS = "principle-"
DEFAULT = "default"
LABEL = "Skills:"
RUN = "Skills run:"
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SPLIT = re.compile(r"[,\s]+")
_ITEM = re.compile(r"^[-*] +`?(?P<name>[^`:\s]+)`?:[ \t]*(?P<artifact>.*)$")
_LABEL = re.compile(r"^(?P<label>[A-Z][A-Za-z]*(?: [A-Za-z]+)*):")
SHOWN = 5
_SKIP = re.compile(r"skip(?:ped)?\s*(?:$|[:.,;(\-])", re.I)
_PLACEHOLDER = re.compile(r"<[^<>]*>[\s.]*")
_HOLLOW = frozenset(("none", "n/a", "na", "tbd", "todo", "tba", "-", "--", "...", "…"))


@dataclass(frozen=True)
class Named:
    """One name of a `Skills:` line: as it was written, and the file it resolves to, or
    None where it resolves to none."""

    said: str
    path: Path | None

    @property
    def name(self) -> str:
        """The canonical name: the skill's directory, or the principle's or playbook's file
        without `.md`."""
        if self.path is None:
            return self.said
        return self.path.parent.name if self.path.name == "SKILL.md" else self.path.stem

    @property
    def kind(self) -> str:
        if self.path is None:
            return "unknown"
        if self.path.name == "SKILL.md":
            return "skill"
        return self.path.parent.name.removesuffix("s")

    @property
    def relative(self) -> str:
        return str(self.path.relative_to(root())) if self.path else ""


@cache
def checkout() -> Path | None:
    """The checkout this package runs from: the nearest directory above it with both a
    `pyproject.toml` and a `skills.json`, wherever the package sits in it, so another
    project's `pyproject.toml` above an installed copy is not taken for it. None for a
    release, which has no checkout above it."""
    here = Path(__file__).resolve()
    return next(
        (up for up in here.parents if (up / MARKER).is_file() and (up / CATALOG).is_file()), None
    )


def packaged() -> Path | None:
    """The source tree a release's wheel installs under the environment this runs in,
    `PACKAGED` (its shared data, which scripts/jtrees/outputs/pyproject.py writes into
    pyproject.toml), whose `skills.json` gives each path from the tree itself, as in a
    checkout. None where it is not there."""
    copy = Path(sys.prefix) / PACKAGED
    return copy if (copy / CATALOG).is_file() else None


@cache
def root() -> Path:
    """Where every path of `skills.json` is read from: the checkout this package runs from,
    else the source tree a release carries beside it."""
    found = checkout() or packaged()
    if found is None:
        here, copy = Path(__file__).resolve(), Path(sys.prefix) / PACKAGED
        raise LookupError(
            f"no {CATALOG} beside a {MARKER} above {here}, and none in {copy}: "
            "no checkout of jstack and no release"
        )
    return found


def _items(at: Path) -> tuple[dict[str, Any], ...]:
    """The items of the `skills.json` at `at`, read again whenever the file changes, so a
    long-running server sees a regenerated list."""
    path = at / CATALOG
    return _read(path, path.stat().st_mtime_ns)


@cache
def _read(path: Path, changed: int) -> tuple[dict[str, Any], ...]:
    return tuple(json.loads(path.read_text())["items"])


def listed(kind: str, at: Path | None = None) -> dict[str, Path]:
    """Every file of `kind` (`skill`, `principle`, `playbook` or `template`) that the
    `skills.json` of the checkout `at`, this one by default, lists, by name."""
    at = root() if at is None else at
    return {item["name"]: at / item["path"] for item in _items(at) if item["kind"] == kind}


def where(kind: str, name: str, at: Path | None = None) -> Path:
    """The file of `name` of `kind`, from `skills.json`: a template by its path under
    `templates/`, as `where("template", "gates.md")`. LookupError for one it does not list."""
    found = listed(kind, at).get(name)
    if found is None:
        raise LookupError(f"{CATALOG} lists no {kind} {name}")
    return found


def _listed() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """The skills and principles of `skills.json`, by name and by `pstack_name`."""
    items = [item for item in _items(root()) if item["kind"] in NAMEABLE]
    by_name = {item["name"]: item for item in items}
    by_alias = {item["pstack_name"]: item for item in items if "pstack_name" in item}
    return by_name, by_alias


def resolve(said: str) -> Named:
    """The file a name loads, from `skills.json`: the item of that name, or the one pstack
    names so; for an old principle name, the principle that took the prefix; for a pstack
    skill kept as a playbook, the playbook."""
    if not _NAME.fullmatch(said):
        return Named(said, None)
    by_name, by_alias = _listed()
    item = by_name.get(said) or by_alias.get(said)
    if item is None and not said.startswith(ALIAS):
        old = by_name.get(f"{ALIAS}{said}")
        item = old if old is not None and old["kind"] == "principle" else None
    if item is None:
        item = next(
            (one for one in _items(root()) if one["name"] == said and one.get("nameable")), None
        )
    if item is not None:
        path = root() / item["path"]
        return Named(said, path if path.is_file() else None)
    return Named(said, None)


def _none(line: str) -> bool:
    """Whether a `Skills:` line names nothing: its first word is `none`, as in `none.` or
    `none, <why>`, the form a `Design:` line takes."""
    first = line.split(maxsplit=1)[0] if line.strip() else ""
    return first.rstrip(".,;:").lower() == "none"


def _head(text: str) -> str | None:
    """What the first `Skills:` line of a brief's head says, or None for a head with none."""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith(LABEL):
            return line.removeprefix(LABEL).strip()
    return None


def named(text: str) -> tuple[Named, ...]:
    """Each name on the brief's `Skills:` line, resolved, once each and in order. A brief
    with no line, or one that says `none`, names none."""
    line = _head(text)
    if not line or _none(line):
        return ()
    found: dict[str, Named] = {}
    for word in _SPLIT.split(line.rstrip(".;")):
        word = word.strip("`.;")
        if word:
            one = resolve(word)
            found.setdefault(one.name, one)
    return tuple(found.values())


_NAMES = "(name a skill or principle that skills.json lists, without its path, or none)"


def unknown(text: str) -> str:
    """Why a brief's `Skills:` line names something that is no skill or principle, in one
    line that names it, or nothing. A brief with no line names none, and passes."""
    line = _head(text)
    if line is None or _none(line):
        return ""
    if not line:
        fault = "is empty"
    elif line.startswith("<") or "|" in line:
        fault = "is the template's own text"
    else:
        bad = [one.said for one in named(text) if one.path is None]
        if not bad:
            return ""
        listed = ", ".join(bad[:SHOWN])
        if len(bad) > SHOWN:
            listed += f" and {len(bad) - SHOWN} more"
        which = "which is" if len(bad) == 1 else "which are"
        fault = f"names {listed}, {which} no skill and no principle that skills.json lists"
    return f"brief's Skills: line {fault} {_NAMES}"


def artifacts(path: Path | None = None) -> dict[str, str]:
    """What each name leaves in a Result, from the map file: `- <name>: <the artifact>`."""
    path = where("template", "skill-artifacts.md") if path is None else path
    found: dict[str, str] = {}
    for line in path.read_text().splitlines():
        item = _ITEM.match(line)
        if item:
            found[item["name"]] = item["artifact"].strip()
    return found


def owed(name: str, table: dict[str, str] | None = None) -> str:
    """The artifact a name owes: its own line of the map, else the default line."""
    table = artifacts() if table is None else table
    return table.get(name) or table[DEFAULT]


def _ends() -> frozenset[str]:
    """The labels that end a `Skills run:` section: every other field of the Result and of
    the scout's report, read from their templates, so an artifact may hold a line such as
    `Candidate A: ...` of its own."""
    return frozenset(
        found["label"]
        for name in ("result.md", "scout-report.md")
        for line in where("template", name).read_text().splitlines()
        if (found := _LABEL.match(line)) and f"{found['label']}:" != RUN
    )


def run(text: str) -> dict[str, str]:
    """Every artifact the `Skills run:` sections of a brief's Results hold, by canonical
    name. A section ends at a `## ` heading or at another field of the Result (`_ends`). A
    later Result's item for a name takes the place of an earlier one's."""
    found: dict[str, str] = {}
    inside = False
    current = ""
    ends = _ends()
    for line in text.splitlines():
        if line.startswith(RUN):
            inside, current = True, ""
            first = line.removeprefix(RUN).strip()
            if first and _ITEM.match(f"- {first}"):
                line = f"- {first}"
            else:
                continue
        elif not inside:
            continue
        elif line.startswith("## ") or (
            (label := _LABEL.match(line)) is not None and label["label"] in ends
        ):
            inside = False
            continue
        item = _ITEM.match(line)
        if item:
            current = resolve(item["name"]).name
            found[current] = item["artifact"].strip()
        elif current and line.strip():
            found[current] = f"{found[current]}\n{line.strip()}".strip()
    return found


def hollow(artifact: str) -> bool:
    """Whether an artifact says nothing: empty, a placeholder, or a word that stands for none."""
    said = artifact.strip()
    return (
        not said
        or bool(_PLACEHOLDER.fullmatch(said))
        or said.lower().rstrip(".") in _HOLLOW
        or bool(_SKIP.match(said))
    )


def missing(text: str) -> tuple[str, ...]:
    """The names on the brief's `Skills:` line its Results leave with no artifact, an empty
    one or a placeholder, as the brief spells them and in the line's order. The match is by
    canonical name, so `build-the-lever` in the brief and `principle-build-the-lever` under
    `Skills run:` are one name. A name that resolves to no file is the queue's and the
    launch's to refuse (`unknown`), and owes nothing here."""
    have = run(text)
    return tuple(
        one.said for one in named(text) if one.path is not None and hollow(have.get(one.name, ""))
    )


def shown(text: str) -> str:
    """What the reviewer reads of the artifacts: each named skill's, as `run` reads it, or
    that it has none. Nothing where the brief names none."""
    have = run(text)
    out = []
    for one in named(text):
        if one.path is None:
            continue
        artifact = have.get(one.name, "")
        if hollow(artifact):
            out.append(f"- {one.name}: no artifact")
        else:
            first, *rest = artifact.splitlines()
            out.append(f"- {one.name}: {first}")
            out.extend(f"  {line}" for line in rest)
    return "\n".join(out)


def load(text: str) -> str:
    """What the crew and scout skills print at their start: each named file in full, under
    a line that names them, then the artifact each owes. Nothing where none is named."""
    names = named(text)
    if not names:
        return ""
    out = []
    for one in names:
        if one.path is None:
            out.append(
                f"unknown skill: {one.said} is no skill and no principle that skills.json "
                "lists, so nothing is loaded for it"
            )
    known = [one for one in names if one.path is not None]
    if known:
        listed = " ".join(one.name for one in known)
        out.append(f"loaded: {listed}, the names on the Skills: line, each in full below")
        for one in known:
            out.append(f"\n==> {one.relative} <==")
            out.append(one.path.read_text().rstrip("\n"))
        table = artifacts()
        out.append(
            "\nthe artifact each owes under Skills run: in the Result, "
            "as templates/skill-artifacts.md says:"
        )
        out.extend(f"- {one.name}: {owed(one.name, table)}" for one in known)
    return "\n".join(out)
