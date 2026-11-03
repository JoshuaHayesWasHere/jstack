# Your word to a home

`jbus word` is for an approval or an instruction that answers no open question.
Your word is a message of yours in a T3 Code thread, and `jbus word --to <project> --message <thread id>/<message id>` names it.
jbus reads the message from T3 Code itself and takes its text and its own time: nothing is typed.
A message that is not your own is refused, `refused: message <ref> is not <user>'s own: T3 Code has it as a <type> by <who>`.
What an agent or jbus sent into a thread is such a message, though T3 Code lists it as a user message.
Without `--message` the command refuses, with `refused: a word is the user's own message, --message <thread id>/<message id>, which jbus reads from T3 Code: a word typed with --by and --at is not taken`.

Your words in the bot's chat are a word too, with `jbus word --to <project> --evidence bot-chat:<address>/<device> --words "<your words>"`, or with the bot's own `{"action": "word", "words": "<your words>", "evidence": "bot-chat:<address>/<device>"}` on `POST /act` ([The bot's route](the-queue.md#the-bots-route)).
jbus cannot read the bot's chat, so their evidence is `bot-chat` with `checked: false`, their time is when jbus kept them, and the party is the home on the command line or the bot on its route.
The evidence is checked as a bot's go is, by `party.chat`: `voice:` or any other source, and a chat with no address or no device, is refused with `refused: --evidence is bot-chat:<address>/<device> or t3-message:<thread>/<message>, not <given>`.
`--words` goes only with `bot-chat` evidence, `--as user` is refused for it since jbus did not read the words, and so is `--scope`, which takes only your own message.
`--evidence t3-message:<thread id>/<message id>` is the same as `--message`.
A bot-chat word never opens a door: a go on it for a row whose brief holds for one parks a gate for your own word in T3 Code ([Doors](the-queue.md#doors)).
A bot-chat word's id hashes the project, the words, you and the address, and no time, so the bot sending the same message again later is the same word and is not sent twice.
A short reply in the bot's chat, such as "Telemetry" or "queue the missing", means what the bot's message before it asked, which jbus cannot read.
So a bot-chat word takes that message with `--answers "<the bot's message>"`, or `"answers"` beside `"words"` on `POST /act`.
jbus keeps it on the word's evidence as `answers`, and the message it carries to the home holds it under your words: `The bot's message these words answer: <the bot's message>`.
`--answers` goes only with `bot-chat` evidence, and is refused otherwise with `refused: --answers goes with --evidence bot-chat:<address>/<device>`.
The same message answering another bot message is still the same word: `answers` is not in its id.

## One party acts on a word

A word of yours is acted on once, by one party: the home that got it, a shell, or the bot.
A party is the session that ran the command, wherever it ran it, a shell with no session in its directory, jbus's pass, or the bot.
When one party has approved a row on a word, an approve on the same word by another party is refused, and nothing is queued: `refused: word <id> was acted on by <party>: <rows>`.
That holds for `--word <id>`, for `--message` on a message of yours in T3 Code, and for the bot's go on a message of its chat, and a word and the message it was said in are one word: the bot's go on its chat message and a home's `--word` on the word kept for that message meet.
So a carried word another party already acted on is not acted on again: the second party tells the first, or you, instead of queuing rows beside it.
The same party approves as many rows on its own word as the word asks for.
A go by the follow-up rule or by a plan entry's go is no act on a word, and your own message in T3 Code that names the row by slug is never refused by this check.

A hold is its party's.
`jbus queue hold` keeps who held the row and when, and its line says so as an approve's does: `held <slug>; run <time> by <party>`.
An approve of a held row by another party is refused, `refused: <slug> is held, run <time> by <party>, and a hold is its party's: ...`, so nobody quietly approves over a hold.
The party that held it approves it again, or your own message or pick in T3 Code does.
A row held before holds named their party has no party, and any party approves it.

A word is an act ([Who acts, and the acts log](the-queue.md#who-acts-and-the-acts-log)), one line of `~/.local/state/jbus/<project>/acts.jsonl` whose verb is `word`.
Its subject is the scope of the home the word is for, empty for the root home.
Its id is the first 12 characters of a hash of the project, the words, you, the time and the message, so the same message for the same project is the same word, and a second run sends nothing again.
Its evidence is your words, their time, the message as `ref`, the title of the thread as `said_in`, and `checked: true`.
Its line is `kept`, or why jbus posts the word to nobody.
What became of the word is in `word-sends.json` in the same directory: the thread that received it and when (`thread`, `sent_at`), or why it has not gone yet (`waits`).

jbus sends the word at once, as one queued message, to the thread id in the home's `home-id` file.
It prints `sent: <project>, to <thread>, word <id>` or `waits: <project>, <why>, word <id>`, and on a second run of a word that went, `already sent: <project>, to <thread>, word <id>`.
The id is what `jbus queue approve --word` takes, and the message the home gets names it too.
A word that could not go waits, and each pass tries it again.

A word goes to the one home of the project that owns its subject, so two homes never act on one word.
It is the home of the briefs, requests and rows the words name by slug, when they are all one home's, and a new slug is a scope's when every brief with its prefix is that scope's.
A word that names the work of two homes goes to the root home.
A word that names none goes to the home it was said in (the thread of `--message`) or recorded by (`--from`), so a scoped home's own word stays in that scope, and otherwise to the root home.
A home that records a word about another home's work with `--from` forwards it to that home, and the command prints `sent: <project>, to the <scope> home at <thread>, word <id>`.

A home is not told a word it recorded itself.
A word said in the home's own thread (`--message` whose thread is the one in that project's `home-id`), or recorded by it (`--from <thread id>`, since no environment variable names the calling thread), is kept with `thread` and `sent_at` set and `skipped` saying why, and the command and the pass post no message for it.
It prints `kept: <project>, not posted, <why>, word <id>`.
The word is still a word: `jbus queue approve --word <id>` takes it.
With `--all` only the recording home's own copy is skipped, and every other home gets it once.
A project with no `home-id` (a home that handed off) is nobody, so the word waits there as any other does.

The root home carries your word to scoped homes with `jbus word --to <project> --message <thread id>/<message id> --scope <scope>`, given again for each scope, or once as `--scope every`.
It keeps one word for each scope and sends it to that home's thread at once, as any word, and prints `sent: <project>, to the <scope> home at <thread>, word <id>`, or why it waits.
A scope that already holds the word, by any path, is not sent it again: that prints `held: <project>, the <scope> home holds word <id>, so it is not sent again`.
`--scope` is refused with `--all`, with a scope the project does not have, and as `every` for a project with no scoped home.

`--to` also names a scratch home, whose thread is in its own `home-id` as a repo's home's is ([A scratch home](a-scratch-home.md)), and `--all` does not reach one.

A word is no event, so it wakes no thread.
The log still has a line for it, which `jbus events` prints.
