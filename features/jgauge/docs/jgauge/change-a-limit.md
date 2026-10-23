# The limits and how to change them

jstack caps how much work runs at once, so that many threads and test runs together do not overload the machine or use up your Claude plan.
Three of the caps are sizes of the machine, which jstack works out from its processors and memory.
One more, `headroom`, says when a launch counts your plan as full.
You can set each of these four.
The other caps are fixed in jstack, as shares and floors that mean the same on any machine.

## See the limits on this machine

Run `jgauge sizes`.
It prints `test_slots`, `short_slots` and `max_running`, the value each caller gets and where it came from, then room's six lines.

## Change the number of test slots

1. Open `~/.config/jstack/machine.toml`, and make it if it is not there.
2. Set `test_slots` for the full lane, `short_slots` for the short lane, or both:

   ```toml
   test_slots = 3
   short_slots = 2
   ```

3. Run `jgauge sizes`, and check that each line says it came from `machine.toml`.

To use another count for one command alone, run `jgauge test-slot --slots <n> -- <command>`, or set `TEST_SLOTS` for it.
`TEST_SLOTS` in a shell profile is not seen by `jbus.service`, and `jgauge sizes` says so.

## Change how many crews run at once

1. Open `~/.config/jbus/config.toml`.
2. Set `max_running` at the top level, such as `max_running = 6`.
3. Run `jgauge sizes`, and check that the `max_running` line says it came from jbus's config.

## Change when your plan counts as full

1. Open `~/.config/jstack/config.toml`.
2. Set `headroom` to the share of a usage window, in percent, at which a new launch counts an account as full, such as `headroom = 80`.

A thread already running moves to another account only at a real cap, 100%, whatever `headroom` says ([jroles](../../../jroles/docs/jroles.md#the-ledger)).

## The limits you can set

| Limit | Default | Set it in | Read by |
|---|---|---|---|
| `test_slots`, how many whole suites run at once, machine-wide | One slot for each desk run's workers, a quarter of the processors, and at most one for each 4 GiB: 4 on most machines of 8 cores or more | `~/.config/jstack/machine.toml`; `--slots` and `TEST_SLOTS` come before it | `jgauge test-slot`, `jbus poll` |
| `short_slots`, how many targeted runs and reviewers' proofs run at once | One for each 8 processors, from 2 to 8 | `~/.config/jstack/machine.toml` | `jgauge test-slot --short`, `jbus poll` |
| `max_running`, how many crewmates are out at once, across every project | One for each processor, while each has 2 GiB | `~/.config/jbus/config.toml` | `jbus` |
| `headroom`, the share of a usage window at which a launch counts an account as full | `90` | `~/.config/jstack/config.toml` | `jroles`, `jbus`, `jgauge room` |
| `room_passes`, how many passes a row waits for room before its gate | `10` | `~/.config/jbus/config.toml` | `jbus` |

`jgauge` derives the three sizes from the whole machine, its processors in `/proc/stat` and its `MemTotal`, and never from a caller's own CPU quota, so that `jbus.service` and every shell count the same slots.
A value that is not a whole number of 1 or more is refused with one line.
[Configuration](../../../jinstall/docs/configuration.md#the-machines-sizes) has every key of the three files.

## The limits that are fixed

`jgauge room` waits while any of these holds, and you cannot set them:

| Line | Value |
|---|---|
| The one-minute load, a backstop | At or over 200% of the cores (`LOAD=200`) |
| CPU pressure, `some avg60` | At or over 40 (`CPU=40`) |
| Memory available | Under 6 GB (`MEMORY=6`) |
| Memory pressure, `some avg60` | At or over 10 (`PRESSURE=10`) |
| File slots of `/tmp` used | Over 85% (`SLOTS=85`) |

They are in `features/jgauge/src/jgauge/room.sh`, the one copy of the room check.
A command in the short lane is stopped after 120 seconds (`SHORT_LIMIT_SECONDS`).

## Where the defaults come from

The defaults were measured on one machine, a desk of 24 processors and 62 GiB.
[Limits](../limits.md) records those measurements, every number that caps work and why each has its value.
[Machine-sized limits](../design/limits.md) is the design record of the change that derived the three sizes.
Neither page describes your machine.
