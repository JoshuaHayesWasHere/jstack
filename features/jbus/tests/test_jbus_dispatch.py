"""`jbus.dispatch` launches an approved row only on a machine with room, and reports each spell with
no room once. It writes the thread it launched or adopted on the one `Thread:` line of the brief.
Like `test_jbus_kitchen.py`, the tests run the real pass against the fakes.
"""

import os
import subprocess
import textwrap
import time
from datetime import timedelta
from pathlib import Path

import pytest

from test_home_thread import as_read
from test_jbus_kitchen import NOW, REPO, RESULT, approved, complete, go, queued, review, sends
from test_room import FRESH

FULL = "load 30.00 is at or over 200% of 12 cores"


LATER = [NOW + timedelta(minutes=3 * n) for n in range(40)]


def test_a_machine_with_room_launches(kitchen):
    approved(kitchen, "alpha")
    said = kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]
    assert not any("no room" in line for line in said) and kitchen.lines("note") == []


def test_a_machine_with_no_room_launches_no_row_that_pass_and_sends_nothing(kitchen):
    kitchen.config(max_running=5)
    approved(kitchen, "alpha", priority=1)
    approved(kitchen, "beta", priority=2)
    kitchen.machine(load="30.00")
    said = kitchen.poll()
    assert [line for line in said if "alpha" in line] == [f"wait alpha: no room: {FULL}"]
    assert not any("beta" in line for line in said)
    assert kitchen.t3.launches == [] and not (kitchen.home / "tasks/alpha.md").exists()
    assert list((kitchen.state_dir / "launches").glob("*/*/*.json")) == []
    assert kitchen.lines("gate") == []
    assert not any("no room" in event["line"] + event["text"] for event in kitchen.events())
    kitchen.machine()
    kitchen.poll(LATER[1])
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha", "crew: beta"]


def test_a_plan_past_its_cushion_waits_as_a_full_machine_does(kitchen):
    approved(kitchen, "alpha")
    kitchen.machine(plan={**FRESH, "five_hour": ("100", 3600 + 59)})
    assert (
        "wait alpha: no room: the five-hour limit is 100% used, at or over 90%,"
        " and resets in 1 h 0 min"
    ) in kitchen.poll()
    assert kitchen.t3.launches == []


def test_the_tenth_pass_with_no_room_is_one_gate_and_the_eleventh_is_none(kitchen):
    approved(kitchen, "alpha")
    kitchen.machine(load="30.00")
    for moment in LATER[:9]:
        kitchen.poll(moment)
    assert kitchen.lines("condition") == []
    kitchen.poll(LATER[9])
    assert kitchen.lines("condition") == [f"condition alpha: no room for 10 passes: {FULL}"]
    kitchen.poll(LATER[10])
    assert len(kitchen.lines("condition")) == 1 and kitchen.t3.launches == []


def test_room_passes_in_the_config_is_how_many_passes_wait_before_the_gate(kitchen):
    kitchen.config(room_passes=2)
    approved(kitchen, "alpha")
    kitchen.machine(memory=1048576)
    kitchen.poll(LATER[0])
    assert kitchen.lines("condition") == []
    kitchen.poll(LATER[1])
    assert kitchen.lines("condition") == [
        "condition alpha: no room for 2 passes: 1.0 GB of memory available, under 6"
    ]


def test_a_pass_with_room_starts_the_count_again(kitchen):
    approved(kitchen, "alpha")
    kitchen.machine(load="30.00")
    for moment in LATER[:9]:
        kitchen.poll(moment)
    kitchen.machine()
    kitchen.t3.refuse = "no"
    kitchen.poll(LATER[9])
    assert kitchen.lines("condition") == ["condition alpha: T3 Code refused the launch"]
    kitchen.machine(load="30.00")
    for moment in LATER[10:19]:
        kitchen.poll(moment)
    assert len(kitchen.lines("condition")) == 1
    kitchen.poll(LATER[19])
    assert kitchen.lines("condition")[1:] == [f"condition alpha: no room for 10 passes: {FULL}"]


def test_a_pass_in_which_the_row_does_not_reach_the_check_starts_the_count_again(kitchen):
    kitchen.config(room_passes=3)
    approved(kitchen, "alpha")
    kitchen.machine(load="30.00")
    kitchen.poll(LATER[0])
    kitchen.poll(LATER[1])
    assert kitchen.main("queue", "hold", "alpha")[0] == 0
    kitchen.poll(LATER[2])
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll(LATER[3])
    kitchen.poll(LATER[4])
    assert kitchen.lines("condition") == []
    kitchen.poll(LATER[5])
    assert kitchen.lines("condition") == [f"condition alpha: no room for 3 passes: {FULL}"]


def test_room_passes_lowered_under_a_row_that_waits_still_gates_once(kitchen):
    approved(kitchen, "alpha")
    kitchen.machine(load="30.00")
    for moment in LATER[:6]:
        kitchen.poll(moment)
    kitchen.config(room_passes=5)
    kitchen.poll(LATER[6])
    kitchen.poll(LATER[7])
    assert kitchen.lines("condition") == [f"condition alpha: no room for 7 passes: {FULL}"]


def test_a_second_spell_with_no_room_is_a_gate_of_its_own(kitchen):
    kitchen.config(room_passes=1)
    approved(kitchen, "alpha")
    kitchen.t3.refuse = "no"
    for n, load in enumerate(["30.00", "0.42", "30.00"]):
        kitchen.machine(load=load)
        kitchen.poll(LATER[n])
    gate = f"condition alpha: no room for 1 passes: {FULL}"
    assert kitchen.lines("condition") == [gate, "condition alpha: T3 Code refused the launch", gate]


@pytest.mark.parametrize("jgauge", ["missing", "fails", "says something else"])
def test_a_room_check_that_cannot_run_waits(kitchen, jgauge):
    approved(kitchen, "alpha")
    if jgauge == "missing":
        every = os.environ["PATH"].split(os.pathsep)
        without = [part for part in every if not (Path(part) / "jgauge").exists()]
        kitchen.monkeypatch.setenv("PATH", os.pathsep.join(without))
        assert without != every
    else:
        does = "exit 1" if jgauge == "fails" else "echo maybe"
        (kitchen.stub / "jgauge").write_text(f"#!/bin/sh\n{does}\n")
        (kitchen.stub / "jgauge").chmod(0o755)
    assert "wait alpha: no room: jgauge room did not run" in kitchen.poll()
    assert kitchen.t3.launches == [] and kitchen.lines("gate") == []


def test_a_plan_limit_that_is_not_known_launches_and_is_a_note_once_a_day(kitchen):
    approved(kitchen, "alpha")
    kitchen.t3.refuse = "no"
    limits = kitchen.machine(plan=None)
    kitchen.poll(LATER[0])
    kitchen.poll(LATER[1])
    note = (
        "note demo: the plan's five-hour and weekly limits are not known: "
        f"{limits} does not give them"
    )
    assert kitchen.lines("note") == [note]
    assert len(kitchen.t3.launches) == 2
    kitchen.poll(NOW + timedelta(days=1))
    assert kitchen.lines("note") == [note, note]


def where_the_findings_go(kitchen, slug):
    """Return what step 4 of the pr-review skill's "After the run" prints for the brief on disk."""
    skill = as_read(REPO / "features/pr-review/SKILL.md")
    (found,) = [text for text in skill.split("```") if "crewmate $thread" in text]
    script = textwrap.dedent(found.removeprefix("sh\n")).replace("<slug>", slug)
    script = script.replace("<clean, findings or not run>", "findings")
    ran = subprocess.run(
        ["sh", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "H": str(kitchen.home)},
        check=True,
    )
    return ran.stdout.strip()


@pytest.mark.parametrize(
    ("lost", "had", "result"),
    [
        (None, "", ""),
        ("after", "", ""),
        (None, "Thread: mcp:an-earlier-launch\n", ""),
        ("after", "", RESULT),
    ],
    ids=["a launch", "an adoption", "a line already there", "a Result written before the line"],
)
def test_a_launched_or_adopted_thread_is_the_one_thread_line_in_the_head_of_the_brief(
    kitchen, lost, had, result
):
    approved = complete("alpha", "Decisions: none\n").replace("\n", f"\n{had}", 1)
    queued(kitchen, "alpha", approved)
    brief = kitchen.home / "tasks/alpha.md"
    kitchen.t3.lose = lost
    kitchen.poll()
    if lost:
        assert brief.read_text() == approved
        with brief.open("a") as file:
            file.write(result)
        kitchen.t3.lose = None
        assert "adopted alpha: mcp:thread-1" in kitchen.poll(NOW + timedelta(minutes=3))
    written = brief.read_text()
    lines = written.splitlines()
    assert [line for line in lines if line.startswith("Thread:")] == ["Thread: mcp:thread-1"]
    assert [line for line in lines if line != "Thread: mcp:thread-1"] == [
        line for line in (approved + result).splitlines() if not line.startswith("Thread:")
    ]
    place = lines.index("Thread: mcp:thread-1")
    assert place == (lines.index("## Result") - 1 if result else len(lines) - 1)
    assert where_the_findings_go(kitchen, "alpha").startswith("crewmate mcp:thread-1: ")
    kitchen.poll(NOW + timedelta(minutes=6))
    assert brief.read_text() == written and len(kitchen.t3.launches) == 1


def test_a_launch_whose_brief_never_got_its_line_gets_it_on_the_next_pass(kitchen):
    """The test covers two cases: a pass that ended between writing the launch record and writing
    the line, and a slug that jbus launched before it wrote the line at all."""
    queued(kitchen, "alpha")
    kitchen.poll()
    brief = kitchen.home / "tasks/alpha.md"
    whole = brief.read_text()
    assert "Thread: mcp:thread-1\n" in whole
    brief.write_text(whole.replace("Thread: mcp:thread-1\n", "") + RESULT)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert brief.read_text() == whole.replace("Thread: mcp:thread-1\n", "") + (
        RESULT.replace("\n## Result", "\nThread: mcp:thread-1\n## Result")
    )
    assert where_the_findings_go(kitchen, "alpha").startswith("crewmate mcp:thread-1: ")
    brief.write_text(whole.replace("Thread: mcp:thread-1\n", "") + review())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll(NOW + timedelta(minutes=4))
    assert [given["threadId"] for given in sends(kitchen)] == ["mcp:thread-1"]
    assert kitchen.lines("gate") == []
    brief.write_text(brief.read_text().replace("mcp:thread-1", "mcp:a-later-launch"))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert where_the_findings_go(kitchen, "alpha").startswith("crewmate mcp:a-later-launch: ")


@pytest.mark.parametrize(
    "written",
    [
        "{not json",
        '[{"slug": "alpha", "priority": "soon"}]',
        '[{"slug": "alpha", "priority": 1, "depends": "beta"}]',
        '["alpha"]',
    ],
)
def test_a_queue_that_does_not_parse_is_a_gate_and_nothing_is_launched(kitchen, written):
    kitchen.state.mkdir(parents=True)
    (kitchen.state / "queue.json").write_text(written)
    kitchen.poll()
    assert kitchen.lines() == ["condition demo: queue.json does not parse"]
    assert kitchen.t3.launches == []
    assert (kitchen.state / "queue.json").read_text() == written


def test_a_bare_where_shares_a_path_with_a_ticked_where_under_it(kitchen):
    bare = "Where: client/src/routes/sitter/, client/src/lib/components/ui/ (new X)"
    text = complete("alpha").replace("Where: `src/alpha/`", bare)
    assert kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=text)[0] == 0
    assert go(kitchen, "alpha")[0] == 0
    button = "client/src/lib/components/ui/Button.svelte"
    kitchen.set(
        "claims.txt", f"alpha out root {bare}\nother out root Where: `{button}`, `server/app.py`\n"
    )
    kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]
    assert kitchen.lines("overlap") == [
        f"overlap alpha: shares {button} with other; whichever merges second rebases"
    ]


SHARED = "whichever merges second rebases"


def test_two_pull_requests_whose_diffs_meet_are_one_overlap_and_a_second_pass_none(kitchen):
    """Neither brief's `Where:` names the other's files, but both pull requests change one
    file under `src/shared/`. No row is queued: the pass compares the briefs that are out."""
    kitchen.set(
        "claims.txt",
        "alpha pull request 7 root Where: `src/alpha/` Diff: `src/shared/x.py`\n"
        "beta pull request 8 root Where: `src/beta/` Diff: `docs/b.md`, `src/shared/`\n"
        "gamma not launched root Where: `src/shared/`\n",
    )
    kitchen.poll()
    line = f"overlap alpha: shares src/shared/x.py with beta, by both diffs; {SHARED}"
    assert kitchen.lines("overlap") == [line]
    (event,) = kitchen.events("overlap")
    assert event["slug"] == "alpha"
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines("overlap") == [line]
    assert kitchen.t3.launches == [] and kitchen.lines("gate") == []


def test_a_widening_found_after_launch_names_the_side_that_came_from_a_diff_once(kitchen):
    kitchen.set(
        "claims.txt",
        "alpha out root Where: `src/alpha/`\nbeta out root Where: `src/beta/`\n",
    )
    kitchen.poll()
    assert kitchen.lines("overlap") == []
    kitchen.set(
        "claims.txt",
        "alpha out root Where: `src/alpha/`\n"
        "beta pull request 8 root Where: `src/beta/` Diff: `src/alpha/routes.py`\n",
    )
    kitchen.poll(NOW + timedelta(minutes=3))
    line = f"overlap alpha: shares src/alpha/routes.py with beta, by beta's diff; {SHARED}"
    assert kitchen.lines("overlap") == [line]
    kitchen.set(
        "claims.txt",
        "alpha out root Where: `src/alpha/`\n"
        "beta pull request 8 root Where: `src/beta/` Diff: `src/alpha/`, `src/alpha/more.py`\n",
    )
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kitchen.lines("overlap") == [line]


def test_where_lines_that_meet_name_no_diff_even_when_the_diffs_meet_too(kitchen):
    kitchen.set(
        "claims.txt",
        "alpha out root Where: `src/jbus/cli.py`\n"
        "beta pull request 8 root Where: `src/jbus/` Diff: `docs/x.md`\n"
        "gamma pull request 9 root Where: `docs/` Diff: `src/zeta.py`\n",
    )
    kitchen.poll()
    assert kitchen.lines("overlap") == [
        f"overlap alpha: shares src/jbus/cli.py with beta; {SHARED}",
        f"overlap beta: shares docs/x.md with gamma, by beta's diff; {SHARED}",
    ]


def test_ten_pull_requests_of_a_hundred_files_each_are_compared_in_well_under_a_pass(kitchen):
    """The timer runs a pass every minute, so comparing the briefs out takes a small part of
    one: 10 pull requests that change 100 files each, and two of them share one file."""
    lines = []
    for n in range(10):
        files = [f"src/b{n}/d{d}/f{f}.py" for d in range(10) for f in range(10)]
        files += ["src/shared/x.py"] if n in (2, 7) else []
        diff = ", ".join(f"`{path}`" for path in files)
        lines.append(f"b{n} pull request {n + 1} root Where: `docs/b{n}.md` Diff: {diff}\n")
    kitchen.set("claims.txt", "".join(lines))
    began = time.perf_counter()
    kitchen.poll()
    assert time.perf_counter() - began < 5
    assert kitchen.lines("overlap") == [
        f"overlap b2: shares src/shared/x.py with b7, by both diffs; {SHARED}"
    ]


def test_a_glob_where_shares_the_files_it_matches_and_a_dot_where_shares_every_file(kitchen):
    kitchen.set(
        "claims.txt",
        "alpha out root Where: `src/*/x.py`, `docs/**/*.md`\n"
        "beta pull request 8 root Where: `src/beta/` Diff: `src/a/x.py`, `src/a/y.py`\n"
        "gamma pull request 9 root Where: `lib/` Diff: `docs/deep/er/g.md`, `docs/g.txt`\n",
    )
    kitchen.poll()
    assert kitchen.lines("overlap") == [
        f"overlap alpha: shares src/a/x.py with beta, by beta's diff; {SHARED}",
        f"overlap alpha: shares docs/deep/er/g.md with gamma, by gamma's diff; {SHARED}",
    ]
    kitchen.set(
        "claims.txt",
        "delta out root Where: `.`\n"
        "epsilon pull request 10 root Where: `lib/e.py` Diff: `src/e.py`\n",
    )
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines("overlap")[2:] == [
        f"overlap delta: shares lib/e.py with epsilon; {SHARED}"
    ]
