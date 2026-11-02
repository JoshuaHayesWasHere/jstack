A repo runs with a home or with none.
With none, the block below prints nothing and no message is sent: jbus reads the brief from disk, logs each new Result, and runs `jmerge`.
A home plans, assigns and starts, and what finishes the work is not its to hear.
So a crewmate sends its home one message whoever merges: it ends with no pull request ("End").
A gate goes to jbus, and to the home only where jbus cannot take it ("Do the task").
Not when the pull request opens, and not when the findings are handled.

jbus is the only merger, so a line about a pull request goes where jbus's merge reads it, and not to the home.
The lines are: that it is fixed and green; that it is green and has no reviewer, or no second or scoped reviewer where its fix needs one (all in "The review").
A pull request has one of the two, never both.
Before each of them, run this with the block at the top, with `fixed` in place of the words in angle brackets for the `fixed and green` line, and `waits` for any other: a line that says the pull request waits for the user's word.
It is the only check:

```sh
B="$H/tasks/<slug>.md"
line='<fixed or waits>'
if [ "$line" != fixed ] && [ "$line" != waits ]; then
    echo "not filled in: put fixed or waits in place of the placeholder"
elif [ "$line" = fixed ]; then
    echo "jbus merges: send nothing, jbus reads the brief and the pull request on each pass"
else
    echo "jbus merges: send no line, and park it as a gate with the default that the pull request waits"
fi
```

On `jbus merges: send nothing`, write the lines the Result is owed and go on: `jmerge`, run by jbus, reads them.
On `jbus merges: send no line, and park it as a gate`, the line asks for somebody's word and jbus's `jmerge` says only `wait` of such a pull request: park a gate ("Do the task") whose question is the line without its `at <head>`, with the default that the pull request waits and the head on its `Built on it:` line.
The line of a brief that says `Review: none` is the one exception: `jmerge` already holds that pull request for the user's word, so park nothing for it.
jbus tells one gate from another by its slug and its question, so a later head of the same pull request is the same gate, and `already sent` is no fault.
A brief of a scoped home is told the same way: jbus merges its pull request as it merges the root home's.
A block beside a send that prints `tell the home` is answered by this one.

Whom to send it to is this. Shell variables do not last from one call to the next, so run it in one call with the block at the top and `B` set to the brief, `$H/tasks/<slug>.md`:

```sh
uv run --project "$T/../source" jbus home "$B"
```

It prints the id of the brief's home, or nothing where there is none.
Run it each time there is something to tell, and do not keep the id from an earlier run: the next home's start puts its own id in the file.

If it prints a thread id, send that thread the message with the `t3-code` server's `t3_thread_send` (if your harness defers it, load it first). If it prints nothing, there is no home: send nothing. The Result on disk is the record, and jbus, or the next home, reads it from there.
