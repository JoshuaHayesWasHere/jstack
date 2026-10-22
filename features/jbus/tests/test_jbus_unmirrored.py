"""Before jbus puts a thread on a mirror instance, by a launch or by a failover move, it asks
`jroles mirror --check` of it, runs the mirror once on drift, and passes over an instance
that is still not mirrored for that pass. Run as `test_jbus_failover.py` runs, with a
`jroles` on the kitchen's PATH that answers as the test sets it."""

import json
from datetime import timedelta

import pytest

from test_jbus_failover import FAILED_16TH, POOL, PRIME, WEEKLY, cap, configures, failed_on
from test_jbus_kitchen import NOW, approved, sends
from test_jbus_resume import crew


@pytest.fixture(autouse=True)
def pools(kitchen, jstack_config, tmp_path):
    """The crew's pool is claudeAgent then prime, and providers.json makes prime a mirror."""
    kitchen.machine(plan=None)
    (jstack_config.parent / "roles").write_text(
        f"crew: claudeAgent claude-sonnet-5-5 {POOL}\nhome: claudeAgent claude-opus-5-5 {POOL}\n"
    )
    (jstack_config.parent / "providers.json").write_text(
        json.dumps(
            {
                "claudeAgent": {"driver": "claudeAgent"},
                PRIME: {"driver": "claudeAgent", "config": {"homePath": str(tmp_path / "prime")}},
            }
        )
    )


class Mirror:
    """The fake `jroles`: `--check` passes once the mirror is made, and a run makes it only
    where `mends` is set. `asked` is each call, in order."""

    def __init__(self, kitchen, tmp_path):
        self.root = tmp_path / "fake-mirror"
        self.root.mkdir()
        self.log = self.root / "log"
        fake = kitchen.stub / "jroles"
        fake.write_text(
            "#!/bin/sh\n"
            f'echo "$*" >> {self.log}\n'
            'case " $* " in *" --check "*)\n'
            f"  [ -f {self.root / 'made'} ] && exit 0\n"
            '  echo "would link x"; exit 1;;\n'
            "esac\n"
            f"[ -f {self.root / 'mends'} ] && touch {self.root / 'made'}\n"
            "exit 0\n"
        )
        fake.chmod(0o755)

    def mends(self):
        (self.root / "mends").touch()

    @property
    def asked(self):
        return self.log.read_text().splitlines() if self.log.exists() else []


@pytest.fixture
def fake(kitchen, tmp_path):
    return Mirror(kitchen, tmp_path)


CHECK, RUN = f"mirror --instance {PRIME} --check", f"mirror --instance {PRIME}"


def test_a_launch_passes_over_an_instance_that_stays_unmirrored_and_waits(kitchen, fake):
    cap("claudeAgent")
    approved(kitchen, "alpha")
    said = kitchen.poll()
    assert kitchen.t3.launches == []
    assert f"wait alpha: {PRIME} is not mirrored" in said
    (waits,) = [line for line in said if line.startswith("wait alpha: no launch")]
    assert waits.endswith(f"; {PRIME} is not mirrored")
    assert fake.asked == [CHECK, RUN, CHECK]
    assert kitchen.lines("stall") == []


def test_a_launch_on_drift_runs_the_mirror_once_and_goes_on_when_it_mends(kitchen, fake):
    cap("claudeAgent")
    fake.mends()
    approved(kitchen, "alpha")
    kitchen.poll()
    (given,) = kitchen.t3.launches
    assert given["modelSelection"]["instanceId"] == PRIME
    assert fake.asked == [CHECK, RUN, CHECK]


def test_a_launch_on_the_main_home_asks_nothing_of_the_mirror(kitchen, fake):
    approved(kitchen, "alpha")
    kitchen.poll()
    (given,) = kitchen.t3.launches
    assert given["modelSelection"]["instanceId"] == "claudeAgent"
    assert fake.asked == []


def test_a_failover_does_not_move_a_thread_onto_an_unmirrored_instance_until_it_is(kitchen, fake):
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    said = kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == [] and sends(kitchen) == []
    assert f"wait alpha: {PRIME} is not mirrored" in said
    assert any(line.startswith("wait alpha: no move: claudeAgent is capped") for line in said)
    assert kitchen.lines("stall") == []
    fake.mends()
    kitchen.poll(FAILED_16TH + timedelta(minutes=3))
    (given,) = configures(kitchen)
    assert given["modelSelection"]["instanceId"] == PRIME
    assert len(sends(kitchen)) == 1


def test_the_check_is_asked_once_a_pass_for_every_row_it_stops(kitchen, fake):
    kitchen.config(max_running=3)
    cap("claudeAgent")
    approved(kitchen, "alpha")
    approved(kitchen, "beta", priority=2)
    said = kitchen.poll(NOW)
    assert kitchen.t3.launches == []
    assert fake.asked == [CHECK, RUN, CHECK]
    assert f"wait alpha: {PRIME} is not mirrored" in said
