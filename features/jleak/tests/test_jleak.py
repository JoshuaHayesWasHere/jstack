"""`jleak`: what it prints for text that matches a pattern, and its exit code.

Every test runs the command. The private patterns are a file the test writes in its own config
directory, with made-up words in it. A test that needs a key that a built-in pattern matches
builds that key while the test runs, so this file holds no such key.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import jleak
from testing.paths import REPO

WORD = "zorblat"
PRIVATE = f"[patterns]\ncodename = '{WORD}'\nburrow = '/burrow/quill(?![\\w-])'\n"
KEYS = {
    "github-token": "ghp_" + "a1B2" * 9,
    "private-key": "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
    "aws-access-key": "AKIA" + "Q7" * 8,
    "slack-token": "xoxb-" + "2211-3344-" + "kLm9" * 6,
    "anthropic-key": "sk-ant-" + "api03-" + "aB3_" * 6,
}


def run(*args, cwd=None, stdin=""):
    env = os.environ | {"PYTHONPATH": str(REPO / "features" / "jleak" / "src")}
    done = subprocess.run(
        [sys.executable, "-m", "jleak", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        input=stdin,
    )
    return done.returncode, done.stdout.splitlines(), done.stderr


@pytest.fixture
def patterns(jstack_config):
    path = jstack_config.with_name(jleak.FILE)
    path.write_text(PRIVATE)
    return path


@pytest.fixture
def tree(tmp_path):
    repo = tmp_path / "tree"
    subprocess.run(["git", "init", "-q", repo], check=True)
    (repo / "notes.md").write_text("a line\nanother line\n")
    (repo / "src").mkdir()
    (repo / "src" / "code.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    return repo


def track(repo, name, text):
    (repo / name).write_text(text)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)


def test_a_clean_tree_prints_0_findings_and_exits_0(patterns, tree):
    assert run("--all", cwd=tree) == (0, ["0 findings"], "")


def test_a_finding_is_the_file_the_line_and_the_patterns_name_and_never_the_text(patterns, tree):
    track(tree, "notes.md", f"a line\nseen in /burrow/quill/desk\nby {WORD}, and {WORD}\n")
    track(tree, "key.txt", f"token = {KEYS['github-token']}\n")
    code, said, err = run("--all", cwd=tree)
    assert (code, err) == (1, "")
    assert said == [
        "key.txt:1: github-token",
        "notes.md:2: burrow",
        "notes.md:3: codename",
        "3 findings",
    ]
    assert WORD not in "\n".join(said) and KEYS["github-token"] not in "\n".join(said)


def test_a_file_whose_own_name_matches_is_a_finding_at_line_0(patterns, tree):
    track(tree, f"{WORD}.md", "nothing here\n")
    assert run("--all", cwd=tree)[:2] == (1, [f"{WORD}.md:0: codename", "1 finding"])


def test_all_reads_only_tracked_files_and_passes_over_one_that_is_not_text(patterns, tree):
    (tree / "untracked.md").write_text(f"{WORD}\n")
    (tree / "blob.bin").write_bytes(b"\0" + WORD.encode())
    subprocess.run(["git", "-C", tree, "add", "blob.bin"], check=True)
    assert run("--all", cwd=tree)[:2] == (0, ["0 findings"])


@pytest.mark.parametrize("name", KEYS)
def test_a_built_in_pattern_needs_no_file(jstack_config, tmp_path, name):
    (tmp_path / "said.txt").write_text(f"one\ntwo {KEYS[name]}\n")
    code, said, err = run(str(tmp_path / "said.txt"))
    assert (code, said) == (1, [f"{tmp_path / 'said.txt'}:2: {name}", "1 finding"])
    assert err == (
        f"jleak: no private patterns at {jstack_config.with_name(jleak.FILE)},"
        " so only the built-in ones are checked\n"
    )


def test_text_on_stdin_is_named_as_the_field_it_is(patterns):
    code, said, _ = run("--as", "title", "-", stdin=f"fix: what {WORD} asked for\n")
    assert (code, said) == (1, ["title:1: codename", "1 finding"])
    assert run("--as", "body", "-", stdin="a body\nof two lines\n")[:2] == (0, ["0 findings"])


def test_strict_refuses_to_check_with_no_private_patterns(jstack_config, tmp_path):
    (tmp_path / "said.txt").write_text("one\n")
    code, said, err = run("--strict", str(tmp_path / "said.txt"))
    assert (code, said) == (2, [])
    assert err == (
        f"jleak: no private patterns at {jstack_config.with_name(jleak.FILE)}:"
        " sh install.sh makes the file, and nothing is checked without it\n"
    )


@pytest.mark.parametrize(
    ("written", "why"),
    [
        ("[patterns\n", "it is not TOML"),
        ("codename = 'x'\n", "it has no [patterns] table"),
        ("[patterns]\n[other]\n", "other: only [patterns] is read"),
        ("[patterns]\ncodename = 3\n", "patterns.codename: not a string"),
        ("[patterns]\nCode_Name = 'x'\n", "patterns.Code_Name: a name is lower case"),
        ("[patterns]\ncodename = '(unclosed'\n", "patterns.codename: not a regular expression"),
        ("[patterns]\ncodename = 'x*'\n", "patterns.codename: it matches an empty line"),
        ("[patterns]\ngithub-token = 'x'\n", "patterns.github-token: a built-in pattern"),
    ],
)
def test_a_patterns_file_that_cannot_be_read_stops_the_check_and_shows_no_value(
    patterns, tmp_path, written, why
):
    patterns.write_text(written)
    (tmp_path / "said.txt").write_text("one\n")
    code, said, err = run(str(tmp_path / "said.txt"))
    assert (code, said) == (2, [])
    assert err.startswith(f"jleak: {patterns}: {why}")
    assert "unclosed" not in err


def test_the_file_the_install_makes_is_read_and_holds_the_home_and_the_thread_id(tmp_path):
    made = tmp_path / jleak.FILE
    made.write_text(jleak.example(Path("/burrow/quill")))
    names = [pattern.name for pattern in jleak.load(made)]
    assert names == ["home-path", "thread-id", "tailnet-name", "tailnet-address"]
    thread = "mcp:" + "-".join(("0a" * 4, "1b" * 2, "2c" * 2, "3d" * 2, "4e" * 6))
    said = tmp_path / "said.txt"
    said.write_text(
        f"in /burrow/quill/repos\nin /burrow/quillfeather\nfrom {thread}\n"
        f"at box.tail{'9f' * 3}.ts.net\nat {'.'.join(('100', '101', '2', '3'))}\nat 100.2.3.4\n"
    )
    code, lines, _ = run("--patterns", str(made), str(said))
    assert lines == [
        f"{said}:1: home-path",
        f"{said}:3: thread-id",
        f"{said}:4: tailnet-name",
        f"{said}:5: tailnet-address",
        "4 findings",
    ]


def test_this_tree_has_no_key_a_built_in_pattern_matches(jstack_config):
    code, said, _ = run("--all", cwd=REPO)
    assert (code, said) == (0, ["0 findings"])


def test_this_tree_has_nothing_the_file_the_install_makes_matches(tmp_path):
    """The test uses a made-up home, so it checks the formats the install writes
    patterns for: a thread id and a tailnet's names and addresses."""
    made = tmp_path / jleak.FILE
    made.write_text(jleak.example(Path("/burrow", "hollow")))
    code, said, _ = run("--strict", "--patterns", str(made), "--all", cwd=REPO)
    assert (code, said) == (0, ["0 findings"])
