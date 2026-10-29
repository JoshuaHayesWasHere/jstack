from __future__ import annotations

from dataclasses import dataclass

from jbriefs import below, home, parse
from jmerge import sweep

ROOT = "root"
NOBODY = ""
NOT_LAUNCHED = "not launched"
OUT = "out"
NO_WHERE = "no Where line"


@dataclass(frozen=True)
class Claim:
    """A brief that still holds files."""

    slug: str
    state: str
    home: str
    where: str

    def line(self) -> str:
        return f"{self.slug} {self.state} {self.home} {self.where}"


def _where(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Where:"):
            return line.strip()
    return NO_WHERE


def branch_of(slug: str, text: str) -> tuple[str, str]:
    for line in below.last(text, "## Result") or []:
        if line.startswith("Branch:"):
            words = line.removeprefix("Branch:").split()
            pull = next((word for word in words if word.startswith("http")), "")
            return (words[0] if words else slug), pull
    return slug, ""


def scope(text: str, changed: list[str]) -> list[str]:
    inside = parse.where(text)
    return [f"outside: {path}" for path in changed if not parse.covers(inside, path)]


def home_of(text: str, homes: dict[str, str]) -> str:
    return homes.get(home.named(text), ROOT)


def of_brief(
    slug: str,
    text: str,
    open_pulls: dict[str, int],
    homes: dict[str, str],
) -> Claim | None:
    record = sweep.of_brief(slug, text)
    if not any(line.startswith("## Result") for line in text.splitlines()):
        state = OUT if record.thread else NOT_LAUNCHED
    elif record.pull in open_pulls:
        state = f"pull request {open_pulls[record.pull]}"
        if record.paused:
            state = f"{sweep.PAUSED} {state}"
    elif record.paused and not record.pull:
        state = sweep.PAUSED
    else:
        return None
    return Claim(slug, state, home_of(text, homes), _where(text))
