"""`tell` tells a crew that main was fixed, a wake that a red pull request never gets by itself.

A pull request that is red because main was broken has no review. `jmerge` says only that the
pull request has none, and `rebase.tell` finds nothing in it to act on. The pull request's crew
has ended its turn, and a fix to main wakes nobody.

`tell` records the default branch's commit from pass to pass. When main goes from red to
green, it sends one message to the crew of each open pull request that is red, but a stacked
link still on its base's branch, whose move is `stack`'s to tell. When main
moves while green, a branch has no reason to move.

`main.json` is the one record of main's red tip, which `jmerge.mainjson` reads for a launch
and for `jmerge`. `tell` keeps a red tip there as `broken` until a green tip follows it. So
`tell` loses no tip whose check had not ended when the tip landed, and no second red tip
either. It keeps the last tip whose check passed as `green`.

`landed` lists each tip main went through since the last pass, and `tell` looks at them in
order. A tip still counts when it failed or passed before any pass looked at it, even with a
newer tip on top of it. `tell` keeps a tip whose check has not ended as `pending`, and looks
at that tip again until the check of a later tip ends. A tip's check is main's own, and
`tell` reads it through `main_check`. Each pass asks again about a failed check at main's
tip, or at the red tip kept as `broken`: a rerun that passes on that same commit ends the
red there.

`tell` does not tell a crew of a conflict. Only a push ends a conflict, and `rebase.github`
tells the crew about a conflict once per head. `tell` asks the remote for main's commit on
each pass, since no step of a pass is sure to fetch. A pull request's check state is GitHub's own.
`tell` reads it in the pass's list of open pull requests.

The message names the green tip that ended the red. The message's key,
`mainmoved|<slug>|#<number>|<that tip 12>`, is both its retry key at T3 Code and its mark in
`sent.json`. `tell` advances the commit in `main.json` only when it owes no send, so a pass
that got no answer looks again. With the mark, no pass sends the same message twice.
A pass that still owes a send writes only `fixed`, the green tip. `jmerge.mainjson` then
reads main as green. The record still keeps the old commit, so the next pass looks at it
again. The next pass takes the red as ended at that tip, whatever tip main is at by then. A
pass does the same when the rebase message went to a red head and GitHub has not yet said
whether that head still conflicts.

`rebase.held` holds back a message when its thread is at work or its head moved. A held
message delays no other message: a turn may last long, and a pull request that turns red meanwhile
was not red when main moved. `tell` puts the held message's slug on `held` in `main.json`,
beside the commit, the red tip and the green tip that ended the red (`broken` and
`fixed`). Each pass looks at those slugs again, and at no others, until main moves again.

jbus tells a crew to rebase a head once, here or in `rebase.tell`. `tell` skips a red head
that is also in conflict and already has `rebase|<slug>|<head 12>`. It marks a head it tells
with that key, and the rebase message marks this module's key for the commit main is at.
`tell` also marks with `failed|<slug>|<head 12>` each head it tells, and each head whose
message T3 Code refused and jbus then sent to a gate instead. This message says what to do about the
failed check, so `rebase.github` does not say it again. It writes no `failure|` key beside it, since
it told no failure: a merge of main onto that head is told by `rebase.github` as a new head.

A tip whose check started no job (`watch.NO_JOB`, a spent Actions limit or a failed payment) is
neither red nor green: no code was judged, so it changes neither `broken` nor `green`, and
`watch` files no main-red row for it. It is a decision about the account, which no fix to the
code makes. `account` raises it once for the project, as a gate (`questions.park`), however many
runs start no job, and closes it (`questions.clear`) when a tip whose check ran passes.
`account.json` in the project's state keeps the question's number while it is raised.
"""

from __future__ import annotations

from jbus import Refused, dispatch, expedite, questions, read_json, rebase, verbs, write_json
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import NO_JOB, World, _api, _check, checks
from jmerge import mainjson
from jmerge import stacked as stacks
from jmerge.mainjson import SETTLED

EVENTS = {"mainmoved": "quiet"}
RED = "red: checks failed"
NO_THREAD = "red pull request with no thread to tell"
REFUSED = "T3 Code refused the main-moved message"
MERGEABLE_UNKNOWN, MERGEABLE_CONFLICTING = "UNKNOWN", "CONFLICTING"
WAITING = 10
ACCOUNT, ACCOUNT_FILE = "ci-account", "account.json"
DECISION = "\n".join(
    (
        "## Gate <n>: CI on main started no job at {sha}: put the GitHub account's Actions limit "
        "or payment right?",
        "Status: open",
        "Asked by: {slug}, a jbus pass of mainmoved",
        "Default: jbus files no main-red row for a run that starts no job, and waits for a run "
        "whose jobs pass",
        "Built on it: main.json keeps its red and green tips as they were; no fix row is queued "
        "for {sha}",
        "Undo: none to take back: a run on main whose jobs pass closes this question",
        "Context: each failed check run at {sha} has a job that GitHub started on no runner and "
        "that ran no step, as on a spent Actions limit or a failed payment; no change to the code "
        "fixes that",
        "Option: wait for the account (default, recommended): no main-red row, and this question "
        "closes itself when a run with jobs passes",
        "Option: put it right now: pay or raise the limit on GitHub, then re-run the failed jobs "
        "at {sha}; this question closes when they pass",
    )
)
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
    """Return why `tell` wakes the crew of a pull request, in the message's words, or an empty
    string for a pull request whose crew it does not wake."""
    return RED if checks(pull) == "failed" else ""


def main_check(run: Pass, sha: str, again: bool = False) -> str:
    """Return whether the checks of a commit on main passed, as `watch._check` answers.

    It goes through the answers `checks.json` keeps, so it asks GitHub for a final answer
    once. With `again`, it asks again about a kept `failed` or `NO_JOB`, since a rerun of the
    check on the same commit may have passed."""
    known: dict[str, str] = read_json(run.state / "checks.json", {})
    if again and known.get(sha) in ("failed", NO_JOB):
        del known[sha]
    answer = _check(run, known, sha)
    write_json(run.state / "checks.json", known)
    return answer


def landed(run: Pass, last: str, main: str) -> list[str]:
    """Return the tips main went through since `last`, along first parents, as GitHub lists
    main's commits. The oldest comes first, and `main` is the newest.

    Where `last` is not on that line of first parents (no record yet, a main that was
    rewritten, more than `WAITING` tips, or no answer), it returns the tips back to the newest
    one whose check has ended."""
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


def account(run: Pass, unrun: str, passed: str) -> None:
    """Raise one decision about the account for `unrun`, the newest tip whose check started no
    job, unless one is raised already. Close it when `passed`, a tip whose check ran, passed. A
    tip that passed after `unrun` gives `unrun` empty."""
    path = run.state / ACCOUNT_FILE
    raised = read_json(path, {}).get("question")
    try:
        if passed and raised:
            questions.clear(run, raised, f"a run on main whose jobs ran passed at {passed[:12]}")
            path.unlink(missing_ok=True)
            raised = None
        if unrun and not raised:
            lines = DECISION.format(sha=unrun[:12], slug=ACCOUNT)
            one, _ = questions.park(run, ACCOUNT, lines)
            write_json(path, {"question": one.number})
    except Refused as refused:
        run.condition(ACCOUNT, f"the decision about CI that starts no job was not kept: {refused}")


def tell(run: Pass, client: Client, world: World) -> None:
    """Send the crew of a red pull request one message when main goes from red to green: the
    commit that fixed main may fix the pull request too.

    It tells only the crew of a pull request open under a slug jbus launched. Whoever works
    on any other pull request is not jbus's crew.
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
    green, check, waiting, stands, unrun = "", "", [], broken, ""
    for tip in dict.fromkeys(
        (
            *([stands] if stands else []),
            *(tip for tip in was.get("pending", []) if tip != main),
            *landed(run, last or "", main),
        )
    ):
        check = main_check(run, tip, again=tip in (main, stands))
        if check == "green":
            green, broken, waiting, unrun = tip, "", [], ""
        elif check == "failed":
            broken, waiting, unrun = tip, [], ""
        elif check == "pending":
            waiting.append(tip)
        elif check == NO_JOB:
            unrun = tip
    account(run, unrun, green)
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
        if stacks.unmoved(brief):
            continue
        thread = dispatch.thread_of(brief)
        if not thread:
            run.gate(slug, NO_THREAD, f"#{number}: {why}", key=f"{NO_THREAD} {fixed[:12]}")
            continue
        if rebase.held(run, client, world, slug, number, head):
            held.append(slug)
            continue
        if expedite.waits_on_cap(run, client, thread, slug, "its crew being told main moved"):
            owed = True
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
