"""`tell` keeps `main.json` and `checks.json`, the record of whether main is red, once a pass.

It tells no crew anything. A pull request that is red over a red main needs no message when main
is green again: `jmerge` judges it again by itself and asks GitHub to merge main into it
(`jmerge.cli.Repo.again`), and the new check's failure, if any, reaches the crew as any failure
does (`rebase.github`).

`tell` records the default branch's commit from pass to pass. `main.json` is the one record of
main's red tip, which `jmerge.mainjson` reads for a launch and for `jmerge`. `tell` keeps a red tip
there as `broken` until a green tip follows it. So `tell` loses no tip whose check had not ended
when the tip landed, and no second red tip either. It keeps the last tip whose check passed as
`green`.

`tell` keeps beside `broken` the tests that failed there, as `failed_at` reads them from the red
run's logs once for each red tip: `jbus.reverts` reads them to tell a flake from a culprit's own
red.

`landed` lists each tip main went through since the last pass, and `tell` looks at them in
order. A tip still counts when it failed or passed before any pass looked at it, even with a
newer tip on top of it. `tell` keeps a tip whose check has not ended as `pending`, and looks
at that tip again until the check of a later tip ends. A tip's check is main's own, and
`tell` reads it through `main_check`. Each pass asks again about a failed check at main's
tip, or at the red tip kept as `broken`: a rerun that passes on that same commit ends the
red there. `tell` asks the remote for main's commit on each pass, since no step of a pass is sure
to fetch.

A failed check at main's tip is not red at once: `main_check` reruns its failed push run once
(`watch._check`), and the tip is `pending` until the rerun ends. A pass on the rerun leaves the
tip green, with no `broken` kept and no fix row filed. A second failure, or a run rerun once
already, by jbus or by hand, is red as before.

A record that jbus wrote before `tell` stopped telling crews may keep `fixed`, the green tip that
ended the red while a message was owed, and `held`. `tell` reads `fixed` as the end of that red
and writes neither key again.

A tip whose check started no job (`watch.NO_JOB`, a spent Actions limit or a failed payment) is
neither red nor green: no code was judged, so it changes neither `broken` nor `green`, and
`watch` files no main-red row for it. It is a decision about the account, which no fix to the
code makes. `account` raises it once for the project, as a gate (`questions.park`), however many
runs start no job, and closes it (`questions.clear`) when a tip whose check ran passes.
`account.json` in the project's state keeps the question's number while it is raised.
"""

from __future__ import annotations

from jbus import Refused, questions, read_json, verbs, watch, write_json
from jbus.passes import Pass
from jbus.watch import NO_JOB, NOT_RED, _api, _check, _judged, _log_failed
from jmerge import mainjson
from jmerge.mainjson import SETTLED

WAITING = 10
CHECKS = "checks.json"
ACCOUNT, ACCOUNT_FILE = "ci-account", "account.json"
DECISION = (
    "## Gate <n>: CI on main started no job at {sha}: put the GitHub account's Actions limit "
    "or payment right?\n"
    "Status: open\n"
    "Asked by: {slug}, a jbus pass of mainmoved\n"
    "Default: jbus files no main-red row for a run that starts no job, and waits for a run "
    "whose jobs pass\n"
    "Built on it: main.json keeps its red and green tips as they were; no fix row is queued "
    "for {sha}\n"
    "Undo: none to take back: a run on main whose jobs pass closes this question\n"
    "Context: each failed check run at {sha} has a job that GitHub started on no runner and "
    "that ran no step, as on a spent Actions limit or a failed payment; no change to the code "
    "fixes that\n"
    "Option: wait for the account (default, recommended): no main-red row, and this question "
    "closes itself when a run with jobs passes\n"
    "Option: put it right now: pay or raise the limit on GitHub, then re-run the failed jobs "
    "at {sha}; this question closes when they pass"
)


def main_check(run: Pass, sha: str, again: bool = False, rerun: bool = False) -> str:
    """Return whether the checks of a commit on main passed, as `watch._check` answers.

    It goes through the answers `checks.json` keeps, so it asks GitHub for a final answer
    once. This module is the file's one writer. With `again`, it asks again about a kept
    `failed` or `NO_JOB`, since a rerun of the check on the same commit may have passed, and it
    reruns a cancelled run once (`watch._check`). With `rerun`, a failed push run at its first
    attempt is rerun once, and the commit is `pending` until the rerun ends."""
    known: dict[str, str] = read_json(run.state / CHECKS, {})
    if again and known.get(sha) in ("failed", NO_JOB):
        del known[sha]
    answer = _check(run, known, sha, again=again, rerun=rerun)
    write_json(run.state / CHECKS, known)
    return answer


def failed_at(run: Pass, sha: str) -> list[str] | None:
    """Return the tests that failed at a red tip of main, as its failed check runs' logs name
    them (`mainjson.failures`), or None where a log could not be read, so that the next pass
    asks again."""
    jobs = []
    for one in _judged(run, sha)[0]:
        if one.get("status") != "completed" or one.get("conclusion") in NOT_RED:
            continue
        found = _log_failed(run, one.get("id"))
        if found is None:
            return None
        jobs.append((str(one.get("name") or ""), found.tests, found.count))
    return mainjson.failures(jobs)


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


def tell(run: Pass) -> None:
    """Judge each tip main went through since the last pass, and write `main.json`: the red tip,
    the last green one and the tips still pending. A pass whose GitHub budget is at jbus's floor,
    or not known, runs no `tell` (`jbus.budget`)."""
    asked = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    default = asked.stdout.strip().removeprefix("origin/")
    if not default:
        return
    asked = run.run("git", "ls-remote", "origin", f"refs/heads/{default}")
    main = (asked.stdout.split() or [""])[0]
    if asked.returncode != 0 or not main:
        return
    was = mainjson.load(run.state) or {}
    last, broken = was.get("main"), was.get("broken", "")
    if main == last and was.get("check") == "green":
        return
    if was.get("fixed") or was.get("check") == "green":
        broken = ""
    green, check, waiting, stands, unrun = "", "", [], broken, ""
    for tip in dict.fromkeys(
        (
            *([stands] if stands else []),
            *(tip for tip in was.get("pending", []) if tip != main),
            *landed(run, last or "", main),
        )
    ):
        check = main_check(run, tip, again=tip in (main, stands), rerun=tip == main)
        if check == "green":
            green, broken, waiting, unrun = tip, "", [], ""
        elif check == "failed":
            broken, waiting, unrun = tip, [], ""
        elif check == "pending":
            waiting.append(tip)
        elif check == NO_JOB:
            unrun = tip
    account(run, unrun, green)
    at = (was.get("at") if main == last else "") or run.now.isoformat()
    failed = was.get("failed") if broken == was.get("broken") else None
    record = mainjson.record(
        main=main,
        at=at,
        check=check,
        broken=broken,
        failed=failed if failed is not None or not broken else failed_at(run, broken),
        pending=waiting[-WAITING:],
        green=green or mainjson.of(was).green,
    )
    write_json(run.state / mainjson.NAME, record)


STEPS = (
    verbs.Step(
        "after-expedite",
        10,
        "mainmoved.tell",
        lambda half: tell(half.run),
        ("budget",),
    ),
    verbs.Step(
        "after-expedite",
        11,
        "watch.retro",
        lambda half: watch.retro(
            half.run, half.seen.world, half.rows or [], lambda sha: main_check(half.run, sha)
        ),
        ("world",),
    ),
)
