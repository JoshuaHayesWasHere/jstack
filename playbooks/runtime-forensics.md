# Runtime forensics

Run by: a crewmate, for a symptom that shows only in a running process (a spinning CPU, a leak, a visual glitch, a loop firing without input), to be diagnosed and not fixed, in a brief with `Pull request: ask first`.

Source: pstack, `pstack/skills/poteto-mode/playbooks/runtime-forensics.md`

<!-- card: Diagnose, fix nothing | 1 | A symptom that shows only in a running process: a spinning CPU, a leak, a visual glitch, a loop firing without input. | plain: `Pull request: ask first` -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the diagnosis.** Instrument the live process, and do not theorize from source. What you hand over is a cited diagnosis, not a fix. Where the capture already exists as a file, this is not the playbook: `playbooks/trace-forensics.md` is, and a scout runs it.

1. Reach the process and see the symptom yourself, live: the repo's verify skill where it has one, otherwise the command or surface the brief names. Start it from your worktree, or attach to the one the brief names. Write down its command and process id, and what the symptom looks like as it happens. A symptom you have not seen is not yet one you can instrument.
2. Capture the live signal while the symptom shows, with the profiler or inspector the runtime itself ships: a CPU profile for a spinning process, a heap snapshot for a leak, a trace for a visual glitch. Write it to a new directory, `mktemp -d /tmp/<slug>-forensics.XXXXXX`, and run `ls -l` on it: a real artifact of a real size, not a guess.
3. Reduce the artifact to the smoking gun: the function on the hot path, the retainer chain from the leaked object to a root, the loop that fires without input. An artifact too large to read goes to one `Explore` subagent, and you keep its reduced finding, not its output (`principles/guard-the-context-window.md`). Write the finding as one sentence that could be false.
4. Prove the mechanism on the running process before you believe it (`principles/prove-it-works.md`). Write down first what you expect to see. Then evaluate a probe through the process's inspector (a counter, a log line, a stack printed at the suspect call), or patch the live code without a reload, and read what it prints. A prediction that fails sends you back to step 2 with a new capture, not to a second guess.
5. Map the finding to source: the file, the symbol, and the line that allocates or schedules, read in the worktree at the commit the process runs (`principles/fix-root-causes.md`). A frame you cannot map is said to be unmapped, with what would map it.
6. Take out what you put in: stop every process you started, and undo every probe and live patch. Run `git status --porcelain` in the worktree and see it print nothing. The artifacts stay in the directory of step 2.
7. End as `skills/crew/SKILL.md` "End" says for a task with no pull request. The diagnosis goes in the Result, with its `Proof:` line holding the capture command and the probe's output as printed.

Never done here, and who does it:

- **The fix.** A crewmate makes it, from a new brief with `playbooks/bug-fix.md`. The home plans it from the Result.
- **A diagnosis from reading the source.** Nobody gives one here: without a capture and a probe that confirmed it, the Result says "hypothesis" and what run would confirm it.
- **A probe in a process that serves anyone else.** Only the user's word allows one. Reproduce the symptom in a process you start, and park the question as a gate, as `skills/crew/SKILL.md` "Do the task" says, with that as its default.
- **A commit or a pull request.** Nobody makes one: a probe is not a change to keep.
- **A capture read raw into this thread.** The one `Explore` subagent of step 3 reads it.

**Hand over:** in the Result, to the home: the signal captured, the reduced finding, how the mechanism was proven, the source location, and the artifact paths. No fix.
