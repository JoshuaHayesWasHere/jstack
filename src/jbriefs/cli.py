from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from jbriefs import findings, page, parse, pick, skills

DEFAULT_STATE = Path.home() / ".local" / "state" / "home"


def default_out() -> Path:
    """Under the cache, never the state directory: the homes own that."""
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "jbriefs" / "briefs.html"


def pick_parser() -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(
        prog="jbriefs pick",
        description="Print the role skill, the playbook and the other skills for a brief, a "
        "scout's request, or text with no file.",
    )
    made.add_argument(
        "work",
        help="a brief under tasks/, a request under scouts/, or - to read text from stdin",
    )
    return made


def pick_main(argv: list[str]) -> int:
    made = pick_parser()
    args = made.parse_args(argv)
    if args.work == "-":
        job = pick.work(None, sys.stdin.read())
    else:
        path = Path(args.work).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            made.error(f"cannot read {path}: {error.strerror}")
        job = pick.work(path.resolve(), text)
    for line in pick.pick(job):
        print(line)
    return 0


def parser() -> argparse.ArgumentParser:
    """The parser of `jbriefs`; `jbriefs pick` has its own, `pick_parser`."""
    made = argparse.ArgumentParser(
        prog="jbriefs",
        description="Write one page of every home's handoff, open plan entries, briefs and "
        "results, and print its path.",
    )
    made.add_argument(
        "state",
        nargs="?",
        type=Path,
        default=DEFAULT_STATE,
        help="the directory that holds one home per repo (default: %(default)s); "
        "`jbriefs pick <path | ->` picks the skills for a piece of work instead",
    )
    made.add_argument("--out", type=Path, help="where to write the page (default: the cache)")
    made.add_argument(
        "--skills",
        type=Path,
        metavar="BRIEF",
        help="print in full each skill or principle the brief's Skills: line names, and the "
        "artifact each owes; write no page",
    )
    made.add_argument(
        "--skills-run",
        type=Path,
        metavar="BRIEF",
        help="print the artifact the brief's Results hold for each skill its Skills: line "
        "names, or that it has none; write no page",
    )
    made.add_argument(
        "--findings",
        type=Path,
        metavar="BRIEF",
        help="print the findings of every ## Review section of the brief as one triaged list, "
        "each with its id, its reviewers, its bucket and its answer; write no page",
    )
    told = made.add_mutually_exclusive_group()
    told.add_argument(
        "--left",
        action="store_true",
        help="with --findings, print only what the crew is to do next with them",
    )
    told.add_argument(
        "--rounds",
        action="store_true",
        help="with --findings, print only the sections that ran, the head the last saw, "
        "every head a section names and the blocking declines no scoped pass has ruled on",
    )
    return made


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["pick"]:
        return pick_main(argv[1:])
    made = parser()
    args = made.parse_args(argv)

    if (args.left or args.rounds) and not args.findings:
        made.error("--left and --rounds go with --findings")
    if args.findings:
        try:
            text = args.findings.expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            print(f"jbriefs: {args.findings} cannot be read: {error.strerror}", file=sys.stderr)
            return 1
        said = findings.triage(text)
        if args.left:
            print(findings.left(said))
        elif args.rounds:
            print(findings.rounds(said))
        else:
            for line in findings.listed(said):
                print(line)
            print(f"next: {findings.left(said)}")
        return 0
    if args.skills_run:
        said = skills.shown(args.skills_run.expanduser().read_text())
        if said:
            print(said)
        return 0
    if args.skills:
        said = skills.load(args.skills.expanduser().read_text())
        if said:
            print(said)
        return 0

    state = args.state.expanduser()
    out = (args.out or default_out()).expanduser()
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    html = page.render(parse.repos(state), state=state, generated=generated)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    return 0
