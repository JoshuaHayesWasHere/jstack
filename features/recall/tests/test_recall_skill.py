"""The recall skill's blocks list the transcripts of a directory that fall in the window, and
what the home wrote in it. They say so when there is none."""

from skill_blocks import aged, block, home, outside, repo, run, transcripts

__all__ = ["home", "outside", "repo"]


def test_recall_lists_the_transcripts_of_this_directory_in_the_window_newest_first(repo, home):
    here = transcripts(home, repo)
    new = aged(here / "new.jsonl", 0)
    older = aged(here / "older.jsonl", 3)
    aged(here / "stale.jsonl", 30)
    aged(here / "mine.jsonl", 0)
    aged(here / "new" / "subagents" / "agent.jsonl", 0)
    aged(transcripts(home, "/another/project") / "theirs.jsonl", 0)
    body = block("recall", ".claude/projects")
    assert run(body, repo, home, session="mine") == [str(new), str(older)]
    assert run(body, repo, home, before="DAYS=2\n", session="mine") == [str(new)]


def test_recall_reads_the_directory_it_is_given(repo, home, tmp_path):
    worktree = tmp_path / "trees" / "fix.login"
    theirs = aged(transcripts(home, worktree) / "theirs.jsonl", 1)
    body = block("recall", ".claude/projects")
    assert run(body, repo, home, before=f"W={worktree}\n") == [str(theirs)]


def test_recall_says_so_when_there_is_no_transcript(repo, home):
    aged(transcripts(home, repo) / "stale.jsonl", 30)
    said = run(block("recall", ".claude/projects"), repo, home)
    assert said == [
        f"no transcript: nothing under {transcripts(home, repo)} changed in the last 7 days"
    ]


def test_recall_lists_what_the_home_wrote_in_the_window(repo, home):
    record = home / ".local" / "state" / "home" / "demo"
    brief = aged(record / "tasks" / "fix-login.md", 0)
    handoff = aged(record / "handoff.md", 2)
    aged(record / "tasks" / "old.md", 30)
    aged(record / "reports" / "page.html", 0)
    aged(home / ".local" / "state" / "home" / "other" / "handoff.md", 0)
    assert run(block("recall", "home record"), repo, home) == [str(brief), str(handoff)]


def test_recall_says_so_when_there_is_no_home_record(repo, home, outside):
    body = block("recall", "home record")
    record = home / ".local" / "state" / "home" / "demo"
    assert run(body, repo, home) == [
        f"no home record: nothing under {record} changed in the last 7 days"
    ]
    assert run(body, outside, home) == ["no home record: this is not a git repository"]
