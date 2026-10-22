"""The verify-jstack skill's scripts. `launch.sh` says `ready:` only when a drive can run.
`doctor.sh` fails a feature whose seed the sandbox lacks. `record.sh` starts the evidence with
what a stand-in set up. Every test but the last runs the scripts, under a temporary
`TMPDIR`. The last follows each link of the pages to the file it names."""

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest

from testing.paths import REPO

SCRIPTS = REPO / "features" / "verify-jstack" / "project-skill" / "scripts"
PAGES = REPO / "testing" / "verify"
BUILT = Path(sys.executable).parent
FEATURES = sorted(
    [path.stem for path in PAGES.glob("*.md") if path.stem != "README"]
    + [path.parent.name for path in REPO.glob("features/*/verify.md")]
)
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def launch(tmp, scripts=SCRIPTS, path=os.environ["PATH"]):
    env = {k: v for k, v in os.environ.items() if not k.startswith("VERIFY_JSTACK_")}
    return subprocess.run(
        [scripts / "launch.sh"],
        env={**env, "TMPDIR": str(tmp), "PATH": path},
        capture_output=True,
        text=True,
    )


def inside(env_sh, command):
    return subprocess.run(
        ["sh", "-c", f'. "{env_sh}" && {command}'], capture_output=True, text=True
    )


def script(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\n{text}\n")
    path.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path):
    ran = launch(tmp_path)
    assert ran.returncode == 0, ran.stderr
    env_sh = Path(ran.stdout.strip().removeprefix("ready: . "))
    yield env_sh
    subprocess.run([SCRIPTS / "cleanup.sh", env_sh.parent], capture_output=True)


def checkout_with(tmp_path, tool, body):
    """A checkout with this one's scripts and build, except one command, `tool`, which is
    `body`."""
    checkout = tmp_path / "checkout"
    scripts = checkout / "features" / "verify-jstack" / "project-skill" / "scripts"
    shutil.copytree(SCRIPTS, scripts)
    subprocess.run(["git", "init", "-q", checkout], check=True)
    for name in ("python", "jbus", "jmerge", "jgauge", "jbriefs"):
        script(checkout / ".venv" / "bin" / name, f'exec "{BUILT / name}" "$@"')
    script(checkout / ".venv" / "bin" / tool, body)
    script(tmp_path / "bin" / "uv", "exit 0")
    return scripts, f"{tmp_path / 'bin'}:{os.environ['PATH']}"


def gone(pid):
    for _ in range(50):
        if not Path(f"/proc/{pid}").exists():
            return True
        time.sleep(0.1)
    return False


def test_a_launch_is_ready_with_an_empty_gh_log(sandbox):
    assert sandbox.is_file()
    assert not (sandbox.parent / "gh" / "calls.log").exists()
    assert not list((sandbox.parent / "state").iterdir())


@pytest.mark.parametrize(
    "tool, body, step",
    [
        ("jbus", "echo 'jbus: broken on purpose' >&2; exit 3", "jbus --project demo queue show"),
        ("jmerge", "echo 'jmerge: broken on purpose' >&2; exit 3", "jmerge --check"),
        ("jmerge", "exit 0", "jmerge --check"),
    ],
)
def test_a_launch_whose_command_fails_is_not_ready_and_tears_down(tmp_path, tool, body, step):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    scripts, path = checkout_with(tmp_path, tool, body)

    ran = launch(tmp, scripts, path)
    left = sorted(tmp.glob("verify-jstack.*"))
    for stranded in left:
        subprocess.run([SCRIPTS / "cleanup.sh", stranded], capture_output=True)

    assert left == []
    assert ran.returncode == 1
    assert ran.stdout == ""
    assert not any(line.startswith("ready:") for line in ran.stderr.splitlines())
    assert f"launch.sh: not ready: `{step}`" in ran.stderr
    stopped = [line for line in ran.stderr.splitlines() if line.startswith("stopped the stand-in")]
    assert len(stopped) == 1
    assert gone(stopped[0].rstrip(")").split()[-1])
    assert list(tmp.iterdir()) == [tmp / "verify-jstack-evidence"]
    assert list((tmp / "verify-jstack-evidence").iterdir()) == []


def test_doctor_passes_every_feature_on_a_new_sandbox(sandbox):
    ran = inside(sandbox, '"$VERIFY_JSTACK_SCRIPTS/doctor.sh"')

    assert ran.returncode == 0, ran.stdout
    assert ran.stdout.splitlines()[-1] == "doctor: ok"
    seeded = [line.split()[1] for line in ran.stdout.splitlines() if ": seed has " in line]
    assert sorted(seeded) == [f"{name}:" for name in FEATURES]


def test_doctor_fails_the_feature_whose_seed_is_missing(sandbox):
    (sandbox.parent / "gh" / "open.json").unlink()

    ran = inside(sandbox, '"$VERIFY_JSTACK_SCRIPTS/doctor.sh"')

    assert ran.returncode == 1
    lines = ran.stdout.splitlines()
    assert "bad  jmerge: seed lacks gh/open.json" in lines
    assert any(line.startswith("ok   jinstall: seed has ") for line in lines)
    assert lines[-1] == "doctor: not ok"


def test_doctor_tells_a_needs_line_it_cannot_check_from_a_missing_seed(sandbox, tmp_path):
    skill = tmp_path / "skill"
    shutil.copytree(SCRIPTS, skill / "scripts")
    (skill / "features").mkdir()
    (skill / "features" / "typo.md").write_text("# Typo\n\nNeeds: `demo`, `gh/opne.json`\n")
    (skill / "features" / "bare.md").write_text("# Bare\n\nPreconditions:\n")

    ran = inside(sandbox, f'"{skill}/scripts/doctor.sh"')

    assert ran.returncode == 1
    lines = ran.stdout.splitlines()
    unknown = "its Needs: line names gh/opne.json, which doctor.sh has no check for"
    assert f"bad  typo: {unknown}" in lines
    assert "bad  bare: no Needs: line says which seed its journey relies on" in lines
    assert not any("seed lacks" in line for line in lines)
    assert lines[-1] == "doctor: not ok"


def test_a_host_that_exports_its_own_directories_does_not_reach_into_the_sandbox(sandbox, tmp_path):
    host = {
        name: str(tmp_path / "host" / name)
        for name in (
            "XDG_CONFIG_HOME",
            "XDG_STATE_HOME",
            "XDG_DATA_HOME",
            "XDG_BIN_HOME",
            "UV_TOOL_BIN_DIR",
        )
    }
    said = 'echo "${XDG_CONFIG_HOME-}${XDG_STATE_HOME-}${XDG_DATA_HOME-}${XDG_BIN_HOME-}"'
    steps = [
        f'{said}"${{UV_TOOL_BIN_DIR-}}"',
        'sh "$VERIFY_JSTACK_REPO/install.sh"',
        '"$VERIFY_JSTACK_SCRIPTS/doctor.sh"',
    ]

    ran = subprocess.run(
        ["sh", "-c", f'. "{sandbox}" && {" && ".join(steps)}'],
        capture_output=True,
        text=True,
        env={**os.environ, **host},
    )

    assert ran.returncode == 0, ran.stdout + ran.stderr
    lines = ran.stdout.splitlines()
    assert lines[0] == ""
    in_the_sandbox = (
        "ok   the units, the state, uv's tools and its bin directory are in the sandbox"
    )
    assert in_the_sandbox in lines
    assert lines[-1] == "doctor: ok"
    assert (sandbox.parent / "home" / ".config" / "systemd" / "user" / "jbus.timer").is_symlink()
    assert not (tmp_path / "host").exists()


def test_doctor_still_passes_after_a_recipe_edits_the_seed(sandbox):
    edits = [
        ': > "${VERIFY_JSTACK_SANDBOX:?}/machine/limits"',
        'echo "999.00 9.99 9.99 1/100 1" > "${VERIFY_JSTACK_SANDBOX:?}/machine/proc/loadavg"',
        '"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py',
        'sh "$VERIFY_JSTACK_REPO/install.sh"',
    ]
    for edit in edits:
        assert inside(sandbox, edit).returncode == 0, edit

    ran = inside(sandbox, '"$VERIFY_JSTACK_SCRIPTS/doctor.sh"')

    assert ran.returncode == 0, ran.stdout
    assert ran.stdout.splitlines()[-1] == "doctor: ok"


def test_record_heads_the_evidence_with_what_a_stand_in_set_up(sandbox):
    for _ in range(2):
        assert inside(sandbox, "record demo echo hello").stdout == "hello\n"

    kept = inside(sandbox, 'cat "$VERIFY_JSTACK_EVIDENCE/demo.txt"').stdout
    shutil.rmtree(inside(sandbox, 'echo "$VERIFY_JSTACK_EVIDENCE"').stdout.strip())

    head, _, runs = kept.partition("$ echo hello\n")
    assert head.startswith("# Set up by a stand-in, so not verified by this run:\n")
    unverified = [line for line in head.splitlines() if line.startswith("# - ")]
    for stand_in in ("fake-gh", "fake_t3.py", "notify-send", "PROC", "LIMITS"):
        assert any(stand_in in line for line in unverified), stand_in
    assert kept.count("# Set up by a stand-in") == 1
    assert runs.count("hello\n") == 3


def test_each_link_of_a_page_goes_to_a_file_that_is_there():
    pages = [*PAGES.glob("*.md"), *REPO.glob("features/*/verify.md")]
    gone = [
        f"{page.relative_to(REPO)}: {target}"
        for page in pages
        for target in LINK.findall(page.read_text())
        if not urlparse(target).scheme and not (page.parent / target).exists()
    ]

    assert len(pages) > len(FEATURES) // 2
    assert gone == []
