"""One sentence per line, for new prose: `prose_lint.py <base>`.

It reads what a pull request adds or changes with `git diff --unified=0 --find-renames
<base>...HEAD`, in the Markdown files of `docs/`, `skills/`, `playbooks/` and `templates/`,
and fails on each added line that holds more than one sentence. It prints one fault a line,
`<file>:<line>: ...: <the line>`, and exits 1. A line the diff does not add is never judged,
so old prose stays as it is until a pull request touches it: a file moved whole adds no
line, and a moved file adds only the lines that changed.

A line is judged in its place in the file at HEAD, read whole, so it knows what the line is
in. These are not prose and are never judged: a line in a code fence, in the front matter, in
an HTML comment, of a table, a heading, and a field (`Key: value`, as a brief's `Task:` or
`Done when:`) with the list items and indented lines under it up to a blank line.

`sentences` decides what a sentence is, and nothing else does: a `.`, `!` or `?`, with any
closing quote, bracket or emphasis after it, then a space and a word that starts with a
capital, a backtick, a quote or a bracket. A `code` span, a link's address, a decimal, a path
and an abbreviation such as "e.g." end nothing.

The base is the one `make check-fast` hands `scripts/select_tests.py`: `origin/main` on a
desk, and `HEAD^1` in a pull request's CI, the tip of main in GitHub's merge commit. It needs
only the standard library, so it runs before `uv sync`.
"""

import re
import subprocess
import sys

FOLDERS = ("docs/", "skills/", "playbooks/", "templates/")
ABBREVIATIONS = {"e.g", "i.e", "etc", "vs", "cf", "approx", "incl", "no", "mr", "mrs", "ms", "dr"}
CODE = re.compile(r"(`+).+?\1")
LINK = re.compile(r"\]\([^)]*\)")
END = re.compile(r"[.!?]+[\"')\]*_]*\s+(?=[A-Z`\"'(\[*_])")
WORD_BEFORE = re.compile(r"(\S+?)[.!?]+[\"')\]*_]*$")
FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^\s{0,3}#{1,6}(\s|$)")
TABLE = re.compile(r"^\s*\|")
FIELD = re.compile(r"^[A-Z][\w-]*(?: [\w-]+){0,2}:(?:\s|$)")
UNDER_A_FIELD = re.compile(r"^(\s+\S|\s*[-*+] |\s*\d+\. )")
LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def sentences(line):
    """The sentences of one line of prose, in order, as they are written."""
    text = LINK.sub(lambda found: "]" + "x" * (len(found[0]) - 1), line)
    text = CODE.sub(lambda found: "`" + "x" * (len(found[0]) - 1), text)
    found, start = [], 0
    for end in END.finditer(text):
        before = WORD_BEFORE.search(text, start, end.start() + len(end[0].rstrip()))
        word = before[1].lstrip("(\"'*_`").lower() if before else ""
        if word in ABBREVIATIONS or len(word) == 1 and word.isalpha():
            continue
        found.append(line[start : end.start() + len(end[0].rstrip())].strip())
        start = end.end()
    rest = line[start:].strip()
    return [*found, rest] if rest else found


def prose(lines):
    """For each line of a Markdown file, whether it is prose that `sentences` judges."""
    judged, fence, front, comment, field = [], None, False, False, False
    for at, line in enumerate(lines):
        opened = FENCE.match(line)
        if fence:
            judged.append(False)
            if opened and opened[1] == fence:
                fence = None
            continue
        if opened:
            fence = opened[1]
            judged.append(False)
            continue
        if at == 0 and line.strip() == "---":
            front = True
            judged.append(False)
            continue
        if front:
            front = line.strip() != "---"
            judged.append(False)
            continue
        if comment or line.lstrip().startswith("<!--"):
            comment = "-->" not in line
            judged.append(False)
            continue
        if not line.strip():
            field = False
            judged.append(False)
            continue
        if FIELD.match(line):
            field = True
            judged.append(False)
            continue
        if field and UNDER_A_FIELD.match(line):
            judged.append(False)
            continue
        field = False
        judged.append(not (HEADING.match(line) or TABLE.match(line)))
    return judged


def added(diff):
    """Each file of a `--unified=0` diff, with the numbers of the lines it adds, at HEAD."""
    found, path = {}, None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif path and (hunk := HUNK.match(line)):
            first, count = int(hunk[1]), int(hunk[2] or 1)
            found.setdefault(path, []).extend(range(first, first + count))
    return found


def git(*args):
    ran = subprocess.run(["git", *args], capture_output=True, text=True)
    if ran.returncode:
        sys.exit(f"prose_lint.py: git {args[0]} failed: {ran.stderr.strip()}")
    return ran.stdout


def faults(base):
    """Each added prose line of more than one sentence, as `(path, number, line)`."""
    diff = git("diff", "--unified=0", "--find-renames", "--no-ext-diff", f"{base}...HEAD", "--")
    found = []
    for path, numbers in added(diff).items():
        if not path.startswith(FOLDERS) or not path.endswith(".md"):
            continue
        lines = git("show", f"HEAD:{path}").splitlines()
        judged = prose(lines)
        for number in numbers:
            line = lines[number - 1]
            if judged[number - 1] and len(sentences(LIST_MARK.sub("", line))) > 1:
                found.append((path, number, line))
    return found


def main(argv):
    if len(argv) != 1:
        sys.exit("usage: prose_lint.py <base>")
    found = faults(argv[0])
    for path, number, line in found:
        print(f"{path}:{number}: more than one sentence, break it at sentence ends: {line}")
    if found:
        print(f"prose_lint.py: {len(found)} new prose lines hold more than one sentence: one each")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
