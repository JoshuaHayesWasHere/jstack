"""The home a launched row belongs to: the `Home:` line a launch writes in the row's copy under
`tasks/` (`homed`), and the rows a pass launches under no home (`unhomed`).

The root home owns no row. A row whose queued brief names no home, or names `root`, does not
launch: `jbus.dispatch` makes it a gate, which the digest lists, until `jbus queue move` gives it
a child home. `jbus queue add` refuses such a brief from a user, and every brief jbus files itself
names one (`tests/test_jbus_shots.py`), so the launch is the last place a row could start under
the root."""

from __future__ import annotations

from jbriefs.home import ROOT, UNCATEGORIZED, named


def unhomed(slug: str, brief: str) -> tuple[str, str]:
    """Return why the row `slug` may not launch with its queued `brief` and how to give it a
    home, or two empty strings where its `Home:` line names a child home."""
    home = named(brief)
    if home not in ("", ROOT):
        return "", ""
    why = f"its brief names {home or 'no home'}, and the root home owns no row"
    return why, f"jbus queue move {slug} --home {UNCATEGORIZED}, or the row's scope"


def homed(text: str, brief: str) -> str:
    """Return `text` with the `Home:` line of `brief`, the queued brief, last in its head, when
    `brief` names a home and the head of `text` names none. Every message about a launched row is
    routed by its copy in `tasks/`, so the copy names the home its row belongs to. `judgement.body`
    leaves the line out, so the brief's sha stays the same."""
    home = named(brief)
    if not home or named(text):
        return text
    lines = text.splitlines(keepends=True)
    place = next((n for n, line in enumerate(lines) if line.startswith("## ")), len(lines))
    if place and not lines[place - 1].endswith("\n"):
        lines[place - 1] += "\n"
    lines.insert(place, f"Home: {home}\n")
    return "".join(lines)
