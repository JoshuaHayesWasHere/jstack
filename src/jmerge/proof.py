"""The one fact a change is safe because of, as its review proved it by running code.

The review's step 5 (blast-radius) runs one command at the head it reviews, and writes what
ran on the `Proof:` line of its `## Review` section: the command, `exit <code>`, and the last
line or two it printed, with a comma between them. The reviewer writes the line by hand, so
an exit code is read whether a comma, a colon, a full stop or the end of the line follows.
A fact it could not prove is written `Proof: unproven, <the fact>`.

A proof is of the commit it ran at and of no other: the section's `Head:` line. So here a
fact is proven at a head only by a review of that head, and a push since leaves none. The
one carry is `jmerge`'s, not this module's: over a rebase, or a push for a failed check,
that it compared by range-diff and found to leave the content as it was, it asks for the
proof at the commit the review saw.
The gate reads the line the skill leaves, not whether the skill was run.
"""

from __future__ import annotations

import re

_PROOF = re.compile(r"(?:^|\s)Proof:[ \t]*(.*)$")
_CODE = r"exit[ \t]+(\d+)"
_EXIT = re.compile(rf",[ \t]*{_CODE}(?P<ends>[ \t]*(?=,|$)|(?=[:.](?!\d)))?")
_SAID = re.compile(rf"\b{_CODE}", re.IGNORECASE)


def _reviews(text: str) -> list[tuple[str, str]]:
    """The head and the proof of each `## Review` section, in the order they were written."""
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


def fact(text: str, head: str) -> tuple[str, str] | None:
    """(fact, command) from the Proof: line of the review that covers head, or None when
    there is none, it is of an older head, or it says unproven.

    The review that covers a head is the last one written of it. Its proof stands when the
    command ran and ended with `exit 0`: one that failed found the fact false, and one with
    no exit code did not say. A line with two exit codes is proven only when both are 0:
    which one is the command's cannot be told. So an exit code that is not 0 refuses the
    line wherever it stands in it, in the command and the fact too, and in any case of its
    letters. A 0 counts only after a comma, and before a comma, a colon, a full stop or the
    end of the line. Any run of spaces and tabs may stand between `exit` and the code, in
    both readings. The fact is what the command printed last, which is all the line holds
    of it, or the command where it printed nothing.
    """
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
    """Why the pull request has no proven safety fact at its head, or nothing."""
    if fact(text, head):
        return ""
    return f"no proven safety fact at {head[:12]} (blast-radius, review step 5)"
