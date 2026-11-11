# Chart labels for PrVerdict: one pull request through jmerge's verdict.
reader_actions = ["Approve", "MergeOn", "Accept", "AcceptOther"]

SAID = {
    "none": "opened, not judged yet",
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


def _held(v):
    """Why a row whose crew jbus tells nothing is held, where jmerge says it waits on its crew."""
    if v["st"] != "open" or not v["held"] or v["said"] not in FIXES:
        return ""
    return "its check failed twice"


def _main(v):
    if v["mainRed"]:
        return "Main red"
    if v["moved"]:
        return "Main moved past its check"
    return "Main as its check saw it"


def state(v, facts):
    held = _held(v)
    return f"{_main(v)}: {SAID[v['said']]}" + (f", and held: {held}" if held else "")


region_names = ["Main", "What jmerge says"]


def group(v, facts):
    if v["st"] == "merged":
        return "Merged"
    if v["said"] in HOLDS or _held(v):
        return "Waits on your word"
    if getattr(facts, "settled", False):
        return "Stuck"
    if v["said"] in CREW:
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
    "Twice": "jbus holds its row: its check failed at two heads",
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
