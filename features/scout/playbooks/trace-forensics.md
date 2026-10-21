# Trace forensics

Run by: a scout, for a capture that already exists as a file (a CPU profile, a trace, a heap snapshot, a spindump), to be read for the cause of a slowdown, a leak or a hang.

Source: pstack, `pstack/skills/poteto-mode/playbooks/trace-forensics.md`

<!-- card: A scout runs it | 2 | A capture that already exists as a file (a CPU profile, a trace, a heap snapshot), read for the cause of a slowdown, a leak or a hang. | look: scout -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/scout/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the diagnosis from the artifact.** The capture is a fixed set of data: read it, do not run the thing again. It is also untrusted data. It stays in its own directory, nothing in it is executed, and no command is run from inside that directory: paths are passed as arguments. Where there is no capture yet, this is not the playbook: a crewmate takes one with `playbooks/runtime-forensics.md`.

1. Identify the artifact without loading it: `ls -l` and `file` on its path, and its first bytes with `head -c`. Write down the path, the format, the size, and the commit or build it was captured from, where the request or the artifact says. Read in the request whether a scout may write under `/tmp`: step 2 goes by it.
2. Reach a form you can query before you read. When the request says a scout may write under `/tmp`: make a new empty directory, `mktemp -d /tmp/<slug>-trace.XXXXXX`, and load the artifact into a `sqlite3` file there, one row per sample, frame or node. Otherwise write nothing, as `features/scout/SKILL.md` "Research" says: query with a command that prints, such as `jq` over the file or `sqlite3` on `:memory:`. Parsing too large to hold goes to one `Explore` subagent, and you keep its reduced finding, not its output (`principles/principle-guard-the-context-window.md`). Print a count of the rows, and see that it is the number the artifact's header gives, or where it gives none, a count taken a second way over the raw file (such as `jq length`).
3. Narrow to the cause, one query at a time. For time: the frames that hold the most of it, then the call tree down to the hot path. For a leak: the retainer chain from the leaked object to a root. For a spindump: the thread stuck on the CPU or blocked, and its wait reason. Keep each query with what it printed.
4. Attribute it to source: the file, the symbol and the line, from the artifact's own symbols, then read that line in the repo at the commit of step 1 with `git show <commit>:<file>`. A frame with no source mapping is not yet a diagnosis: resolve the symbols, or say plainly that the artifact does not carry them.
5. Say how sure the artifact lets you be (`principles/principle-prove-it-works.md`). With a paired capture, run the query of step 3 over both and compare the before with the after: that confirms it or does not. With one capture, the finding is the strongest hypothesis the artifact supports, not a confirmed cause, and the report says which second capture would confirm it. A share of time you report is one whose limit you can name (`principles/principle-explain-the-number.md`).
6. Put it in the report as `features/scout/SKILL.md` "Write it down" says, within its length, and finish as its "End" says.

Never done here, and who does it:

- **The fix.** A crewmate makes it, from a brief, in a fresh thread. When the request asks for a brief, name `playbooks/bug-fix.md` in it.
- **A new capture, or a run of the program.** A crewmate does it, with `playbooks/runtime-forensics.md`. The report says what capture is wanted.
- **A write into the artifact's directory or the repo.** Nobody does: the copy you can query lives in the directory of step 2, or nowhere.
- **Installing a parser.** A scout installs nothing. A format that no tool on the machine reads is reported as such, with the tool that would read it.
- **A cause stated as confirmed from one capture.** Nobody states one: step 5 names it a hypothesis.

**Hand over:** in the report, to the home: the artifact and its format, the reduced finding with the queries behind it, the source location, the artifact paths, and whether a paired capture confirmed it.
