## 1. What a top professional would do
A concurrency/performance engineer. They would not guess where the queue serialises. They would catch the blocked runs in the act: see what the waiting process is waiting on (a lock, a semaphore, a worker count of 1, a file lock) and read that from the stack, not from the config. They would also measure the peak number of reviews in flight before the fix and after it, so "three at a time" is a number they observed and not one they assumed.

## 2. The rawest material
- `ps -eo pid,ppid,lstart,etime,stat,wchan:32,cmd --forest | grep -i review` and `pstree -p` taken while several reviews are queued: in place of "it seems to run one at a time"
- The per-review start and end timestamps in the run logs (e.g. `grep -hE 'review.*(start|done|finish)' logs/*.log ~/.local/state/*/log*`): in place of a remembered impression of the ordering
- `lslocks -o COMMAND,PID,TYPE,MODE,PATH` and any lock or pid files (`ls -la /tmp/*.lock ~/.cache/**/*.lock`): in place of an assumption about which lock is involved
- `grep -rnE 'max_workers|concurrency|Semaphore|Lock\(|flock|parallel|-j ?1|queue' .` over the code and config that launch reviews: in place of a guessed setting
- `git log -S 'concurrency' -S 'max_workers' --oneline` if reviews ever ran in parallel: in place of "it used to work"

## 3. The methods and tools
- `py-spy dump --pid <waiting pid>` (or `gdb -p` / `jstack` for other runtimes): read the stack of a blocked review to find the exact line it waits on. Install with `pacman -S py-spy` or `pipx install py-spy`
- `strace -f -tt -e trace=flock,fcntl,futex,wait4 -p <pid>`: find out whether the wait is a file lock, a mutex, or a parent process waiting on a single child
- A timeline from the log timestamps (a short `awk` or `python -I` script that sweeps the start and end events and prints peak concurrency): measure the in-flight count, before and after
- `git bisect run <the concurrency test>`: if parallel runs once worked, find the commit that serialised them instead of guessing
- `hyperfine --runs 5 '<launch 6 stub reviews>'`: wall time with a spread, before and after

## 4. What outside the agent shows it is right
- A test that launches 6 reviews against a stub that sleeps a fixed time and records start and end. It must fail on the current code (peak in flight = 1) and pass after the fix, with a peak of exactly 3: it reaches 3 and never reaches 4.
- `hyperfine` reports wall time for those 6 reviews at no more than 2.2× a single review (it is about 6× today). That target is tight but reasonable: ideal scheduling gives 2×.
- A `ps --forest` snapshot during a real run shows three review processes running at once, with the fourth waiting.

## Rewritten prompt
```
"Something is blocking our process and making a run in a one at a time basis or something."
Reviews should run three at a time: never one at a time, never more than three.

Start from the raw evidence, not from impressions. While several reviews are queued, capture
`ps -eo pid,ppid,lstart,etime,stat,wchan:32,cmd --forest`, `lslocks`, and any lock/pid files.
Take the per-review start/end timestamps from the run logs, and grep the launch code and config
for max_workers / concurrency / Semaphore / Lock / flock / queue settings. If reviews once ran in
parallel, check `git log -S` for the change.

Find the serialising point by observing it: `py-spy dump` (or the equivalent for the runtime) and
`strace -f -e trace=flock,fcntl,futex,wait4` on a waiting review, to name the exact line or lock
it blocks on. Fix that cause and nothing else, and set the limit to 3. If it was a regression,
use `git bisect run` with the test below.

Proof, before and after:
- a test that launches 6 reviews on a sleeping stub and records start/end. It fails today
  (peak in flight 1) and passes after with a peak of exactly 3, never 4;
- `hyperfine --runs 5` puts 6 reviews at ≤ 2.2× the wall time of one;
- a `ps --forest` snapshot from a real run showing three reviews at once.
Report the blocking line or lock you found, the fix, and the before/after numbers.
```
