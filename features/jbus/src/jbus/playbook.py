"""`jbus playbook <role> <brief>`: open the playbook a brief, a request or a plan names.

This is the one way a thread opens a playbook. The crew, scout, home, expert and pr-review
skills each call it, and none keeps its own block that reads the `Playbook:` line:
`features/repo-guards/tests/test_one_way.py` fails on a skill that carries such a block
again. The playbook's name is the first word of the first `Playbook:` line in the file's head
(`jbriefs.parse.playbook_named`), or the name `--name` gives. A home and an expert get the
name that way, in place of a line.

With the name `none`, or no name, it prints nothing. Otherwise it opens the playbook of that
name that `skills.json` lists in the repo this package is in. The skills are in that repo
too, and it reads that repo also when the work is in another repo (`jbriefs.skills.where`).
For a name `skills.json` does not list, it prints `no playbook: ...`. For a playbook whose
`Run by:` line names a role other than the one asked for, it prints `not <role's>: ...`. For
a playbook of the role, it prints, by role:

- `crewmate` and `scout`: its path; a `has` or `lacks` line for each line its `Run by:`
  asks a brief to have; its numbered steps under a line that names them; a `no principle`
  line for each cited principle `skills.json` does not list; and each principle it
  cites, once and in full, under a line that names them all.
- `home`: its path, and an `asks of its brief:` line for each line its `Run by:` asks.
- `expert`: its path.
- `reviewer`: the lines a reviewer reads of the crewmate's playbook, in place of the path:
  its name, and the first paragraph of each principle it cites. A brief is a crewmate's,
  so the reviewer opens a crewmate's playbook.

`--named` prints the name alone, as the line gives it, and opens nothing.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import jbus
from jbriefs import parse as briefs
from jbriefs import skills
from jbus import verbs

REPO: Path | None = None
ROLES = {
    "crewmate": "a crewmate",
    "scout": "a scout",
    "reviewer": "a crewmate",
    "home": "the home",
    "expert": "an expert",
}
WHOSE = {
    "a crewmate": "a crewmate's",
    "a scout": "a scout's",
    "the home": "the home's",
    "an expert": "an expert's",
}
CITED = re.compile(r"principles/[a-z0-9-]*\.md")
ASKED = re.compile(r"`([^`]*)`")
CHECKLIST = "a checklist to copy into your todo list as printed"
STEP = re.compile(r"^[0-9]+\. ")


def opened(role: str, text: str, name: str = "", repo: Path | None = None) -> list[str]:
    """Return what `jbus playbook` prints for `role`. `text` is the brief, request or plan,
    and `name` is the playbook's name where the caller gives one in place of its line."""
    name = name or briefs.playbook_named(text)
    if name in ("", "none"):
        return []
    path = skills.listed("playbook", repo).get(name)
    if path is None or not path.is_file():
        said = f"no playbook: playbooks/ has no {name}.md"
        return [f"{said}: the crewmate worked with none" if role == "reviewer" else said]
    playbook = path.read_text()
    by = next(
        (line[len("Run by: ") :] for line in playbook.splitlines() if line.startswith("Run by: ")),
        "",
    )
    whose = by.split(",")[0]
    if whose != ROLES[role]:
        said = f"not {WHOSE[ROLES[role]]}: playbooks/{name}.md is for {whose}"
        return [f"{said}: the crewmate worked with none" if role == "reviewer" else said]
    asked = ASKED.findall(by.partition(" in a brief with ")[2])
    cited = list(dict.fromkeys(CITED.findall(playbook)))
    principles = skills.listed("principle", repo)
    found = {one: principles.get(_named(one)) for one in cited}
    if role == "reviewer":
        return _reviewed(name, {one: path for one, path in found.items() if path is not None})
    if role == "expert":
        return [str(path.resolve())]
    if role == "home":
        return [str(path.resolve()), *(f"asks of its brief: {line}" for line in asked)]
    said = [str(path.resolve())]
    lines = text.splitlines()
    for line in asked:
        has = "has" if any(one.startswith(line) for one in lines) else "lacks"
        said.append(f"{has} the line the playbook asks for: {line}")
    steps = [line for line in playbook.splitlines() if STEP.match(line)]
    if steps:
        said.append(f"the steps of playbooks/{name}.md, {CHECKLIST}:")
        said += steps
    there = []
    for one in cited:
        if found[one] is not None:
            there.append(one)
        else:
            said.append(f"no principle: playbooks/{name}.md cites {one}, which is not there")
    if there:
        names = " ".join(_named(one) for one in there)
        said.append(f"the principles playbooks/{name}.md cites, each in full below: {names}")
        for one in there:
            said += ["", f"==> {one} <==", *found[one].read_text().splitlines()]
    return said


def _named(cited: str) -> str:
    """Return the name of the principle a citation names: for `principles/<name>.md`, the
    stub each layout has for the principle, it is `<name>`."""
    return cited.removeprefix("principles/").removesuffix(".md")


def _reviewed(name: str, cited: dict[str, Path]) -> list[str]:
    """Return the reviewer's lines: the playbook's name, and each cited principle's first
    paragraph, joined. That paragraph is the lines after the principle's `# ` title, up to the
    first blank line under them."""
    said = [f"Playbook: {name}, the steps the crewmate worked by."]
    first = []
    for one, path in cited.items():
        lines = path.read_text().splitlines()
        title = next((at for at, line in enumerate(lines) if line.startswith("# ")), None)
        if title is None:
            continue
        paragraph: list[str] = []
        for line in lines[title + 1 :]:
            if line.strip():
                paragraph.append(line)
            elif paragraph:
                break
        if paragraph:
            first.append(f"- {_named(one)}: {' '.join(paragraph)}")
    if first:
        said += ["The principles it cites, and when each applies:", *first]
    return said


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("role", choices=ROLES, help="who opens it")
    parser.add_argument(
        "brief", nargs="?", help="the brief, request or plan whose Playbook: line names it"
    )
    parser.add_argument("--name", default="", help="the playbook's name, in place of the line's")
    parser.add_argument(
        "--named", action="store_true", help="print the name the line gives, and open nothing"
    )


def _run(args: argparse.Namespace, config: jbus.Config | None) -> int:
    text = ""
    if args.brief is not None:
        try:
            text = Path(args.brief).read_text()
        except OSError as error:
            raise jbus.Refused(
                f"no file: {args.brief} could not be read ({error.strerror})"
            ) from None
    elif not args.name:
        raise jbus.Refused("refused: give the brief, request or plan, or --name")
    if args.named:
        named = args.name or briefs.playbook_named(text)
        if named:
            print(named)
        return 0
    for line in opened(args.role, text, args.name, REPO):
        print(line)
    return 0


VERBS = (
    verbs.Verb(
        "playbook",
        "open the playbook a brief, a request or a plan names, for the role that runs it",
        _arguments,
        _run,
        config=False,
    ),
)
