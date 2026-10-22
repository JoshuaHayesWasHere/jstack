# jbus-thread-cap: find what the jbus thread cap really counts and reset it from measured headroom

Task: "I was just warned that I hit an arbitrary thread limit despite being at 3.5 of 12 cores used address this, I want to push my machine as hard as I can without going over the edge" and "is the cap relevant? Can we go higher based off the past runs we've done?"

Done when:
- The line that raises the warning is quoted with its path:line, found by grepping the jbus source and ~/.config/jbus/ for the warning's text. The brief states exactly what the cap counts: threads, processes, crewmates or API calls in flight, and per what.
- Past runs are tabulated from jbus's run logs, `journalctl --user` and `journalctl -k`, with peak concurrency, wall time, failures, 429s and OOMs for each run.
- The machine's real limits are recorded: /proc/pressure/{cpu,memory,io}, `free -m`, the user slice's memory.peak, pids.max and pids.peak, `ulimit -u -n`, and sar history if any exists.
- USE (utilisation, saturation, errors) is reported for CPU, memory, PIDs/fds, disk and the API rate limit. It is built from `pidstat -t`, `vmstat 5`, `iostat -xz 5` and PSI sampled every 5 s, and it names the resource that binds first.
- A sweep runs a representative workload at the current cap, 1.5x, 2x and 3x, with 3 repeats each. It records tasks/hour, p95 task time, failures and 429s for each run and gives the run-to-run spread.
- The new cap sits at the knee of that curve, with headroom, and is set in jbus config or source.
- At the new cap, throughput beats the old cap by more than the run-to-run spread.
- For the whole run at the new cap there are zero OOM kills, zero swap-in, PSI memory full avg10 = 0, PSI cpu some avg10 < 25% and no 429s, and the machine sustains at least 9 of 12 cores.
- If another resource binds before 9 of 12 cores, the numbers show it and the cap is set at 80% of that resource instead.
- sysstat is installed and its collector enabled, so future runs leave sar history.

Where: the jbus source where the cap and its warning live; ~/.config/jbus/; jbus run logs; the user journal and kernel log; the user slice's cgroup files; /proc/pressure/*; the sysstat package and its timer/service.

Do not touch: system or cgroup limits (pids.max, MemoryMax, ulimits, sysctl), swap settings, or any config outside jbus, except installing and enabling sysstat. Do not change past run logs or journals. Do not run the sweep against anything other than the representative workload.

Decisions: "I want to push my machine as hard as I can without going over the edge". Set the cap at the knee of the sweep curve with headroom. If another resource binds first, set the cap at 80% of that resource.

Design: none, this is measurement and the change of one limit in existing code or config. It needs no architecture call.

Pull request: ask first

Review: review

Playbook: none
