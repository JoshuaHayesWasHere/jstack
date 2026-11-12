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

`tell` writes why main went red once for each tip it judges `failed`, as one line of
`main-reds.jsonl` in the project's state: the tip, the green tip it came `after`, the pull requests
landed since, the step each failed part of the run failed at, the tests the run failed, and a
`Verdict`, `change`, `flake` or `infra`. A later tip of the spell that fails only tests its lines
name is part of that spell and takes its first line's verdict (`red_line`). When main goes green,
`tell` writes one more line for the spell, at its first red tip: the green tip and the spell's
`cause`, `fix: #<n>` or `no fix` (`closing_line`), since only the end of a spell tells a break from
a flake. A fix is a fix row, a revert, or a pull request that changed a file a failed test runs
(`runs`). `tell` is the one owner of main's red, so its readers take the cause from the ledger and
keep no rule of their own: the store reads it for `main_spells.cause`, `change-failure` counts
only the spells a change caused, and `flakerow` counts as flakes only the spells with `no fix`. A
tip whose logs could not be read gets its line on a later pass that judges it, and a tip with a
line gets no second one.

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

import json
import re
from collections.abc import Collection, Sequence
from datetime import timedelta
from enum import StrEnum

from jbus import Refused, questions, read_json, reverts, verbs, watch, write_json
from jbus.ci.ledger import read as ledger
from jbus.passes import Pass
from jbus.watch import (
    NO_JOB,
    NOT_RED,
    _api,
    _check,
    _judged,
    _log_failed,
    job_log,
    unjudged,
    when,
)
from jmerge import mainjson
from jmerge.mainjson import SETTLED

WAITING = 10
CHECKS = "checks.json"
UNJUDGED = "unjudged.json"
"""The commits `main_check` found nothing judges (`watch.unjudged`), each with when a pass first
and last found it so: `{sha: [first, last]}`."""
UNJUDGED_WAIT = timedelta(minutes=15)
"""How far apart two reads that find nothing judges a commit settle it: GitHub lists a push run
within seconds of the push, so a commit that has none this long after it was first read never
will."""
UNJUDGED_OLD = timedelta(days=1)
"""How long a commit has been found unjudged before `again` reads it only once an
`UNJUDGED_EVERY`: a tip of main nothing has judged for a day is a project with no check to run."""
UNJUDGED_EVERY = timedelta(hours=1)
"""How often `again` reads a commit unjudged for `UNJUDGED_OLD`, so that a run that comes late, as
after check.yml is switched on again, is still judged."""
REDS = "main-reds.jsonl"
"""Why main went red: one line for each tip `tell` judged `failed`, as `red_line` writes it, and one
for each spell that ended, as `closing_line` writes it."""
TESTS, LINT = "test", "lint"
"""The last word of a failed step that ran the tests (`make test`, `make check: test`), and of one
that linted the tree (`make lint`, `prose lint`, `make check: lint`), as `jbus.ci.collect.step`
names a step: GitHub's name, with the make target that failed where the log names one."""
REVERT = "revert-"
"""How the branch of a revert starts, GitHub's `revert-<number>-<branch>` (`reverts.close`)."""
NO_FIX = "no fix"
"""The cause of a spell that went green with no fix row, no revert and no change to a file a test
it failed runs (`runs`) merged in it: a flake."""
PROSE = (".md", ".txt", ".rst")
"""The files a test reads as prose, if at all, which no fix of a red runs: with any file under a
`docs/` directory, a merge that changes only these fixes no failed test (`runs`)."""
PULL = re.compile(r"\(#(\d+)\)$")
"""A squash merge's subject ends in its pull request's number."""
UNCOLLECTED = re.compile(r"\bERROR collecting \S|\b\d+ errors? during collection\b")
"""pytest's word that it could not collect a test file, as on an ImportError or a syntax error in
the code: `ERROR collecting <path>`, and `Interrupted: <n> error during collection`."""


class Verdict(StrEnum):
    """Why main's check went red at a tip.

    `CHANGE`: the code is wrong, a test or the lint fails on it, or pytest could not collect a test
    file, and only a change to the code ends it. `FLAKE`: each test that failed is one `jbus ci`
    counts as a flake (`reverts.flaky`).
    `INFRA`: the run failed outside the code's own checks, at a step that is neither the tests nor
    the lint, or at the tests with no test named and every test file collected, as when the
    coverage file or the runner breaks."""

    CHANGE = "change"
    FLAKE = "flake"
    INFRA = "infra"


def verdict(
    steps: Collection[str],
    failed: Collection[str],
    flakes: Collection[str],
    uncollected: bool = False,
) -> Verdict:
    """The rule: why a red run failed, from the step each failed part failed at, the tests the run
    failed (`mainjson.failures`: none where any part fails no test it names), the tests
    `reverts.flaky` names, and whether pytest could not collect a test file (`uncollected`). A
    step not known, "", says nothing either way."""
    targets = {step.rsplit(" ", 1)[-1] for step in steps if step}
    if LINT in targets or uncollected:
        return Verdict.CHANGE
    if not failed or targets - {TESTS}:
        return Verdict.INFRA
    if all(test in flakes for test in failed):
        return Verdict.FLAKE
    return Verdict.CHANGE


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
    attempt is rerun once, and the commit is `pending` until the rerun ends.

    A commit nothing judges, with no push run and no check run of one (`watch.unjudged`), is
    `pending`. Passes read it again until a read `UNJUDGED_WAIT` after the first still finds it
    so, as `unjudged.json` keeps, and after that only with `again`, at main's tip or the red
    tip kept. Once a commit has been found so for `UNJUDGED_OLD`, `again` reads it at most once
    an `UNJUDGED_EVERY`, and it is `pending` between."""
    known: dict[str, str] = read_json(run.state / CHECKS, {})
    if again and known.get(sha) in ("failed", NO_JOB):
        del known[sha]
    seen: dict[str, list[str]] = read_json(run.state / UNJUDGED, {})
    first, last = seen.get(sha) or [run.now.isoformat()] * 2
    if not again and when(last) - when(first) >= UNJUDGED_WAIT:
        return "pending"
    if when(last) - when(first) >= UNJUDGED_OLD and run.now - when(last) < UNJUDGED_EVERY:
        return "pending"
    answer = _check(run, known, sha, again=again, rerun=rerun)
    write_json(run.state / CHECKS, known)
    if answer == "pending" and unjudged(run, sha):
        write_json(run.state / UNJUDGED, {**seen, sha: [first, run.now.isoformat()]})
    elif sha in seen:
        write_json(run.state / UNJUDGED, {k: v for k, v in seen.items() if k != sha})
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


def _failed_parts(run: Pass, sha: str) -> list[dict]:
    """The check runs that failed at a commit on main, less a run that only gathers others, as
    `full` gathers `full 1 of 4` (`mainjson.failures`)."""
    runs = [
        one
        for one in _judged(run, sha)[0]
        if one.get("status") == "completed" and one.get("conclusion") not in NOT_RED
    ]
    names = [str(one.get("name") or "") for one in runs]
    return [
        one
        for one, name in zip(runs, names, strict=True)
        if not any(other.startswith(f"{name} ") for other in names)
    ]


def failed_steps(run: Pass, sha: str) -> list[str]:
    """Return the step each failed part of main's check failed at, as `jbus ci` names it in
    `ci.jsonl` (`collect.step`), each once, "" where GitHub does not say."""
    from jbus.ci.collect import evidence, failed_step, step

    steps = []
    for one in _failed_parts(run, sha):
        job = watch.job(run, "{owner}/{repo}", str(one.get("id")))
        log = job_log(run, "{owner}/{repo}", one.get("id")) or ""
        steps.append(step(failed_step(job), evidence(log)) or "")
    return list(dict.fromkeys(steps))


def uncollected(run: Pass, sha: str) -> bool:
    """Return whether the log of a failed part of main's check says pytest could not collect a
    test file (`UNCOLLECTED`)."""
    return any(
        UNCOLLECTED.search(job_log(run, "{owner}/{repo}", one.get("id")) or "")
        for one in _failed_parts(run, sha)
    )


def pulls(run: Pass, tips: Sequence[str]) -> list[tuple[int, str, str]]:
    """Return the pull request merged at each tip, with its branch and the tip, as `merged.json`
    keeps them, else the number its commit's subject ends in, as GitHub lists main's commits."""
    merged: dict[str, dict] = read_json(run.state / "merged.json", {})
    kept = {
        (one.get("mergeCommit") or {}).get("oid"): (one.get("number"), one.get("headRefName", ""))
        for one in merged.values()
        if isinstance(one, dict)
    }
    said = _api(run, f"repos/{{owner}}/{{repo}}/commits?sha={tips[-1]}&per_page={WAITING}")
    subjects = {
        one.get("sha"): str((one.get("commit") or {}).get("message", "")).split("\n")[0]
        for one in (said if isinstance(said, list) else [])
        if isinstance(one, dict)
    }
    found = []
    for tip in tips:
        number, branch = kept.get(tip, (None, ""))
        if number is None and (named := PULL.search(subjects.get(tip, ""))):
            number = named[1]
        if number is not None:
            found.append((int(number), str(branch or ""), tip))
    return found


def spell(lines: list[dict], green: str) -> list[dict]:
    """The lines of `REDS` that judged a red tip of the spell since `green`, the last green tip,
    the first first: each line `red_line` writes keeps the green tip it came `after`. A line from
    before `after` was kept belongs to no spell."""
    return [one for one in lines if "verdict" in one and "after" in one and one["after"] == green]


def red_line(
    run: Pass, tip: str, green: str, failed: list[str], opened: Sequence[dict] = ()
) -> dict:
    """The line of `REDS` for a tip judged `failed`, with `green` the last green tip before it,
    `failed` the tests that failed there and `opened` the open spell's lines, the first first.

    A tip that fails only tests the spell's lines name is part of that spell, the same break or
    the same flake with merges on top of it, and takes its first line's verdict: `reverts.flaky`
    would name its tests a flake by then, since the pull requests checked over the red main fail
    them on their own branches before `jbus ci` holds main's own red run, which makes their
    failure main's. So it judged jstack's 8b6c51f76 and 54d9f0055, second reds of two real
    faults."""
    landed_ = pulls(run, landed(run, green, tip) if green else [tip])
    steps = failed_steps(run, tip)
    named = {test for one in opened for test in one.get("failed") or []}
    if opened and failed and set(failed) <= named:
        judged = str(opened[0]["verdict"])
    else:
        flakes = reverts.flaky(run, landed_[0][1]) if landed_ and failed else frozenset[str]()
        judged = str(verdict(steps, failed, flakes, uncollected(run, tip)))
    return {
        "at": run.now.isoformat(),
        "sha": tip,
        "after": green,
        "prs": [number for number, _, _ in landed_],
        "step": ", ".join(steps),
        "failed": failed,
        "verdict": judged,
    }


def changed(run: Pass, tip: str) -> set[str]:
    """Return the files the commit `tip` changed, as GitHub lists them, none where it gives no
    answer."""
    said = _api(run, f"repos/{{owner}}/{{repo}}/commits/{tip}")
    files = said.get("files") if isinstance(said, dict) else None
    return {str(one.get("filename")) for one in files or [] if isinstance(one, dict)}


def runs(test: str, path: str) -> bool:
    """Return whether a change to the file `path` can change how the failed test `test` runs: it
    is the test's own file, or a file of the test's feature, the directory that holds its `tests`
    directory, that is no other test file (`test_*`) and no doc (`PROSE`). So #1628's `fake-gh`,
    the script `features/verify-jstack/tests` drive, fixed jstack's spell 43, while #1649's new
    test file in `features/repo-guards/tests` did not end spell 45, a flake of another test
    there."""
    own = test.split("::")[0]
    if path == own:
        return True
    parts = own.split("/")
    root = "/".join(parts[: parts.index("tests")]) if "tests" in parts[:-1] else ""
    inside = not root or path.startswith(f"{root}/")
    name = path.rsplit("/", 1)[-1]
    prose = path.endswith(PROSE) or "docs/" in f"/{path}"
    return inside and not name.startswith("test_") and not prose


def closing_line(run: Pass, first: str, green: str, failed: Collection[str] = ()) -> dict:
    """The line of `REDS` that closes the spell whose first red tip is `first` at `green`, the
    tip whose check passed, with `failed` the tests the spell's red tips failed: the pull requests
    merged after `first` up to `green`, and its `cause`. That is `fix: #<n>` where one of them is
    a fix row (`mainjson.FIX`), a revert (`REVERT`), or a pull request that changed a file a test
    in `failed` runs (`runs`), as an ordinary row that fixed the break does, the last such;
    `NO_FIX` where none is. Only a merge that is neither a fix row nor a revert is asked for its
    files, one call each, once a spell. A rerun that passed at `first` merged nothing: `NO_FIX`."""
    merged = pulls(run, landed(run, first, green)) if green != first else []
    fixes = [
        number
        for number, branch, tip in merged
        if branch.startswith((mainjson.FIX, REVERT))
        or (failed and any(runs(test, path) for path in changed(run, tip) for test in failed))
    ]
    return {
        "at": run.now.isoformat(),
        "sha": first,
        "green": green,
        "prs": [number for number, _, _ in merged],
        "cause": f"fix: #{fixes[-1]}" if fixes else NO_FIX,
    }


def close(run: Pass, under: str, green: str) -> None:
    """Append the closing line of the spell since `under` that `green` ends, once: none where
    the spell has no line, or its first line has a closing line already."""
    lines = ledger(run.state / REDS)
    opened = spell(lines, under)
    if not opened or any("cause" in one and one.get("sha") == opened[0]["sha"] for one in lines):
        return
    with open(run.state / REDS, "a") as handle:
        failed = [test for one in opened for test in one.get("failed") or []]
        line = closing_line(run, str(opened[0]["sha"]), green, list(dict.fromkeys(failed)))
        handle.write(json.dumps(line) + "\n")


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
    or not known, runs no `tell` (`jbus.budget`). Main's tip is the one `git ls-remote` gives
    the pass (`Pass.tip`)."""
    main = run.tip()
    if not main:
        return
    was = mainjson.load(run.state) or {}
    last, broken = was.get("main"), was.get("broken", "")
    if main == last and was.get("check") == "green":
        return
    if was.get("fixed") or was.get("check") == "green":
        broken = ""
    green, check, waiting, stands, unrun = "", "", [], broken, ""
    under, tests, judged = mainjson.of(was).green, {}, None
    for tip in dict.fromkeys(
        (
            *([stands] if stands else []),
            *(tip for tip in was.get("pending", []) if tip != main),
            *landed(run, last or "", main),
        )
    ):
        check = main_check(run, tip, again=tip in (main, stands), rerun=tip == main)
        if check == "green" and tip != under:
            close(run, under, tip)
        if check == "green":
            green, broken, waiting, unrun, under = tip, "", [], "", tip
        elif check == "failed":
            broken, waiting, unrun = tip, [], ""
            if judged is None:
                judged = {str(one.get("sha")) for one in ledger(run.state / REDS)}
            if tip not in judged and (read := failed_at(run, tip)) is not None:
                tests[tip] = read
                opened = spell(ledger(run.state / REDS), under)
                line = red_line(run, tip, under, read, opened)
                with open(run.state / REDS, "a") as handle:
                    handle.write(json.dumps(line) + "\n")
        elif check == "pending":
            waiting.append(tip)
        elif check == NO_JOB:
            unrun = tip
    account(run, unrun, green)
    at = (was.get("at") if main == last else "") or run.now.isoformat()
    failed = was.get("failed") if broken == was.get("broken") else None
    if failed is None and broken:
        failed = tests[broken] if broken in tests else failed_at(run, broken)
    record = mainjson.record(
        main=main,
        at=at,
        check=check,
        broken=broken,
        failed=failed,
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
