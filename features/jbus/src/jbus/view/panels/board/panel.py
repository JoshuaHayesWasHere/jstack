"""The board: each home of the project as one card, with its workers, each on a stage of the
process and how long it has been on it.

A worker is a crew, which is a task of the queue or a row that merged today, a reviewer or a
scout, each in the home `homes.Homes` gives it. A home's own thread is the card's head, as the
summary has it (`homes.Homes.group`), and a thread of no home's is on no card.

`STAGES` are the seven stages, in the order of the process. The current stage is the one in
progress: a pull request at `check` is on green, working toward it, and one at `hold` is green
and waits for the user's word. A crew's stage is that of the step the last pass gave its task
(`STAGE_OF_STEP`). A gate, a hung or waiting turn, a leftover and a closed pull request are on
a step that says nothing of the pull request, so for those the stage is that of the pull
request, where it has one (`STAGE_OF_PULL`). A task the pass did not judge is on the stage of
its row's status (`STAGE_OF_STATUS`). So no worker is ever on an unknown stage, and the tables
are checked against every step, facet and status when the module loads.

A reviewer at work is in review. Once its turn ended, it is where its task is, for as long as
its task has been there, and it is off the board once that task merged or is gone, since the
crew stands for the work. A scout is
running until its request has a Report that is done, and green from then until its home
settles its thread. `tone` says what asks: `bad` for what is broken, `ask` for what waits on
the user, as `state.RANK` groups it. A crew whose row has a fault that an agent owns says who
fixes it and when jbus told them (`fixing`, from `state.fixing`): the band leaves it out.

`since` is when the worker came to its stage. For a pull request it is the first line of the
run of `jmerge`'s lines, last first, whose steps are all on that stage, so review and its
second pass count as one stay in review. A card keeps what is merged apart from its other
workers, under `merged`: what merged today and what the pass judged merged or done.

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

from jbus import plan, queue, work
from jbus.view.homes import GROUP
from jbus.view.state import (
    ASKS,
    BROKEN,
    MERGE_LOG,
    MOVES_FILE,
    PASS_FILE,
    QUEUE_FILE,
    STEP,
    UNKNOWN,
    WORK_FILE,
    Read,
    Source,
    _mtime,
    fixing,
    text,
)

STAGES = (
    ("briefed", "Briefed"),
    ("running", "Running"),
    ("pr", "PR open"),
    ("review", "In review"),
    ("fixing", "Fixing"),
    ("green", "Green"),
    ("merged", "Merged"),
)
STAGE_OF_STEP = {
    "queued": "briefed",
    "running": "running",
    "gate": "running",
    "result": "pr",
    "review": "review",
    "second": "review",
    "proof": "review",
    "findings": "fixing",
    "rebase": "fixing",
    "check": "green",
    "hold": "green",
    "merged": "merged",
}
STAGE_OF_PULL = {
    work.Pull.MERGED: "merged",
    work.Pull.CLOSED: "pr",
    work.Pull.OTHER: "pr",
    **{pull: STAGE_OF_STEP[str(pull)] for pull in work.STEPPED},
}
STAGE_OF_STATUS = {
    "queued": "briefed",
    "launched": "running",
    "running": "running",
    "waiting": "running",
    "failed": "running",
    "stale": "running",
    "gate": "running",
    "left": "running",
    "pr": "pr",
    "merged": "merged",
    "done": "merged",
}
PLACED_BY_PULL = ("gate", "running")
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
    "researching": ("running", "Researching", ""),
    "reported": ("green", "Reported", ""),
    "blocked": ("running", "Blocked", "ask"),
    "not done": ("running", "Not done", "ask"),
    "missing": ("running", "No request", "ask"),
}
_KEYS = {key for key, _ in STAGES}
for table, over in (
    (STAGE_OF_STEP, set(STEP) - {UNKNOWN.key}),
    (STAGE_OF_PULL, set(work.Pull) - {work.Pull.NONE}),
    (STAGE_OF_STATUS, set(queue.STATUSES)),
):
    if missed := over - set(table):
        raise ValueError(f"no stage for {sorted(missed)}: add each to its table")
    if wrong := set(table.values()) - _KEYS:
        raise ValueError(f"{sorted(wrong)} are no stage of STAGES")

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
    "stages": [{"key": None, "name": None}],
    "homes": [
        GROUP | {"goal": None, "chain": [STEP_SHAPE], "workers": [WORKER], "merged": [WORKER]}
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


def stage_of(task: dict[str, Any], pull: str) -> str:
    """The stage of a task: its step's, or its pull request's for a step that says nothing of
    one, or its row's status's where the pass did not judge it."""
    if task["step"] == UNKNOWN.key:
        return STAGE_OF_STATUS.get(task["status"], "briefed")
    if task["step"] in PLACED_BY_PULL and pull in STAGE_OF_PULL:
        return STAGE_OF_PULL[work.Pull(pull)]
    return STAGE_OF_STEP[task["step"]]


def _since(task: dict[str, Any], stage: str) -> str | None:
    at = task["since"]
    for one in reversed(task["history"]):
        if STAGE_OF_STEP.get(one["step"]) != stage:
            break
        at = min(at, one["at"]) if at else one["at"]
    return at


def _crew(read: Read, task: dict[str, Any]) -> dict[str, Any]:
    """A crew's worker, with the fault an agent fixes on its row, where one stands."""
    facts = read.judged.get(task["slug"], {}).get("facts")
    pull = facts.get("pull", "") if isinstance(facts, dict) else ""
    stage = stage_of(task, pull)
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
            stage, since = "review", thread["created"]
        elif slug in crews and crews[slug]["stage"] != "merged":
            stage, since = crews[slug]["stage"], crews[slug]["since"]
        else:
            return None
    elif role == "scout":
        said = (thread.get("request") or {}).get("state", "missing")
        stage, state, asks = SCOUT[said]
        tone = tone or asks
        since = thread["updated"] if stage == "green" else thread["created"]
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
    order = {key: at for at, (key, _) in enumerate(STAGES)}
    crews = [_crew(read, task) for task in read.tasks + read.ended]
    by_slug = {one["slug"]: one for one in crews}
    homes = {task["slug"]: task["home"] for task in read.tasks + read.ended}
    for one in read.panel("merged")["merged"]:
        if one["slug"] in by_slug:
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
    for card in cards:
        mine = [one for home, one in placed if home == card["name"]]
        mine.sort(key=lambda one: (order[one["stage"]], one["since"] or "~", one["slug"]))
        card["workers"] = [one for one in mine if one["stage"] != "merged"]
        card["merged"] = [one for one in mine if one["stage"] == "merged"]
        card["goal"], card["chain"] = _plan(read.home / card["name"], read.rows)
    return {"stages": [{"key": key, "name": name} for key, name in STAGES], "homes": cards}
