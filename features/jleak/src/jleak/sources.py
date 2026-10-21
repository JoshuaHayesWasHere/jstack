"""Where outbound text comes from: each function gives the `Text`s of one way out.

    tree      every tracked file of a repo, and each file's own name
    files     the files named, with `-` for what is piped in
    pushed    what a `git push` is about to send, as git tells a `pre-push` hook
    command   a shell command an agent is about to run

A `git push` sends a ref's name and every commit the destination does not have yet, so
`pushed` gives the name, and for each such commit its message, the lines it adds and the name
of each file it creates. What the destination has is asked of the destination, by its URL:
the checkout's own record of a remote says what some remote had, under a name that may point
elsewhere by now. A line that was already there, or that a commit takes out, is not sent
anew and is not given, and a merge gives only what the merge itself adds.

`command` reads a command as the shell would: joined over a backslash at a line's end, cut
into words with their quotes taken off, and into simple commands at `;`, `&&`, `|` and a new
line. A simple command that runs `gh pr create`, `edit`, `comment` or `review` gives each
of its words, since a title or a body can be any of them, and its body file. One that runs
`git ... push` gives a finding when it would skip the `pre-push` hook. Nothing else in the
command is read: a `cd`, a `grep`, a commit's message. A command inside a quoted string
(`sh -c "..."`) is not seen.
"""

import os
import re
import shlex
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path

from jleak import Finding, Text

VERBS = {"create", "edit", "comment", "review"}
ENDS = set(";|&()\n")
WRAPPERS = {"env", "command", "exec", "time", "nohup", "sudo", "builtin"}
ASSIGNED = re.compile(r"[A-Za-z_]\w*=")
TAKES_A_VALUE = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
CONTINUED = re.compile(r"\\\n[ \t]*")
HUNK = re.compile(r"@@ -[0-9,]+ \+([0-9]+)")
NO_COMMIT = re.compile(r"0+")
DIFF = (
    "--unified=0",
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--diff-merges=remerge",
    "--src-prefix=a/",
    "--dst-prefix=b/",
)


class Unreadable(Exception):
    """Text that is on its way out could not be read, so it cannot be checked."""


def git(*args: str, cwd: Path | None = None, given: str = "") -> str:
    done = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=cwd,
        input=given.encode(),
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        said = done.stderr.decode(errors="replace").strip().splitlines()
        raise Unreadable(f"git {args[0]}: {said[-1] if said else done.returncode}")
    return done.stdout.decode(errors="replace")


def _read(path: Path) -> str | None:
    """A file's text, or None for one that is not text."""
    try:
        data = path.read_bytes()
    except OSError:
        raise Unreadable(f"{path} could not be read") from None
    return None if b"\0" in data else data.decode(errors="replace")


def tree(top: Path) -> Iterator[Text]:
    root = Path(git("rev-parse", "--show-toplevel", cwd=top).strip())
    for name in sorted(filter(None, git("ls-files", "-z", cwd=root).split("\0"))):
        path = root / name
        text = None if path.is_symlink() or not path.is_file() else _read(path)
        lines = Text.of(name, text or "").lines
        yield Text(name, ((0, name), *lines))


def files(names: Iterable[str], piped: str, field: str) -> Iterator[Text]:
    for name in names:
        if name == "-":
            yield Text.of(field, piped)
        else:
            yield Text.of(name, _read(Path(name)) or "")


def _added(commit: str, diff: str) -> Iterator[Text]:
    """The lines a commit's diff adds, a Text for each file, and before it the file's own
    name at line 0 when the commit creates the file or moves one there."""
    name, lines, new, head, at = "", [], False, True, 0

    def ended() -> Iterator[Text]:
        if name and (lines or new):
            yield Text(f"commit {commit} {name}", (*(((0, name),) if new else ()), *lines))

    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            yield from ended()
            sides = line.removeprefix("diff --git ")
            half = len(sides) // 2
            same = sides[2:half] == sides[half + 3 :] and not sides.startswith('"')
            name, lines, new, head = sides[half + 3 :] if same else "", [], False, True
        elif head and line.startswith(("rename to ", "copy to ")):
            name, new = line.split(" to ", 1)[1], True
        elif head and line.startswith("new file mode"):
            new = True
        elif head and line.startswith(("+++ b/", '+++ "b/')):
            name = line[4:].rstrip("\t").strip('"').removeprefix("b/")
        elif line.startswith("@@"):
            head = False
            at = int(found[1]) if (found := HUNK.match(line)) else 0
        elif not head and line.startswith("+"):
            if not name:
                raise Unreadable(f"commit {commit} adds lines to a file git does not name")
            lines.append((at, line[1:]))
            at += 1
    yield from ended()


def pushed(refs: Iterable[str], url: str) -> Iterator[Text]:
    """`refs` is what git writes to a `pre-push` hook: a line
    `<local ref> <local commit> <remote ref> <remote commit>` for each ref. `url` is the
    hook's second argument, where the push goes. A commit is left out only when it is
    reachable from a commit that `git ls-remote` of that URL lists and this checkout holds."""
    refs = [ref.split() for ref in refs if ref.strip()]
    if all(NO_COMMIT.fullmatch(local) for _, local, _, _ in refs):
        return
    listed = {line.split()[0] for line in git("ls-remote", url).splitlines() if line.strip()}
    there = git("cat-file", "--batch-check", given="".join(f"{each}\n" for each in sorted(listed)))
    has = [line.split()[0] for line in there.splitlines() if not line.endswith(" missing")]
    for _, local, remote_ref, _ in refs:
        if NO_COMMIT.fullmatch(local):
            continue
        kind, _, name = remote_ref.removeprefix("refs/").partition("/")
        yield Text.of("branch" if kind == "heads" else "ref", name)
        asked = "".join(f"{each}\n" for each in (local, *(f"^{commit}" for commit in has)))
        for commit in git("rev-list", "--reverse", "--stdin", given=asked).split():
            short = commit[:7]
            yield Text.of(f"commit {short} message", git("show", "-s", "--format=%B", commit))
            yield from _added(short, git("show", "--format=", *DIFF, commit))


def _simple(typed: str) -> list[tuple[list[str], bool]]:
    """The simple commands of a shell command, each as its words and whether it reads a
    here-document. One that does takes every word after it too, since the document's lines
    are its input. Raises ValueError for a command whose quotes do not close."""
    lexer = shlex.shlex(CONTINUED.sub(" ", typed), posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace, lexer.whitespace_split, lexer.commenters = " \t\r", True, ""
    found, words, here = [], [], False
    for word in lexer:
        if not here and word and set(word) <= ENDS:
            found.append((words, here))
            words = []
        else:
            here = here or word.startswith("<<")
            words.append(word)
    return [(words, here) for words, here in (*found, (words, here)) if words]


def _run(words: list[str]) -> list[str]:
    """The words from the program on: without the assignments and the wrappers in front."""
    at = 0
    while at < len(words) and (ASSIGNED.match(words[at]) or words[at] in WRAPPERS):
        at += 1
    return words[at:]


def _push_rules(words: list[str]) -> Iterator[str]:
    """The rules a `git ... push` breaks: the names of what would skip the `pre-push` hook."""
    at, set_here = 1, []
    while at < len(words) and words[at].startswith("-"):
        if words[at] in TAKES_A_VALUE:
            set_here += words[at + 1 : at + 2] if words[at] == "-c" else []
            at += 1
        at += 1
    if words[at : at + 1] != ["push"]:
        return
    if "--no-verify" in words[at:]:
        yield "push-no-verify"
    if any(each.lower().startswith("core.hookspath") for each in set_here):
        yield "push-hooks-path"


def _sent(words: list[str], here: bool, cwd: Path) -> Iterator[Text]:
    """The words of a `gh pr` command that writes, and its body file."""
    named, kept, skip = [], [], False
    for word in words:
        if skip:
            named.append(word)
            skip = False
        elif word in ("-F", "--body-file"):
            skip = True
        elif word.startswith("--body-file="):
            named.append(word.partition("=")[2])
        elif word.startswith("-F") and not word.startswith("-F="):
            named.append(word[2:])
        else:
            kept.append(word)
    lines, at = [], 1
    for word in kept:
        lines += [(at + more, part) for more, part in enumerate(word.split("\n"))]
        at += word.count("\n")
    yield Text("command", tuple(lines))
    for name in named:
        if name == "-" and here:
            continue
        if name == "-":
            raise Unreadable("the body is piped in to the command, where it cannot be read")
        try:
            body = (cwd / os.path.expandvars(os.path.expanduser(name))).read_text(errors="replace")
        except OSError:
            raise Unreadable("the body file of the command could not be read") from None
        yield Text.of("body file", body)


def command(typed: str, cwd: Path) -> tuple[list[Finding], list[Text]]:
    """What a command breaks by itself, and the text it sends to a pull request. A command
    that cannot be cut into words is given whole when it names `gh` and `pr`, and is a
    finding when it names a push and a way around the hook."""
    try:
        simple = _simple(typed)
    except ValueError:
        low = typed.lower()
        around = "push" in low and ("--no-verify" in low or "hookspath" in low)
        whole = re.search(r"\bgh(-axi)?\b", typed) and re.search(r"\bpr\b", typed)
        return (
            [Finding("command", 1, "push-no-verify")] if around else [],
            [Text.of("command", typed)] if whole else [],
        )
    broken, sent = [], []
    for words, here in simple:
        words = _run(words)
        program = Path(words[0]).name if words else ""
        if program == "cd" and len(words) > 1:
            cwd = cwd / os.path.expandvars(os.path.expanduser(words[1]))
        elif program == "git":
            broken += [Finding("command", 1, rule) for rule in _push_rules(words)]
        elif program in ("gh", "gh-axi"):
            verbs = zip(words, words[1:], strict=False)
            if any(one == "pr" and verb in VERBS for one, verb in verbs):
                sent += _sent(words, here, cwd)
    return broken, sent
