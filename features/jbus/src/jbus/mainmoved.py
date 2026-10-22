"""Telling a crew that main was fixed: the wake a red pull request never gets by itself.

A pull request that is red because main was broken has no review, so `jmerge` says only
that it has none, and `rebase.tell` hears nothing it acts on. Its crew ended its turn, and
fixing main wakes nobody. `tell` keeps the default branch's commit from pass to pass, and
sends the crew of each open pull request that is red one message when main goes from red to
green: a main that moved while green was no reason for a branch to move. A red tip is kept
as `broken` in `main.json` until a green one follows it, so a tip whose check had not ended
when it landed, or a second red one, loses nothing, and the last tip whose check passed is
kept as `green`: `main.json` is the one record of main's red tip, which `jmerge.mainjson` reads for
a launch and for `jmerge`. Each tip main went through since the last pass is looked at in
order (`landed`), so a tip that failed or passed under a newer one before a pass saw it
counts, and a tip whose check has not ended is kept as `pending` and looked at again until
a tip after it settles. A tip's check is main's own, read as `main_check`
reads it, and a failed check at main's tip, or at the red tip kept as `broken`, is asked
again each pass: a rerun that passes on that same commit ends the red there. A conflict is
not told here: only a push ends it, and
`rebase.github` tells it once per head. The commit is the remote's own, asked for each pass:
nothing in a pass is sure to fetch. A pull request's check state is GitHub's own, read
out of the pass's list of open pull requests.

The message names the green tip that ended the red, and its key,
`mainmoved|<slug>|#<number>|<that tip 12>`, is its retry key at T3 Code and its mark in
`sent.json`. The commit in `main.json` moves on only when no send is owed, so a
pass that got no answer looks again, and the mark keeps what was told from being told twice.
A pass that still owes a send writes only `fixed`, the green tip, so main reads as green for
`jmerge.mainjson` while the record keeps the commit to look at again, and the next pass takes the
red as ended there, whatever tip main is at by then.
So does a pass in which GitHub had not yet said whether a red head the rebase message went to
still conflicts.

A message `rebase.held` keeps back, for a thread at work or a head that moved, holds nothing
else up: a turn may last, and a pull request that turns red meanwhile was not red when main
moved. Its slug goes on `held` in `main.json`, beside the commit and the red tip with the
green one that ended it (`broken` and `fixed`), and each pass looks at
those slugs again, and at no other, until main moves again.

A crew is told to rebase a head once, here or by `rebase.tell`. A red head that is also in
conflict and has `rebase|<slug>|<head 12>` is not told here, a head told here is marked with
that key, and the rebase message marks this module's key for the commit main is at. A head
told here, or refused and put to a gate, is marked with `failed|<slug>|<head 12>` too: this
message says what to do of its failed check, so `rebase.github` does not say it again.
"""

from __future__ import annotations

from jbus import dispatch, read_json, rebase, verbs, write_json
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import World, _api, _check, checks
from jmerge import mainjson
from jmerge.mainjson import SETTLED

EVENTS = {"mainmoved": "quiet"}
RED = "red: checks failed"
NO_THREAD = "red pull request with no thread to tell"
REFUSED = "T3 Code refused the main-moved message"
MERGEABLE_UNKNOWN, MERGEABLE_CONFLICTING = "UNKNOWN", "CONFLICTING"
WAITING = 10
MESSAGE = (
    "jbus: main is green again at {main} while your pull request #{number} is {why}. If main "
    "was what broke it, it may be fixed now. In your own worktree: run `git update-ref "
    'refs/jstack/pre-rebase/{slug}/{short} {head}`, rebase onto origin/{default} as "A '
    'conflict" says, rerun the tests your change touches plus the ones that failed, and push '
    "with `git push --force-with-lease=refs/heads/{slug}:{head} origin "
    "HEAD:refs/heads/{slug}`. Then carry on your flow: launch its reviewer on that push if it "
    'has none, without waiting for green ("The review"), and handle the rest as "Stay on the '
    'pull request" says.'
)


def short_of(pull: dict) -> str:
    """Why a pull request is woken, in the message's words, or nothing for one that is not."""
    return RED if checks(pull) == "failed" else ""


def main_check(run: Pass, sha: str, again: bool = False) -> str:
    """Whether the checks of a commit on main passed, as `watch._check` says it, through the
    answers `checks.json` keeps: a final one is asked of GitHub once. With `again`, a kept
    `failed` is asked again: a rerun of the check on the same commit may have passed."""
    known: dict[str, str] = read_json(run.state / "checks.json", {})
    if again and known.get(sha) == "failed":
        del known[sha]
    answer = _check(run, known, sha)
    write_json(run.state / "checks.json", known)
    return answer


def landed(run: Pass, last: str, main: str) -> list[str]:
    """The tips main went through since `last`, oldest first and `main` the newest, along
    first parents, as GitHub lists main's commits. Where `last` is not on that way (no record
    yet, a main that was rewritten, more than `WAITING` tips, or no answer), it is the tips
    back to the newest one whose check has settled."""
    if main == last:
        return [main]
    said = _api(run, f"repos/{{owner}}/{{repo}}/commits?sha={main}&per_page={WAITING}")
    commits = (
        [commit for commit in said if isinstance(commit, dict)] if isinstance(said, list) else []
    )
    parent = {
        commit.get("sha"): (commit.get("parents") or [{}])[0].get("sha") for commit in commits
    }
    tips, at = [], main
    while at and at != last and len(tips) < WAITING:
        tips.append(at)
        at = parent.get(at)
    if not last or at != last:
        ended = (n for n, tip in enumerate(tips) if main_check(run, tip) in SETTLED)
        tips = tips[: next(ended, len(tips) - 1) + 1]
    return tips[::-1]


def tell(run: Pass, client: Client, world: World) -> None:
    """Send the crew of a red pull request one message when main goes from red to green: the
    commit that fixed it may fix them.

    Only a pull request that is open under a slug jbus launched: any other is not its crew.
    """
    asked = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    default = asked.stdout.strip().removeprefix("origin/")
    if not default:
        return
    asked = run.run("git", "ls-remote", "origin", f"refs/heads/{default}")
    main = (asked.stdout.split() or [""])[0]
    if asked.returncode != 0 or not main:
        return
    path = run.state / mainjson.NAME
    was = mainjson.load(run.state) or {}
    last, kept, broken = was.get("main"), was.get("held", []), was.get("broken", "")
    asked_before = main == last and was.get("check") == "green"
    if asked_before and not kept:
        return
    red, owed_at = broken, was.get("fixed", "")
    if owed_at or was.get("check") == "green":
        broken = ""
    green, check, waiting, stands = "", "", [], broken
    for tip in dict.fromkeys(
        (
            *([stands] if stands else []),
            *(tip for tip in was.get("pending", []) if tip != main),
            *landed(run, last or "", main),
        )
    ):
        check = main_check(run, tip, again=tip in (main, stands))
        if check == "green":
            green, broken, waiting = tip, "", []
        elif check == "failed":
            broken, waiting = tip, []
        elif check == "pending":
            waiting.append(tip)
    fixed = (green or owed_at) if red and not broken else ""
    owed, held = False, []
    sent = read_json(run.state / "sent.json", [])
    for slug, pull in world.open.items() if last and fixed else ():
        if asked_before and slug not in kept:
            continue
        why, head, number = short_of(pull), pull.get("headRefOid", ""), pull["number"]
        key = f"mainmoved|{slug}|#{number}|{fixed[:12]}"
        if not head or not dispatch.launched(run, slug):
            continue
        mergeable = pull.get("mergeable")
        if not why:
            continue
        if key in sent:
            continue
        if f"rebase|{slug}|{head[:12]}" in sent:
            if mergeable == MERGEABLE_UNKNOWN:
                owed = True
                continue
            if mergeable == MERGEABLE_CONFLICTING:
                continue
        try:
            brief = (run.home / "tasks" / f"{slug}.md").read_text(errors="replace")
        except OSError:
            brief = ""
        thread = dispatch.thread_of(brief)
        if not thread:
            run.gate(slug, NO_THREAD, f"#{number}: {why}", key=f"{NO_THREAD} {fixed[:12]}")
            continue
        if rebase.held(run, client, world, slug, number, head):
            held.append(slug)
            continue
        message = MESSAGE.format(
            main=fixed[:12],
            number=number,
            why=why,
            slug=slug,
            short=head[:12],
            head=head,
            default=default,
        )
        client.recipients = client.recipients | {thread}
        asked = {"threadId": thread, "message": message, "mode": "queue", "clientRequestId": key}
        try:
            client.call("t3_thread_send", asked)
        except T3Refused as error:
            run.gate(slug, REFUSED, f"{error}\n\n{message}", key=f"{REFUSED} {fixed[:12]}")
            run.box.mark(key)
            run.box.mark(f"failed|{slug}|{head[:12]}")
            continue
        except T3Error as error:
            owed = True
            run.say(f"wait {slug}: its crew could not be told that main moved ({error})")
            continue
        run.box.mark(key)
        run.told.add(slug)
        run.box.mark(f"rebase|{slug}|{head[:12]}")
        run.box.mark(f"failed|{slug}|{head[:12]}")
        line = f"mainmoved {slug}: told the crew (#{number}, main {fixed[:12]})"
        run.find(slug, "mainmoved", line, message, key=f"#{number} {fixed[:12]}")
        run.say(line)
    if not owed:
        at = (was.get("at") if main == last else "") or run.now.isoformat()
        record = mainjson.record(
            main=main,
            at=at,
            check=check,
            broken=broken or (red if held else ""),
            fixed="" if broken or not held else fixed,
            pending=waiting[-WAITING:],
            green=green or mainjson.of(was).green,
            held=held,
        )
        write_json(path, record)
    else:
        write_json(path, mainjson.owed(was, fixed))


STEPS = (
    verbs.Step(
        "after-expedite",
        10,
        "mainmoved.tell",
        lambda half: tell(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
