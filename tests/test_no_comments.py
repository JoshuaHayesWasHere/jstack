"""No swept file holds a plain comment: a new one fails here, with its file and line.

A Python file is read with `tokenize`, so a `#` in a string is no comment, and a shell file
character by character, so a `#` in quotes is none either. A systemd unit and a list of
jmerge's paths are read line by line: a line that starts with `#` is a comment, and in a unit
one that starts with `;` too. What a tool reads as an instruction
is let through: a shebang, `# type:` and `# pragma`. A `# noqa` is not: what it silences is
written so that ruff has nothing to say.

A script, and the `<script>` and `<style>` of a page, is read for `/* */` and `//` past its
strings, its regular expressions and a `://`. A comment there that holds an `https://` link
is let through: it names a fact of the platform, with where it is written down.
"""

import io
import re
import tokenize

import pytest

from testing.paths import REPO

SWEPT = (
    "src/**/*.py",
    "src/**/*.sh",
    "src/**/*.js",
    "src/**/*.html",
    "features/*/src/**/*.py",
    "features/*/src/**/*.sh",
    "features/*/src/**/*.js",
    "features/*/src/**/*.html",
    "hooks/*.sh",
    "scripts/*.sh",
    "install.sh",
    "tests/**/*.py",
    "features/*/tests/**/*.py",
    "testing/*.py",
    "conftest.py",
    "templates/*.service",
    "templates/*.timer",
    "templates/*.html",
    "features/*/templates/*.html",
    "src/jmerge/*.txt",
)
READ_BY_A_TOOL = ("# type:", "# pragma")
LINKED = "https://"
EMBEDDED = re.compile(r"<(script|style)\b[^>]*>(.*?)</\1>", re.S | re.I)
WORD = re.compile(r"[\w$]+")
PACKAGE = re.compile(r"(?:features/[^/]+/)?src/([^/]+)/")
AFTER_A_WORD_A_REGEX = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete"}
AFTER_A_MARK_A_REGEX = {"", *"([{,;:=!&|?+-*%<>~^"}


def swept():
    return sorted({path.relative_to(REPO).as_posix() for glob in SWEPT for path in REPO.glob(glob)})


def python_comments(text):
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    return [(token.start[0], token.string) for token in tokens if token.type == tokenize.COMMENT]


def shell_comments(text):
    found, quote, at = [], "", 0
    while at < len(text):
        char = text[at]
        if char == "\\" and quote != "'":
            at += 1
        elif quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and text[at - 1 : at].strip() == "":
            end = text.find("\n", at) % (len(text) + 1)
            found.append((text.count("\n", 0, at) + 1, text[at:end]))
            at = end
        at += 1
    return found


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


def comment_end(text, at):
    closing = "*/" if text[at + 1] == "*" else "\n"
    end = text.find(closing, at + 2)
    return len(text) if end < 0 else end + len(closing.strip())


def script_comments(text):
    found, before, at = [], "", 0
    while at < len(text):
        char, two, word = text[at], text[at : at + 2], WORD.match(text, at)
        if char in "'\"`":
            before, at = char, quoted_end(text, at)
        elif two == "/*" or (two == "//" and text[at - 1 : at] != ":"):
            end = comment_end(text, at)
            found.append((text.count("\n", 0, at) + 1, text[at:end]))
            at = end
        elif char == "/" and (before in AFTER_A_WORD_A_REGEX or before in AFTER_A_MARK_A_REGEX):
            before, at = "/", regex_end(text, at)
        elif word:
            before, at = word[0], word.end()
        else:
            before, at = before if char.isspace() else char, at + 1
    return found


def page_comments(text):
    return [
        (text.count("\n", 0, embedded.start(2)) + at, comment)
        for embedded in EMBEDDED.finditer(text)
        for at, comment in script_comments(embedded[2])
    ]


def line_comments(text, marks=("#",)):
    lines = enumerate(text.splitlines(), 1)
    return [(at, line.strip()) for at, line in lines if line.lstrip().startswith(marks)]


def unit_comments(text):
    return line_comments(text, ("#", ";"))


READERS = {
    ".py": python_comments,
    ".js": script_comments,
    ".html": page_comments,
    ".service": unit_comments,
    ".timer": unit_comments,
    ".txt": line_comments,
}


def plain_comments(path, root=REPO):
    read = READERS.get(path.suffix, shell_comments)
    return [
        f"{path.relative_to(root).as_posix()}:{at}: {comment}"
        for at, comment in read(path.read_text())
        if not comment.startswith(READ_BY_A_TOOL)
        and not (at == 1 and comment.startswith("#!"))
        and not (path.suffix in (".js", ".html") and LINKED in comment)
    ]


def test_the_sweep_reads_every_package_the_scripts_and_the_tests():
    files = swept()
    assert {at.group(1) for name in files if (at := PACKAGE.match(name))} == {
        "jsettings",
        "jbriefs",
        "jbus",
        "jdrift",
        "jinstall",
        "jleak",
        "jmerge",
        "jpack",
        "jgauge",
        "jroles",
    }
    assert {
        "install.sh",
        "hooks/home-start.sh",
        "hooks/limits.sh",
        "features/skill-library/hooks/skill-tips.sh",
    } <= set(files)
    assert {"src/jgauge/room.sh", "testing/jstack_fixtures.py", "tests/test_no_comments.py"} <= set(
        files
    )
    assert "features/show-me-your-work/tests/test_show_me_your_work.py" in files
    assert {
        "templates/jbus.service",
        "templates/jbus.timer",
        "features/grilling/templates/grill-page.html",
        "src/jmerge/protected.txt",
        "src/jmerge/guarded.txt",
        "src/jmerge/ci-paths.txt",
    } <= set(files)


@pytest.mark.parametrize("name", swept())
def test_a_swept_file_holds_no_plain_comment(name):
    assert plain_comments(REPO / name) == []


@pytest.mark.parametrize(
    ("name", "text", "found"),
    [
        ("own_line.py", "x = 1\n# why\ny = 2\n", ["own_line.py:2: # why"]),
        ("trailing.py", "x = 1  # why\n", ["trailing.py:1: # why"]),
        (
            "late_shebang.py",
            "x = 1\n#!/usr/bin/env python\n",
            ["late_shebang.py:2: #!/usr/bin/env python"],
        ),
        ("formatter.py", "x = [1]  # fmt: skip\n", ["formatter.py:1: # fmt: skip"]),
        ("suppressed.py", "f = lambda: 1  # noqa: E731\n", ["suppressed.py:1: # noqa: E731"]),
        ("own_line.sh", "#!/bin/sh\n# why\necho hi\n", ["own_line.sh:2: # why"]),
        ("trailing.sh", "#!/bin/sh\n  LOAD=85 # percent\n", ["trailing.sh:2: # percent"]),
        ("indented.sh", "#!/bin/sh\nrun() {\n\t# why\n}\n", ["indented.sh:3: # why"]),
        ("after_a_quote.sh", '#!/bin/sh\necho "a #1" # why\n', ["after_a_quote.sh:2: # why"]),
        ("panel.js", "/* why */\npanel({});\n", ["panel.js:1: /* why */"]),
        ("trailing.js", "var x = 1; // why\n", ["trailing.js:1: // why"]),
        (
            "block.js",
            "var x = 1;\n  /* why,\n  and why */\n",
            ["block.js:2: /* why,\n  and why */"],
        ),
        ("after_a_string.js", 'say("a"); // why\n', ["after_a_string.js:1: // why"]),
        ("after_a_regex.js", "x.replace(/a/g, b); // why\n", ["after_a_regex.js:1: // why"]),
        ("unclosed.js", "x();\n/* why", ["unclosed.js:2: /* why"]),
        ("unclosed_first.js", "/* why", ["unclosed_first.js:1: /* why"]),
        ("unclosed_second.js", "x/* why", ["unclosed_second.js:1: /* why"]),
        ("unclosed.html", "<script>\n/* why</script>\n", ["unclosed.html:2: /* why"]),
        (
            "quoted.service",
            "[Unit]\nDescription=the homes' state\n# why\n  ; and why\n",
            ["quoted.service:3: # why", "quoted.service:4: ; and why"],
        ),
        ("own_line.timer", "# why\n[Timer]\n", ["own_line.timer:1: # why"]),
        ("list.txt", "secrets/\n  # why\n/dns/\n", ["list.txt:2: # why"]),
        (
            "page.html",
            "<p>it's</p>\n<style>\n  a { b: c; } /* why */\n</style>\n"
            "<script>\n// why\n</script>\n",
            ["page.html:3: /* why */", "page.html:6: // why"],
        ),
    ],
)
def test_a_file_written_with_a_comment_fails_with_its_file_and_line(tmp_path, name, text, found):
    (tmp_path / name).write_text(text)
    assert plain_comments(tmp_path / name, tmp_path) == found


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("shebang.py", "#!/usr/bin/env python\nx = 1\n"),
        ("typed.py", "x: int = 1  # type: ignore[assignment]\n"),
        ("pragma.py", "if x:  # pragma: no cover\n    pass\n"),
        ("in_a_string.py", 'x = "# not a comment"\ny = """\n# nor this\n"""\n'),
        ("shebang.sh", "#!/bin/sh\necho hi\n"),
        ("expansion.sh", '#!/bin/sh\necho "${state#"${state%% *}"}" "$#"\n'),
        ("quoted.sh", "#!/bin/sh\necho \"issue #3\" 'and #4'\nawk '\n  # in awk\n'\n"),
        ("escaped.sh", "#!/bin/sh\necho \\# \\' it\n"),
        ("strings.js", "say(\"// no\", '/* no */', `// no\n/* no */`);\n"),
        ("escaped.js", "say('it\\'s // no', \"a \\\" // no\");\n"),
        ("regex.js", "var a = /\\/\\//, b = /[/]*/g;\n"),
        ("returned.js", "function f(u) { return /^https:\\/\\/x\\//.test(u); }\n"),
        ("divided.js", "var a = b / c / d, e = (f) / 2;\n"),
        ("address.js", "var at = url(http://example.org/x);\n"),
        ("linked.js", "/* Chromium drops a write past 200: https://example.org/spec */\nx();\n"),
        ("css.html", '<style>\n  .a::before { content: "/" / ""; }\n</style>\n'),
        ("prose.html", "<p>a // b, and /* c */ in words</p>\n"),
        ("specifier.service", "[Unit]\nDocumentation=file:%Y/../docs/jbus.md#the-view\n"),
        ("pattern.txt", ".env.*\n/src/a#b.py\n"),
    ],
)
def test_what_a_tool_reads_and_a_hash_that_opens_no_comment_pass(tmp_path, name, text):
    (tmp_path / name).write_text(text)
    assert plain_comments(tmp_path / name, tmp_path) == []
