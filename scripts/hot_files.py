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
   The table also counts the rebases that changed the patch. Those are the `Rebase: patch
   changed in <files>, before <sha>, head <sha>` lines of the home's briefs. The script counts
   each one once for each head, for a brief whose pull request is in table 1. Their list of
   files is free text ("a.md and b.md", "12 feature files"). The script counts a word of it
   when the word is a path of that pull request, or a name that only one of its paths ends
   with. It names the other words on stderr.

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
CHANGED = re.compile(r"^Rebase: patch changed in (.+), before [0-9a-f]+, head ([0-9a-f]+)$", re.M)
PULL = re.compile(r"(https://\S+?)/pull/(\d+)")


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


def changed(briefs, repo, files):
    """The rebases that changed a pull request's patch, counted for each file. `files` maps each
    pull request's number to the paths it touched. The list of files on a brief's `Rebase:` line is
    free text, so the script counts a word only when it is a path of that pull request, or a name
    that only one of its paths ends with. It names the other words on stderr."""
    heads = set()
    counted = Counter()
    for brief in briefs:
        text = brief.read_text(encoding="utf-8", errors="replace")
        pulls = [int(number) for url, number in PULL.findall(text) if url == repo]
        if not pulls or pulls[-1] not in files:
            continue
        touched = files[pulls[-1]]
        for paths, head in CHANGED.findall(text):
            if head in heads:
                continue
            heads.add(head)
            found, unread = set(), []
            for word in paths.split():
                ends = [path for path in touched if path.endswith(f"/{word}")]
                if word in touched:
                    found.add(word)
                elif len(ends) == 1:
                    found.add(ends[0])
                elif word != "and":
                    unread.append(word)
            counted.update(found)
            if unread:
                print(
                    f"unread: {brief.name} at {head[:12]} names {' '.join(unread)}, "
                    f"no path of #{pulls[-1]}, so it is not counted",
                    file=sys.stderr,
                )
    return counted


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
    files = {pull["number"]: {one["path"] for one in pull["files"]} for pull in pulls}
    patched = changed(sorted((home / "tasks").glob("*.md")), repo, files)
    print(
        "Rebases that dropped lines per file (merge.log, once a pull request and head), "
        "the lines dropped, and the rebases that changed the patch (the briefs of table 1)"
    )
    print(f"{'drops':>6}  {'lines':>5}  {'changed':>7}  file")
    order = sorted(
        set(rebases) | set(patched),
        key=lambda path: (-rebases[path], -patched[path], -lines[path], path),
    )
    for path in order[: args.top]:
        print(f"{rebases[path]:6}  {lines[path]:5}  {patched[path]:7}  {path}")


if __name__ == "__main__":
    main()
