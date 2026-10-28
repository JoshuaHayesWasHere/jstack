# Your word to a home

`jbus word` is for an approval or an instruction that answers no open question. jbus keeps the word in `~/.local/state/jbus/<project>/words.json` and sends it at once, as one queued message, to the thread id in the home's `home-id` file. It prints `sent: <project>, to <thread>, word <id>` or `waits: <project>, <why>, word <id>`, and on a second run of a word that went, `already sent: <project>, to <thread>, word <id>`. The id is what `jbus queue approve --word` takes, and the message the home gets names it too. A word that could not go waits in the file, and each pass tries it again. The same words with the same `--by` and `--at` for the same project are the same word, and a second run sends nothing again.

A word goes to the one home of the project that owns its subject, so two homes never act on one word.
With `jbus word --page <file>`, that is the home whose page the word was given on: a page under a scope's directory, or one named for a brief or a request, as `reports/<slug>/` is.
Otherwise it is the home of the briefs, requests and rows the words name by slug, when they are all one home's, and a new slug is a scope's when every brief with its prefix is that scope's.
A word that names the work of two homes goes to the root home.
A word that names none goes to the home it was said in (the thread of `--message`) or recorded by (`--from`), so a scoped home's own word stays in that scope, and otherwise to the root home.
A word with neither `--from` nor `--message` that goes to the root home of a project with scoped homes gets a line on stderr saying so, since jbus cannot tell whether a scope said it.
A home that records a word about another home's work with `--from` forwards it to that home, and the command prints `sent: <project>, to the <scope> home at <thread>, word <id>`.

A home is not told a word it recorded itself. A word said in the home's own thread (`--message` whose thread is the one in that project's `home-id`), or recorded by it (`--from <thread id>`, since no environment variable names the calling thread), is kept with `thread` and `sent_at` set and `skipped` saying why, and the command and the pass post no message for it. It prints `kept: <project>, not posted, <why>, word <id>`. The word is still a word: `jbus queue approve --word <id>` takes it. With `--all` only the recording home's own copy is skipped, and every other home gets it once. A project with no `home-id` (a home that handed off) is nobody, so the word waits there as any other does.

With `--message <thread id>/<message id>`, jbus reads the message from T3 Code itself and takes its text and its own time: nothing is typed. A message that is not your own is refused, `refused: message <ref> is not <user>'s own: T3 Code has it as a <type> by <who>`. What an agent or jbus sent into a thread is such a message, though T3 Code lists it as a user message. The record then has `ref`, the title of the thread as `said_in`, and `checked: true`. The typed form, `--by` and `--at` with the words, is still taken, and its record has `checked: false`: jbus checks the name and the form of the time, and cannot check that you said it then. `--message` with `--by`, `--at` or words is refused.

The root home carries your word to scoped homes with `jbus word --to <project> --message <thread id>/<message id> --scope <scope>`, given again for each scope, or once as `--scope every`.
It keeps one record of the word for each scope and sends it to that home's thread at once, as any word, and prints `sent: <project>, to the <scope> home at <thread>, word <id>`, or why it waits.
A scope that already holds the word, by any path, is not sent it again: that prints `held: <project>, the <scope> home holds word <id>, so it is not sent again`.
`--scope` takes only `--message`, so the root writes no words of its own, and it is refused with `--all`, with a scope the project does not have, and as `every` for a project with no scoped home.

`--to` also names a scratch home, whose thread is in its own `home-id` as a repo's home's is ([A scratch home](a-scratch-home.md)), and `--all` does not reach one.

A word is no event, so it wakes no thread.
The log still has a line for it, which `jbus events` prints.
