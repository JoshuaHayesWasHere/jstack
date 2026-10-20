"""The Usage panel: what `jgauge session` counts, for a task's worktree and for each home,
read only when the panel is asked for."""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jbus.view.panels.usage import panel as usage
from jgauge import session
from view.scene import NOW, Scene, Served, iso, out

SECRET = "made-up-secret-plum-7f3a9c"
JGAUGE = Path(sys.executable).with_name("jgauge")


def turn(key, at, fresh, read, written, out_tokens, said=SECRET):
    """One call as Claude Code writes it, with text that is no figure."""
    return {
        "type": "assistant",
        "timestamp": iso(at).replace("+00:00", "Z"),
        "sessionId": "made-up",
        "message": {
            "id": key,
            "model": "claude-x",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": said}],
            "usage": {
                "input_tokens": fresh,
                "cache_read_input_tokens": read,
                "cache_creation_input_tokens": written,
                "output_tokens": out_tokens,
            },
        },
    }


def transcript(path, calls, start=NOW, pad=0):
    """A made-up transcript: a user's line with the secret, then `calls` calls a minute
    apart, and `pad` more bytes of the user's text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    said = {
        "type": "user",
        "timestamp": iso(start).replace("+00:00", "Z"),
        "message": {"role": "user", "content": SECRET + " " + "x" * pad},
    }
    lines = [said] + [
        turn(f"msg_{path.stem}_{n}", start + timedelta(minutes=n + 1), 3, 1000 * n, 50 + n, 7)
        for n in range(calls)
    ]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


@pytest.fixture
def place(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(usage, "WORKTREES", tmp_path / "worktrees")
    monkeypatch.setattr(usage, "_kept", {})
    return tmp_path


@pytest.fixture
def scene(tmp_path, monkeypatch, place):
    return Scene(tmp_path / "scene", monkeypatch)


@pytest.fixture
def served(scene):
    made = Served(scene)
    yield made
    made.close()


def worktree(place, slug):
    return usage.folder(place / "worktrees" / "demo" / slug)


def asked(served):
    return served.json("/panel/usage.json?project=demo")["data"]["usage"]


def task(served, slug):
    return next(one for one in asked(served)["tasks"] if one["slug"] == slug)


def test_the_folder_is_the_working_directory_with_each_character_not_a_letter_or_digit_a_dash():
    named = usage.folder(Path("/home/me/.t3/worktrees/hydra/jv_usage.2"))
    assert named == usage.PROJECTS / "-home-me--t3-worktrees-hydra-jv-usage-2"


def test_a_tasks_figures_are_what_jgauge_session_prints_for_its_transcript(place, served):
    path = transcript(worktree(place, "jam-jar") / "s1.jsonl", 4)
    printed = subprocess.run(
        [JGAUGE, "session", "--format", "json", str(path)], capture_output=True, text=True
    )
    assert printed.returncode == 0, printed.stderr
    total = json.loads(printed.stdout)["total"]
    (row,) = json.loads(printed.stdout)["rows"]
    said = task(served, "jam-jar")
    assert said["known"] is True
    assert {key: said[key] for key in usage.SUMMED} == {key: total[key] for key in usage.SUMMED}
    assert (said["calls"], said["peak_context"]) == (4, 3 + 3000 + 53)
    assert (said["first"], said["last"]) == (
        iso(NOW + timedelta(minutes=1)),
        iso(NOW + timedelta(minutes=4)),
    )
    assert [row["first_ts"], row["last_ts"]] == ["2026-10-12T20:01:00Z", "2026-10-12T20:04:00Z"]


def test_every_transcript_of_the_worktree_is_summed_and_each_is_a_session_of_its_own(place, served):
    transcript(worktree(place, "jam-jar") / "crew.jsonl", 3)
    transcript(worktree(place, "jam-jar") / "review.jsonl", 2, start=NOW + timedelta(hours=1))
    said = task(served, "jam-jar")
    assert said["calls"] == 5
    assert [one["calls"] for one in said["sessions"]] == [3, 2]
    assert said["last"] == iso(NOW + timedelta(hours=1, minutes=2))


def test_a_task_with_no_transcript_is_not_known_and_never_zero(place, served):
    said = task(served, "oat-milk")
    looked = str(worktree(place, "oat-milk")).replace(str(Path.home()) + "/", "~/", 1)
    assert said["said"] == f"not known: no transcript under {looked}"
    assert said["known"] is False
    assert {said[key] for key in usage.SUMMED} == {None}


def test_the_panel_names_its_source_and_the_age_of_what_it_read(place, served):
    path = transcript(worktree(place, "jam-jar") / "s1.jsonl", 1)
    answer = served.json("/panel/usage.json?project=demo")
    assert [one["name"] for one in answer["sources"]] == ["~/.claude/projects"]
    assert answer["sources"][0]["at"] == answer["data"]["usage"]["newest"]
    assert answer["data"]["usage"]["newest"] is not None
    assert abs(path.stat().st_mtime - _seconds(answer["data"]["usage"]["newest"])) < 1


def _seconds(at):
    return datetime.fromisoformat(at).timestamp()


def test_no_transcript_is_read_for_the_first_screen_and_one_ask_reads_each_once(
    place, served, monkeypatch
):
    transcript(worktree(place, "jam-jar") / "s1.jsonl", 2)
    read = []
    real = session.of_transcript
    monkeypatch.setattr(session, "of_transcript", lambda path: read.append(path) or real(path))
    served.json("/state.json?project=demo")
    assert read == []
    asked(served)
    assert len(read) == 1
    asked(served)
    assert len(read) == 1


def test_the_second_ask_of_a_task_with_20_mb_of_transcripts_takes_under_a_second(
    place, served, monkeypatch
):
    for n in range(10):
        transcript(worktree(place, "jam-jar") / f"s{n}.jsonl", 200, pad=2_000_000)
    size = sum(one.stat().st_size for one in worktree(place, "jam-jar").iterdir())
    assert size >= 20_000_000
    first = task(served, "jam-jar")
    began = time.monotonic()
    second = task(served, "jam-jar")
    assert time.monotonic() - began < 1.0
    assert second == first and first["calls"] == 2000


def test_a_transcript_that_grew_is_counted_again(place, served):
    path = transcript(worktree(place, "jam-jar") / "s1.jsonl", 2)
    assert task(served, "jam-jar")["calls"] == 2
    transcript(path, 3)
    assert task(served, "jam-jar")["calls"] == 3


def test_the_answer_is_numbers_and_times_and_no_text_of_a_transcript(place, scene, served):
    transcript(worktree(place, "jam-jar") / "s1.jsonl", 3)
    home(place, scene)
    answer = served.ask("/panel/usage.json?project=demo")[2]
    assert task(served, "jam-jar")["known"] is True
    assert SECRET not in answer
    assert SECRET not in served.ask("/state.json?project=demo")[2]


def home(place, scene, started=NOW - timedelta(hours=1)):
    """A home thread the pass saw, created an hour ago, and its checkout, named by the
    `.git` file of a worktree T3 made of it."""
    checkout = place / "repos" / "demo"
    made = place / "worktrees" / "demo" / "jam-jar"
    made.mkdir(parents=True, exist_ok=True)
    (made / ".git").write_text(f"gitdir: {checkout}/.git/worktrees/jam-jar\n")
    scene.passed(20, threads=[out("home: demo", minutes=5), out("crew: jam-jar")])
    return usage.folder(checkout)


def test_a_home_is_the_session_of_the_checkout_that_started_with_its_thread(place, scene, served):
    where = home(place, scene)
    created = NOW - timedelta(hours=1)
    transcript(where / "other.jsonl", 9, start=created - timedelta(hours=3))
    mine = transcript(where / "home.jsonl", 3, start=created + timedelta(seconds=2))
    agents = mine.with_suffix("") / "subagents" / "agent-a1.jsonl"
    agents.parent.mkdir(parents=True)
    agents.write_text(json.dumps(turn("msg_agent", created, 1, 900_000, 1, 1)) + "\n")
    (said,) = asked(served)["homes"]
    assert (said["title"], said["known"]) == ("home: demo", True)
    assert said["calls"] == 4
    assert said["peak_context"] == 3 + 2000 + 52


def test_a_home_with_no_session_that_started_with_it_is_not_known(place, scene, served):
    where = home(place, scene)
    transcript(where / "late.jsonl", 3, start=NOW)
    (said,) = asked(served)["homes"]
    assert said["known"] is False
    assert said["said"].startswith("not known: no transcript that starts with its thread under ")


def test_the_homes_limit_is_the_one_home_gauge_holds_it_to(place, scene, served):
    script = usage.GAUGE.read_text()
    held = asked(served)["limit"]
    assert f"limit={held['limit']} ;;" in script
    assert f"ceiling={held['ceiling']} ;;" in script
    assert held["from"].endswith("hooks/home-gauge.sh")
    (scene.home_dir / "demo").mkdir(parents=True, exist_ok=True)
    (scene.home_dir / "demo" / "limit").write_text("250000\n")
    held = asked(served)["limit"]
    assert held["limit"] == 250000
    assert held["from"].endswith("demo/limit")
