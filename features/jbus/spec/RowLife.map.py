# Chart labels for RowLife: what you see of one row of the queue, in `jbus queue` and the sidebar.
# Each status names what in features/jbus/src/jbus/work.py sets it (`work.status` and its `_THREAD`
# table), and `removed` the verb that writes it. A row that is over keeps its status (`work.kept`).
reader_actions = ["Grant", "Hold", "Lift", "Remove"]

STATUS = {
    "queued": "queued (no thread yet)",
    "launched": "launched (a launch with no thread yet)",
    "running": "running (the thread at work, a Result or not, or its pull request opening)",
    "waiting": "waiting (the thread asks you)",
    "stale": "stale (the thread ended with nothing written)",
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

# queue.MOVES, the change of facts that makes each move, in the words of the table.
QUESTION_CLOSED = "the question closes, and the row's"
MOVES = {
    ("queued", "launched"): "a launch record names a thread for the row",
    ("queued", "gate"): "jbus opens a question on the row",
    ("gate", "queued"): f"{QUESTION_CLOSED} launch has no record",
    ("gate", "launched"): f"{QUESTION_CLOSED} launch has no thread yet",
    ("gate", "pr"): f"{QUESTION_CLOSED} pull request is open",
    ("gate", "done"): f"{QUESTION_CLOSED} Result says done",
    ("gate", "merged"): f"{QUESTION_CLOSED} pull request merged",
    ("launched", "running"): "T3 Code lists the thread at work",
    ("launched", "failed"): "the thread fails before a pass sees it at work",
    ("launched", "left"): "the thread ends with work left before a pass sees it at work",
    ("launched", "done"): "the thread ends with a clean Result before a pass sees it at work",
    ("failed", "running"): "the failed thread works again",
    ("failed", "left"): "the failed thread leaves its work to its home",
    ("failed", "done"): "a Result says done after the thread failed",
    ("running", "pr"): "a pull request opens",
    ("running", "left"): "the Result leaves work, or the pull request closes",
    ("running", "done"): "the thread ends with a clean Result and no pull request",
    ("running", "waiting"): "the thread asks for an answer to its request",
    ("running", "stale"): "the turn hangs, or the thread ends with nothing written",
    ("running", "failed"): "the thread fails",
    ("running", "merged"): "the pull request opens and merges between two passes",
    ("waiting", "running"): "the request is answered and the thread works again",
    ("waiting", "left"): "the thread ends after its request with work left",
    ("waiting", "failed"): "the thread fails while it waits",
    ("stale", "running"): "the thread works again",
    ("stale", "left"): "the thread stays quiet with nothing written, or writes a leftover",
    ("left", "pr"): "a pull request opens for what was left",
    ("left", "done"): "a follow-up Result says done",
    ("left", "running"): "the thread works again on what was left",
    ("left", "waiting"): "the thread asks for an answer again",
    ("left", "launched"): "jbus launches the row again for what was left",
    ("pr", "merged"): "the pull request merges",
    ("pr", "gate"): "jbus opens a question on the row with its pull request open",
    ("pr", "left"): "the pull request closes unmerged",
    ("pr", "done"): "the pull request leaves the open list, and the Result says done",
    ("done", "merged"): "the pull request of a done row merges on your accept",
}

# What a pass sees change, by the fact that changed, where the status stays.
THREAD = {
    "none": "T3 Code lists no thread",
    "starting": "the thread starts",
    "atwork": "the thread works",
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
        "Pull": PULL.get(after["pull"], action),
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
        return "you hold the approved row" if before["go"] == "approved" else "you hold the row"
    if action == "Remove":
        return f"you remove the row from {before['status']}"
    if action == "Grant":
        if before["go"] == "waiting":
            return "you approve the row, or a rule gives its go"
        if before["go"] == "kept":
            return "you approve the row over the hold that kept its go"
        return "you approve the held row, and the hold ends"
    return {
        "Lift": "you lift the hold, and its go comes back",
        "Void": "its go no longer holds, and it waits for yours",
    }.get(action, action)


def cause(v, facts, invariant):
    return {
        "FinalStays": "a pass writes the status a final row's facts give over it",
    }.get(invariant)


legend = {"works": "Works today", "wrong": "Wrong today", "fixed": "Fixed by the design"}
