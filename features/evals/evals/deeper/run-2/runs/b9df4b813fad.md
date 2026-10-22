# review-concurrency-three: find what serializes reviews and let exactly three run at once

Task: "Something is blocking our process and making a run in a one at a time basis or something": reviews should run "three at a time". Before changing any code, catch a batch while it is running. Take `ps -eo pid,ppid,stat,wchan:32,etime,cmd --forest`, then for each waiting worker take `/proc/<pid>/stack`, `py-spy dump --pid <pid>` and `strace -f -tt -e trace=flock,fcntl,futex,wait4 -p <pid>`, plus `lslocks`. From these, name the exact lock, semaphore, queue or wait that serializes the reviews, with the file and line where it is taken. Find where the concurrency setting is defined and where it is read (`rg -n 'max_workers|concurrency|Semaphore|Lock|flock'`). From the runner's log stamps, give the current peak concurrency and batch wall time; use `git log -S` or `git bisect` if runs were once parallel. Then make the smallest fix that lets exactly three reviews run at once. Proof: add a test with 6 stub reviews of 10 s each. It must fail on the current code and pass after the fix, asserting that peak concurrency is exactly 3 (never 4) and that the batch finishes in under 21 s. Also report `hyperfine --runs 5` wall time before and after, with its spread.
Done when:
- A batch was caught while running, before any code changed, and its `ps --forest` output, plus `/proc/<pid>/stack`, `py-spy dump` and `strace` for each waiting worker, plus `lslocks`, is in the report.
- The report names the exact lock, semaphore, queue or wait that serializes the reviews, with the file and line where it is taken, backed by those captures.
- The report gives the file and line where the concurrency setting is defined and every place it is read.
- The report gives the current peak concurrency and batch wall time from the runner's log stamps.
- If runs were once parallel, the report names the commit that serialized them, found with `git log -S` or `git bisect`.
- A new test runs 6 stub reviews of 10 s each and asserts that peak concurrency is exactly 3 (never 4) and that the batch finishes in under 21 s.
- That test is shown failing on the current code and passing after the fix, with output from both runs.
- The fix is the smallest change that lets exactly three reviews run at once.
- The existing test suite passes after the fix.
- `hyperfine --runs 5` wall time is reported before and after the fix, with its spread.
Where: the review runner and the code that launches review workers; the place the concurrency setting is defined and the places it is read; any lock, semaphore, `flock` or queue on the review path; the runner's logs; the test suite (new test).
Do not touch: anything beyond the smallest fix that serializes the reviews; scouts, crewmates and the home thread's own scheduling; no change to the concurrency value other than three; no loosening of the new test's bounds.
Decisions: reviews should run "three at a time"; "Before changing any code, catch a batch while it is running"; "make the smallest fix that lets exactly three reviews run at once"; the test uses "6 stub reviews of 10 s each", must "fail on the current code and pass after the fix", and asserts "peak concurrency is exactly 3 (never 4)" and "the batch finishes in under 21 s"; report "`hyperfine --runs 5` wall time before and after, with its spread".
Design: none, this is a diagnosis plus the smallest fix to one serialization point, and the user has already fixed the target behavior and the proof.
Pull request: ask first
Review: review
Playbook: none
