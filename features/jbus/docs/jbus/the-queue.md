# The queue

The queue holds the rows jbus may launch, one row for each brief.
A pass launches a row only after you approve it.

## Approve a row

A home or the Chef adds the row with its brief.
To approve it from a shell:

1. Read what waits on you:

   ```sh
   jbus queue show
   ```

   Above the table, a row that waits for your go has its own line, with the brief's sha in it:

   ```text
   approve alpha: jbus --project demo queue approve alpha --sha 52e43397dc8c with --word <id>, --answer <number>, --message <thread id>/<message id>, --pick <thread id>/<item id> or --page <session key>/<entry id>
   ```

2. Read the brief you approve, `~/.local/state/jbus/<project>/briefs/<slug>.md`.
   The sha is of that file.
3. Say your go in a T3 Code thread, such as `go alpha`, and record that message with `jbus word`, so jbus keeps your words:

   ```sh
   jbus word --to demo --message <thread id>/<message id>
   ```

   jbus reads the message from T3 Code, and its line ends with the word's id, such as `word 6f6dcb57a29b`.
   The word also goes to the project's home ([Your word to a home](your-word-to-a-home.md)).
4. Approve the row on that word, with the command the first line gave:

   ```sh
   jbus --project demo queue approve alpha --sha 52e43397dc8c --word 6f6dcb57a29b
   ```

   The table's `approved` column now says `your word, <time>, in <thread title>; run <time> by <who>`.

The next pass with room launches the row and prints `launched alpha: <thread id>`.
To take the go back before it launches, run `jbus queue hold alpha`.
A message of yours in a T3 Code thread is a basis too, with `--message <thread id>/<message id>` in place of `--word`.
An answer to a question is another, with `--answer <number>` ([The bases](#the-bases)).

## The table

The queue table is `~/.local/state/jbus/<project>/queue.json`, and `jbus queue show` prints it as Markdown.
It prints only the rows still open.
It leaves out a row that is `merged` or `done` with no reason to wait.
A last line counts the rows it left out, as `<n> finished rows not shown: jbus queue show --all`, or `1 finished row not shown: jbus queue show --all` for one.
`jbus queue show --all` prints every row.
`add`, `approve`, `hold`, `remove`, `withdraw` and `rename` print the open rows after they run, with the same last line.
Each column has one writer.

| Columns | Written by |
|---|---|
| `slug`, `priority`, `depends`, `merge_after`, `approved`, `approval`, `brief_sha`, `held`, `entry`, `item`, `role` | `jbus queue add`, `approve`, `hold`, `remove`, `withdraw` and `rename`, run by a home, the Chef or you. The Chef never runs `remove`, since a removal needs your word. Only `add` writes `entry`, `item`, `merge_after` and `role`, which is `scout` for a scout's request ([What a pass launches](what-a-pass-launches.md#a-scout)) and empty for a crewmate's brief. `hold` sets `held`, and `approve` clears it. |
| `status`, `thread`, `pr`, `checks`, `updated` | A pass, from T3 Code and GitHub. No command takes one, and a pass rewrites a hand edit. |

`jbus queue apply` reads a batch on stdin, one verb to a line.
Each `add` is followed by its brief, between two marker lines:

```
add alpha --priority 1 --depends beta,gamma --merge-after delta
--- brief alpha
# alpha: the brief, as it will be launched
--- end
approve alpha --word 0a1b2c3d4e5f --sha 1a2b3c4d5e6f
approve epsilon --follows alpha
hold delta
```

It applies every verb or none, under one lock, and prints one result line per verb.
If a verb cannot be done, it prints `refused: line <n>: <why>, and nothing in the batch was applied` and exits with code 1.
The verbs run in order, so an `approve` can name the sha of a brief added earlier in the same batch.
Each of the four verbs typed alone is a batch of one, with the brief of an `add` on stdin:

```sh
jbus queue add <slug> --priority <n> --depends <slug>,<slug> --merge-after <slug>,<slug> --entry <entry> < brief.md
jbus queue approve <slug> --sha <sha12> --word <id>
jbus queue hold <slug>
jbus queue remove <slug> --by <user> --at "<YYYY-MM-DD HH:MM zone>"
```

Typed alone, `jbus queue remove` also takes your own words that jbus reads itself, `--message <thread id>/<message id>` or `--page <session key>/<entry id>`, in place of `--by` and `--at`.

Two more verbs let a home undo a row of its own that never launched, and run only typed alone:

```sh
jbus queue rename <old> <new>
jbus queue withdraw <slug> --why "<why>"
```

`add` refuses a brief that another row already has under another slug, while that row is queued, held, at a gate, launched or at a pull request.
Two briefs are the same when they are the same with each one's `# <slug>:` head line taken out, and with the lines a launch writes (`Home:`, `Thread:`, `Green main:`, `Stacked on:`) left out as for a sha.
It prints ``refused: <slug>'s brief is <other>'s (<status>): rename by `jbus queue rename <other> <slug>`, or withdraw one``, and queues nothing.
A row that merged, failed or ended does not count, so a brief can be queued again once its first row is over.

`add` checks the brief when a row is first queued, so you are never asked for a go on a brief that could not launch.
The head must have a `Task:`, `Done when:`, `Proves it:`, `Size:`, `Where:`, `Pull request:`, `Review:` and `Playbook:` line, as `features/jbriefs/templates/brief.md` has them.
Each must be filled in, not left as the template's own text.
A line is not filled in while it, or an item of a list under it, is still the template's `<...>`, bare or quoted.
A `Pull request:` or `Review:` line that still offers its choices (`review | none`) is not filled in either.
These five lines must also hold the right kind of value, and `add` makes more checks besides, in `jbriefs.parse.CHECKS` and `jbus.queue.conduct`:

- `Proves it:` names something outside the agent.
- `Size:` is a t-shirt size.
- `Where:` names at least one path under the repo.
  A path is in backticks, or is a word that has a `/`, a glob character or a file extension.
  Prose and a flag are not paths.
- `Playbook:` names a crewmate's file of `playbooks/`, or `none`.
- `Design:` names a file, or says `none, <why>`.

`add` refuses a brief short of any of these with one line for each fault, and queues nothing:

```text
refused: alpha's brief has 2 faults, and nothing is queued
- brief has no Size: line (S, M or L)
- brief's Playbook: line names autopilot-full, which is not a crewmate's playbook (name a file in playbooks/, without its .md, or none)
```

In a batch, the line is `refused: line <n>: <slug>'s brief has <k> faults, and nothing is queued, and nothing in the batch was applied`, with the same lines under it.
A launch makes none of these checks.
A row with a go is grandfathered, so a check added after the go neither refuses its brief at an `add` nor stops its launch.
When a row's go still holds for its new brief, `add` refuses the row only for a fault the edit brought, not for one the brief already had.
`jbus queue show` ends with two notes, when it has rows for them.
Under the line `grandfathered, approved before a lint that refuses the brief now; the go stands:` it lists each grandfathered row, with the faults a check finds in its stored brief now.
The line `re-asked, the go does not hold for the stored brief: <slugs>` names each row a pass gates as `brief changed after approval`.
When the row had a go and its brief changed, `add` prints a line above the table, `added <slug>: priority <n>, brief <sha12>`.
The line ends `, its go holds` or `, its go does not hold for it: approve it again` ([What an approval is bound to](#what-an-approval-is-bound-to)).

`--priority` is an integer, and the lowest launches first.
`--depends` is optional, and names the slugs that must end before this row launches, or, for the one slug left, open its pull request: the row then launches stacked on that pull request's branch ([What a pass launches](what-a-pass-launches.md)).
A slug ends by a merge, or by a row that ended `done` with no pull request.
Such a row's thread ended, and its last Result says `Status: done`, `Left: none` and a `Branch:` line that is not a URL.
`--merge-after` is optional too, and names the slugs whose pull requests merge before this row's.
It gates the merge and not the launch, so the row launches and its crew works at once.
`jmerge` leaves its pull request with `wait <number> <url>: merges after <slug> (#<n>), not merged yet` until every row it names is `merged` or `done`.
For a row with no pull request open, `no pull request yet` takes the place of `#<n>`.
The order is a column of the row, so a home that declares one writes it here and not in a report.
In `--merge-after`, `add` refuses a slug that is the row itself, that has no row, or that was removed.
It also refuses a slug whose row merges after this one or depends on it, since neither row would ever merge.
`remove` refuses a row that another row merges after, as it refuses one that another row depends on.
`--entry` is optional too, and names the plan entry the row is work for, where that is not the row's own slug.
An `add` of a row that exists sets `--priority`, `--depends` and `--merge-after` anew and keeps the row's entry unless you give `--entry`.
`--entry <the row's own slug>` makes the row its own entry again, and then it takes no entry from a parent it names.
A follow-up with no `--entry` counts for its parent's entry in `jbus plan` ([The plan](the-plan.md)), and keeps it through a `rename` where a `Follows:` line names the parent.
`jbus queue add <slug> --item <id>` links the row to the work item `--item` names ([Work items](work-items.md)).
With no `--item`, a new row gets an item of its own, with source `cli`.
`add` refuses an item that is not there, or that is another row's, and queues nothing.
A row keeps its item, and `add` refuses an `--item` that names another.
`jbus queue add <slug> --from <thread id>` says which home adds the row, and an empty id is the root home.
`add` refuses a row whose brief's `Home:` line names a home other than the one adding it, and queues nothing, so two homes do not brief the same fix unseen.
`jbus queue add --for <home>`, `root` or a scope's name, hands the row over on purpose, and `add` refuses a `--for` that is not the brief's home.
`hold` takes a row's approval back, which stops both its launch and its merge.
A held row that was never launched does not launch.
If its pull request is open, `jmerge` leaves it unmerged, with `wait <number> <url>: its queue row is held: approve it again to let it merge`, until `jbus queue approve` gives the row its go again.
A row with no go is held by `jmerge` too: it leaves the row's pull request unmerged, with `wait <number> <url>: its queue row has no go: the user's go, or the bot's, lets it merge (jbus queue approve)`, until a go is given.
A pull request that no row names is judged as any other.

An approval names its brief.
`--sha` is required with a basis of your word, and it is the first 12 characters of the sha256 of the brief you were shown.
If the stored brief has another sha, `approve` prints `refused: <slug>'s brief is <sha12>, not <given>`.
With no `--sha`, it prints `refused: approve on the user's word needs --sha <sha12>, the first 12 of the sha256 of the brief they were shown; a go by --follows needs none`.

### The bases

An approval also names the words of yours that it is based on.
`jbus queue approve` takes one basis, `--word <id>`, `--answer <number>`, `--message <thread id>/<message id>`, `--pick <thread id>/<item id>` or `--page <session key>/<entry id>`:

| Basis | What it names |
| --- | --- |
| `--word <id>` | A word `jbus word` kept, an act of the project's `acts.jsonl` ([Your word to a home](your-word-to-a-home.md)). |
| `--answer <number>` | The answer that `jbus answer` closed a question of the project's `questions.json` with. An open question, or one its home closed in a `gates.md`, is refused. |
| `--message <thread id>/<message id>` | A message of yours in a T3 Code thread, which jbus reads when you approve, as `jbus word --message` does. |
| `--pick <thread id>/<item id>` | Your answer to a question box in a T3 Code thread, the box Claude Code's AskUserQuestion shows, which T3 Code keeps as an item of the type `user_input_request` with an id `turn-item:runtime-request:<request>`. jbus reads the item with T3 Code's thread read, and reads who answered it, when and with what in T3 Code's own store, `$T3CODE_HOME/userdata/statev2.sqlite` (`~/.t3` by default), read only: the thread read does not say who answered, and an agent can answer a box with `t3_pending_request`. A box whose answer came from T3 Code's app, a command with a bare UUID for its id, is yours; one an MCP client answered, a command id that begins `mcp:`, is an agent's and is refused. The go is for each row a picked label names, the slug standing in the label as a word of its own (`cite-renumber (M)` names `cite-renumber`), so one answer that picks three rows is the go for the three, given with one `approve` for each. Text you typed in place of a label approves nothing. The record keeps the label that names the row and its question as the words, the time the box was answered as when, and the thread's title as where, and the row reads `your pick in a question box, <time>, in <thread>: "<label>", for "<question>"`. jbus refuses, in one line, an item that is not a question box, a box nobody has answered, a box an agent answered, an answer none of whose labels names the row, and a store that is not there. |
| `--page <session key>/<entry id>` | What you sent from a page of Lavish, an optional tool. It is the entry with that `id` in that session's `chat`. jbus reads it at the approval from Lavish's state file, `state.json` under `LAVISH_AXI_STATE_DIR` or `~/.lavish-axi`, and never writes that file. The record keeps the entry's `text` as the words, its `at` as when, and the page's file as where, and the row reads `your pick on a Lavish page, <time>, <page file name>`. jbus refuses, in one line, a state file that is not there, a session or an entry the file does not have, an entry whose `role` is not `user`, and a reference with no `/`. The grilling skill prints the reference of a page's last send. |

It takes no name and no time.
With no basis, with two, or with `--by` or `--at`, it prints `refused: approve takes one basis, --word <id>, --answer <number>, --message <thread id>/<message id>, --pick <thread id>/<item id> or --page <session key>/<entry id>, or --follows <parent slug>, and no --by and no --at: jbus writes who ran it and when`.

There is one more basis, and it is not your word for the row.
A follow-up of approved work needs no new approval: that is the follow-up rule, and jbus knows it by what it says, not by its number in a home's `standing.md`.
A home can approve a follow-up by naming the approved row it follows:

```sh
jbus queue approve <slug> --follows <parent slug>
```

`--follows` goes with none of the bases above.
It takes no `--sha`, since nobody read the brief's sha for a follow-up, and a `--sha` beside it is taken and not read: the go is for the brief jbus stores.
A `--rule <n>` beside it, from the days when jbus read the rule out of `standing.md`, is taken and not read, so `jbus queue approve <slug> --rule 6 --follows <parent slug>` still approves, and a home that renumbers its standing rules breaks nothing.
Any other mix gets the refusal above.
jbus checks the parent and judges nothing else.
The home decides whether the brief is really a follow-up, and you audit that call through the mark on the row and the count in the digest.

- **The parent** is a row of the same queue, or one that was removed after it merged.
  It must have a go that holds for its brief: your word, the typed string of an older row, or the follow-up rule's own, so a chain of follow-ups goes back to your word one go at a time.
  A parent that is no row gets `refused: <slug> cannot follow <parent>: the queue has no row <parent>`, one with no approval gets `refused: <slug> cannot follow <parent>: <parent> has no approval`, and one whose brief changed after its go gets `refused: <slug> cannot follow <parent>: <parent>'s brief changed after its approval`.
- **The ground** is the parent's go: the record keeps the rule's words and the line of that go, and the row reads `the follow-up rule, follow-up of <parent>; run <time> by <who>; you did not speak of this row`.
  A row whose own go from your word still holds is refused: `refused: <slug> has the user's go, which holds, and a follow-up's go would write over it`.

jbus also gives this approval itself, so that a follow-up never asks you and no home approves it.
A row is a follow-up of P when it names P (a line `Follows: P` in its brief's head), when it is a fix row jbus filed or, when it is queued, does work for P's plan entry, and when P passes the parent check above.
A fix row jbus filed is one that jbus's own pass queued (the row's `queued_by`) and whose brief's `Decisions:` line begins `none, jbus filed this from a red`, whatever its slug, with the `Follows:` line jbus writes where a row's merge turned the check red.
Such a fix that names no parent, as for a red check no row's merge caused, is approved by the same rule on the red run its `Task:` line quotes, and reads `the follow-up rule, jbus filed it from the red run "<the run>"; run <time> by jbus's pass; you did not speak of this row`.
The same brief queued by a home or a person is not jbus's, and waits for your go.
Each pass approves every waiting fix row jbus filed whose parent's go holds, before anything launches, and asks again until a round approves none, so a follow-up of a follow-up goes on the same pass.
`queue add` approves such a row in the same write, and so does an `approve` of P, for the waiting rows that name P; there a row that does work for P's plan entry (the same `--entry` as P) is a follow-up too.
A row that names a parent and is no follow-up gets one line from `queue add`, `<slug> waits for the user's go, not a follow-up: <why>`, and waits for your go.
A row whose go an edit voided is approved again only where its brief still follows the parent its go named, and a row your word approved waits for your word again.
A held row stays held, and a `hold` of P takes back the go of every queued follow-up down the chain from P.
The help that `jbus queue add` prints gives the rule.

The row's `approval` field records the approval:

| Field | What it holds |
| --- | --- |
| `basis`, `ref` | `word`, `answer`, `message`, `pick`, `page` or `bot-chat`, and the id, the number or the reference. By rule: `rule` and `follow-up`, or the rule's number for a record made before the rule was known by what it says. |
| `words`, `said_at`, `said_in` | Your words, when you said them, and the title of the thread you said them in, where jbus knows it. By rule: the follow-up rule's words and the line of the parent's go, or the line of the red run for a fix jbus filed, and the other two are empty, since you said nothing of the row. |
| `checked` | `true` when jbus read the words and the time from T3 Code, `false` for words it did not read itself: a typed answer, a word given on the page of `jbus view`, or a word typed before `jbus word` took only `--message`. For a row approved by rule it is `true`, since jbus read the rule itself. |
| `follows` | By rule only: the slug of the parent row. |
| `ground` | By rule only, for a fix jbus filed from a red check, which names no parent: the words that name the red run, which the line says in place of the parent (above). |
| `ran_by`, `ran_at` | The session that ran the command (`CLAUDE_CODE_SESSION_ID`) with its directory, and the time by the clock. No option gives either. |
| `brief_sha` | The sha256 of the stored brief at the go, which `--sha` named for a go on your word. |
| `meaning`, `scope` | The brief's meaning fingerprint at the go, and the sha256 of it. The go holds for any brief that means the same (below). |

`jbus queue show` prints it in the `approved` column as `your word, <said_at>, in <said_in>; run <ran_at> by <who>`, with `(time typed)` after the time where `checked` is false.
`<who>` is `the <directory> home` for a session, and `a shell in <directory>` where no session ran it.
The view's row says the same line.
A row approved by rule prints `the follow-up rule, follow-up of <parent>; run <ran_at> by <who>; you did not speak of this row`, and the view's row says the same and carries a `by rule` mark.
`jbus queue hold <parent>` takes back the parent's go and the go of each of its queued follow-ups.
It prints their slugs on a line above the table, `held <parent>, and <slugs> with it: a follow-up approved by rule has no go without its parent's`.
`jbus queue remove` of a parent that did not merge does the same.
`jbus digest --json` lists each such row under its project's `by_rule`, as `{"slug", "rule", "follows", "at"}`, for the approvals run at or after `--since`.
The length of that list is the count of rows that launched without your word for them.
A row approved before these records existed holds only the typed string.
It keeps its go, still launches, and prints `<the string> (typed, not checked)`.
jbus reads no time out of such a string, so the view gives no time from approval to merge for it.

The sha leaves out the `Home:`, `Thread:`, `Green main:` and `Stacked on:` lines of the brief's head, the lines above its first `## `.
They say whom the brief is sent to and where main last passed, not what it asks for.
jbus keeps the stored brief whole, those lines included.
A launch sends the brief without those four lines, and a row that launches stacked gets its `Stacked on:` line in place of `Green main:`.
It writes its own `Green main: <sha>` line under the brief's first line, both in the brief it sends and in the home's `tasks/<slug>.md`.
The crew rebases onto that sha when main is red.
The sha is the last tip of main whose check passed, `green` in `main.json`.
When jbus knows no such tip, it writes no `Green main:` line.
jbus also writes the launch's own `Thread:` line.

### Who acts, and the acts log

A go, an answer, a hold, a removal, a withdrawal, a word, a work item's go and an accept are acts, and each one, whatever came of it, appends one line to `~/.local/state/jbus/<project>/acts.jsonl`.
`jbus queue approve`, `jbus answer`, `jbus queue hold`, `jbus queue remove`, `jbus queue withdraw`, `jbus word`, each go, hold and remove line of a `jbus queue apply` batch, and `jmerge --accept` in a project of jbus's act on the command line.
The page of `jbus view` acts as you over the view, and the bot acts over its own route, `POST /act` on `jbus view`.
`features/jbus/src/jbus/acts.py` logs every one of them, most through its one function `act`, and the shapes are in `features/jbus/src/jbus/party.py`.

An act's line is JSON with `v: 1`, an `id`, the time `at`, and these:

| Key | What it holds |
| --- | --- |
| `party` | Who acted: `kind` is `user`, `bot`, `home` or `jbus`, and `route` is `cli`, `view` or `bot`. The bot has no name: one bot speaks for you. |
| `action` | `verb`, one of `go`, `answer`, `hold`, `remove`, `withdraw`, `word`, `item` and `accept`, its `subject` (the slug, the question's number, the item's id, or for a word the scope of the home it is for, empty for the root home), the `pre` sha or head it was given, the event it had `seen`, and the `doors` the brief, the gate or the pull request holds for. |
| `evidence` | The words it rests on: `source`, `ref`, `words`, `said_at`, `said_in`, `checked`, true only where jbus read your words and their time itself, and `picks`, each label you picked in a question box with its `question`, empty for every other source. |
| `outcome` | `done`, `gated`, `refused` or `noop`. |
| `line` | What the act printed, and `gate` the number of the gate a `gated` go parked. |

Each basis is one `source`: `--word` is `typed`, `--answer` is `answer`, `--message` is `t3-message`, `--pick` is `t3-pick`, `--page` is `lavish-page`, and the follow-up rule is `rule`.
The bot's words are `bot-chat`, and an answer, a hold, a work item's go and a word given on the view's page are `view`.
The approval record in `queue.json` keeps its fields as before, so a bot's go reads `the bot's go for you, <time>, from bot-chat <address>/<device>; run <time> by the bot`.

On the command line the party is `--as home`, the default, or `--as user`, given before the verb.
`--as user` acts only on words jbus reads itself, `--message`, `--pick` or `--page`, or `--evidence t3-message:<thread>/<message>` in their place.
`--as bot` is refused, with `refused: --as bot: the bot acts only over its own route, POST /act on jbus view, with its key, and on the command line a party is user or home`, so no crew or home acts as the bot.

The page of `jbus view` acts as `user` with the route `view`, on `view` evidence that is not checked, since jbus took the words from the page and not from T3 Code.
So the view opens no door.
Its answer to a gate that holds is refused, and the gate stays open.
Its go on a row whose brief holds keeps a word of the view's and parks a gate for your own word in place of the go.

#### Doors

A door is an action that is irreversible or slow to revert, one of the six cases of the table in [Questions](questions.md#act-unless-stopped-and-the-gates-that-hold), and `party.DOORS` is that table.
A brief holds for a door when a line of its head, above its first `## `, is `Holds: <case>`, with several cases split by commas.
A line that names a case the table does not have holds for every door.
An act on a door goes through only for you, on words jbus read itself.
A go on such a brief from the bot, a home or the view approves nothing: it parks a gate that holds, `may <slug> go? Its brief holds for <case>`, and the act is `gated`.
Your own go, `jbus --as user queue approve <slug> --sha <sha12> --message <thread>/<message>`, or `--pick <thread>/<item>` for your answer to a question box, approves the row and closes that gate.
`jbus queue apply` refuses a batch that approves a brief with a door, and applies nothing of it.

A second go that the row's go already holds for is a `noop`, and writes nothing to the row.
A go given with `jbus queue approve <slug> --sha <sha12> --seen <event id>` is refused as stale when the project's event log has an event for the row after that one, or has no event of that id.
`jbus events` prints the `id` of each event, the one a go names and the feed's cursor: two equal events have two ids, and an id names the same event across restarts and the daily prune.

#### The bot's route

The bot gives a go, an answer or a word with `POST /act?project=<name>` on `jbus view`, with a JSON body, and an address with no known project gets 404:

```
{"action": "go", "slug": "alpha", "sha12": "52e43397dc8c", "evidence": "bot-chat:<address>/<device>", "seen": "<event id>"}
{"action": "answer", "number": 3, "words": "tea", "keeps": true, "evidence": "bot-chat:<address>/<device>"}
{"action": "word", "words": "read vision.md", "evidence": "bot-chat:<address>/<device>"}
```

The evidence of each is `bot-chat:<address>/<device>` with both parts named, and any other, `voice:` included, answers 400.
A word is kept for the project's home and sent to its thread at once, as `jbus word` sends one ([Your word to a home](your-word-to-a-home.md)), and answers 200 with the act and `say`, the line `jbus word` prints for it.

`seen` may be left out, and so may `keeps`, which is false then.
The route takes the bot's key, `Authorization: Bearer <key>`, and refuses any request without the right one with 401, from loopback or any other peer, whatever its `X-Forwarded-For` says.
jbus keeps only the key's sha256, in `~/.local/state/jbus/bot-key.json`, and compares it in constant time.
`jbus bot key` makes a new key, prints it once for you to hand to the bot, and replaces the stored hash: it is yours to run, and it is refused in an agent's session (`CLAUDE_CODE_SESSION_ID` set).
The route checks the request's `Host` as the view's other routes do, and takes no `Origin`.
A refused act answers 409 with its line as `error` and the act as `act`, and a done, gated or noop act answers 200 with the act.
An answer from the bot closes a gate that does not hold; on a gate that holds it is refused, and the gate stays open.

#### The bot's feed

The bot reads what changed with `GET /feed?project=<name>&after=<id>&wait=<seconds>` on `jbus view`, which prints one JSON page.
The page is `{"v": 1, "project", "reset", "cursor", "events"}`, and the next read is after its `cursor`.
Each event is `{"v": 1, "id", "at", "project", "kind", "subject", "line", "need", "act"}`, in the order of the project's log, and each act is an event of the kind `act`, with the act as `acts.jsonl` has it.
`need` is what waits on you about the event's subject now, as `/stack.json`'s `needs` has it, or null.
A cursor the log does not have, an unknown one or one the 14-day prune dropped, or no cursor, gives `reset` true, no events, the newest cursor, and `needs`, everything that waits on you, to catch up from.
On an empty log that cursor is `start`, the start of the log: a read after it gives every event from the first one, and waits like any other.
`wait`, up to 600 seconds, is a long poll: the page comes at the first new event, or empty once the time is up, and a reset never waits.
Each need names its `doors`, the cases of the one door table its action opens, so the bot can tell what it may not act on: a row to approve has those of its brief's `Holds:` lines, a gate those of its own, and any other need none.
Nothing is pushed: the bot has no endpoint, and you want no webhook alarms.

### What an approval is bound to

A go is bound to the goal, the scope and the done-when of the brief, and to nothing else.
A typo fixed, a line re-wrapped, or an edit to `Skills`, `Decisions`, `Design`, `Proves it`, `Review`, `Playbook`, `Pull request` or a note keeps the go.
A change to the title, the `Task`, `Done when`, `Where`, `Do not touch` or `Size` asks you again.
`approve` records the brief's meaning fingerprint (`features/jbriefs/src/jbriefs/meaning.py`), and a later brief keeps the go when its fingerprint is the same.
It is deterministic and asks no model.

The fingerprint reads six fields (`MEANING` in `features/jbriefs/src/jbriefs/meaning.py`): the title, `Task` (the goal), `Done when`, `Where`, `Do not touch` and `Size`.
It leaves out every other (`NOT_MEANING`): `Skills`, `Decisions`, `Design`, `Proves it`, `Review`, `Playbook`, `Pull request`, `Stack`, `Read`, `Change`, `Rests on`, `Sources`, `Ruled out`, `Home` and `Thread`, a field the template does not name, and anything under a `## ` in the brief.
These say how the work is done or who runs it, not what it is for.
A field starts at a line `<Label>: ` of the head, and runs to the next one.
The fingerprint normalises each field in these steps:

1. A list field, such as `Done when:`, is one line for each `- ` item, with the lines an item is wrapped over joined. Any other field is one line.
2. Every code span in backticks, every URL, and every word with a `/`, a `.` inside it or a digit is kept exactly as written, since such a word is a path, a file name or a number.
3. Every other word is lowercased, with the markdown, the punctuation and the white space around it dropped.
   A `n't` is a word of its own, `not`.
   So `shouldn't` becomes the two words `should` and `not`, and the fingerprint never takes a negation for a typo.
   A word of a short fixed list of fillers (`a`, `an`, `the`, `of`, `to`, `in`, `on`, `at`, `for`, `by`, `with`, `is`, `are`, `was`, `be`, `been`, `it`, `its`, `that`, `this`, `as`, `from`, `so`, `then`, `there`) is dropped.
4. The fingerprint sorts the words and exact tokens of a line, and the lines of a field.
5. The value of `Size` is kept whole, lowercased and with its white space collapsed.
6. The fields go in a fixed order, the six above as listed, each present even where the brief has none of it.

Two fingerprints mean the same when each field has the same number of lines in both.
Each approved line must also pair with a line of the new brief that has the same exact tokens and the same words.
A word of five letters or more within two edits of the approved word counts as the same word, so a typo fixed keeps the go.
These edits keep the go:

- a fixed typo
- a change of formatting, punctuation or case
- lines put in another order
- an edit only to the fields the fingerprint leaves out

These edits ask you for a new go:

- a line added to, taken out of or changed in the six fields
- a changed path, number or value
- one of the six fields added

The fingerprint compares words, not meaning.
A reword that swaps one content word for another, `must` for `may` or `all` for `any`, asks you again, by design.
A check with no model cannot tell a harmless synonym from a change of intent.
Two words of five letters or more within two edits of each other also count as one, so that a fixed typo keeps its go.
Some such pairs differ in meaning, such as `files` and `fixes`, and some are opposites, such as `include` and `exclude`, `import` and `export`, or `maximum` and `minimum`.
A swap between two such words keeps the go.

A go recorded before the fingerprint read the title and `Task` has neither in its `meaning`, and holds for any title and `Task`.
The fingerprint does not compare the fields such a go recorded that it no longer reads, so the go keeps holding for the brief it was run for.
A row approved before the fingerprint existed has no `meaning` in its record.
It keeps its go while its stored brief has the sha its row holds, line for line, as before.
That sha is the `brief_sha` of the text, or, for a row approved before the sha left the two lines out, the sha256 of the whole text.

`jbus queue verify <slug>` prints, as JSON, what another reader needs to check that a brief is the one you approved.
It prints the row's `approval` record: its basis, its reference and your words, and the `brief_sha`, `meaning` and `scope` at the go.
It also prints the brief it checked, with its `brief_sha`, `meaning` and `scope`, and whether the go `holds` for it.
The brief `jbus queue verify` checks is the stored one, or the file `--brief <path>` names.
It exits 0 when the go holds, and 1 when it does not or there is no such row.

`jbus queue remove` takes a row out of the queue permanently, and a batch takes the same line without `jbus queue`.
A removal rests on your own words: `--message <thread id>/<message id>` or `--page <session key>/<entry id>`, which jbus reads itself, or typed `--by <user> --at "<YYYY-MM-DD HH:MM zone>"`, with your name as `--by`.
A batch's `remove` line takes only the typed form.
With none of these, or more than one, it prints `refused: remove takes the user's own words, one of --message <thread>/<message>, --page <session>/<entry>, or --by <user> with --at`.
Each removal is an act, a line of `acts.jsonl` ([Who acts, and the acts log](#who-acts-and-the-acts-log)).

One file tells a pass which slugs are gone permanently.
`~/.local/state/jbus/<project>/removed.json` names each removed slug, with who said so and when.
From then on a pass sends no event for that slug, whatever its brief in the home's `tasks/`, its thread or a gate it asked says.
A pass also tells no thread of that slug to carry on.
A pass still settles a thread of the slug whose brief has a done Result with nothing left, or whose pull request merged.
A thread that ended with no Result stays open in T3 Code until you settle it.
A pull request opened for the slug later is still a pull request, so `jmerge` judges it, and jbus tells its crew what it is short of.
The slug is on no list: not in `jbus queue show`, not in `waiting-on-user.json`, not in the digest, and on the view only in the feed of past events.
`jbus queue add` refuses the slug, as a row and in `--depends`.
`jbus gate <slug>` refuses it too, and an answer to a question the slug asked before goes to no thread.

The removal is one line of `transitions.jsonl`, with the row as it was, and one `queue` event, which jbus logs and does not post.
jbus sends no home a message, since a home sees the removal in the queue.
jbus moves its stored copy of the brief to `removed/<slug>.<sha12>.md` in the same directory, and leaves the home's own `tasks/<slug>.md` as it is.

`remove` asks T3 Code and GitHub which threads and pull requests are open at that moment, and refuses in these cases:

| The row | What `remove` prints |
|---|---|
| Another row that is not merged depends on it. | `refused: <slugs> wait on <slug>: remove them first` |
| Its thread is at work. | `refused: <slug> is out: its thread <id> is <status>` |
| Its pull request is open. | `refused: <slug> is out: its pull request #<n> is open` |
| Its pull request merged. | `refused: <slug> merged as #<n>, and a merged row stays` |
| A launch of it has no answer from T3 Code yet. | `refused: <slug> is out: its launch has no answer yet (<the launch record>)` |
| The slug is no row. | `refused: the queue has no row <slug>` |

A thread that ended or was settled does not stop a removal.

A `--by` that is not you is refused, and nothing changes: `refused: only <user> removes a row, on their own words: --by <user>, or --message <thread>/<message> or --page <session>/<entry>, not <by>; a home takes out a row of its own that never launched with jbus queue withdraw`.
In a batch the same refusal applies nothing of the batch.
A home takes out a row of its own that never launched with `jbus queue withdraw` ([A home undoes its own row](#a-home-undoes-its-own-row)).

## A home undoes its own row

A home that queued a row by mistake takes it out or renames it itself, while the row has not launched: it has no thread, and it is queued, held or at a gate.
Neither verb needs your word, since nothing of the row has run.

`jbus queue withdraw <slug> --why "<why>"` takes the row out as a removal does: its line of `transitions.jsonl`, its slug in `removed.json` and its brief kept aside.
Both records keep the `why`, and their `by` is the home that ran the command, as `the flow home`.
It refuses a row that launched, as `refused: <slug> launched, and its crew has it`, and a row that another row waits on, as `remove` does.
jbus's pass withdraws a fix row whose red has gone the same way, with `jbus` as its `by`.

`jbus queue rename <old> <new>` moves the row to a new slug and keeps its priority, depends, merge_after, entry and go.
A row that was its own plan entry keeps `<old>` as its entry, so it stays in that plan entry.
It rewrites the brief's `# <old>:` head line to `# <new>:`, and the rest of the brief is the one the go was given for, so a go that held for the old brief holds for the renamed one.
It prints `renamed <old> to <new>: brief <sha12>, its go holds`, or the same line without `, its go holds` for a row whose go did not hold.
The old slug goes into `removed.json` with `why: renamed to <new>`, so no `add` brings it back, and the pass gives the renamed row a work item of its own.
jbus writes the renamed brief and the table before it retires the old slug, so a rename cut short leaves the row under its new slug with its go.
It refuses a row that launched, a row whose slug another row names in its depends, merge_after, entry or go, a new slug that is taken or was removed, and a new slug that is not a slug.

If `removed.json` does not parse, jbus treats it as it treats a `queue.json` that does not parse.
jbus refuses every `queue` verb until you mend the file, and a pass records `condition <project>: removed.json does not parse`.
Such a pass cannot tell which slugs were removed, so it launches nothing, reads no brief, acts on no thread or pull request except through `jmerge`, and leaves `waiting-on-user.json` as it was.
