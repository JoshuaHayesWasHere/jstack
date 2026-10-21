"""`home-thread` is the switch that hands merging from jbus to a home, and it is set by hand:
no skill step and no script writes it. A home keeps its own id in `home-id`, which jbus does
not read, so jbus goes on merging while a home runs. The start block is lifted from the home
skill and run, and jbus's pass is run over what it left."""

import os
import re
import subprocess

import pytest

from test_home_thread import OTHER, TYPED, WHICH, Scene, about_the_home_id, block, paths
from test_jbus_kitchen import Kitchen
from testing.paths import REPO

THREAD = "mcp:thread-one"
SCANNED = ["skills", "src", ".cursor", "hooks", "install.sh"]
NAMED = r"[^\s|;&<>()]*home-thread"
WRITES = [
    re.compile(rf">>?\s*{NAMED}"),
    re.compile(rf"\btee\b[^|;&]*{NAMED}"),
    re.compile(r"home-thread[^\n]*\.write_(text|bytes)\("),
    re.compile(r"""home-thread[^\n]*\bopen\(\s*["'][wax]"""),
    re.compile(r"""\bopen\([^)\n]*home-thread[^)\n]*,\s*["'][wax]"""),
]


def writes(text):
    """The lines of a text that write to a `home-thread`, each with its number."""
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), 1)
        if any(shape.search(line) for shape in WRITES)
    ]


def scanned():
    for top in SCANNED:
        assert (REPO / top).exists(), f"{top} is scanned and is not in the repo"
        for path in sorted([REPO / top, *(REPO / top).rglob("*")]):
            if path.is_file() and "__pycache__" not in path.parts:
                yield path


def test_no_skill_and_no_script_writes_a_home_thread():
    found = []
    for path in scanned():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        found += [f"{path.relative_to(REPO)}:{number}: {line}" for number, line in writes(text)]
    assert found == []


@pytest.mark.parametrize(
    "line",
    [
        """printf '%s\\n' "$ME" > "$M/home-thread\"""",
        'echo "$ME" >> $H/home-thread',
        "echo $ME >~/.local/state/home/jstack/home-thread",
        'printf "%s\\n" "$ME" | tee "$M/home-thread" > /dev/null',
        'echo "$ME" | tee -a "$H/$scope/home-thread"',
        '(state / "home-thread").write_text(f"{thread}\\n")',
        '(state / "home-thread").write_bytes(b"")',
        '(state / "home-thread").open("a").write(thread)',
        'open(state / "home-thread", "w").write(thread)',
        'with open(f"{state}/home-thread", "a") as switch:',
    ],
)
def test_a_write_to_a_home_thread_is_found(line):
    assert writes(f"a line before\n{line}\n") == [(2, line.strip())]


@pytest.mark.parametrize(
    "line",
    [
        'if [ -s "$H/home-thread" ]; then told=$(cat "$H/home-thread"); fi',
        'return (run.home / "home-thread").read_text().strip()',
        'cat "$H/home-thread" 2> /dev/null',
        'rm -f "$M/home-thread"',
        """printf '%s\\n' "$ME" > "$M/home-id\"""",
        "A project's `home-thread` is the merge switch, and no skill writes it.",
    ],
)
def test_a_read_of_a_home_thread_is_not_a_write(line):
    assert writes(line) == []


def test_jbus_still_merges_while_a_home_that_started_is_running(tmp_path, monkeypatch):
    """A root home starts by steps 1 and 3 of the home skill, in the state directory jbus
    reads. Its id is in `home-id`, `home-thread` is not there, and the pass runs `jmerge`."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    try:
        (kitchen.home / "plan.md").write_text("# demo: plan\n")
        user = tmp_path / "user"
        (user / ".claude").mkdir(parents=True)
        (user / ".claude" / "skills").symlink_to(REPO / "skills")
        (user / ".local" / "state").mkdir(parents=True)
        (user / ".local" / "state" / "home").symlink_to(kitchen.home.parent)

        def step(text):
            ran = subprocess.run(
                ["sh", "-c", f"{paths('home')}\n{text}"],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(user)},
                cwd=kitchen.checkout,
            )
            assert (ran.returncode, ran.stderr) == (0, "")
            return ran.stdout

        which, *_ = step(block("home", "title: home:").replace(TYPED, "")).splitlines()
        assert which == "root"
        third = about_the_home_id("home")
        assert "not written" not in step(third.replace("<threadId>", THREAD).replace(WHICH, which))

        assert (kitchen.home / "home-id").read_text() == f"{THREAD}\n"
        assert not (kitchen.home / "home-thread").exists()
        kitchen.set("jmerge.txt", "merged 7 alpha abc1234\n")
        said = kitchen.poll()
        assert not any(line.startswith("skipped") for line in said)
        assert kitchen.log("jmerge") == [""]
        assert kitchen.lines("jmerge") == ["merged 7 alpha abc1234"]
    finally:
        kitchen.close()


@pytest.mark.parametrize("left", [THREAD, OTHER])
def test_a_start_over_a_switch_that_holds_an_id_says_jbus_does_not_merge(tmp_path, left):
    """The state directory as a home of the skill before `home-id` left it, or as a hand
    set it: `home-thread` holds an id and there is no `home-id`. The start says so, and
    leaves the switch as it is."""
    scene = Scene(tmp_path)
    (scene.home_dir / "plan.md").write_text("# a demo repo: plan\n")
    switch = scene.home_dir / "home-thread"
    switch.write_text(f"{left}\n")
    said = scene.home_starts()
    assert said == (
        f"jbus does not merge here: {switch} holds {left}. "
        "Nothing empties it but the user, by hand.\n"
    )
    assert scene.file.read_text() == f"{THREAD}\n"
    assert switch.read_text() == f"{left}\n"


def test_a_start_over_an_empty_switch_says_nothing_of_jbus(tmp_path):
    scene = Scene(tmp_path)
    (scene.home_dir / "plan.md").write_text("# a demo repo: plan\n")
    (scene.home_dir / "home-thread").write_text("\n")
    assert scene.home_starts() == ""
