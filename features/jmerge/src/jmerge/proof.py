from __future__ import annotations

import re

_PROOF = re.compile(r"(?:^|\s)Proof:[ \t]*(.*)$")
_CODE = r"exit[ \t]+(\d+)"
_EXIT = re.compile(rf",[ \t]*{_CODE}(?P<ends>[ \t]*(?=,|$)|(?=[:.](?!\d)))?")
_SAID = re.compile(rf"\b{_CODE}", re.IGNORECASE)


def _reviews(text: str) -> list[tuple[str, str]]:
    found: list[list[str]] = []
    review = False
    for line in text.splitlines():
        if line.startswith("## "):
            review = line == "## Review"
            if review:
                found.append(["", ""])
        elif not review or line.startswith("- "):
            continue
        elif line.startswith("Head:"):
            found[-1][0] = "".join(line.split()[1:2])
        elif not found[-1][1] and _PROOF.search(line):
            found[-1][1] = _PROOF.search(line)[1].strip()
    return [(head, said) for head, said in found]


def last(text: str) -> str:
    """The head of the last review that names one."""
    return next((head for head, _ in reversed(_reviews(text)) if head), "")


def fact(text: str, head: str) -> tuple[str, str] | None:
    said = next((said for at, said in reversed(_reviews(text)) if head and at == head), "")
    ended = [m for m in _EXIT.finditer(said) if m["ends"] is not None]
    failed = any(m[1] != "0" for m in _SAID.finditer(said))
    if said.lower().startswith("unproven") or not ended or failed:
        return None
    command = said[: ended[0].start()].strip().strip("`").strip()
    if not command:
        return None
    return said[ended[-1].end() + 1 :].strip() or command, command


def short(text: str, head: str) -> str:
    if fact(text, head):
        return ""
    return f"no proven safety fact at {head[:12]} (blast-radius, review step 5)"
