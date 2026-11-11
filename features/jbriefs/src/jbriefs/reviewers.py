"""Whom a brief's review waits on: the reviewer lines a crew and jbus write below its first
`## Result`, `Reviewer:`, `Second reviewer:` and `Scoped reviewer:`, read against the `## Review`
sections written after them. jbus waits on `running` before it moves a head, and the crew's
blocks ask it through `jbriefs line reviewing`, so both act on one answer."""

from __future__ import annotations

import re

from jbriefs import below, findings

_SEAT = re.compile(r"\s#(\d+)$")


def launched(text: str) -> int:
    """How many reviewer lines of the brief's results name a reviewer that was launched: a
    `Reviewer:`, `Second reviewer:` or `Scoped reviewer:` line that does not say `none`."""
    said = (one for kind in below.REVIEWERS for one in below.reviewers(text, kind))
    return sum(map(below.launched, said))


def reviewed(text: str) -> bool:
    """Whether the brief's results hold a review or a reviewer: a `## Review` section, or a
    reviewer line that names one (`launched`). A `Reviewer: none, <why>` line is no reviewer,
    and a `Reviewer:` line in the head is the home's guidance for one."""
    return "## Review" in below.results(text) or launched(text) > 0


def running(text: str) -> bool:
    """Whether a reviewer launched on the brief has not written its section yet, so a rebase or
    a move of its head would go from under it. Each reviewer line waits for a section with a
    `Head:` line written after it: a numbered line (`#<n>`, a `Reviewer:` or a
    `Second reviewer:`) for a section of its seat that is not scoped, a `Scoped reviewer:` line
    for a scoped section, and an unnumbered line for any other section. A seat launched again
    after its section waits for a new one, and launched again before it waits for one. Once a
    `Reviewer:` line has a number, the unnumbered `Reviewer:` lines are a launch that the
    numbered ones replaced (`Numbered`), and wait for nothing. In a brief with no numbered
    `Reviewer:` line (`Legacy`) every line, a scoped one too, waits for any later section."""
    lines = text.splitlines()
    first = next((at for at, one in enumerate(lines) if one.startswith("## Result")), len(lines))
    events: list[tuple[int, str, int | None]] = []
    numbered = False
    for at, line in enumerate(lines[first:], first):
        kind, _, said = line.partition(": ")
        if kind in below.REVIEWERS and below.launched(said.strip()):
            found = _SEAT.search(said.rstrip())
            seat = int(found[1]) if found and kind != "Scoped reviewer" else None
            numbered = numbered or (kind == "Reviewer" and seat is not None)
            events.append((at, kind, seat))
    events.extend(
        (one.line, "scoped" if one.scoped else "section", one.seat)
        for one in findings.sections(text)
        if one.head
    )
    seats: set[int] = set()
    plain = scoped = 0
    for _, said, seat in sorted(events, key=lambda event: event[0]):
        kind = (
            said
            if numbered
            else {"Scoped reviewer": "Reviewer", "scoped": "section"}.get(said, said)
        )
        if kind == "Scoped reviewer":
            scoped += 1
        elif kind == "scoped":
            scoped = max(0, scoped - 1)
        elif kind == "section":
            if seat in seats:
                seats.discard(seat)
            elif plain:
                plain -= 1
        elif seat is not None:
            seats.add(seat)
        elif not (kind == "Reviewer" and numbered):
            plain += 1
    return bool(seats or plain or scoped)
