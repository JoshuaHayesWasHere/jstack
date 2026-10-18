"""Telling a crew that main was fixed: the wake a red pull request never gets by itself.

A pull request that is red because main was broken has no review, so `jmerge` says only
that it has none, and `rebase.tell` hears nothing it acts on. Its crew ended its turn, and
fixing main wakes nobody. `tell` keeps the default branch's commit from pass to pass, and
sends the crew of each open pull request that is red one message when main goes from red to
green: a main that moved while green was no reason for a branch to move. A red tip is kept
as `broken` in `main.json` until a green one follows it, so a tip whose check had not ended
when it landed, or a second red one, loses nothing, and the last tip whose check passed is
kept as `green`: `main.json` is the one record of main's red tip, which `mainstate` reads for
a launch and for `jmerge`. The tip's check is main's own, read as `main_check`
reads it. A conflict is not told here: only a push ends it, and
`rebase.github` tells it once per head. The commit is the remote's own, asked for each pass:
nothing in a pass is sure to fetch. A pull request's check state is GitHub's own, read
out of the pass's list of open pull requests.

The message's key, `mainmoved|<slug>|#<number>|<main 12>`, is its retry key at T3 Code and
its mark in `sent.json`. The commit in `main.json` moves on only when no send is owed, so a
pass that got no answer looks again, and the mark keeps what was told from being told twice.
A tip whose check has not ended is looked at again each pass, whether or not it is new.
So does a pass in which GitHub had not yet said whether a red head the rebase message went to
still conflicts.

A message `rebase.held` keeps back, for a thread at work or a head that moved, holds nothing
else up: a turn may last, and a pull request that turns red meanwhile was not red when main
moved. Its slug goes on `held` in `main.json`, beside the commit, and each pass looks at
those slugs again, and at no other, until main moves again.

A crew is told to rebase a head once, here or by `rebase.tell`. A red head that is also in
conflict and has `rebase|<slug>|<head 12>` is not told here, a head told here is marked with
that key, and the rebase message marks this module's key for the commit main is at. A head
told here, or refused and put to a gate, is marked with `failed|<slug>|<head 12>` too: this
message says what to do of its failed check, so `rebase.github` does not say it again.
"""

from __future__ import annotations

from jbus import dispatch, mainstate, read_json, rebase, verbs, write_json
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import World, _check, checks

EVENTS = {"mainmoved": "quiet"}
RED = "red: checks failed"
NO_THREAD = "red pull request with no thread to tell"
REFUSED = "T3 Code refused the main-moved message"
MERGEABLE_UNKNOWN, MERGEABLE_CONFLICTING = "UNKNOWN", "CONFLICTING"
SETTLED = ("green", "failed")
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


def main_check(run: Pass, sha: str) -> str:
    """Whether the checks of a commit on main passed, as `watch._check` says it, through the
    answers `checks.json` keeps: a final one is asked of GitHub once."""
    known: dict[str, str] = read_json(run.state / "checks.json", {})
    answer = _check(run, known, sha)
    write_json(run.state / "checks.json", {**read_json(run.state / "checks.json", {}), **known})
    return answer


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
    path = run.state / "main.json"
    was = read_json(path, {})
    last, kept, broken = was.get("main"), was.get("held", []), was.get("broken", "")
    asked_before = main == last and was.get("check") in SETTLED
    if asked_before and not kept:
        return
    check = main_check(run, main)
    if check == "failed":
        broken = main
    fixed = check == "green" and bool(broken)
    owed, held = False, []
    sent = read_json(run.state / "sent.json", [])
    for slug, pull in world.open.items() if last and fixed else ():
        if asked_before and slug not in kept:
            continue
        why, head, number = short_of(pull), pull.get("headRefOid", ""), pull["number"]
        key = f"mainmoved|{slug}|#{number}|{main[:12]}"
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
            run.gate(slug, NO_THREAD, f"#{number}: {why}", key=f"{NO_THREAD} {main[:12]}")
            continue
        if rebase.held(run, client, world, slug, number, head):
            held.append(slug)
            continue
        message = MESSAGE.format(
            main=main[:12],
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
            run.gate(slug, REFUSED, f"{error}\n\n{message}", key=f"{REFUSED} {main[:12]}")
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
        line = f"mainmoved {slug}: told the crew (#{number}, main {main[:12]})"
        run.find(slug, "mainmoved", line, message, key=f"#{number} {main[:12]}")
        run.say(line)
    if not owed:
        at = was.get("at") if main == last else run.now.isoformat()
        record = {"main": main, "at": at, "check": check}
        if broken and (held or check != "green"):
            record["broken"] = broken
        green = main if check == "green" else mainstate.of(was).green
        if green:
            record[mainstate.GREEN] = green
        if held:
            record["held"] = held
        write_json(path, record)


STEPS = (
    verbs.Step(
        "after-expedite",
        10,
        "mainmoved.tell",
        lambda half: tell(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
