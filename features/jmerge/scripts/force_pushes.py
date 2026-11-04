"""Say why each branch of a merged pull request was force-pushed, over a period.

`jbus ci` counts the force-pushes of the branches of the pull requests merged in a period, over
those pull requests (`rebases per merged PR`, held to under 0.3). This splits that count by what
jbus told the crew before each push:

- `crew fix`: its check failed (`failed`, `refailed`), a review found something (`review` with
  findings, `rereview`, `expedite`), a rebase dropped lines (`drops`), or it was told to carry on
  (`resume`)
- `stack move`: the pull request it was stacked on merged (`restack`)
- `conflict`: it conflicted with main (`conflict`, and a `rebase` for a conflict or for a check
  that failed over today's main)
- `other`: anything else, a told `mainmoved` and a push no event explains included

The cause of a push is the last such event of its pull request in the two hours before it, as
`jbus.ci.numbers` reads a push, else the last since the push before it, at most a day back.

    uv run python features/jmerge/scripts/force_pushes.py ~/.local/state/jbus/jstack \\
        --since 2026-10-26T14:00:00Z --until 2026-11-02T14:00:00Z

It reads `ci-prs.jsonl` and `events.jsonl` in that state directory and prints the counts.

With `--files`, it also prints a table of what lay under each `conflict` and `crew fix` push, the
counts adding up to the two lines above it, and a table of each file that conflicted under them,
with the kinds of its hunks, read with `merge.conflictStyle=diff3`: `insert` where both sides add
lines at one place in the base (two rows appending to one list), `renumber` where only a number
changed, `edit` where both sides changed a line, `whole-file` where the file has no markers. The
file with the most `insert` hunks is its top line: the next list to split into one file per entry.
Under it, each row of `SPLITS` that does such a split says how many insert hunks its paths took
before its merge and since, which is none where the split worked. It asks GitHub for each push's
commits, one call for each 20 pull requests, and asks git, in the repo it runs in, which files
conflicted with main at the told event and at the push, each over the main of its moment. Run it in
a worktree with `origin/main` fetched, since it fetches the commits GitHub no longer has on a
branch.

With `--json`, it prints the same as one JSON object instead, for a program to read: the counts,
and with `--files` each file that conflicted, with its pull requests and its hunks by kind
(`files_of`). `jbus.collisions` reads it for the weekly report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

LOOKBACK = timedelta(hours=2)
FALLBACK = timedelta(hours=24)
CAUSES = ("crew fix", "stack move", "conflict", "other")
FIX = {"failed", "refailed", "expedite", "rereview", "drops", "resume"}
TOLD = {*FIX, "review", "restack", "conflict", "rebase", "mainmoved"}

EXPLAINED = ("conflict", "crew fix")
REBASED = "no conflict, rebased onto a later main"
REWRITTEN = "no conflict, rewritten on the same base"
NUMBERS = "line numbers only, in cites of code"
GENERATED = "generated files"
SPECS = "the specs and the tests that map them, which cited code by line until #675"
LIST = "the list of event kinds or the table of verbs"
DOCS = "other docs"
PARENT = "code, a cleanup row against the row it cleans up"
WAVE = "code, two rows of one wave"
ROWS = "code, two other rows"
UNKNOWN = "not known: GitHub gave no commit for the push, or git could not read it"
REASONS = (
    REBASED,
    REWRITTEN,
    NUMBERS,
    GENERATED,
    SPECS,
    LIST,
    DOCS,
    PARENT,
    WAVE,
    ROWS,
    UNKNOWN,
)
LISTS = {
    "features/jbus/docs/jbus/events-and-the-webhook.md",
    "features/jbus/docs/jbus/events-and-wakes.md",
    "features/jbus/docs/jbus/the-verbs.md",
}
MAPS = ("/spec/", "tests/test_flow_spec.py", "tests/test_home_tree_spec.py", "main_red_model.py")
# A push is as hard as the hardest file that conflicted, so it is cut only when all of them are.
HARDEST = (NUMBERS, GENERATED, SPECS, LIST, DOCS, "code")
# What one conflict hunk is, read with merge.conflictStyle=diff3: both sides add lines where the
# base has none (two rows append to one list), the sides differ only in their numbers, or any other;
# a conflicted file with no markers (a delete, a binary) conflicted as a whole.
KINDS = ("insert", "renumber", "edit", "whole-file")
# The rows that split a list two rows kept adding to into one file per entry, and the paths of the
# list before the split and of its entries after it: after its merge none should take an insert.
SPLITS = {
    "tm-kpi-registry-split": (
        "features/jbus/src/jbus/telemetry/kpis.py",
        "features/jbus/src/jbus/telemetry/kpis/",
        "features/jbus/src/jbus/telemetry/schema.py",
        "features/jbus/src/jbus/telemetry/migrations/",
        "features/jbus/src/jbus/telemetry/views/",
    ),
    "tm-source-modules": (
        "features/jbus/src/jbus/telemetry/records.py",
        "features/jbus/src/jbus/telemetry/sources/",
        "features/jbus/docs/jbus/the-telemetry-store.md",
        "features/jbus/tests/test_jbus_telemetry.py",
    ),
    "verbs-one-line-lists": ("features/jbus/docs/jbus/the-verbs.md",),
}
# A push a file conflicted under: when, the pull request's number, and the kinds of its hunks.
Hit = tuple[datetime, int, list[str]]
PUSHES = """
query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { %s } }
"""
TIMELINE = """
pr%d: pullRequest(number: %d) {
  timelineItems(itemTypes: [HEAD_REF_FORCE_PUSHED_EVENT], first: 100) {
    nodes { ... on HeadRefForcePushedEvent {
      createdAt beforeCommit { oid } afterCommit { oid }
    } }
  }
}
"""


def when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def cause_of(event: dict) -> str:
    kind, text = event["event"], event.get("text", "") + event.get("line", "")
    if kind in FIX or kind == "review":
        return "crew fix"
    if kind == "restack":
        return "stack move"
    if kind == "conflict" or (kind == "rebase" and re.search(r"conflicts with|fails on", text)):
        return "conflict"
    return "other"


def told(pulls: list[dict], events: list[dict]) -> dict[int, list[tuple[datetime, str]]]:
    """Each pull request's told events, as (time, cause). An event names its pull request by
    its slug, which is its branch, else by the `#<n>` of its line, except a `restack`, whose
    number is the pull request that merged under it."""
    numbers = {one["branch"]: int(one["number"]) for one in pulls}
    found: dict[int, list[tuple[datetime, str]]] = {}
    for event in events:
        kind = event.get("event")
        if kind not in TOLD or not event.get("at"):
            continue
        if kind == "review" and "findings" not in event.get("line", ""):
            continue
        number = numbers.get(event.get("slug", ""))
        named = re.search(r"#(\d+)", event.get("line", ""))
        if number is None and named and kind != "restack":
            number = int(named[1])
        if number is not None:
            found.setdefault(number, []).append((when(event["at"]), cause_of(event)))
    return found


def merged_in(pulls: list[dict], since: datetime, until: datetime) -> list[dict]:
    return [one for one in pulls if one.get("merged") and since <= when(one["merged"]) < until]


def pushes_of(
    pulls: list[dict], events: list[dict], since: datetime, until: datetime
) -> list[tuple[dict, datetime, tuple[datetime, str] | None]]:
    """Each force-push of each pull request merged in `[since, until)`, with the told event that
    gives its cause, as (time, cause), or None where no event does."""
    merged = merged_in(pulls, since, until)
    by_pull = told(merged, events)
    found = []
    for one in merged:
        near = by_pull.get(int(one["number"]), [])
        pushes = sorted(when(at) for at in one.get("pushes", []))
        for at, pushed in enumerate(pushes):
            before = [m for m in near if pushed - LOOKBACK <= m[0] <= pushed]
            if not before:
                start = max(pushed - FALLBACK, pushes[at - 1] if at else pushed - FALLBACK)
                before = [m for m in near if start <= m[0] <= pushed]
            found.append((one, pushed, max(before) if before else None))
    return found


def causes(pulls: list[dict], events: list[dict], since: datetime, until: datetime) -> Counter:
    """The cause of each force-push of each pull request merged in `[since, until)`."""
    counted: Counter = Counter(dict.fromkeys(CAUSES, 0))
    for _, _, event in pushes_of(pulls, events, since, until):
        counted[event[1] if event else "other"] += 1
    return counted


def ran(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """git's answer, a binary file it shows read with its undecodable bytes replaced."""
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, errors="replace"
    )


def git(repo: Path, *args: str) -> str:
    return ran(repo, *args).stdout


def merged_over(repo: Path, main: str, head: str) -> tuple[str, list[str]] | None:
    """The tree of `head` merged over `main`, and the files of it that conflict, or None where git
    could not merge them: merge-tree ends 0 on a clean merge, 1 on a conflict, else on a fault."""
    command = ["-c", "merge.conflictStyle=diff3", "merge-tree", "--write-tree", "--name-only"]
    said = ran(repo, *command, "--no-messages", main, head)
    lines = said.stdout.splitlines()
    if said.returncode not in (0, 1) or not lines:
        return None
    return lines[0], lines[1:]


def hunks_in(repo: Path, tree: str, path: str) -> list[tuple[str, str, str]]:
    """Each conflict hunk of one file of a merged tree, as its (ours, base, theirs) text."""
    found: list[tuple[str, str, str]] = []
    side: dict[str, list[str]] | None = None
    part = ""
    for line in git(repo, "show", f"{tree}:{path}").splitlines():
        if line.startswith("<<<<<<< "):
            side, part = {"ours": [], "base": [], "theirs": []}, "ours"
        elif side is None:
            continue
        elif line.startswith("||||||| "):
            part = "base"
        elif line == "=======":
            part = "theirs"
        elif line.startswith(">>>>>>> "):
            found.append(tuple("\n".join(side[k]) for k in ("ours", "base", "theirs")))
            side = None
        else:
            side[part].append(line)
    return found


def same_but_numbers(ours: str, theirs: str) -> bool:
    return re.sub(r"\d+", "N", ours) == re.sub(r"\d+", "N", theirs)


def hunk_kinds(repo: Path, tree: str, path: str) -> list[str]:
    """The kind of each conflict hunk of one file of a merged tree, as `KINDS` names them."""
    kinds = []
    for ours, base, theirs in hunks_in(repo, tree, path):
        if not base.strip() and ours.strip() and theirs.strip():
            kinds.append("insert")
        else:
            kinds.append("renumber" if same_but_numbers(ours, theirs) else "edit")
    return kinds or ["whole-file"]


def kind_of_file(repo: Path, tree: str, path: str) -> str:
    """What conflicted in one file. A hunk whose two sides differ only in their digits is a cite
    of a line that moved."""
    if path in LISTS:
        return LIST
    if path.endswith(("uv.lock", "CATALOG.md", ".png")) or "/fixtures/" in path:
        return GENERATED
    hunks = hunks_in(repo, tree, path)
    if hunks and all(same_but_numbers(ours, theirs) for ours, _, theirs in hunks):
        return NUMBERS
    if any(part in path for part in MAPS):
        return SPECS
    return DOCS if path.endswith(".md") else "code"


def against(repo: Path, branch: str, branches: dict[int, str], files: list, main: str, head: str):
    """Which rows' merges on main made the code of a push conflict: the row a cleanup row cleans
    up, a row of the same wave, by the first word of its slug, or another."""
    base = git(repo, "merge-base", head, main).strip()
    log = git(repo, "log", "--format=%s", f"{base}..{main}", "--", *files)
    others = [branches.get(int(n), "") for n in re.findall(r"\(#(\d+)\)$", log, re.M)]
    bare = branch.removeprefix("cleanup-")
    if any(other.removeprefix("cleanup-") == bare for other in others):
        return PARENT
    return WAVE if any(o.split("-")[0] == branch.split("-")[0] for o in others) else ROWS


def reason_of(
    repo: Path,
    before: str,
    after: str,
    at_push: str,
    at_event: str,
    branch: str,
    branches: dict[int, str],
) -> tuple[str, list[str], dict[str, list[str]]]:
    """What lay under one push from `before` to `after`, the files of that kind that conflicted
    over main at the told event, or over main at the push, and the kinds of the hunks of every file
    that conflicted, read where it conflicted at the told event, else at the push. A commit git
    cannot read, or a merge or merge base it cannot work out, is not known, never a push with no
    conflict."""
    commits = (before, after, at_push, at_event)
    if any(ran(repo, "cat-file", "-e", f"{c}^{{commit}}").returncode for c in commits):
        return UNKNOWN, [], {}
    pushed, told_then = merged_over(repo, at_push, before), merged_over(repo, at_event, before)
    if pushed is None or told_then is None:
        return UNKNOWN, [], {}
    tree, files = pushed[0], sorted({*pushed[1], *told_then[1]})
    if not files:
        bases = [ran(repo, "merge-base", head, at_push) for head in (before, after)]
        if any(base.returncode for base in bases):
            return UNKNOWN, [], {}
        return (REBASED if bases[0].stdout != bases[1].stdout else REWRITTEN), [], {}
    hunks = {
        path: hunk_kinds(repo, told_then[0] if path in told_then[1] else tree, path)
        for path in files
    }
    kinds = {path: kind_of_file(repo, tree, path) for path in files}
    hardest = max(kinds.values(), key=HARDEST.index)
    hard = [path for path, kind in kinds.items() if kind == hardest]
    if hardest != "code":
        return hardest, hard, hunks
    return against(repo, branch, branches, hard, at_push, before), hard, hunks


def pushed_commits(repo: Path, numbers: list[int]) -> dict[tuple[int, datetime], tuple[str, str]]:
    """The commits before and after each force-push of these pull requests, from GitHub, fetched
    into `repo` where it lacks them."""
    whose = git(repo, "remote", "get-url", "origin").strip().removesuffix(".git")
    owner, name = re.split(r"[:/]", whose)[-2:]
    found: dict[tuple[int, datetime], tuple[str, str]] = {}
    for start in range(0, len(numbers), 20):
        fields = "".join(TIMELINE % (n, n) for n in numbers[start : start + 20])
        said = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={PUSHES % fields}"]
            + ["-F", f"owner={owner}", "-F", f"name={name}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for field, pull in json.loads(said)["data"]["repository"].items():
            for push in pull["timelineItems"]["nodes"]:
                if push.get("beforeCommit") and push.get("afterCommit"):
                    commits = (push["beforeCommit"]["oid"], push["afterCommit"]["oid"])
                    found[(int(field[2:]), when(push["createdAt"]))] = commits
    wanted = {commit for commits in found.values() for commit in commits}
    absent = [c for c in sorted(wanted) if git(repo, "cat-file", "-t", c).strip() != "commit"]
    if absent:
        git(repo, "fetch", "-q", "origin", *absent)
    return found


def main_moves(repo: Path, pulls: list[dict]) -> list[tuple[datetime, str]]:
    """Each commit main has been, with when it landed, the oldest first. Main was rewritten on
    2026-10-23, so today's `origin/main` has other commits for the merges before then, which no
    head of that time shares a history with: a pull request's merge commit is main from its merge
    on where its first parent was main before it, and a merge into another row's branch is not. A
    commit of today's `origin/main` that names no such pull request is main from its commit time,
    in the order of its first parents, so two that landed in one second keep their order."""
    log = git(repo, "log", "--first-parent", "--format=%cI %H %s", "origin/main").splitlines()
    today = [(line.split(" ", 2) + [""])[:3] for line in reversed(log)]
    on_main = {commit for _, commit, _ in today}
    merges = sorted(
        (when(one["merged"]), one["merge_commit"], int(one["number"]))
        for one in pulls
        if one.get("merged") and one.get("merge_commit")
    )
    commits = [c for _, c, _ in merges]
    shown = git(repo, "log", "--no-walk=unsorted", "--ignore-missing", "--format=%H %P", *commits)
    first_parent = {line.split()[0]: line.split()[1:2] for line in shown.splitlines()}
    moves, numbers = [], set()
    for merged, commit, number in merges:
        if commit in on_main or set(first_parent.get(commit, [])) & on_main:
            on_main.add(commit)
            moves.append((merged, commit))
            numbers.add(number)
    for at, commit, subject in today:
        named = re.search(r"\(#(\d+)\)$", subject)
        if not (named and int(named[1]) in numbers):
            moves.append((when(at), commit))
    return sorted(moves, key=lambda move: move[0])


def explained(
    repo: Path, pulls: list[dict], events: list[dict], since: datetime, until: datetime
) -> tuple[dict[str, Counter], dict[str, Counter], dict[str, list[Hit]], int]:
    """The reason under each `conflict` and `crew fix` push, counted for each cause, the files
    that conflicted for each reason, for each file that conflicted each push it conflicted under
    with the kinds of its hunks, and how many pushes that leaves out: those of a pull request
    merged into another row's branch, which main was never the base of."""
    told_pushes = [
        (one, pushed, event)
        for one, pushed, event in pushes_of(pulls, events, since, until)
        if event and event[1] in EXPLAINED
    ]
    numbers = sorted({int(one["number"]) for one, _, _ in told_pushes})
    commits = pushed_commits(repo, numbers)
    landed = main_moves(repo, pulls)
    branches = {int(one["number"]): one["branch"] for one in pulls}
    onto_main = {commit for _, commit in landed}

    def main_then(moment: datetime) -> str:
        return [commit for at, commit in landed if at <= moment][-1]

    counted: dict[str, Counter] = {cause: Counter() for cause in EXPLAINED}
    files: dict[str, Counter] = defaultdict(Counter)
    hunks: dict[str, list[Hit]] = defaultdict(list)
    elsewhere = 0
    for one, pushed, event in told_pushes:
        pair = commits.get((int(one["number"]), pushed))
        if pair is None:
            counted[event[1]][UNKNOWN] += 1
            continue
        reason, conflicted, kinds = reason_of(
            repo, *pair, main_then(pushed), main_then(event[0]), one["branch"], branches
        )
        counted[event[1]][reason] += 1
        files[reason].update(conflicted)
        merge = one.get("merge_commit")
        if merge and merge not in onto_main and not ran(repo, "cat-file", "-e", merge).returncode:
            elsewhere += 1
            continue
        for path, of_path in kinds.items():
            hunks[path].append((pushed, int(one["number"]), of_path))
    return counted, files, hunks, elsewhere


def table(counted: dict[str, Counter], files: dict[str, Counter]) -> list[str]:
    """The Markdown table of `explained`, with a line of each cause's total under it."""
    lines = ["| What lay under the push | conflict | crew fix | Files, most often first |"]
    lines.append("|---|---|---|---|")
    for reason in REASONS:
        shown = ", ".join(f"`{path}` {n}" for path, n in files[reason].most_common(3))
        lines.append(
            f"| {reason} | {counted['conflict'][reason]} | {counted['crew fix'][reason]} "
            f"| {shown} |"
        )
    totals = [str(sum(counted[cause].values())) for cause in EXPLAINED]
    lines.append(f"| all | {totals[0]} | {totals[1]} | |")
    return lines


def split_of(path: str) -> str:
    return next((row for row, paths in SPLITS.items() if path.startswith(paths)), "")


def by_file(
    hunks: dict[str, list[Hit]],
    pulls: list[dict],
    until: datetime,
    elsewhere: int = 0,
) -> list[str]:
    """The Markdown table of each file that conflicted, with the pushes it conflicted under and its
    hunks by kind, first the file the most rows took an `insert` hunk in, then the most `insert`
    hunks: the list rows keep adding to is the top line.
    Under it, how many pushes it leaves out, and a line for each row of `SPLITS`: the insert hunks
    in its paths before its merge and since."""
    counted = {
        path: Counter(k for _, _, kinds in pushed for k in kinds) for path, pushed in hunks.items()
    }
    rows = {path: {number for _, number, _ in pushed} for path, pushed in hunks.items()}
    adding = {
        path: {number for _, number, kinds in pushed if "insert" in kinds}
        for path, pushed in hunks.items()
    }
    order = sorted(
        hunks,
        key=lambda path: (
            -len(adding[path]),
            -counted[path]["insert"],
            -counted[path].total(),
            path,
        ),
    )
    lines = ["| Conflicted file | Rows | Pushes | Hunks | Split into one file per entry by |"]
    lines.append("|---|---|---|---|---|")
    for path in order:
        shown = ", ".join(f"{kind} {counted[path][kind]}" for kind in KINDS if counted[path][kind])
        split = f" {split_of(path)} " if split_of(path) else " "
        lines.append(f"| `{path}` | {len(rows[path])} | {len(hunks[path])} | {shown} |{split}|")
    merges = {one["branch"]: one for one in pulls if one.get("merged")}
    lines.append("")
    if elsewhere:
        pushes = "push" if elsewhere == 1 else "pushes"
        lines.append(
            f"Left out: {elsewhere} {pushes} of pull requests merged into another row's branch, "
            "which main was never the base of."
        )
        lines.append("")
    for row in SPLITS:
        inserts = [
            (at, kinds.count("insert"))
            for path, pushed in hunks.items()
            if split_of(path) == row
            for at, _, kinds in pushed
        ]
        merged = merges.get(row)
        if merged is None or when(merged["merged"]) >= until:
            before = sum(n for _, n in inserts)
            lines.append(f"- {row}, not merged: {before} insert hunks before it")
            continue
        at = when(merged["merged"])
        before = sum(n for pushed, n in inserts if pushed < at)
        since = sum(n for pushed, n in inserts if pushed >= at)
        lines.append(
            f"- {row} (#{merged['number']}), merged {at:%Y-%m-%dT%H:%MZ}: {before} insert hunks "
            f"before it, {since} since"
        )
    return lines


def files_of(hunks: dict[str, list[Hit]]) -> list[dict]:
    """Each file that conflicted, by path, with the pull requests it conflicted under and the count
    of its hunks of each kind."""
    return [
        {
            "path": path,
            "pulls": sorted({number for _, number, _ in hunks[path]}),
            "pushes": len(hunks[path]),
            "hunks": dict(Counter(kind for _, _, kinds in hunks[path] for kind in kinds)),
        }
        for path in sorted(hunks)
    ]


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    asked = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    asked.add_argument("state", type=Path, help="the project's jbus state directory")
    asked.add_argument("--since", type=when, required=True)
    asked.add_argument("--until", type=when, required=True)
    asked.add_argument(
        "--files", action="store_true", help="also say what lay under each conflict and crew fix"
    )
    asked.add_argument("--json", action="store_true", help="print one JSON object instead")
    args = asked.parse_args()
    pulls = read(args.state / "ci-prs.jsonl")
    events = read(args.state / "events.jsonl")
    counted = causes(pulls, events, args.since, args.until)
    merged = len(merged_in(pulls, args.since, args.until))
    total = sum(counted.values())
    if args.json:
        said: dict = {"pushes": total, "merged": merged, "causes": dict(counted)}
        if args.files:
            _, _, hunks, elsewhere = explained(Path.cwd(), pulls, events, args.since, args.until)
            said |= {"files": files_of(hunks), "elsewhere": elsewhere}
        print(json.dumps(said, sort_keys=True))
        return 0
    print(f"{total} force-pushes over {merged} merged pull requests ({total / max(merged, 1):.2f})")
    for cause in CAUSES:
        print(f"{cause}: {counted[cause]}")
    if args.files:
        print()
        counted, files, hunks, elsewhere = explained(
            Path.cwd(), pulls, events, args.since, args.until
        )
        print("\n".join(table(counted, files)))
        print()
        print("\n".join(by_file(hunks, pulls, args.until, elsewhere)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
