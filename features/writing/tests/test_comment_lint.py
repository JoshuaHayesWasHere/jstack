"""The mechanical unslop rules in comments and docstrings: `features/writing/scripts/
comment_lint.py` is run here as `make check-fast` runs it, with `python3 -I -S`, on files
written to a temporary directory. It warns on one hit of each rule it holds, says nothing of
the text it lets through, and exits 0 either way."""

import subprocess
import sys

from testing.paths import REPO

SCRIPT = REPO / "features" / "writing" / "scripts" / "comment_lint.py"
DASH, EN_DASH, LEFT, RIGHT = "—", "–", "“", "”"

HITS = f'''"""Additionally, the helper serves as a cache {DASH} for now.

It reads {LEFT}them{RIGHT}. I hope this helps.
"""


def run():
    """In order to read the file, it utilizes a reader."""
    return 1


x = 1  # a range of 2 {EN_DASH} 4
'''

EXEMPT = '''#!/usr/bin/env python3
"""The value stands as it is, and its utilization is counted.

`in order to` and "serves as" are quoted, and so is `a code span
that crosses a line, prior to` the next.
"""

TEXT = "in order to, prior to, certainly"


def run():
    """Say "let me know" and `leverage` and nothing else."""
    return TEXT
'''


def lint(directory, *names):
    ran = subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), *names],
        cwd=directory,
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stderr == ""
    return ran.stdout.splitlines()


def test_one_hit_of_each_rule_is_warned_on_with_its_file_line_rule_and_match(tmp_path):
    (tmp_path / "hits.py").write_text(HITS)
    assert lint(tmp_path, "hits.py") == [
        "warn hits.py:1: rule 7 AI vocabulary: Additionally",
        "warn hits.py:1: rule 8 a fancy is: serves as",
        f"warn hits.py:1: rule 13 em or en dash: {DASH}",
        f"warn hits.py:3: rule 19 curly quote: {LEFT}",
        f"warn hits.py:3: rule 19 curly quote: {RIGHT}",
        "warn hits.py:3: rule 20 chatbot phrase: I hope this helps",
        "warn hits.py:8: rule 23 filler phrase: In order to",
        "warn hits.py:8: rule 31 plain word: utilizes",
        f"warn hits.py:12: rule 13 em or en dash: {EN_DASH}",
        "comment_lint.py: 9 warnings in comments and docstrings, which fail nothing",
    ]


def test_a_shell_line_and_a_script_comment_are_read_and_a_string_is_not(tmp_path):
    (tmp_path / "run.sh").write_text(
        '#!/bin/sh\n# it boasts a flag\necho "# whilst not a comment"\n'
    )
    (tmp_path / "page.js").write_text(
        'say("// numerous, not a comment");\nx(/[/]*/g); // it facilitates\n'
        "/* due to the fact\n   that it commences */\n"
    )
    assert lint(tmp_path, "run.sh", "page.js") == [
        "warn run.sh:2: rule 8 a fancy is: boasts",
        "warn page.js:2: rule 31 plain word: facilitates",
        "warn page.js:3: rule 23 filler phrase: due to the fact",
        "warn page.js:4: rule 31 plain word: commences",
        "comment_lint.py: 4 warnings in comments and docstrings, which fail nothing",
    ]


def test_code_quotes_stands_as_strings_and_a_minified_script_are_let_through(tmp_path):
    (tmp_path / "exempt.py").write_text(EXEMPT)
    (tmp_path / "vendor.min.js").write_text("/* it leverages numerous things */\n")
    (tmp_path / "notes.md").write_text("It serves as a note, in order to say so.\n")
    assert lint(tmp_path, "exempt.py", "vendor.min.js", "notes.md") == []


def test_with_no_file_named_it_reads_the_sources_tests_scripts_and_installer(tmp_path):
    hit = '"""It serves as one."""\n'
    for name in (
        "features/one/src/one/a.py",
        "features/one/tests/test_a.py",
        "features/one/docs/a.py",
        "features/one/tests/fixtures/vendor.min.js",
        "scripts/b.py",
        "testing/c.py",
        "elsewhere/d.py",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(hit)
    (tmp_path / "install.sh").write_text("#!/bin/sh\n# it serves as one\n")
    assert lint(tmp_path) == [
        "warn features/one/src/one/a.py:1: rule 8 a fancy is: serves as",
        "warn features/one/tests/test_a.py:1: rule 8 a fancy is: serves as",
        "warn install.sh:2: rule 8 a fancy is: serves as",
        "warn scripts/b.py:1: rule 8 a fancy is: serves as",
        "warn testing/c.py:1: rule 8 a fancy is: serves as",
        "comment_lint.py: 5 warnings in comments and docstrings, which fail nothing",
    ]
