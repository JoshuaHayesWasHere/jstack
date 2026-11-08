"""No swept file holds a plain comment. The test fails on a new one and names its file and line.

The swept files, and what passes there, are the `comments` part of `.repo-standard.yml`, and the
repo standard's `comments` guard reads them (features/repo-standard/docs/guards.md): this test runs
it on jstack. The guard reads a Python file with `tokenize`, so a `#` in a string is no comment. It
reads a shell file character by character, so a `#` in quotes is no comment either. It reads a
systemd unit and a list of jmerge's paths line by line: a line that starts with `#` is a comment,
and in a unit so is a line that starts with `;`. jstack lets through what a tool reads as an
instruction: a shebang, `# type:` and `# pragma`. It does not let a `# noqa` through: write the
code so that ruff reports nothing on it instead.

In a script, and in the `<script>` and `<style>` of a page, the guard looks for `/* */` and `//`. It
skips strings, regular expressions and a `://`. jstack lets through a comment there that holds an
`https://` link. Such a comment names a fact of the platform, and the link is the page that
documents that fact.

The cases below run jstack's `comments` part through the guard on files written for them.
"""

import re
from dataclasses import replace

import pytest

from repo_standard import size
from repo_standard.__main__ import main
from repo_standard.config import Config, load
from repo_standard.tree import chosen, tracked
from testing.paths import REPO

COMMENTS = load(REPO).part("comments")
PACKAGE = re.compile(r"features/[^/]+/src/([^/]+)/")


def swept():
    return chosen(tracked(REPO), COMMENTS.files, COMMENTS.exclude)


def plain_comments(root, name):
    """Each plain comment of the file `name` under `root`, read by jstack's `comments` part."""
    config = Config(comments=replace(COMMENTS, files=(name,), exclude=()))
    return [
        f"{fault.path}:{fault.line}: {fault.why.removeprefix('a plain comment: ')}"
        for fault in size.comments(root, config, [name])
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
        "jstack",
        "repo_standard",
    }
    assert {
        "install.sh",
        "features/home/hooks/home-start.sh",
        "features/jgauge/hooks/limits.sh",
    } <= set(files)
    assert {
        "features/jgauge/src/jgauge/room.sh",
        "testing/jstack_fixtures.py",
        "features/repo-guards/tests/test_no_comments.py",
    } <= set(files)
    assert "features/show-me-your-work/tests/test_show_me_your_work.py" in files
    assert "features/jleak/hooks/pre-push.sh" in files
    assert {
        "features/jbus/units/jbus.service",
        "features/jbus/units/jbus.timer",
        "features/jroles/units/jroles-mirror.timer",
        "features/jmerge/src/jmerge/protected.txt",
    } <= set(files)


def test_jstack_passes_the_comments_guard(capsys):
    assert main(["comments", "--root", str(REPO)]) == 0
    assert capsys.readouterr().out == ""


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
    assert plain_comments(tmp_path, name) == found


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
    assert plain_comments(tmp_path, name) == []
