"""Find the hot files: `hot_files.py --since <date> [--until <date>] [--home <dir>] [--top <n>]`.

It prints three tables for the days from `--since` to `--until`, which is today when the
command leaves it out. Each table lists files with their counts, highest first, and keeps the
first `--top` (20):

1. merged pull requests that touched the file, from a run of `gh pr list --state merged
   --search merged:<since>..<until> --json number,files,createdAt,mergedAt` in the repo checked
   out here. The days are local days: the search gives each end with its local offset, since
   GitHub reads a bare date as UTC.
2. concurrent-open pairs: pairs of those pull requests that touched the file and were open at
   the same time, from creation to merge. The table counts each pair once.
3. rebases that dropped lines, from the home's `merge.log`. The script reads the `wait` and
   `hold` lines that jmerge logged in the range for pull requests of this repo, the lines that
   say `the rebase dropped <n> of ... in <file> and ...`. It counts each such line once for each
   pull request and head, and puts the lines dropped beside the count. A hold line names no
   head, so the script counts it once for each drop it reports.

jmerge logs a wait or hold line only when it differs from the last one for its pull request
(`merge.log.last`). So table 3 counts a rebase once, however long its pull request waited. A pull
request that waited on one drop and then on another shows both drops.

`gh pr list --json files` gives at most 100 files of a pull request, so when a pull request
lists 100 files, the script names it on stderr as undercounted. The home is
`~/.local/state/home/<repo>` unless `--home` names one. The script needs only the standard
library and `gh`.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, time
from itertools import combinations
from pathlib import Path

CAP = 100
FIELDS = "number,files,createdAt,mergedAt"
DROPPED = re.compile(
    r"^(\d{4}-\d\d-\d\d) \d\d:\d\d (?:wait|hold) (\d+) (\S+): .*?the rebase dropped (.+?)"
    r"(?: with no Dropped on rebase line at ([0-9a-f]{12}))?$"
)
LOST = re.compile(r"(\d+) of (?:main's lines|its own) in (\S+)")


def gh(*args):
    return json.loads(
        subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout
    )


def bound(day, at):
    """The local moment a day starts or ends, as GitHub's search reads it."""
    return datetime.combine(day, at).astimezone().isoformat(timespec="seconds")


def merged(since, until):
    search = f"merged:{bound(since, time.min)}..{bound(until, time(23, 59, 59))}"
    return gh(
        "pr", "list", "--state", "merged", "--search", search, "--limit", "1000", "--json", FIELDS
    )


def moment(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def touched(pulls):
    return Counter(one["path"] for pull in pulls for one in pull["files"])


def concurrent(pulls):
    """For each file, the pairs of pull requests that touched it while both were open."""
    open_on = {}
    for pull in pulls:
        span = (moment(pull["createdAt"]), moment(pull["mergedAt"]))
        for one in pull["files"]:
            open_on.setdefault(one["path"], []).append(span)
    pairs = Counter()
    for path, spans in open_on.items():
        for (start, end), (other_start, other_end) in combinations(spans, 2):
            if start < other_end and other_start < end:
                pairs[path] += 1
    return pairs


def drops(log, repo, since, until):
    """Per file, the rebases that dropped lines in it and the lines they dropped."""
    seen = set()
    rebases, lines = Counter(), Counter()
    for line in log.splitlines():
        found = DROPPED.match(line)
        if not found:
            continue
        day, number, slug, lost, head = found.groups()
        if not since.isoformat() <= day <= until.isoformat():
            continue
        if slug.startswith("https://") and not slug.startswith(f"{repo}/pull/"):
            continue
        key = (number, head or lost)
        if key in seen:
            continue
        seen.add(key)
        for count, path in LOST.findall(lost):
            lines[path] += int(count)
        for path in {path for _, path in LOST.findall(lost)}:
            rebases[path] += 1
    return rebases, lines


def ranked(counts, top):
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top]


def default_home():
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    if common.returncode:
        return None
    return Path.home() / ".local/state/home" / Path(common.stdout.strip()).parent.name


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", required=True, type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat, default=date.today())
    parser.add_argument("--home", type=Path)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()
    home = args.home or default_home()
    span = f"{args.since}..{args.until}"

    pulls = merged(args.since, args.until)
    for pull in sorted(pulls, key=lambda pull: pull["number"]):
        if len(pull["files"]) >= CAP:
            print(
                f"undercounted: #{pull['number']} lists {CAP} files, gh's cap, "
                f"so a file past its {CAP}th is not counted",
                file=sys.stderr,
            )

    print(f"Merged pull requests per file, {span}: {len(pulls)} pull requests")
    for path, count in ranked(touched(pulls), args.top):
        print(f"{count:6}  {path}")
    print()
    print("Concurrent-open pairs per file: two of them that touched it, open at once")
    for path, count in ranked(concurrent(pulls), args.top):
        print(f"{count:6}  {path}")
    print()

    log = home / "merge.log" if home else None
    if not log or not log.is_file():
        print(f"Rebases that dropped lines per file: no merge.log in {home}")
        return
    repo = gh("repo", "view", "--json", "url")["url"]
    rebases, lines = drops(
        log.read_text(encoding="utf-8", errors="replace"), repo, args.since, args.until
    )
    print(
        "Rebases that dropped lines per file (merge.log, once a pull request and head), "
        "and the lines dropped"
    )
    print(f"{'drops':>6}  {'lines':>5}  file")
    order = sorted(rebases, key=lambda path: (-rebases[path], -lines[path], path))
    for path in order[: args.top]:
        print(f"{rebases[path]:6}  {lines[path]:5}  {path}")


if __name__ == "__main__":
    main()
