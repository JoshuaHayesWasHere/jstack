"""A crew's push of a head its desk check does not bind, refused at git's `pre-push`.

A crew works in a linked worktree on a branch named for its brief, `<homes>/<repo>/tasks/
<branch>.md`, which a launch gives a `Thread:` line. Each head pushed to that branch is asked
`jmerge`'s own rule (`ready.short_on_checked`), with no other head carried, as the crew's first
push block asks it: the fix pushes of "The review" and "The checks" are held to it too. A push
from the main checkout (jbus's restack of a link), a deletion and a branch with no such brief are
no crew's push.

A last `Checked:` line of the guards and the lint (`PART=guards`), which the crew's conflict
block writes, binds one head more narrowly: the head's one change over the head of the last line
of the desk's whole check must be the base it sits on (`only_the_base`), so a pull request in
conflict pushes its merge or rebase on that line and CI checks the rest, and no other change does.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from jleak.sources import NO_COMMIT, Unreadable, git
from jsettings.paths import homes_dir

THREAD = re.compile(r"^Thread: \S", re.MULTILINE)
REFUSED = (
    'crew-push: refused: {why}: run the check block of "Do the task" at {head}, then push again'
)
LIGHT = re.compile(r"make check-fast BASE=[0-9a-f]{40}(?: PYTEST=:)? PART=guards")
NO_FULL = (
    "its last Checked: line, the guards and the lint at {at}, has no line of the desk's whole "
    "check before it to be a merge of the base over"
)
MORE = (
    "its last Checked: line, the guards and the lint at {at}, binds only a merge of {base} over "
    "{full}, the head the desk's whole check passed at, and {head} changes more than that"
)


def only_the_base(checked: str, head: str, base: str) -> bool:
    """Whether `head` is `checked` moved onto a later `base` and nothing more: its fork from
    `base` descends from the fork `checked` had and is not that fork, and it has as many commits
    of its own, merges left out, as `checked` had over its fork. A merge of the base over
    `checked` is such a head, and so is a rebase of it; a commit added on either is not."""
    try:
        old = git("merge-base", checked, base).strip()
        new = git("merge-base", head, base).strip()
        if old == new or git("merge-base", old, new).strip() != old:
            return False
        own = [
            git("rev-list", "--count", "--no-merges", f"{fork}..{tip}").strip()
            for fork, tip in ((old, checked), (new, head))
        ]
    except Unreadable:
        return False
    return own[0] == own[1]


def _light(text: str, head: str) -> str:
    """Why a last `Checked:` line of the guards and the lint does not bind `head`, or nothing,
    also where the last line is no such line."""
    from jbriefs import checked, stacked
    from jmerge import ready

    lines = [said for line in text.splitlines() if (said := checked.read(line))]
    if not lines or not LIGHT.fullmatch(lines[-1].command):
        return ""
    at = lines[-1].head
    whole = [said for said in lines if not LIGHT.fullmatch(said.command) and said.exit == "0"]
    if not whole or ready.short_on_checked(
        f"Checked: {whole[-1].command} exit 0 at {whole[-1].head}", whole[-1].head
    ):
        return NO_FULL.format(at=at[:12])
    found = stacked.of(text)
    base = f"origin/{found.branch if found else 'main'}"
    if only_the_base(whole[-1].head, head, base):
        return ""
    return MORE.format(at=at[:12], base=base, full=whole[-1].head[:12], head=head[:12])


def refused(refs: Iterable[str]) -> list[str]:
    """Why each crew head among `refs`, what git writes to a `pre-push` hook, may not be pushed.
    It imports `jmerge` only once the push is a worktree's, so `jleak` alone imports no other
    command's feature."""
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
    from jmerge import ready

    tasks = homes_dir() / Path(common).parent.name / "tasks"
    found = []
    for local, branch in heads:
        try:
            text = (tasks / f"{branch}.md").read_text()
        except OSError:
            continue
        if THREAD.search(text) and (
            why := ready.short_on_checked(text, local) or _light(text, local)
        ):
            found.append(REFUSED.format(why=why, head=local[:12]))
    return found
