"""The roles of a thread: the start of a thread's title gives it its role (`role_of`).

`jbus.threads` lists the threads with their roles, `jbus.work` names who holds the work of a
role's thread (`work.holder`), and the view shows the roles (`shown`). This module imports nothing
of jbus, so that each of them can import it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

SCOUT = "scout: "
PREFIXES = ("crew: ", "review: ", SCOUT)
OTHER = "other"


@dataclass(frozen=True)
class Role:
    """A `Role` is a kind of thread. The start of a thread's title (`prefix`) gives the thread its
    role, and the other fields say how the view shows the role. `holder` is who holds the work that
    the thread does (`work.holder`), and `holder` also sets the shape that the page draws. `called`
    is the page's name for one thread of the role. `one` and `many` are the words that the threads
    drawer uses to count threads of the role, and `says` describes one thread of the role. The
    drawer lists the roles in the order of `ROLES`."""

    name: str
    prefix: str
    holder: str
    called: str
    one: str
    many: str
    says: str


ROLES = (
    Role(
        "crew",
        "crew: ",
        "crew",
        "crewmate",
        "crew",
        "crews",
        "The thread that does a task's one brief, in its own worktree: it writes the Result "
        "and handles the findings.",
    ),
    Role(
        "scout",
        SCOUT,
        "scout",
        "scout",
        "scout",
        "scouts",
        "A thread that researches one request, read-only, and writes its Report under it: it "
        "changes nothing in the repo.",
    ),
    Role(
        "reviewer",
        "review: ",
        "rev",
        "reviewer",
        "reviewer",
        "reviewers",
        "A fresh thread that reads a task's pull request and writes its findings in the brief.",
    ),
    Role(
        "home",
        "home: ",
        "home",
        "home",
        "home",
        "homes",
        "The thread that plans the project's work and hands each task to a crewmate.",
    ),
    Role(
        OTHER,
        "",
        "other",
        "other thread",
        "other thread",
        "other threads",
        "A thread whose title names no role, so what it works on is not known.",
    ),
)
SECOND = ", second pass"
SCOPED = ", scoped"
_SEAT = re.compile(r", [0-9]+$")


def slug_in(title: str, prefix: str) -> str | None:
    if not title.startswith(prefix):
        return None
    slug = title.removeprefix(prefix).removesuffix(SECOND).removesuffix(SCOPED).strip()
    return _SEAT.sub("", slug)


def shown() -> list[dict[str, str]]:
    """Return the roles as the page has them, in the order of `ROLES`."""
    return [asdict(role) for role in ROLES]


def role_of(title: str) -> tuple[str, str]:
    """Return the role and the slug that a thread's title gives. A title that starts with none of
    the prefixes of `ROLES` gives `OTHER` and no slug."""
    for role in ROLES:
        slug = slug_in(title, role.prefix) if role.prefix else None
        if slug is not None:
            return role.name, slug
    return OTHER, ""
