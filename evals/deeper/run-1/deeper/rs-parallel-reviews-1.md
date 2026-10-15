## 1. What a top professional would do
A concurrency and performance engineer would not guess at the cause or simply raise a limit. They would first catch the serialization in the act, with a timeline of when each review starts and ends and a stack of every waiting process, and name the exact lock, queue or single-worker setting that causes it. Then they would put in a bounded limit of three, so reviews never run one at a time and never run four or more at once.

## 2. The rawest material
- The start and end timestamps of each review, taken from the runner's own log (e.g. `logs/*.log`, `journalctl --user -u <runner> --since today`). This replaces the impression that "it runs one at a time or something".
- The live process tree while several reviews are queued (`pstree -ap $(pgrep -f <runner>)`, `ps -eo pid,ppid,stat,wchan:32,etime,cmd`). This replaces a guess at which process is waiting.
- The kernel's view of each waiting process (`cat /proc/<pid>/stack`, `cat /proc/<pid>/wchan`, `ls -l /proc/<pid>/fd`). This replaces the assumption that the process is "busy".
- The code that launches reviews, read at the exact lines that hold a lock, `flock`, `Semaphore`, `max_workers`, `concurrency`, `-j` or `--jobs`, or a single queue consumer (`rg -n 'flock|Lock\(|Semaphore|max_workers|concurrency|--jobs|-j ?1|queue' .`). This replaces a remembered setting.
- The lock files and sockets held while reviews wait (`lsof +D /tmp`, `lsof -p <pid>`, `ls -l /run/lock /tmp/*.lock`). This replaces "something is blocking".

## 3. The methods and tools
- **`py-spy dump --pid <pid>`** (or `gdb -p <pid> -batch -ex 'thread apply all bt'` for non-Python code): a stack of each waiting process, so the lock is found in the stack rather than guessed.
- **`strace -f -tt -e trace=flock,fcntl,futex,wait4,read,connect -p <pid>`**: shows the exact system call each waiting review is blocked on.
- **A timeline built from the log timestamps** (`awk`/`sqlite3` over start and end lines, counting how many reviews overlap at each moment): measures concurrency before and after the change, instead of describing it.
- **`hyperfine --runs 3 '<launch 9 reviews and wait>'`**: wall-clock time of a fixed batch, with a run count and a spread, before and after the change.
- **`pidstat -u -d 1`** during the batch: shows whether the waiting is CPU, I/O, or plain waiting on a lock. That tells you whether three-at-once is limited by the machine or only by the code.

## 4. What outside the agent shows it is right
- **The overlap timeline from the runner's own log** for a batch of nine reviews. It must show exactly three running at once for most of the batch, and never more than three.
- **A measured number against a stated target.** Nine reviews must finish in no more than about 3.3× the time of a single review, which is about one third of the serial time, by `hyperfine` over three runs. Measure the serial baseline first.
- **A test that fails before and passes after.** Launch five stub reviews that each sleep and record their start times. Assert that the maximum overlap is 3 and that it is greater than 1.
- **The user's own check.** The user starts a normal batch and sees three reviews in progress at once in `ps` or in the runner's output.

## Rewritten prompt
```
"Something is blocking our process and making a run in a one at a time basis or something" —
reviews should run "three at a time".

Before changing anything, catch the serialization while it happens. Queue at least five reviews.
Then read, for each waiting process:
- the process tree (pstree -ap, ps -eo pid,stat,wchan:32,etime,cmd)
- /proc/<pid>/stack
- py-spy dump --pid <pid> (or gdb bt)
- strace -f -tt -e trace=flock,fcntl,futex,wait4,connect
- lsof for held lock files and sockets
Also read the start and end timestamps of each review from the runner's own log. Locate the exact
lock, flock, single queue consumer, or concurrency/max_workers/-j setting that forces one at a
time, and cite its file:line.

Measure the serial baseline: build an overlap timeline from the log, and time a batch of 9
reviews with hyperfine --runs 3. Then make the fix: a bounded limit of exactly 3 concurrent
reviews, not an unbounded one. Watch pidstat -u -d 1 during the batch to confirm the machine
can sustain three.

Done when:
(a) A test that launches 5 stub reviews fails before the fix and passes after. It asserts that
    max overlap == 3.
(b) The log timeline for 9 real reviews shows 3 running at once and never more than 3.
(c) hyperfine shows the 9-review batch at no more than ~3.3× a single review's time, with the
    spread reported.
(d) I can start a batch myself and see three reviews in progress at once.
```
