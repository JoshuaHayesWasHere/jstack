"""The skills a brief names on its `Skills:` line: each name resolved to the one file it
loads, and each held to the artifact a Result owes for it.

This is the one resolver. `jbus queue add` and the launch refuse a name it does not
resolve (`parse.CHECKS`), the crew and scout skills load the files it names (`jbriefs
--skills`), and `jmerge` holds a pull request whose Results leave a named skill with no
artifact (`jmerge.ready.short_of`).

The names are pstack's, so that a name in a brief resolves the same way in Grok Bot, which
pstack drives, and in T3, which jstack drives. A name is a skill, `skills/<name>/SKILL.md`,
or a principle, `principles/principle-<name>.md`, of the repo this module lives in, and its
canonical form is the directory's or the file's name: `architect`, `principle-model-the-
domain`. The one list of names is those two directories: there is no table to keep beside
them. Two kinds of alias are read from the same list. A principle's name before it took
pstack's prefix, `model-the-domain`, is that principle. A pstack skill that jstack keeps as
a playbook (`PLAYBOOKS`) is `playbooks/<name>.md`. Any other spelling, a path, a `/` in
front or a capital letter, is no name, and so is a pstack skill jstack did not take
(`poteto-mode`, and the `Not taken:` line of `THIRD_PARTY.md`).

`templates/skill-artifacts.md` says what each one leaves under `Skills run:` in a Result:
one item, `- <name>: <the artifact>`, its further lines indented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parents[2]
SKILLS = ROOT / "skills"
PRINCIPLES = ROOT / "principles"
PLAYBOOK_DIR = ROOT / "playbooks"
PLAYBOOKS = ("arena", "swarm")
ARTIFACTS = ROOT / "templates" / "skill-artifacts.md"
ALIAS = "principle-"
DEFAULT = "default"
LABEL = "Skills:"
RUN = "Skills run:"
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SPLIT = re.compile(r"[,\s]+")
_ITEM = re.compile(r"^[-*] +`?(?P<name>[^`:\s]+)`?:[ \t]*(?P<artifact>.*)$")
_LABEL = re.compile(r"^(?P<label>[A-Z][A-Za-z]*(?: [A-Za-z]+)*):")
SHOWN = 5
_SKIP = re.compile(r"skip(?:ped)?\s*(?::|$)", re.I)
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
        return str(self.path.relative_to(ROOT)) if self.path else ""


def resolve(said: str) -> Named:
    """The file a name loads: `skills/<name>/SKILL.md`; for `principle-<name>`,
    `principles/principle-<name>.md` alone; for an old principle name, the principle that
    took the prefix; for a pstack skill kept as a playbook, the playbook."""
    if not _NAME.fullmatch(said):
        return Named(said, None)
    if said.startswith(ALIAS):
        principle = PRINCIPLES / f"{said}.md"
        return Named(said, principle if principle.is_file() else None)
    for path in (
        SKILLS / said / "SKILL.md",
        PRINCIPLES / f"{ALIAS}{said}.md",
        PLAYBOOK_DIR / f"{said}.md" if said in PLAYBOOKS else None,
    ):
        if path is not None and path.is_file():
            return Named(said, path)
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


_NAMES = "(name a skill of skills/ or a principle of principles/, without its path, or none)"


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
        fault = f"names {listed}, {which} no skill in skills/ and no principle in principles/"
    return f"brief's Skills: line {fault} {_NAMES}"


def artifacts(path: Path = ARTIFACTS) -> dict[str, str]:
    """What each name leaves in a Result, from the map file: `- <name>: <the artifact>`."""
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
    templates = ROOT / "templates"
    return frozenset(
        found["label"]
        for name in ("result.md", "scout-report.md")
        for line in (templates / name).read_text().splitlines()
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
    one or a placeholder, by canonical name and in the line's order. A name that resolves to
    no file is the queue's and the launch's to refuse (`unknown`), and owes nothing here."""
    have = run(text)
    return tuple(
        one.name for one in named(text) if one.path is not None and hollow(have.get(one.name, ""))
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
                f"unknown skill: {one.said} is no skill of skills/ and no principle of "
                "principles/, so nothing is loaded for it"
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
