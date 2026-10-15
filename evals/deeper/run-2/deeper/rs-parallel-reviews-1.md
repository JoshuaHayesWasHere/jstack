## 1. What a top professional would do
A concurrency and performance engineer would first catch the blocked process while it is blocked, and name the exact lock, semaphore, queue or `wait()` that holds the other reviews back, before changing anything. They would also put a number on "one at a time": a timeline of when each review starts and ends, and the peak count running at once. The fix is then judged against "three at a time" by measurement.

## 2. The rawest material
- `ps -eo pid,ppid,stat,wchan:32,etime,cmd --forest`, taken while a batch of reviews is running: in place of the impression that runs happen "one at a time or something"
- `/proc/<pid>/stack`, `/proc/<pid>/wchan` and `ls -l /proc/<pid>/fd` for each waiting review process: in place of a guess about what it waits on
- `lslocks` and `ls -l /tmp/*.lock ~/.cache/**/*.lock`: in place of an assumption that no file lock is held
- The runner's own log, with a start and end timestamp per review (for example `grep -E 'review (start|done)' <runner log>`): in place of a remembered sense of how long a batch takes
- The concurrency setting where it is defined and where it is read (`rg -n 'max_workers|concurrency|parallel|Semaphore|Lock|flock|-j ?[0-9]' .`): in place of the belief that the setting is 3 and is honoured

## 3. The methods and tools
- `py-spy dump --pid <pid>` (or `gdb -p <pid> -batch -ex 'thread apply all bt'` for a native process): a stack of every waiting worker, to find where it blocks before any fix is written. If py-spy is missing, install it with `pipx install py-spy` or `pacman -S py-spy`
- `strace -f -tt -e trace=flock,fcntl,futex,wait4,read -p <pid>`: names the system call each worker is stuck in, and since when
- `pidstat -t 1` while a batch runs: shows whether three workers are busy, or one is busy and two are asleep
- A timeline script over the log's start and end stamps that reports peak concurrency and total wall time: the method is a measured count and spread, not a guess
- `hyperfine --runs 5 '<command that runs 6 stub reviews>'`: wall time before and after the fix, with its spread
- `git log -S '<lock or setting name>'`, then `git bisect` if runs used to be parallel: to find the commit that serialized them, instead of guessing

## 4. What outside the agent shows it is right
- A test that runs 6 stub reviews, each sleeping 10 s and recording its start and end. It asserts that peak concurrency is exactly 3, never 4, and that the batch finishes in under 21 s. It must fail on the current code (peak 1, about 60 s) and pass after the fix.
- `hyperfine` over 5 runs of that batch, showing a mean under 21 s with a spread under 1 s. That target is strict and also reasonable: it is what a semaphore of 3 should give.
- The user's own check: a real batch of reviews, watched with `ps --forest`, shows three running at once.

## Rewritten prompt
> "Something is blocking our process and making a run in a one at a time basis or something":
> reviews should run "three at a time". Before changing any code, catch a batch while it is
> running. Take `ps -eo pid,ppid,stat,wchan:32,etime,cmd --forest`, then for each waiting
> worker take `/proc/<pid>/stack`, `py-spy dump --pid <pid>` and
> `strace -f -tt -e trace=flock,fcntl,futex,wait4 -p <pid>`, plus `lslocks`. From these, name
> the exact lock, semaphore, queue or wait that serializes the reviews, with the file and line
> where it is taken. Find where the concurrency setting is defined and where it is read
> (`rg -n 'max_workers|concurrency|Semaphore|Lock|flock'`). From the runner's log stamps, give
> the current peak concurrency and batch wall time; use `git log -S` or `git bisect` if runs
> were once parallel. Then make the smallest fix that lets exactly three reviews run at once.
> Proof: add a test with 6 stub reviews of 10 s each. It must fail on the current code and
> pass after the fix, asserting that peak concurrency is exactly 3 (never 4) and that the batch
> finishes in under 21 s. Also report `hyperfine --runs 5` wall time before and after, with its
> spread.
