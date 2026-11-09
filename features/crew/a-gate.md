A crewmate gates only a one-way door: a default that is irreversible or slow to revert, one of the cases of the table in `$T/gates.md`, because undoing it needs the user, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine.
Any other choice is no gate and asks the user nothing: take the default you would recommend, act on it at once, carry on, and record it in the Result as a `Decision:` line (`$T/result.md`), with what you took and how to take it back.
A question only the user can answer, of such a choice, is a decision too.
For a one-way door, do not act.
Read `$T/gates.md` now, the gate's lines and the rule under them, and fill the lines in.
Do its fail-safe (the dry-run, the bundle, the plan or diff, the exact artifact), add the `Holds:` and `Fail-safe:` lines under `Undo:`, and carry on with what does not depend on it: the action waits for the user's answer.
Leave its `<n>` as it is: jbus numbers the question and is the one place it is kept.
A gate goes to jbus and not into the home's thread: the user answers it wherever they are, and only the user's answer closes it.
Under the gate go one `Context:` line and one `Option:` line for every option you weighed, the default you took among them, which is the one you recommend, marked `(default, recommended)`, and the rest with no mark.
Run this in this worktree, with the block at the top and the filled-in lines in place of the line in angle brackets:

```sh
if command -v jbus > /dev/null; then
    jbus gate '<slug>' << 'THE_GATE_ENDS_HERE'
<the gate, filled in>
Context: <what the user needs to know to answer it, in one line, with the links to it>
Option: <an option's short name> (default, recommended): <what follows from it>
THE_GATE_ENDS_HERE
else
    echo "not asked: jbus is not installed here"
fi
```

`jbus gate` checks the lines against `$T/gates.md`, the one copy of their shape, and prints every line to go by.
It speaks for the project whose repo this worktree is of, and refuses a repo its config does not name.
On `asked:`, jbus holds the question: send the home nothing.
The line under it, `Gate: question <number>`, is all the Result keeps of the gate: add it to the Result as a line of its own, as printed, and no line of the gate itself.
Where it says `asked: already answered: question <number>:`, nothing was asked: the same question was answered before, and the line gives that answer.
Go by it, and take the default back where it differs.
On `not asked: not sent:`, nothing was queued: fill in the line it names and run it again.
On `decided:`, the gate had no `Holds:` line, so it was no one-way door: jbus wrote it to the brief as a `## Decision:` section and asked nobody.
Send the home nothing, keep no `Gate:` line of it, and add its `Decision:` line to the Result.
On `not asked: settled:`, a rule already answers the question, and the line names the rule and what to do instead: do that, and send nothing to the home and no gate line to the Result.
On any other `not asked`, jbus holds nothing: send the lines, under a first line `<slug>: gate`, to the thread "Telling the home" finds, and with no home there put them in the Result above its `Left:` line, the one place left that can hold them.
An answer that differs from the default comes back as a message here, from jbus.
A review finding you cannot settle without the user's word is a gate only where it is a one-way door, and any other is a decision.
