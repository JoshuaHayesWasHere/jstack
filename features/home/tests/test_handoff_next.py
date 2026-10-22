"""The end of a handoff: a repo's home writes a note of ten lines at most, starts the next home,
then renames and settles itself, and any other thread starts nothing. A party's home starts its next
thread on the model the role map gives its role. The tests run the handoff skill's own shell block
in a temporary repo and check the skill's own JSON blocks against the tools."""

import json
import re

import pytest

from test_home_thread import NAME, NOTE, OTHER, THREAD, Scene, block
from test_party_handoff import DESK, Party, takes
from test_party_handoff import OTHER as COOK
from test_tool_calls import CALLS, PLACEHOLDER, REPO, errors

TEMPLATES = REPO / "features" / "home" / "templates"
THE_HOME = (
    "the home: start the next home, then rename and settle this thread\n"
    f"title: home: {NAME}\n"
    "message: /home <seed>\n"
)
NOT_THE_HOME = "not the home: start nothing, tell the user\n"
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


def hands_off(scene, thread, checkout=None):
    """What the handoff's close prints when `thread` runs it as step 3 says, after the test writes
    the note. The test gives the close no reply of `list_scheduled_tasks`, so the close's lines on
    the tasks are not here."""
    ran = scene.home_hands_off(thread, checkout)
    assert ran.returncode == 0
    return "".join(line for line in ran.stdout.splitlines(True) if not line.startswith("not read:"))


def was_home(scene):
    """The thread the next home's start settles, read as the home skill's block reads it."""
    before = block("home", "so no thread is looked for")
    (line,) = [line for line in before.splitlines() if "was=$(" in line]
    return scene.run("home", f'{line}\nprintf "%s" "$was"', scene.main).stdout


def test_the_home_that_hands_off_is_told_to_start_the_next_one(scene):
    scene.home_starts(THREAD)
    assert hands_off(scene, THREAD) == THE_HOME
    assert not scene.file.exists()


def test_a_crewmate_that_runs_the_handoff_starts_nothing(scene):
    scene.home_starts(THREAD)
    assert hands_off(scene, OTHER, scene.worktree) == NOT_THE_HOME


def test_an_ordinary_thread_in_the_main_checkout_starts_nothing(scene):
    scene.home_starts(THREAD)
    assert hands_off(scene, OTHER) == NOT_THE_HOME


def test_a_home_another_home_took_the_place_of_starts_nothing(scene):
    scene.home_starts(THREAD)
    scene.home_starts(OTHER)
    assert hands_off(scene, THREAD) == NOT_THE_HOME


def test_a_repo_with_no_home_thread_file_starts_nothing(scene):
    assert hands_off(scene, THREAD) == NOT_THE_HOME


def state(scene):
    return {
        str(path.relative_to(scene.home_dir)): path.read_bytes()
        for path in scene.home_dir.rglob("*")
        if path.is_file()
    }


CLOSED_BEFORE = re.compile(r"closed before: .*Launch only if no next home was started, .*")


def test_a_close_run_twice_and_cut_before_the_launch_ends_where_one_run_ends(scene):
    """The test runs the close again and cuts the turn between the removal of `home-id` and the
    launch. The next home's start finds the note and writes its own id."""
    scene.home_starts(THREAD)
    assert hands_off(scene, THREAD) == THE_HOME
    after = state(scene)
    again = hands_off(scene, THREAD).splitlines()
    assert CLOSED_BEFORE.fullmatch(again[0])
    assert again[1:] == THE_HOME.splitlines()[1:]
    assert state(scene) == after
    found = block("handoff", "printf 'write:").replace("<threadId>", THREAD)
    assert scene.run("handoff", found, scene.main).stdout.startswith("closed before: ")

    scene.home_starts(OTHER)
    assert (scene.home_dir / "handoff.md").read_text() == f"{NOTE}\nWas home: {THREAD}\n"
    assert scene.file.read_text() == f"{OTHER}\n"
    assert not (scene.home_dir / "handoff.next.md").exists()
    assert hands_off(scene, THREAD) == NOT_THE_HOME
    assert scene.file.read_text() == f"{OTHER}\n"


def test_the_handoff_launches_then_renames_then_settles_and_only_passes_mail_on_after():
    assert [call.tool for call in HANDOFF] == [
        "update_scheduled_task",
        "t3_thread_launch",
        "t3_thread_list",
        "t3_thread_update",
        "t3_thread_organize",
        "t3_thread_send",
        "t3_thread_send",
    ]
    _, launch, lookup, rename, settle, *_ = (call.given for call in HANDOFF)
    assert launch["title"] == "home: demo"
    assert launch["workspaceStrategy"] == {"type": "root"}
    assert lookup == {"titleContains": launch["title"]}
    assert rename == {"action": "rename", "title": "home: demo (handed off 2026-10-10)"}
    assert settle == {"action": "settle"}


def test_the_launch_takes_a_seed_written_from_the_template():
    launch = HANDOFF[1]
    filled = PLACEHOLDER.sub('1. The user: "keep the watch armed"', template("handoff-seed.md"))
    seed = filled.strip()
    assert "\n" in seed and '"' in seed
    title, message = (line.split(": ", 1)[1] for line in THE_HOME.splitlines()[1:])
    assert f'"{message}"' in launch.written
    written = launch.written.replace("<title>", title).replace("<seed>", json.dumps(seed)[1:-1])
    given = json.loads(written)
    assert errors(launch, given) == []
    assert given["title"] == f"home: {NAME}"
    assert given["message"] == f"/home {seed}"


def filled_in(text=None):
    """The template as a home fills it in: each label with an entry, and the guide line gone."""
    lines = (text or template("handoff.md")).splitlines()
    return "".join(f"{line.split(' <')[0]} none\n" for line in lines if not line.startswith("<"))


def test_the_template_is_a_note_of_ten_lines_at_most_with_its_four_labels():
    lines = template("handoff.md").splitlines()
    assert len(lines) <= 10
    labels = [line.split(" <")[0] for line in lines if not line.startswith("<")]
    assert labels == ["Next:", "Out, not on the bus:", "Do not redo:", "Uncommitted:"]


def test_a_note_written_from_the_template_names_the_home_that_wrote_it_once(scene):
    (scene.home_dir / "handoff.md").write_text(f"{NOTE}\nWas home: mcp:the-home-before\n")
    scene.home_starts(THREAD)
    note = filled_in() + "Was home: mcp:typed-by-hand\n"
    assert scene.home_hands_off(THREAD, note=note).stdout.startswith("the home: ")
    assert (scene.home_dir / "handoff.md").read_text() == f"{filled_in()}\nWas home: {THREAD}\n"
    assert was_home(scene) == THREAD


GATE = "## Gate <n>: tea or coffee?\nStatus: open\nDefault: tea\nAsked by: alpha\nUndo: pour it"


@pytest.mark.parametrize(
    ("note", "why"),
    [
        (None, "is not there"),
        (template("handoff.md"), "a line of it is still the template's"),
        (filled_in().replace("Uncommitted:", "Left:"), "it has no Uncommitted: line"),
        (filled_in().replace("Next: none", "Next: <the one thing>"), "it has no Next: line"),
        (filled_in() + "- one more\n" * 7, "it has 11 lines above its gates"),
        (f"{GATE}\n{filled_in()}", "it has no Next: line above its gates"),
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
    note = filled_in() + "- one more\n" * 6 + "\n" + f"{GATE}\n" * 4
    assert scene.home_hands_off(THREAD, note=note).stdout.startswith("the home: ")
    assert (scene.home_dir / "handoff.md").read_text() == f"{note}\nWas home: {THREAD}\n"


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
    """The launch call a party's close printed, after a check that the launch tool takes it."""
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
