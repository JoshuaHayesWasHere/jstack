"""No step jstack gives a thread deletes a file or starts a shell inside the shell.

Claude Code asks the user before it runs a command that removes files, even in full access, and
it asks too when an inner `sh -c` or `eval` holds a script it cannot read (2.1.310: "This shell
-c script runs rm and could not be checked"). A thread that runs such a step stops and waits for
Josh. The rule is the user's (2026-10-25: "one script doesn't seem like the fix"): a step a
thread runs holds no `rm`, `rmdir`, `unlink`, `find -delete`, `sh -c` or `eval` in command
position, whatever shape the check takes next. A step that needs to delete or to run a command
in the background calls a jstack command that does it, as `jgauge check` and `jgauge proof` do.

The lint reads every fenced `sh` block of the thread files, `features/**/*.md` but docs, tests,
`evals/evals/` and READMEs, and splits each into commands with a small shell reader: it follows
quotes, `$(...)`, backticks, here-documents, `case` patterns and wrappers such as `setsid`,
`xargs` and `env`, so a word in quotes or a `case` pattern is no command. `ASKS_TODAY` holds the
blocks that ap-blocks-rest moves into commands of their owners, by file and count. It may only
shrink: a file that holds one more fails, and so does a file that holds one fewer until its line
leaves the list. A block that fails is fixed by moving its delete or its background run into a
jstack command, as `jgauge check` does, and never by a comment or a list entry.
"""

import re
import textwrap
from collections import Counter
from pathlib import PurePosixPath

import pytest

from testing.paths import REPO

READ_SET = ("*.md",)
FENCED = re.compile(r"^[ \t]*```(?:sh|bash|shell|zsh)\n(.*?)^[ \t]*```[ \t]*$", re.M | re.S)
DELETES = frozenset({"rm", "rmdir", "unlink"})
SHELLS = frozenset({"sh", "bash", "zsh", "dash"})
KEEP_EXPECTING = frozenset({"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"})
ENDS = frozenset({"fi", "done", "esac"})
WRAPPERS = frozenset(
    {"exec", "command", "builtin", "nohup", "setsid", "env", "nice", "timeout", "xargs"}
    | {"sudo", "time", "stdbuf", "ionice", "flock", "chronic"}
)
TAKES_ONE = {
    "timeout": 1,
    "flock": 1,
}
ARGUED_FLAGS = {
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"},
    "nice": {"-n"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "flock": {"-w", "-E", "--timeout", "--conflict-exit-code"},
    "sudo": {"-u", "-g", "-C", "-D"},
    "stdbuf": {"-i", "-o", "-e"},
    "ionice": {"-c", "-n"},
    "env": {"-u", "-C", "-S"},
}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")
OPERATORS = ("<<<", "<<-", ";;&", "&&", "||", ";;", ";&", "|&", "&>", ">>", ">&", "<&", ">|", "<<")
REDIRECTS = frozenset({"<", ">", ">>", "&>", ">&", "<&", ">|", "<<<"})
ASKS_TODAY = {
    "features/crew/SKILL.md": 1,
    "features/crew/a-conflict.md": 3,
    "features/expert/when-an-expert-starts.md": 1,
    "features/home/skills/handoff/SKILL.md": 2,
    "features/home/skills/home/gates.md": 1,
    "features/home/skills/home/queue-and-its-hourly-audit.md": 1,
    "features/home/skills/home/scoped-homes.md": 1,
    "features/home/skills/home/when-a-home-starts.md": 1,
    "features/home/skills/nohome/SKILL.md": 2,
    "features/pr-review/SKILL.md": 1,
    "features/pr-review/the-review.md": 1,
}


class Reader:
    """Splits a shell script into tokens: `("word", text)` and `("op", text)`, with a newline as
    the op `\\n`. The text of a `$(...)`, `<(...)` or backtick goes to `inner`, read the same
    way, and so does every one inside double quotes. A here-document's body is data and is
    skipped."""

    def __init__(self, text):
        self.text, self.at, self.inner = text, 0, []

    def peek(self, size=1):
        return self.text[self.at : self.at + size]

    def tokens(self, until=""):
        found, word, started, heredocs, redirected = [], [], False, [], False

        def end_word():
            nonlocal word, started, redirected
            if started:
                text = "".join(word)
                if heredocs and heredocs[-1] is None:
                    heredocs[-1] = text
                elif not redirected:
                    found.append(("word", text))
                redirected = False
            word, started = [], False

        while self.at < len(self.text):
            char = self.peek()
            if until and char == until:
                self.at += 1
                break
            if char == "\n":
                end_word()
                self.at += 1
                found.append(("op", "\n"))
                for delimiter in heredocs:
                    self.skip_body(delimiter or "")
                heredocs = []
                continue
            if char in " \t":
                end_word()
                self.at += 1
            elif char == "#" and not started:
                while self.at < len(self.text) and self.peek() != "\n":
                    self.at += 1
            elif char == "\\":
                if self.peek(2) != "\\\n":
                    word.append(self.peek(2)[1:])
                    started = True
                self.at += 2
            elif char == "'":
                close = self.text.find("'", self.at + 1)
                close = len(self.text) if close < 0 else close
                word.append(self.text[self.at + 1 : close])
                started, self.at = True, close + 1
            elif char == '"':
                self.at += 1
                word.append(self.quoted())
                started = True
            elif char == "`":
                self.at += 1
                self.nested("`")
                word.append("`...`")
                started = True
            elif char == "$":
                word.append(self.dollar())
                started = True
            elif char in "<>" and self.peek(2) in ("<(", ">("):
                self.at += 2
                self.nested(")")
                word.append("<(...)")
                started = True
            elif char in ";&|()<>":
                if started and char in "<>" and "".join(word).isdigit():
                    word, started = [], False
                end_word()
                op = next((one for one in OPERATORS if self.text.startswith(one, self.at)), char)
                self.at += len(op)
                if op in ("<<", "<<-"):
                    heredocs.append(None)
                elif op in REDIRECTS:
                    redirected = True
                else:
                    found.append(("op", op))
            else:
                word.append(char)
                started = True
                self.at += 1
        end_word()
        return found

    def nested(self, until):
        self.inner.append(self.tokens(until))

    def quoted(self):
        kept = []
        while self.at < len(self.text) and self.peek() != '"':
            if self.peek() == "\\":
                kept.append(self.peek(2)[1:])
                self.at += 2
            elif self.peek() == "`":
                self.at += 1
                self.nested("`")
                kept.append("`...`")
            elif self.peek() == "$":
                kept.append(self.dollar())
            else:
                kept.append(self.peek())
                self.at += 1
        self.at += 1
        return "".join(kept)

    def dollar(self):
        if self.peek(3) == "$((":
            self.skip_paired("((", "))")
            return "$((...))"
        if self.peek(2) == "$(":
            self.at += 2
            self.nested(")")
            return "$(...)"
        if self.peek(2) == "${":
            self.skip_paired("{", "}")
            return "${...}"
        self.at += 1
        return "$"

    def skip_paired(self, opening, closing):
        depth = 0
        while self.at < len(self.text):
            if self.text.startswith(opening, self.at) or self.peek() == opening[0]:
                depth += 1
            elif self.peek() == closing[0]:
                depth -= 1
                if depth <= 0:
                    self.at += len(closing) if self.text.startswith(closing, self.at) else 1
                    return
            self.at += 1

    def skip_body(self, delimiter):
        while self.at < len(self.text):
            end = self.text.find("\n", self.at)
            end = len(self.text) if end < 0 else end
            line = self.text[self.at : end]
            self.at = end + 1
            if line.strip() == delimiter:
                return


def commands(tokens):
    """The simple commands of a token list, each the words from its command word to the next
    separator. `case` patterns, the words of a `for` and assignments before a command are not
    commands."""
    found, current, expecting, mode, cases = [], None, True, "", []
    for kind, text in tokens:
        if kind == "op":
            if current:
                found.append(current)
            current = None
            if text == ")" and cases and cases[-1] == "pattern":
                cases[-1] = "body"
            elif text in (";;", ";&", ";;&") and cases:
                cases[-1] = "pattern"
            expecting = True
            continue
        if mode == "case-subject":
            mode = "case-in"
        elif mode == "case-in":
            mode = ""
            cases.append("pattern")
        elif mode == "for":
            mode = "" if text == "do" else "for"
        elif cases and cases[-1] == "pattern":
            if text == "esac":
                cases.pop()
                expecting = False
        elif current is not None:
            current.append(text)
        elif not expecting:
            continue
        elif text in KEEP_EXPECTING or ASSIGNMENT.match(text):
            continue
        elif text == "case":
            mode = "case-subject"
        elif text == "for":
            mode = "for"
        elif text in ENDS:
            if text == "esac" and cases:
                cases.pop()
            expecting = False
        else:
            current = [text]
    if current:
        found.append(current)
    return found


def unwrapped(words):
    """The command a wrapper runs: `setsid sh -c x` runs `sh -c x`, `xargs rm` runs `rm`."""
    while words and PurePosixPath(words[0]).name in WRAPPERS:
        name, words = PurePosixPath(words[0]).name, words[1:]
        if name == "flock" and any(one in ("-c", "--command") for one in words):
            return ["sh", "-c"]
        while words and (words[0].startswith("-") or (name == "env" and "=" in words[0])):
            words = words[2:] if words[0] in ARGUED_FLAGS.get(name, ()) else words[1:]
        words = words[TAKES_ONE.get(name, 0) :]
    return words


def why(words):
    """Why a command asks, or an empty string."""
    words = unwrapped(words)
    if not words:
        return ""
    name = PurePosixPath(words[0]).name
    if name in DELETES:
        return f"{name} deletes"
    if name == "eval":
        return "eval runs a script the check cannot read"
    if name in SHELLS:
        for one in words[1:]:
            if not one.startswith("-") or one == "--":
                break
            if one.startswith("-") and not one.startswith("--") and "c" in one:
                return f"{name} {one} runs a script the check cannot read"
    if name == "find":
        if "-delete" in words:
            return "find -delete deletes"
        for at, one in enumerate(words):
            if one in ("-exec", "-execdir", "-ok", "-okdir"):
                inner = why(words[at + 1 :])
                if inner:
                    return f"find {one} {inner}"
    return ""


def reasons(script):
    """Each reason a script asks, for every command in it and in its substitutions."""
    reader = Reader(script)
    lists = [reader.tokens()]
    found = []
    while lists or reader.inner:
        lists.extend(reader.inner)
        reader.inner = []
        for words in commands(lists.pop()):
            said = why(words)
            if said:
                found.append(said)
    return found


def thread_files():
    for path in sorted(REPO.glob("features/**/*.md")):
        relative = path.relative_to(REPO).as_posix()
        parts = set(relative.split("/"))
        if parts & {"docs", "tests"} or "evals/evals/" in relative or path.name == "README.md":
            continue
        yield relative, path


def blocks_that_ask():
    """Each fenced block of a thread file that asks, as `(file, line, reasons)`."""
    found = []
    for relative, path in thread_files():
        text = path.read_text()
        for match in FENCED.finditer(text):
            said = reasons(textwrap.dedent(match.group(1)))
            if said:
                found.append((relative, text.count("\n", 0, match.start()) + 1, said))
    return found


def test_no_block_a_thread_runs_deletes_or_starts_an_inner_shell():
    found = blocks_that_ask()
    counts = Counter(relative for relative, _, _ in found)
    new = [one for one in found if counts[one[0]] > ASKS_TODAY.get(one[0], 0)]
    assert new == []
    fixed = {
        relative: (allowed, counts[relative])
        for relative, allowed in ASKS_TODAY.items()
        if counts[relative] < allowed
    }
    assert fixed == {}


@pytest.mark.parametrize(
    ("script", "said"),
    [
        ('rm -f "$x"', ["rm deletes"]),
        ("if true; then rmdir d; fi", ["rmdir deletes"]),
        ("x=$(unlink f)", ["unlink deletes"]),
        ('echo "$(rm x)"', ["rm deletes"]),
        ("echo `rm x`", ["rm deletes"]),
        ("find . -name '*.tmp' -delete", ["find -delete deletes"]),
        ("find . -exec rm {} +", ["find -exec rm deletes"]),
        ("ls | xargs -n 1 rm", ["rm deletes"]),
        ("setsid sh -c 'exec sleep 1' &", ["sh -c runs a script the check cannot read"]),
        ("bash -lc true", ["bash -lc runs a script the check cannot read"]),
        ("env A=1 dash -e -c true", ["dash -c runs a script the check cannot read"]),
        ('eval "$cmd"', ["eval runs a script the check cannot read"]),
        ("flock -n lock -c true", ["sh -c runs a script the check cannot read"]),
        ("X=1 /bin/rm x", ["rm deletes"]),
        ("echo rm -rf; printf '%s\\n' 'rm x'", []),
        ("docker run --rm image; git rm x", []),
        ("case $k in\nrm | eval) echo one ;;\n*) rm x ;;\nesac", ["rm deletes"]),
        ("for f in rm eval; do echo $f; done", []),
        ("cat << 'END'\nrm -rf /\neval x\nEND\necho ok", []),
        ("cat << END > f\nrm x\nEND\nrm y", ["rm deletes"]),
        ('sh "$C/run" 2> /dev/null; flock -n lock true', []),
        ("echo $((1 + 2)) ${x#rm} # rm here is a comment", []),
        ("uv run jgauge check --thread x << 'E'\nmake check\nE", []),
    ],
)
def test_the_reader_finds_a_delete_or_an_inner_shell_only_in_command_position(script, said):
    assert reasons(script) == said
