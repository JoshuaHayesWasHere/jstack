# Machine-sized limits: three derived counts, everything else stays put

## Problem

jstack's limits were sized by hand for adalaide (12 cores) and nudged for yelena (24 cores, 62 GB), and the owner wants machine-neutral defaults derived from what the code can measure, machine values only in local config, and one inventory, `docs/limits.md`.
Most of the numbers are not machine sizes at all.
Room's six lines in `src/jgauge/room.sh` (`LOAD=200`, `CPU=40`, `MEMORY=6`, `PRESSURE=10`, `CUSHION=100`, `SLOTS=85`) are a share of the cores, pressure shares of time, a floor and percents, which mean the same on any machine.
The Makefile already sizes `TEST_WORKERS` from the run's own processors.
Only three numbers are sizes of the machine: the full test slots (`slot.DEFAULT = 3`, with `TEST_SLOTS=4` in the owner's zshenv), the short test slots (`SHORT_SLOTS = 3`), and the crew cap (`MAX_RUNNING = 24`, and `max_running = 24` in `~/.config/jbus/config.toml`).

The constraints that shape the answer:

- room.sh stays `sh room.sh`, run by `jgauge room`, by the jbus view and by the tests, and it stays the one copy of its logic.
- The Makefile runs in CI containers with `make`, `sh` and `uv`, and no jstack venv.
- `--slots` and `TEST_SLOTS` stay overrides.
- `jbus.service` (no shell profile) and every desk or agent shell reach the same slot count, or callers lock different ranges of `test-slot.<n>.lock`.
- The live key `max_running` in jbus's config keeps working.
- A bad local value refuses in one line, and a fact that cannot be read falls back to a safe value.
- The worker-budget test in `tests/test_check_command.py` pins `slot.DEFAULT == 3` against 3 runners of quota 4, while the machine has 7 full and 2 fast runners inside infra's slice of 20 CPUs at CPUWeight 50.

## Usage (caller's view)

```
$ jgauge limits
test_slots   4  derived from 24 cores, 62 GiB
short_slots  3  derived from 24 cores, 62 GiB
max_running 24  ~/.config/jbus/config.toml (derived: 24)
room LOAD=200 CPU=40 MEMORY=6 PRESSURE=10 CUSHION=100 SLOTS=85  src/jgauge/room.sh
```

To change a machine size, the owner edits one file, which takes these two keys and refuses any other:

```toml
# ~/.config/jstack/machine.toml
test_slots = 5
```

`jgauge test-slot` (`src/jgauge/slot.py`):

```python
def count(asked: str | None) -> int:
    try:
        return limits.resolve(limits.Name.TEST_SLOTS, flag=asked).value
    except limits.Refused as error:
        raise BadCount(str(error)) from error
```

`jbus.load` (`src/jbus/__init__.py`), which keeps the live key:

```python
cap = limits.resolve(limits.Name.MAX_RUNNING, written=raw.get("max_running"), written_in=path)
```

The test that replaces the worker budget runs `make` and holds the derivation to it:

```python
@pytest.mark.parametrize("cores", [1, 2, 4, 8, 12, 24, 64])
def test_every_full_slot_at_once_runs_at_most_one_desk_worker_a_processor(cores):
    slots = limits.derive(limits.Name.TEST_SLOTS, limits.Machine(cores=cores, memory_gib=256))
    assert workers(f"CORES={cores}") == limits.desk_workers(cores)
    assert slots * limits.desk_workers(cores) <= cores
```

## Shape

`src/jgauge/limits.py` holds the three sizes and nothing else.
Its types are `Name` (a `StrEnum` of the three keys), `Machine(cores, memory_gib, fell_back)` and `Limit(name, value, came_from, where, derived)`.
`resolve` is the only maker of a `Limit`, so every value a caller holds is 1 or more.
Nothing is cached and nothing is written, so a count edited by hand applies to the next take, and two readers at once change nothing.

A default reads whole-machine facts only: the `cpuN` lines of `$PROC/stat` and `MemTotal` of `$PROC/meminfo`.
It never reads the caller's cgroup quota, affinity or `nproc`, which differ between `jbus.service`, a `systemd-run` scope, an agent's slice and a CI container on the same machine.
The Makefile's workers do read the quota, on purpose: a run's workers are sized to the run, and a machine's slots to the machine.

| cores | 2 | 8 | 12 | 24 | 64 |
|---|---|---|---|---|---|
| desk workers, `max(2, c // 4)` | 2 | 2 | 3 | 6 | 16 |
| `test_slots = max(1, min(c // workers, GiB // 4))` | 1 | 4 | 4 | 4 | 4 |
| `short_slots = clamp(c // 8, 2, 8)` | 2 | 2 | 2 | 3 | 8 |
| `max_running = max(1, min(c, GiB // 2))` | 2 | 8 | 12 | 24 | 64 |

The memory column is 4, 16, 32, 62 and 128 GiB.
Four full slots of six workers on yelena is 24 workers at the measured 0.86 of a core, about 21 cores busy.
Measured at four suites at once that held CPU pressure at 17 to 29, under room's line of 40, at 2.0 suites a minute; five gained 10% at pressure 30, and six took 195 s a suite at pressure 55 and flaked a test.
The count is 4 on most machines of 8 cores or more, and 5 on 10, 11 or 15 cores, because the desk share is a quarter: the slots fill the machine once, whatever its size.
The crew cap derives the 24 the owner set by hand, so no yelena number lives in jstack.

Each key has one local home.
`test_slots` and `short_slots` live in `~/.config/jstack/machine.toml`, beside jsettings' `config.toml` and not in it, so that file's strict three keys stay who the user is and the time zone.
`max_running` stays in jbus's config, where it lives today: jbus hands the raw value to `resolve`, which checks it as it checks any count.
The order is `--slots`, then `TEST_SLOTS` (both for the full lane only), then the local home, then the derivation.
`jgauge limits` prints the derived value beside an override, and a `note:` when `TEST_SLOTS` is set, since `jbus.service` does not see it.

Shell callers get nothing new: room.sh keeps its six lines and the Makefile its share and quota reading.
The one copy across the language line is `DESK_SHARE = 4`, which the test above holds to the Makefile's `1 / 4` by running `make`.
`sample.load_line()` becomes `sample.room_line(name)`, the parser of room.sh's `NAME=` lines, which `jgauge limits` uses too.
`sample.PRESSURE_LINE = 10.0` stays: it is the report's own line for "CPU pressure is low", compared with `cpu_some_avg60`, and not a copy of room's memory `PRESSURE`.

`docs/limits.md` is hand-written, one row per limit, with where it is set, its value, who set it for which machine, what it protects and the measurement it rests on.
A test keeps it true: each row that names a constant, a room.sh line or a `limits.Name` gives the value the code has now.

The public surface is `resolve`, `Name`, `Refused`, `every` for the one command, and `derive`, `desk_workers` and `Machine` for tests.
Behind it are the `/proc` reads with their fallbacks, the precedence, the TOML file, the validation and the derivation.

## Synthesis decision

The arena ran twice, each round with two runners on one prompt and one judge.
Round one gave two candidates of one shape: a stdlib registry of every number (room's six included) that room.sh and the Makefile run through `python3 -I limits.py` and `eval`, with a generated doc table.
My scores and the judge's agreed: b was the base for its whole-machine slot count, a for keeping live callers working, and both were bigger than the task.
That shape costs a Python start on every room look, a Python on PATH for room.sh, and six numbers moved that are not sizes.
My own whole-shape alternative for step 7, keeping room.sh and the Makefile as they are and deriving only the three sizes, scored higher on blast radius and size, so the frame had missed a shape and round two ran with it in the task.
Both round-two runners took that shape.
Round-two a derived 3 full slots on yelena from a three-quarter budget of the cores, and b derived 4, the measured knee, and named every test the change breaks.
The judge and I picked round-two b, with two grafts and one cut:

- Grafts from round-two a: `Limit.derived`, so `jgauge limits` shows the derived value beside an override, and the doc test that checks each row's value against its source.
- Rejected from round-two b: folding `sample.PRESSURE_LINE` into room's `CPU` line, since it is a different line with a different meaning.

## Tradeoffs accepted

- We accept `max_running` in a different file from the slot counts in exchange for no migration of a live key and one home per key.
- We accept `TEST_SLOTS` still beating the file in exchange for keeping a one-run override, with a `note:` from `jgauge limits` for a profile that sets it.
- We accept one hand-kept copy, `DESK_SHARE`, across the Python and Makefile line in exchange for a Makefile that needs no Python in CI.
- We accept leaving the runners out of the slot formula: infra's slice bounds them and gives way to the desk at CPUWeight 50, and room's CPU pressure line is the backstop.
- We accept the suite's measured costs (0.86 of a core a worker, 1.1 GB, 45,000 /tmp files) as the reasoning in comments, re-measured when the suite changes.
- We accept reading two `/proc` files on each `resolve` in exchange for no cache that goes stale.

## Alternatives considered

- A registry of every number run by the shell callers through Python (round one): it puts a Python boundary in front of two shell callers that need none and moves six numbers that are not sizes.
- All three keys in `machine.toml` with jbus's `max_running` as an alias: two homes for one value need a rule for when they differ.
- A slot count written by jbus into a state file that every caller reads: a second writer of shared state, and a desk caller that breaks where jbus is not running.
- Slots derived from the caller's cgroup quota: `jbus.service`, a scope and a container on one machine would count differently.
- Three slots, from a budget of three quarters of the cores (round-two a): it leaves the knee for less throughput and was not what the owner chose; the load run decides if four holds with crews and runners beside it.

## Open questions and risks

- Does four hold with 24 crews and the runners busy at once: the load run of this task answers it, and `test_slots = 3` in the local file is the one-line way back.
- Should `max_running` have a ceiling that is not the machine's, given that 64 cores would derive 64 crews and only room's checks would hold them?

## Next implementation step

Implement `Machine.here`, `derive`, `count` and `resolve` in `src/jgauge/limits.py` with tests over a fake `PROC` tree, then switch `slot.count`, `slot.short` and `jbus.load` to `resolve`.
