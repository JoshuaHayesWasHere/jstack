# Chart labels for PrVerdict: one pull request through jmerge's verdict.
reader_actions = ["Approve", "MergeOn", "Accept", "AcceptOther"]

SAID = {
    "none": "jmerge judges it next",
    "merged": "merged",
    "no-review": "waits on its review",
    "not-passed": "waits on its check",
    "check-failed": "its check failed",
    "conflicts": "conflicts with main",
    "row-held": "held: its row has no go",
    "declines": "held: a drop or decline the review did not uphold",
    "touches": "held: it touches a protected path",
    "merge-off": "held: merging is off",
    "base-merge-asked": "GitHub merges main into it, for its failed check",
    "base-moved-asked": "GitHub merges main into it, for the guards",
    "in-line": "in line behind the pull request ahead",
    "undecided": "GitHub has not decided whether it merges",
    "merged-tree-fails": "merged over main, it fails the guards",
    "in-batch": "in jmerge's batch, whose check runs",
}

HOLDS = {"row-held", "declines", "touches", "merge-off"}
CREW = {"no-review", "check-failed", "conflicts", "merged-tree-fails"}
FIXES = {"check-failed", "conflicts", "merged-tree-fails"}


HELD = "held: its check failed twice"
"""A row jbus held at its limit of failed heads, whatever jmerge last said of it: only your approve
or a head whose check passes lifts it."""


def _held(v):
    return v["st"] == "open" and v["held"] and v["said"] in FIXES


# The steps of jmerge's run. Once one can be taken, the verdict jmerge last said no longer holds:
# what it waited on came (the check ended, the review landed, the crew pushed, GitHub merged main
# in, you approved), and jmerge judges it next. A batch whose check runs still holds it.
RUN = {"Judge", "Merge", "GuardsFail", "JoinBatch"}


def _lifted(v, facts):
    return v["said"] not in ("none", "merged") and v["batch"] != "pending" and facts.enabled & RUN


def _said(v, facts):
    return "none" if _lifted(v, facts) else v["said"]


def _main(v):
    if v["mainRed"]:
        return "Main red"
    if v["moved"]:
        return "Main moved past its check"
    return "Main as its check saw it"


def state(v, facts):
    return f"{_main(v)}: {HELD if _held(v) else SAID[_said(v, facts)]}"


region_names = ["Main", "What jmerge says"]


def group(v, facts):
    if v["st"] == "merged":
        return "Merged"
    said = _said(v, facts)
    if said in HOLDS or _held(v):
        return "Waits on your word"
    if getattr(facts, "settled", False):
        return "Stuck"
    if said in CREW:
        return "Waits on its crew"
    return "Waits on jmerge, GitHub or a check"


group_colors = {
    "Merged": "#d1f2eb",
    "Waits on your word": "#fdebd0",
    "Waits on its crew": "#f2e6f9",
    "Waits on jmerge, GitHub or a check": "#e8eef9",
    "Stuck": "#f9d6d5",
}

STEPS = {
    "Accept": "you accept it, and it merges",
    "AcceptOther": "you accept the one ahead, and it merges",
    "Approve": "you approve its row",
    "BatchFails": "the batch's check fails: it goes alone at this head",
    "BatchProves": "the batch's check passes, and jmerge merges it",
    "CheckEnds": "its check ends",
    "CrewFix": "its crew rebases and fixes it",
    "GitHubDecides": "GitHub decides it merges cleanly or not",
    "GitHubMergesBase": "GitHub merges main into it",
    "GuardsFail": "the guards fail on its tree over main",
    "JoinBatch": "it joins jmerge's batch",
    "Judge": "jmerge judges it",
    "Lift": "its check passes, and jbus lifts its hold",
    "MainFixed": "jbus's revert or fix lands, and main is green",
    "MainMoves": "other work merges into main",
    "Merge": "jmerge merges it",
    "MergeOn": "you turn merging on",
    "OtherMerges": "the one ahead in line merges",
    "Release": "the one ahead waits on its crew or user, and gives up the line",
    "Review": "its reviewer's round holds",
    "Twice": "jbus holds its row: its check failed at three heads, or two that name no test",
}


def step(action, before, after):
    if action == "MovesMain":
        if after["movesLeft"] < before["movesLeft"]:
            return STEPS["MainMoves"]
        return STEPS["OtherMerges"] if before["ahead"] == "other" else STEPS["AcceptOther"]
    if action == "NewHead":
        crew = before["reviewed"] and not after["reviewed"]
        return STEPS["CrewFix"] if crew else STEPS["GitHubMergesBase"]
    if action == "CheckEnds":
        return "its check passes" if after["ci"] == "pass" else "its check fails"
    return STEPS.get(action, action)


def cause(v, facts, invariant):
    if v["st"] == "merged":
        return "it merged while a hold for your word stood"
    return "it waits for ever, on nothing your word can lift"
