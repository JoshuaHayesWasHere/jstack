"""The systemd units of `templates/`: systemd takes each one's documentation, a section of
docs/jbus.md that is there, and an exit status a unit names is the one its program exits with."""

import configparser
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"
DOCS = REPO / "docs" / "jbus.md"
UNITS = sorted(path.name for path in TEMPLATES.iterdir() if path.suffix in (".service", ".timer"))
DOCUMENTED = re.compile(r"file:%Y/\.\./docs/jbus\.md#([a-z0-9-]+)")


def unit(name):
    read = configparser.ConfigParser(interpolation=None, strict=False)
    read.optionxform = str
    read.read(TEMPLATES / name)
    return read


def anchors():
    headings = re.findall(r"^#+ (.+)$", DOCS.read_text(), re.M)
    return {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}


def test_the_units_are_the_ones_install_links():
    assert UNITS == [
        "jbus-ci.service",
        "jbus-ci.timer",
        "jbus-failed.service",
        "jbus-relay.service",
        "jbus-snapshot-failed.service",
        "jbus-snapshot.service",
        "jbus-snapshot.timer",
        "jbus-view.service",
        "jbus.service",
        "jbus.timer",
    ]


@pytest.mark.parametrize("name", UNITS)
def test_each_unit_names_the_section_of_the_jbus_page_that_says_what_it_does(name, tmp_path):
    if not shutil.which("systemd-analyze"):
        pytest.skip("no systemd-analyze on PATH")
    documentation = unit(name)["Unit"]["Documentation"]
    for uri in documentation.split():
        found = DOCUMENTED.fullmatch(uri)
        assert found, f"{name}: {uri} is not file:%Y/../docs/jbus.md#<section>"
        assert found[1] in anchors(), f"{name}: docs/jbus.md has no section #{found[1]}"
    probe = tmp_path / name.replace(".timer", ".service")
    probe.write_text(
        f"[Unit]\nDescription=probe\nDocumentation={documentation}\n\n"
        "[Service]\nType=oneshot\nExecStart=/bin/true\n"
    )
    done = subprocess.run(
        ["systemd-analyze", "--user", "verify", str(probe)], capture_output=True, text=True
    )
    said = (done.stdout + done.stderr).splitlines()
    assert (done.returncode, [line for line in said if line.startswith(str(probe))]) == (0, [])


def test_the_relay_is_not_restarted_after_it_refused_to_start():
    refused = subprocess.run(
        [sys.executable, "-c", "from jbus import relay; raise SystemExit(relay.relay({}))"],
        capture_output=True,
        text=True,
    )
    assert refused.stdout.startswith("relay: refused to start: ")
    service = unit("jbus-relay.service")["Service"]
    assert service["Restart"] == "on-failure"
    assert service["RestartPreventExitStatus"] == str(refused.returncode)
