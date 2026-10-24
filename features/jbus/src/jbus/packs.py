"""jbus runs the stale check of a project's context pack once a day, and logs what it finds.

A project whose main checkout has a pack, `docs/context/` with a `notes/` folder, gets the
stale check of `jpack.stale` once a day. The check runs against the default branch that the
checkout's `origin/HEAD` names. When the checkout has no such branch, the check runs against
the checkout's `HEAD`. jbus puts the check's `stale` and `prune` lines into one quiet event,
`pack`. The log keeps them, and jbus posts them to nobody. For a pack with nothing stale, jbus
logs nothing. jbus edits no pack: the subject repo's home
rechecks or prunes a note, in a pull request of its own.

`packs.json` in the project's state directory records the day the check last ran, so a pass
runs it at most once a day. When the check could not run, the next pass tries again.
The check is a step of the pass's `close` slot, after the sweep.
"""

from __future__ import annotations

from jbus import read_json, verbs, write_json
from jbus.passes import Pass
from jpack import Refused, stale
from jpack.verify import git

EVENTS = {"pack": "quiet"}
PACK = ("docs", "context")
NAME = "packs.json"


def check(run: Pass) -> None:
    """Run the day's stale check of the project's pack, if the project has a pack and
    today's check has not run yet."""
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
