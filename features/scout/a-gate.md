A question only the user can answer does not wait.
A gate acts unless stopped: take the default you would recommend, act on it at once, carry on with everything, what depends on the default included, and park the question as a gate: read `$T/gates.md` now, the gate's lines and the rule under them, and fill the lines in.
The one exception is a default that is irreversible or slow to revert, one of the six cases of the table in `$T/gates.md`: undoing it needs the user, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine.
Do not act on that one.
Do its fail-safe (the dry-run, the bundle, the plan or diff, the exact artifact), add the `Holds:` and `Fail-safe:` lines under `Undo:`, and carry on with what does not depend on it: the action waits for the user's answer.
Leave its `<n>` as it is: jbus numbers the question and is the one place it is kept.
A gate goes to jbus and not into the home's thread: the user answers it wherever they are, and jbus closes it, or, when it has no `Holds:` line, closes it with its default in the first pass that sees it.
Under the gate go one `Context:` line and one `Option:` line for every option you weighed, the default you took among them, which is the one you recommend, marked `(default, recommended)`, and the rest with no mark.
Run this in this checkout, with the block at the top and the filled-in lines in place of the line in angle brackets:

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
It speaks for the project whose repo this checkout is of, and refuses a repo its config does not name.
On `asked:`, jbus holds the question: send the home nothing.
The line under it, `Gate: question <number>`, is all the report keeps of the gate: add it under "Findings", as printed, and no line of the gate itself.
Where it says `asked: already answered: question <number>:`, nothing was asked: the same question was answered before, and the line gives that answer.
Go by it, and take the default back where it differs.
On `not asked: not sent:`, nothing was queued: fill in the line it names and run it again.
On any other `not asked`, jbus holds nothing: send the lines, under a first line `<slug>: gate`, to the thread the block in step 3 of "End" prints, and with no home there put them in the report under "Findings", the one place left that can hold them.
An answer that differs from the default comes back as a message here, from jbus.
The four things "Carry on" never does on a default are such gates, each one that holds.
Besides a gate jbus could not take, a scout sends its home nothing before the End.
