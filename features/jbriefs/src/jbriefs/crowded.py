"""Judge the length of a brief's `Done when:` list: a brief of `CROWDED` items or more is more
than one pull request's worth, and `jbus queue add` warns of it (`jbriefs.parse.warnings`)."""

from __future__ import annotations

from jbriefs.meets import done_when

CROWDED = 5


def crowded(text: str) -> str:
    """Why a brief's `Done when:` list is too long for one pull request, as one line. It is an
    empty string when the list has fewer than `CROWDED` items.

    Every item counts, the check command's too. A brief of 5 or more took a second review round
    about twice as often as one of 1 or 2 (po-briefs-scout, 2026-11-09: 74% of 83 against 38% of
    219), so the line asks for a split, and says not to fold items into fewer lines, which keeps
    the size and hides it from this count.
    """
    count = len(done_when(text.splitlines()))
    if count < CROWDED:
        return ""
    return (
        f"brief's Done when: lists {count} items, and a brief of {CROWDED} or more took a second "
        "review round about twice as often as one of 1 or 2: split the row into briefs of one "
        'pull request\'s worth each, the rest on a brief with a "Follows: <slug>" line or queued '
        "with --depends, and do not fold items into fewer lines"
    )
