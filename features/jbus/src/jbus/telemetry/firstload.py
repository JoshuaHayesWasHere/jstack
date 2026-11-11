"""The crew's first load: the bytes of jstack's own text a crew reads before its work, as
installed, kept as a record each time the installed files change.

A crew launched as `/crew <slug>` reads two things of jstack's before its first task call: the
crew skill's `SKILL.md`, which the slash command expands, and what `jbus playbook crewmate`
prints for its brief's playbook. The trimmed `SKILL.md` reads no other file before the task. So
the first load is `SKILL.md` and one playbook print. The print depends on the brief, so the
record counts each crewmate playbook's print, and its `bytes` is `SKILL.md` and the largest
print: no crew's first load of jstack's own is larger. A brief with no playbook reads less.

What the harness wraps around the expansion, the line that names the skill's directory and the
command message, is the harness's and not counted: the crew-scout-router report's `today.py`
adds 1.4 KB for it. Neither is the brief, nor the `jbriefs --skills` print, which is the brief's.

The installed files are those of the jstack source this jbus runs from (`jbriefs.skills.root`),
which is the tree each harness's install links its skills to. `hash` is the sha256 of every
counted text, by name, so it is the install's: a change to `SKILL.md`, to a playbook, or to where
the install is, which a print names, gives a new hash. A build keeps a record when the hash is not
the one of the latest record, and only then, so a store holds one record for each install it
saw, in order, and an install that comes back after another is a record again.

`starts` counts the same for each role, crew, reviewer, scout and home, against a budget in
tokens: the files the role's start reads (`ROLES`), the largest print of `jbus playbook` for
the role, and the skill listing a session is given, rebuilt from `skills.json`.
`python -m jbus.telemetry.firstload --check`, which `make lint` runs, fails a role over its
`BUDGET`, a budget more than 10% above its role's count, and a start file that is not there.
The budget covers jstack's text only: the harness's system prompt and tool schemas, the user's
own instructions file and the brief are not this repo's to bound.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from pathlib import Path

from jbriefs import skills
from jbus import playbook
from jbus.telemetry import values

TABLE = "first_loads"
TABLE_SQL = (
    f"CREATE TABLE {TABLE} (project TEXT NOT NULL, key TEXT NOT NULL, at TEXT, hash TEXT, "
    "bytes INTEGER, skill_bytes INTEGER, playbook TEXT, playbook_bytes INTEGER, files TEXT, "
    f"day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    f"CREATE INDEX {TABLE}_at ON {TABLE} (at);\n"
)
"""One row for each install a build saw, the machine's, keyed by its time and hash. `files` is
a JSON object of the bytes of each text counted, by its name: `features/crew/SKILL.md`, and
`jbus playbook crewmate --name <name>` for each playbook's print."""

REPO: Path | None = None
"""The jstack source whose installed files are counted, `jbriefs.skills.root()` when None."""


@dataclass(frozen=True)
class FirstLoad:
    """An install's crew first load: `bytes`, the skill and the largest print, and every text
    counted, by name."""

    hash: str
    bytes: int
    skill_bytes: int
    playbook: str
    playbook_bytes: int
    files: dict[str, int]


def _print(name: str, repo: Path) -> bytes | None:
    """What `jbus playbook crewmate --name <name>` prints, or None for a playbook that is not
    a crewmate's."""
    lines = playbook.opened("crewmate", "", name, repo)
    if not lines or not Path(lines[0]).is_absolute():
        return None
    return ("\n".join(lines) + "\n").encode()


def measure(repo: Path | None = None) -> FirstLoad:
    """Count the crew first load of the install at `repo`, `REPO` by default."""
    repo = repo or REPO or skills.root()
    skill = skills.where("skill", "crew", repo)
    texts = {str(skill.relative_to(repo)): skill.read_bytes()}
    prints = {}
    for name in sorted(skills.listed("playbook", repo)):
        said = _print(name, repo)
        if said is not None:
            prints[f"jbus playbook crewmate --name {name}"] = (name, said)
    texts.update((label, said) for label, (_, said) in prints.items())
    digest = hashlib.sha256()
    for label, text in texts.items():
        digest.update(f"{label}\0{len(text)}\0".encode())
        digest.update(text)
    largest, said = max(prints.values(), key=lambda one: (len(one[1]), one[0]), default=("", b""))
    skill_bytes = len(texts[str(skill.relative_to(repo))])
    return FirstLoad(
        digest.hexdigest(),
        skill_bytes + len(said),
        skill_bytes,
        largest,
        len(said),
        {label: len(text) for label, text in texts.items()},
    )


def keep(connection: sqlite3.Connection, zone: tzinfo | None) -> int:
    """Keep a record of the install's first load where its hash is not the latest record's, and
    return how many rows that wrote. An install with no crew skill or no `skills.json` keeps
    nothing."""
    try:
        found = measure()
    except (LookupError, OSError, ValueError):
        return 0
    latest = connection.execute(
        f"SELECT hash FROM {TABLE} WHERE project = ? ORDER BY at DESC, key DESC LIMIT 1",
        (values.MACHINE,),
    ).fetchone()
    if latest and latest[0] == found.hash:
        return 0
    at = values.utc(datetime.now(UTC).isoformat())
    connection.execute(
        f"INSERT OR IGNORE INTO {TABLE} (project, key, at, hash, bytes, skill_bytes, playbook, "
        "playbook_bytes, files, day) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            values.MACHINE,
            f"{at} {found.hash}",
            at,
            found.hash,
            found.bytes,
            found.skill_bytes,
            found.playbook,
            found.playbook_bytes,
            json.dumps(found.files, sort_keys=True),
            values.day(at, zone),
        ),
    )
    return 1


ROLES = {
    "crew": ("crewmate", ("features/crew/SKILL.md",)),
    "reviewer": ("reviewer", ("features/pr-review/SKILL.md", "features/pr-review/the-review.md")),
    "scout": ("scout", ("features/scout/SKILL.md",)),
    "home": (
        "home",
        tuple(
            f"features/home/skills/home/{name}.md"
            for name in (
                "SKILL",
                "when-a-home-starts",
                "clearing-its-own-blockers",
                "gates",
                "merging-a-pull-request-that-is-ready",
            )
        ),
    ),
}
"""Each role's `jbus playbook` role and the files its start reads before its first act: the
skill the slash command expands and the files it reads at every start, by the paths each role
named in the first tool calls of its sessions."""

BUDGET = {
    "crew": 10_600,
    "reviewer": 20_000,
    "scout": 9_500,
    "home": 35_000,
}
"""The most tokens of jstack's own text each role may start with. It is raised on purpose, by a
pull request that edits this table, and lowered when a cut leaves more than `SLACK` above the
count."""

CHARACTERS = (29, 10)
"""A token is 2.9 characters, as numerator and denominator: the first calls the store measured
since 2026-11-08 hold 2.90 to 2.95 characters a token, by role."""

SLACK = (11, 10)
"""How far above a role's count its budget may be, 10%, so a cut lowers the budget with it."""

INSTALL = "/home/user/.local/share/jstack/green.d/" + "0" * 40
"""The root a print's paths are counted at: an install's, the same on every machine, in place
of the checkout's, which is as long as the path the checkout happens to sit at."""


@dataclass(frozen=True)
class Start:
    """A role's start: the characters of each text counted, by name, and the start files that
    are not there."""

    role: str
    texts: dict[str, int]
    missing: tuple[str, ...]

    @property
    def characters(self) -> int:
        return sum(self.texts.values())

    @property
    def tokens(self) -> int:
        per, by = CHARACTERS
        return -(-self.characters * by // per)


def _head(path: Path) -> dict[str, str]:
    """The flat front matter of a `SKILL.md`, its keys and their values unquoted: none for a file
    that does not open with `---`."""
    text = path.read_text()
    front = text[4:].partition("\n---")[0] if text.startswith("---\n") else ""
    pairs = (line.partition(":") for line in front.splitlines() if not line.startswith(" "))
    return {key: value.strip().strip("\"'") for key, colon, value in pairs if colon}


def listing(repo: Path) -> str:
    """The skill listing a session of this repo is given: `- name: description` for each skill
    and principle of `skills.json` a model may load by itself, and each of this repo's own,
    less those whose front matter lists `paths:`, which are listed only once a matching file is
    read."""
    catalog = json.loads((repo / skills.CATALOG).read_text())
    found = [
        (item["name"], item["description"], repo / item["path"])
        for item in catalog["items"]
        if item["kind"] in skills.NAMEABLE and not item.get("hidden")
    ]
    for own in catalog.get("projectSkills", []):
        path = repo / own["path"] / "SKILL.md"
        found.append((own["name"], _head(path).get("description", ""), path))
    return "".join(
        f"- {name}: {description}\n"
        for name, description, path in found
        if "paths" not in _head(path)
    )


def _printed(role: str, name: str, repo: Path) -> str | None:
    """What `jbus playbook <role> --name <name>` prints, at `INSTALL`, or None where it opens
    no playbook of the role's."""
    lines = playbook.opened(role, "", name, repo)
    opens = lines and (
        lines[0].startswith("Playbook: ") if role == "reviewer" else lines[0][:1] == "/"
    )
    if not opens:
        return None
    return ("\n".join(lines) + "\n").replace(str(repo.resolve()), INSTALL)


def starts(repo: Path | None = None) -> dict[str, Start]:
    """Count each role's start of jstack's own text: its start files, the largest playbook print
    it can get, and the skill listing."""
    repo = repo or REPO or skills.root()
    shown = listing(repo)
    names = sorted(skills.listed("playbook", repo))
    counted = {}
    for role, (asks, files) in ROLES.items():
        texts = {name: len((repo / name).read_text()) for name in files if (repo / name).is_file()}
        prints = {
            name: len(said) for name in names if (said := _printed(asks, name, repo)) is not None
        }
        if prints:
            largest = max(prints, key=lambda name: (prints[name], name))
            texts[f"jbus playbook {asks} --name {largest}"] = prints[largest]
        texts["the skill listing"] = len(shown)
        counted[role] = Start(role, texts, tuple(name for name in files if name not in texts))
    return counted


def _line(role: str) -> str:
    """Where `BUDGET` gives `role` its number, as `path:line`."""
    table = next(
        node.value
        for node in ast.parse(Path(__file__).read_text()).body
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "BUDGET"
    )
    assert isinstance(table, ast.Dict)
    key = next(key for key in table.keys if isinstance(key, ast.Constant) and key.value == role)
    return f"features/jbus/src/jbus/telemetry/firstload.py:{key.lineno}"


def faults(counted: dict[str, Start]) -> list[str]:
    """What fails the check: a start file that is not there, a role over its budget, and a
    budget more than `SLACK` above its role's count."""
    per, by = CHARACTERS
    over, under = SLACK
    said = []
    for role, start in counted.items():
        budget, at = BUDGET[role], _line(role)
        said += (
            f"{role}: {name} is not there: count it under its new name in ROLES"
            for name in start.missing
        )
        if start.characters * by > budget * per:
            said.append(
                f"{role}: {start.tokens} tokens, over its budget of {budget}: cut its start, "
                f"or raise its budget at {at} in a pull request that says why"
            )
        elif budget * per * under > start.characters * by * over:
            said.append(
                f"{role}: {start.tokens} tokens, its budget of {budget} is more than 10% above: "
                f"lower it at {at}"
            )
    return said


def main(argv: list[str] | None = None) -> int:
    """Print each role's start against its budget; with `--check`, fail on a fault."""
    parser = argparse.ArgumentParser(
        prog="python -m jbus.telemetry.firstload",
        description="count each role's start of jstack's own text against its budget",
    )
    parser.add_argument("--check", action="store_true", help="exit 1 on a fault")
    args = parser.parse_args(argv)
    counted = starts()
    for role, start in counted.items():
        print(
            f"{role}: {start.characters} characters, {start.tokens} tokens, budget {BUDGET[role]}"
        )
    found = faults(counted)
    for line in found:
        print(f"fault: {line}")
    return 1 if args.check and found else 0


if __name__ == "__main__":
    raise SystemExit(main())
