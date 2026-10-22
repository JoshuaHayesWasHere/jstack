## 1. What a top professional would do
A concurrency and performance engineer would first prove the serialization from timestamps, so the claim does not rest on how slow it feels. Then they would catch a blocked run in the act and name the exact thing it waits on: a lock, a semaphore, a single worker, a queue, a SQLite write lock, or an API rate limit. Only after that would they set the limit to three, and they would put it in one named setting.

## 2. The rawest material
- The per-review run logs with start and end timestamps (e.g. `logs/*.log`, or `journalctl --user -u <service> --since today -o short-iso`): in place of "it seems to go one at a time".
- A live process snapshot while reviews are queued, from `ps -eo pid,ppid,lstart,stat,wchan:32,cmd --forest | rg -i review`: in place of a guess about which process is stuck.
- The open lock files and handles, from `lsof -p <pid>` and `ls -la` on any `*.lock` and `*.db-wal` files near the run: in place of an assumed lock.
- The code paths that set concurrency, from `rg -n 'Semaphore|Lock|flock|max_workers|concurrency|parallel|-j ?1|queue' .`: in place of a remembered default.

## 3. The methods and tools
- `strace -f -tt -p <pid>`, or `py-spy dump --pid <pid>` for Python (`pip install py-spy` or `pacman -S py-spy`): a stack of the waiting process, taken before any fix is chosen.
- `lsof` and `flock --verbose`: identify who holds the lock and who waits on it.
- A timeline built from the log timestamps (start and end per run, with the maximum overlap counted, e.g. with `awk` or `sqlite3` over the parsed lines): measure the concurrency instead of inferring it.
- `hyperfine --runs 5 '<launch 3 reviews>'`, or `/usr/bin/time` over several runs with a spread: the wall time as a number with its variance.
- `pidstat -u -d 1`: check that the limit is not CPU, disk or a shared resource, rather than code.

## 4. What outside the agent shows it is right
- A test that launches four reviews against a stub that sleeps N seconds. It must assert that peak overlap is exactly 3 and that wall time is about 2N, not 4N. It fails on today's code and passes after the fix.
- A real run's log timeline that shows three review intervals overlapping and the fourth starting only when one ends.
- Wall time for three real reviews within 1.2× of one review alone. This is a reasonable target for independent work.
- The user's own look at `ps` during a run, showing three review processes in state `R` or `S` on I/O, none waiting on a lock.

## Rewritten prompt
> "Something is blocking our process and making a run in a one at a time basis or something" — reviews should run "three at a time".
> Do not guess the cause. First prove the serialization from the run logs' start and end timestamps (`logs/*.log` or `journalctl`) by counting the peak overlap. Then, while reviews are queued, catch a waiting one with `ps -eo pid,lstart,stat,wchan:32,cmd --forest`, `py-spy dump --pid` or `strace -f -tt -p`, plus `lsof` on any lock or `.db` files. Name the exact lock, semaphore, worker count, queue or rate limit that holds it, with `file:line` (search `rg -n 'Semaphore|Lock|flock|max_workers|concurrency|queue'`).
> Fix only that, so that at most three reviews run at once, set in one named setting.
> Prove it outside your own judgement:
> - a test that starts four stub reviews of N seconds, asserts peak overlap == 3 and wall time ≈ 2N, and fails before the fix and passes after;
> - a real run's timeline showing three overlapping reviews;
> - `hyperfine --runs 5` wall time for three reviews within 1.2× of one review.
