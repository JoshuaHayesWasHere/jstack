"""The systemd units of jbus, jgauge and jroles as `install.sh` links them, enables them and
writes `jbus-view.service`'s drop-in, under a temporary HOME as `test_install` runs it."""

import os
import re

import pytest

from test_install import (
    OPTED,
    RELAY_KEYS,
    REPO,
    TIMERS,
    UNITS,
    User,
    line_for,
    linux_only,
    template,
)


@pytest.fixture
def user(tmp_path):
    return User(tmp_path)


@linux_only(
    "test_launchd.py::test_setup_writes_and_bootstraps_each_agent_and_a_second_run_writes_nothing"
)
def test_the_units_are_linked_and_the_timer_enabled_once_jbus_has_a_config(user):
    units = user.with_jbus()
    assert user.run("--check") == (1, user.every("missing", units))
    assert user.run() == (0, user.every("ok", units))
    for name in UNITS:
        assert os.readlink(user.units / name) == str(template(name))
    for timer in TIMERS:
        wanted = user.units / "timers.target.wants" / timer
        assert os.readlink(wanted) == str(template(timer))
    ran = [line for line in user.said(user.systemctl_log) if not re.search("show|is-enabled", line)]
    enabled = [f"--user enable --now {timer}" for timer in TIMERS]
    assert ran[: 1 + len(TIMERS)] == ["--user daemon-reload", *enabled]
    before = user.snapshot()
    assert user.run() == (0, user.every("ok", units))
    assert user.snapshot() == before


@linux_only(
    "test_launchd.py::test_setup_writes_and_bootstraps_each_agent_and_a_second_run_writes_nothing"
)
def test_a_strangers_machine_enables_no_ci_relay_or_snapshot_unit_and_nothing_fails(user):
    units = user.with_jbus()
    assert user.run() == (0, user.every("ok", units))
    assert [name for name in [*TIMERS, *OPTED] if user.enabled(name)] == TIMERS
    ran = user.said(user.systemctl_log)
    assert not [line for line in ran if "able --now" in line and line.split()[-1] in OPTED]
    assert all((user.units / name).is_symlink() for name in OPTED)


@linux_only(
    "test_launchd.py::test_the_owners_mac_runs_the_ci_relay_and_snapshot_agents_and_drops_one_nothing_asks_for"
)
def test_the_owners_machine_enables_the_ci_relay_and_snapshot_units(user):
    units = user.as_owner()
    assert user.run() == (0, user.every("ok", units))
    assert all(user.enabled(name) for name in [*TIMERS, *OPTED])
    relay = user.units / "default.target.wants" / "jbus-relay.service"
    assert os.readlink(relay) == str(template("jbus-relay.service"))
    before = user.snapshot()
    assert user.run() == (0, user.every("ok", units))
    assert user.snapshot() == before


@linux_only(
    "test_launchd.py::test_the_owners_mac_runs_the_ci_relay_and_snapshot_agents_and_drops_one_nothing_asks_for"
)
def test_a_unit_whose_config_is_gone_is_disabled_and_one_whose_config_is_wrong_is_left_on(user):
    units = user.as_owner()
    user.run()
    user.write(user.relay_env, RELAY_KEYS.replace("a-token", "REPLACE_ME"))
    assert user.run("--check") == (0, user.every("ok", units))
    assert user.enabled("jbus-relay.service")
    user.relay_env.unlink()
    off = f"old {units} -> jbus-relay.service is enabled, and nothing asks for it"
    assert line_for(user.run("--check")[1], "units") == [off]
    assert user.run() == (0, user.every("ok", units))
    assert not user.enabled("jbus-relay.service") and user.enabled("jbus-ci.timer")
    assert os.readlink(user.units / "jbus-relay.service") == str(template("jbus-relay.service"))


@linux_only(
    "test_launchd.py::test_agents_stay_due_after_the_jbus_config_is_gone_and_say_what_they_lack"
)
def test_units_stay_due_after_the_jbus_config_is_gone_and_say_what_they_lack(user):
    units = user.with_jbus()
    user.run()
    (user.jbus / "config.toml").unlink()
    (user.units / "jbus-failed.service").unlink()
    code, said = user.run("--check")
    assert (code, line_for(said, "units")) == (1, [f"old {units} -> lacks jbus-failed.service"])
    assert user.run() == (0, user.every("ok", units))


@linux_only("test_launchd.py::test_check_and_the_doctor_read_each_agent_from_launchctl_print")
def test_a_timer_that_is_not_enabled_is_old_and_a_run_enables_it(user):
    units = user.with_jbus()
    user.run()
    (user.units / "timers.target.wants" / "jbus.timer").unlink()
    code, said = user.run("--check")
    assert (code, line_for(said, "units")) == (1, [f"old {units} -> jbus.timer is not enabled"])
    assert user.run() == (0, user.every("ok", units))


@linux_only(
    "test_launchd.py::test_a_plist_the_templates_no_longer_make_is_rewritten_and_loaded_again"
)
def test_units_linked_where_templates_kept_them_before_a_move_are_old_and_a_run_relinks_them(
    user,
):
    units = user.with_jbus()
    user.run()
    was = {
        name: REPO / "templates" / name for name in ("jroles-mirror.service", "jroles-mirror.timer")
    }
    for name, there in was.items():
        (user.units / name).unlink()
        (user.units / name).symlink_to(there)
    wanted = user.units / "timers.target.wants" / "jroles-mirror.timer"
    wanted.unlink()
    wanted.symlink_to(was["jroles-mirror.timer"])

    stale = f"old {units} -> jroles-mirror.service -> {was['jroles-mirror.service']}"
    assert line_for(user.run("--check")[1], "units") == [stale]
    assert user.run() == (0, user.every("ok", units))
    for name in was:
        assert os.readlink(user.units / name) == str(template(name))
    assert os.readlink(wanted) == str(template("jroles-mirror.timer"))


@linux_only("test_launchd.py::test_a_plist_no_install_made_is_left_as_it_is")
def test_a_unit_copied_by_hand_becomes_a_link(user):
    units = user.with_jbus()
    for name in UNITS:
        user.write(user.units / name, template(name).read_text())
    copies = f"old {units} -> {' '.join(UNITS)}: a copy of its template, not a link"
    assert line_for(user.run("--check")[1], "units") == [copies]
    assert user.run() == (0, user.every("ok", units))
    assert all((user.units / name).is_symlink() for name in UNITS)


@linux_only("test_launchd.py::test_a_plist_no_install_made_is_left_as_it_is")
def test_a_unit_made_by_hand_is_backed_up_and_replaced_and_the_install_says_so(user):
    units = user.with_jbus()
    user.run()
    edited = user.units / "jbus.service"
    edited.unlink()
    edited.write_text("[Unit]\nDescription=mine\n")

    differs = f"old {units} -> jbus.service -> not a link, differs: the install backs it up"
    code, said = user.run("--check")
    assert (code, line_for(said, "units")) == (1, [differs])
    assert edited.read_text() == "[Unit]\nDescription=mine\n"

    code, said, err = user.run_with_stderr()

    (backup,) = user.units.glob("jbus.service.*.bak")
    assert (code, said) == (0, user.every("ok", units))
    assert os.readlink(edited) == str(template("jbus.service"))
    assert backup.read_text() == "[Unit]\nDescription=mine\n"
    assert (
        f"install.sh: units {user.units}: jbus.service was not the install's: kept as {backup}"
        in err
    )
    user.run("--uninstall")
    assert backup.read_text() == "[Unit]\nDescription=mine\n"


@linux_only("test_launchd.py::test_a_plist_no_install_made_is_left_as_it_is")
def test_the_views_drop_in_is_written_from_the_config_and_follows_it(user):
    units = user.with_jbus()
    config = user.jbus / "config.toml"
    view = (
        '[view]\nhost = "192.0.2.7"\nnames = ["box", "box.tail.net"]\n'
        'origins = ["https://example.test"]\n'
    )
    user.write(config, f'server = "http://127.0.0.1:1"\n{view}')
    config.chmod(0o600)
    drop_in = user.units / "jbus-view.service.d" / "jstack.conf"

    assert user.run() == (0, user.every("ok", units))
    assert drop_in.read_text() == (
        f"# install.sh writes this from the [view] table of {config}: change that, not this.\n"
        "[Service]\n"
        'Environment="JBUS_VIEW_HOST=192.0.2.7"\n'
        'Environment="JBUS_VIEW_NAMES=box,box.tail.net"\n'
        'Environment="JBUS_VIEW_ORIGINS=https://example.test"\n'
    )
    restart = "--user try-restart jbus-view.service"
    assert user.said(user.systemctl_log).count(restart) == 1
    user.systemctl_log.unlink()
    (user.units / "jbus-failed.service").unlink()
    assert user.run() == (0, user.every("ok", units))
    assert "--user daemon-reload" in user.said(user.systemctl_log)
    assert restart not in user.said(user.systemctl_log)

    user.write(config, 'server = "http://127.0.0.1:1"\n[view]\norigins = ["https://example.com"]\n')
    stale = f"old {units} -> {drop_in} does not say the [view] of {config}"
    assert line_for(user.run("--check")[1], "units") == [stale]
    assert user.run() == (0, user.every("ok", units))
    assert drop_in.read_text().splitlines()[2:] == [
        'Environment="JBUS_VIEW_ORIGINS=https://example.com"'
    ]

    user.write(config, 'server = "http://127.0.0.1:1"\n')
    assert line_for(user.run("--check")[1], "units") == [stale]
    assert user.run() == (0, user.every("ok", units))
    assert not drop_in.exists()

    user.write(config, f'server = "http://127.0.0.1:1"\n{view}')
    user.run()
    user.run("--uninstall")
    assert not drop_in.parent.exists()
