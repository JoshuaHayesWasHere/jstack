import os
import subprocess
import sys
from pathlib import Path

import pytest

from jgauge import cli, sizes
from jgauge.sizes import From, Machine, Name

BIN = Path(sys.executable).parent
KIB_PER_GIB = 1024 * 1024


def fake_proc(root: Path, cores: int, gib: int) -> Path:
    """A /proc of `cores` processors and `gib` GiB, as `Machine.here` and room.sh read it."""
    root.mkdir(parents=True, exist_ok=True)
    lines = "".join(f"cpu{n} 1 2 3 4 5 6 7 8 0 0\n" for n in range(cores))
    (root / "stat").write_text(f"cpu  9 9 9 9 9 9 9 9 0 0\n{lines}intr 1\nctxt 2\n")
    (root / "meminfo").write_text(f"MemTotal:       {gib * KIB_PER_GIB} kB\nMemFree: 1 kB\n")
    return root


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A machine of 8 processors and 16 GiB, with no limits file and no TEST_SLOTS."""
    monkeypatch.setenv("PROC", str(fake_proc(tmp_path / "proc", 8, 16)))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("TEST_SLOTS", raising=False)
    return tmp_path


def write_machine(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config" / "jstack" / "machine.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_the_facts_are_the_processors_and_the_memory_of_the_whole_machine(tmp_path):
    found = Machine.here(fake_proc(tmp_path, 24, 62))
    assert found == Machine(24, 62)
    assert found.says() == "24 cores, 62 GiB"


def test_a_fact_that_cannot_be_read_is_taken_as_its_fallback(tmp_path):
    found = Machine.here(tmp_path / "no-proc")
    assert found == Machine(sizes.FALLBACK_CORES, sizes.FALLBACK_GIB, ("cores", "memory"))
    assert (
        found.says() == "2 cores, 4 GiB (cores not read, taken as 2) (memory not read, taken as 4)"
    )


DARWIN = Path(__file__).parent / "fixtures" / "darwin"


@pytest.fixture
def mac(tmp_path, monkeypatch):
    """A Mac: `sys.platform` is darwin and `sysctl` prints the output in fixtures/darwin, 12
    processors and 16 GiB. `PROC` is unset, as on a Mac."""
    shown = tmp_path / "darwin"
    shown.mkdir()
    (shown / "sysctl.txt").write_text((DARWIN / "sysctl.txt").read_text())
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("DARWIN", str(shown))
    monkeypatch.setenv("PATH", f"{DARWIN / 'bin'}:{os.environ['PATH']}")
    monkeypatch.delenv("PROC", raising=False)
    return shown


def test_the_facts_of_a_mac_are_its_processors_and_memory_from_sysctl(mac):
    found = Machine.here()
    assert found == Machine(12, 16)
    assert found.says() == "12 cores, 16 GiB"


def test_a_mac_given_a_proc_reads_that_proc_and_not_sysctl(mac, tmp_path, monkeypatch):
    """A caller that names a /proc in `PROC` has that machine read on every system."""
    monkeypatch.setenv("PROC", str(fake_proc(tmp_path / "proc", 24, 62)))
    assert Machine.here() == Machine(24, 62)


def test_a_mac_whose_sysctl_says_nothing_takes_the_fallbacks(mac):
    (mac / "sysctl.txt").write_text("")
    assert Machine.here() == Machine(sizes.FALLBACK_CORES, sizes.FALLBACK_GIB, ("cores", "memory"))


@pytest.mark.parametrize(
    ("cores", "gib", "full", "short", "crews"),
    [
        (1, 2, 1, 1, 1),
        (2, 4, 1, 1, 2),
        (8, 16, 2, 1, 8),
        (12, 32, 1, 2, 12),
        (24, 62, 1, 4, 24),
        (64, 128, 2, 8, 64),
        (24, 8, 1, 4, 4),
    ],
)
def test_each_size_is_derived_from_the_cores_and_the_memory(cores, gib, full, short, crews):
    machine = Machine(cores, gib)
    assert sizes.derive(Name.TEST_SLOTS, machine) == full
    assert sizes.derive(Name.SHORT_SLOTS, machine) == short
    assert sizes.derive(Name.MAX_RUNNING, machine) == crews


@pytest.mark.parametrize("cores", [1, 2, 3, 4, 8, 12, 16, 24, 32, 64, 128])
def test_every_full_slot_at_once_runs_at_most_one_desk_worker_a_processor(cores):
    slots = sizes.derive(Name.TEST_SLOTS, Machine(cores, 1024))
    assert slots * sizes.desk_workers(cores) <= max(cores, sizes.desk_workers(cores))


def test_the_flag_wins_then_the_variable_then_the_file_then_the_machine(machine, monkeypatch):
    assert sizes.resolve(Name.TEST_SLOTS).came_from is From.DERIVED
    assert sizes.resolve(Name.TEST_SLOTS).value == 2
    written = write_machine(machine, "test_slots = 3\nshort_slots = 5\n")
    assert sizes.resolve(Name.TEST_SLOTS) == sizes.Limit(
        Name.TEST_SLOTS, 3, From.FILE, str(written), 1
    )
    assert sizes.resolve(Name.SHORT_SLOTS).value == 5
    monkeypatch.setenv("TEST_SLOTS", "4")
    assert (
        sizes.resolve(Name.TEST_SLOTS).line() == "test_slots     4  env TEST_SLOTS=4 (derived: 1)"
    )
    assert sizes.resolve(Name.TEST_SLOTS, flag="1").came_from is From.FLAG


def test_the_crew_cap_is_jbus_value_else_the_machine(machine):
    path = machine / "config.toml"
    given = sizes.resolve(Name.MAX_RUNNING, written=6, written_in=path)
    assert (given.value, given.came_from, given.where, given.derived) == (
        6,
        From.FILE,
        str(path),
        8,
    )
    assert sizes.resolve(Name.MAX_RUNNING, written=None).value == 8


@pytest.mark.parametrize(
    ("text", "why"),
    [
        (
            "test_slots = 0\n",
            "test_slots in {path} is 0, and the number of test_slots is 1 or more",
        ),
        ("test_slots = true\n", "test_slots in {path} is True, and the number of test_slots is"),
        ("short_slots = 1.5\n", "short_slots in {path} is 1.5, and the number of short_slots"),
        ("max_running = 4\n", "{path} has the key max_running, not one of test_slots, short_slots"),
        ("test_slots = \n", "{path} does not parse: "),
    ],
)
def test_a_limits_file_that_cannot_be_used_refuses_in_one_line(machine, text, why):
    path = write_machine(machine, text)
    with pytest.raises(sizes.Refused) as refused:
        sizes.resolve(Name.TEST_SLOTS)
    assert str(refused.value).startswith(why.format(path=path))


def test_jgauge_limits_prints_each_size_where_it_came_from_and_rooms_lines(
    machine, monkeypatch, capsys
):
    jbus = machine / "jbus"
    jbus.mkdir()
    (jbus / "config.toml").write_text("max_running = 6\n")
    monkeypatch.setenv("JBUS_CONFIG_DIR", str(jbus))
    monkeypatch.setenv("TEST_SLOTS", "3")
    assert cli.main(["sizes"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[:5] == [
        "test_slots     3  env TEST_SLOTS=3 (derived: 2)",
        "short_slots    1  derived from 8 cores, 16 GiB",
        f"max_running    6  file {jbus / 'config.toml'} (derived: 8)",
        "workers        8  derived from 8 cores, 16 GiB",
        "total         10  3 full x 2 + 1 short x 4 workers, over workers 8 by 2: lower test_slots"
        f" or short_slots, or raise workers, in {machine / 'config' / 'jstack' / 'machine.toml'}",
    ]
    assert out[5].startswith("room LOAD=200 CPU=40 MEMORY=6 PRESSURE=10 CUSHION=90 SLOTS=85 ")
    assert out[6] == (
        "note: TEST_SLOTS=3 is set here and jbus.service does not see it:"
        f" set test_slots in {machine / 'config' / 'jstack' / 'machine.toml'}"
    )


def printed(monkeypatch, capsys, root: Path, cores: int) -> dict[str, list[str]]:
    """What `jgauge sizes` prints on a machine of `cores` processors and 64 GiB, by first word."""
    monkeypatch.setenv("PROC", str(fake_proc(root / f"proc{cores}", cores, 64)))
    monkeypatch.setenv("JBUS_CONFIG_DIR", str(root / "no-jbus"))
    assert cli.main(["sizes"]) == 0
    return {line.split()[0]: line.split() for line in capsys.readouterr().out.splitlines()}


@pytest.mark.parametrize(("cores", "desk"), [(24, 6), (8, 2)])
def test_the_derived_slots_of_both_lanes_keep_their_workers_within_the_budget(
    machine, monkeypatch, capsys, cores, desk
):
    """The short lane is inside the core budget (sc-short-lane-budget): 6 short slots of 4 beside
    4 full of 6 put 48 workers on yelena's 24 cores, and the slots made a run queue of 25 on their
    own. With every slot of both lanes taken, the workers fit the cores, and each lane keeps a
    slot. `desk` is the Makefile's count for a full run, a quarter of the cores, at least 2."""
    said = printed(monkeypatch, capsys, machine, cores)
    full, short = int(said["test_slots"][1]), int(said["short_slots"][1])
    assert said["workers"][1:3] == [str(cores), "derived"]
    assert full >= 1 and short >= 1
    total = int(said["total"][1])
    assert total == full * desk + short * 4
    assert total <= cores
    assert said["total"][-3:] == ["within", "workers", str(cores)]


def test_the_owner_sets_the_budget_and_both_lanes_are_sized_inside_it(machine, monkeypatch, capsys):
    """A `workers` line in machine.toml is the budget in place of the cores: 14 on 24 cores leaves
    room for 1 full slot of 6 and 2 short slots of 4."""
    written = write_machine(machine, "workers = 14\n")
    said = printed(monkeypatch, capsys, machine, 24)
    assert said["workers"][1:4] == ["14", "file", str(written)]
    assert (said["test_slots"][1], said["short_slots"][1]) == ("1", "2")
    assert said["total"][1] == "14"


def test_slots_the_owner_sets_past_the_budget_are_kept_and_called_over_budget(
    machine, monkeypatch, capsys
):
    """The owner's count wins over the budget, as over any derived count, and `jgauge sizes` says
    by how much it is over: yelena's 6 short slots of 4 are 24 workers before the full lane's 6."""
    write_machine(machine, "short_slots = 6\n")
    said = printed(monkeypatch, capsys, machine, 24)
    assert (said["test_slots"][1], said["short_slots"][1]) == ("1", "6")
    assert said["total"][1] == "30"
    assert "workers, over workers 24 by 6: " in " ".join(said["total"])


def test_the_module_runs_with_the_standard_library_alone(machine):
    """`jgauge.sizes` imports nothing of jstack, so a bare `python3 -I` can run it."""
    source = Path(sizes.__file__).read_text()
    imported = {
        line.split()[1].split(".")[0]
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
    }
    assert imported <= {
        "__future__",
        "os",
        "re",
        "subprocess",
        "sys",
        "tomllib",
        "collections",
        "dataclasses",
        "enum",
        "pathlib",
    }
    ran = subprocess.run(
        [str(BIN / "python"), "-I", "-c", f"exec(open({str(sizes.__file__)!r}).read())"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr


@pytest.mark.skipif(
    not hasattr(os, "sched_getaffinity"),
    reason="os.sched_getaffinity is Linux only: a Mac cannot hold a process to one processor",
)
def test_a_caller_held_to_one_processor_counts_the_same_sizes_as_one_that_is_not(tmp_path):
    """The sizes are the whole machine's: a shell, `jbus.service` and a CI container count the
    same slots whatever CPUs or quota they are given. The test runs on the real /proc."""
    env = {key: value for key, value in os.environ.items() if key not in ("PROC", "TEST_SLOTS")}
    env |= {"XDG_CONFIG_HOME": str(tmp_path / "config"), "JBUS_CONFIG_DIR": str(tmp_path)}

    def counted(cpus=None):
        ran = subprocess.run(
            [str(BIN / "jgauge"), "sizes"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            preexec_fn=(lambda: os.sched_setaffinity(0, cpus)) if cpus else None,
        )
        return ran.stdout.splitlines()[:3]

    whole = counted()
    assert counted({min(os.sched_getaffinity(0))}) == whole
    assert whole[0].split()[1] == str(sizes.derive(Name.TEST_SLOTS, Machine.here()))
