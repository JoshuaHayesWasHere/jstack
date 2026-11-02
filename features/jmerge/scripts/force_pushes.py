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
counts adding up to the two lines above it. It asks GitHub for each push's commits, one call for
each 20 pull requests, and asks git, in the repo it runs in, which files conflicted with main at the
told event and at the push. Run it in a worktree with `origin/main` fetched, since it fetches the
commits GitHub no longer has on a branch."""

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
UNKNOWN = "not known: GitHub gave no commit for the push"
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
HUNK = re.compile(r"^<{7} .*?\n(.*?)^\|{7} .*?\n.*?^={7}\n(.*?)^>{7} .*?$", re.S | re.M)
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
    counted: Counter = Counter({cause: 0 for cause in CAUSES})
    for _, _, event in pushes_of(pulls, events, since, until):
        counted[event[1] if event else "other"] += 1
    return counted


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True).stdout


def merged_over(repo: Path, main: str, head: str) -> tuple[str, list[str]]:
    """The tree of `head` merged over `main`, and the files of it that conflict."""
    command = ["-c", "merge.conflictStyle=diff3", "merge-tree", "--write-tree", "--name-only"]
    said = git(repo, *command, "--no-messages", main, head).splitlines()
    return said[0] if said else "", said[1:]


def kind_of_file(repo: Path, tree: str, path: str) -> str:
    """What conflicted in one file. A hunk whose two sides differ only in their digits is a cite
    of a line that moved."""
    if path in LISTS:
        return LIST
    if path.endswith(("uv.lock", "CATALOG.md", ".png")) or "/fixtures/" in path:
        return GENERATED
    hunks = HUNK.findall(git(repo, "show", f"{tree}:{path}"))
    if hunks and all(re.sub(r"\d+", "N", a) == re.sub(r"\d+", "N", b) for a, b in hunks):
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
) -> tuple[str, list[str]]:
    """What lay under one push from `before` to `after`, and the files of that kind that conflicted
    over main at the told event, or over main at the push."""
    tree, files = merged_over(repo, at_push, before)
    files = sorted({*files, *merged_over(repo, at_event, before)[1]})
    if not files:
        moved = git(repo, "merge-base", before, at_push) != git(repo, "merge-base", after, at_push)
        return (REBASED if moved else REWRITTEN), []
    kinds = {path: kind_of_file(repo, tree, path) for path in files}
    hardest = max(kinds.values(), key=HARDEST.index)
    hard = [path for path, kind in kinds.items() if kind == hardest]
    if hardest != "code":
        return hardest, hard
    return against(repo, branch, branches, hard, at_push, before), hard


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


def main_at(repo: Path) -> list[tuple[datetime, str]]:
    """Each commit of `origin/main` with when it landed, the oldest first."""
    log = git(repo, "log", "--first-parent", "--format=%cI %H", "origin/main").splitlines()
    return sorted((when(line.split()[0]), line.split()[1]) for line in log)


def explained(
    repo: Path, pulls: list[dict], events: list[dict], since: datetime, until: datetime
) -> tuple[dict[str, Counter], dict[str, Counter]]:
    """The reason under each `conflict` and `crew fix` push, counted for each cause, and the files
    that conflicted for each reason."""
    told_pushes = [
        (one, pushed, event)
        for one, pushed, event in pushes_of(pulls, events, since, until)
        if event and event[1] in EXPLAINED
    ]
    numbers = sorted({int(one["number"]) for one, _, _ in told_pushes})
    commits = pushed_commits(repo, numbers)
    landed = main_at(repo)
    branches = {int(one["number"]): one["branch"] for one in pulls}

    def main_then(moment: datetime) -> str:
        return [commit for at, commit in landed if at <= moment][-1]

    counted: dict[str, Counter] = {cause: Counter() for cause in EXPLAINED}
    files: dict[str, Counter] = defaultdict(Counter)
    for one, pushed, event in told_pushes:
        pair = commits.get((int(one["number"]), pushed))
        if pair is None:
            counted[event[1]][UNKNOWN] += 1
            continue
        reason, conflicted = reason_of(
            repo, *pair, main_then(pushed), main_then(event[0]), one["branch"], branches
        )
        counted[event[1]][reason] += 1
        files[reason].update(conflicted)
    return counted, files


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
    args = asked.parse_args()
    pulls = read(args.state / "ci-prs.jsonl")
    events = read(args.state / "events.jsonl")
    counted = causes(pulls, events, args.since, args.until)
    merged = len(merged_in(pulls, args.since, args.until))
    total = sum(counted.values())
    print(f"{total} force-pushes over {merged} merged pull requests ({total / max(merged, 1):.2f})")
    for cause in CAUSES:
        print(f"{cause}: {counted[cause]}")
    if args.files:
        print()
        print("\n".join(table(*explained(Path.cwd(), pulls, events, args.since, args.until))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
