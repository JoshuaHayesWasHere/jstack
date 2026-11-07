"""A crew's push of a head its desk check does not bind, refused at git's `pre-push`.

A crew works in a linked worktree on a branch named for its brief, `<homes>/<repo>/tasks/
<branch>.md`, which a launch gives a `Thread:` line. Each head pushed to that branch is asked
`jmerge`'s own rule (`ready.short_on_checked`), with no other head carried, as the crew's first
push block asks it: the fix pushes of "The review" and "The checks" are held to it too. A push
from the main checkout (jbus's restack of a link), a deletion and a branch with no such brief are
no crew's push.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from jleak.sources import NO_COMMIT, git
from jsettings.paths import homes_dir

THREAD = re.compile(r"^Thread: \S", re.MULTILINE)
REFUSED = (
    'crew-push: refused: {why}: run the check block of "Do the task" at {head}, then push again'
)


def refused(refs: Iterable[str]) -> list[str]:
    """Why each crew head among `refs`, what git writes to a `pre-push` hook, may not be pushed."""
    heads = [
        (local, remote.removeprefix("refs/heads/"))
        for _, local, remote, _ in (ref.split() for ref in refs if len(ref.split()) == 4)
        if not NO_COMMIT.fullmatch(local) and remote.startswith("refs/heads/")
    ]
    if not heads:
        return []
    asked = ("rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir")
    own, common = git(*asked).splitlines()
    if own == common:
        return []
    from jmerge import ready  # here, so `jleak` alone imports no other command's feature

    tasks = homes_dir() / Path(common).parent.name / "tasks"
    found = []
    for local, branch in heads:
        try:
            text = (tasks / f"{branch}.md").read_text()
        except OSError:
            continue
        if THREAD.search(text) and (why := ready.short_on_checked(text, local)):
            found.append(REFUSED.format(why=why, head=local[:12]))
    return found
