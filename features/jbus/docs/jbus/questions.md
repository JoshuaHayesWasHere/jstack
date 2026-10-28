# Questions

A crewmate or scout pipes a gate to `jbus gate <slug>`. jbus keeps it in `~/.local/state/jbus/<project>/questions.json` as a question with a number, sends one `gate` event, and prints `queued: question <n>`. The same question from the same slug is the same record: a second run prints `already sent: question <n>`, or `already answered: question <n>: <the answer>` once you answered it.

A gate proposes every option its thread weighed. Each is one line, `Option: <short name>: <what follows from it>`, and the name ends at the first colon that a space follows. The option the thread took is the one it recommends, and it carries both marks between the name and that colon, `(default, recommended)`. The other options have no mark.

```
## Gate <n>: tea or coffee?
Status: open
Asked by: alpha, thread mcp:crew-alpha
Default: made tea
Built on it: the cups in pull request 7
Undo: pour it out, one revert
Context: the shelf has both, and the cups are in https://example.test/demo/pull/7
Option: tea (default, recommended): the cups stay as they are
Option: coffee: the cups go back, one revert
Option: water: nothing is brewed
```

jbus checks the lines against `features/home/templates/gates.md`, the one copy of a gate's shape, so a skill pipes the gate and checks nothing first.
It refuses with `not sent: <why>` and keeps nothing when the first line is not `## Gate <n>: ` and the question (`## Gate <number>: ` for a gate a home's old `gates.md` numbered), when there is more than one `## ` line, when there is no `Status: open` line, and when a line of the template's head (`Status:`, `Asked by:`, `Default:`, `Built on it:`, `Undo:`) is missing or still its placeholder.

The record keeps the `Context:` line as `context` and the options, in order, as `options`: each one's `name`, what `follows` from it, and whether it is the `default` and the one `recommended`. `proposed` is when a pass asked the thread of a question with no options for them. A gate may leave out the `Context:` line. jbus refuses, with `not sent:` and the form of an `Option:` line, a gate that has fewer than two options, none or several marked `(default)`, none or several marked `(recommended)`, a recommended option that is not the default, two options of one name, a name that ends in parentheses that are not one of the marks, or an `Option:` line that is not filled in. Nothing is kept of such a gate, and the thread pipes it again with its lines mended.

An open question piped again by the same slug takes the new lines, its context and options included, and keeps its number. An answered one is left as it is. A question asked before gates had options has none. Each pass asks the thread on the `Thread:` line of its brief or request, once for a question, to pipe the gate again with them. The message holds the gate's lines as the record has them, for the thread to pipe as they are. A question whose slug has no such line, or whose thread T3 Code no longer lists, gets no message and stays open as it is: the log has one `note` for it.

### Act unless stopped, and the gates that hold

A gate acts unless stopped.
The thread acts on its default at once and carries on, and the question is shown to you as already acted on: each one on the list of what waits on you has `acted: true`.
No question parks work while it waits.
The first pass that sees a question with no `Holds:` line closes it with its default at once, by silence.
A go gate, a home's pick for a new row parked under the setting `go = "silence"`, waits `go_quiet_minutes` first, and its close by silence approves its row.
The answer on the record is `default`, `closed_by: silence`, `by: jbus`, the time of that pass, and `where: settled at once`.
Any other close by silence is not your word, and no approval rests on it.
The question leaves the list, the log has one `note`, and nothing is sent, since the thread already acted.
You can still answer it later.
Your answer replaces the close by silence, and one that differs goes to the thread as any other.

A default that is irreversible or slow to revert does not act. Undoing such a default needs you, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine. Its gate has two more lines. `Holds: <case>` names the case, word for word from this table. `Fail-safe: <what was prepared>` names the dry-run, plan or bundle you answer on, with its path or link.

| Case | Examples | Fail-safe |
|---|---|---|
| deletes data | removing files, folders, branches, a repo, a T3 project or thread, a database, a bucket, a cloud resource | dry-run: list exactly what goes; a backup or bundle first where one can be made; then hold for you |
| rewrites history | force-push to a shared branch, filter-repo, deleting tags | safety bundle of the old history, verify script, then hold for you |
| spends money | creating paid cloud resources, raising a plan or a limit, a purchase | the cost estimate or plan, then hold for you |
| touches prod or real users | a prod deploy, a prod data or schema change, a message to a customer or anyone outside | the plan or diff (`terraform plan`, `cdk diff`, the message text), then hold for you |
| changes access or secrets | rotating or granting a key or token, tailnet policy or DNS | the diff of the change, then hold for you (jmerge's protected paths already hold the code side) |
| publishes | a public release, a tag, a package, a public repo or post | the exact artifact and where it goes, then hold for you |

Everything else acts at once on its default: a merge (reverted by `gh pr revert`), a branch, a brief, a config edit with its backup, a launch. A gate that holds waits for your answer, and silence never closes it. The record keeps the case as `holds` and the fail-safe as `fail_safe`, and the list shows both, with `acted: false`. Each question's line on the list says which it is: `Its default is acted on already, and stands unless you stop it.`, or `It holds (<case>) for your answer, with its fail-safe: <fail-safe>.` A link's conflict asks its home and not you, so silence never closes it either. `jbus gate` refuses with `not sent:` a `Holds:` line with no filled `Fail-safe:` line, a case not in the table, two `Holds:` lines, and a `Fail-safe:` line with no `Holds:` line.

### Answers

A question with no `Holds:` line settles on its default at once, in the first pass that sees it, and your answer can still replace that default later.
A gate that holds waits on you until `jbus answer` closes it, however long that takes.
A home's `gates.md` that marks a gate `Status: answered` closes a gate with no `Holds:` line with the words of that line.
It never closes a gate that holds: that gate stays open for your own answer, and the pass says so once, in a quiet `note`.
Your answer closes it once.
After `--default`, jbus sends the thread nothing, because the thread already did what you chose.
A gate that holds is the exception: its thread waits for you, so the next pass sends `--default` to it as a go-ahead, with the fail-safe.
After `--differs`, the next pass sends your words to the thread that asked.
You can also answer on the page of `jbus view`, which sends a differing answer at once: [Answer a question on the page](the-view.md#answer-a-question-on-the-page).

The answer is a message of yours, which jbus reads as `jbus word --message` does ([Your word to a home](your-word-to-a-home.md)), or is typed, and its `checked` is false then.
A gate that holds is answered only by you, on words jbus read itself: `jbus --as user answer <n> --message <thread>/<message>`.
A typed answer, an answer from a home, the bot's answer over `POST /act` and an answer on the page of `jbus view` are refused for it, with `refused: question <n> holds (<case>): ...`, and it stays open.
The bot's answer closes any other gate.
Each answer is an act, a line of `acts.jsonl`: [Who acts, and the acts log](the-queue.md#who-acts-and-the-acts-log).
The table of cases is `party.DOORS` in `features/jbus/src/jbus/party.py`, which `jbus gate` checks a `Holds:` line against.

`jbus done <slug>` sends a thread's result as a `result` event at once, in place of waiting for a pass to read the brief.
