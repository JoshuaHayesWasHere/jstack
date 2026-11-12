# Chart labels for CrewProof, for statechart.
# Write labels in plain words, not variable or action names.
# v, before, and after map each variable to its value.
# Strings, numbers, and booleans keep their kind.
# Sequences, tuples, and sets become lists, indexed from 0. Records and functions become dicts.
# A crew's proof, review round and rebase of features/crew/spec/CrewProof.tla. Variables: finding,
# declines, scoped, proved, checked, dropped, crewCheck, proofFiles, outcome, before, preRef,
# failed, steps, sides, head, dirty, origin, rebased, lost, conflict, result, repo, kind, pc, bg,
# call, sections, saw, meets, reviewer, out, kept, twice, runs.
#
# Each state reads "<the proof on the brief at the head>: <where the round stands>", so the
# overview may draw two regions. The labels keep apart what a reader of the brief and the git
# dir tells apart, and join the rest, each join named here:
# - The Checked: line's exits 1, 75 and 124 are one "a check that did not pass": none of them
#   lets jmerge merge, and a crew runs the block again on each. Exit 0 stands alone.
# - The Proved: line's kinds base/head and tests only are one "proved"; "none, <kinds>" is
#   "nothing to prove". Its exits are not drawn: jmerge judges them, and ProofAtHead is the
#   chart's red border where an exit was not of the head it names.
# - A line of an earlier head is "no proof at this head", whatever it says.
# - The jgauge run's files (D-063) are drawn only while the block waits on them; a run killed
#   outright (pid, no exit) and one that ended are the same "the check is not running".
# - Outcome (D-065), the reviewer's proof files (D-064), crew-failed-files (D-128),
#   crew-check-steps (D-129) and crew-proof-sides (D-130) are not drawn: they hold what a later
#   block reads, and the step labels name what the block did with them.
# - The finding's fixed and a decline no pass ruled on are one "answered"; upheld and overruled
#   (D-028) are the ruling of an older brief and are told in the step that writes them.
# - The Scoped review: line's "none, one round" and no line are one "no scoped review owed".
# - A Dropped on rebase: line (D-041) is told in its step; the state says only whether a drop
#   still lacks its line.
# - The pre-rebase ref (D-127) is never removed and is not drawn.
reader_actions = []

DOING = {
    "checking": "the check runs",
    "checkEnd": "the check runs",
    "waiting": "the check runs",
    "proving": "the proof runs",
    "proveEnd": "the proof runs",
}


def proof(v):
    """What the brief's lines prove of the head the worktree is at."""
    if v["pc"] in DOING:
        where = " in the background" if v["bg"] else ""
        return DOING[v["pc"]] + where
    head = v["head"]
    checked = v["checked"]
    dirty = ", edits not committed" if v["dirty"] else ""
    if checked["at"] != head:
        return "No check at this head" + dirty
    if checked["exit"] != 0:
        return "The check did not pass at this head" + dirty
    proved = v["proved"]
    if proved["at"] != head:
        return "Checked at this head, not proved" + dirty
    if proved["kind"] == "none":
        return "Checked, nothing to prove at this head" + dirty
    return "Checked and proved at this head" + dirty


def round_(v):
    """Where the review round and the rebase stand."""
    if v["pc"] in ("kept", "recorded"):
        return "rebasing"
    if v["pc"] == "pushed":
        return "the rebase is pushed, its record not removed yet"
    if v["rebased"]:
        drop = (
            ", a dropped line has no line in the Result"
            if v["lost"] and v["dropped"] != v["head"]
            else ""
        )
        return "rebased, not pushed" + drop
    if v["before"]["at"] != 0:
        return "a rebase record left behind"
    if v["conflict"]:
        return "the pull request is in conflict"
    if v["out"] == "first":
        return "the review runs"
    if v["out"] == "scoped" or v["pc"] == "launching":
        twice = ", a second reviewer for the same round" if v["twice"] else ""
        return "the scoped review runs" + twice
    if not v["sections"]:
        return "the Result is written, no review yet" if v["result"] else "at work, no Result"
    if v["finding"] == "open":
        return "reviewed, a finding to answer"
    if v["scoped"]["line"] == "needed":
        reviewed = any(h > v["scoped"]["since"] for h, _ in v["sections"])
        if reviewed:
            return "its scoped review is written"
        if v["reviewer"]["line"] == "none" and v["reviewer"]["of"] == v["head"]:
            return "a scoped review is owed, none could be launched, yours to decide"
        return "a scoped review is owed"
    pushed = ", pushed" if v["origin"] == v["head"] else ""
    return "reviewed, no scoped review owed" + pushed


def state(v, facts):
    return f"{proof(v)}: {round_(v)}"


region_names = ["The proof at the head", "The review and the rebase"]


def group(v, facts):
    """The phase of the round, read off the same words the state's label ends with, so a drawn
    state is never in two groups, and no group holds more than 15 of them."""
    words = round_(v)
    for start, name in PHASES:
        if words.startswith(start):
            return name
    return "At work"


PHASES = [
    ("at work", "At work"),
    ("the Result is written", "Result written"),
    ("the review runs", "In review"),
    ("the scoped review runs", "In review"),
    ("reviewed, a finding", "A finding to answer"),
    ("a scoped review is owed", "A scoped review owed"),
    ("its scoped review is written", "A scoped review owed"),
    ("reviewed, no scoped review owed", "Nothing owed"),
    ("the pull request is in conflict", "In conflict"),
    ("rebased, not pushed, a dropped", "A drop not written"),
    ("rebased, not pushed", "Rebasing"),
    ("rebasing", "Rebasing"),
    ("the rebase is pushed", "The rebase record"),
    ("a rebase record left behind", "The rebase record"),
]
"""Each start of the round's words and its group: the first that matches wins, so a longer
start comes before a shorter one it begins with."""

group_colors = {
    "At work": "#ffffff",
    "Result written": "#eaf2f8",
    "In review": "#e8daef",
    "A finding to answer": "#fadbd8",
    "A scoped review owed": "#f5eef8",
    "Nothing owed": "#d1f2eb",
    "In conflict": "#fef9e7",
    "Rebasing": "#fdebd0",
    "A drop not written": "#f6ddcc",
    "The rebase record": "#e5e8e8",
}

# The label for one step. A step that leaves the reader in the same state is not drawn,
# unless the reader takes it on a bug path. "" draws no label, and a numbered bug step shows the
# action.
STEPS = {
    "Edit": "the crew edits",
    "Undo": "the crew drops its edits",
    "Commit": "the crew commits",
    "MovedToBackground": "the call outlives 10 minutes and goes to the background",
    "Die": "the block is killed",
    "CheckStart": "the crew runs the check block",
    "CheckStep": "a step of the check runs",
    "OutOfTime": "the check's time runs out, steps left",
    "AllRan": "every step ran",
    "CheckEnd": "the check block ends",
    "CheckCall": "the crew runs jgauge check",
    "RunEnds": "the check's run ends",
    "CheckAnswer": "jgauge check answers",
    "ProveNone": "proved.sh writes Proved none",
    "ProveStart": "the crew runs proved.sh",
    "ProveSide": "a side of the proof runs",
    "ProveEnd": "proved.sh ends",
    "WriteResult": "the crew writes its Result",
    "Push": "the crew pushes",
    "CIFails": "CI fails on a test file",
    "LaunchFirst": "jbus launches the review",
    "ReviewerWrites": "the reviewer writes its review",
    "ReviewerStops": "the head moved: the scoped reviewer stops",
    "Answer": "the crew answers the finding",
    "SecondPass": "the crew runs the second pass",
    "ReviewerLine": "the crew writes the Scoped reviewer line",
    "Conflict": "GitHub says the pull request is in conflict",
    "RebaseKeep": "the head is kept under pre-rebase",
    "RebaseRecord": "the rebase record is written",
    "RebaseRun": "git rebases",
    "WriteDropped": "the crew writes Dropped on rebase",
    "RebasePush": "the rebase is pushed with its lease",
    "Forget": "the rebase record is removed",
}


def step(action, before, after):
    if action == "SecondPass":
        if after["scoped"] != before["scoped"]:
            if after["scoped"]["line"] == "needed":
                return "the second pass writes that a scoped review is needed"
            return "the second pass writes that none is"
        if after["reviewer"]["line"] == "none":
            return "no launch tool: the home is told"
        return "the crew launches the scoped reviewer"
    if action == "ReviewerWrites" and after["declines"] != before["declines"]:
        return f"the scoped review writes its review, the decline {after['declines']}"
    if action == "CheckEnd" and after["checked"] != before["checked"]:
        return f"the check block writes its Checked line, exit {after['checked']['exit']}"
    if action == "CheckAnswer" and after["checked"] != before["checked"]:
        return f"jgauge check says {after['outcome']}, Checked line exit {after['checked']['exit']}"
    if action == "CheckAnswer":
        return f"jgauge check says {after['outcome']}"
    if action == "ProveEnd" and after["proved"] != before["proved"]:
        return "proved.sh writes its Proved line"
    return STEPS.get(action, action)


RULES = {
    "ProofAtHead": "a Proved: or Checked: line names a head its files did not pass at",
    "ReviewHeld": "a scoped review is owed and nobody launches it",
    "RebaseRecorded": "a rebase record stays after its push",
    "TypeOK": "a value the code never writes",
}


def cause(v, facts, invariant):
    if invariant == "ProofAtHead" and v["proved"]["at"] and not v["runs"]["proved"]:
        return (
            "an edit or a commit while the proof ran in the background,"
            " and the Proved line names the head it began at"
        )
    if invariant == "ProofAtHead":
        return "a step kept as passed for the head ran over edits not committed"
    return RULES.get(invariant)
