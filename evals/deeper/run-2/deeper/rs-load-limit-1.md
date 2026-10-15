## 1. What a top professional would do
A capacity-planning / performance engineer would not treat "3.5 of 12 cores" as the headroom. CPU is one resource out of several. Before moving the cap they would find which resource saturates first as concurrency rises: memory, swap, I/O, file descriptors, or an upstream API rate limit. They would also find out what the cap protects. Then they would run a step test and set the cap just below the knee where throughput stops rising and latency, pressure, or errors start climbing.

## 2. The rawest material
- **The cap's own source.** Find it with `rg -n -i "thread limit|max_threads|concurrency|MAX_" ~/.claude ~/bin $(command -v jbus)` and read the line that emits the warning, plus its git blame or comment. This replaces the guess that the limit is "arbitrary".
- **The warning itself, with its timestamp and the counts at that moment.** Get it with `journalctl --user --since "2026-10-15" | rg -i "limit"` or the home's own log. This replaces the remembered "3.5 of 12 cores".
- **Past runs' per-second machine counters.** Use `sar -u -r -q -B -d -f /var/log/sa/saDD` for each run day; if sysstat isn't collecting, `systemctl enable --now sysstat-collect.timer`. This replaces the impression that past runs were fine.
- **Pressure stall data.** Read `/proc/pressure/{cpu,memory,io}` (`some`/`full` avg10/avg60), logged during runs. This replaces load average and the CPU % as the measure of "the edge".
- **Kills and throttling in past runs.** Check `journalctl -k | rg -i "oom|killed process"`, then `rg -c " 429 |rate.?limit|overloaded" <run logs>`. This replaces "nothing broke".
- **Per-task resident memory and run time from past runs.** Use `pidstat -r -u -p <pids> 5`, or the run logs' start/end times. This replaces an average guessed per thread.

## 3. The methods and tools
- **`rg` and git blame on the cap's definition**: find out what the cap protects before changing it. The constraint behind it may be RAM, API quota, or a cost ceiling.
- **`sar` / `vmstat 1` / `pidstat -urd 5` over past run windows**: find the binding resource. Compute peak RSS per task × proposed concurrency against `MemAvailable`, and peak API calls/min against the quota.
- **A step test**: run the same representative batch at the current cap, then +2, +4, +6 and so on. Log `/proc/pressure/*` every 10 s with `while sleep 10; do date +%s; cat /proc/pressure/*; done >> psi.log`. Record tasks completed per hour, p95 task duration, 429 count, and swap-in rate (`sar -W`) at each step.
- **Little's law (concurrency = throughput × duration)**: check whether added threads produce more throughput or only more queueing upstream.
- **A guard instead of a fixed number, if the field would use one**: admit a new thread only while memory PSI `some avg10` is below its threshold and `MemAvailable` covers one more task's peak RSS.

## 4. What outside the agent shows it is right
- **Step-test numbers on this machine.** At the chosen cap, completed tasks per hour must be measurably higher than at the current cap, about 2× and not just more threads, with p95 task duration no more than 1.25× the baseline.
- **Kernel counters across a full real run at the new cap.** Zero OOM kills in `journalctl -k`, no sustained swap-in, memory PSI `full avg60` = 0 and `some avg60` < 5%, cpu `some avg60` < 25%. Ask for that full=0 bar; it is the reasonable line for "not over the edge".
- **The upstream API's own responses.** The 429/overloaded rate at the new cap is no higher than at the old one.
- **The user's check.** The desktop stays responsive during the run.

## Rewritten prompt
> "I was just warned that I hit an arbitrary thread limit despite being at 3.5 of 12 cores
> used address this, I want to push my machine as hard as I can without going over the edge"
> and "is the cap relevant? Can we go higher based off the past runs we've done?"
> Start from the code that defines and emits the limit (find it with `rg`, read its comment
> and git blame) and say what it protects. Then read the raw record of past runs, not
> recollection: `sar -u -r -q -B -W -d -f /var/log/sa/saDD` for each run day, the warning's
> own log line and timestamp, `/proc/pressure/{cpu,memory,io}`, OOM lines from
> `journalctl -k`, 429/rate-limit counts in the run logs, and per-task peak RSS and duration.
> Name the resource that saturates first; CPU at 3.5/12 is not proof of headroom. Then run a
> step test on one representative batch: current cap, then +2 each step. Log PSI every 10 s
> and record tasks/hour, p95 task duration, swap-in rate and 429s at each step. Pick the cap
> just below the knee, or replace the fixed cap with a PSI/MemAvailable admission guard if
> that fits better. Done when a full real run at the new cap shows about 2× the tasks/hour
> of the current cap, p95 duration within 1.25× baseline, zero OOM kills, memory PSI
> `full avg60` = 0 and `some avg60` < 5%, no rise in the 429 rate, and the desktop staying
> responsive by my own check. Report the step-test table as the proof.
