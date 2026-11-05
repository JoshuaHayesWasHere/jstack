## Gate <n>: <the question only the user can answer, in one line>
Status: open
Asked by: <the slug of the brief or request, or `home`>, thread <the asking thread's id>
Default: <what the thread did in place of an answer, in one line>
Built on it: <what now rests on the default: the files, the pull request, the steps that followed>
Undo: <how to take the default back if the answer differs, in one line>

A gate acts unless stopped.
The thread acts on its default at once and carries on, and the user sees the question as already acted on.
The default is the option the thread recommends, marked `(default, recommended)`.
A differing answer comes back as a message, and the thread takes the default back.
The first jbus pass that sees the question closes it with its default, by silence.
That close is not the user's word, and a later answer of theirs still replaces it.

There is one exception. When the default is irreversible or slow to revert, the thread does not act. It does the fail-safe instead, and adds two lines under `Undo`, `Holds: <the case>` and `Fail-safe: <what was prepared, with its path or link>`. Then the action waits for the user's answer, and silence never closes it. A default is irreversible or slow to revert when undoing it needs the user, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine. The case is one of these six, word for word:

| Case | Examples | Fail-safe |
|---|---|---|
| deletes data | removing files, folders, branches, a repo, a T3 project or thread, a database, a bucket, a cloud resource | dry-run: list exactly what goes; a backup or bundle first where one can be made; then hold for the user |
| rewrites history | force-push to a shared branch, filter-repo, deleting tags | safety bundle of the old history, verify script, then hold for the user |
| spends money | creating paid cloud resources, raising a plan or a limit, a purchase | the cost estimate or plan, then hold for the user |
| touches prod or real users | a prod deploy, a prod data or schema change, a message to a customer or anyone outside | the plan or diff (`terraform plan`, `cdk diff`, the message text), then hold for the user |
| changes access or secrets | rotating or granting a key or token, tailnet policy or DNS | the diff of the change, then hold for the user (jmerge's protected paths already hold the code side) |
| publishes | a public release, a tag, a package, a public repo or post | the exact artifact and where it goes, then hold for the user |

Everything else acts at once on its default: a merge (reverted by `gh pr revert`), a branch, a brief, a config edit with its backup, a launch. `jbus gate` refuses a gate with no filled `Default:` line, a default that is not the recommended option, a `Holds:` line with no filled `Fail-safe:` line, a case not in the table, and a `Fail-safe:` line with no `Holds:` line.
`jbus gate` asks nothing a rule already settles: a gate with no `Holds:` line whose question asks whether to swarm, whether a `Review: none` pull request merges, whether to write `Fixed:` after a check ended 124, which base a pull request goes on, whether to add a `cross-cutting` label, or whether to wait for the fix of a red that is its base's is refused as `settled:`, with the rule that settles it and what to do instead.
It refuses as `not sent:` a gate with no `Holds:` line whose default waits for the user's word, since the first pass closes it at once and nobody is left to give that word: the default says what is done with no word.

A home that marks a gate `Status: answered` in its own `gates.md` closes a gate with no `Holds:` line, and never one that holds.
Only the user's own answer, read by jbus in T3 Code with `jbus --as user answer <n> --default --message <thread>/<message>` (`--differs` for an answer that is not the default), closes a gate that holds, and that message names the gate's number or its row.
The page of `jbus view` refuses to close a gate that holds.
A word a bot or a home carried, `bot-chat` evidence or typed words, opens no door, whatever it says.
