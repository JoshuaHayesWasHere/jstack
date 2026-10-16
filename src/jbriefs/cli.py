from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from jbriefs import page, parse, pick, skills

DEFAULT_STATE = Path.home() / ".local" / "state" / "home"


def default_out() -> Path:
    """Under the cache, never the state directory: the homes own that."""
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "jbriefs" / "briefs.html"


def pick_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="jbriefs pick",
        description="Print the role skill, the playbook and the other skills for a brief, a "
        "scout's request, or text with no file.",
    )
    parser.add_argument(
        "work",
        help="a brief under tasks/, a request under scouts/, or - to read text from stdin",
    )
    args = parser.parse_args(argv)
    if args.work == "-":
        job = pick.work(None, sys.stdin.read())
    else:
        path = Path(args.work).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            parser.error(f"cannot read {path}: {error.strerror}")
        job = pick.work(path.resolve(), text)
    for line in pick.pick(job):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["pick"]:
        return pick_main(argv[1:])
    parser = argparse.ArgumentParser(
        prog="jbriefs",
        description="Write one page of every home's handoff, open plan entries, briefs and "
        "results, and print its path.",
    )
    parser.add_argument(
        "state",
        nargs="?",
        type=Path,
        default=DEFAULT_STATE,
        help="the directory that holds one home per repo (default: %(default)s); "
        "`jbriefs pick <path | ->` picks the skills for a piece of work instead",
    )
    parser.add_argument("--out", type=Path, help="where to write the page (default: the cache)")
    parser.add_argument(
        "--skills",
        type=Path,
        metavar="BRIEF",
        help="print in full each skill or principle the brief's Skills: line names, and the "
        "artifact each owes; write no page",
    )
    parser.add_argument(
        "--skills-run",
        type=Path,
        metavar="BRIEF",
        help="print the artifact the brief's Results hold for each skill its Skills: line "
        "names, or that it has none; write no page",
    )
    args = parser.parse_args(argv)

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
