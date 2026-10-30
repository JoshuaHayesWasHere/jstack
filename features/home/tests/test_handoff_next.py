"""The end of a handoff: a repo's home writes a note of ten lines at most, keeps it in its log and
is archived, then renames and settles itself, and starts no next home. Any other thread archives
nothing. A party's home starts its next thread on the model that the role map gives the thread's
role. The tests run the handoff skill's own shell block in a temporary repo and check the skill's
own JSON blocks against the tools."""

import json

import pytest

from test_home_thread import NAME, NOTE, OTHER, THREAD, Scene, block
from test_party_handoff import DESK, Party, takes
from test_party_handoff import OTHER as COOK
from test_tool_calls import CALLS, REPO, errors

TEMPLATES = REPO / "features" / "home" / "templates"
ARCHIVED = (
    f"archived: the root home is archived, and {NAME} has no home until someone types /home."
    " Start no home: switch off its scheduled tasks, tell the user, then rename and settle this"
    " thread"
)
NOT_THE_HOME = "not the home: "
HANDOFF = [
    call
    for call in CALLS
    if call.where.startswith("handoff:")
    and "<model selection>" not in call.written
    and "bindToCurrentThread" not in call.written
]


def template(name):
    return (TEMPLATES / name).read_text()


@pytest.fixture
def scene(tmp_path):
    return Scene(tmp_path)


def hands_off(scene, thread, checkout=None, code=0):
    """What the handoff's archive prints when `thread` runs it. The test first writes the note,
    and `thread` then runs the block the way step 3 says to. The test gives the block no reply
    from `list_scheduled_tasks`, so the output has no lines about the scheduled tasks."""
    ran = scene.home_hands_off(thread, checkout)
    assert ran.returncode == code
    return [line for line in ran.stdout.splitlines() if not line.startswith("not read:")]


def was_home(scene):
    """The thread that the next home's start settles. The test reads it the way the home skill's
    block does."""
    before = block("home", "so no thread is looked for")
    (line,) = [line for line in before.splitlines() if "was=$(" in line]
    return scene.run("home", f'M="$H"\n{line}\nprintf "%s" "$was"', scene.main, None).stdout


def kept(scene):
    """The note the archive kept in the root home's log."""
    (found,) = [path for path in (scene.home_dir / "log").iterdir() if "-before" not in path.name]
    return found.read_text()


def test_the_home_is_archived_and_told_to_start_no_home(scene):
    scene.home_starts(THREAD)
    said = hands_off(scene, THREAD)
    assert said[0] == ARCHIVED
    assert said[1].startswith(f"note: {scene.home_dir}/log/")
    assert said[-1] == f"title: home: {NAME}"
    assert not any(line.startswith("message:") for line in said)
    assert not scene.file.exists()
    assert not (scene.home_dir / "handoff.md").exists()


def test_a_crewmate_that_runs_the_handoff_archives_nothing(scene):
    scene.home_starts(THREAD)
    said = hands_off(scene, OTHER, scene.worktree, code=1)
    assert said[0].startswith(NOT_THE_HOME)
    assert scene.file.exists()


def test_an_ordinary_thread_in_the_main_checkout_archives_nothing(scene):
    scene.home_starts(THREAD)
    assert hands_off(scene, OTHER, code=1)[0].startswith(NOT_THE_HOME)


def test_a_home_another_home_took_the_place_of_archives_nothing(scene):
    scene.home_starts(THREAD)
    scene.home_starts(OTHER)
    assert hands_off(scene, THREAD, code=1)[0].startswith(NOT_THE_HOME)
    assert scene.file.read_text() == f"{OTHER}\n"


def test_a_repo_with_no_home_thread_file_archives_nothing(scene):
    assert hands_off(scene, THREAD, code=1)[0].startswith(NOT_THE_HOME)


def state(scene):
    return {
        str(path.relative_to(scene.home_dir)): path.read_bytes()
        for path in scene.home_dir.rglob("*")
        if path.is_file()
    }


def test_an_archive_run_twice_ends_where_one_run_ends_and_a_later_home_takes_its_place(scene):
    scene.home_starts(THREAD)
    first = hands_off(scene, THREAD)
    after = state(scene)
    again = hands_off(scene, THREAD)
    assert again == [first[0].replace("archived: ", "archived before: ", 1), *first[1:]]
    assert state(scene) == after
    found = block("handoff", "printf 'write:").replace("<threadId>", THREAD)
    assert scene.run("handoff", found, scene.main).stdout.startswith("archived before: ")

    scene.home_starts(OTHER)
    assert was_home(scene) == THREAD
    assert scene.file.read_text() == f"{OTHER}\n"
    assert not (scene.home_dir / "handoff.next.md").exists()


def test_the_handoff_switches_tasks_off_renames_settles_and_launches_nothing():
    tools = [call.tool for call in HANDOFF]
    assert "t3_thread_launch" not in tools
    assert tools[:3] == ["update_scheduled_task", "t3_thread_update", "t3_thread_organize"]
    off, rename, settle = (call.given for call in HANDOFF[:3])
    assert off["enabled"] is False
    assert rename == {"action": "rename", "title": "home: demo (archived 2026-10-10)"}
    assert settle == {"action": "settle"}
    assert [errors(call, call.given) for call in HANDOFF] == [[]] * len(HANDOFF)
    assert not (TEMPLATES / "handoff-seed.md").exists()


def filled_in(text=None):
    """The template as a home fills it in: the home gives each label an entry and deletes the
    guide line."""
    lines = (text or template("handoff.md")).splitlines()
    return "".join(f"{line.split(' <')[0]} none\n" for line in lines if not line.startswith("<"))


def test_a_note_written_from_the_template_names_the_home_that_wrote_it_once(scene):
    (scene.home_dir / "handoff.md").write_text(f"{NOTE}\nWas home: mcp:the-home-before\n")
    scene.home_starts(THREAD)
    note = filled_in() + "Was home: mcp:typed-by-hand\nMoved to the root: typed\n"
    assert scene.home_hands_off(THREAD, note=note).stdout.startswith("archived: ")
    text = kept(scene)
    assert text.startswith(filled_in())
    assert text.count("Was home:") == 1 and text.endswith(f"\nWas home: {THREAD}\n")
    assert "typed" not in text
    assert was_home(scene) == THREAD


GATE = "## Gate <n>: tea or coffee?\nStatus: open\nDefault: tea\nAsked by: alpha\nUndo: pour it"


@pytest.mark.parametrize(
    ("note", "why"),
    [
        (None, "is not there"),
        (template("handoff.md"), "a line of it is still the template's"),
        (filled_in().replace("Uncommitted:", "Left:"), "it has no Uncommitted: line"),
        (filled_in().replace("Why: none", "Why: <the reason>"), "it has no Why: line"),
        (filled_in() + "- one more\n" * 8, "it has 11 lines above its gates"),
        (f"{GATE}\n{filled_in()}", "it has no Why: line above its gates"),
    ],
    ids=["missing", "the template", "a label gone", "a label unfilled", "eleven", "a gate first"],
)
def test_a_note_that_is_not_one_is_refused_and_nothing_is_changed(scene, note, why):
    scene.home_starts(THREAD)
    (scene.home_dir / "handoff.md").write_text(NOTE)
    if note is not None:
        (scene.home_dir / "handoff.next.md").write_text(note)
    before = state(scene)
    ran = scene.home_hands_off(THREAD, note=None)
    assert ran.returncode == 1
    assert ran.stdout.startswith("not written: ")
    assert why in ran.stdout
    assert state(scene) == before


def test_the_gates_under_a_note_of_ten_lines_are_not_counted_and_are_kept_whole(scene):
    scene.home_starts(THREAD)
    note = filled_in() + "- one more\n" * 7 + "\n" + f"{GATE}\n" * 4
    assert scene.home_hands_off(THREAD, note=note).stdout.startswith("archived: ")
    assert kept(scene).startswith(note)


GROK = {"provider": "grok", "model": "grok-build", "instanceId": "grok-work"}
ROLES = """home: codex gpt-5-codex
expert: grok grok-build grok-work
"""


@pytest.fixture
def party(tmp_path):
    return Party(tmp_path)


@pytest.fixture
def role_map(jstack_config):
    """Write the role map the party's block reads, beside the test's own config."""
    return (jstack_config.parent / "roles").write_text


def launched(printed):
    """The launch call that a party's close printed. The function first checks that the call
    matches the schema of the launch tool."""
    given = json.loads(dict(printed)["launch"])
    assert takes("t3_thread_launch", given) == []
    return given


def test_a_partys_handoff_starts_its_next_thread_on_the_model_the_map_gives_expert(party, role_map):
    role_map(ROLES)
    given = launched(party.hands_off())
    assert set(given) == {"title", "workspaceStrategy", "message", "modelSelection"}
    assert given["modelSelection"] == GROK
    assert given["title"] == "home: desk"
    own = party.folder("cook", COOK)
    given = launched(party.hands_off(COOK, own))
    assert given["title"] == "home: cook"
    assert given["modelSelection"] == GROK


@pytest.mark.parametrize("roles", [None, "home: codex gpt-5-codex\n", "expert: inherit\n"])
def test_with_no_model_for_its_role_the_launch_is_the_one_that_inherits(party, role_map, roles):
    if roles is not None:
        role_map(roles)
    assert set(launched(party.hands_off())) == {"title", "workspaceStrategy", "message"}


def test_a_map_that_cannot_be_used_is_said_and_the_handoff_still_launches(party, role_map):
    role_map("expert: claudeAgent\n")
    (party.own / "handoff.next.md").write_text("# desk: handoff, today\n")
    ran = party.does("launch: ", DESK, quiet=False)
    assert ran.returncode == 0
    assert ran.stderr == "bad line 1: expert: claudeAgent\n"
    printed = [tuple(line.split(": ", 1)) for line in ran.stdout.splitlines()]
    assert set(launched(printed)) == {"title", "workspaceStrategy", "message"}


def test_a_close_run_again_prints_the_same_model_selection(party, role_map):
    role_map(ROLES)
    first = party.hands_off()
    ran = party.does("launch: ", DESK)
    again = [tuple(line.split(": ", 1)) for line in ran.stdout.splitlines()]
    assert again[0][0] == "closed before"
    assert launched(again) == launched(first)
