"""The mechanical unslop rules, in comments and docstrings: `comment_lint.py [<file>...]`.

It reads the comments and docstrings of the files it is given and warns on each line that
breaks a rule of `features/writing/skills/unslop/SKILL.md` a pattern can hold: 7 (the AI
vocabulary), 8 (`serves as`, `boasts`), 13 (an em or en dash), 19 (a curly quote), 20 (a
chatbot phrase), 23 (`in order to`, `due to the fact`, `it is important to note`, `it is worth
noting`) and 31 (`utilize`, `leverage`, `facilitate`, `numerous`, `in the event that`,
`commence`, `prior to`, `subsequently`, `whilst`). It prints one warning a hit, `warn
<file>:<line>: rule <n> <name>: <match>`, and always exits 0: a warning fails nothing yet.

A Python file is read with `tokenize` for its comments and with `ast` for the docstrings of
its module, classes and functions, a shell file for its lines that start with `#`, and a
script for its `//` and `/* */` comments past its strings and regular expressions. A shebang
is no comment. Before a rule is matched, text in backticks or in double quotes is blanked: it
is code, output or a quote, and not this repo's prose. "stands as" is no fancy "is" here: the
repo says it for "remains".

With no file named it reads every Python, shell and script file under `features/*/src`,
`features/*/tests`, `scripts/` and `testing/`, and `install.sh`, from the current directory,
a minified `.min.js` left out. With files named it reads only those of the kinds it reads.
`make check-fast` names the files of the diff from its base. It needs only the standard
library, so it runs before `uv sync`.
"""

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

RULES = tuple(
    (number, name, re.compile(pattern, re.I))
    for number, name, pattern in (
        (
            7,
            "AI vocabulary",
            r"\b(additionally|crucial(ly)?|delv(e|es|ed|ing)|enduring|enhanc(e|es|ed|ing|ement)"
            r"|foster(s|ed|ing)?|garner(s|ed|ing)?|interplay|intricate|landscape|pivotal"
            r"|showcas(e|es|ed|ing)|tapestry|testament|underscor(e|es|ed|ing)|vibrant)\b",
        ),
        (8, "a fancy is", r"\b(serves? as|served as|serving as|boasts?|boasted|boasting)\b"),
        (13, "em or en dash", "[—–]"),
        (19, "curly quote", "[‘’“”]"),
        (
            20,
            "chatbot phrase",
            r"\b(i hope this helps|let me know|of course|certainly|smoking gun)\b",
        ),
        (
            23,
            "filler phrase",
            r"\b(in order to|due to the fact|it is important to note|it(?: is|'s) worth noting)\b",
        ),
        (
            31,
            "plain word",
            r"\b(utiliz(e|es|ed|ing)|leverag(e|es|ed|ing)|facilitat(e|es|ed|ing)|numerous"
            r"|in the event that|commenc(e|es|ed|ing)|prior to|subsequently|whilst)\b",
        ),
    )
)
QUOTED = re.compile(r"(`+)[\s\S]*?\1|\"[^\"]*\"")
DELIMITER = re.compile(r"^[rRbBuUfF]*(\"\"\"|'''|\"|')|(\"\"\"|'''|\"|')$")
DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
SCOPE = ("features/*/src", "features/*/tests", "scripts", "testing")
WORD = re.compile(r"[\w$]+")
AFTER_A_WORD_A_REGEX = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete"}
AFTER_A_MARK_A_REGEX = {"", *"([{,;:=!&|?+-*%<>~^"}


def python_blocks(text):
    """Each comment, and each docstring as it is written in the source, of a Python file."""
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    found = [
        (token.start[0], token.string)
        for token in tokens
        if token.type == tokenize.COMMENT and not (token.start[0] == 1 and token.string[:2] == "#!")
    ]
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, DOCUMENTED) and ast.get_docstring(node, clean=False) is not None:
            written = node.body[0].value
            found.append((written.lineno, DELIMITER.sub("", ast.get_source_segment(text, written))))
    return found


def shell_blocks(text):
    """Each line of a shell file that starts with `#`, a shebang left out."""
    return [
        (at, line.strip())
        for at, line in enumerate(text.splitlines(), 1)
        if line.lstrip().startswith("#") and not (at == 1 and line.startswith("#!"))
    ]


def quoted_end(text, at):
    quote, at = text[at], at + 1
    while at < len(text) and text[at] != quote and (quote == "`" or text[at] != "\n"):
        at += 2 if text[at] == "\\" else 1
    return at + 1


def regex_end(text, at):
    within, at = False, at + 1
    while at < len(text) and text[at] != "\n":
        if text[at] == "\\":
            at += 1
        elif text[at] in "[]":
            within = text[at] == "["
        elif text[at] == "/" and not within:
            return at + 1
        at += 1
    return at


def script_blocks(text):
    """Each `//` and `/* */` comment of a script, read past its strings and regular
    expressions, and past a `://`."""
    found, before, at = [], "", 0
    while at < len(text):
        char, two, word = text[at], text[at : at + 2], WORD.match(text, at)
        if char in "'\"`":
            before, at = char, quoted_end(text, at)
        elif two == "/*" or (two == "//" and text[at - 1 : at] != ":"):
            closing = "*/" if two == "/*" else "\n"
            end = text.find(closing, at + 2)
            end = len(text) if end < 0 else end + len(closing.strip())
            found.append((text.count("\n", 0, at) + 1, text[at:end]))
            at = end
        elif char == "/" and (before in AFTER_A_WORD_A_REGEX or before in AFTER_A_MARK_A_REGEX):
            before, at = "/", regex_end(text, at)
        elif word:
            before, at = word[0], word.end()
        else:
            before, at = before if char.isspace() else char, at + 1
    return found


READERS = {".py": python_blocks, ".sh": shell_blocks, ".js": script_blocks}


def reader(path):
    """The function that reads a file's comments, or `None` for a file of no kind it reads."""
    if path.name.endswith(".min.js"):
        return None
    return READERS.get(path.suffix)


def blanked(text):
    """The text with what is in backticks or double quotes taken out, its line breaks kept."""
    return QUOTED.sub(lambda found: " " + "\n" * found[0].count("\n"), text)


def warnings(path):
    """Each hit in a file's comments and docstrings, as `(line, rule, name, match)`."""
    try:
        blocks = reader(path)(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, tokenize.TokenError):
        return []
    found = []
    for first, block in blocks:
        for at, line in enumerate(blanked(block).split("\n"), first):
            for number, name, pattern in RULES:
                found.extend((at, number, name, hit[0]) for hit in pattern.finditer(line))
    return sorted(found, key=lambda hit: hit[:2])


def default_files():
    """Every file the lint reads with no file named, in order."""
    found = {path for folder in SCOPE for path in Path().glob(f"{folder}/**/*") if path.is_file()}
    return sorted(path for path in found | {Path("install.sh")} if reader(path))


def main(argv):
    files = [path for path in map(Path, argv) if reader(path)] if argv else default_files()
    count = 0
    for path in files:
        for at, number, name, match in warnings(path):
            print(f"warn {path.as_posix()}:{at}: rule {number} {name}: {match}")
            count += 1
    if count:
        print(f"comment_lint.py: {count} warnings in comments and docstrings, which fail nothing")


if __name__ == "__main__":
    main(sys.argv[1:])
