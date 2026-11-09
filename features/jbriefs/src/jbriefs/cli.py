from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from jbriefs import findings, home, meets, page, parse, pick, propose, proved, shown, skills
from jsettings.paths import common_dir, jbus_state_dir


def default_out() -> Path:
    """A path under the cache. It is never in the state directory, which belongs to the homes."""
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


def go_of(slug: str, brief: Path) -> str:
    """Why a proposal for the brief would void a go, or an empty string where it voids none.

    It asks `jbus queue verify`, the one copy of the go rule, for the brief at `brief` and for
    the one jbus keeps: either go that holds is one an edit would void. A row the queue does not
    have has no go. Any other answer is one this cannot read, and it refuses."""
    for asked in (["--brief", str(brief)], []):
        ran = subprocess.run(
            [sys.executable, "-m", "jbus", "queue", "verify", slug, *asked],
            capture_output=True,
            text=True,
        )
        said = ran.stdout.strip()
        if said.startswith("refused: the queue has no row"):
            return ""
        try:
            found = json.loads(said)
        except ValueError:
            return f"jbus cannot say whether {slug} has a go: {said or ran.stderr.strip()}"
        if found.get("holds"):
            return f"the go holds for {slug} ({found.get('approved', '')})"
    return ""


def propose_main(brief: Path) -> int:
    try:
        text = brief.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        print(f"jbriefs: {brief} cannot be read: {error.strerror}", file=sys.stderr)
        return 1
    slug = propose.Brief.of(text, brief.stem).slug
    why = go_of(slug, brief)
    if why:
        print(
            f"jbriefs: refused: {why}, and a new Done when voids it: propose for a row with no go",
            file=sys.stderr,
        )
        return 1
    for one in propose.propose(text, brief.stem):
        print(one.line())
    return 0


def runnable_main(project: str | None, statuses: str) -> int:
    if project is None:
        common = common_dir()
        if common is None:
            print("jbriefs: --runnable needs --project outside a git repo", file=sys.stderr)
            return 1
        project = common.parent.name
    state = jbus_state_dir() / project
    try:
        found = propose.share(state, [one for one in statuses.split(",") if one])
    except (OSError, ValueError) as error:
        print(f"jbriefs: {state / 'queue.json'} cannot be read: {error}", file=sys.stderr)
        return 1
    print(found.line())
    return 0


def rounds(said: findings.Triage) -> str:
    """The one line the crew's "A second pass" reads about the review: how many sections ran,
    the head the last of them saw, and every head a section names, joined with commas, or `-`
    where there is none."""
    ran = [one for one in said.sections if one.ran]
    saw = next((one.head for one in reversed(ran) if one.head), "-")
    heads = ",".join(dict.fromkeys(one.head for one in said.sections if one.head)) or "-"
    return f"{len(ran)} {saw} {heads}"


def proved_none_main(base: str, head: str) -> int:
    listed = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", base, head], capture_output=True, text=True
    )
    if listed.returncode != 0:
        print(f"no kind: git diff {base} {head} failed: {listed.stderr.strip()}")
        return 1
    files = listed.stdout.splitlines()
    kinds, other = proved.none_kinds(files, proved.prose_in(os.getcwd(), base, head))
    if other or not kinds:
        print(f"no kind: {other or 'the change has no file'}")
        return 1
    print(f"Proved: none, {' and '.join(kinds)}")
    return 0


def store_time(said: str) -> str:
    """An ISO time in T3's store's own form, UTC with milliseconds and a `Z`
    (`2026-11-09T19:11:15.428Z`), so it compares as a string. A time with no zone is local."""
    when = datetime.fromisoformat(said).astimezone(timezone.utc)
    return when.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def shown_main(thread: str, since: str, store: Path, attachments: Path) -> int:
    try:
        found = shown.pictures(store, attachments, thread, since)
    except sqlite3.Error as error:
        print(f"jbriefs: {store} cannot be read: {error}", file=sys.stderr)
        return 1
    for one in found:
        print(one.line())
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
        default=home.homes_dir(),
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
    parser.add_argument(
        "--findings",
        type=Path,
        metavar="BRIEF",
        help="print the findings of every ## Review section of the brief as one triaged list, "
        "each with its id, its reviewers, its bucket and its answer; write no page",
    )
    parser.add_argument(
        "--meets",
        type=Path,
        metavar="BRIEF",
        help="print what the last review round says of the brief, as jmerge reads it: yes, no, "
        "unread, miscounted or none, the lines met (or -), the brief's Done when count and the "
        "head (or -); write no page",
    )
    parser.add_argument(
        "--propose",
        type=Path,
        metavar="BRIEF",
        help="print a proposal for each Done when item of the brief that runs nothing, one line "
        "each, `<n>. <kind>: <item with its check>`; refuse a brief whose go holds, which a new "
        "Done when would void; write no page",
    )
    parser.add_argument(
        "--runnable",
        action="store_true",
        help="print how many Done when items of the queue's rows of --status run something; "
        "write no page",
    )
    parser.add_argument(
        "--status",
        default="queued,running,pr",
        help="with --runnable, the statuses of the rows to count, with commas (default: "
        "%(default)s)",
    )
    parser.add_argument(
        "--project",
        help="with --runnable, the jbus project whose queue to read (default: this repo's name)",
    )
    parser.add_argument(
        "--proved-none",
        metavar="BASE..HEAD",
        help="print the `Proved: none, <kinds>` line of the change from BASE to HEAD in this "
        "repo, a .py file whose change is to its docstrings and comments alone being docs, or, "
        "exiting 1, the first file of no kind; write no page",
    )
    parser.add_argument(
        "--shown",
        metavar="THREAD",
        help="print, for each message of the T3 thread in which the user sent a picture, its "
        "time, its id, its first words and each picture's file, or `gone` where it is not on "
        "disk, for a brief's Shown: line; read T3's store read-only and write nothing",
    )
    parser.add_argument(
        "--since",
        metavar="ISO",
        help="with --shown, only the messages from this time on (with no zone, local time)",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=shown.STORE,
        help="with --shown, T3 Code's store (default: %(default)s)",
    )
    parser.add_argument(
        "--attachments",
        type=Path,
        default=shown.ATTACHMENTS,
        help="with --shown, T3 Code's attachments directory (default: %(default)s)",
    )
    told = parser.add_mutually_exclusive_group()
    told.add_argument(
        "--left",
        action="store_true",
        help="with --findings, print only what the crew is to do next with them",
    )
    told.add_argument(
        "--rounds",
        action="store_true",
        help="with --findings, print only the sections that ran, the head the last saw and "
        "every head a section names",
    )
    args = parser.parse_args(argv)

    if (args.left or args.rounds) and not args.findings:
        parser.error("--left and --rounds go with --findings")
    if args.since and not args.shown:
        parser.error("--since goes with --shown")
    if args.shown:
        try:
            since = store_time(args.since) if args.since else ""
        except ValueError:
            parser.error(f"--since {args.since} is no ISO time")
        return shown_main(
            args.shown,
            since,
            args.store.expanduser(),
            args.attachments.expanduser().resolve(),
        )
    if args.proved_none:
        base, _, head = args.proved_none.partition("..")
        return proved_none_main(base, head)
    if args.propose:
        return propose_main(args.propose.expanduser())
    if args.runnable:
        return runnable_main(args.project, args.status)
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
            print(rounds(said))
        else:
            for line in findings.listed(said):
                print(line)
            print(f"next: {findings.left(said)}")
        return 0
    if args.meets:
        try:
            text = args.meets.expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            print(f"jbriefs: {args.meets} cannot be read: {error.strerror}", file=sys.stderr)
            return 1
        print(meets.shown(meets.reading(text)))
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
