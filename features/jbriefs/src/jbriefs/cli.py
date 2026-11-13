from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from jbriefs import (
    below,
    findings,
    home,
    meets,
    page,
    parse,
    pick,
    propose,
    proved,
    reviewers,
    shown,
    skills,
    stacked,
)
from jbriefs import status as status_line
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


def _yes(said: bool) -> str:
    return "yes" if said else "no"


def _reviewer(text: str) -> str:
    named = [one for one in below.reviewers(text, "Reviewer") if below.launched(one)]
    return named[0].split()[0].rstrip(",") if named else "none"


def _stacked(text: str) -> str:
    found = stacked.of(text)
    if found is not None:
        return stacked.line(found).removeprefix(stacked.LINE).strip()
    return "none" if stacked.said(text) is None else "malformed"


def _pull(text: str) -> str:
    found = below.pull(below.last_result(text))
    return "missing" if found is None else found.shown()


LINES = {
    "status": lambda text: status_line.of(below.last_result(text)).value,
    "pr": _pull,
    "reviewer": _reviewer,
    "reviewed": lambda text: _yes(reviewers.reviewed(text)),
    "reviewing": lambda text: _yes(reviewers.running(text)),
    "base": lambda text: found.branch if (found := stacked.of(text)) else "none",
    "stacked": _stacked,
}
"""What `jbriefs line` prints of a brief, each through the line's one reader, and never empty:
- `status`: the last Result's `Status:` as `jbriefs.status` reads it (`done`, `not done`,
  `paused`, `blocked`, `open`, `answered`, `other`, or `none`), a scout's last Report's in a
  request;
- `pr`: the pull request the last Result's `Branch:` line names (`below.pull`): its address,
  `after the review`, `none`, or `missing` where the Result has no `Branch:` line;
- `reviewer`: the thread of the first `Reviewer:` line below the first Result that names one,
  or `none`;
- `reviewed`: `yes` where the results hold a `## Review` or a reviewer (`findings.reviewed`);
- `reviewing`: `yes` where a reviewer launched has not written its section (`reviewers.running`);
- `base`: the branch of the head's `Stacked on:` line (`jbriefs.stacked`), or `none`;
- `stacked`: that line as `<slug> <branch>` or `<slug> <branch> at <commit>`, `malformed` for a
  line in neither shape, or `none`.
`path`, the brief's own path, may go with them, for a call over several briefs."""


def line_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="jbriefs line",
        description="Print what the lines a crew, a reviewer and jbus write say of each brief, "
        "read as jbriefs, jmerge and jbus read them: one line for each brief, its values "
        "joined by tabs.",
    )
    parser.add_argument(
        "what",
        help=f"the lines to print, joined by commas, of: {', '.join(LINES)}, and path, the "
        "brief's own path",
    )
    parser.add_argument("briefs", nargs="+", type=Path, metavar="BRIEF")
    args = parser.parse_args(argv)
    asked = args.what.split(",")
    unknown = [one for one in asked if one not in LINES and one != "path"]
    if unknown:
        parser.error(f"no such line: {', '.join(unknown)}; the lines are {', '.join(LINES)}, path")
    failed = 0
    for path in args.briefs:
        try:
            text = path.expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            print(f"jbriefs: {path} cannot be read: {error.strerror}", file=sys.stderr)
            failed = 1
            continue
        print("\t".join(str(path) if one == "path" else LINES[one](text) for one in asked))
    return failed


def not_run_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="jbriefs not-run",
        description="Append to the brief the `## Review` of a reviewer that stopped before its "
        "review, with `Verdict: not run` and its head, so the brief no longer waits on that "
        "reviewer (`jbriefs line reviewing` says no); write nothing where the brief already ends "
        "in that section.",
    )
    parser.add_argument("brief", type=Path, metavar="BRIEF")
    parser.add_argument("head", help="the head the review was to be of")
    parser.add_argument("why", help="the section's Why: line, why it stopped")
    parser.add_argument("by", help="the reviewer's By: line, as Start printed it, or empty")
    parser.add_argument("scope", help="on a scoped pass, its Scope: line, whole, else empty")
    args = parser.parse_args(argv)
    brief = args.brief.expanduser()
    if not brief.is_file():
        print(f"no section: there is no brief at {brief}")
        return 1
    text = brief.read_text(encoding="utf-8", errors="replace")
    section = reviewers.not_run(text, args.head, args.why, args.by, args.scope)
    if not section:
        print(f"no section: the brief already ends in a review of {args.head} that was not run")
        return 0
    with brief.open("a", encoding="utf-8") as out:
        out.write(section)
    print(f"written: ## Review with Verdict: not run, in {brief}")
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
    when = datetime.fromisoformat(said).astimezone(UTC)
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
    if argv[:1] == ["line"]:
        return line_main(argv[1:])
    if argv[:1] == ["not-run"]:
        return not_run_main(argv[1:])
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
        "`jbriefs pick <path | ->` picks the skills for a piece of work instead, and "
        "`jbriefs line <lines> <brief>...` prints what a brief's Result lines say, and "
        "`jbriefs not-run <brief> <head> <why> <by> <scope>` writes a stopped reviewer's section",
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
        "repo, a .py file whose change is to its docstrings and comments alone, or a Makefile or "
        "*.mk whose change is to its comment lines alone, being docs, or, exiting 1, the first "
        "file of no kind; write no page",
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
