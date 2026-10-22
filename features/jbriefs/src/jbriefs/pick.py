"""`jbriefs pick <path | ->`: the role skill, the playbook and the other skills for a piece of work.

The work is a brief (a file under `tasks/`), a scout's request (a file under `scouts/`), or
text with no file, which goes to the home. Everything comes from the tree this module is in.
The role comes from the file's place. The playbook comes from the file's `Playbook:` line or
from the `Run by:` rows of `playbooks/`. The other skills come from the `tip:` phrases of
`skills/*/SKILL.md`, by the rule of `features/skill-library/hooks/skill-tips.sh`, and last
from each skill the text names. No table here names a skill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jbriefs.skills import listed
from jbriefs.skills import root as checkout

TIPS = 3
_FRONT = re.compile(r"\A---\n(.*?)^---$", re.M | re.S)
_SPAN = re.compile(r"`([^`\n]+)`")
_SLASH = re.compile(r"(?<![\w/.~$-])/([a-z][a-z0-9-]*)(?![\w/-]|\.\w)")
_DIRECTORY = re.compile(r"(?<![\w/.-])skills/([a-z][a-z0-9-]*)(?![\w-])")
_PATH = re.compile(r"[\w.~*<>-]*/[\w.*<>/-]*|[\w.-]+\.[A-Za-z]{1,5}\b")
_TIPPED_FROM = ("# ", "Task:", "Done when:", "- ")
_SCOPE_FROM = ("Where:", "Change:")
_ALONGSIDE = "tests/"


@dataclass(frozen=True)
class Role:
    """Who takes a piece of work: the skill, the kind of input it is typed with, and the
    `Run by:` runner."""

    skill: str
    runner: str
    default: str
    takes_slug: bool

    def command(self, slug: str) -> str:
        return f"/{self.skill} {slug}" if self.takes_slug else f"/{self.skill}"


CREW = Role("crew", "a crewmate", "feature", takes_slug=True)
SCOUT = Role("scout", "a scout", "investigation", takes_slug=True)
HOME = Role("home", "the home", "none", takes_slug=False)
PLACES = {"tasks": CREW, "scouts": SCOUT}


@dataclass(frozen=True)
class Row:
    """One playbook's `Run by:` line: who runs it, the paths it is for, and the brief lines it
    asks for."""

    name: str
    runner: str
    scope: tuple[str, ...]
    asks: tuple[str, ...]


@dataclass(frozen=True)
class Skill:
    name: str
    phrases: tuple[str, ...]
    path: str = ""


@dataclass(frozen=True)
class Work:
    role: Role
    slug: str
    text: str
    from_file: bool


@dataclass(frozen=True)
class Line:
    kind: str
    name: str
    said: str

    def __str__(self) -> str:
        return f"{self.kind} {self.name}: {self.said}" if self.said else f"{self.kind} {self.name}"


def work(path: Path | None, text: str) -> Work:
    """The work, with the role that takes it. A file's role follows its directory: `tasks/` is
    a crewmate's and `scouts/` a scout's. Any other file, and text with no file, is the
    home's."""
    if path is None:
        return Work(HOME, "", text, from_file=False)
    return Work(PLACES.get(path.parent.name, HOME), path.stem, text, from_file=True)


def front(text: str) -> dict[str, str]:
    found = _FRONT.match(text)
    pairs = (line.partition(":") for line in (found.group(1) if found else "").splitlines())
    return {key.strip(): value.strip() for key, colon, value in pairs if colon}


def rows(root: Path | None = None) -> list[Row]:
    """Every playbook's `Run by:` row. A path in backticks in the part before `in a brief with`
    is a scope the row is for, and each span after it is a line the row asks the brief for."""
    found = []
    for _, path in sorted(listed("playbook", root).items()):
        by = next((ln[8:] for ln in path.read_text().splitlines() if ln.startswith("Run by: ")), "")
        runner, _, what = by.partition(", for ")
        if not what or "never picked" in what:
            continue
        kind, _, asked = what.partition(" in a brief with ")
        scope = tuple(span for span in _SPAN.findall(kind) if "/" in span or "." in span)
        found.append(Row(path.stem, runner, scope, tuple(_SPAN.findall(asked))))
    return found


def skills(root: Path | None = None) -> dict[str, Skill]:
    found = {}
    at = checkout() if root is None else root
    for _, path in sorted(listed("skill", at).items()):
        fields = front(path.read_text())
        name = fields.get("name") or path.parent.name
        tip = fields.get("tip", "").split("|")
        phrases = tuple(p.strip() for p in tip[1:] if p.strip()) if tip[0].strip() else ()
        found[name] = Skill(name, phrases, path.relative_to(at).as_posix())
    return found


def head(text: str) -> list[str]:
    """The lines of a brief above its first `## `: what the home wrote, with no result."""
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    return lines


def said(lines: list[str], label: str) -> str | None:
    return next((ln.removeprefix(label).strip() for ln in lines if ln.startswith(label)), None)


def _in_scope(path: str, scope: str, root: Path) -> bool:
    """Whether a path that the brief changes is one that a row's scope is for. A directory
    scope covers what is under it. A file name covers that file, and anything under a
    directory whose subdirectories hold such a file, as `skills/` holds a `SKILL.md` in
    each `<name>/`."""
    if scope.endswith("/"):
        return path.startswith(scope) or f"/{scope}" in path
    if path == scope or path.endswith(f"/{scope}"):
        return True
    homes = {f.parent.parent.relative_to(root).as_posix() + "/" for f in root.glob(f"*/*/{scope}")}
    return any(path.startswith(home) for home in homes)


def scoped(lines: list[str]) -> list[str]:
    """The paths that a brief's `Where:` and `Change:` lines name, except tests, which go with
    any kind of change."""
    text = " ".join(ln.split(":", 1)[1] for ln in lines if ln.startswith(_SCOPE_FROM))
    return [p for p in _PATH.findall(text) if not p.startswith((_ALONGSIDE, "~"))]


def at(name: str, root: Path | None = None) -> str:
    """Where the playbook `name` is, from the root of the checkout, as `skills.json` lists it."""
    top = checkout() if root is None else root
    return listed("playbook", top)[name].relative_to(top).as_posix()


def best(lines: list[str], role: Role, found: list[Row], root: Path | None = None) -> Line:
    """The row of the role's runner that fits the brief best. First comes a row whose requested
    lines the brief has, the row with the most of them first. Next comes a row whose scope
    covers every path the brief changes. Last comes the role's own default row."""
    mine = [row for row in found if row.runner == role.runner]
    asked = [
        r for r in mine if r.asks and all(any(ln.startswith(a) for ln in lines) for a in r.asks)
    ]
    if asked:
        row = max(asked, key=lambda r: len(r.asks))
        return Line(
            "playbook", row.name, f"{at(row.name, root)} (the brief has {', '.join(row.asks)})"
        )
    paths = scoped(lines)
    for row in mine:
        if (
            paths
            and row.scope
            and all(any(_in_scope(p, s, root or checkout()) for s in row.scope) for p in paths)
        ):
            return Line(
                "playbook",
                row.name,
                f"{at(row.name, root)} (every path it changes is {' or '.join(row.scope)})",
            )
    if role.default == "none":
        return Line("playbook", "none", f"(no row {role.runner} runs fits)")
    return Line("playbook", role.default, f"{at(role.default, root)} ({role.runner}'s default row)")


def playbook(job: Work, root: Path | None = None) -> Line:
    lines = head(job.text) if job.from_file else []
    named = said(lines, "Playbook:")
    name = named.split()[0] if named else ""
    if name == "none":
        return Line("playbook", "none", "(its Playbook: line)")
    if name and not name.startswith("<"):
        if name in listed("playbook", root):
            return Line("playbook", name, f"{at(name, root)} (its Playbook: line)")
        return Line("unknown", name, "(its Playbook: line names no file in playbooks/)")
    return best(lines, job.role, rows(root), root)


def _words(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9*]+", " ", text.lower()).split())


_ONE_TO_FOUR = "[a-z0-9]+( [a-z0-9]+)?( [a-z0-9]+)?( [a-z0-9]+)?"


def tipped(text: str, found: dict[str, Skill]) -> list[tuple[str, str]]:
    """The skills whose `tip:` phrases the text says, by the rule of
    `features/skill-library/hooks/skill-tips.sh`. A phrase is its words, `*` stands for one
    to four of them, and a phrase matches at the word bounds of the text's words. A skill
    counts by its phrase with the most literal words. A skill that the text names as `/name`
    or `$name` is not tipped. The order is the most words first, then by name."""
    typed = re.sub(r"[^a-z0-9/$_-]+", " ", text.lower())
    named = f" {typed} "
    words = f" {_words(typed)} "
    scored = []
    for skill in found.values():
        if f" /{skill.name} " in named or f" ${skill.name} " in named:
            continue
        most, best_phrase = 0, ""
        for phrase in skill.phrases:
            parts = _words(phrase).split()
            literal = sum(part != "*" for part in parts)
            pattern = "".join(" " + (_ONE_TO_FOUR if p == "*" else re.escape(p)) for p in parts)
            if literal > most and re.search(pattern + " ", words):
                most, best_phrase = literal, phrase
        if most:
            scored.append((-most, skill.name, best_phrase))
    return [(name, phrase) for _, name, phrase in sorted(scored)[:TIPS]]


def named(text: str) -> list[str]:
    """Each name that the text gives as `/name` or as `skills/<name>`, once, in order. A path
    such as `/tmp/x` or `~/.local/state/home` names nothing. A lone `/tmp` reads as a name,
    and `jbriefs pick` prints it as unknown with the rest."""
    seen: dict[str, None] = {}
    for found in sorted(
        [*_SLASH.finditer(text), *_DIRECTORY.finditer(text)], key=lambda m: m.start()
    ):
        seen.setdefault(found.group(1))
    return list(seen)


def _own_text(job: Work) -> str:
    """What the work's author wrote: the head of a brief or a request, with no Result or Review
    under it, and the whole of anything else."""
    return job.text if job.role is HOME else "\n".join(head(job.text))


def _tip_text(job: Work) -> str:
    """The words a tip is read from. For a brief or a request that is its title, task and list
    items, because its own labels and paths would call for skills nobody asked for. For
    anything else it is the whole text."""
    if job.role is HOME:
        return job.text
    return "\n".join(ln for ln in head(job.text) if ln.startswith(_TIPPED_FROM))


def pick(job: Work, root: Path | None = None) -> list[Line]:
    """The lines that `jbriefs pick` prints for a piece of work, each naming a file that
    exists, or `unknown`."""
    found = skills(root)

    def where(name: str) -> str:
        return found[name].path if name in found else f"skills/{name}/SKILL.md"

    role = job.role
    lines = [Line("role", role.skill, f"{role.command(job.slug)} ({where(role.skill)})")]
    lines.append(playbook(job, root))
    tips = tipped(_tip_text(job), found)
    for name, phrase in tips:
        lines.append(Line("tip", name, f'/{name} ({where(name)}), its tip "{phrase}"'))
    given = {role.skill, *(name for name, _ in tips)}
    for name in named(_own_text(job)):
        if name in given:
            continue
        given.add(name)
        if name in found:
            lines.append(Line("named", name, f"/{name} ({where(name)})"))
        else:
            lines.append(Line("unknown", name, f"(no skills/{name}/SKILL.md)"))
    return lines
