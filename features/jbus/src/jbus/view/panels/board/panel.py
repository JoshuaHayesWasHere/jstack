"""The board: each home of the project as one card, with its workers, each on a stage of the
process and how long it has been on it.

A worker is a crew, which is a task of the queue or a row that merged today, a reviewer or a
scout, each in the home `homes.Homes` gives it. A home's own thread is the card's head, as the
summary has it (`homes.Homes.group`), and a thread of no home's is on no card.

Its stages are `state.STAGES`, the one table every screen names them from, in the order of the
process. A crew is on the stage `state.stages` puts its task on, the same stage the pipeline and
the project page draw it on, and on none where the view cannot place its task. A crew whose
task the pass judged merged or done, and a row that merged today, is merged.

A reviewer at work is on re-review where its task is, and else in review. Once its
turn ended, it is where its task is, for as long as its task has been there, and it is off the
board once that task merged or is gone, since the crew stands for the work. A scout is on its
task's stage where it has a task, and else on scout until its home settles its thread, with
what its request says: researching, reported, blocked, not done, or no request. `tone` says
what asks: `bad` for what is broken, `ask` for what waits on the user, as `state.RANK` groups
it. A crew whose row has a fault that an agent owns says who fixes it and when jbus told them
(`fixing`, from `state.fixing`): the band leaves it out.

`since` is when the worker came to its stage. For a pull request it is the first line of the
run of `jmerge`'s lines, last first, whose steps are all on that stage
(`state.STAGE_OF_STEP`), so waiting on a Result and the review count as one stay in review. A
card keeps what is over apart from its other workers: under `merged` each crew that merged
today, the merged panel's rows and so the project's one count of what merged today, and under
`done` each crew that is over and did not merge today, such as a row the pass judged done. A
row the merged panel has is merged, also while the pass still has it on another step.

A card also has its home's goal and the chain toward it, from the home's `plan.md` as
`jbus plan` reads it (`plan.entries`). The goal is the plan's `Goal (<day>, <who>): <goal>` line
before its first entry, or else its `Scope:` line. Each entry is one step of the chain, in the
plan's order, with a mark from the rows that do its work (`plan.rows_of`): `merged` where every
row is over, `working` where a row has started, with the open pull requests in `prs`, `queued`
where every open row waits to start, and where it has no row, `parked` or `planned` as its
`Stage:` line says. A home with no plan has no goal and no chain.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jbus import plan, queue
from jbus.view.homes import GROUP
from jbus.view.state import (
    ASKS,
    BROKEN,
    MERGE_LOG,
    MOVES_FILE,
    PASS_FILE,
    QUEUE_FILE,
    STAGE_OF_STEP,
    STAGES,
    WORK_FILE,
    Read,
    Source,
    _mtime,
    fixing,
    said_stages,
    stages,
    text,
)

TONE = {BROKEN: "bad", ASKS: "ask"}
LIVE_WORD = {
    "moving": "Working",
    "quiet": "Quiet",
    "hung": "Hung",
    "waiting": "Waiting",
    "ended": "Ended",
    "unknown": "Not known",
}
SCOUT = {
    "researching": ("Researching", ""),
    "reported": ("Reported", ""),
    "blocked": ("Blocked", "ask"),
    "not done": ("Not done", "ask"),
    "missing": ("No request", "ask"),
}

WORKER = {
    "kind": None,
    "slug": None,
    "pr": None,
    "stage": None,
    "state": None,
    "tone": None,
    "since": None,
    "open": None,
    "fixing": {"owner": None, "told": None},
}
STEP_SHAPE = {"slug": None, "line": None, "mark": None, "prs": [None]}
SHAPE = {
    "stages": [{"key": None, "name": None, "note": None}],
    "homes": [
        GROUP
        | {
            "goal": None,
            "chain": [STEP_SHAPE],
            "workers": [WORKER],
            "merged": [WORKER],
            "done": [WORKER],
        }
    ],
}
PLAN = "plan.md"
SOURCES = (
    PASS_FILE,
    WORK_FILE,
    QUEUE_FILE,
    MOVES_FILE,
    MERGE_LOG,
    Source(PLAN, "server", lambda read: {"at": _mtime(read.home / PLAN)}, 150),
)
STARTED = ("launched", "running", "waiting", "pr", "gate", "failed", "stale", "left")
_GOAL = re.compile(r"^Goal \([^)]*\): *(.+)$", re.M)
_SCOPE = re.compile(r"^Scope: *(.+)$", re.M)


def _since(task: dict[str, Any], stage: str) -> str | None:
    at = task["since"]
    for one in reversed(task["history"]):
        if STAGE_OF_STEP.get(one["step"]) != stage:
            break
        at = min(at, one["at"]) if at else one["at"]
    return at


def _crew(read: Read, task: dict[str, Any], stage: str | None) -> dict[str, Any]:
    """A crew's worker, with the fault an agent fixes on its row, where one stands."""
    return {
        "kind": "crew",
        "slug": task["slug"],
        "pr": task["pr"] or task["row_pr"],
        "stage": stage,
        "state": task["state"]["name"],
        "tone": TONE.get(task["rank"], ""),
        "since": _since(task, stage),
        "open": f"task:{task['slug']}",
        "fixing": read.once(fixing).get(task["slug"]),
    }


def _thread(thread: dict[str, Any], crews: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    role, slug = thread["role"], thread["slug"]
    tone = TONE.get(thread["rank"], "")
    if role == "reviewer":
        state = LIVE_WORD[thread["live"]]
        if thread["out"]:
            again = slug in crews and crews[slug]["stage"] == "review2"
            stage, since = ("review2" if again else "review"), thread["created"]
        elif slug in crews and crews[slug]["stage"] != "merged":
            stage, since = crews[slug]["stage"], crews[slug]["since"]
        else:
            return None
    elif role == "scout":
        said = (thread.get("request") or {}).get("state", "missing")
        state, asks = SCOUT[said]
        tone = tone or asks
        stage, since = "scout", thread["created"]
        if slug in crews and crews[slug]["stage"] != "merged":
            stage, since = crews[slug]["stage"], crews[slug]["since"]
    else:
        return None
    return {
        "kind": role,
        "slug": slug or thread["title"],
        "pr": "",
        "stage": stage,
        "state": state,
        "tone": tone,
        "since": since,
        "open": f"thread:{role}:{slug}" if slug else "threads",
        "fixing": None,
    }


def _mark(entry: plan.Entry, rows: list[queue.Row]) -> tuple[str, list[str]]:
    if not rows:
        return ("parked" if entry.stage.split(" ", 1)[0] == "parked" else "planned"), []
    still = [row for row in rows if not queue.over(row)]
    if not still:
        return "merged", []
    prs = sorted({text(row.get("pr"), 20) for row in still if row.get("pr")}, key=len)
    started = prs or any(row.get("status") in STARTED for row in still)
    return ("working" if started else "queued"), prs


def _plan(home: Path, rows: list[queue.Row]) -> tuple[str, list[dict[str, Any]]]:
    """The goal of the home whose directory is `home`, and its chain."""
    try:
        whole = (home / PLAN).read_text(errors="replace")
    except OSError:
        return "", []
    head = whole.split("\n## ", 1)[0]
    found = _GOAL.search(head) or _SCOPE.search(head)
    chain = []
    for entry in plan.entries(whole):
        mark, prs = _mark(entry, plan.rows_of(entry.slug, rows))
        chain.append({"slug": entry.slug, "line": text(entry.line, 160), "mark": mark, "prs": prs})
    return (text(found[1].strip(), 300) if found else ""), chain


def build(read: Read) -> dict[str, Any]:
    order = {one.key: at for at, one in enumerate(STAGES)}
    placed = read.once(stages)
    crews = [_crew(read, task, placed[task["slug"]]) for task in read.tasks]
    crews += [_crew(read, task, "merged") for task in read.ended]
    by_slug = {one["slug"]: one for one in crews}
    homes = {task["slug"]: task["home"] for task in read.tasks + read.ended}
    today = read.panel("merged")["merged"]
    for one in today:
        if one["slug"] in by_slug:
            by_slug[one["slug"]] |= {"stage": "merged", "state": "Merged"}
            continue
        crews.append(
            {
                "kind": "crew",
                "slug": one["slug"],
                "pr": one["pr"],
                "stage": "merged",
                "state": "Merged",
                "tone": "",
                "since": one["at"],
                "open": f"task:{one['slug']}",
                "fixing": None,
            }
        )
        homes[one["slug"]] = read.homes.of_task(one["slug"]).name
    placed = [(homes[one["slug"]], one) for one in crews]
    for thread in read.out or []:
        made = _thread(thread, by_slug)
        if made is not None and thread["home"] is not None:
            placed.append((thread["home"], made))
    cards = read.homes.group(read.tasks, read.panel("you")["needs"], read.out, read.acts)
    merged = {one["slug"] for one in today}
    for card in cards:
        mine = [one for home, one in placed if home == card["name"]]
        mine.sort(key=lambda one: (order.get(one["stage"], -1), one["since"] or "~", one["slug"]))
        card["workers"] = [one for one in mine if one["stage"] != "merged"]
        over = [one for one in mine if one["stage"] == "merged"]
        card["merged"] = [one for one in over if one["slug"] in merged]
        card["done"] = [one for one in over if one["slug"] not in merged]
        card["goal"], card["chain"] = _plan(read.home / card["name"], read.rows)
    return {"stages": said_stages(), "homes": cards}
