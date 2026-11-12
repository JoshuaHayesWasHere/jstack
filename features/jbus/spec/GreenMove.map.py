# Chart labels for GreenMove: what you see of the green copy as passes move it to main's green
# tip, in `~/.local/bin/jbus`, the `green` link and green.json. Each phase names the step of
# features/jbus/src/jbus/green.py the pass is at (`_advance`, `_settle`, `_back`, `_resume`),
# and the rest what a command you run meets: the tool the link names, an older one, or none.
# v, before and after map each variable of GreenMove.tla to its value; tips are numbers, and
# MaxTip + 1 stands for no tool and no reload owed.
reader_actions = []

NOTHING = 4  # GreenMove.cfg's MaxTip = 3, plus one


def tool(v):
    if v["tool"] == NOTHING:
        return "no tool, so jbus does not start"
    if v["tool"] == v["link"]:
        return "the tool runs the linked tree"
    return "the tool runs another tree than the link"


def back(v):
    """A move that went back: `_back` writes to = from, the tree it came from."""
    return v["to"] == v["from"] and v["to"] != v["green"]


def state(v, facts):
    pc, owed = v["pc"], v["owed"]
    if pc == "idle" and owed == "none":
        at = "at main's green tip" if v["link"] == v["green"] else "main's green tip is newer"
        return f"Settled: {at}, {tool(v)}"
    if pc == "idle":
        return f"A pass died, green.json owes the {owed}: {tool(v)}"
    if pc in ("failed", "back", "removing") or (pc == "owed" and back(v)):
        where = {
            "failed": "uv refused the install",
            "back": "green.json owes the install of the tree it came from",
            "removing": "the link points back, the new tree to remove",
            "owed": "the link back, the tool to install again",
        }[pc]
        return f"Going back: {where}, {tool(v)}"
    where = {
        "owed": "green.json owes the install"
        + (", the link on the new tree" if v["link"] == v["to"] else ", the link on the old tree"),
        "pointed": "the link on the new tree, uv installs",
        "installed": "the tool installed, the old trees still on disk",
        "cleaned": "the old trees removed, the layouts to put",
    }[pc]
    return f"Moving: {where}, {tool(v)}"


region_names = ["Where the move is", "What the tool runs"]


def group(v, facts):
    pc, owed = v["pc"], v["owed"]
    if pc == "idle" and owed == "none":
        return "Settled"
    if pc == "idle":
        return "A step owed after a pass died"
    if pc in ("failed", "back", "removing") or (pc == "owed" and back(v)):
        return "Going back after uv refused"
    return "Moving to the new tip"


group_colors = {
    "Settled": "#d1f2eb",
    "Moving to the new tip": "#d6eaf8",
    "Going back after uv refused": "#fdebd0",
    "A step owed after a pass died": "#f9d6d5",
}


def step(action, before, after):
    if action == "Install":
        if after["pc"] == "installed":
            return "uv installs the tool from the linked tree"
        if after["tool"] == NOTHING and before["tool"] != NOTHING:
            return "uv refuses the install and removed the tool first"
        return "uv refuses the install"
    if action == "Relink":
        if after["owed"] == "none":
            return "the harness layouts are put from the linked tree"
        return "the relink is refused, and stays owed"
    if action == "Resume":
        return f"the next pass takes up the owed {before['owed']}"
    return {
        "MainGoesGreen": "main goes green at a newer tip",
        "Advance": "a pass grows the new tip's tree and writes the install it owes",
        "Point": "the pass points the link at the tree it moves to",
        "Back": "the pass goes back, owing the install of the tree it came from",
        "PointBack": "the pass points the link back",
        "Remove": "the pass removes the tree it went to",
        "Clean": "the pass removes the trees no command runs",
        "Die": "the pass dies: a timeout, a reboot or an OOM kill",
        "Reload": "systemd reloads the units green.json owes",
    }.get(action, action)
