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
"""

from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from pathlib import Path

from jbriefs import meets
from jbus import Config, Refused, acts, locked, party, queue, t3, verbs
from jbus.passes import Pass
from jsettings.brief import head_lines

KIND = "waive"
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
    """`jbus waive`: bind the user's plain reply to the home's ask, as the module says."""
    project = verbs.project(config, args.to)
    run = Pass(config, project, datetime.now(UTC), lambda _: None)
    slug, ref, numbers = args.slug, args.message, sorted(set(args.lines))
    brief = run.home / "tasks" / f"{slug}.md"
    if not brief.is_file():
        raise Refused(f"refused: {project.name}'s home has no brief {slug}")
    text = brief.read_text()
    items = meets.done_when(head_lines(text))
    off = [one for one in numbers if not 1 <= one <= len(items)]
    if off:
        raise Refused(f"refused: {slug}'s brief has no Done when line {off[0]}")
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
    there = {(one.number, one.ref) for one in meets.waivers(text)}
    lines = [
        f"{meets.WAIVED} {items[one - 1]}, {ref}\n" for one in numbers if (one, ref) not in there
    ]
    if lines:
        brief.write_text(text + ("" if text.endswith("\n") else "\n") + "".join(lines))
    print(f"waived {slug}: lines {', '.join(map(str, numbers))}, on {ref}")
    return 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug", help="the row whose Done when lines the user waived")
    parser.add_argument(
        "lines", nargs="+", type=int, metavar="LINE", help="a Done when line's number"
    )
    parser.add_argument("--to", metavar="PROJECT", help="the project, by default this repo's")
    parser.add_argument(
        "--message",
        required=True,
        metavar="THREAD/MESSAGE",
        help="the user's own reply in a home's thread to the home's ask that named the lines",
    )
    parser.add_argument("--as", dest="as_", choices=party.CLI_PARTIES, default="home")


VERBS = (
    verbs.Verb(
        "waive",
        "the user's plain reply to a home's ask, as the brief's Waived: lines",
        _arguments,
        _waive,
    ),
)
