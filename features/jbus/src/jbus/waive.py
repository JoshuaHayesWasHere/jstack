"""`jbus waive`: the user's plain reply to a home's ask, bound to the rows and lines it asked about.

A `Waived: <the Done when line>, <thread>/<message>` line of a brief clears a line its review
says is unmet (`jbriefs.meets`), on a word jbus checked (`jbus.port.Port.heard`). The word can
quote the line after "waive" itself, or it can be the user's plain answer to a home that asked:
"yes clear them", said in the home's own thread right after the home's message that named the
row and its lines. The home records that answer with

    jbus waive <slug> <line number>... --message <thread id>/<message id>

which checks, before anything is written:

- the message is the user's own, read in T3 Code (`t3.own`), as every word jbus takes is;
- its thread is the thread of a home of the project, the root's or a scoped one's (`home-id`);
- the last message the home wrote in that thread before it (`t3.home_ask`) names the row's slug
  and each line by its number, as `alpha: lines 2 and 3` (`asked`, on `t3.asked_of`). So a message
  older than the ask, an ask about another row, and a line the home did not ask about waive
  nothing.

It then logs one act of the verb `waive` (`jbus.acts`), whose subject is the slug and whose `pre`
holds the line numbers, and appends the brief's `Waived:` lines for them, naming each line by its
words. `Port.heard` counts a `Waived:` line whose message and slug such an act holds, for the
lines it names. The same command again logs and writes nothing new.

The root home waives on its own judgment, with no word of the user's, as the user asked on
2026-11-12 ("update jbus to not need me for this type of thing anymore"):

    jbus waive <slug> <line number>... --as root --from <root thread> --reason <why> --undo <how>

which refuses, with one line and before anything is written, a `--from` that is not the thread in
the root home's `home-id` (a scoped home's, a crew's, or none), a waiver with no `--reason` or no
`--undo`, and a brief that holds for a one-way door (`party.doors`), whose merge no revert undoes:
those stay the user's. It logs one `waive` act of the party `root`, whose evidence holds the
reason as its words and the undo, and whose id is the hash of the slug, the lines, the reason and
the undo, so the brief's `Waived: <the Done when line>, root/<act id>` lines name the act, and the
evidence's ref is that same `root/<act id>`, which `held`, and so `Port.heard`, counts. The user
reads each such waiver as one line of `jbus needs`, and so of the catch-up, with nothing to answer,
for a day after it was made (`SHOWN`, `recent`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jbriefs import meets
from jbriefs.home import thread_of
from jbus import Config, Refused, acts, locked, party, queue, t3, verbs
from jbus.passes import Pass
from jsettings.brief import head_lines

KIND = "waive"
SHOWN = timedelta(days=1)
"""How long `jbus needs` lists a root waiver after it was made, so the user who checks in once a
day reads each one."""
NOT_ROOT = (
    "is not the root home's thread, and only the root waives on its own judgment: a scoped home "
    "sends its pick to the root with jbus stop --kind decision"
)
_LINES = re.compile(r"\blines?\s+(\d+(?:(?:\s*,\s*|\s+and\s+|\s*&\s*|\s*,\s*and\s+)\d+)*)", re.I)


def asked(text: str, slug: str, others: frozenset[str]) -> frozenset[int]:
    """The line numbers a home's message names for the row `slug`: those named as `line <n>` or
    `lines <n>, <m> and <k>` in each part of it about the row (`t3.asked_of`)."""
    return frozenset(
        int(number)
        for part in t3.asked_of(text, slug, others)
        for found in _LINES.finditer(part)
        for number in re.findall(r"\d+", found[1])
    )


def held(state: Path, slug: str, ref: str) -> frozenset[int]:
    """The line numbers of the row `slug` that the `waive` acts on the message `ref` bound."""
    return frozenset(
        int(number)
        for act in acts.read(state)
        if act["action"]["verb"] == KIND
        and act["outcome"] == "done"
        and act["action"]["subject"] == slug
        and act["evidence"].get("ref") == ref
        for number in act["action"]["pre"].split()
    )


def _waive(args: argparse.Namespace, config: Config) -> int:
    """`jbus waive`: bind the user's plain reply to the home's ask, or record the root's own
    waiver (`--as root`), as the module says."""
    project = verbs.project(config, args.to)
    numbers = sorted(set(args.lines))
    if args.as_ == party.ROOT.kind:
        if args.message:
            raise Refused("refused: --as root waives on the root's own judgment, with no --message")
        run = Pass(config, project, verbs.clock(), lambda _: None)
        brief, text, items = _brief(run, project.name, args.slug, numbers)
        return _root(run, args, brief, text, items, numbers)
    stray = next((name for name in ("from_", "reason", "undo") if getattr(args, name)), "")
    if stray:
        raise Refused(
            f"refused: --{stray.rstrip('_')} is only for --as root, and records nothing here"
        )
    if not args.message:
        raise Refused(
            "refused: --message names the user's own reply to the home's ask; only --as root "
            "waives without one"
        )
    run = Pass(config, project, datetime.now(UTC), lambda _: None)
    slug, ref = args.slug, args.message
    brief, text, items = _brief(run, project.name, slug, numbers)
    said, ask = t3.home_ask(config, run.home, project.name, ref)
    others = queue.known(run.state) | {one.stem for one in (run.home / "tasks").glob("*.md")}
    named = asked(ask.text, slug, others - {slug})
    if not named:
        raise Refused(f"refused: the home's message before {ref} does not name {slug}")
    missing = [one for one in numbers if one not in named]
    if missing:
        raise Refused(f"refused: the home's message before {ref} does not name line {missing[0]}")
    words = " ".join(said.text.split())
    evidence = party.Evidence(
        "t3-message", ref, words, config.user.stamp(said.at), said.title, True
    )
    who = acts.cli_party(args, evidence)
    with locked(run.state, acts.LOCK):
        new = [one for one in numbers if one not in held(run.state, slug, ref)]
        if new:
            line = f"waived {slug}: lines {', '.join(map(str, new))}, on {ref}"
            action = party.Action(KIND, slug, pre=" ".join(map(str, new)))
            acts.logged(run, who, action, evidence, "done", line)
    _written(brief, text, items, numbers, ref)
    print(f"waived {slug}: lines {', '.join(map(str, numbers))}, on {ref}")
    return 0


def _brief(
    run: Pass, project: str, slug: str, numbers: list[int]
) -> tuple[Path, str, tuple[str, ...]]:
    """The row's brief, its text and its `Done when` lines. Refuse a row with no brief and a line
    number the brief does not have."""
    brief = run.home / "tasks" / f"{slug}.md"
    if not brief.is_file():
        raise Refused(f"refused: {project}'s home has no brief {slug}")
    text = brief.read_text()
    items = meets.done_when(head_lines(text))
    off = [one for one in numbers if not 1 <= one <= len(items)]
    if off:
        raise Refused(f"refused: {slug}'s brief has no Done when line {off[0]}")
    return brief, text, items


def _written(brief: Path, text: str, items: tuple[str, ...], numbers: list[int], ref: str) -> None:
    """Append the brief's `Waived:` line for each line number it has none for on `ref`."""
    there = {(one.number, one.ref) for one in meets.waivers(text)}
    lines = [
        f"{meets.WAIVED} {items[one - 1]}, {ref}\n" for one in numbers if (one, ref) not in there
    ]
    if lines:
        brief.write_text(text + ("" if text.endswith("\n") else "\n") + "".join(lines))


def _root(
    run: Pass,
    args: argparse.Namespace,
    brief: Path,
    text: str,
    items: tuple[str, ...],
    numbers: list[int],
) -> int:
    """`jbus waive --as root`: the root home's own waiver, as the module says. It logs one act
    whose id is the hash of what it waives and why, so its `Waived:` lines can name it by
    `root/<id>` and the same waiver again is the same act."""
    slug, by = args.slug, args.from_ or ""
    if not by or by != thread_of(run.home):
        raise Refused(f"refused: --from {by or 'nothing'} {NOT_ROOT}")
    reason, undo = " ".join((args.reason or "").split()), " ".join((args.undo or "").split())
    if not reason:
        raise Refused("refused: a root waiver names why the line need not hold, --reason")
    if not undo:
        raise Refused(
            "refused: a root waiver names how to undo it, --undo: one that cannot be undone is "
            "the user's to waive"
        )
    doors = party.doors(text)
    if doors:
        raise Refused(
            f"refused: {slug} holds for {', '.join(doors)}, so its merge cannot be undone and the "
            "user waives its lines"
        )
    pre = " ".join(map(str, numbers))
    id = hashlib.sha256(json.dumps([slug, pre, reason, undo]).encode()).hexdigest()[:16]
    ref = f"{party.ROOT.kind}/{id}"
    evidence = party.Evidence("typed", ref, reason, run.user.stamp(run.now), by, undo=undo)
    said = f"root waived {slug}: line{'s' if len(numbers) > 1 else ''} {', '.join(pre.split())}"
    with locked(run.state, acts.LOCK):
        if not any(one["id"] == id for one in acts.read(run.state)):
            action = party.Action(KIND, slug, pre=pre)
            line = f"{said}, because {reason}; undo: {undo}"
            acts.logged(run, party.ROOT, action, evidence, "done", line, id=id)
    _written(brief, text, items, numbers, ref)
    print(f"{said}, as {ref}")
    return 0


def recent(state: Path, now: datetime) -> list[dict[str, Any]]:
    """The root's own waivers made in the `SHOWN` before `now`, oldest first: what `jbus needs`
    tells the user, with nothing to answer."""
    return [
        act
        for act in acts.read(state)
        if act["action"]["verb"] == KIND
        and act["party"]["kind"] == party.ROOT.kind
        and act["outcome"] == "done"
        and timedelta(0) <= now - datetime.fromisoformat(act["at"]) <= SHOWN
    ]


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug", help="the row whose Done when lines the user waived")
    parser.add_argument(
        "lines", nargs="+", type=int, metavar="LINE", help="a Done when line's number"
    )
    parser.add_argument("--to", metavar="PROJECT", help="the project, by default this repo's")
    parser.add_argument(
        "--message",
        metavar="THREAD/MESSAGE",
        help="the user's own reply in a home's thread to the home's ask that named the lines"
        "; THREAD/last is the user's newest message there",
    )
    parser.add_argument(
        "--as", dest="as_", choices=(*party.CLI_PARTIES, party.ROOT.kind), default="home"
    )
    parser.add_argument(
        "--from",
        dest="from_",
        metavar="THREAD",
        help="with --as root: the root home's own thread, its home-id",
    )
    parser.add_argument("--reason", help="with --as root: why the line need not hold")
    parser.add_argument("--undo", help="with --as root: how the merge it lets through is undone")


VERBS = (
    verbs.Verb(
        "waive",
        "the user's plain reply to a home's ask, or the root's own waiver, as the brief's "
        "Waived: lines",
        _arguments,
        _waive,
    ),
)
