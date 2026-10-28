# Machine-sized limits: three derived counts, everything else stays put

> This page is the design record of the change that derived the machine's sizes.
> It is written for jstack's developers and covers the owner's machines.
> It does not describe your machine.
> [The limits and how to change them](../jgauge/change-a-limit.md) describes each limit for any install, and how to change it.

## Problem

The owner set jstack's limits by hand for adalaide (12 cores), then adjusted them a little for yelena (24 cores, 62 GB).
The owner wants three things:

- defaults derived from what the code can measure
- machine values only in local config
- one inventory of the limits, `features/jgauge/docs/limits.md`

Most of the numbers are not machine sizes at all.
Room's six lines in `features/jgauge/src/jgauge/room.sh` are `LOAD=200`, `CPU=40`, `MEMORY=6`, `PRESSURE=10`, `CUSHION=100` and `SLOTS=85`.
`LOAD` is a share of the cores, `CPU` and `PRESSURE` are shares of time, `MEMORY` is a floor, and `CUSHION` and `SLOTS` are percents.
Each means the same on any machine.
The Makefile already sizes `TEST_WORKERS` from the run's own processors.
Only three numbers are sizes of the machine:

- the full test slots (`slot.DEFAULT = 3`, with `TEST_SLOTS=4` in the owner's zshenv)
- the short test slots (`SHORT_SLOTS = 3`)
- the crew cap (`MAX_RUNNING = 24`, and `max_running = 24` in `~/.config/jbus/config.toml`)

The design must meet these constraints:

- room.sh stays a script that `jgauge room`, the jbus view and the tests run as `sh room.sh`.
  It stays the only implementation of the room check.
- The Makefile runs in CI containers with `make`, `sh` and `uv`, and no jstack venv.
- `--slots` and `TEST_SLOTS` stay overrides.
- `jbus.service`, which reads no shell profile, and every desk or agent shell must get the same slot count.
  Otherwise callers lock different ranges of `test-slot.<n>.lock`.
- The live key `max_running` in jbus's config keeps working.
- jstack refuses a bad local value and prints one line.
  For a fact it cannot read, it uses a safe value.
- The worker-budget test in `testing/tests/test_check_command.py` asserts `slot.DEFAULT == 3` and assumes 3 runners of quota 4.
  The machine actually has 7 full and 2 fast runners inside infra's slice of 20 CPUs at CPUWeight 50.

## Usage (caller's view)

```
$ jgauge sizes
test_slots   4  derived from 24 cores, 62 GiB
short_slots  3  derived from 24 cores, 62 GiB
max_running 24  ~/.config/jbus/config.toml (derived: 24)
room LOAD=200 CPU=40 MEMORY=6 PRESSURE=10 CUSHION=100 SLOTS=85  features/jgauge/src/jgauge/room.sh
```

To change a machine size, the owner edits one file.
`jgauge` accepts these two keys in it and refuses any other:

```toml
# ~/.config/jstack/machine.toml
test_slots = 5
```

`jgauge test-slot` calls `sizes.resolve` like this, in `features/jgauge/src/jgauge/slot.py`:

```python
def count(asked: str | None) -> int:
    try:
        return sizes.resolve(sizes.Name.TEST_SLOTS, flag=asked).value
    except sizes.Refused as error:
        raise BadCount(str(error)) from error
```

`jbus.load`, in `features/jbus/src/jbus/__init__.py`, calls `sizes.resolve` like this and still reads the live key `max_running`:

```python
cap = sizes.resolve(sizes.Name.MAX_RUNNING, written=raw.get("max_running"), written_in=path)
```

The test that replaces the worker budget runs `make` and checks the derived slot count against the Makefile's worker count:

```python
@pytest.mark.parametrize("cores", [1, 2, 4, 8, 12, 24, 64])
def test_every_full_slot_at_once_runs_at_most_one_desk_worker_a_processor(cores):
    slots = sizes.derive(sizes.Name.TEST_SLOTS, sizes.Machine(cores=cores, memory_gib=256))
    assert workers(f"CORES={cores}") == sizes.desk_workers(cores)
    assert slots * sizes.desk_workers(cores) <= cores
```

## Shape

`features/jgauge/src/jgauge/sizes.py` holds the three sizes and nothing else.
Its types are `Name` (a `StrEnum` of the three keys), `Machine(cores, memory_gib, fell_back)` and `Limit(name, value, came_from, where, derived)`.
Only `resolve` creates a `Limit`, so every value a caller holds is 1 or more.
`sizes.py` caches nothing and writes nothing.
So a count that you edit by hand applies the next time a caller takes a slot.
Two callers that read at the same time cannot change each other's result.

The derivation reads only whole-machine facts: the `cpuN` lines of `$PROC/stat` and `MemTotal` of `$PROC/meminfo`, or on macOS `hw.ncpu` and `hw.memsize` of `sysctl`.
It never reads the caller's cgroup quota, affinity or `nproc`, which differ between `jbus.service`, a `systemd-run` scope, an agent's slice and a CI container on the same machine.
The Makefile does read the quota when it sizes its workers, on purpose.
The Makefile sizes a run's workers to the run, and `sizes.py` sizes a machine's slots to the machine.

| cores | 2 | 8 | 12 | 24 | 64 |
|---|---|---|---|---|---|
| desk workers, `max(2, c // 4)` | 2 | 2 | 3 | 6 | 16 |
| `test_slots = max(1, min(c // workers, GiB // 4))` | 1 | 4 | 4 | 4 | 4 |
| `short_slots = clamp(c // 8, 2, 8)` | 2 | 2 | 2 | 3 | 8 |
| `max_running = max(1, min(c, GiB // 2))` | 2 | 8 | 12 | 24 | 64 |

The table assumes 4, 16, 32, 62 and 128 GiB of memory for the five core counts.
On yelena, four full slots of six workers each make 24 workers.
At the measured 0.86 of a core per worker, they keep about 21 cores busy.
In the measurements, four suites at once held CPU pressure at 17 to 29, under room's line of 40, at 2.0 suites a minute.
Five suites at once gave 10% more throughput at CPU pressure 30.
Six took 195 s a suite at CPU pressure 55, and one test failed intermittently.
The count is 4 on most machines of 8 cores or more, because the desk share is a quarter of the cores.
On 10, 11 or 15 cores it is 5, because dividing the cores by the desk workers (2, 2 and 3) rounds down to 5.
On any machine, all the full slots at once run at most one desk worker per processor.
The crew cap derives the same 24 that the owner set by hand, so jstack's source contains no number specific to yelena.

Each key is set in one local file.
`test_slots` and `short_slots` go in `~/.config/jstack/machine.toml`, beside jsettings' `config.toml` and not in it.
That way `config.toml` keeps only its own keys, and no machine size goes in it.
`max_running` stays in jbus's config, where it is today.
jbus passes the raw value to `resolve`, which checks it as it checks any count.
The order is `--slots`, then `TEST_SLOTS` (both for the full lane only), then the key's local file, then the derived value.
`jgauge sizes` prints the derived value beside an override.
It also prints a `note:` when `TEST_SLOTS` is set, since `jbus.service` does not see that variable.

Shell callers get nothing new.
room.sh keeps its six lines, and the Makefile still sets workers as a share of the processors and still reads the CPU quota.
One value is kept in both Python and the Makefile: `DESK_SHARE = 4`, which the test above checks against the Makefile's `1 / 4` by running `make`.
`sample.load_line()` becomes `sample.room_line(name)`, which parses room.sh's `NAME=` lines, and `jgauge sizes` uses it too.
`sample.PRESSURE_LINE = 10.0` stays.
It is the report's own threshold for "CPU pressure is low", compared with `cpu_some_avg60`, and not a copy of room's memory `PRESSURE`.

`features/jgauge/docs/limits.md` is hand-written, with one row per limit.
Each row gives where the limit is set, its value, who set it for which machine, what it protects, and the measurement behind it.
A test checks that each row that names a constant, a room.sh line or a `sizes.Name` gives the value the code has now.

The public names are `resolve`, `Name`, `Refused`, `every` for `jgauge sizes`, and `derive`, `desk_workers` and `Machine` for tests.
Inside the module are the `/proc` reads with their fallbacks, the precedence, the TOML file, the validation and the derivation.

## Synthesis decision

The design comparison (the `arena` playbook) ran in two rounds.
In each round, two runners answered one prompt and one judge scored them.
Round one gave two candidates with the same design.
Both were a stdlib registry of every number, and room.sh and the Makefile read it through `python3 -I limits.py` and `eval`.
The registry included room's six thresholds.
A generated table documented the registry.
My scores and the judge's agreed.
We took candidate b as the starting point for its whole-machine slot count.
We took candidate a as the starting point for keeping live callers working.
Both did more than the task needed.
That design starts Python on every room check, needs Python on PATH for room.sh, and moves six numbers that are not sizes.
My own alternative for step 7 kept room.sh and the Makefile as they are and derived only the three sizes.
It scored higher on blast radius (how much else a change can break) and on size.
The task as written had left that design out, so round two ran with that design in the task.
Both round-two runners took that design.
Round-two a derived 3 full slots on yelena from a budget of three quarters of the cores.
Round-two b derived 4, the measured knee, and named every test the change breaks.
The judge and I picked round-two b, took two parts from round-two a, and dropped one part of round-two b:

- We took two parts from round-two a: `Limit.derived`, so that `jgauge sizes` shows the derived value beside an override, and the doc test that checks each row's value against its source.
- We cut one part of round-two b: folding `sample.PRESSURE_LINE` into room's `CPU` line, since it is a different line with a different meaning.

## Tradeoffs accepted

- We accept `max_running` in a different file from the slot counts in exchange for no migration of a live key and one file per key.
- We accept that `TEST_SLOTS` still overrides the file, in exchange for keeping a one-run override, with a `note:` from `jgauge sizes` for a profile that sets it.
- We accept one value, `DESK_SHARE`, kept by hand in both Python and the Makefile, in exchange for a Makefile that needs no Python in CI.
- We accept leaving the runners out of the slot formula.
  infra's slice caps them, and at CPUWeight 50 it yields CPU to the desk, and room's CPU pressure line catches any overload that is left.
- We accept recording the suite's measured costs (0.86 of a core a worker, 1.1 GB, 45,000 /tmp files) in code comments as the reason for the numbers, and we measure them again when the suite changes.
- We accept reading two `/proc` files on each `resolve` in exchange for no cache that goes stale.

## Alternatives considered

- A registry of every number, which the shell callers run through Python (round one): it makes two shell callers that need no Python start Python, and it moves six numbers that are not sizes.
- All three keys in `machine.toml`, with jbus's `max_running` as an alias: two places for one value need a rule for when they differ.
- A slot count written by jbus into a state file that every caller reads: it adds a second writer of shared state, and a desk caller breaks where jbus is not running.
- Slots derived from the caller's cgroup quota: `jbus.service`, a scope and a container on one machine would count differently.
- Three slots, from a budget of three quarters of the cores (round-two a): it gives less throughput than four slots, the measured knee of the curve, and the owner did not choose it.
  The load run shows whether four slots still work with crews and runners running beside them.

## Open questions and risks

- Do four slots still work with 24 crews and the runners busy at once?
  This task's load run tests that.
  To go back to three slots, set `test_slots = 3` in the local file.
- Should `max_running` have a ceiling that does not come from the machine?
  On 64 cores the formula gives 64 crews, and only `jgauge room` would limit how many launch.

## Next implementation step

Implement `Machine.here`, `derive`, `count` and `resolve` in `features/jgauge/src/jgauge/sizes.py`, with tests over a fake `PROC` tree.
Then switch `slot.count`, `slot.short` and `jbus.load` to `resolve`.
