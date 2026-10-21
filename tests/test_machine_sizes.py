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


@pytest.mark.parametrize(
    ("cores", "gib", "full", "short", "crews"),
    [
        (1, 2, 1, 2, 1),
        (2, 4, 1, 2, 2),
        (8, 16, 4, 2, 8),
        (12, 32, 4, 2, 12),
        (24, 62, 4, 3, 24),
        (64, 128, 4, 8, 64),
        (24, 8, 2, 3, 4),
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


def test_the_flag_wins_then_the_variable_then_the_file_then_the_machine(machine):
    assert sizes.resolve(Name.TEST_SLOTS).came_from is From.DERIVED
    assert sizes.resolve(Name.TEST_SLOTS).value == 4
    written = write_machine(machine, "test_slots = 2\nshort_slots = 5\n")
    assert sizes.resolve(Name.TEST_SLOTS) == sizes.Limit(
        Name.TEST_SLOTS, 2, From.FILE, str(written), 4
    )
    assert sizes.resolve(Name.SHORT_SLOTS).value == 5
    os.environ["TEST_SLOTS"] = "3"
    assert (
        sizes.resolve(Name.TEST_SLOTS).line() == "test_slots     3  env TEST_SLOTS=3 (derived: 4)"
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


def test_jgauge_limits_prints_each_size_where_it_came_from_and_rooms_lines(machine, capsys):
    jbus = machine / "jbus"
    jbus.mkdir()
    (jbus / "config.toml").write_text("max_running = 6\n")
    os.environ["JBUS_CONFIG_DIR"] = str(jbus)
    os.environ["TEST_SLOTS"] = "3"
    try:
        assert cli.main(["sizes"]) == 0
    finally:
        del os.environ["JBUS_CONFIG_DIR"]
    out = capsys.readouterr().out.splitlines()
    assert out[:3] == [
        "test_slots     3  env TEST_SLOTS=3 (derived: 4)",
        "short_slots    2  derived from 8 cores, 16 GiB",
        f"max_running    6  file {jbus / 'config.toml'} (derived: 8)",
    ]
    assert out[3].startswith("room LOAD=200 CPU=40 MEMORY=6 PRESSURE=10 CUSHION=90 SLOTS=85 ")
    assert out[4] == (
        "note: TEST_SLOTS=3 is set here and jbus.service does not see it:"
        f" set test_slots in {machine / 'config' / 'jstack' / 'machine.toml'}"
    )


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


def test_a_caller_held_to_one_processor_counts_the_same_sizes_as_one_that_is_not(tmp_path):
    """The sizes are the whole machine's: a shell, `jbus.service` and a CI container count the
    same slots whatever CPUs or quota they are given. Run on the real /proc."""
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
