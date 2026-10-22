"""Where outbound text comes from: each function gives the `Text`s of one way that text leaves
this machine.

    tree      every tracked file of a repo, and each file's own name
    files     the files named, with `-` for what is piped in
    pushed    what a `git push` is about to send, as git tells a `pre-push` hook
    command   a shell command an agent is about to run

A `git push` sends a ref's name and every commit the destination does not have yet, so `pushed`
gives the ref's name. For each such commit, `pushed` also gives the commit's message, the lines the
commit adds and the name of each file the commit creates. `pushed` asks the destination itself, by
its URL, what it has. It does not trust the checkout's own record of a remote. That record says only
what a remote had when the checkout last fetched, and the remote's name may now point to another
URL. The push does not send again a line the destination already has, or a line that a commit
removes, so `pushed` gives neither. For a merge, `pushed` gives only what the merge adds.

`command` reads a command as the shell would. It joins a line that ends in a backslash to the next.
It cuts the command into words, takes their quotes off, and splits it into simple commands at `;`,
`&&`, `|` and a new line. For a simple command that runs `gh pr create`, `edit`, `comment` or
`review`, it gives each of that command's words and the command's body file. It gives every word
because a title or a body can be any of them. For one that runs `git ... push`, it gives a finding
when the push would skip the `pre-push` hook. It reads nothing else in the command: not a `cd`, a
`grep` or a commit's message. It does not see a command inside a quoted string (`sh -c "..."`).
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
    """jleak could not read text that a push or a command is about to send, so it cannot check
    that text."""


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
    """The lines a commit's diff adds, as one Text for each file. When the commit creates
    a file, or renames or copies a file to that name, the Text has the file's own name at line
    0, before the lines."""
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
    hook's second argument, where the push goes. The function leaves a commit out only when
    the commit is reachable from a commit that this checkout holds and that `git ls-remote`
    lists for that URL."""
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
    """The simple commands of a shell command. Each is a pair: the simple command's words, and a
    flag that says whether the simple command reads a here-document. A simple command that reads a
    here-document also gets every word after the `<<`, since the document's lines are that command's
    input. Raises ValueError for a command whose quotes do not close."""
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
    """The program's name and the words after it, without the assignments and wrappers in
    front of the program."""
    at = 0
    while at < len(words) and (ASSIGNED.match(words[at]) or words[at] in WRAPPERS):
        at += 1
    return words[at:]


def _git_verb(words: list[str]) -> tuple[int, list[str]]:
    """Where the verb of a `git ...` command is, past git's own options, and the settings that
    its `-c` options give."""
    at, set_here = 1, []
    while at < len(words) and words[at].startswith("-"):
        if words[at] in TAKES_A_VALUE:
            set_here += words[at + 1 : at + 2] if words[at] == "-c" else []
            at += 1
        at += 1
    return at, set_here


def _push_rules(words: list[str]) -> Iterator[str]:
    """The rules a `git ... push` breaks: the names of the flags and settings in it that would
    skip the `pre-push` hook."""
    at, set_here = _git_verb(words)
    if words[at : at + 1] != ["push"]:
        return
    if "--no-verify" in words[at:]:
        yield "push-no-verify"
    if any(each.lower().startswith("core.hookspath") for each in set_here):
        yield "push-hooks-path"


def _sent(words: list[str], here: bool, cwd: Path) -> Iterator[Text]:
    """The words of a `gh pr` command that writes to a pull request, and the command's body
    file."""
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
    """The findings that come from a command's own words, such as a push that skips the hook,
    and the text the command sends to a pull request. When the function cannot cut a command
    into words, it gives the whole command as text if the command names `gh` and `pr`. It gives
    a finding if the command names a push and a way around the hook."""
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


MESSAGE_VERBS = {"create", "edit", "merge"}
WRITES_A_MESSAGE = re.compile(r"\bgit\b.*\bcommit\b|\bgh(-axi)?\b.*\bpr\b", re.S)


def _file_flags(words: list[str]) -> tuple[str, str] | None:
    """The flags that name a message file, for a simple command that writes a commit's message
    or a pull request's text, and None for any other simple command."""
    program = Path(words[0]).name if words else ""
    if program == "git":
        at, _ = _git_verb(words)
        return ("-F", "--file") if words[at : at + 1] == ["commit"] else None
    if program in ("gh", "gh-axi"):
        verbs = zip(words, words[1:], strict=False)
        if any(one == "pr" and verb in MESSAGE_VERBS for one, verb in verbs):
            return ("-F", "--body-file")
    return None


def _lines(words: list[str]) -> tuple[tuple[int, str], ...]:
    """The lines of a simple command's words, numbered as lines of the command. A word before a
    here-document is a line of its own, with a line for each new line in the word, and with the
    value of an `--option=value` word as one more line. A here-document's words are joined back
    into the lines they came from."""
    lines, at, here, joined = [], 1, False, []
    for word in words:
        if not here:
            lines += [(at + more, part) for more, part in enumerate(word.split("\n"))]
            if word.startswith("-") and "=" in word:
                lines.append((at, word.partition("=")[2]))
            at += word.count("\n")
            here = word.startswith("<<")
            continue
        first, *rest = word.split("\n")
        joined += [first] if first else []
        for part in rest:
            lines.append((at, " ".join(joined)))
            at, joined = at + 1, [part] if part else []
    if joined:
        lines.append((at, " ".join(joined)))
    return tuple(lines)


def _parts(words: list[str]) -> list[list[str]]:
    """The simple commands inside the words of one that reads a here-document, which `_simple`
    does not split: the words between two words that end a command."""
    found, part = [], []
    for word in words:
        if word and not word.strip("<>" + "".join(ENDS)) and set(word) & ENDS:
            found.append(part)
            part = []
        else:
            part.append(word)
    return [each for each in (*found, part) if each]


def _file(name: str, cwd: Path) -> Text | None:
    """A message file's text, or None for one that is not there yet, such as a file that the same
    command writes first."""
    try:
        text = (cwd / os.path.expandvars(os.path.expanduser(name))).read_text(errors="replace")
    except OSError:
        return None
    return Text.of("message file", text)


def messages(typed: str, cwd: Path) -> list[Text]:
    """The text that a command writes into a commit's message or a pull request: the lines of
    each simple command that runs `git ... commit` or `gh pr create`, `edit` or `merge`, and the
    message file it names (`-F`, `--file`, `--body-file`). A simple command that reads a
    here-document gives all its lines when a commit or a pull request is among the commands
    inside it, so a message that `cat` writes to a file before `git commit -F` reads it is read.
    A file that is not there is not read: git's `commit-msg` hook reads the message then.
    When the function cannot cut a command into words, it gives the whole command, as long as
    the command may write a commit or a pull request."""
    try:
        simple = _simple(typed)
    except ValueError:
        return [Text.of("command", typed)] if WRITES_A_MESSAGE.search(typed) else []
    found = []
    for words, here in simple:
        words = _run(words)
        program = Path(words[0]).name if words else ""
        if program == "cd" and len(words) > 1:
            cwd = cwd / os.path.expandvars(os.path.expanduser(words[1]))
        writers = [
            (part, flags)
            for part in (_parts(words) if here else [words])
            if (flags := _file_flags(_run(part)))
        ]
        if not writers:
            continue
        found.append(Text("command", _lines(words)))
        for part, (short, long) in writers:
            for at, word in enumerate(part):
                if word in (short, long):
                    name = part[at + 1] if at + 1 < len(part) else "-"
                elif word.startswith(f"{long}="):
                    name = word.partition("=")[2]
                elif word.startswith(short) and len(word) > len(short) and word[2] != "=":
                    name = word[len(short) :]
                else:
                    continue
                text = _file(name, cwd) if name != "-" else None
                found += [text] if text else []
    return found
