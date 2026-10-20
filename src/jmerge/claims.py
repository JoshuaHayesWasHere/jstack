from __future__ import annotations

from dataclasses import dataclass

from jbriefs import parse
from jmerge import ready, sweep

ROOT = "root"
NOBODY = ""
NOT_LAUNCHED = "not launched"
OUT = "out"
NO_WHERE = "no Where line"


@dataclass(frozen=True)
class Claim:
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


def _last_result(text: str) -> list[str]:
    lines = text.splitlines()
    last = [at for at, line in enumerate(lines) if line.startswith("## Result")]
    return lines[last[-1] :] if last else []


def _wider(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in _last_result(text):
        path, _, why = line.removeprefix("Wider:").partition(":")
        path = path.strip().strip("`")
        if line.startswith("Wider:") and path and not path.startswith("<") and why.strip():
            found[path] = why.strip()
    return found


def branch_of(slug: str, text: str) -> tuple[str, str]:
    for line in _last_result(text):
        if line.startswith("Branch:"):
            words = line.removeprefix("Branch:").split()
            pull = next((word for word in words if word.startswith("http")), "")
            return (words[0] if words else slug), pull
    return slug, ""


def stacked_on(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("Stack:"):
            words = line.removeprefix("Stack:").split()
            return words[-1] if len(words) == 4 and words[2] == "on" else ""
    return ""


def scope(text: str, changed: list[str]) -> list[str]:
    inside, wider = parse.where(text), _wider(text)
    return [
        f"wider: {path}: {wider[path]}" if path in wider else f"outside: {path}"
        for path in changed
        if not parse.covers(inside, path)
    ]


def home_of(text: str, homes: dict[str, str]) -> str:
    return homes.get(ready.home_of(text), ROOT)


def of_brief(
    slug: str, text: str, open_pulls: dict[str, int], homes: dict[str, str]
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
