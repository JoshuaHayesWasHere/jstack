"""The pruning schedule of a project's context pack: the stale check once a day, logged.

A project whose main checkout has a pack, `docs/context/` with a `notes/` folder, gets the
stale check of `jpack.stale` once a day, against the default branch as the checkout's
`origin/HEAD` names it, or its `HEAD` where that is not known. Its `stale` and `prune` lines
go into one quiet event, `pack`: the log has them, and nobody is posted. A pack with nothing
stale logs nothing. jbus edits no pack: rechecking a note, or pruning it, is the pull request
of the subject repo's home.

`packs.json` in the project's state directory keeps the day the check last ran, so a pass
runs it at most once a day, and a pass whose check could not run tries again on the next.
It is a step of the pass's `close` slot, after the sweep.
"""

from __future__ import annotations

from jbus import read_json, verbs, write_json
from jbus.wake import Pass
from jpack import Refused, stale
from jpack.verify import git

EVENTS = {"pack": "quiet"}
PACK = ("docs", "context")
NAME = "packs.json"


def check(run: Pass) -> None:
    """Run the day's stale check of the project's pack, if it has one and it is owed."""
    pack = run.project.checkout.joinpath(*PACK)
    path = run.state / NAME
    if not (pack / "notes").is_dir() or read_json(path, {}).get("day") == run.day:
        return
    checkout = run.project.checkout
    known = git(checkout, "rev-parse", "-q", "--verify", "refs/remotes/origin/HEAD^{commit}")
    rev = "refs/remotes/origin/HEAD" if known.returncode == 0 else "HEAD"
    try:
        found = stale.lines(pack, checkout, run.now, rev=rev)
    except (Refused, OSError, ValueError) as error:
        run.say(f"wait {run.project.name}: the pack's stale check did not run ({error})")
        return
    if found:
        pruned = sum(line.startswith("prune ") for line in found)
        line = f"pack {run.project.name}: {len(found) - pruned} stale, {pruned} to prune"
        run.box.send("", "pack", line, "\n".join(found), key=f"pack|{run.day}")
    write_json(path, {"day": run.day})


STEPS = (verbs.Step("close", 70, "packs.check", lambda half: check(half.run)),)
