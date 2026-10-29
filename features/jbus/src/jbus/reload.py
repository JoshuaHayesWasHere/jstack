"""`tell` tells each thread out that a merge changed a skill it may have loaded.

A thread keeps the text of each skill it loaded and runs it until it reads the file again, so
after a merge that changed a skill, a thread out runs the old text. `jmerge` names on its
`merged` line each skill whose `SKILL.md` the merge changed (`jmerge.lines.skills_of`).

`tell` keeps each such merge in `reload.json`, written before any send so a pass that stops
partway loses none, until every thread that was out when the merge landed is told: one message a
thread for every merge kept, under the key `reload|<commit 12>...|<thread>`, and each
`reload|<commit 12>|<thread>` marked in `sent.json` once T3 Code took it. Once every one is
told, the merge itself is marked, `reload|<commit 12>`, and a `merged` line printed again for it
adds nothing. So a thread hears of a merge once, and a send that got no answer, or that the
outbox held, goes on a later pass. A thread started after the merge loaded the new text and is
not told. A thread is told only of the skills it loaded (`loaded`): the ones its role loads
(`LOADS`), and each that its brief's `Skills:` line names. A thread whose title gives no role
(`roles.OTHER`) is the user's own and is not told.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jbriefs import skills
from jbus import outbox, queue, read_json, record, roles, t3, verbs, write_json
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.watch import when
from jmerge import lines as lines_of
from jmerge.lines import one as parse

if TYPE_CHECKING:
    from collections.abc import Iterable

FILE = "reload.json"
LOADS = {
    "crew": {"crew"},
    "reviewer": {"pr-review"},
    "scout": {"scout"},
    "home": {"home", "handoff", "new-home"},
}
TEMPLATE = "reload"
TOLD = (
    "jbus: pull request {merges} merged and changed these skills: {names}. The text of them"
    " you loaded before then is old: read each one's SKILL.md again from the file "
    "before you next follow it."
)


def owed(run: Pass, said: Iterable[str]) -> list[dict[str, Any]]:
    """Return the merges whose threads are still to be told: those kept in `reload.json`, and
    each `merged` line of this pass that names a skill."""
    kept: list[dict[str, Any]] = read_json(run.state / FILE, [])
    for text in said:
        line, names = parse(text), lines_of.skills_of(text)
        if not names or line is None or line.word != "merged":
            continue
        commit = text.split()[3]
        done = f"{TEMPLATE}|{commit[:12]}" in run.box.sent()
        if not done and all(one["commit"] != commit for one in kept):
            at = record.stamp(run.now)
            kept.append({"number": line.number, "commit": commit, "skills": names, "at": at})
    return kept


def tell(run: Pass, client: Client, said: Iterable[str]) -> None:
    """Tell each thread out of a merge that changed a skill, once, as the module says."""
    kept = owed(run, said)
    if not kept:
        return
    write_json(run.state / FILE, kept)
    try:
        out = t3.listed(client, run.project.project_id, settled=False)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the threads out could not be told of a skill ({error})")
        return
    write_json(run.state / FILE, _told(run, client, kept, out))


def loaded(run: Pass, role: str, slug: str) -> set[str]:
    """Return the skills a thread of this role and slug loaded: its role's own, and each that its
    brief's `Skills:` line names."""
    text = queue.brief(run.state, slug) or ""
    for kind in ("tasks", "scouts"):
        file = run.home / kind / f"{slug}.md"
        if not text and file.exists():
            text = file.read_text(errors="replace")
    return LOADS.get(role, set()) | {one.name for one in skills.named(text)}


def _told(
    run: Pass, client: Client, kept: list[dict[str, Any]], out: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Tell each thread of `out` that has a role, in one message, of every merge of `kept` that
    landed while it was out and changed a skill it loaded, and return the merges still owed."""
    left: set[str] = set()
    for thread in out:
        at, title = thread["threadId"], str(thread.get("title", ""))
        role, slug = roles.role_of(title)
        try:
            began = when(thread["createdAt"])
        except (KeyError, TypeError, ValueError):
            began = None
        wanted = set() if role == roles.OTHER else loaded(run, role, slug)
        due = [
            one
            for one in kept
            if set(one["skills"]) & wanted
            and (began is None or began <= when(one["at"]))
            and f"{TEMPLATE}|{one['commit'][:12]}|{at}" not in run.box.sent()
        ]
        commits = [one["commit"][:12] for one in due]
        names = ", ".join(dict.fromkeys(n for one in due for n in one["skills"] if n in wanted))
        merges = ", ".join(f"#{one['number']} at {one['commit'][:12]}" for one in due)
        try:
            went = bool(due) and outbox.send(
                run,
                client,
                thread=at,
                row=slug or title,
                key="|".join([TEMPLATE, *commits, at]),
                text=TOLD.format(merges=merges, names=names),
                template=TEMPLATE,
                needs="decide",
            )
        except T3Error as error:
            run.say(f"wait {slug or title}: its thread could not be told of a skill ({error})")
            went = False
        for commit in commits:
            if went:
                run.box.mark(f"{TEMPLATE}|{commit}|{at}")
            else:
                left.add(commit)
    for merge in (one for one in kept if one["commit"][:12] not in left):
        run.box.mark(f"{TEMPLATE}|{merge['commit'][:12]}")
        run.say(f"told {run.project.name}: #{merge['number']} changed {', '.join(merge['skills'])}")
    return [one for one in kept if one["commit"][:12] in left]


STEPS = (
    verbs.Step(
        "tellers",
        75,
        "reload.tell",
        lambda half: tell(half.run, half.client, half.said),
        ("client",),
    ),
)
