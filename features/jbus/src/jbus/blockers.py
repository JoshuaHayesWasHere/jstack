"""A home clears its own blockers, and raises to the user only what the user has to decide.

A blocker is one thing that holds a home's work up, named by a key: an open question (`question
<n>`), a pull request whose check failed (`check:<slug>`), a row that was refused or is stuck
(`row:<slug>`), a row whose Result left something (`left:<slug>`), and a row whose wait has not
changed past its code's bound (`wait:<slug>`, `jbus.aged`), whoever owns the code: the backstop
for a wait no step has a remedy for, as a run GitHub keeps queued. A check that was only
cancelled, which jbus runs again and has not yet told the home of (`cancelled.owns`), is no blocker.
`jbus clear` is what a home runs each time it wakes. It reads only what jbus keeps
(`questions.json`, `queue.json`, `waits.jsonl`, `cancelled.json`), asks no service, and prints one
line for each blocker of that home:

- `decision question <n>`: a question the user has to decide (`needs`). The pass raises it.
- `fix <key>`: a blocker the home fixes. It writes a brief whose head has `Fix of: <key>` and a
  `When green:` line, and queues it with `jbus queue add`. `try <n> of <cap>` counts the fixes
  queued for the key so far.
- `wait <key>`: a fix of the key is at work: its row is not over, not stuck and its check has
  not failed. A fix that failed is no fix at work, so the next try is briefed, or the cap raised.
  It is also the line while the key's last fix has merged and the blocker's failed check has not
  been judged since (`pending`): the merged fix may be what clears it, so no next fix and no page
  yet. A stuck or left row is never judged again, so it does not wait.
- `decision <key>`: the key had its cap of fixes and still blocks, raised to the user.

A fix's own blockers count against the key it fixes: a fix whose check fails is the same blocker
again, so a chain of fixes of fixes is bounded by the one cap.

`admit` is the one door every fix a home queues goes through, `jbus queue add` and `jbus queue
apply` alike. A brief whose head has a `Fix of:` line is a fix. It is refused with no `When green:`
line, the exact check that ends the work, such as CI's check passing on the fix's head. Each brief
admitted for a key is counted, by its `brief_sha`, in `blockers.json` in the directory of the
brief's home (`jbriefs.home.home_of`), `{"<key>": [{"slug", "sha", "at"}]}`, under the same lock
that checks the cap, and the count is taken back when the queue refuses the brief. The same brief
queued again is no new try. Once a key has `retry_cap` tries (`jsettings`, 2 by default), the next
fix is refused, and the key is raised as a decision instead.

A fix is counted when it is queued, so the cap is checked under that one lock, and `forgo` takes
the count back when `jbus queue remove` takes out a fix row that never launched: it did no work,
so it spent no try. A row launched once keeps its count when it is removed, so a cap cannot be
dodged by removing a fix that ran. The cap waits for the effect of the key's last fix on a failed
check: while that fix has merged and no pass has judged the check since (its pull request's latest
check, as the pass record keeps it, started after the merge and completed, or its row changed), the
key is not raised, and `admit` refuses the next fix with no decision (`pending`). A blocker the
merged fix cleared blocks no more, and is never raised. A stuck or left row is raised at once: the
pass record keeps a check only for an open pull request, and such a row changes no column when a
fix merges, so no pass would judge it again.

A decision is the one event of the kind `decision`, at `user`, for each key: `decide` sends it under
the key `decision|<key>`, which names no slug, so whoever raises the same blocker again sends
nothing. An item of the list of what waits is raised once for each time it is on the list: its key
holds the item's `since`, so a hold or an approval that leaves the list and comes back is raised
again. A blocker at its cap is `blocker:<key>`, the same from `admit` and `jbus clear`. Its line
ends with `Reply: <hint>` (`reply`): the user replies in their own words, which go to the home as
the user's word (`jbus word`), and the home turns them into a verb. No line gives the user words
to send. A pass raises one for each item of the list of what waits that the user
has to decide (`needs`): a question or a gate that holds, has no default or names one of
`party.PAUSE`, a go gate whose silence starts nothing, a row to approve, a pull request `jmerge`
holds, and a config item. `jbus decide` raises one by hand, for a scope change. A project's first
pass raises none, as it sends nothing else.

The list was built from what the pass read at its start, and a home may approve a row or answer a
gate while the pass runs. So just before it sends, the pass reads again what each item stands on
(`_Ground`), as `dispatch` reads a row again before a launch: a row whose go now holds for its
brief, a gate no longer open and a hold whose row has merged are not raised. A row to approve is
raised only once it has waited unapproved for `APPROVE_GRACE_SECONDS`, one pass, since a home
that queues a row approves it in the moments after. A gate that holds is raised at once.

An item that leaves the list is told to no one: the decision raised for it stays in the log, and
no event says it went.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsettings
from jbriefs import home as homes
from jbus import (
    Config,
    Project,
    Refused,
    aged,
    alert,
    cancelled,
    dispatch,
    locked,
    party,
    questions,
    queue,
    read_json,
    record,
    verbs,
    waiting,
    work,
    write_json,
)
from jbus.passes import Pass
from jmerge import judgement
from jsettings import brief as brief_head

if TYPE_CHECKING:
    from jbus.poll import Half

LOCK = "blockers.lock"
EVENTS = {"decision": "user"}
KIND = "decision"
APPROVE_GRACE_SECONDS = 60
LEDGER = "blockers.json"
FIX_OF, WHEN_GREEN = "Fix of", "When green"
OWN_WORDS = "reply in your own words to {what} or say what to do instead"
"""The hint an item ends in (`reply`)."""
DEFAULT_WIDTH = 60
"""How much of a gate's default the hint shows, cut short at a word."""
FIXED = {"check": "its check failed", "row": "it was refused or is stuck", "left": "it left work"}
"""What each kind of blocker says it is. A `wait` says its wait (`aged.Aged.said`)."""
STUCK = ("gate", "failed", "stale")
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def head(text: str, name: str) -> str:
    """Return what a line `<name>: ` in the brief's head says, or nothing when the line is not
    there or still holds a placeholder."""
    said = brief_head.head(text, f"{name}:") or ""
    return "" if said.startswith("<") else said


def decide(run: Pass, slug: str, key: str, said: str, reply: str, *, listed: bool = False) -> bool:
    """Log one decision for the key, and return False when it was logged before. A home thread
    hears of it from the one list (`jbus.wakes`): a decision `listed` is an item of what waits
    there already, and any other is the project's alert, which ends after `alert.LASTS`."""
    line, keyed = f"{KIND} {slug}: {said}. Reply: {reply}", f"{KIND}|{key}"
    sent = run.box.send(slug, KIND, line, key=keyed)
    if sent and not listed:
        ends = (run.now + alert.LASTS).isoformat()
        alert.raise_(run.config, keyed, line, owner=run.project.name, now=run.now, ends=ends)
    return sent


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 'es'}"


def ledger(directory: Path) -> dict[str, list[dict[str, str]]]:
    kept = read_json(directory / LEDGER, {})
    return kept if isinstance(kept, dict) else {}


def tries(directory: Path, key: str) -> list[dict[str, str]]:
    found = ledger(directory).get(key)
    return found if isinstance(found, list) else []


def _capped(key: str, had: list[dict[str, str]]) -> tuple[str, str]:
    """The decision of a key that had its cap of fixes: what it says and its reply."""
    slugs = ", ".join(one.get("slug", "") for one in had)
    said = f"{key} had {_count(len(had), 'fix')} ({slugs}), the retry cap, and it still blocks"
    return said, OWN_WORDS.format(what=f"take {key} on yourself")


def admit(config: Config, project: Project, slug: str, text: str) -> Callable[[], None]:
    """Refuse a fix that has no `When green:` line, or whose key had its cap of fixes, and raise
    the second as a decision. Otherwise count the fix at once, under the lock that checks the
    cap, so neither a batch nor two adds at the same time pass the cap. Return what takes the
    count back when the queue then refuses the brief: nothing for a brief that is no fix, or that
    was counted before."""
    key = head(text, FIX_OF)
    if not key:
        return lambda: None
    if not head(text, WHEN_GREEN):
        raise Refused(
            f"refused: {slug} is a fix of {key}, and its brief has no When green: line, the "
            "exact check that ends the work (such as `check` passing on the fix's head): "
            "nothing is queued"
        )
    directory = homes.home_of(config.home(project), text)
    sha = judgement.brief_sha(text)
    with locked(directory, LOCK):
        kept = ledger(directory)
        found = kept.get(key)
        had = found if isinstance(found, list) else []
        if any(one.get("sha") == sha for one in had):
            return lambda: None
        if len(had) < config.user.retry_cap:
            at = jsettings.stamp(datetime.now(UTC))
            kept[key] = [*had, {"slug": slug, "sha": sha, "at": at}]
            write_json(directory / LEDGER, kept)
            return lambda: _release(directory, key, sha)
    run = Pass(config, project, datetime.now(UTC))
    rows = {row["slug"]: row for row in queue.load(run.state)}
    merged = pending(run, rows, had, rows.get(key.partition(":")[2]))
    if merged:
        raise Refused(
            f"refused: {merged}, so {slug} is not queued and nothing is raised: wait for "
            f"{key}'s next judgment"
        )
    said, reply = _capped(key, had)
    decide(run, slug, f"blocker:{key}", said, reply)
    raise Refused(
        f"refused: {said}: raised to {config.user.user} as a decision, and {slug} is not queued"
    )


def _release(directory: Path, key: str, sha: str = "", slug: str = "") -> None:
    """Take back the count of a fix the queue refused, by its sha, or of a fix row removed
    unrun, by its slug."""
    with locked(directory, LOCK):
        kept = ledger(directory)
        if key not in kept:
            return
        kept[key] = [
            one
            for one in kept[key]
            if not (sha and one.get("sha") == sha) and not (slug and one.get("slug") == slug)
        ]
        if not kept[key]:
            del kept[key]
        write_json(directory / LEDGER, kept)


def rehome(home: Path, slug: str, text: str) -> None:
    """Carry the tries a fix row counts to the ledger of the home its brief names, `text`, from
    that of every other home under `home`, so its home's cap counts them and `forgo` finds them
    there. It reads only what the ledgers hold, so a `jbus queue move` cut short before it, or
    between its two writes, carries what is left when run again, and each try once: a try the
    home already holds, by its sha, is not counted twice. A brief that is no fix carries nothing."""
    key = head(text, FIX_OF)
    if not key:
        return
    to = homes.home_of(home, text)
    for was in sorted(path.parent for path in home.glob(f"*/{LEDGER}")):
        if was == to or not any(one.get("slug") == slug for one in tries(was, key)):
            continue
        with locked(min(was, to), LOCK), locked(max(was, to), LOCK):
            old, new = ledger(was), ledger(to)
            going = [one for one in old.get(key, []) if one.get("slug") == slug]
            held = {one.get("sha") for one in new.get(key, [])}
            new[key] = [*new.get(key, []), *(one for one in going if one.get("sha") not in held)]
            old[key] = [one for one in old.get(key, []) if one.get("slug") != slug]
            if not old[key]:
                del old[key]
            write_json(to / LEDGER, new)
            write_json(was / LEDGER, old)


def forgo(run: Pass, move: dict[str, Any]) -> None:
    """Give back the try of a fix whose row `jbus queue remove` took out before it launched: no
    thread, no pull request and no launch record. `move` is the removal's line of
    `transitions.jsonl`, with the row as it was and where its brief was kept."""
    row, slug = move.get("row") or {}, move["slug"]
    if row.get("thread") or row.get("pr") or dispatch.records(run, slug):
        return
    try:
        text = Path(move["brief"]).read_text(errors="replace") if move.get("brief") else ""
    except OSError:
        return
    key = head(text, FIX_OF)
    if key:
        _release(homes.home_of(run.config.home(run.project), text), key, slug=slug)


def _moment(stamp: str, user: jsettings.Settings) -> datetime | None:
    """The time a pass stamped on a row, which is a time in the user's zone."""
    found = _STAMP.match(stamp or "")
    return user.local(datetime.fromisoformat(found[0])) if found else None


def _iso(text: Any) -> datetime | None:
    try:
        return jsettings.when(str(text)) if text else None
    except ValueError:
        return None


def _ended(run: Pass, row: queue.Row) -> datetime | None:
    """When a pass first saw the fix's row merged or done: its last move there in
    `transitions.jsonl`, or the row's stamp where the log has none."""
    try:
        lines = queue.transitions_path(run.state).read_text().splitlines()
    except OSError:
        lines = []
    moved = None
    for line in lines:
        if row["slug"] in line:
            try:
                one = json.loads(line)
            except ValueError:
                continue
            if one.get("slug") == row["slug"] and one.get("to") in work.FINAL:
                moved = _iso(one.get("at")) or moved
    return moved or _moment(row.get("updated", ""), run.user)


def _judged(run: Pass, blocker: queue.Row, since: datetime) -> bool:
    """Whether a pass has judged the blocker since then: its pull request's latest check started
    after it and completed, as the pass record keeps it (`record`), or its row changed after it."""
    rows = (record.read(run.config).get("projects") or {}).get(run.project.name) or {}
    check = ((rows.get("rows") or {}).get(blocker["slug"]) or {}).get("check") or {}
    started = _iso(check.get("started"))
    if started is not None and started > since and check.get("completed"):
        return True
    changed = _moment(blocker.get("updated", ""), run.user)
    return changed is not None and changed > since


def pending(
    run: Pass, rows: dict[str, queue.Row], had: list[dict[str, str]], blocker: queue.Row | None
) -> str:
    """Say that the key's last counted fix has merged and no pass has judged the blocker since,
    or nothing. Such a fix has not had its effect yet: the blocker's next judgment, its check run
    again over the merged fix, says whether it still stands. Only a failed check is judged
    again, as the pass record keeps a check only for a row with an open pull request: a stuck or
    left row changes no column when a fix merges, so it is never pending."""
    last = rows.get(had[-1].get("slug", "")) if had else None
    if last is None or blocker is None or not work.over(last):
        return ""
    if blocker.get("checks") != "failed":
        return ""
    ended = _ended(run, last)
    if ended is not None and _judged(run, blocker, ended):
        return ""
    return f"{last['slug']} {last['status']} at {last.get('updated') or 'a time not stamped'}"


def needs(one: waiting.Item, context: str = "", known: frozenset[str] = frozenset()) -> str:
    """Say why the user has to decide an item of the list of what waits, or nothing when the
    home clears it. `known` are the slugs the queue knows (`queue.known`), which the gate's words
    may name with no door meant, as they may its own."""
    kind = one["kind"]
    if kind == "hold":
        return "a pull request jmerge holds for your word"
    if kind == "approve":
        return "a row with no approval of its brief"
    if kind == "config":
        return "jbus lacks a setup only you can give"
    if kind == "stalled":
        return "a home that stalled again after jbus started it again"
    if kind == "install":
        return "a T3 Code build only you can install"
    if kind == "held" and one.get("lift"):
        numbers = " ".join(str(number) for number in one.get("numbers", []))
        return f"no crew clears it, and your word lifts it: {one['lift']} {numbers}".rstrip()
    if kind != "gate":
        return ""
    if one.get("holds"):
        return f"it holds ({one['holds']}) for your answer"
    if not str(one.get("default") or "").strip():
        return "a gate with no default"
    if one.get("waits"):
        return f"its silence starts nothing, since {one['waits']}"
    named = party.paused(f"{one.get('question', '')} {context}", known | {one.get("slug") or ""})
    return f"it names {named}" if named else ""


def reply(one: waiting.Item) -> str:
    """Return the hint that ends an item, which a decision carries as its `Reply:` and `jbus
    needs` prints: the user replies in their own words, and the home turns them into a verb. It
    gives the user no words to send."""
    kind = one["kind"]
    if kind == "gate" and questions.listed(one):
        default = textwrap.shorten(str(one.get("default") or ""), DEFAULT_WIDTH, placeholder="...")
        return OWN_WORDS.format(what=f"keep the default ({default})")
    if kind == "gate":
        return OWN_WORDS.format(what="hold it")
    if kind == "hold":
        return OWN_WORDS.format(what=f"merge #{one['number']}")
    if kind == "held" and one.get("lift"):
        numbers = " and ".join(f"#{number}" for number in one.get("numbers", []))
        return OWN_WORDS.format(what=f"merge {numbers}")
    if kind == "approve":
        return OWN_WORDS.format(what=f"give {one['slug']} its go")
    if kind == "stalled":
        return "get the home going in its thread, or start it again, then say so in your own words"
    if kind == "install":
        return "nothing to reply: the next pass after the install takes it off"
    return "set it up, then say so in your own words"


def _keyed(one: waiting.Item) -> tuple[str, str]:
    """Return the key an item's decision is raised under, after `decision|`, and its slug."""
    key, slug = f"{one['key']}|{one['since']}", one.get("slug") or one["key"]
    if one["kind"] == "config":
        key = f"{key}|{hashlib.sha256(one['line'].encode()).hexdigest()[:12]}"
        slug = "config"
    return key, slug


def _pr_row(run: Pass, number: Any) -> queue.Row | None:
    """Return the row whose pull request is `#<number>`, as the queue has it now."""
    try:
        rows = queue.load(run.state)
    except queue.Unparsable:
        return None
    return next((row for row in rows if row.get("pr") == f"#{number}"), None)


class _Ground:
    """What an item of the list stands on, read again just before its decision is sent, as
    `dispatch` reads a row again before it launches it. The list was built from what the pass
    read at its start, and a home may approve a row or answer a gate while the pass runs."""

    def __init__(self, run: Pass) -> None:
        self.run = run
        self._gates: set[str] | None = None

    def gates(self) -> set[str] | None:
        """Return the keys of the gates open now, or None where `questions.json` does not
        parse, and the list's own reading stands."""
        if self._gates is None:
            run = self.run
            try:
                asked = questions.read(run.state)
            except questions.Unparsable:
                return None
            why = questions.waits(run.state, run.user)
            self._gates = {one["key"] for one in waiting.gates(run.home, asked, run.removed, why)}
        return self._gates

    def stands(self, one: waiting.Item) -> bool:
        """Say whether the item still waits on the user: a row with no go that holds for its
        brief, a gate still open, a pull request whose row has not merged."""
        kind, run = one["kind"], self.run
        if kind == "approve":
            row, text = queue.current(run.state, one["slug"])
            if row is None or one["slug"] in run.removed or row.get("status", "queued") != "queued":
                return False
            return not (
                row.get("approved") and text is not None and judgement.approved_text(row, text)
            )
        if kind == "gate":
            open_now = self.gates()
            return open_now is None or one["key"] in open_now
        if kind == "hold":
            row = _pr_row(run, one.get("number"))
            return row is None or not work.over(row)
        return True


def _early(run: Pass, one: waiting.Item) -> bool:
    """Say whether a row to approve is still within its grace: a home that queues a row approves
    it in the minutes after, and only a row still unapproved after that waits on the user."""
    if one["kind"] != "approve":
        return False
    since = datetime.fromisoformat(one["since"])
    return run.now - since < timedelta(seconds=APPROVE_GRACE_SECONDS)


def deciding(run: Pass, listed: list[waiting.Item] | None) -> list[tuple[waiting.Item, str]]:
    """Each item of the list that the user has to decide and that still stands when it is read
    again, with what it asks."""
    if run.first or listed is None:
        return []
    context = {questions.item(one)["key"]: one.context for one in questions.load(run.state)}
    ground, found, known = _Ground(run), [], queue.known(run.state)
    for one in listed:
        why = needs(one, context.get(one["key"], ""), known)
        if not why or _early(run, one) or not ground.stands(one):
            continue
        asked = f"question {one['number']}: {one['question']}" if questions.listed(one) else ""
        found.append((one, f"{(asked or one['line']).rstrip('.?')}, {why}"))
    return found


def holding(run: Pass) -> frozenset[str]:
    """Return the slugs that a gate of the user's holds now: each open gate whose item `jbus
    needs` lists (`deciding`), read from the gates on disk, since `work.json` is written before
    the pass lists what waits. None holds where `questions.json` does not parse."""
    try:
        asked = questions.read(run.state)
        why = questions.waits(run.state, run.user)
        found = deciding(run, waiting.gates(run.home, asked, run.removed, why))
    except questions.Unparsable:
        return frozenset()
    return frozenset(str(one.get("slug") or "") for one, _ in found) - {""}


def raise_listed(run: Pass, listed: list[waiting.Item] | None) -> None:
    """Log one decision for each item that the user has to decide (`deciding`). A home thread
    hears of it from the one list (`jbus.wakes`), and the log keeps this event."""
    for one, said in deciding(run, listed):
        key, slug = _keyed(one)
        decide(run, slug, key, said, reply(one), listed=True)


def _raise(half: Half) -> None:
    raise_listed(half.run, half.listed)


@dataclass(frozen=True)
class Directory:
    """The home whose blockers `jbus clear` reads: its directory, and its own slug."""

    root: Path
    path: Path

    @property
    def works(self) -> frozenset[Path]:
        """The homes whose rows these are (`jbriefs.home.works`)."""
        return homes.works(self.root, self.path)

    @property
    def own(self) -> str:
        return "home" if self.path == self.root else f"home-{self.path.name}"

    def has(self, slug: str) -> bool:
        """Say whether a slug is this home's: its own, or by the home of its brief or request,
        and the catch-all's (`uncategorized`) when it has neither, as `jbus needs` reads it."""
        if slug == self.own or (slug.startswith("home-") and self.root / slug[5:] in self.works):
            return True
        if slug == "home" or (slug.startswith("home-") and (self.root / slug[5:]).is_dir()):
            return False
        for kind in ("tasks", "scouts"):
            file = self.root / kind / f"{slug}.md"
            if file.exists():
                return homes.home_of(self.root, file.read_text(errors="replace")) in self.works
        return (homes.catchall(self.root) if slug else self.root) in self.works


def _gates(run: Pass, home: Directory) -> list[str]:
    """Say each open question of the home that the user has to decide. A question that does not
    need the user is closed with its default by silence, in the first pass that sees it
    (`questions.silent`), so the home has nothing to clear."""
    said = []
    silence = questions.waits(run.state, run.user)
    known = queue.known(run.state)
    for one in questions.load(run.state):
        if one.answer is not None or not home.has(one.slug):
            continue
        why = needs(questions.item(one, silence(one)), one.context, known)
        if why:
            said.append(f"decision question {one.number}: {why}, it waits on {run.user.user}")
    return said


def waits(state: Path) -> list[dict[str, Any]]:
    """The lines of `waits.jsonl`, each change of a row's `why` with its time, or none where the
    file is not there. A line that does not parse is skipped."""
    try:
        text = queue.waits_path(state).read_text()
    except OSError:
        return []
    found = []
    for line in text.splitlines():
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if isinstance(one, dict):
            found.append(one)
    return found


def _rows(run: Pass, home: Directory) -> list[str]:
    """Say what to do with each row of the home that blocks: brief a fix, wait for the one at
    work, or raise it once it had its cap of fixes."""
    rows = queue.load(run.state)
    texts = {row["slug"]: queue.brief(run.state, row["slug"]) or "" for row in rows}
    old = aged.aged(rows, waits(run.state), run.now)
    mine = [
        row
        for row in rows
        if homes.home_of(home.root, texts[row["slug"]]) in home.works and not work.over(row)
    ]
    open_fixes: dict[str, list[str]] = {}
    for row in mine:
        fixes = head(texts[row["slug"]], FIX_OF)
        if fixes and row.get("status") not in STUCK and row.get("checks") != "failed":
            open_fixes.setdefault(fixes, []).append(row["slug"])
    said, seen = [], set()
    cap = run.user.retry_cap
    for row in mine:
        slug, status = row["slug"], row.get("status")
        if row.get("checks") == "failed":
            if cancelled.owns(run, slug):
                continue
            kind = "check"
        elif status in STUCK:
            kind = "row"
        elif status == "left":
            kind = "left"
        elif slug in old:
            kind = "wait"
        else:
            continue
        key = head(texts[slug], FIX_OF) or f"{kind}:{slug}"
        if key in seen:
            continue
        seen.add(key)
        had = tries(homes.home_of(home.root, texts[slug]), key)
        at_work = [one for one in open_fixes.get(key, []) if one != slug]
        merged = pending(run, {one["slug"]: one for one in rows}, had, row)
        if at_work:
            said.append(f"wait {key}: {', '.join(at_work)} is at work on it")
        elif merged:
            said.append(f"wait {key}: {merged}, and {slug} has not been judged since")
        elif len(had) >= cap:
            what, reply = _capped(key, had)
            decide(run, slug, f"blocker:{key}", what, reply)
            said.append(f"decision {key}: {what}, raised, it waits on {run.user.user}")
        else:
            what = old[slug].said if kind == "wait" else FIXED[kind]
            said.append(
                f'fix {key}: {what}, brief a fix whose head has "Fix of: {key}" and '
                f'"When green: <the exact check that ends it>", try {len(had) + 1} of {cap}'
            )
    return said


def _clear(args: argparse.Namespace, config: Config) -> int:
    """`jbus clear`: clear this home's blockers, and say what is left to do with each."""
    project = verbs.here(config, args.project)
    run = Pass(config, project, verbs.clock())
    root = config.home(project)
    path = root / args.scope if args.scope else root
    if args.scope and not (path / "plan.md").exists():
        raise Refused(f"refused: {path} has no plan.md, so {args.scope} is no scoped home")
    home = Directory(root, path)
    said = _gates(run, home) + _rows(run, home)
    print("\n".join(said) if said else "nothing blocks this home")
    return 0


def _decide(args: argparse.Namespace, config: Config) -> int:
    """`jbus decide`: raise a decision by hand, such as a scope change."""
    project = verbs.here(config, args.project)
    question, reply = " ".join(args.question.split()), " ".join(args.reply.split())
    if not question or not reply:
        raise Refused("refused: a decision needs --question and --reply, each filled in")
    run = Pass(config, project, datetime.now(UTC))
    key = "decide " + hashlib.sha256(f"{args.slug}\n{question}".encode()).hexdigest()[:16]
    sent = decide(run, args.slug, key, question, reply)
    print(f"{'raised' if sent else 'raised already'}: {args.slug}: {question}")
    return 0


def _clears(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", help="the scoped home whose blockers these are")


def _decides(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug")
    parser.add_argument("--question", required=True, help="what the user has to decide")
    parser.add_argument(
        "--reply",
        required=True,
        help="a plain hint for the user's reply, as: reply in your own words to ...",
    )


VERBS = (
    verbs.Verb("clear", "clear this home's blockers, and say what is left", _clears, _clear),
    verbs.Verb("decide", "raise a decision for the user, as a scope change", _decides, _decide),
)

STEPS = (verbs.Step("close", 25, "blockers.raise_listed", _raise),)
