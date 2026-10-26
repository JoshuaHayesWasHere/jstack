"""Every tracked shell script parses under bash 3.2, the `/bin/sh` and `/bin/bash` of macOS.

Bash 3.2 cannot parse a `case` pattern with no leading `(` inside `$( )`, and a script that
does not parse exits 2 before it runs a line: `jgauge room` did so on every Mac. On macOS the
guard runs `/bin/bash -n` on each script; elsewhere it runs it in the `bash:3.2` docker image,
and is skipped where docker cannot run that image.
"""

import io
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from testing.paths import REPO

IMAGE = "bash:3.2"
SHEBANG = re.compile(r"#!\s*(/bin/|/usr/bin/env\s+)(sh|bash)\b")


def tracked_scripts(root):
    """Every tracked `*.sh`, and every tracked file whose first line is a `sh` or `bash` shebang."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    found = []
    for name in filter(None, listed):
        path = Path(root, name)
        if not path.is_file():
            continue
        with path.open("rb") as file:
            first = file.readline(128).decode("utf-8", "replace")
        if name.endswith(".sh") or SHEBANG.match(first):
            found.append(name)
    return found


def docker_runs():
    try:
        probe = subprocess.run(
            ["docker", "run", "--rm", IMAGE, "true"], capture_output=True, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def bash32_errors(root, names):
    """What `bash -n` under bash 3.2 says of each script, empty when every one parses."""
    if sys.platform == "darwin":
        return "".join(
            subprocess.run(
                ["/bin/bash", "-n", name], cwd=root, capture_output=True, text=True
            ).stderr
            for name in names
        )
    if not docker_runs():
        pytest.skip(f"docker cannot run {IMAGE}, so there is no bash 3.2 here")
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode="w") as tar:
        for name in names:
            tar.add(Path(root, name), arcname=name)
    loop = 'mkdir /w && cd /w && tar -x && for f; do bash -n "$f"; done'
    return subprocess.run(
        ["docker", "run", "-i", "--rm", IMAGE, "sh", "-c", loop, "sh", *names],
        input=bundle.getvalue(),
        capture_output=True,
        timeout=120,
    ).stderr.decode()


def test_every_tracked_shell_script_parses_under_bash_3_2():
    names = tracked_scripts(REPO)
    assert "features/jgauge/src/jgauge/room.sh" in names
    assert "install.sh" in names
    assert bash32_errors(REPO, names) == ""


def test_an_unparenthesised_case_inside_a_substitution_is_found_and_its_fix_is_not(tmp_path):
    """The planted hook has no `.sh` and is found by its shebang, and fails the guard on its
    line until each pattern of its `case` has a leading `(`."""
    hook = tmp_path / "features" / "demo" / "hooks" / "pick"
    hook.parent.mkdir(parents=True)
    hook.write_text('#!/bin/sh\nn=$(case $1 in "" | *[!0-9]*) ;; *) echo "$1" ;; esac)\n')
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    names = tracked_scripts(tmp_path)
    assert names == ["features/demo/hooks/pick"]
    assert "pick: line 2: syntax error" in bash32_errors(tmp_path, names)
    hook.write_text('#!/bin/sh\nn=$(case $1 in ("" | *[!0-9]*) ;; (*) echo "$1" ;; esac)\n')
    assert bash32_errors(tmp_path, names) == ""
