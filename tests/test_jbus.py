"""What holds for the package as a whole: what its source imports and names, what the repo
may hold, the example config and the units that run a pass, and what `jbus/__init__.py`
keeps for every pass: the config it refuses and the status file.

The tests that run a pass run it in the kitchen of `test_jbus_kitchen`, against a faked T3
Code server, `gh`, `jmerge` and webhook. Nothing reaches the network.
"""

import configparser
import json
import re
import shlex
import stat
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from jbus import queue, t3, wake
from jbus.view.panels.usage import panel as usage
from jmerge import cli
from test_jbus_kitchen import FIXTURE, NOW, REPO


def test_the_source_imports_no_model_client_and_names_no_other_t3_tool():
    source = "\n".join(path.read_text() for path in sorted((REPO / "src/jbus").rglob("*.py")))
    counted = "\n".join(path.read_text() for path in sorted((REPO / "src/jgauge").rglob("*.py")))
    counted += "\n" + (REPO / "src/jbriefs/parse.py").read_text()
    counted += "\n" + "\n".join(
        path.read_text() for path in sorted((REPO / "src/jpack").glob("*.py"))
    )
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", source + counted, re.M)
    roots = {name.split(".")[0] for name in imports}
    assert roots <= set(sys.stdlib_module_names) | {
        "jbus",
        "jmerge",
        "jsettings",
        "jgauge",
        "jbriefs",
        "jroles",
        "jpack",
    }, roots
    named = source.replace(queue.SESSION, "").replace(f'KEPT = "{usage.KEPT}"', "", 1)
    assert not re.search(r"anthropic|openai|claude|api\.|/v1/messages", named, re.I)
    assert set(re.findall(r"\bt3_[a-z_]+\b", source)) == {t for t in t3.TOOLS if t[:3] == "t3_"}


@pytest.mark.parametrize("name", ["config.toml", "t3.json"])
@pytest.mark.parametrize("mode", [0o640, 0o604])
def test_a_config_or_a_token_others_can_read_stops_jbus(kitchen, name, mode):
    (kitchen.config_dir / name).chmod(mode)
    code, said = kitchen.main("poll")
    assert code == 1
    path = kitchen.config_dir / name
    assert said == f"refused: {path} is mode {mode:03o}, readable by others: chmod 600 it\n"
    assert kitchen.log("jmerge") == []


def test_nothing_in_the_repo_holds_a_url_a_key_or_a_token():
    files = [
        *(REPO / "src/jbus").rglob("*.py"),
        REPO / "src/jbus/view/page.html",
        *(REPO / "tests").glob("test_jbus*.py"),
        REPO / "tests/fixtures/t3/jbus-mcp.json",
        REPO / "templates/jbus.service",
        REPO / "templates/jbus.timer",
        REPO / "templates/jbus-view.service",
        REPO / "README.md",
        REPO / "docs/jbus.md",
        REPO / "docs/chef.md",
        REPO / "docs/configuration.md",
    ]
    allowed = re.compile(r"^(127\.0\.0\.1|localhost|example\.(com|test|invalid)|[^/]*[<{$].*)")
    own = json.loads((REPO / "plugin.json").read_text())["repository"]
    for path in files:
        text = path.read_text().replace(own, "")
        for host in re.findall(r"https?://([^\s\"'`)>/]*)", text):
            assert allowed.match(host) or host == "", f"{path.name}: {host}"
        assert not re.search(r"Bearer [A-Za-z0-9_-]{20,}", text), path.name
    assert not re.search(r"[A-Za-z0-9_-]{30,}", json.dumps(FIXTURE["token_response"]))


def test_no_page_of_docs_jbus_holds_a_url_a_key_or_a_token():
    pages = sorted((REPO / "docs/jbus").glob("*.md"))
    assert len(pages) > 10
    allowed = re.compile(r"^(127\.0\.0\.1|localhost|example\.(com|test|invalid)|[^/]*[<{$].*)")
    for path in pages:
        text = path.read_text()
        for host in re.findall(r"https?://([^\s\"'`)>/]*)", text):
            assert allowed.match(host) or host == "", f"{path.name}: {host}"
        assert not re.search(r"Bearer [A-Za-z0-9_-]{20,}", text), path.name


def test_the_example_config_ships_with_dispatch_on_and_only_placeholders():
    page = (REPO / "docs/configuration.md").read_text()
    (example,) = [
        one for one in re.findall(r"```toml\n(.*?)```", page, re.S) if "[[project]]" in one
    ]
    import tomllib

    given = tomllib.loads(example)
    assert given["dispatch"] is True and "max_running" not in given
    (project,) = given["project"]
    assert set(project) == {"name", "checkout", "state", "projectId", "webhook_url", "webhook_key"}
    assert all("<" in project[key] for key in ("projectId", "webhook_url", "webhook_key"))


def test_the_timer_runs_a_pass_every_minute_and_a_failed_one_runs_the_alarm():
    """The three units as systemd reads them, and the commands the services name."""
    units = {}
    for name in ("jbus.service", "jbus.timer", "jbus-failed.service"):
        units[name] = configparser.ConfigParser(interpolation=None)
        units[name].optionxform = str
        units[name].read(REPO / "templates" / name)
    service, failed = units["jbus.service"], units["jbus-failed.service"]
    for unit, verb in ((service, "poll"), (failed, "alarm")):
        command = shlex.split(unit["Service"]["ExecStart"])
        assert (Path(command[0]).name, command[1:]) == ("jbus", [verb])
        assert unit["Service"]["Type"] == "oneshot"
    assert service["Unit"]["OnFailure"] == "jbus-failed.service"
    assert units["jbus.timer"]["Timer"]["OnUnitActiveSec"] == "1min"
    assert units["jbus.timer"]["Install"]["WantedBy"] == "timers.target"


def test_a_fresh_check_ends_before_jbus_stops_jmerge_and_jmerge_before_systemd_stops_the_pass():
    """The three limits, each named once: the check's own, what a pass allows `jmerge`, and
    the unit's. A check that outran a later one was killed before it recorded (03:26 ET)."""
    service = configparser.ConfigParser(interpolation=None)
    service.optionxform = str
    service.read(REPO / "templates" / "jbus.service")
    started = service["Service"]["TimeoutStartSec"]
    assert re.fullmatch(r"\d+min", started)
    assert cli.Fresh.TIMEOUT < wake.JMERGE_TIMEOUT < int(started.removesuffix("min")) * 60


def test_each_pass_rewrites_the_status_file_and_jbus_status_prints_it(kitchen):
    assert kitchen.main("status") == (
        1,
        f"refused: no status at {kitchen.state_dir / 'status.json'}: no pass has run\n",
    )
    kitchen.poll()
    written = {
        "last_pass": "2026-10-12 11:00 ET",
        "projects": {
            "demo": {
                "failed_wakes": 0,
                "last_error": "",
                "outbox": 0,
                "sign_in": "",
                "sweep": "",
            }
        },
        "streaks": {},
        "homes_off_bus": [],
        "scratch": {},
        "token_expires": "2026-11-11 10:00 ET",
        "sign_in_reminder": (
            "sign-in to the webhook of demo on 2026-11-04, each day from 2026-11-08, "
            "and when it runs out at 2026-11-11 10:00 ET"
        ),
    }
    assert kitchen.status() == written
    assert stat.S_IMODE((kitchen.state_dir / "status.json").stat().st_mode) == 0o600
    code, said = kitchen.main("status")
    printed = json.loads(said)
    assert printed.pop("pass")["started"] == "2026-10-12T15:00:00Z"
    assert (code, printed) == (0, written)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.status()["last_pass"] == "2026-10-12 11:03 ET"


def test_with_no_token_the_status_file_has_no_expiry(kitchen):
    (kitchen.config_dir / "t3.json").unlink()
    kitchen.poll()
    assert kitchen.status()["token_expires"] is None
