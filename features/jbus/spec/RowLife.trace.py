# How a line of jbus's `~/.local/state/jbus/<project>/transitions.jsonl` reads as a step of
# RowLife, for `statechart replay` (statechart/replay.py says the contract).
#
# - A line a pass wrote, `queue.derive`, is `{slug, from, to, at[, legal]}`: the row's status went
#   from `from` to `to`, by whatever facts changed since the pass before.
# - A line with `by` is a verb's, `remove` or `withdraw` (`queue._take_out`): one `Remove` step.
# - A line with `go` is a verb's or a rule's that moved the row's go (`queue._go`): one step of
#   the action that moves the go there.

# The actions a verb takes, each written as a line of its own: a pass's line never crosses one.
verbs = ("Remove", "Grant", "Hold", "Lift", "Void")

# The actions that leave the go at each value a go line names, and the spec's gos the value is:
# `_grant` and `_lift` both write `approved`, which the spec calls `behind` while a row the row
# depends on is not over (queue.py `return work.Row.BEHIND if unmet else work.Row.FREE`).
GO = {
    "approved": (("Grant", "Lift"), None),
    "held": (("Hold",), "held"),
    "kept": (("Hold",), "kept"),
    "waiting": (("Void",), "waiting"),
}


def observe(line):
    slug = line.get("slug")
    if not isinstance(slug, str):
        return None
    if "go" in line:
        if line["go"] not in GO:
            return None
        actions, go = GO[line["go"]]
        return slug, {}, {} if go is None else {"go": go}, actions
    if "from" not in line or "to" not in line:
        return None
    before, after = {"status": line["from"]}, {"status": line["to"]}
    return slug, before, after, ("Remove",) if "by" in line else None
