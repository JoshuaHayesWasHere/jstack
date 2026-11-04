import argparse
import json
import os
import re
import shutil
import subprocess

import pytest

from jbriefs import cli, propose
from jbriefs.runnable import runs
from test_jbus_queue import add, brief, go
from testing.paths import REPO

NO_RG = pytest.mark.skipif(shutil.which("rg") is None, reason="rg is not installed")
IDLE = (
    "- a held row says why in a test\n"
    "- `release.yml` has a step that calls `green_run`\n"
    "- the Result says what Josh decided\n"
)
CORPUS = json.loads((REPO / "features/jbriefs/tests/fixtures/propose_replay.json").read_text())


def idle(slug):
    """A brief `jbus queue add` takes, with one item that runs and three that run nothing."""
    return brief(slug).replace("- `make check` passes\n", f"- `make check` passes\n{IDLE}")


def proposed(capsys, path):
    code = cli.main(["--propose", str(path)])
    out, err = capsys.readouterr()
    return code, out.splitlines(), err


def test_each_item_that_runs_nothing_gets_one_proposal_that_runs(kitchen, capsys, tmp_path):
    path = tmp_path / "alpha.md"
    path.write_text(idle("alpha"))
    code, lines, _ = proposed(capsys, path)
    assert code == 0
    assert [line.split(":", 1)[0] for line in lines] == ["2. test", "3. grep", "4. judged"]
    assert all(runs(line.split(": ", 1)[1]) for line in lines)
    assert "`uv run pytest -q tests/test_alpha.py::test_a_held_row_says_why_in`" in lines[0]
    assert "`rg -nF -e 'green_run' release.yml`" in lines[1]
    assert lines[2].endswith("(judged: only the user can say)")


@NO_RG
def test_a_grep_of_a_flag_finds_it_where_it_is_and_not_where_it_is_not(tmp_path):
    (made,) = propose.propose("# demo: x\nDone when:\n- `--status` names the rows in cli.py\n")
    assert made.kind == "grep"
    (command,) = re.findall(r"`([^`]+)`", made.check)
    for text, exit in (("parser.add_argument('--status')\n", 0), ("nothing here\n", 1)):
        (tmp_path / "cli.py").write_text(text)
        ran = subprocess.run(["bash", "-c", command], cwd=tmp_path, capture_output=True)
        assert ran.returncode == exit, ran.stderr


def test_a_queued_row_with_no_go_gets_its_proposals(kitchen, capsys, tmp_path):
    add(kitchen, "alpha", approve=False, text=idle("alpha"))
    path = kitchen.state / "briefs" / "alpha.md"
    code, lines, _ = proposed(capsys, path)
    assert code == 0
    assert len(lines) == 3


def test_a_row_whose_go_holds_is_refused(kitchen, capsys):
    add(kitchen, "alpha", text=idle("alpha"))
    code, lines, err = proposed(capsys, kitchen.state / "briefs" / "alpha.md")
    assert (code, lines) == (1, [])
    assert err.startswith("jbriefs: refused: the go holds for alpha")


def test_a_copy_whose_go_lapsed_is_refused_while_the_stored_brief_has_one(
    kitchen, capsys, tmp_path
):
    add(kitchen, "alpha", text=idle("alpha"))
    copy = tmp_path / "alpha.md"
    copy.write_text(idle("alpha").replace("decided", "decided today"))
    code, _, err = proposed(capsys, copy)
    assert code == 1
    assert "the go holds for alpha" in err


def test_a_go_given_after_the_add_is_refused(kitchen, capsys):
    add(kitchen, "alpha", approve=False, text=idle("alpha"))
    assert go(kitchen, "alpha")[0] == 0
    assert proposed(capsys, kitchen.state / "briefs" / "alpha.md")[0] == 1


def test_no_jbus_to_ask_is_refused(kitchen, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("JBUS_CONFIG_DIR", str(tmp_path / "none"))
    path = tmp_path / "alpha.md"
    path.write_text(idle("alpha"))
    code, lines, err = proposed(capsys, path)
    assert (code, lines) == (1, [])
    assert "jbus cannot say whether alpha has a go" in err


@pytest.mark.parametrize(
    ("item", "verb"),
    [
        ("jbus queue add refuses a brief with no Size", "jbus queue add"),
        ("jmerge holds a pull request with no Proved line", "jmerge"),
        ("jgauge limits writes a row for each account", "jgauge limits"),
    ],
)
def test_a_verb_that_writes_is_a_drive_and_never_a_command(item, verb):
    (made,) = propose.propose(f"# demo: x\nDone when:\n- {item}\n")
    assert made.kind == "drive"
    assert "verify-jstack" in made.check
    assert f"run {verb} there" in made.check
    assert all(not span.startswith(verb) for span in re.findall(r"`([^`]+)`", made.item))
    assert runs(made.item)


@pytest.mark.parametrize(
    ("item", "check"),
    [
        ("jbus status names the stuck row", "`jbus status`"),
        ("jmerge --check prints held for it", "`jmerge --check`"),
        ("jgauge room says wait on a full machine", "`jgauge room`"),
    ],
)
def test_a_verb_that_only_reads_is_a_command(item, check):
    (made,) = propose.propose(f"# demo: x\nDone when:\n- {item}\n")
    assert (made.kind, made.check) == ("run", check)


def subcommands(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_every_verb_in_the_table_is_one_its_tool_has():
    """A verb a tool gains after the table was written is one `propose.verb` does not know, and
    an item that names it gets no command at all, so only a stale or made-up entry fails here."""
    from jbus import asks
    from jbus.cli import LISTED
    from jgauge.cli import parser as jgauge
    from jmerge.cli import parser as jmerge

    table = argparse.ArgumentParser()
    asks._table(table)
    flags = {flag for action in jmerge()._actions for flag in action.option_strings}
    assert set(propose.VERBS["jbus"]) <= set(LISTED)
    assert set(propose._QUEUE) <= subcommands(table)
    assert set(propose.VERBS["jgauge"]) <= subcommands(jgauge())
    assert set(propose.VERBS["jmerge"]) <= flags
    for tool, reads in propose.READS.items():
        assert {name.split()[0] for name in reads} <= set(propose.VERBS[tool])


def test_the_share_counts_the_items_of_the_rows_of_each_status(kitchen, capsys):
    add(kitchen, "alpha", text=idle("alpha"))
    add(kitchen, "beta")
    assert cli.main(["--runnable", "--status", "queued"]) == 0
    assert capsys.readouterr().out == (
        "2 of 5 Done when items run something (40%), on 2 rows queued\n"
    )
    assert cli.main(["--runnable", "--status", "merged"]) == 0
    assert capsys.readouterr().out.startswith("0 of 0 Done when items run something (-), on 0")


def git(*argv, cwd=REPO):
    return subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True)


def present(sha):
    return git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def ran(worktree, sha, check):
    """The exit of the check's command in the worktree checked out at `sha`, with none of this
    run's environment but PATH, HOME and LANG."""
    assert git("checkout", "-q", "--detach", "--force", sha, cwd=worktree).returncode == 0
    (command,) = re.findall(r"`([^`]+)`", check)[-1:]
    keep = {name: os.environ[name] for name in ("PATH", "HOME", "LANG") if name in os.environ}
    return subprocess.run(
        ["bash", "-c", command], cwd=worktree, env=keep, capture_output=True, timeout=120
    ).returncode


def wrong(worktree, entries):
    """The entries whose check does not exit 0 at the merge and not 0 at its parent."""
    return [
        entry
        for entry in entries
        if not (
            ran(worktree, entry["merge"], entry["check"]) == 0
            and ran(worktree, f"{entry['merge']}^", entry["check"]) != 0
        )
    ]


@NO_RG
def test_replay(tmp_path):
    if not all(present(entry["merge"]) for entry in CORPUS):
        pytest.skip("the checkout lacks the corpus's merges: CI's is shallow (fetch-depth 2)")
    worktree = tmp_path / "replay"
    assert git("worktree", "add", "-q", "--detach", str(worktree), "HEAD").returncode == 0
    try:
        made = []
        for entry in CORPUS:
            text = f"# {entry['slug']}: x\nWhere: {entry['where']}\nDone when:\n- {entry['item']}\n"
            (one,) = propose.propose(text)
            made.append({**entry, "check": one.check})
        assert len(made) == 30
        assert wrong(worktree, made) == []
        first = CORPUS[0]
        planted = {**first, "check": "`rg -nF 'def main' features/jbriefs/src/jbriefs/cli.py`"}
        assert wrong(worktree, [planted]) == [planted]
    finally:
        git("worktree", "remove", "--force", str(worktree))
