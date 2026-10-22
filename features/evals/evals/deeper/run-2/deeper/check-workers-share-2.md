## 1. What a top professional would do
A capacity and performance engineer would not pick a worker count by feel, and would not budget workers one run at a time. They would:
- Measure where throughput stops rising as `make check` workers go from 1 to 12. That is the knee, and past it extra workers only add contention.
- Size the whole machine's budget against that knee: runners × workers, plus the crews' own runs, against 12 cores.
- Define "the edge" with a real saturation signal, CPU and memory pressure stall, rather than one-minute load. Load also counts tasks blocked on I/O, so it can overstate CPU saturation.

## 2. The rawest material
- `cat /proc/pressure/cpu /proc/pressure/memory /proc/pressure/io`, sampled each second during a run: in place of "the one-minute load was 14 to 15".
- `/var/log/sa/sa12` (`sar -u -q -r -f /var/log/sa/sa12 -s 21:00:00 -e 22:15:00`, if sysstat was collecting) and `journalctl --since "2026-10-12 21:20" --until "2026-10-12 22:10"`: in place of the remembered account of the evening of 2026-10-12.
- `room`'s own source and its log for that window, showing which signal and threshold made it say wait: in place of "room said wait".
- pbus's log line `gate pp-doctor: no room for 10 passes`, with what it asked `room` for: in place of the summary of it.
- The `check` target in `Makefile` and the diff of #339 (`git show` on its merge commit), showing exactly how `-n 6` is passed: in place of "six workers since tests-parallel".
- `pytest -n 6 --durations=0` output from one `make check`: in place of an assumption that the tests are CPU-bound. A suite dominated by sleep or I/O has a different knee.
- `nproc` and `lscpu`, giving the physical core count against the 12 logical CPUs: in place of "12 cores".

## 3. The methods and tools
- `hyperfine --runs 5 -L n 1,2,3,4,6,8,12 'pytest -q -n {n}'`: a scan of worker counts with a run count and spread, to find the knee rather than guess it.
- `perf stat -e task-clock,context-switches,cpu-migrations -- make check`: whether added workers buy CPU work or only switching. Install with `pacman -S perf` if missing.
- `vmstat 1` and `pidstat -u -w 1` (sysstat; `pacman -S sysstat hyperfine` if missing): per-second run queue, steal from runners and crews, and memory headroom, recorded during a run.
- A replay of 2026-10-12, run with PSI sampled throughout: three concurrent `make check` runs plus a stand-in crew load. This is a reproduction before a fix, not a fix tested against nothing.
- `systemd-run --user --scope -p CPUWeight=50 make check` for test runs, if the answer is to bound them: a weight so tests yield to crews and pbus, rather than a fixed cap that idles the machine.

## 4. What outside the agent shows it is right
- The hyperfine table:
  - Wall time of `make check` at the chosen worker count is within 10% of the fastest count measured, with spread stated.
  - Running three at once finishes within 1.3× one alone. That is ambitious, but reasonable once workers sit at the knee rather than past it.
- A replay of 2026-10-12's load:
  - `/proc/pressure/cpu` "some avg10" stays under the threshold `room` is set to, and memory pressure stays near 0.
  - `room` says go.
  - pbus launches `gate pp-doctor`'s 10 passes, and its own log says so.
- The user's own check: the next evening of three runners and crews passes without a "no room" line in pbus's log.

## Rewritten prompt
> "I want to push my machine as hard as I can without going over the edge" and "run the test in
> parallel". Since #339, `make check` runs pytest on six workers. On 2026-10-12 at 21:35 ET, three
> runners plus the crews' runs held the one-minute load at 14 to 15 on 12 CPUs for over ten minutes.
> `room` said wait, and pbus logged `gate pp-doctor: no room for 10 passes`. Set `make check`'s
> parallelism so the machine is used to the full and never refuses work.
>
> Start from the raw record, not the remembered numbers:
> - the `check` target and #339's diff
> - `nproc` and `lscpu`
> - `sar -u -q -r -f /var/log/sa/sa12` and `journalctl` for 21:20 to 22:10 that evening
> - `room`'s source and log, to see which signal and threshold refused
> - pbus's log line
> - `pytest -n 6 --durations=0`, to see whether the suite is CPU-bound
>
> Then measure:
> - `hyperfine --runs 5 -L n 1,2,3,4,6,8,12 'pytest -q -n {n}'`, to find the knee
> - `perf stat -e task-clock,context-switches,cpu-migrations -- make check`
> - a replay of three concurrent `make check` runs plus a crew load, with `/proc/pressure/{cpu,memory,io}`,
>   `vmstat 1` and `pidstat -u -w 1` recorded throughout
>
> Install `perf`, `sysstat` and `hyperfine` with pacman if they are missing. Define "the edge" by
> pressure stall, not load average. Budget workers against the whole machine, not one run. If tests
> must yield, use `systemd-run --user --scope -p CPUWeight=` rather than a fixed cap.
>
> It is done when:
> - the hyperfine table shows the chosen worker count within 10% of the fastest, with spread;
> - three concurrent runs finish within 1.3× one alone;
> - in the replay, CPU "some avg10" stays under `room`'s threshold, `room` says go, and pbus's own log
>   shows `gate pp-doctor` launching its 10 passes.
