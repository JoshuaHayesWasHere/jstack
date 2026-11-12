# Chart labels for RowLife: what you see of one row of the queue, in `jbus queue` and the sidebar.
# Each status names what in features/jbus/src/jbus/work.py sets it (`work.status` and its `_THREAD`
# table), and `removed` the verb that writes it. A row that is over keeps its status (`work.kept`).
# RowLife.trace.py, beside it, reads jbus's log of the row as the spec's steps.
# The line's value in work.json (`value`) is not drawn: each status node joins the values that give
# it, as work.status projects them (running: working, opening; stale: hung, lost, unknown;
# left: leftover, closed; queued: unapproved, behind, ready; launched: launching), and
# the value of a row that is over may say otherwise than its kept status, as a pull request that
# opens on a done row shows `check`. The facts are joined too: a step names the one that changed.
reader_actions = ["Grant", "Depends", "Hold", "Lift", "Remove"]

STATUS = {
    "queued": "queued (no thread yet, or its thread settled)",
    "launched": "launched (a launch with no thread yet)",
    "running": "running (the thread at work, a Result or not, or its pull request opening)",
    "waiting": "waiting (the thread asks you)",
    "stale": (
        "stale (the turn hung, or the thread ended, was settled or left T3 Code's list with "
        "nothing written)"
    ),
    "failed": "failed (the thread failed)",
    "gate": "gate (a question is open)",
    "pr": "pr (its pull request is open)",
    "left": "left (the Result leaves work)",
    "done": "done (a clean Result from a thread that ended)",
    "merged": "merged (its pull request merged)",
    "removed": "removed (queue.py `remove`, no pass sets it)",
}

GO = {
    "waiting": "No go",
    "approved": "Approved",
    "behind": "Approved, behind a row it depends on",
    "held": "Held",
    "kept": "Held, its go kept",
}


def state(v, facts):
    return f"{GO[v['go']]}: {STATUS[v['status']]}"


region_names = ["The go", "The row's status"]


def group(v, facts):
    if v["status"] in ("merged", "done"):
        return "Final"
    if v["status"] == "removed":
        return "Removed"
    if v["status"] in ("queued", "gate"):
        return "Not launched"
    return "Launched"


group_colors = {
    "Not launched": "#fdebd0",
    "Launched": "#d6eaf8",
    "Final": "#d1f2eb",
    "Removed": "#e5e8e8",
}

# queue.MOVES, the change of facts that makes each move, in the words of the table. A move not
# named here is labelled by the fact that changed, as `step` says it.
QUESTION_CLOSED = "the question closes, and the row's"
UNNAMED = "the pull request closes unmerged with no address of it in the Result, and"
MOVES = {
    ("queued", "launched"): "a launch record names a thread for the row",
    ("queued", "gate"): "jbus opens a question on the row",
    ("queued", "running"): "the thread T3 Code settled, whose launch stands, works again",
    ("queued", "waiting"): "the thread T3 Code settled, whose launch stands, asks for an answer",
    ("queued", "failed"): "the thread T3 Code settled, whose launch stands, fails",
    ("queued", "stale"): "the thread T3 Code settled, whose launch stands, ends with nothing "
    "written, or its turn hangs",
    ("queued", "left"): "the thread T3 Code settled, whose launch stands, writes a Result that "
    "leaves work",
    ("queued", "done"): "the thread T3 Code settled, whose launch stands, writes a clean Result",
    ("queued", "pr"): "the thread T3 Code settled, whose launch stands, opens a pull request",
    ("queued", "merged"): "the thread T3 Code settled, whose launch stands, opens a pull request "
    "that merges between two passes",
    ("gate", "queued"): f"{QUESTION_CLOSED} launch has no record",
    ("gate", "launched"): f"{QUESTION_CLOSED} launch has no thread yet",
    ("gate", "running"): f"{QUESTION_CLOSED} thread is at work",
    ("gate", "waiting"): f"{QUESTION_CLOSED} thread asks for an answer",
    ("gate", "failed"): f"{QUESTION_CLOSED} thread failed",
    ("gate", "stale"): f"{QUESTION_CLOSED} thread ended with nothing written",
    ("gate", "left"): f"{QUESTION_CLOSED} Result leaves work",
    ("gate", "pr"): f"{QUESTION_CLOSED} pull request is open",
    ("gate", "done"): f"{QUESTION_CLOSED} Result says done",
    ("gate", "merged"): f"{QUESTION_CLOSED} pull request merged",
    ("launched", "running"): "T3 Code lists the thread at work",
    ("launched", "waiting"): "the thread asks for an answer before a pass sees it at work",
    ("launched", "failed"): "the thread fails before a pass sees it at work",
    ("launched", "stale"): "the thread ends with nothing written before a pass sees it at work",
    ("launched", "left"): "the thread ends with work left before a pass sees it at work",
    ("launched", "done"): "the thread ends with a clean Result before a pass sees it at work",
    ("launched", "pr"): "a pull request opens before a pass sees the thread at work",
    ("launched", "merged"): "the pull request opens and merges between two passes",
    ("launched", "gate"): "jbus opens a question on the row",
    ("launched", "queued"): "T3 Code settles the thread, and the row may launch anew",
    ("failed", "running"): "the failed thread works again",
    ("failed", "waiting"): "the failed thread asks for an answer",
    ("failed", "stale"): "the failed thread ends with nothing written",
    ("failed", "launched"): "T3 Code no longer lists the thread, and its launch stands",
    ("failed", "left"): "the failed thread leaves its work to its home",
    ("failed", "done"): "a Result says done after the thread failed",
    ("failed", "pr"): "a pull request opens",
    ("failed", "merged"): "the pull request opens and merges between two passes",
    ("failed", "gate"): "jbus opens a question on the row",
    ("failed", "queued"): "T3 Code settles the thread, and the row may launch anew",
    ("running", "pr"): "a pull request opens",
    ("running", "left"): "the Result leaves work, or the pull request closes",
    ("running", "done"): "the thread ends with a clean Result and no pull request",
    ("running", "waiting"): "the thread asks for an answer to its request",
    ("running", "stale"): "the turn hangs, or the thread ends or is settled with nothing written",
    ("running", "failed"): "the thread fails",
    ("running", "merged"): "the pull request opens and merges between two passes",
    ("running", "launched"): "T3 Code no longer lists the thread, and its launch stands, or the "
    "crew opens nothing after its review",
    ("running", "gate"): "jbus opens a question on the row",
    ("running", "queued"): "T3 Code settles the thread, and the row may launch anew",
    ("waiting", "running"): "the request is answered and the thread works again",
    ("waiting", "left"): "the thread ends after its request with work left",
    ("waiting", "done"): "the thread ends after its request with a clean Result",
    ("waiting", "stale"): "the thread ends after its request with nothing written",
    ("waiting", "failed"): "the thread fails while it waits",
    ("waiting", "launched"): "T3 Code no longer lists the thread, and its launch stands",
    ("waiting", "pr"): "a pull request opens",
    ("waiting", "merged"): "the pull request opens and merges between two passes",
    ("waiting", "gate"): "jbus opens a question on the row",
    ("waiting", "queued"): "T3 Code settles the thread, and the row may launch anew",
    ("stale", "running"): "the thread works again",
    ("stale", "left"): "the thread stays quiet with nothing written for long enough, or writes a "
    "leftover",
    ("stale", "done"): "a Result says done after the thread ended",
    ("stale", "waiting"): "the thread asks for an answer",
    ("stale", "failed"): "the thread fails",
    ("stale", "launched"): "T3 Code no longer lists the thread, and its launch stands",
    ("stale", "pr"): "a pull request opens",
    ("stale", "merged"): "the pull request opens and merges between two passes",
    ("stale", "gate"): "jbus opens a question on the row",
    ("stale", "queued"): "T3 Code settles the thread, and the row may launch anew",
    ("left", "pr"): "a pull request opens for what was left",
    ("left", "done"): "a follow-up Result says done, and names no closed pull request",
    ("left", "running"): "the thread works again on what was left",
    ("left", "waiting"): "the thread asks for an answer again",
    ("left", "launched"): "the row is launched again for what was left",
    ("left", "merged"): "the pull request opens and merges between two passes",
    ("left", "gate"): "jbus opens a question on the row",
    ("left", "queued"): "the Result no longer names the closed pull request, and the thread "
    "settled",
    ("left", "failed"): "the Result no longer names the closed pull request, and the thread failed",
    ("left", "stale"): "the turn hangs, or the Result no longer names the closed pull request",
    ("pr", "merged"): "the pull request merges",
    ("pr", "gate"): "jbus opens a question on the row",
    ("pr", "left"): "the pull request closes unmerged",
    ("pr", "done"): "the pull request closes unmerged, and the clean Result names no address of it",
    ("pr", "running"): f"{UNNAMED} the thread works",
    ("pr", "failed"): f"{UNNAMED} the thread failed",
    ("pr", "stale"): "the pull request closes unmerged while the turn hangs, or with no address "
    "of it in the Result after the thread ended",
    ("pr", "launched"): f"{UNNAMED} T3 Code lists no thread",
    ("pr", "queued"): f"{UNNAMED} the thread settled",
    ("pr", "waiting"): "the pull request closes unmerged while the thread asks for an answer",
    ("done", "merged"): "the pull request of a done row merges on the user's accept",
}

# What a pass sees change, by the fact that changed, where the status stays.
THREAD = {
    "none": "T3 Code lists no thread",
    "starting": "the thread starts",
    "atwork": "the thread works",
    "hung": "the thread's turn hangs",
    "settled": "T3 Code settles the thread",
    "missing": "T3 Code no longer lists the thread",
    "waiting": "the thread asks for an answer",
    "failed": "the thread fails",
    "ended": "the thread ends",
}
WRITTEN = {
    "clean": "the crew writes a clean Result",
    "leftover": "the crew writes a Result that leaves work",
}
PULL = {
    "none": "the crew opens nothing after its review",
    "opening": "the crew is on its way to its pull request after its review",
    "open": "the pull request opens",
    "merged": "the pull request merges",
    "closed": "the pull request closes unmerged",
}


def step(action, before, after):
    said = {
        "Launch": "a launch record names a thread for the row",
        "Thread": THREAD.get(after["thread"], action),
        "Write": WRITTEN.get(after["written"], action),
        "Pull": (
            "the Result no longer names the closed pull request"
            if before["pull"] == "closed" and after["pull"] == "none"
            else PULL.get(after["pull"], action)
        ),
        "Ask": "jbus opens a question" if after["question"] else "the question closes",
    }.get(action)
    if said is not None:
        if before["status"] != after["status"]:
            return MOVES.get((before["status"], after["status"]), said)
        if before["status"] in ("merged", "done"):
            return f"{said}, and the row stays {before['status']}"
        return said
    if action == "Hold":
        if after["go"] == "kept":
            return "you hold the row, keeping its go"
        if before["go"] in ("held", "kept"):
            return "you hold the held row again"
        return "you hold the approved row" if before["go"] == "approved" else "you hold the row"
    if action == "Remove":
        return f"you remove the row from {before['status']}"
    if action == "Grant":
        if after["go"] == "behind":
            return "you approve the row, behind a row it depends on"
        if before["go"] == "waiting":
            return "you approve the row, or a rule gives its go"
        if before["go"] == "kept":
            return "you approve the row over the hold that kept its go"
        if before["go"] in ("approved", "behind"):
            return "you approve the approved row again"
        return "you approve the held row, and the hold ends"
    return {
        "Lift": "you lift the hold, and its go comes back",
        "Ahead": "the rows it depends on are over",
        "Depends": "you give the approved row other depends, and its line waits for a pass",
        "Pass": "a pass writes the row's line again",
        "Void": "its go no longer holds, and it waits for yours",
    }.get(action, action)


def cause(v, facts, invariant):
    return {
        "FinalStays": "a pass writes the status a final row's facts give over it",
    }.get(invariant)


legend = {"works": "Works today", "wrong": "Wrong today", "fixed": "Fixed by the design"}


# The reference lanes `statechart site --lanes` draws: the status, its 12 values nested in six
# superstates, and the go, each a row of boxes. A row that launched and reads `queued` again, its
# thread settled, missing or gone, is at work, not waiting for a launch: it is the chip "queued
# again" inside "At work". The moves between the statuses of one superstate are a table.
SUPERSTATE = {
    "queued": "notlaunched",
    "gate": "question",
    "launched": "atwork",
    "running": "atwork",
    "waiting": "atwork",
    "stale": "atwork",
    "failed": "atwork",
    "left": "atwork",
    "pr": "review",
    "done": "final",
    "merged": "final",
    "removed": "removed",
}

lanes = {
    "status": {
        "name": "Status",
        "about": "6 superstates of the 12 statuses",
        "start": "notlaunched",
        "boxes": {
            "notlaunched": "Not launched",
            "question": "Question",
            "atwork": "At work",
            "review": "In review",
            "final": "Final",
            "removed": "Removed",
        },
        "chips": {
            "notlaunched": {"queued": "queued"},
            "question": {"gate": "gate"},
            "atwork": {
                "launched": "launched",
                "running": "running",
                "waiting": "waiting",
                "stale": "stale",
                "failed": "failed",
                "left": "left",
                "requeued": "queued again",
            },
            "review": {"pr": "pr"},
            "final": {"done": "done", "merged": "merged"},
            "removed": {"removed": "removed"},
        },
    },
    "go": {
        "name": "The go",
        "about": "approval, its own lane",
        "start": "waiting",
        "boxes": {
            "waiting": "No go yet",
            "approved": "Approved",
            "behind": "Approved, behind a row",
            "held": "Held",
            "kept": "Held, go kept",
        },
    },
}

who = {
    "merge": "a merge, or GitHub",
    "crew": "a crew or its thread",
    "jbus": "jbus's pass",
    "you": "you, or a home",
}


def chip(v):
    """The status as the lanes draw it: `queued` after a launch is `requeued`."""
    return "requeued" if v["status"] == "queued" and v["launched"] else v["status"]


def superstate(v):
    return "atwork" if chip(v) == "requeued" else SUPERSTATE[v["status"]]


def lane_moves(before, after, action):
    """The boxes one step moves, as (lane, from, to, effect), and, for a step that moves none,
    the key of the `still` row that says what it does. A move between two statuses of one
    superstate stays in its box, with the effect `from>to`."""
    if chip(before) != chip(after):
        was, now = superstate(before), superstate(after)
        effect = action if was != now else f"{chip(before)}>{chip(after)}"
        return [("status", was, now, effect)], None
    if before["go"] != after["go"]:
        return [("go", before["go"], after["go"], action)], None
    return [], f"status:{action}"


# Each arrow: who moves it, what happens, and the guard it needs, if any.
arrows = {
    ("status", "notlaunched", "atwork", "Launch"): ("jbus", "jbus launches it", "go approved"),
    ("status", "notlaunched", "question", "Ask"): ("jbus", "jbus opens a question", None),
    ("status", "notlaunched", "removed", "Remove"): ("you", "you remove it", None),
    ("status", "question", "notlaunched", "Ask"): (
        "you",
        "the question closes, no launch yet",
        None,
    ),
    ("status", "question", "atwork", "Ask"): ("you", "the question closes; a thread is out", None),
    ("status", "question", "review", "Pull"): ("merge", "its pull request opens", None),
    ("status", "question", "final", "Pull"): ("merge", "its pull request merges", None),
    ("status", "question", "final", "Thread"): (
        "crew",
        "the thread ends after a clean Result",
        None,
    ),
    ("status", "question", "final", "Write"): ("crew", "the crew writes a clean Result", None),
    ("status", "atwork", "question", "Ask"): ("jbus", "jbus opens a question", None),
    ("status", "atwork", "review", "Pull"): ("merge", "its pull request opens", None),
    ("status", "atwork", "final", "Pull"): ("merge", "its pull request merges", None),
    ("status", "atwork", "final", "Thread"): ("crew", "the thread ends after a clean Result", None),
    ("status", "atwork", "final", "Write"): ("crew", "the crew writes a clean Result", None),
    ("status", "atwork", "removed", "Remove"): ("you", "you remove it", "left, or queued again"),
    ("status", "review", "atwork", "Pull"): ("merge", "the pull request closes unmerged", None),
    ("status", "review", "question", "Pull"): ("merge", "it closes while a question is open", None),
    ("status", "review", "final", "Pull"): ("merge", "the pull request merges", None),
    ("status", "review", "removed", "Remove"): ("you", "you remove it", None),
    ("go", "waiting", "approved", "Grant"): ("you", "you approve, or a rule gives its go", None),
    ("go", "waiting", "behind", "Grant"): (
        "you",
        "you approve; a row it depends on is not over",
        None,
    ),
    ("go", "waiting", "held", "Hold"): ("you", "you hold it", None),
    ("go", "approved", "held", "Hold"): ("you", "you hold it", None),
    ("go", "approved", "kept", "Hold"): ("you", "you hold it, keeping its go", None),
    ("go", "approved", "waiting", "Void"): (
        "jbus",
        "its go no longer holds",
        "status queued or gate",
    ),
    ("go", "behind", "approved", "Ahead"): ("jbus", "the rows it depends on are over", None),
    ("go", "behind", "held", "Hold"): ("you", "you hold it", None),
    ("go", "behind", "kept", "Hold"): ("you", "you hold it, keeping its go", None),
    ("go", "behind", "waiting", "Void"): (
        "jbus",
        "its go no longer holds",
        "status queued or gate",
    ),
    ("go", "held", "approved", "Grant"): ("you", "you approve it; the hold ends", None),
    ("go", "held", "behind", "Grant"): ("you", "you approve it, behind a row; the hold ends", None),
    ("go", "kept", "approved", "Grant"): ("you", "you approve it", None),
    ("go", "kept", "approved", "Lift"): ("you", "you lift the hold", None),
    ("go", "kept", "behind", "Grant"): ("you", "you approve it, behind a row", None),
    ("go", "kept", "behind", "Lift"): ("you", "you lift the hold, behind a row", None),
}

# Each kind of step that moves no box: who takes it, its lane, and what it does.
still = {
    "status:Thread": (
        "crew",
        "status",
        "T3 Code says something new of the thread, and the status the facts give stays",
    ),
    "status:Write": ("crew", "status", "the crew writes a Result, and the status stays"),
    "status:Pull": ("merge", "status", "GitHub lists the pull request anew, and the status stays"),
    "status:Ask": (
        "jbus",
        "status",
        "a question opens or closes and the status stays: the row is over, or the facts win",
    ),
}


def seen(state=None):
    """{arrow or (lane, from, to): (count, where the count comes from)} for each move
    transitions.jsonl records. It records statuses, not what moved them, so a count between two
    superstates is on their arc, and one inside a superstate on its cell. A `queued` after the row
    left `queued` or `gate` once is `requeued`. A file that is not there, or a line that does not
    parse, counts as nothing. The logs are jbus's state folder, ~/.local/state/jbus unless `state`
    names another."""
    import collections
    import json
    from pathlib import Path

    state = Path(state) if state else Path.home() / ".local" / "state" / "jbus"

    rows = collections.defaultdict(list)
    for log in sorted(state.glob("*/transitions.jsonl")):
        try:
            lines = log.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                t = json.loads(line)
            except ValueError:
                continue
            if (
                isinstance(t, dict)
                and isinstance(t.get("slug"), str)
                and t.get("from") in SUPERSTATE
                and t.get("to") in SUPERSTATE
            ):
                rows[(log.parent.name, t["slug"])].append(t)
    moves, stamps = collections.Counter(), []
    for ts in rows.values():
        launched = False
        for t in sorted(ts, key=lambda t: str(t.get("at", ""))):
            stamps.append(str(t.get("at", "")))
            a = "requeued" if t["from"] == "queued" and launched else t["from"]
            launched = launched or t["to"] not in ("queued", "gate", "removed")
            b = "requeued" if t["to"] == "queued" and launched else t["to"]
            x = "atwork" if a == "requeued" else SUPERSTATE[a]
            y = "atwork" if b == "requeued" else SUPERSTATE[b]
            if x != y:
                moves[("status", x, y)] += 1
            elif a != b:
                moves[("status", x, x, f"{a}>{b}")] += 1
    stamps = sorted(s for s in stamps if s)
    span = f"{stamps[0][:10]} to {stamps[-1][:10]}" if stamps else "no dates"
    source = f"jbus/*/transitions.jsonl, {len(rows):,} rows, {span}"
    return {key: (n, source) for key, n in moves.items()}
