"""The tests check a context pack with no model. They run `jpack lint`, `jpack verify`
and `jpack stale` on a made-up pack in a temporary git repo. One of the pack's notes is the
template's own example note. They also run the stale check that a jbus pass makes once a day,
on a project whose checkout has a pack."""

import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from jpack import cli
from testing.paths import REPO

TEMPLATE = REPO / "features" / "jpack" / "templates" / "context"
UPLOAD = "".join(
    {12: "RETRIES = 3\n", 30: "    for _ in range(RETRIES):\n", 31: "        time.sleep(1)\n"}.get(
        number, f"line {number}\n"
    )
    for number in range(1, 41)
)
NO_REVISION = (
    "a source with no revision, in it or above the four parts"
    " (a commit id in backticks or after at, or a date as YYYY-MM-DD)"
)
UNCITED = "a source names a commit and cites no `path:line` at it"
NOTE = """\
# {question}

## Answer
{answer}

## Sources
{sources}

## Confidence
Direct: the line says it.

## Not checked
- none
"""


IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}
PINNED_AT = datetime(2026, 9, 1, tzinfo=UTC)
PINNED = "71703307a3e0071d8706eeb578e6a7365f7b4a96"


def git(cwd, *args, env=None):
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **IDENTITY, **(env or {})},
    )
    return done.stdout.strip()


def commit(repo, files, message="work", when=None):
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    dated = None
    if when:
        stamp = f"{int(when.timestamp())} +0000"
        dated = {"GIT_COMMITTER_DATE": stamp, "GIT_AUTHOR_DATE": stamp}
    git(repo, "commit", "-q", "-m", message, env=dated)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def subject(tmp_path):
    """A subject repo with one commit, the one a pack's notes are pinned to. Its author, date
    and files are fixed, so its id is the same on every run: `PINNED`, whose first seven
    characters hold a digit, as the lint asks of a commit id."""
    repo = tmp_path / "subject"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    sha = commit(repo, {"src/upload.py": UPLOAD, "src/other.py": "one\n"}, when=PINNED_AT)
    assert sha == PINNED, f"the subject commit is {sha}, not {PINNED}: what in git changed its id?"
    return repo, sha


def days_ago(days):
    return datetime.now(UTC) - timedelta(days=days)


def pack(repo, notes):
    """A pack in the repo's `docs/context/`. Each note is `(name, question, sources)`, and
    the index lists each."""
    folder = repo / "docs" / "context"
    (folder / "notes").mkdir(parents=True)
    index = []
    for name, question, sources in notes:
        text = NOTE.format(question=question, answer="Three.", sources=sources)
        (folder / "notes" / name).write_text(text)
        index.append(
            f"`{name}`: {question} (checked at `{re.search(r'[0-9a-f]{7,40}', sources)[0]}`)"
        )
    (folder / "INDEX.md").write_text("\n".join(index) + "\n")
    return folder


def jpack(*argv, cwd=None):
    """The command as a user runs it, from the subject repo's checkout."""
    done = subprocess.run(
        [sys.executable, "-m", "jpack", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return done.returncode, done.stdout.splitlines(), done.stderr


def test_the_templates_example_note_passes_the_lint_and_the_verifier_once_pinned(subject):
    repo, sha = subject
    folder = repo / "docs" / "context"
    shutil.copytree(TEMPLATE, folder)
    for path in (folder / "INDEX.md", folder / "notes" / "retries.md"):
        path.write_text(path.read_text().replace("3f9c2ab", sha[:7]))
    assert jpack("lint", "docs/context", cwd=repo) == (0, [], "")
    assert jpack("verify", "docs/context", cwd=repo) == (0, [], "")
    assert jpack("stale", "docs/context", cwd=repo) == (0, [], "")


def test_a_good_citation_passes_and_each_wrong_one_fails_with_its_line(subject):
    repo, sha = subject
    short = sha[:7]
    pack(
        repo,
        [
            ("good.md", "How many retries?", f'- `src/upload.py:12` at `{short}`: "RETRIES = 3"'),
            ("range.md", "How long between?", f'- `src/upload.py:30-31` at `{short}`: "sleep(1)"'),
            ("line.md", "Where is the count?", f'- `src/upload.py:99` at `{short}`: "RETRIES"'),
            ("path.md", "Where is the lid?", f'- `src/lid.py:3` at `{short}`: "lid"'),
            ("quote.md", "How many tries?", f'- `src/upload.py:12` at `{short}`: "RETRIES = 5"'),
            ("commit.md", "Since when?", '- `src/upload.py:12` at `abc1234`: "RETRIES = 3"'),
            ("mute.md", "What does it say?", f"- `src/upload.py:12` at `{short}`"),
        ],
    )
    code, said, _ = jpack("verify", str(repo / "docs" / "context"))
    assert code == 1
    assert said == [
        f"commit.md: `src/upload.py:12` at abc1234: no commit abc1234 in {repo}",
        f"line.md: `src/upload.py:99` at {short}: src/upload.py has 40 lines at {short}",
        f"mute.md: `src/upload.py:12` at {short}: quotes no words of the line in double quotes",
        f"path.md: `src/lid.py:3` at {short}: no src/lid.py at {short}",
        f'quote.md: `src/upload.py:12` at {short}: the line does not say "RETRIES = 5"',
    ]
    assert jpack("lint", "docs/context", cwd=repo) == (0, [], "")


def test_a_source_pinned_to_a_commit_with_no_citation_to_check_fails_and_a_dated_one_passes(
    subject,
):
    repo, sha = subject
    short = sha[:7]
    pack(
        repo,
        [
            ("bare.md", "How many?", f'- src/upload.py:12 at {short}: "RETRIES = 5"'),
            ("file.md", "Where?", f"- `src/upload.py` at `{short}`"),
            (
                "dated.md",
                "Who?",
                f'- `src/upload.py:12` at `{short}`: "RETRIES = 3"\n- the owner, asked 2026-10-15',
            ),
        ],
    )
    code, said, _ = jpack("verify", "docs/context", cwd=repo)
    assert code == 1
    assert said == [
        f'bare.md: {UNCITED}: src/upload.py:12 at {short}: "RETRIES = 5"',
        f"file.md: {UNCITED}: `src/upload.py` at `{short}`",
    ]


def test_a_shallow_checkout_says_so_where_a_cited_commit_is_not_in_it(subject, tmp_path):
    repo, sha = subject
    pack(repo, [("good.md", "How many?", f'- `src/upload.py:12` at `{sha[:7]}`: "RETRIES = 3"')])
    commit(repo, {"README.md": "later\n"})
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow))
    code, said, _ = jpack("verify", "docs/context", cwd=shallow)
    assert code == 1
    assert said[0].endswith("and the checkout is shallow: fetch its history")


def test_the_lint_reads_a_packs_index_at_its_top_and_holds_it_to_40_lines(subject):
    repo, sha = subject
    source = f'- `src/upload.py:12` at `{sha[:7]}`: "RETRIES = 3"'
    folder = pack(repo, [("good.md", "How many?", source)])
    (folder / "notes" / "unlisted.md").write_text(
        NOTE.format(question="Q?", answer="A.", sources=source)
    )
    (folder / "notes" / "bare.md").write_text(
        NOTE.format(question="Q?", answer="A.", sources="- `src/upload.py:12`")
    )
    (folder / "INDEX.md").write_text(
        (folder / "INDEX.md").read_text() + "`bare.md`: Q? (checked at `abc1234`)\n" + "\n" * 5
    )
    code, said, _ = jpack("lint", "docs/context", cwd=repo)
    assert (code, said) == (
        1,
        [f"bare.md: {NO_REVISION}: - `src/upload.py:12`", "unlisted.md: no line in INDEX.md"],
    )
    (folder / "notes" / "unlisted.md").unlink()
    (folder / "notes" / "bare.md").unlink()
    (folder / "INDEX.md").write_text(
        "".join(f"`n{n}.md`: Q? (checked at `abc1234`)\n" for n in range(40))
        + "`good.md`: How many? (checked at `abc1234`)\n"
    )
    assert jpack("lint", "docs/context", cwd=repo)[1] == [
        "INDEX.md: 41 lines that are not blank, a pack's index is at most 40"
    ]


def test_a_folder_with_no_notes_or_no_checkout_exits_2(tmp_path):
    assert jpack("verify", str(tmp_path))[0] == 2
    (tmp_path / "notes").mkdir()
    code, said, told = jpack("verify", str(tmp_path))
    assert (code, said) == (2, [])
    assert told == f"jpack: {tmp_path} is in no git checkout: name one with --repo\n"


def test_a_note_citing_a_file_changed_since_its_pin_is_stale_and_after_14_days_to_prune(subject):
    repo, sha = subject
    short = sha[:7]
    pack(
        repo,
        [
            ("fresh.md", "What is other?", f'- `src/other.py:1` at `{short}`: "one"'),
            ("old.md", "How many?", f'- `src/upload.py:12` at `{short}`: "RETRIES = 3"'),
            (
                "new.md",
                "Which?",
                f'- `src/upload.py:12` at `{short}`: "RETRIES"\n- `README.md:1` at `{short}`',
            ),
        ],
    )
    commit(repo, {"src/upload.py": UPLOAD.replace("RETRIES = 3", "RETRIES = 4")}, when=days_ago(20))
    commit(repo, {"README.md": "now\n"})
    code, said, _ = jpack("stale", "docs/context", cwd=repo)
    assert code == 1
    assert said == [
        f"stale new.md: src/upload.py changed since {short}",
        f"stale new.md: README.md changed since {short}",
        "prune new.md",
        f"stale old.md: src/upload.py changed since {short}",
        "prune old.md",
    ]
    assert jpack("stale", "docs/context", "--days", "30", cwd=repo)[1] == [
        line for line in said if not line.startswith("prune ")
    ]
    pinned = git(repo, "rev-parse", "HEAD~1")
    assert jpack("stale", "docs/context", "--rev", pinned, cwd=repo)[1] == said[:1] + said[2:]


def test_the_day_s_jbus_pass_logs_the_stale_lines_of_a_projects_pack_once(kitchen):
    from test_jbus_kitchen import NOW
    from test_jbus_word import logged

    repo = kitchen.checkout
    sha = commit(repo, {"src/upload.py": UPLOAD}, when=NOW - timedelta(days=30))
    pack(repo, [("old.md", "How many?", f'- `src/upload.py:12` at `{sha[:7]}`: "RETRIES = 3"')])
    commit(repo, {"src/upload.py": "RETRIES = 4\n"}, when=NOW - timedelta(days=20))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(hours=1))
    found = [one for one in logged(kitchen) if one["event"] == "pack"]
    assert [(one["line"], one["text"]) for one in found] == [
        (
            "pack demo: 1 stale, 1 to prune",
            f"stale old.md: src/upload.py changed since {sha[:7]}\nprune old.md",
        )
    ]
    assert kitchen.wakes.posts == [] or all(
        one["event"] != "pack" for post in kitchen.wakes.posts for one in post
    )
    kitchen.poll(NOW + timedelta(days=1))
    assert len([one for one in logged(kitchen) if one["event"] == "pack"]) == 2


def test_the_cli_main_gives_the_same_lines(subject, capsys, monkeypatch):
    repo, sha = subject
    pack(repo, [("good.md", "How many?", f'- `src/upload.py:12` at `{sha[:7]}`: "RETRIES = 9"')])
    monkeypatch.chdir(repo)
    assert cli.main(["verify", "docs/context"]) == 1
    assert capsys.readouterr().out.startswith("good.md: `src/upload.py:12`")
