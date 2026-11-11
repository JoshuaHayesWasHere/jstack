# Chart labels for GhBudget: what GitHub has left, what jbus's passes do about it, and what the
# call log keeps.
#
# What the labels keep apart, and each join of values the code writes:
# - GitHub's count (`left`): above the floor, at or under it, spent. Each count between is one
#   of these three, as `held` reads it (`if low.remaining - calls > FLOOR:`).
# - The passes: a call that started with the budget read at or under the floor, a call under way,
#   a pass held, or none at work. A held gate joins its two reasons, the budget at the floor and
#   GitHub giving no answer (`return "GitHub did not say what is left of its API budget"`): both
#   make the pass ask nothing.
# - The call log (gh-calls.jsonl): no file, room left, or past its size (KEPT).
# - The old log (gh-calls.old.jsonl): none yet, the last full log, or a log a second rename moved
#   over it. Its lines join every field but `remaining` (at, caller, endpoint, status, resource,
#   reset, retry_after, http, requests, waited), which the rules do not read.
# - Joined in the spec itself and named there: `core` and `graphql` as one window, a kept
#   answer's `at` as within WITHIN or not, and the 16 slot files as Cap slots.
import re
from pathlib import Path

CFG = Path(__file__).with_name("GhBudget.cfg").read_text()
FLOOR = int(re.search(r"Floor = (\d+)", CFG)[1])
KEPT = int(re.search(r"Kept = (\d+)", CFG)[1])
"""The spec's floor and the lines a log holds before its rename, from the config the chart is
drawn with."""
CALLING = ("running", "logging", "checked", "rotating", "appending")


def _lost(v):
    old = v["old"]
    return bool(old) and len(old) <= KEPT


def _low_call(v):
    return any(v["pc"][p] == "running" and v["began"][p] == "low" for p in v["pc"])


def _github(v):
    if v["left"] == 0:
        return "The API budget spent"
    if v["left"] <= FLOOR:
        return "The API budget at the floor"
    return "The API budget above the floor"


def _passes(v):
    if _low_call(v):
        return "a call starts at the floor"
    if any(v["pc"][p] in CALLING for p in v["pc"]):
        return "a call under way"
    if any(v["gate"][p] == "held" for p in v["gate"]):
        return "a pass held"
    return "no call"


def _log(v):
    if not v["log"]:
        return "no call log"
    return "the call log past its size" if len(v["log"]) > KEPT else "the call log has room"


def _old(v):
    if not v["old"]:
        return "no old log"
    return "a full log lost" if _lost(v) else "the old log keeps the last full log"


def state(v, facts):
    return f"{_github(v)}: {_passes(v)}, {_log(v)}, {_old(v)}"


def group(v, facts):
    if _lost(v):
        return "A whole log lost"
    if _low_call(v):
        return "A call under the floor"
    if _passes(v) == "a pass held":
        return "A pass held"
    return "Budget kept"


group_colors = {
    "Budget kept": "#d1f2eb",
    "A pass held": "#d6eaf8",
    "A call under the floor": "#fdebd0",
    "A whole log lost": "#f9d6d5",
}


def _who(before, after):
    """The process the step moved: its place, or else its gate, which a held pass's look sets
    while it stays idle."""
    moved = [p for p in after["pc"] if after["pc"][p] != before["pc"][p]]
    moved += [p for p in after["gate"] if after["gate"][p] != before["gate"][p]]
    return moved[0] if moved else None


def step(action, before, after):
    p = _who(before, after)
    if action == "Look":
        if p is None or after["pc"][p] == "idle":
            return "a pass reads the budget at the floor and holds"
        if after["pc"][p] == "locking":
            return "a pass finds nothing said in the last minute"
        return "a pass reads the budget above the floor and goes on"
    if action == "TakeKeepLock":
        return "the pass takes the rate-limit record's lock"
    if action == "Relook":
        if after["kept"] != before["kept"]:
            return "the pass asks the API what is left and keeps the answer"
        if after["gate"][p] == "held":
            return (
                "the pass reads the budget at the floor, or the API gives no answer, and it holds"
            )
        return "another pass's answer is there, and the pass takes it"
    if action == "Call":
        return "a pass starts a gh call in a free slot"
    if action == "Done":
        return "a pass ends"
    if action == "Run":
        return "the API answers the call and counts it"
    if action == "LockRotate":
        return (
            "the call goes to log its line"
            if after["rotLock"] == "none"
            else "it takes the log's lock"
        )
    if action == "Check":
        if after["pc"][p] == "rotating":
            return "the log is past its size, so the process will rename it"
        return "the log has room"
    if action == "Rotate":
        if after["old"] != before["old"]:
            return "the process renames the log to the old log"
        return "the log is renamed already, and the rename fails quietly"
    if action == "Append":
        return "the call's line goes in the log"
    if action == "Tick":
        return "a minute passes"
    return action


def cause(v, facts, invariant):
    if invariant == "NoLostGeneration":
        return (
            "two processes found the log past its size at once: the first renamed it to the old "
            "log, a call started a new log, and the second renamed that one over the old log, so "
            "the whole log the first kept is gone"
        )
    if invariant == "HeldWhenLow":
        return (
            "a pass reads the budget once, as it starts, and goes on calling while its own calls "
            "and another pass's take the budget to the floor"
        )
    return None


legend = {"works": "Works today", "wrong": "Breaks a rule today"}
