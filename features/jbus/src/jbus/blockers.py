"""A home clears its own blockers, and raises to the user only what the user has to decide.

A blocker is one thing that holds a home's work up, named by a key: an open question (`question
<n>`), a pull request whose check failed (`check:<slug>`), a row that was refused or is stuck
(`row:<slug>`), and a row whose Result left something (`left:<slug>`). A check that was only
cancelled, which jbus runs again and has not yet told the home of (`cancelled.owns`), is no blocker.
`jbus clear` is what a home runs each time it wakes. It reads only what jbus keeps
(`questions.json`, `queue.json`, `cancelled.json`), asks no service, and prints one line for each
blocker of that home:

- `cleared question <n>`: a question that does not need the user, open `--after` minutes or more
  (30 by default, `leftover.CLOSE_MINUTES`). The thread acted on its default when it asked, so
  the home takes that default: `clear` logs the gate in the home's `gates.md` as answered by the
  home, and `questions.closed_in_files` closes the record from there, as it closes any gate a
  home answered in its file. Nothing is posted.
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
ends with `Reply: "<reply>"`, a line the user can send as it is: the reply goes to the home as the
user's word (`jbus word`). A pass raises one for each item of the list of what waits that the user
has to decide (`needs`): a question or a gate that holds, has no default or names one of
`waiting.PAUSE`, a row to approve, a pull request `jmerge` holds, and a config item. `jbus decide`
raises one by hand, for a scope change. A project's first pass raises none, as it sends nothing
else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsettings
from jbriefs import home as homes
from jbus import (
    Config,
    Project,
    Refused,
    cancelled,
    dispatch,
    leftover,
    locked,
    questions,
    queue,
    read_json,
    record,
    verbs,
    waiting,
    write_json,
)
from jbus.passes import Pass
from jbus.wake import Box

if TYPE_CHECKING:
    from jbus.cli import Half

LOCK = "blockers.lock"
EVENTS = {"decision": "user"}
KIND = "decision"
LEDGER = "blockers.json"
FIX_OF, WHEN_GREEN = "Fix of", "When green"
TAKE_IT = "I take it"
FIXED = {"check": "its check failed", "row": "it was refused or is stuck", "left": "it left work"}
STUCK = ("gate", "failed", "stale")
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def head(text: str, name: str) -> str:
    """Return what a line `<name>: ` in the brief's head says, or nothing when the line is not
    there or still holds a placeholder."""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith(f"{name}:"):
            said = line[len(name) + 1 :].strip()
            return "" if said.startswith("<") else said
    return ""


def decide(box: Box, slug: str, key: str, said: str, reply: str) -> bool:
    """Raise one decision for the key, and return False when it was raised before."""
    line = f'{KIND} {slug}: {said}. Reply: "{reply}"'
    return box.send(slug, KIND, line, key=f"{KIND}|{key}")


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 'es'}"


def ledger(directory: Path) -> dict[str, list[dict[str, str]]]:
    kept = read_json(directory / LEDGER, {})
    return kept if isinstance(kept, dict) else {}


def tries(directory: Path, key: str) -> list[dict[str, str]]:
    found = ledger(directory).get(key)
    return found if isinstance(found, list) else []


def _capped(project: Project, slug: str, key: str, had: list[dict[str, str]]) -> tuple[str, str]:
    """The decision of a key that had its cap of fixes: what it says and its reply."""
    slugs = ", ".join(one.get("slug", "") for one in had)
    said = f"{key} had {_count(len(had), 'fix')} ({slugs}), the retry cap, and it still blocks"
    return said, f"{project.name} {key}: {TAKE_IT}"


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
    sha = queue.brief_sha(text)
    with locked(directory, LOCK):
        kept = ledger(directory)
        had = kept.get(key) if isinstance(kept.get(key), list) else []
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
    said, reply = _capped(project, slug, key, had)
    decide(run.box, slug, f"blocker:{key}", said, reply)
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
            if one.get("slug") == row["slug"] and one.get("to") in queue.FINAL:
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
    if last is None or blocker is None or last.get("status") not in queue.FINAL:
        return ""
    if blocker.get("checks") != "failed":
        return ""
    ended = _ended(run, last)
    if ended is not None and _judged(run, blocker, ended):
        return ""
    return f"{last['slug']} {last['status']} at {last.get('updated') or 'a time not stamped'}"


def needs(one: waiting.Item, context: str = "") -> str:
    """Say why the user has to decide an item of the list of what waits, or nothing when the
    home clears it. A question about a link's conflict asks its home, not the user."""
    kind = one["kind"]
    if kind == "hold":
        return "a pull request jmerge holds for your word"
    if kind == "approve":
        return "a row with no approval of its brief"
    if kind == "config":
        return "jbus lacks a setup only you can give"
    if kind != "gate" or str(one.get("question", "")).endswith(questions.LINK):
        return ""
    if one.get("holds"):
        return f"it holds ({one['holds']}) for your answer"
    if not str(one.get("default") or "").strip():
        return "a gate with no default"
    named = waiting.paused(f"{one.get('question', '')} {context}")
    return f"it names {named}" if named else ""


def _reply(project: Project, one: waiting.Item) -> str:
    kind = one["kind"]
    if kind == "gate" and questions.listed(one):
        return f"{project.name} question {one['number']}: default"
    if kind == "gate":
        home = f"{one['home']}#" if one.get("home") else ""
        return f"{project.name} gate {home}{one['number']}: hold it"
    if kind == "hold":
        return f"{project.name} #{one['number']}: merge it"
    if kind == "approve":
        return f"{project.name} approve {one['slug']}: go"
    return f"{project.name} config: I set it up"


def raise_listed(run: Pass, listed: list[waiting.Item] | None) -> None:
    """Raise one decision for each item of the list that the user has to decide."""
    if run.first or not listed:
        return
    context = {questions.item(one)["key"]: one.context for one in questions.load(run.state)}
    for one in listed:
        why = needs(one, context.get(one["key"], ""))
        if why:
            asked = f"question {one['number']}: {one['question']}" if questions.listed(one) else ""
            said = f"{(asked or one['line']).rstrip('.?')}, {why}"
            key, slug = f"{one['key']}|{one['since']}", one.get("slug") or one["key"]
            if one["kind"] == "config":
                key = f"{key}|{hashlib.sha256(one['line'].encode()).hexdigest()[:12]}"
                slug = "config"
            decide(run.box, slug, key, said, _reply(run.project, one))


def _raise(half: Half) -> None:
    raise_listed(half.run, half.listed)


@dataclass(frozen=True)
class Directory:
    """The home whose blockers `jbus clear` reads: its directory, and its own slug."""

    root: Path
    path: Path

    @property
    def own(self) -> str:
        return "home" if self.path == self.root else f"home-{self.path.name}"

    def has(self, slug: str) -> bool:
        """Say whether a slug is this home's: its own, or by the home of its brief or request,
        and the root home's when it has neither."""
        if slug == self.own:
            return True
        if slug == "home" or (slug.startswith("home-") and (self.root / slug[5:]).is_dir()):
            return False
        for kind in ("tasks", "scouts"):
            file = self.root / kind / f"{slug}.md"
            if file.exists():
                return homes.home_of(self.root, file.read_text(errors="replace")) == self.path
        return self.path == self.root


def _logged(one: questions.Question, minutes: int, stamp: str) -> str:
    return (
        f"\n## Gate q{one.number}: {one.question}\n"
        f"Status: answered, the default taken by the home, {stamp}: open {minutes} min with no "
        "answer\n"
        f"Asked by: {one.slug}\n"
        f"Default: {one.default}\n"
        f"Built on it: {one.built_on}\n"
        f"Undo: {one.undo}\n"
    )


def _gates(run: Pass, home: Directory, after: int) -> list[str]:
    """Clear each question of the home that the user need not decide and that has been open
    `after` minutes, and say each question the user has to decide."""
    said, cleared = [], []
    silence = questions.waits(run.state, run.user)
    for one in questions.load(run.state):
        if one.answer is not None or not home.has(one.slug):
            continue
        item = questions.item(one, silence(one))
        why = needs(item, one.context)
        minutes = int((run.now - datetime.fromisoformat(one.asked_at)).total_seconds() // 60)
        if why:
            said.append(f"decision question {one.number}: {why}, it waits on {run.user.user}")
        elif not one.question.endswith(questions.LINK) and minutes >= after:
            cleared.append(_logged(one, minutes, run.user.stamp(run.now)))
            said.append(
                f"cleared question {one.number}: took its default, {one.default}, logged in "
                f"{home.path / 'gates.md'}"
            )
    if cleared:
        file = home.path / "gates.md"
        was = file.read_text() if file.exists() else ""
        file.write_text(was + "".join(cleared))
        questions.closed_in_files(run)
    return said


def _rows(run: Pass, home: Directory) -> list[str]:
    """Say what to do with each row of the home that blocks: brief a fix, wait for the one at
    work, or raise it once it had its cap of fixes."""
    rows = queue.load(run.state)
    texts = {row["slug"]: queue.brief(run.state, row["slug"]) or "" for row in rows}
    mine = [
        row
        for row in rows
        if homes.home_of(home.root, texts[row["slug"]]) == home.path
        and row.get("status") not in queue.FINAL
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
        else:
            continue
        key = head(texts[slug], FIX_OF) or f"{kind}:{slug}"
        if key in seen:
            continue
        seen.add(key)
        had = tries(home.path, key)
        at_work = [one for one in open_fixes.get(key, []) if one != slug]
        merged = pending(run, {one["slug"]: one for one in rows}, had, row)
        if at_work:
            said.append(f"wait {key}: {', '.join(at_work)} is at work on it")
        elif merged:
            said.append(f"wait {key}: {merged}, and {slug} has not been judged since")
        elif len(had) >= cap:
            what, reply = _capped(run.project, slug, key, had)
            decide(run.box, slug, f"blocker:{key}", what, reply)
            said.append(f"decision {key}: {what}, raised, it waits on {run.user.user}")
        else:
            said.append(
                f'fix {key}: {FIXED[kind]}, brief a fix whose head has "Fix of: {key}" and '
                f'"When green: <the exact check that ends it>", try {len(had) + 1} of {cap}'
            )
    return said


def _clear(args: argparse.Namespace, config: Config) -> int:
    """`jbus clear`: clear this home's blockers, and say what is left to do with each."""
    project = verbs.here(config, args.project)
    run = Pass(config, project, datetime.now(UTC))
    root = config.home(project)
    path = root / args.scope if args.scope else root
    if args.scope and not (path / "plan.md").exists():
        raise Refused(f"refused: {path} has no plan.md, so {args.scope} is no scoped home")
    home = Directory(root, path)
    said = _gates(run, home, args.after) + _rows(run, home)
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
    sent = decide(run.box, args.slug, key, question, f"{project.name} {reply}")
    print(f"{'raised' if sent else 'raised already'}: {args.slug}: {question}")
    return 0


def _clears(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", help="the scoped home whose blockers these are")
    parser.add_argument(
        "--after",
        type=int,
        default=leftover.CLOSE_MINUTES,
        help="how many minutes a question stays open before the home takes its default",
    )


def _decides(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug")
    parser.add_argument("--question", required=True, help="what the user has to decide")
    parser.add_argument("--reply", required=True, help="the reply the user can send as it is")


VERBS = (
    verbs.Verb("clear", "clear this home's blockers, and say what is left", _clears, _clear),
    verbs.Verb("decide", "raise a decision for the user, as a scope change", _decides, _decide),
)

STEPS = (verbs.Step("close", 25, "blockers.raise_listed", _raise),)
