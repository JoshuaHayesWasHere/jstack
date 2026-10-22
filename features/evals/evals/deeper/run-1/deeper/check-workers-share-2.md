## 1. What a top professional would do
A systems performance engineer (capacity planning, USE method) would first ask what "the edge" is. Load average on Linux counts runnable and uninterruptible (I/O-wait) tasks, so 14–15 on 12 cores may be stall or may be a queue the cores barely notice. They would:
- Define the edge by measured pressure (PSI) and by `make check` wall time.
- Find the worker count at the knee of a measured scaling curve rather than taking `-n 6` as given.
- Have every consumer (`make check`, the three runners, the crews, pbus) draw from one shared budget instead of each sizing itself blind.

## 2. The rawest material
- `sar -q -u -P ALL -f /var/log/sa/sa12` (sysstat's record of 2026-10-12, if `sysstat-collect.timer` was enabled; on Arch it is off by default, and if so that night is gone and must be reproduced): in place of the remembered "14 to 15 for over ten minutes"
- `journalctl --since '2026-10-12 21:20' --until '2026-10-12 22:00'`, plus room's and pbus's own logs for that window (the line `gate pp-doctor: no room for 10 passes`, and what room read when it said wait): in place of the summary that "room said wait"
- `room`'s source, read for the exact signal and threshold it gates on (loadavg? which window? what number?): in place of the belief that it measures "too busy"
- `/proc/pressure/cpu`, `/proc/pressure/io`, `/proc/pressure/memory`, sampled while the 21:35 mix is replayed: in place of load average as the measure of overload
- The diff of #339 and the `check` target in the `Makefile` (where `-n 6` is set, and whether runners and crews invoke `make check` too, nesting 6 workers per caller): in place of "since tests-parallel it runs on six workers"
- `pytest --durations=0 -p no:randomly` output, one serial run: in place of an assumed even split of work across workers

## 3. The methods and tools
- `hyperfine --warmup 1 --runs 5 -L n 1,2,4,6,8,12 'pytest -n {n} -q'`: a scaling curve with run count and spread, to find the knee where another worker stops buying wall time
- `pidstat -u -d -w 1` and `vmstat 1` during a replay: the USE method (utilisation, saturation, errors per resource), to tell CPU queueing from I/O wait (the `D` column, `wa`) from context-switch thrash
- `perf stat -e task-clock,context-switches,cpu-migrations -- make check`: whether the extra workers buy CPU work or only scheduling
- `cat /proc/pressure/cpu` (`some avg10`) polled in a loop, or `below`/`atop` if installed (`pacman -S atop`): PSI as the edge signal instead of loadavg
- A shared token budget: GNU make's jobserver (`make -j12`, with `pytest -n auto` replaced by a jobserver-aware count) or a `flock`-guarded slot counter that room hands out. One budget across `make check`, the runners, crews and pbus
- `systemd-run --user --scope -p CPUWeight=20 make check`: let background test load yield to launches without forbidding it
- A scripted replay of the 21:35 mix (three runners + `make check` + one crew run, all at once): reproduce before fixing, since the original data is likely gone

## 4. What outside the agent shows it is right
- A replay of the 2026-10-12 21:35 mix, run three times, with the numbers printed:
  - `/proc/pressure/cpu some avg10` stays under 10%.
  - room never says wait for longer than 2 minutes.
  - pbus launches `pp-doctor`'s 10 passes within 2 minutes of asking.
  - Mean CPU utilisation across the 12 cores (from `sar`/`pidstat`) stays at or above 85%.

  This is "as hard as it can without going over the edge" made measurable. A performance engineer would call that target reasonable.
- `hyperfine` shows `make check` wall time alone on an idle machine no worse than today's `-n 6` (within the measured spread), and the chosen worker count sits at the knee of the curve.
- The user watches the next real evening of parallel crews and sees no `no room` gate in pbus's log.

## Rewritten prompt
```
"I want to push my machine as hard as I can without going over the edge" and "run the test in
parallel". Since #339, `make check` runs pytest on six workers; on 2026-10-12 at 21:35 ET three
runners plus the crews' runs held the one-minute load at 14–15 on 12 cores for over ten minutes,
room said wait, and pbus launched nothing (`gate pp-doctor: no room for 10 passes`). Keep tests
parallel and the machine busy, and stop that stall.

Start from the raw record, not the remembered numbers:
- `sar -q -u -P ALL -f /var/log/sa/sa12` if sysstat was collecting; say so if it wasn't.
- `journalctl` and room's and pbus's logs for 21:20–22:00 that night.
- room's source: what it reads and the threshold it waits on.
- The #339 diff and the Makefile `check` target: does anything nest `make check` inside a
  runner or crew, multiplying the six workers?
- `/proc/pressure/{cpu,io,memory}`.
- One serial `pytest --durations=0`.

Work as a performance engineer would:
- Replay the 21:35 mix (three runners + `make check` + a crew run) under `pidstat -u -d -w 1`
  and `vmstat 1` to see whether the load is CPU queueing, I/O wait or switching.
- Measure a scaling curve with
  `hyperfine --warmup 1 --runs 5 -L n 1,2,4,6,8,12 'pytest -n {n} -q'` and pick the worker
  count at its knee.
- If the replay shows room is gating on loadavg where PSI would be the truer edge, change
  room's signal to `/proc/pressure/cpu some avg10`.
- Have `make check`, the runners, the crews and pbus draw from one shared CPU budget (the make
  jobserver or a slot counter room hands out) rather than each sizing itself.
- Use `systemd-run --scope -p CPUWeight=` where background tests should yield to launches.

Done when the replay, run three times with numbers printed, shows:
- PSI cpu `some avg10` under 10%
- mean CPU across the 12 cores at or above 85%
- room never waiting longer than 2 minutes
- pbus launching pp-doctor's 10 passes within 2 minutes of asking
- `make check` alone no slower than today's `-n 6` within the measured spread

This target is ambitious but reasonable. The final check is mine: an evening of real crews
with no `no room` gate in pbus's log.
```
