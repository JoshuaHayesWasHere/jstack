# Autonomous run

Run by: a crewmate, for one task driven to its "Done when" with nobody watching, where each line of it can be checked by a command.

Source: pstack, `pstack/skills/poteto-mode/playbooks/autonomous-run.md`

<!-- card: Long or wide runs | 1 | One task driven to its "Done when" with nobody watching, where each line of it can be checked by a command. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the exit condition.** Say what done is as a check that can fail, then drive to it without stopping. The brief's "Done when" is the predicate, and it is not yours to loosen.

1. Turn the predicate into one command before the first change (`principles/build-the-lever.md`): a script in the scratch directory `mktemp -d /tmp/<slug>-run.XXXXXX` that runs a check for each "Done when" line and prints `holds` or `does not hold` beside it, and exits zero only when all hold. A line that no command can check gets the nearest check that can fail, and the Result says what it leaves unproved (`principles/prove-it-works.md`). Run it now and see it print `does not hold`. If it already says every line holds, the predicate is wrong or the task is done: find out which before any change.
2. Open the log: read `skills/show-me-your-work/SKILL.md` in full and write the first row with its block, the predicate command and what it printed.
3. Loop. Make the smallest change the evidence so far justifies, run the predicate command and the repo's check command, and read what they print. If a line moved to `holds` and nothing moved back, commit. If not, discard the change in full, `git checkout -- <files>` and `git clean -f -- <the files it added>`: what "might help" is reverted, not left to ride. Log one row per round, what changed and which lines moved. Each round ends in the check before the next begins, never several changes and one check at the end (`principles/sequence-verifiable-units.md`). Wait for every command inside this turn: a thread that ends its turn on a background command is not woken.
4. What turns up on the way is yours when it is inside the brief's **Where** and reversible: a flaky check, a broken script, a related bug in a file you are in. Fix it at its cause in a commit of its own, log the row, and go back to the predicate (`principles/fix-root-causes.md`). What is outside **Where** goes under "Noticed". Ask nothing that an experiment can settle. A question only the user can answer is parked as a gate with your default, as `skills/crew/SKILL.md` "Do the task" says, and the run carries on (`principles/never-block-on-the-human.md`). Only the four pauses of that skill's "Carry on" wait.
5. A plateau is not a stop. After three rounds in which no line moved, read the log, then change the approach: another cause, a smaller step, the check itself read again. Stop only when the predicate command exits zero, or at a real dead end, which is a line that no change inside **Where** can make hold. Then the Result says `Status: blocked`, the line, and what was tried, from the log. Never edit the predicate command so that a line holds.
6. Check the log as "Check the log before handing over" in the log skill says. Run the predicate command once more on the committed head with `git status --porcelain` printing nothing, and keep what it prints for the `Proof:` line.
7. Run `playbooks/opening-a-pr.md`. With a pull request open the run goes on as `skills/crew/SKILL.md` "Stay on the pull request" says: the watch wakes this thread, and a failed check or a finding is one more round.

Never done here, and who does it:

- **A timer, a loop or a watcher that wakes this thread.** Nobody arms one. Before the pull request the run is this thread's turn. After it, `watch_pull_request` wakes the thread.
- **A fix outside the brief's Where, in a pull request of its own.** The home plans it, from a line under "Noticed".
- **Loosening "Done when".** The user does, in this thread or through the home. A line you think is wrong is a gate, and the run goes on to the line as written.
- **Stopping to ask.** Nobody does, but for the four pauses. A gate holds the question.
- **Merging, to make a line hold.** The home merges. A "Done when" line that needs a merge is reported as waiting on it.

**Hand over:** in the pull request and the Result, to the reviewer and the home: the predicate command and what it printed at the end, the rounds run, what landed, what was discarded, the log's path and rows, and each gate parked.
