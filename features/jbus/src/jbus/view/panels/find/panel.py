"""Find: every row of the queue, for the page to match what the user types against its slug and
the title of its brief. Each row gives its stage, its pull request and when it merged.

The stage of a row with a task is the task's state, as the task's drawer names it. A row that
ended with no task gives its status. The merged time is that of the row's last move in
`transitions.jsonl`, where that move is to merged. The open rows come first, in the queue's
order, then the rest, the newest merge first. The page filters them as the user types, and
`find:<words>` opens the drawer with those words in its box."""

from __future__ import annotations

from typing import Any

from jbus import queue
from jbus.view.state import MERGE_LOG, MOVES_FILE, QUEUE_FILE, WORK_FILE, Read, text, when

SHAPE = {"found": [{"slug": None, "title": None, "stage": None, "pr": None, "merged": None}]}
SOURCES = (QUEUE_FILE, WORK_FILE, MOVES_FILE, MERGE_LOG)


def title(read: Read, slug: str) -> str:
    """The heading of the row's brief in jbus's copies, after the slug it starts with, or
    nothing where there is no such brief."""
    brief = "" if "/" in slug else queue.brief(read.state, slug) or ""
    heading = next((line[2:] for line in brief.splitlines() if line.startswith("# ")), "")
    return text(heading.removeprefix(f"{slug}: "), 160)


def build(read: Read) -> dict[str, Any]:
    merged: dict[str, str | None] = {}
    for move in read.moves or []:
        at = when(move.get("at"))
        merged[text(move.get("slug"), 80)] = at if move.get("to") == "merged" else None
    open_ = {one["slug"]: one for one in read.tasks}
    tasks = open_ | {one["slug"]: one for one in read.ended}
    made = []
    for row in read.rows:
        slug = row["slug"]
        task = tasks.get(slug)
        stage = task["state"]["name"] if task else str(row.get("status") or "").capitalize()
        made.append(
            {
                "slug": slug,
                "title": title(read, slug),
                "stage": text(stage, 40),
                "pr": text(row.get("pr"), 20),
                "merged": merged.get(slug),
            }
        )
    first = [one for one in made if one["slug"] in open_]
    rest = sorted(
        (one for one in made if one["slug"] not in open_), key=lambda one: one["merged"] or ""
    )
    return {"found": first + rest[::-1]}
