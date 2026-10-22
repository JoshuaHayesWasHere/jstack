"""The systemd units of `templates/` and of each feature's `units/`.

systemd accepts each unit's documentation, which names a section that exists in the docs
beside the unit. An exit status that a unit names is the one its program exits with."""

import configparser
import re
import shutil
import subprocess
import sys

import pytest

from jinstall.kinds import unit_templates
from testing.paths import REPO

PATHS = unit_templates(REPO)
UNITS = sorted(PATHS)
DOCUMENTED = re.compile(r"file:%Y/\.\./docs/([a-z/-]+\.md)#([a-z0-9-]+)")


def unit(name):
    read = configparser.ConfigParser(interpolation=None, strict=False)
    read.optionxform = str
    read.read(PATHS[name])
    return read


def anchors(name, page):
    """The sections of `page` in the docs that `%Y/../docs/` names, which sit beside the
    folder of `name`."""
    docs = PATHS[name].parent.parent / "docs"
    headings = re.findall(r"^#+ (.+)$", (docs / page).read_text(), re.M)
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
        "jbus-stale.service",
        "jbus-stale.timer",
        "jbus-view.service",
        "jbus.service",
        "jbus.timer",
        "jgauge-limits.service",
        "jgauge-limits.timer",
        "jgauge-sample.service",
        "jgauge-sample.timer",
        "jroles-mirror.service",
        "jroles-mirror.timer",
    ]


@pytest.mark.parametrize("name", UNITS)
def test_each_unit_names_the_section_of_the_docs_that_says_what_it_does(name, tmp_path):
    documentation = unit(name)["Unit"]["Documentation"]
    for uri in documentation.split():
        found = DOCUMENTED.fullmatch(uri)
        assert found, f"{name}: {uri} is not file:%Y/../docs/<page>.md#<section>"
        assert found[2] in anchors(name, found[1]), f"{name}: {found[1]} has no section #{found[2]}"
    if not shutil.which("systemd-analyze"):
        pytest.skip("no systemd-analyze on PATH")
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
