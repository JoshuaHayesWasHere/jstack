# check-cpu-budget: keep tests parallel and the machine busy without room stalling pbus launches

Task: "I want to push my machine as hard as I can without going over the edge" and "run the test in parallel"
Done when:
- The raw record of 2026-10-12, 21:20–22:00 ET, is reported:
  - `sar -q -u -P ALL -f /var/log/sa/sa12` output, or a plain statement that sysstat wasn't collecting.
  - `journalctl` for that window.
  - room's and pbus's logs for that window, including the `gate pp-doctor: no room for 10 passes` lines.
- room's source is cited with path and line: what it reads and the threshold it waits on.
- The #339 diff and the Makefile `check` target are checked for anything that nests `make check` inside a runner or crew and multiplies the six workers, and the answer is stated.
- Current `/proc/pressure/{cpu,io,memory}` values are recorded.
- One serial `pytest --durations=0` is recorded.
- The 21:35 mix (three runners, `make check` and a crew run) is replayed under `pidstat -u -d -w 1` and `vmstat 1`. The result says whether the load was CPU queueing, I/O wait or context switching.
- `hyperfine --warmup 1 --runs 5 -L n 1,2,4,6,8,12 'pytest -n {n} -q'` is run, its table is printed, and the worker count at the knee is chosen.
- `make check`, the runners, the crews and pbus all draw from one shared CPU budget (the make jobserver or a slot counter room hands out) instead of each sizing itself.
- The replay, run three times with numbers printed for each run, shows:
  - PSI cpu `some avg10` under 10%
  - mean CPU across the 12 cores at or above 85%
  - room never waiting longer than 2 minutes
  - pbus launching pp-doctor's 10 passes within 2 minutes of asking
  - `make check` alone no slower than today's `-n 6` within the measured spread

Where: the Makefile `check` target and pytest/xdist worker config; room's source (its load signal and wait threshold); pbus's gate and launch path; how runners and crews start their test runs; the #339 diff; `/var/log/sa/sa12`, journald, and room's and pbus's logs.
Do not touch: test parallelism itself (no fallback to serial); pp-doctor's 10-pass request; room's gate as a safeguard. Don't remove or loosen the gate just to make the numbers pass.
Decisions: "Keep tests parallel and the machine busy, and stop that stall." "Start from the raw record, not the remembered numbers." Pick "the worker count at its knee." "If the replay shows room is gating on loadavg where PSI would be the truer edge, change room's signal to `/proc/pressure/cpu some avg10`." "Have `make check`, the runners, the crews and pbus draw from one shared CPU budget (the make jobserver or a slot counter room hands out) rather than each sizing itself." "Use `systemd-run --scope -p CPUWeight=` where background tests should yield to launches." "The final check is mine: an evening of real crews with no `no room` gate in pbus's log."
Design: none, the user named the signal, the shared-budget options and the CPUWeight scopes. The replay and the scaling curve choose among them.
Pull request: ask first
Review: review
Playbook: none
