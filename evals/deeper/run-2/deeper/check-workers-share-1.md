## 1. What a top professional would do
A performance/capacity engineer would not pick a worker count by feel. They would first find the knee: the point where `make check` wall time stops falling as workers rise. Past the knee, extra workers only add queueing.

They would also measure "the edge" as CPU and memory pressure stall rather than load average. Load average counts tasks waiting on I/O and runnable tasks the same way, so 14 to 15 on 12 cores does not show by itself where the edge is.

Finally, they would make the parallelism one budget shared by every runner and crew. Today each `make check` takes a fixed six workers whatever else is running.

## 2. The rawest material
- `/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io` sampled each second, and `/proc/loadavg` alongside: in place of the remembered "load 14 to 15 for over ten minutes".
- `journalctl --since '2026-10-12 21:25' --until '2026-10-12 21:50'`, plus `room`'s and pbus's own logs for that window (the `gate pp-doctor: no room for 10 passes` line with its timestamps and the thresholds `room` compared against): in place of the summary that `room` "said wait".
- `sar -q -u -r -f /var/log/sa/sa12` for 2026-10-12, if sysstat was recording: in place of a reconstruction of what ran.
- The `check` target in `Makefile` and the diff of tests-parallel (#339) (`git show` on its merge): in place of "since #339 it runs on six workers".
- `pytest -n 6 --durations=0` output from one `make check`: in place of the assumption that the suite scales evenly across workers.
- `room`'s source, for the rule that turns load into go or wait: in place of trusting that rule as the definition of the edge.

## 3. The methods and tools
- `hyperfine -w 1 -r 5 -P n 1 12 'pytest -q -n {n}' --export-json scan.json`: a scan of wall time against worker count, with a run count and a spread, to find the knee.
- The same scan run while two more `make check` processes run alongside it: finds the knee under the real contention of three runners.
- `vmstat 1`, `pidstat -u -r -d 1`, and a loop on `/proc/pressure/*`: shows whether the limit is CPU, memory or I/O at each N. Use PSI `some avg10` as the measure of the edge.
- `perf stat -a -e task-clock,context-switches,cpu-migrations -- make check`: shows whether past the knee the time goes to work or to switching.
- A shared token budget, either GNU make's jobserver or a `flock`-based semaphore that pytest-xdist reads through `-n`: every runner and crew draws from one pool of about the knee value, not six each.
- `systemd-run --user --scope -p CPUWeight=50 make check`: lowers test runs below interactive work and pbus launches, without lowering their throughput.
- sysstat (`sudo pacman -S sysstat && sudo systemctl enable --now sysstat`), if `sar` or `pidstat` is missing.

## 4. What outside the agent shows it is right
- The hyperfine scan's JSON, which names the knee N. The chosen setting must be within 10% of the best measured wall time.
- A replay of the 2026-10-12 load, with three concurrent `make check` runs plus a crew's run, while pbus asks for `pp-doctor`'s 10 passes. `room` must say go and pbus must launch within 60 seconds, with no "no room" line in its log. This target sounds unreasonable, but it is reasonable: the 2026-10-12 stall was oversubscription, not lack of capacity.
- `/proc/pressure/cpu` `some avg10` must stay under 25% during that replay, and memory `some` must stay near 0. Load average is recorded but does not decide.
- The user's own check: the machine stays responsive at the keyboard during the replay.

## Rewritten prompt
> "I want to push my machine as hard as I can without going over the edge" and "run the test in parallel".
> Since #339, `make check` runs pytest on six workers. On 2026-10-12 at 21:35 ET, three runners plus the crews' runs held the load at 14 to 15 on 12 cores, `room` said wait, and pbus logged `gate pp-doctor: no room for 10 passes`.
>
> Start from the raw record of that evening: `journalctl` and `room`'s and pbus's logs for 21:25 to 21:50, `sar -f /var/log/sa/sa12` if sysstat ran, the `check` target and the #339 diff, `room`'s rule for go and wait, and `pytest -n 6 --durations=0` from one run.
>
> Treat CPU and memory pressure stall (`/proc/pressure/*`) as the measure of the edge, not load average. Find the knee with `hyperfine -P n 1 12 'pytest -q -n {n}'`, run alone and again beside two other `make check` runs, using `vmstat`, `pidstat` and `perf stat` to see what limits it. Then make the parallelism one budget shared by all runners and crews (a make jobserver or a `flock` semaphore feeding `-n`) at about the knee, and run tests under a lower `CPUWeight`.
>
> It is done when the scan's JSON shows the chosen setting within 10% of the best wall time, and when a replay of three concurrent `make check` runs plus a crew's run lets pbus launch `pp-doctor`'s 10 passes within 60 seconds with no "no room" in its log, while CPU `some avg10` stays under 25%. Report those numbers, and leave me to check that the machine stays responsive during the replay.
