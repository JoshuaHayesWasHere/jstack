# Chart labels for Setup: what jstack leaves on your machine, as you see it after an install.sh
# run or an uninstall, and an expert's webhook, as you see it in T3 Code's scheduled tasks.
# Setup.chart.cfg draws the install and the expert, two regions that change apart; the mirror,
# which breaks no rule, is labelled for a config that draws it alone.
#
# What each label keeps apart, and each join:
# - created, repos, seeded: a label names each path the records leave out ("leaves ... behind"),
#   and joins the records that cover all of it into "uninstall removes it all". Which record
#   covers a path is joined: an uninstall removes it either way.
# - disk: each path jstack made that no record covers is named. The paths a record covers are
#   joined into the phase: "installed" is any of them on disk.
# - fresh: joined. A HOME whose ~/.local/state was there already never shows "~/.local/state".
# - alone, op, step, pend: joined into "installing". The steps tell them apart.
# - homeId: "thread 1" and "thread 2", or no expert yet.
# - webhook, url, tasks: kept apart as how many webhooks are live, whether the record names the
#   live one, and whether the address kept is the kept webhook's. Which id is joined.
# - epc, me, got, nextId: joined into "starting", "its turn stopped" and a start that ended;
#   the steps tell the start's calls apart, and the label shows what each call made or kept.
# - entry, bak, mirrorLock, mpc: the mirror's entry is its own, gone with its copy in a backup,
#   or a link, beside the install, once it moved; the lock and where the run is are joined, and
#   so is a backup beside an entry that is its own, which no step makes.
reader_actions = ["Begin", "Uninstall", "ExpertStart", "MirrorBegin"]

PATH = {
    "above": "~/.local/state",
    "state": "~/.local/state/jstack",
    "dir": "a folder it made",
    "seed": "a seeded config",
    "hook": "a repo's hook",
    "stage": "a half-made state folder",
}
ORDER = ["above", "state", "dir", "seed", "hook", "stage"]


def covered(v, path):
    return (
        path in v["created"]
        or (path == "state" and len(v["created"]) > 0)
        or (path == "seed" and v["seeded"])
        or (path == "hook" and v["repos"])
        or path == "stage"
    )


def left(v):
    return [PATH[p] for p in ORDER if p in v["disk"] and not covered(v, p)]


def installed(v):
    if v["op"] != "none":
        phase = "Installing"
    elif v["disk"]:
        phase = "Installed"
    else:
        return "Nothing of jstack's on disk"
    behind = left(v)
    if not behind:
        return f"{phase}, uninstall removes it all"
    return f"{phase}, uninstall leaves {' and '.join(behind)} behind"


THREAD = {"t1": "thread 1", "t2": "thread 2"}


def webhooks(v, starting=False):
    """What T3 Code's scheduled tasks and the expert's folder show of its webhook."""
    tasks, kept = v["tasks"], v["webhook"]
    if len(tasks) > 1:
        hook = "two webhooks live"
    elif not tasks:
        hook = "a kept webhook that is gone" if kept["id"] else "no webhook"
    elif kept["id"] == tasks[0]["id"] and kept["by"] == tasks[0]["to"]:
        hook = f"its webhook kept, posting into {THREAD[tasks[0]['to']]}"
    else:
        hook = "a webhook no record names"
    if kept["id"] and v["url"] != kept["id"] and starting:
        hook += ", its address not kept yet"
    elif kept["id"] and v["url"] != kept["id"]:
        hook += ", its address lost" if v["url"] == 0 else ", the address of an old webhook"
    return hook


def expert(v):
    if v["homeId"] == "none":
        return "No expert yet"
    who = f"Expert in {THREAD[v['homeId']]}"
    if v["epc"] == "idle":
        return f"{who}, {webhooks(v)}"
    if v["epc"] == "stopped":
        return f"{who}, {webhooks(v)}, its turn stopped"
    return f"{who} starting, {webhooks(v, starting=True)}"


def mirrored(v):
    return {
        "own": "The mirror holds its own entry",
        "gone": "The mirror's entry is in its backup, not linked",
        "link": "The mirror's entry links to ~/.claude's, its own in a backup",
    }[v["entry"]]


def state(v, facts):
    if v["entry"] == "own" and v["mpc"] == "idle":
        return f"{installed(v)}: {expert(v)}"
    return f"{installed(v)}; {mirrored(v)}: {expert(v)}"


region_names = ["What an uninstall would leave", "The expert's webhook"]


def group(v, facts):
    return "Leaves something behind" if left(v) else None


group_colors = {"Leaves something behind": "#fdebd0"}

MAKES = {
    "dir": "the install makes a folder",
    "seed": "--setup seeds a config",
    "repo": "--repo sets up a repo",
}
MADE = {
    "dir": "it makes the folder",
    "seed": "it writes the seeded config",
    "repo": "it puts the repo's hook",
}
SEEN = {
    "delete": "it finds a webhook no record keeps",
    "create": "it finds no live webhook kept",
    "lost": "it finds the kept webhook's address lost",
    "bind": "it finds the webhook kept posts into another thread",
    "mend": "it finds the record names another thread",
    "idle": "it finds its own webhook kept",
}


def step(action, before, after):
    op = before["op"] if before["op"] != "none" else after["op"]
    return {
        "Begin": f"you run install.sh: {MAKES.get(after['op'], '')}",
        "NoteMkdir": "it makes ~/.local/state/jstack",
        "NoteWrite": "it writes the record of what it made",
        "WriteRecord": "it records the seeded config" if op == "seed" else "it records the repo",
        "Make": MADE.get(op, "it makes the path"),
        "InstallDies": "the install is killed",
        "Uninstall": "you uninstall",
        "MirrorBegin": "jroles mirror runs",
        "Rename": "it moves the mirror's own entry to a backup",
        "Link": "it links the entry to ~/.claude's",
        "MirrorDies": "jroles mirror is killed",
        "ExpertStart": f"you start the expert in {THREAD.get(after['me'], 'a thread')}",
        "Look": SEEN.get(after["epc"], "it lists the webhooks"),
        "Lost": "it sets out to delete that webhook",
        "Delete": "it deletes the webhook",
        "Create": "T3 Code makes a webhook into this thread",
        "KeepUrl": "it keeps the new address",
        "KeepId": "it keeps the new webhook",
        "Bind": "it writes this thread into the record",
        "TakeOver": "it binds the webhook to this thread",
        "Mend": "it writes this thread into the record",
        "TurnStops": "the turn stops",
    }.get(action, action)


def cause(v, facts, invariant):
    if invariant in ("UninstallComplete", "RecordLevelsRecorded"):
        return "the install makes jstack's state folder before a record names it"
    if invariant == "MadePathsRecorded":
        return "the install makes a folder before it records it"
    return None


legend = {"works": "Works today", "wrong": "Wrong today"}
