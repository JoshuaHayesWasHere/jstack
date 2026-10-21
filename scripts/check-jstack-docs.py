"""Check what README.md, the docs and the skills say about the tree: `check-jstack-docs.py [root]`.

A stdlib port of pstack's check-pstack-docs.mjs, run by `make check` and `make check-fast`. It
reads the tree once and holds each page to it:

- slash commands: `/<name>`, in prose or as the first word of a code span or of a line of a
  fenced block, or "the `<name>` skill", is a skill under `skills/` or in `EXTERNAL`.
- paths: a path that starts at a folder of `ROOTS` (`skills/<n>/SKILL.md`, `templates/gates.md`)
  exists. One with a placeholder, a glob, or a `/` before it is somewhere else and not read.
  A skill is read from its layout, so it may also name a playbook or a skill's file where the
  layout puts it (`playbooks/<p>.md`, `skills/<n>/<file>`), once a move took it out of there.
- links and anchors: a relative Markdown link outside code points at a file that exists and, with
  a `#anchor` into a Markdown file, at a heading of it as GitHub slugs it (fences skipped, `-N`
  for repeats).
- counts: "has 39 skills" and the like, in the README or a docs page, is the number of skills,
  commands, principles or playbooks the tree has. A skill counts things of its own: not read.
- models: every `claude-<family>-N-N` id in the README or a docs page is in the `## Models` table
  of `features/jroles/docs/jroles.md`.
- tables: a row of a README table names each command, and a page of the docs links each skill's
  `SKILL.md` and each playbook (the generated catalog of `docs/playbooks.md` does).

It prints `FAIL <doc>:<line> <why>` for each problem, then `<n> problems`, and exits 1 on any.
A thing no page lists is reported at `README.md:1`.
"""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parent.parent

# Slash words that are no skill of this tree, each with the reason.
EXTERNAL = {
    "clear": "a Claude Code command",
    "loop": "a Claude Code command",
    "code-review": "a Claude Code command",
    "simplify": "a Claude Code command",
    "init": "a Claude Code command",
    "answer": "a reply to an item jbus asked about, in a webhook's reply",
    "ack": "the relay's route that takes an acknowledgement",
    "steer": "the view's route that takes a steer",
    "tmp": "the machine's temporary folder",
    "proc": "the machine's process folder",
}
PROSE_SLASH = re.compile(r"(?<![\w/.~<>$-])/([a-z][a-z0-9-]*)(?![\w/-]|\.\w)")
NAMED_SKILL = re.compile(r"`([a-z][a-z0-9-]*)` skills?\b|\bskills? `([a-z][a-z0-9-]*)`")
PRINCIPLE = "principle-"
ROOTS = ("skills", "templates", "playbooks", "principles", "hooks", "docs")
TREE_PATH = re.compile(rf"(?<![\w/.~<>*$-])((?:{'|'.join(ROOTS)})/[\w.-]+(?:/[\w.-]+)*)")
LINK = re.compile(r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)")
SCHEME = re.compile(r"([a-z][a-z0-9+.-]*:|//)", re.I)
HEADING = re.compile(r"#{1,6}\s+(.*?)\s*#*\s*$")
MODEL = re.compile(r"\bclaude-[a-z]+-\d+(?:-\d+)*\b")
JROLES = "features/jroles/docs/jroles.md"
NUMBERS = (
    "zero one two three four five six seven eight nine ten "
    "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
).split()
HAS = r"(?:has|have|holds?|lists?|contains?|ships|are|is)"
NOUNS = ("skills", "commands", "principles", "playbooks")
COUNT = {
    noun: re.compile(rf"\b{HAS} (?:the |all )?(\d+|{'|'.join(NUMBERS)}) {noun}\b", re.I)
    for noun in NOUNS
}


@dataclass(frozen=True)
class Line:
    number: int
    text: str
    fenced: bool | None  # None for a fence's own line

    @property
    def prose(self) -> str:
        """The line with its inline code spans blanked, so a link in a span is not a link."""
        return re.sub(r"`[^`\n]*`", lambda span: " " * len(span[0]), self.text)


@dataclass(frozen=True)
class Doc:
    path: Path
    name: str
    lines: tuple[Line, ...]

    @property
    def is_skill(self) -> bool:
        return self.path.name == "SKILL.md"

    @classmethod
    def read(cls, root: Path, path: Path) -> Doc:
        return cls(path, path.relative_to(root).as_posix(), lines_of(path.read_text()))


def lines_of(text: str) -> tuple[Line, ...]:
    found, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(("```", "~~~")):
            fenced = not fenced
            found.append(Line(number, line, None))
        else:
            found.append(Line(number, line, fenced))
    return tuple(found)


def slug_of(heading: str) -> str:
    """The anchor GitHub gives a heading: no markup, lower case, no punctuation, `-` for space."""
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"[`*]", "", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")


def anchors_of(text: str) -> set[str]:
    """A Markdown text's anchors: its headings outside fences, repeats numbered, its ids."""
    seen: dict[str, int] = {}
    found = set()
    for line in lines_of(text):
        heading = HEADING.match(line.text)
        if heading and line.fenced is False:
            slug = slug_of(heading[1])
            found.add(slug if slug not in seen else f"{slug}-{seen[slug]}")
            seen[slug] = seen.get(slug, 0) + 1
    return found | set(re.findall(r"""\b(?:id|name)=["']([^"']+)["']""", text))


@dataclass(frozen=True)
class Tree:
    root: Path
    skills: frozenset[str]
    playbooks: tuple[str, ...]
    commands: tuple[str, ...]
    principles: frozenset[str]
    models: frozenset[str]

    @classmethod
    def read(cls, root: Path) -> Tree:
        scripts = tomllib.loads((root / "pyproject.toml").read_text())["project"]["scripts"]
        return cls(
            root,
            frozenset(path.parent.name for path in skill_files(root)),
            tuple(sorted(path.stem for path in playbook_files(root))),
            tuple(sorted(scripts)),
            frozenset(path.parent.name for path in principle_files(root)),
            models_of(root / JROLES),
        )

    def principle(self, path: str) -> bool:
        """Whether `path` is `principles/<name>.md` for a principle: the stub each layout
        holds where the principle is read, which the source tree does not have."""
        name = path.removeprefix("principles/").removesuffix(".md")
        return path == f"principles/{name}.md" and name in self.principles

    def laid(self, path: str) -> bool:
        """Whether `path` is where each layout puts a playbook, `playbooks/<name>.md`, or a file
        of a skill, `skills/<name>/<file>`, which a move into its feature takes out of the
        source tree."""
        kind, _, rest = path.partition("/")
        if kind == "playbooks":
            return "/" not in rest and rest.removesuffix(".md") in self.playbooks
        name, _, file = rest.partition("/")
        return (
            kind == "skills"
            and name in self.skills
            and any(
                (at.parent / file).is_file()
                for at in skill_files(self.root)
                if at.parent.name == name
            )
        )

    def count(self, noun: str) -> int:
        return {
            "skills": len(self.skills),
            "commands": len(self.commands),
            "principles": len(self.principles),
            "playbooks": len(self.playbooks),
        }[noun]


def models_of(page: Path) -> frozenset[str]:
    """The model ids of the `## Models` table of jroles' page: its rows' first cells."""
    if not page.exists():
        return frozenset()
    found, inside = set(), False
    for line in lines_of(page.read_text()):
        if HEADING.match(line.text):
            inside = line.text.lstrip("#").strip() == "Models"
        elif inside and line.text.startswith("|"):
            found |= set(MODEL.findall(line.text.split("|")[1]))
    return frozenset(found)


def skill_files(root: Path) -> list[Path]:
    """Each skill's `SKILL.md`, where it is now and where a move puts it: a principle is not
    one of them."""
    spots = ("skills/*/SKILL.md", "features/*/SKILL.md", "features/*/skills/*/SKILL.md")
    found = (path for spot in spots for path in root.glob(spot))
    return sorted(path for path in found if not path.parent.name.startswith(PRINCIPLE))


def principle_files(root: Path) -> list[Path]:
    """Each principle's `SKILL.md`: a skill whose name has the prefix `principle-`."""
    return sorted(root.glob(f"features/*/skills/{PRINCIPLE}*/SKILL.md"))


def playbook_files(root: Path) -> list[Path]:
    """Each playbook, where it is now and where a move puts it, under the skill that runs it."""
    spots = ("playbooks/*.md", "features/*/playbooks/*.md", "features/*/skills/*/playbooks/*.md")
    return sorted(path for spot in spots for path in root.glob(spot))


def docs_of(root: Path) -> list[Doc]:
    """The README, every page of the docs tree, and each skill's `SKILL.md`, in that order."""
    pages = [
        root / "README.md",
        *sorted((root / "docs").rglob("*.md")),
        *sorted(root.glob("features/*/docs/**/*.md")),
        *skill_files(root),
    ]
    return [Doc.read(root, page) for page in pages]


Found = list[tuple[int, str]]


def links(tree: Tree, doc: Doc) -> Found:
    found = []
    for line in doc.lines:
        if line.fenced is not False:
            continue
        for target in LINK.findall(line.prose):
            if SCHEME.match(target):
                continue
            path, _, anchor = unquote(target).partition("#")
            at = (doc.path.parent / path) if path else doc.path
            if not at.exists():
                found.append((line.number, f"the link {target} goes to a file that is not there"))
            elif anchor and at.suffix == ".md" and anchor not in anchors_of(at.read_text()):
                why = f"the link {target} goes to a heading that is not there"
                found.append((line.number, why))
    return found


def slash_commands(tree: Tree, doc: Doc) -> Found:
    known = tree.skills | set(EXTERNAL)
    found = []
    for line in doc.lines:
        names = []
        if line.fenced:
            names += code_words([line.text.strip()])
        elif line.fenced is False:
            names += code_words(re.findall(r"`([^`\n]+)`", line.text))
            names += PROSE_SLASH.findall(line.prose)
        found += [
            (line.number, f"/{name} is named as a skill and skills/ has no {name}")
            for name in names
            if name not in known
        ]
        if line.fenced is False:
            for pair in NAMED_SKILL.findall(line.text):
                name = pair[0] or pair[1]
                if name not in tree.skills:
                    why = f"{name} is named as a skill and skills/ has no {name}"
                    found.append((line.number, why))
    return found


def code_words(pieces: list[str]) -> list[str]:
    """The skill a piece of code types as its first word, `/<name>`."""
    words = [piece.split()[0] for piece in pieces if piece.split()]
    return [word[1:] for word in words if re.fullmatch(r"/[a-z][a-z0-9-]*", word)]


def paths(tree: Tree, doc: Doc) -> Found:
    found = []
    for line in doc.lines:
        for path in TREE_PATH.findall(re.sub(r"\]\([^)]*\)", "]", line.text)):
            path = path.rstrip(".,:;")
            there = (tree.root / path).exists() or tree.principle(path)
            if not there and not (doc.is_skill and tree.laid(path)):
                why = f"{path} is named and the tree has no such path"
                found.append((line.number, why))
    return found


def counts(tree: Tree, doc: Doc) -> Found:
    if doc.is_skill:
        return []
    found = []
    for line in doc.lines:
        for noun, pattern in COUNT.items():
            for said in pattern.findall(line.text):
                said = int(said) if said.isdigit() else NUMBERS.index(said.lower())
                if said != tree.count(noun):
                    why = f"it counts {said} {noun} and the tree has {tree.count(noun)}"
                    found.append((line.number, why))
    return found


def models(tree: Tree, doc: Doc) -> Found:
    if doc.is_skill:
        return []
    return [
        (line.number, f"the model {model} is not in the Models table of {JROLES}")
        for line in doc.lines
        for model in MODEL.findall(line.text)
        if model not in tree.models
    ]


CHECKS = (links, slash_commands, paths, counts, models)


def listing(tree: Tree, docs: list[Doc]) -> list[str]:
    """What no table of the README or link of the docs lists: each a why for `README.md:1`."""
    readme = next(doc for doc in docs if doc.name == "README.md")
    rows = " ".join(line.text for line in readme.lines if line.text.startswith("|"))
    linked = {
        (doc.path.parent / unquote(target).partition("#")[0]).resolve()
        for doc in docs
        if not doc.is_skill
        for line in doc.lines
        if line.fenced is False
        for target in LINK.findall(line.prose)
        if not SCHEME.match(target)
    }
    wanted = [path.relative_to(tree.root).as_posix() for path in playbook_files(tree.root)]
    wanted += [path.relative_to(tree.root).as_posix() for path in skill_files(tree.root)]
    return [
        f"no table row of the README names the command {name}"
        for name in tree.commands
        if f"`{name}`" not in rows
    ] + [
        f"no page of the docs links {path}"
        for path in wanted
        if (tree.root / path).resolve() not in linked
    ]


def problems(root: Path) -> list[str]:
    tree, docs = Tree.read(root), docs_of(root)
    found = [f"README.md:1 {why}" for why in listing(tree, docs)]
    for doc in docs:
        said = sorted(
            ((number, why) for check in CHECKS for number, why in check(tree, doc)),
            key=lambda pair: pair[0],
        )
        found += [f"{doc.name}:{number} {why}" for number, why in said]
    return found


def main(argv: list[str]) -> int:
    found = problems(Path(argv[0]).resolve() if argv else REPO)
    for problem in found:
        print(f"FAIL {problem}")
    print(f"{len(found)} problems")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
