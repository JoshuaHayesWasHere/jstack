"""No swept file holds a plain comment: a new one fails here, with its file and line.

A Python file is read with `tokenize`, so a `#` in a string is no comment, and a shell file
character by character, so a `#` in quotes is none either. What a tool reads as an instruction
is let through: a shebang, `# type:` and `# pragma`. A `# noqa` is not: what it silences is
written so that ruff has nothing to say.
"""

import io
import tokenize
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SWEPT = (
    "src/**/*.py",
    "src/**/*.sh",
    "hooks/*.sh",
    "scripts/*.sh",
    "install.sh",
    "tests/*.py",
)
READ_BY_A_TOOL = ("# type:", "# pragma")


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


def plain_comments(path, root=REPO):
    read = python_comments if path.suffix == ".py" else shell_comments
    return [
        f"{path.relative_to(root).as_posix()}:{at}: {comment}"
        for at, comment in read(path.read_text())
        if not comment.startswith(READ_BY_A_TOOL) and not (at == 1 and comment.startswith("#!"))
    ]


def test_the_sweep_reads_every_package_the_scripts_and_the_tests():
    files = swept()
    assert {name.split("/")[1] for name in files if name.startswith("src/")} == {
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
    assert {"install.sh", "hooks/home-start.sh", "hooks/limits.sh", "hooks/skill-tips.sh"} <= set(
        files
    )
    assert {"src/jgauge/room.sh", "tests/conftest.py", "tests/test_no_comments.py"} <= set(files)


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
    ],
)
def test_what_a_tool_reads_and_a_hash_that_opens_no_comment_pass(tmp_path, name, text):
    (tmp_path / name).write_text(text)
    assert plain_comments(tmp_path / name, tmp_path) == []
