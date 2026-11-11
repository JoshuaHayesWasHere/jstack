"""`revert` reverts the one clear culprit of a red main, and says why it reverts nothing otherwise.

A red main holds no pull request (`jmerge`, "Main is not red"). Josh chose guess-free reverts on
2026-11-02: once main's tip is red after its one rerun (#672, `watch._check`), jbus reverts the
merge that turned it red only when one culprit is clear, and otherwise files the fix row that a
red main got before (`watch._file`), for the owner to fix.

`culprit` is the rule, a pure function of what `watch.retro` reads of main. It judges the red
run: every commit since the last green, newest first, main's tip first. One culprit is clear when
the run's oldest commit, the first red after the last green, is the merge commit of a briefed pull
request, and every later tip of the run failed no test outside the ones that failed there
(`covered`), the same comparison `watch._file` makes for one fix row per break (#962). The later
merges landed on that red and broke nothing more, so the oldest is the culprit, as #334 was on
2026-10-23 with four merges on top of it. It reverts nothing, and says which `Keep` holds:

- `OVERLAP`: a later tip failed a test that did not fail at the oldest, or named none, as when two
  reds overlap; or a commit of the run ended neither red nor green; or no green is in reach. A
  commit whose push run a newer push displaced (`watch.BATCHED`) is one of those: pushes to main
  share one concurrency group, so one run checks every merge since the last run that ran, and a
  red over a batch of merges shows no one of them to be the break. The fix row names every red
  tip among them.
- `UNREAD`, besides the case below: a commit of the run whose check has not ended is no second red
  yet, as #864's under 52b82e7 on 2026-11-02, so the next pass judges the run again. Once the tip
  is older than `READ_WAIT`, it is `OVERLAP`.
- `UNBRIEFED`: the oldest is no briefed merge's commit, such as a merge by hand.
- `OF_A_REVERT`: the oldest is a revert, jbus's or anyone's: a revert that goes red is not reverted.
- `TWICE`: jbus reverted the same slug before, so a row is never reverted twice.
- `FLAKES`: each test that failed at the oldest is a flake by `jbus ci`'s rule (`flaky`).

`tested` adds one more, on what GitHub says: `SKEW`, where the culprit's own head lacks the green
commit under the oldest red, so its check passed over a main without that merge. Each merge passed
alone and the two went red together, as #864 and #866 did on 2026-11-02, so neither is the one
culprit. Where GitHub does not say, the tip waits as `UNREAD` does, and gets its row as
`UNANSWERED` once it is older than `READ_WAIT`.

A red run with a commit jbus already opened a revert for is `OPENED`: nothing more is done for it,
no row either, while its revert's pull request goes the normal path, and `stuck` says when it no
longer does: closed unmerged, in conflict, with a failed check, or merged with main still red, and
the tip gets its row. A tip whose
failed tests `mainmoved.tell` could not read yet, earlier in the same pass, is `UNREAD`: the next
pass judges it, and nothing is done for it in this one. Once the tip is older than `READ_WAIT` its
logs are taken as unreadable, `NOT_READ`, and it gets its row.

`revert` acts on a clear culprit. `gh pr revert` makes the revert on GitHub, a new commit on a new
branch, so jbus never pushes to main or force-pushes anything. It keeps the revert in
`reverts.json` (`jmerge.reverts`), with the check that went red as its one holder, writes the
brief `tasks/<branch>.md` that ties the pull request to its slug, with the culprit's home, and
logs a routine event for its home's digest.
`jbus.culprits.tell` tells the culprit's crew, from every pass until the message goes, so a capped
thread or a T3 Code that gives no answer loses it to nothing. `opened` asks GitHub for the
revert's branch first, so a pass that stopped between GitHub's answer and the record opens no
second one. `revert` names the revert in `OPENING` before GitHub opens it, and `known`, early in
every pass, keeps each revert named there that has no record yet, whether main is red or green,
so a revert a pass opened and then stopped is never left open with no record. The record is the
last write (`_own`), after the brief and the line, so a revert on record has both. `jmerge`
merges the revert by the normal path, its checks green, with no review.
A revert is held by each check that leans on it (`holders`): the one that went red and opened it,
and each that went red at the same commits and read it as its own since (`Keep.OPENED`, `lean`),
as main's macOS run did on main's revert #1426 on 2026-11-09. `close` closes a revert jbus opened
that is still open once every holder passed at its red or a later commit, as when a fix row merged
first, with a comment that names each green: it would only sit in conflict with main. Closing it
on one holder's green while another is still red there closed #1426 under a red Mac, and the Mac
then opened #1427 on the same branch. A closed revert keeps its record, so a check that goes red
at its commits later leans on it and files a fix row, and the row is never reverted twice. `close`
drops the record once main is green, the revert's pull request is no longer open, every check jbus
judges main by here passed at or above its red, and its culprit's slug is over: no pull request
of it is open, no thread of it is unsettled and its row, if the queue still has one, is final. A
slug that is over merges nothing more, so its record holds nothing, and `TWICE` no longer files a
fix row for a later red that is due a revert.

`macos` judges main's Mac by the same rule. macos.yml's push runs share one group, as main's check
does, so a run selects over every merge since the last Mac run that ran, and a commit whose run a
newer push displaced ends `cancelled`, neither green nor red. That run is never main's check
(`watch._judged`): a Mac red writes nothing to `main.json` and holds no pull request. After its
one rerun (`watch.mac_check`), the newest red commit and every one since the last Mac green are a
`Red`, with the Mac run's failed tests:
`culprit`, `tested` and `covered` judge it, a clear culprit is reverted, and anything else files
the row `macos-red-<commit>` under the home `macos`. A revert the Mac opened or leans on holds on
the Mac, so it is closed only once the Mac is green at a later commit (`MAC_MAIN`).
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from jbriefs import below
from jbriefs import home as homes
from jbus import Refused, queue, read_json, verbs, watch, work, write_json
from jbus.ci.ledger import JOBS, PULLS
from jbus.ci.ledger import read as ledger
from jbus.ci.numbers import Facts, flake_branches
from jbus.passes import Pass
from jbus.watch import World, brief_of, copy_brief, fix_brief, task_brief, tests_said, when
from jmerge import mainjson
from jmerge import reverts as kept

EVENTS = {"revert": "quiet"}
READ_WAIT = timedelta(hours=1)
"""How long after a red tip landed its failed tests may stay unread, a CI round and its rerun with
room to spare, before they are taken as unreadable."""
FLAKE_WINDOW = timedelta(days=7)
"""How far back `flaky` reads `jbus ci`'s ledger for the tests that failed on another branch."""
REVERTED = 'Revert "'
"""How a revert's title starts, GitHub's and jbus's."""
MAIN = "main"
MAC = "main's macOS"
"""What went red: main's check, or macos.yml's run on a merge commit into main (`macos`)."""
MAC_CHECKS = "macos-checks.json"
"""The final answers of macos.yml's push runs, by commit (`watch.mac_check`)."""
MAC_MAIN = "macos-main.json"
"""main's last Mac answer, as `macos` read it: `red`, the newest commit whose Mac run ended red,
or empty once a newer one is green; `green`, the newest green one. A project with no Mac has no
such file."""
CHECKS = (MAIN, MAC)
"""Every check that can hold a revert (`holders`)."""
HOLDERS = "holders"
"""The key in each record of `reverts.json` that names the checks holding its revert, each of
`CHECKS`. jmerge reads the file's other keys alone (`jmerge.reverts.read`)."""
MAC_FIX = "macos-red-"
MAC_WALK = 20
"""How many of main's newest commits `macos` reads, newest first."""
NO_MAC_AFTER = timedelta(hours=1)
"""How long after a commit landed a missing macos.yml run is taken as none, and not as one GitHub
has yet to list."""


class Keep(enum.StrEnum):
    """Why a red tip of main is not reverted."""

    OPENED = "jbus already opened its revert"
    UNREAD = "what failed there, or what main its own check passed over, is not read yet"
    OVERLAP = "two reds overlap: the merges since the last green are not shown to be one break"
    UNBRIEFED = "it is no briefed merge's commit"
    OF_A_REVERT = "it is a revert, and a revert that goes red is not reverted"
    TWICE = "jbus reverted this row before, and a row is never reverted twice"
    FLAKES = "each test that failed there is a flake by jbus ci's rule"
    NOT_READ = "the tests that failed there could not be read from its logs"
    SKEW = (
        "two merges went red together: its own check passed over a main that lacked the merge "
        "under it"
    )
    UNANSWERED = "GitHub did not say what main its own check passed over"


@dataclass(frozen=True)
class Culprit:
    """The one clear culprit of a red tip: the briefed merge whose commit it is."""

    red: str
    slug: str
    pull: dict[str, Any]


@dataclass(frozen=True)
class Red:
    """What `watch.retro` read of a red tip of main, after its one rerun: each commit since the
    last green, newest first, the tip first, with what main's check says there (`watch._check`:
    `failed`, `pending` and the rest); the briefed pull request merged at the oldest and its slug,
    and the tests that failed there, None where they are not read yet; how long ago the tip
    landed; and the green commit under the oldest, or nothing where none is in reach."""

    since: Sequence[tuple[str, str]]
    pull: dict[str, Any] | None
    slug: str
    failed: Sequence[str] | None
    age: timedelta = timedelta(0)
    under: str = ""

    @property
    def tip(self) -> str:
        return self.since[0][0]

    @property
    def oldest(self) -> str:
        return self.since[-1][0]


def culprit(red: Red, made: dict[str, kept.Revert], flakes: Collection[str]) -> Culprit | Keep:
    """The rule: the one clear culprit of `red`, or why none is reverted. `made` is every revert
    jbus opened (`jmerge.reverts`), and `flakes` the tests `flaky` names."""
    if any(sha in made for sha, _ in red.since):
        return Keep.OPENED
    if any(check == "pending" for _, check in red.since):
        return Keep.OVERLAP if red.age > READ_WAIT else Keep.UNREAD
    if len(red.since) > 1 and (not red.under or any(check != "failed" for _, check in red.since)):
        return Keep.OVERLAP
    if red.pull is None or not red.slug:
        return Keep.UNBRIEFED
    if red.slug in {one.branch for one in made.values()} or str(
        red.pull.get("title", "")
    ).startswith(REVERTED):
        return Keep.OF_A_REVERT
    if red.slug in {one.slug for one in made.values()}:
        return Keep.TWICE
    if red.failed is None:
        return Keep.NOT_READ if red.age > READ_WAIT else Keep.UNREAD
    if red.failed and all(test in flakes for test in red.failed):
        return Keep.FLAKES
    return Culprit(red.oldest, red.slug, red.pull)


def covered(found: Culprit, red: Red, later: Iterable[Sequence[str] | None]) -> Culprit | Keep:
    """`found`, the merge at the oldest commit of `red`, where each later tip failed no test
    outside the ones that failed at the oldest: one break, with merges on top of it. `OVERLAP`
    where one failed another test, or names none, as a lint or a timeout does, so it may be a
    break of its own; `UNREAD`, then `NOT_READ` once the tip is older than `READ_WAIT`, where a
    tip's tests are not read yet. `later` gives each later tip's failed tests, None where they
    could not be read, and is read only up to the first tip that settles it."""
    for tests in later:
        if tests is None:
            return Keep.NOT_READ if red.age > READ_WAIT else Keep.UNREAD
        if not red.failed or not tests or not set(tests) <= set(red.failed):
            return Keep.OVERLAP
    return found


def tested(run: Pass, found: Culprit, under: str, age: timedelta) -> Culprit | Keep:
    """`found`, where its own head holds `under`, the green commit under the red tip, so its
    check passed over the main it turned red, or why it is not reverted: `SKEW` where its head
    lacks it, and `UNREAD`, then `UNANSWERED` once the tip is older than `READ_WAIT`, where
    GitHub does not say."""
    head = str(found.pull.get("headRefOid", ""))
    status = compared(run, under, head)
    if not (under and head) or status not in ("ahead", "identical", "behind", "diverged"):
        return Keep.UNANSWERED if age > READ_WAIT else Keep.UNREAD
    return found if status in ("ahead", "identical") else Keep.SKEW


def compared(run: Pass, base: str, head: str) -> str | None:
    """GitHub's status of `head` against `base`, such as `ahead` where `head` holds `base`, or
    None where GitHub does not say."""
    asked = run.run("gh", "api", f"repos/{{owner}}/{{repo}}/compare/{base}...{head}")
    try:
        return json.loads(asked.stdout).get("status") if asked.returncode == 0 else None
    except (ValueError, AttributeError):
        return None


def flaky(run: Pass, branch: str) -> frozenset[str]:
    """The tests `jbus ci` counts as flakes over the last `FLAKE_WINDOW` (`numbers.flaky`'s rule:
    each failed on two branches with no runner fault and no red main to blame), where `branch`,
    the culprit's own, is not one of the two: its own red is no flake."""
    state = run.state
    facts = Facts(
        ledger(state / JOBS), ledger(state / PULLS), ledger(state / "events.jsonl"), run.now
    )
    found = flake_branches(facts, run.now - FLAKE_WINDOW, run.now)
    return frozenset(test for test, branches in found.items() if len(branches - {branch}) > 1)


def brief(branch: str, red: Culprit, url: str, home: str, where: str = MAIN) -> str:
    """The brief jbus writes for its revert, which ties the pull request to its slug: its Result
    names the pull request on its `Branch:` line. `where` is what went red."""
    number = red.pull.get("number")
    return "\n".join(
        [
            f"# {branch}: revert {red.slug} (#{number}), which turned {where} red at "
            f"{red.red[:12]}",
            f'Task: "{where} check failed at {red.red[:12]}" after its one rerun, the first red '
            "since the last green, and no merge on top of it failed another test (jbus reverts its "
            "one clear culprit, Josh's pick of 2026-11-02)",
            "Why: while main is red jmerge merges nothing, and taking the one clear culprit out "
            "is the shortest way back to green, its own row fixing it again after",
            "Pull request: opened by jbus with `gh pr revert`",
            "Review: none needed, jmerge merges jbus's revert by the normal path (jmerge.reverts)",
            f"Home: {home}",
            "",
            "## Result",
            "Status: done",
            f"Branch: {branch}   Pull request: {url}",
            "",
        ]
    )


FIELDS = "url,headRefName,headRefOid"
"""What `revert` reads of a revert's pull request."""
OPENING = "reverts-opening.json"
"""The reverts a pass set out to open and `reverts.json` does not keep yet, by red tip: the
culprit's slug and number, the revert's branch, what went red (`where`) and when (`at`). `revert`
writes it before `gh pr revert` and drops it once the record is written, so a pass that stopped
in between leaves its revert named here, and `known` keeps it on the next pass. It is how a pass
tells a revert of its own from one a hand opened on the same branch, which `known` never keeps."""


def branch_of(pull: dict[str, Any]) -> str:
    """The branch GitHub gives the revert of `pull`: `revert-<number>-<branch>`."""
    return f"revert-{pull.get('number')}-{pull.get('headRefName')}"


def opened(run: Pass, branch: str) -> dict[str, str] | None:
    """The open pull request GitHub has on the revert's `branch`, nothing where it has none, or
    None where GitHub gave no answer."""
    asked = run.run("gh", "pr", "list", "--state", "open", "--head", branch, "--json", FIELDS)
    try:
        found = json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        found = None
    if not isinstance(found, list):
        return None
    return found[0] if found and isinstance(found[0], dict) else {}


def home_of_revert(culprit: str) -> str:
    """The `Home:` line of a revert's brief: the scope the brief of the row it reverts names, and
    the catch-all's, `uncategorized`, where that names none or the root, which owns no row."""
    named = below.line(culprit, "Home:")
    return named if named and named != homes.ROOT else homes.UNCATEGORIZED


def revert(run: Pass, red: Culprit, where: str = MAIN) -> bool:
    """Open the revert of `red`, or take the one GitHub has, and keep it (`_own`), which
    `jbus.culprits` tells the culprit's crew. Return False where GitHub did not open it, so the
    caller files the fix row instead. `where` is what went red: main's check, or its macOS run.
    The revert is named in `OPENING` before GitHub is asked to open it."""
    branch = branch_of(red.pull)
    said = opened(run, branch) or {}
    if not said:
        _intend(run, red, branch, where)
        url = str(red.pull.get("url", ""))
        asked = run.run(
            "gh",
            "pr",
            "revert",
            url,
            "--body",
            f"jbus reverts this: {where} went red at {red.red[:12]} and stayed red after its "
            "one rerun. It was the first red since the last green, and no merge on top of it "
            "failed another test.",
        )
        lines = asked.stdout.strip().splitlines()
        made = lines[-1].strip() if asked.returncode == 0 and lines else ""
        if not made:
            _drop_intent(run, red.red)
            why = (asked.stderr or "no answer").strip()
            run.condition(red.slug, f"its revert was not opened: {why}", key=f"revert {red.red}")
            return False
        viewed = run.run("gh", "pr", "view", made, "--json", FIELDS)
        try:
            said = json.loads(viewed.stdout) if viewed.returncode == 0 else {}
        except ValueError:
            said = {}
        if not (said.get("headRefName") and said.get("headRefOid")):
            line = f"its revert {made} opened, and GitHub does not say its branch yet"
            run.condition(red.slug, line, key=f"listed {red.red}")
            return True
    _own(run, red, said, where)
    return True


def _own(run: Pass, red: Culprit, said: dict[str, Any], where: str) -> None:
    """Keep the revert GitHub has open for `red`, as `said` describes it: its brief, then its line
    in `events.jsonl`, then its record in `reverts.json`, which every later pass reads as the
    revert being its own (`Keep.OPENED`), and last its name leaves `OPENING`. A pass that stops
    before the record leaves the revert in `OPENING`, and the next one keeps it again: it writes
    the brief again, and the line, sent by its key, is not sent twice. So a revert on record has
    its brief and its line (`features/jbus/spec/MainFix.tla`, `RevertSaid`)."""
    branch, head, url = (str(said.get(key, "")) for key in ("headRefName", "headRefOid", "url"))
    home = home_of_revert(task_brief(run, red.slug))
    tasks = run.home / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / f"{branch}.md").write_text(brief(branch, red, url, home, where))
    line = f"revert {red.slug}: {where} red at {red.red[:12]}, jbus opened {url} to revert it"
    if run.find(red.slug, "revert", line, key=f"opened {red.red}"):
        run.say(line)
    made, held = kept.read(run.state), holders(run.state)
    made[red.red] = kept.Revert(red.red, red.slug, branch, head, url)
    _keep(run, made, {**held, red.red: {where}})
    _drop_intent(run, red.red)


def _intend(run: Pass, red: Culprit, branch: str, where: str) -> None:
    """Name the revert of `red` in `OPENING`, before GitHub is asked to open it."""
    intents = read_json(run.state / OPENING, {})
    intents = intents if isinstance(intents, dict) else {}
    one = {"slug": red.slug, "number": red.pull.get("number"), "branch": branch, "where": where}
    write_json(run.state / OPENING, {**intents, red.red: {**one, "at": run.now.isoformat()}})


def _drop_intent(run: Pass, red: str) -> None:
    """Take the revert of the red tip `red` out of `OPENING`."""
    intents = read_json(run.state / OPENING, {})
    if isinstance(intents, dict) and red in intents:
        write_json(run.state / OPENING, {key: one for key, one in intents.items() if key != red})


def known(run: Pass, world: World) -> None:
    """Keep each revert `OPENING` names that `reverts.json` does not, whether main is red or green
    and whatever GitHub's compare says: a pass stopped after GitHub opened it and before its
    record, and no later pass may judge main red again to find it (`features/jbus/spec/MainFix.tla`,
    `RevertKnown`), while jmerge merges, and `close` closes, only a revert on record. The revert
    is found on its branch among the open pull requests this pass read (`world.open`), and else
    by asking GitHub for the branch. Its name is dropped where the record is there already, and
    where GitHub answers that the branch has no open pull request once the name is older than
    `READ_WAIT`, since GitHub may list a revert it just opened late; it stays while GitHub gives
    no answer. A revert a hand opened on such a branch, with no name here, is never kept."""
    intents = read_json(run.state / OPENING, {})
    if not isinstance(intents, dict):
        return
    made = kept.read(run.state)
    heads = {str(pull.get("headRefName", "")): pull for pull in world.open.values()}
    for red, one in intents.items():
        if red in made or not isinstance(one, dict) or not one.get("branch"):
            _drop_intent(run, red)
            continue
        said = heads.get(str(one["branch"]))
        if said is None:
            said = opened(run, str(one["branch"]))
        if said is None:
            continue
        if said.get("headRefName") and said.get("headRefOid") and said.get("url"):
            where = str(one.get("where", MAIN))
            culprit = Culprit(red, str(one.get("slug", "")), {"number": one.get("number")})
            _own(run, culprit, said, where if where in CHECKS else MAIN)
        elif not said and run.now - when(str(one.get("at") or run.now.isoformat())) > READ_WAIT:
            _drop_intent(run, red)


def holders(state: Path) -> dict[str, set[str]]:
    """The checks that hold each revert jbus opened, by its red tip. A record that names none,
    as one kept before holders were, is held by every check, so none closes it too early."""
    raw = read_json(state / kept.NAME, {})
    found = {}
    for red in kept.read(state):
        named = raw[red].get(HOLDERS)
        checks = {one for one in named if one in CHECKS} if isinstance(named, list) else set()
        found[red] = checks or set(CHECKS)
    return found


def _keep(run: Pass, made: dict[str, kept.Revert], held: dict[str, set[str]]) -> None:
    """Write `made` to `reverts.json`, each revert with the checks `held` names as holding it."""
    write_json(
        run.state / kept.NAME,
        {
            red: {**kept.record(one), HOLDERS: sorted(held.get(red) or CHECKS)}
            for red, one in made.items()
        },
    )


def lean(run: Pass, since: Sequence[str], check: str) -> None:
    """Make `check`, red over the commits `since`, newest first, one of the holders of the newest
    revert jbus opened among them, which it reads as its own (`Keep.OPENED`), so `close` waits
    for it too. Where it holds one of them already, it waits on that one alone."""
    held = holders(run.state)
    opened = [red for red in since if red in held]
    if opened and not any(check in held[red] for red in opened):
        held[opened[0]].add(check)
        _keep(run, kept.read(run.state), held)


def stuck(
    run: Pass, one: kept.Revert, checks: Callable[[dict[str, Any]], str], above: bool = False
) -> str:
    """Why the revert on record for a red tip will not end the red by itself, or nothing: its
    pull request closed unmerged, conflicts or has a failed check, or merged while main is still
    red at a later tip, `above` the one it reverts. Nothing where GitHub gives no answer, as the
    next pass asks again."""
    fields = "state,mergeable,statusCheckRollup"
    asked = run.run("gh", "pr", "view", one.pull, "--json", fields)
    try:
        said = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except ValueError:
        said = {}
    if said.get("state") == "CLOSED":
        return f"its revert {one.pull} closed unmerged"
    if said.get("state") == "MERGED" and above:
        return f"its revert {one.pull} merged, and main is still red"
    if said.get("state") == "OPEN" and said.get("mergeable") == "CONFLICTING":
        return f"its revert {one.pull} conflicts with main"
    if said.get("state") == "OPEN" and checks(said) == "failed":
        return f"its revert {one.pull} has a failed check"
    return ""


def close(run: Pass, world: World, rows: list[dict[str, Any]] | None) -> None:
    """Close each revert jbus opened that is still open once every check holding it (`holders`)
    passed at its red or a later commit, with a comment that names each green. `main.json` keeps
    the red tip until a later tip is green, and `MAC_MAIN` keeps the Mac's red until a later
    commit is green, so a check red now has no green above the red; GitHub's compare orders a
    green against the red (`cleared`). Main may also be red again at a newer tip by the time a
    pass sees that green, and `culprits.judge` then opens the revert of the new red: a revert
    whose red is `green` or older is closed all the same, so one revert is open at a time
    (`MainRed.tla`'s `OneRevertOpen`). A pull request GitHub would not close is a condition,
    and the next pass tries again. A revert not in `world.open`, closed or opened in this pass
    after `world` was read, is not closed. While main is green, a revert no longer open is
    dropped from the record once every check jbus judges main by here passed at or above its red
    and its culprit's slug is over (`over`); with no queue read (`rows` is None) none is."""
    main = mainjson.read(run.state)
    if not main.green:
        return
    mac = read_json(run.state / MAC_MAIN, {})
    greens = {MAIN: main.green}
    if mac:
        greens[MAC] = "" if mac.get("red") else str(mac.get("green", ""))
    names = {MAIN: "main's check", MAC: "main's macOS run"}

    def passed(red: str) -> dict[str, str]:
        """Each check here, with the commit at or above `red` where it passed, or nothing."""
        return {
            check: green if green and cleared(run, red, green) else ""
            for check, green in greens.items()
        }

    urls = {str(pull.get("url", "")).rstrip("/") for pull in world.open.values()}
    made, held = kept.read(run.state), holders(run.state)
    ended = [red for red, one in made.items() if one.pull.rstrip("/") not in urls]
    gone = [
        red
        for red in ended
        if not main.red
        and rows is not None
        and over(made[red].slug, world, rows)
        and all(passed(red).values())
    ]
    if gone:
        _keep(run, {red: one for red, one in made.items() if red not in gone}, held)
    for one in made.values():
        if one.red in ended:
            continue
        green = passed(one.red)
        holding = sorted(check for check in held[one.red] if check in green)
        if not holding or not all(green[check] for check in holding):
            continue
        said = " and ".join(f"{names[check]} passed at {green[check][:12]}" for check in holding)
        comment = (
            f"jbus closes this: {said}, at or above the red {one.red[:12]} it reverts, so main "
            "passed without it."
        )
        asked = run.run("gh", "pr", "close", one.pull, "--comment", comment)
        if asked.returncode != 0:
            why = (asked.stderr or "no answer").strip()
            run.condition(one.slug, f"its revert {one.pull} was not closed: {why}")
            continue
        line = f"revert {one.slug}: {said}, jbus closed {one.pull}"
        run.find(one.slug, "revert", line, key=f"closed {one.red}")
        run.say(line)


def cleared(run: Pass, red: str, green: str) -> bool:
    """Whether a check passed at `red` itself or at a later commit, `green`, as GitHub
    compares them. Where GitHub does not say, it did not, and the next pass asks again."""
    return compared(run, red, green) in ("ahead", "identical")


def over(slug: str, world: World, rows: list[dict[str, Any]]) -> bool:
    """Whether the culprit's slug can merge nothing more: no pull request of it is open, no
    thread of it is unsettled, and its row, if the queue has one, is final."""
    row = next((row for row in rows if row.get("slug") == slug), None)
    final = row is None or work.over(row)
    return final and slug not in world.open and not world.threads.get(slug)


QUIET = (Keep.OPENED, Keep.UNREAD)
"""The `Keep`s for which a pass files no row: the revert is open, or the next pass judges it."""


def macos(run: Pass, world: World) -> None:
    """Judge main's Mac as `culprit` judges main's check, one merge commit at a time.

    macos.yml runs on pushes to main over every merge since its last run that ran, one run going
    and the newest push waiting, so a displaced commit's run ends `cancelled` (`watch.mac_check`
    reads it, and reruns a failed run once). Its
    run is no part of main's check (`watch._judged`), so a Mac red never writes `main.json` and
    holds no pull request. `macos` reads the newest of main's commits whose Mac run ended green or
    red; a run that skipped its Mac judged nothing on a Mac, and is passed over, neither a green
    nor a red. A red one, with every commit since the last Mac green that ran, is a `Red`: its one
    clear culprit is reverted (`revert`), as main's is, and otherwise it gets the fix row
    `macos-red-<commit>` under the home `macos`, which says why nothing was reverted. A revert
    opened here, or one this red reads as its own (`lean`), holds on the Mac, so `close` closes
    it only once the Mac is green at a later commit. On a project's first pass, and for a red
    whose failed tests are not read yet, nothing is done.

    A project whose default branch has no macos.yml has no Mac to judge, and `macos` asks GitHub
    nothing for it. It reads the file in the main checkout's `origin/<default branch>`, which
    `jmerge` fetches after each merge, so a macos.yml merged there is judged from the next pass."""
    branch = watch._default_branch(run)
    if run.run("git", "cat-file", "-e", f"origin/{branch}:{watch.MAC_FLOW}").returncode:
        return
    commits = watch.main_commits(run)
    if not isinstance(commits, list) or not commits:
        return
    path = run.state / MAC_CHECKS
    known: dict[str, str] = read_json(path, {})

    def check(commit: dict[str, Any]) -> str:
        sha = commit["sha"]
        said = watch.mac_check(run, known, sha)
        if not said and run.now - when(commit["commit"]["committer"]["date"]) > NO_MAC_AFTER:
            known[sha] = said
        return said

    walked = commits[:MAC_WALK]
    place = next((n for n, c in enumerate(walked) if check(c) in ("green", "failed")), None)
    mac = read_json(run.state / MAC_MAIN, {})
    mac.pop("reverted", None)
    if place is not None:
        tip = walked[place]["sha"]
        red = known[tip] == "failed"
        mac = {**mac, "red": tip if red else "", "green": mac.get("green", "") if red else tip}
        if red and not run.first:
            mac = _mac_red(run, world, walked[place:], check, mac)
    write_json(path, {c["sha"]: known[c["sha"]] for c in commits if c["sha"] in known})
    write_json(run.state / MAC_MAIN, mac)


def _mac_red(
    run: Pass,
    world: World,
    commits: list[dict[str, Any]],
    check: Callable[[dict[str, Any]], str],
    mac: dict[str, Any],
) -> dict[str, Any]:
    """Revert the one clear culprit of the Mac red at `commits[0]`, or file its row, and return
    `mac`. A revert the Mac reads as its own holds on the Mac (`lean`)."""
    since, under = [], ""
    for commit in commits:
        said = "failed" if not since else check(commit)
        if said == "green":
            under = commit["sha"]
            break
        if said != "skipped":
            since.append((commit["sha"], said or "none"))
    tip, oldest = since[0][0], since[-1][0]
    by_commit = {
        (pull.get("mergeCommit") or {}).get("oid"): (slug, pull)
        for slug, pull in world.merged.items()
    }

    def briefed(sha: str) -> tuple[str, dict[str, Any] | None]:
        slug, pull = by_commit.get(sha, ("", None))
        return (slug if pull and brief_of(run, slug) and slug not in run.gated else ""), pull

    slug, pull = briefed(oldest)
    failed = _mac_failed(run, oldest) if pull else None
    landed = when(commits[0]["commit"]["committer"]["date"])
    one = Red(since, pull, slug, failed, run.now - landed, under)
    head = str((pull or {}).get("headRefName", ""))
    flakes = flaky(run, head) if pull and failed else frozenset[str]()
    made = kept.read(run.state)
    found = culprit(one, made, flakes)
    if isinstance(found, Culprit):
        found = tested(run, found, under, one.age)
    if isinstance(found, Culprit):
        found = covered(found, one, (_mac_failed(run, sha) for sha, _ in since[:-1]))
    why = ""
    if found == Keep.OPENED:
        opened = next(sha for sha, _ in since if sha in made)
        lean(run, [sha for sha, _ in since], MAC)
        why = stuck(run, made[opened], watch.checks, opened != tip)
    elif isinstance(found, Culprit):
        if revert(run, found, MAC):
            return mac
        why = "jbus could not open its revert"
    elif found not in QUIET:
        why = str(found)
        if found == Keep.OVERLAP:
            reds = [sha[:12] for sha, said in since if said == "failed"]
            why += f", and main's macOS is red at {' and '.join(reds)}"
    if why:
        _mac_file(run, briefed(tip)[0], tip, since, why)
    return mac


def _mac_failed(run: Pass, sha: str) -> list[str] | None:
    """The tests macos.yml's push run failed at a commit (`mainjson.failures`), or None where
    they cannot be read yet."""
    jobs = watch.mac_jobs(run, sha)
    if jobs is None:
        return None
    return mainjson.failures([(name, found.tests, found.count) for name, _, found in jobs])


def _mac_file(
    run: Pass, slug: str, sha: str, since: Sequence[tuple[str, str]], kept_why: str
) -> None:
    """Queue the fix row `macos-red-<commit>` for the Mac red at `sha`, under the home `macos`,
    once, unapproved: a Mac red holds no pull request, so its row waits its turn."""
    name = f"{MAC_FIX}{sha[:12]}"
    if name in run.removed or queue.fresh(run.state, name) is not None:
        return
    jobs = watch.mac_jobs(run, sha) or []
    reds = [one for one, said in since if said == "failed"]
    text = fix_brief(
        f"{name}: main's macOS run failed at {sha[:12]}"
        + (f", after {slug} merged" if slug else ""),
        f'"macos.yml failed at {sha[:12]} on main after its one rerun, {tests_said(jobs)}" '
        f"(jbus, from macos.yml on main). jbus reverts nothing: {kept_why}",
        "a Mac red holds no pull request, so nothing else brings macOS back to green, and each "
        "user on a Mac meets the failure until this row fixes it",
        [
            "- each failed test named under Read passes on macOS: in macos.yml's run on the "
            "commit that merges the fix, or a manual run of macos-nightly.yml with `ref` set to "
            "the fix's branch",
            "- the Result names the cause: the merge that broke it, or a flake with its evidence",
        ],
        "the touched check, `make check-fast BASE=origin/main PART=touched`, passes, and so "
        "does a manual run of macos-nightly.yml (`gh workflow run macos-nightly.yml -f ref=<the "
        "fix's branch>`)",
        "macos.yml run on main",
        [(job, url, failed.tests) for job, url, failed in jobs],
        [f"- main's macOS run is red at {one}" for one in reds],
        nowhere="the tests of `testing/macos-quick.txt` the merge reaches",
        home="macos",
        follows=slug,
    )
    try:
        queue.add(run.state, name, 0, [], text, user=run.user, ran_by=queue.PASS)
    except (Refused, queue.Unparsable) as refused:
        run.condition(name, f"its brief was not queued: {refused}")
        copy_brief(run, name, text)
        return
    copy_brief(run, name, text)
    line = f"retro {name}: main's macOS run failed at {sha[:12]}, {kept_why}"
    run.find(name, "retro", line, key=f"macos red {sha}", past=True)


STEPS = (
    verbs.Step(
        "tellers", 36, "reverts.known", lambda half: known(half.run, half.seen.world), ("world",)
    ),
    verbs.Step(
        "after-expedite",
        9,
        "reverts.macos",
        lambda half: macos(half.run, half.seen.world),
        ("world", "budget"),
    ),
    verbs.Step(
        "after-expedite",
        13,
        "reverts.close",
        lambda half: close(half.run, half.seen.world, half.rows),
        ("world",),
    ),
)
