## Clearing its own blockers

No bot outside watches the homes or the queue.
Each home clears its own blockers, and raises to the user only what the user has to decide.
What is raised reaches the user through jbus, which wakes this project's home thread only for a `decision`, a `sign-in` and an `alert` that stands.
Where the user runs the jbus relay, what blocks also goes on to the user's chat bot (Sous Chef, the brief's Chief Keef), which pages the user.
Everything else, a merge, a stale thread, a retro, a gate, a stall, is quiet, and the user reads it in the digest.

Each time this home wakes (its start, a thread's message), run this from the main checkout, after the block at the top and the block that finds this home:

```sh
: "${M:?run the block that finds this home first}"
scope=
if [ "$M" != "$H" ]; then scope="--scope $(basename "$M")"; fi
if ! command -v jbus > /dev/null; then
    echo "no jbus: jbus is not installed here, so nothing is cleared"
else
    jbus clear $scope 2>&1
fi
```

It reads only what jbus keeps and asks no service.
Each line it prints is one blocker of this home, and its first word says what to do:

- `cleared question <n>`: a question nobody answered for 30 minutes, whose default the thread already acted on.
  `jbus clear` took that default, logged it in this home's `gates.md` as the home's, and closed the question.
  Nothing is posted and nothing more is done: a later answer from the user still replaces it.
- `decision <what>`: the user has to decide it, and the pass raises it once, as one `decision` event with a reply the user can send as it is.
  Do nothing more for it.
  The reply comes back as the user's word ("The user's word, carried by jbus"): act on it then.
- `fix <key>`: brief a fix, as below, and queue it.
- `wait <key>`: a fix of the key is queued and not over, or its last fix merged and the blocker has not been judged since.
  Nothing to do.
- `nothing blocks this home`: nothing to do.

**Brief a fix** of a failed check, a refused or stuck row, or a leftover, as "Handing a task to a crewmate" says, with two lines more in the brief's head, above its first `## ` heading:

```text
Fix of: <the key the line names, such as check:beta>
When green: <the exact check that ends the work, such as `check` passing on the fix's pull request at its head>
```

The `When green:` line is the fix's stop condition, and it is also the last line of its "Done when": once it holds, the work ends, whatever else is seen.
A fix with no such line is refused by `jbus queue add`, with nothing queued: write the line, and queue it again.
Queue it with `jbus queue add`, and approve it by the follow-up rule (`jbus queue approve <slug> --sha <sha12> --follows <the row it fixes>`) where that row's go holds; otherwise the row waits for the user's go, which the pass raises as a decision.
A refused or stuck row is fixed and queued again the same way: its fix brief names the row's key, `row:<slug>`.

Each blocker has a retry cap, `retry_cap` in `~/.config/jstack/config.toml` (2 with none).
jbus counts each fix brief queued for a key in `blockers.json` in this home's directory, and a fix whose own check fails is the same blocker again, not a new one.
A fix row removed with `jbus queue remove` before it launched gives its try back, and one that launched stays counted.
When a key has had its cap, `jbus queue add` refuses the next fix and raises the key as a decision instead (`refused: <key> had <n> fixes`), and `jbus clear` prints it as `decision`.
Then stop: queue no fix of it under another key and another slug. The user's reply says what happens next.

**Raise one by hand** only for what the user has to decide and no line above raises: a scope change, work the plan the user approved does not hold.
A force-push, a deploy, deleting data or a message to anyone outside is a gate that holds ("Gates"), and the pass raises it.

```sh
jbus decide '<slug>' --question '<what the user has to decide, in one line>' --reply '<the reply the user can send as it is, after the project>'
```

It prints `raised:` once, and `raised already:` for the same question again.
Raise nothing else: every other blocker is this home's to clear.
