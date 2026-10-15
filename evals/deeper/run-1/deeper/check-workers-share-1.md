## 1. What a top professional would do
A capacity and performance engineer would refuse to let a one-minute load average decide anything. Load counts tasks waiting on I/O as well as on CPU, and it lags by a minute. They would measure where the edge actually is: how throughput and pressure change as pytest workers go from 1 to 12, with the other runners present. Then they would set both the worker count and `room`'s admission rule from that curve, using a pressure signal (PSI) in place of load.

## 2. The rawest material
- `/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io` (`some`/`full`, avg10/avg60), sampled each second during a `make check`: in place of "the one-minute load was 14 to 15"
- `sar -q -u -r -B -f /var/log/sa/sa12` for 21:00–22:00 ET on 2026-10-12, if sysstat was collecting, and `journalctl --since '2026-10-12 21:20' --until '2026-10-12 22:00' -k -u systemd-oomd`: in place of the remembered account of that evening
- `room`'s own source (the script `room` runs, e.g. `bin/room`) and the exact threshold it compares against: in place of "room said wait"
- pbus's log line for `gate pp-doctor: no room for 10 passes` and the pbus code that asks `room` how many passes fit: in place of the quoted message alone
- `pytest -n 6 --durations=0 -q` output and the `make check` recipe in the `Makefile` from #339: in place of "it runs on six workers"
- `pidstat -u -r -d -h 1` during three concurrent `make check` runs plus one crew run: in place of the load figure as the only view of who used the machine

## 3. The methods and tools
- `hyperfine -w 1 -r 5 -P n 1 12 'pytest -n {n} -q'` (`pacman -S hyperfine` if missing): a scaling curve with run count and spread, to find the knee where more workers stop buying wall time
- `while sleep 1; do date +%s; cat /proc/pressure/{cpu,memory,io}; done > psi.log` alongside each hyperfine point: the pressure cost of each worker count, so "the edge" becomes a measured PSI value instead of a guess
- `pidstat -u -r -d -h 1` and `perf stat -a -e task-clock,context-switches,cpu-migrations -- sleep 60` during the contended run: attribute the CPU time to runners vs crews vs xdist workers, and check whether the time is CPU or waiting
- `pytest --durations=50`: find the few slow tests that set the wall time, so the worker count is not covering for a long tail
- `sar` (`pacman -S sysstat && systemctl enable --now sysstat`): keep a history so the next evening like 2026-10-12 is on record
- `systemd-run --user --scope -p CPUWeight=` (or one shared token pool, like make's jobserver, across `make check` and crews): one budget for the whole machine instead of each runner picking its own count; set only from the curve above

## 4. What outside the agent shows it is right
- A replay of the 2026-10-12 shape (three `make check` runners plus one crew run), measured by `/proc/pressure/cpu` and pbus's own log: `room` admits, and pbus launches `gate pp-doctor` with no "no room" refusal over 10 minutes. This is reasonable to ask: a 12-core machine at load 15 is usually not CPU-bound
- hyperfine's numbers: a solo `make check` is no slower than its six-worker time today, and under the three-runner replay each run's mean stays within 1.2× its solo mean, with spread reported
- PSI cpu `some avg60` stays under the threshold the curve names, memory `full` stays at 0, and the journal shows no `systemd-oomd` kill in the window
- the user's own check: the desktop stays responsive throughout the replay

## Rewritten prompt
```
"I want to push my machine as hard as I can without going over the edge" and "run the test in
parallel". Since #339, `make check` runs pytest on six workers. On 2026-10-12 at 21:35 ET, three
runners plus crew runs held the one-minute load at 14–15 on 12 cores for over ten minutes. `room`
said wait, and pbus could launch nothing (`gate pp-doctor: no room for 10 passes`).

Find where the edge of this machine actually is, and set `make check`'s worker count and `room`'s
admission rule from that measurement, not from load average.

Start from: `/proc/pressure/{cpu,memory,io}`, `sar -q -u -r -f /var/log/sa/sa12` and
`journalctl -k -u systemd-oomd` for 2026-10-12 21:20–22:00, `room`'s source and its threshold,
pbus's log and code for the "no room" refusal, the `make check` recipe from #339, and
`pytest --durations=0` output.

Measure with: `hyperfine -w 1 -r 5 -P n 1 12 'pytest -n {n} -q'` while sampling PSI each second,
to get the scaling curve and its knee. Use `pidstat -u -r -d 1` and `perf stat -a` during a replay
of three `make check` runs plus one crew run, to see who uses the CPU and whether it is waiting.
Use `pytest --durations=50` for the long tail. Install hyperfine and sysstat with pacman if missing.

Done when, measured and not asserted: in the three-runner replay, `room` admits and pbus launches
`gate pp-doctor` with no "no room" refusal over 10 minutes. Each `make check` stays within 1.2×
its solo hyperfine mean, with spread shown. PSI cpu `some avg60` stays under the threshold the
curve names, and there is no oomd kill. I confirm the desktop stayed responsive.
```
