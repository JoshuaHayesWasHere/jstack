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
"""

from __future__ import annotations

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
