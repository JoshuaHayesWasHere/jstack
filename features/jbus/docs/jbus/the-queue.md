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
   approve alpha: jbus --project demo queue approve alpha --sha 52e43397dc8c with --word <id>, --answer <number>, --message <thread id>/<message id> or --page <session key>/<entry id>
   ```

2. Read the brief you approve, `~/.local/state/jbus/<project>/briefs/<slug>.md`.
   The sha is of that file.
3. Record your go with `jbus word`, so jbus keeps your words:

   ```sh
   jbus word --to demo --by <user> --at "<YYYY-MM-DD HH:MM zone>" go alpha
   ```

   Its line ends with the word's id, such as `word 6f6dcb57a29b`.
   `<user>` is the `user` of your jstack config, and the word also goes to the project's home.
4. Approve the row on that word, with the command the first line gave:

   ```sh
   jbus --project demo queue approve alpha --sha 52e43397dc8c --word 6f6dcb57a29b
   ```

   The table's `approved` column now says `your word, <time> (time typed); run <time> by <who>`.

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
`add`, `approve`, `hold` and `remove` print the open rows after they run, with the same last line.
Each column has one writer.

| Columns | Written by |
|---|---|
| `slug`, `priority`, `depends`, `merge_after`, `approved`, `approval`, `brief_sha`, `held`, `entry`, `item` | `jbus queue add`, `approve`, `hold` and `remove`, run by a home, the Chef or you. The Chef never runs `remove`, since a removal needs your word. Only `add` writes `entry`, `item` and `merge_after`. `hold` sets `held`, and `approve` clears it. |
| `status`, `thread`, `pr`, `checks`, `updated` | A pass, from T3 Code and GitHub. No command takes one, and a pass rewrites a hand edit. |

`jbus queue apply` reads a batch on stdin, one verb to a line.
Each `add` is followed by its brief, between two marker lines:

```
add alpha --priority 1 --depends beta,gamma --merge-after delta
--- brief alpha
# alpha: the brief, as it will be launched
--- end
approve alpha --word 0a1b2c3d4e5f --sha 1a2b3c4d5e6f
approve epsilon --rule 6 --follows alpha --sha 6f5e4d3c2b1a
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

`add` checks the brief when a row is first queued, so you are never asked for a go on a brief that could not launch.
The head must have a `Task:`, `Done when:`, `Proves it:`, `Size:`, `Where:`, `Pull request:`, `Review:` and `Playbook:` line, as `features/jbriefs/templates/brief.md` has them.
Each must be filled in, not left as the template's own text.
A line is not filled in while it, or an item of a list under it, is still the template's `<...>`, bare or quoted.
A `Pull request:` or `Review:` line that still offers its choices (`review | none`) is not filled in either.
Five lines must also hold the right kind of value:

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
- brief has no Size: line (S, M, L or XL)
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
`--depends` is optional, and names the slugs that must end before this row launches.
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
`--entry <the row's own slug>` makes the row its own entry again.
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
A row that was never approved is not held, and `jmerge` judges its pull request as any other.

An approval names its brief.
`--sha` is required, and it is the first 12 characters of the sha256 of the brief you were shown.
If the stored brief has another sha, `approve` prints `refused: <slug>'s brief is <sha12>, not <given>`.

### The bases

An approval also names the words of yours that it is based on.
`jbus queue approve` takes one basis, `--word <id>`, `--answer <number>`, `--message <thread id>/<message id>` or `--page <session key>/<entry id>`:

| Basis | What it names |
| --- | --- |
| `--word <id>` | A word `jbus word` kept in the project's `words.json`. |
| `--answer <number>` | The answer that `jbus answer` closed a question of the project's `questions.json` with. An open question, or one its home closed in a `gates.md`, is refused. |
| `--message <thread id>/<message id>` | A message of yours in a T3 Code thread, which jbus reads when you approve, as `jbus word --message` does. |
| `--page <session key>/<entry id>` | What you sent from a page of Lavish, an optional tool. It is the entry with that `id` in that session's `chat`. jbus reads it at the approval from Lavish's state file, `state.json` under `LAVISH_AXI_STATE_DIR` or `~/.lavish-axi`, and never writes that file. The record keeps the entry's `text` as the words, its `at` as when, and the page's file as where, and the row reads `your pick on a Lavish page, <time>, <page file name>`. jbus refuses, in one line, a state file that is not there, a session or an entry the file does not have, an entry whose `role` is not `user`, and a reference with no `/`. The grilling skill prints the reference of a page's last send. |

It takes no name and no time.
With no basis, with two, or with `--by` or `--at`, it prints `refused: approve takes one basis, --word <id>, --answer <number>, --message <thread id>/<message id> or --page <session key>/<entry id>, or --rule <n> with --follows <parent slug>, and no --by and no --at: jbus writes who ran it and when`.

There is one more basis, and it is not your word for the row.
A home can approve a follow-up of work you approved by citing one of your standing rules, and it names the row you did approve:

```sh
jbus queue approve <slug> --sha <sha12> --rule <n> --follows <parent slug>
```

`--rule` and `--follows` go together, and with none of the bases above.
Any other mix gets the refusal above.
jbus checks two things and judges nothing else.
The home decides whether the brief is really a follow-up, and you audit that call through the mark on the row and the count in the digest.

- **The rule** is rule `<n>` of the home's `standing.md`, in the home's state directory: the line that starts `<n>. `, read up to the next numbered line or heading.
  jbus reads the file and never writes it.
  If the file has no such rule, `approve` prints `refused: <path> has no rule <n>`.
- **The parent** is a row of the same queue, or one that was removed after it merged.
  It must have an approval of its own, by `--word`, `--answer`, `--message` or `--page`, or as the typed string of an older row.
  A parent that is no row gets `refused: <slug> cannot follow <parent>: the queue has no row <parent>`, and one with no approval gets `refused: <slug> cannot follow <parent>: <parent> has no approval`.
  `approve` also refuses a rule approval for a row that another row already follows.
  Such an approval would write over the word that the follow-ups are based on: `refused: <slug> cannot follow <parent>: <followers> follow <slug>, and a chain is one step: take the user's word for <slug>`.
  A chain is one step.
  A parent that was itself approved by rule gets `refused: <slug> cannot follow <parent>: <parent> was approved by rule <n> as a follow-up of <its parent>, and a chain is one step: follow <its parent>, or take the user's word for <slug>`.

jbus also gives this approval itself, when `queue add` queues a follow-up, so that a follow-up never asks you.
A row is a follow-up of P when it names P (a line `Follows: P` in its brief's head, or the slug `cleanup-P`), when it is P's (the slug `cleanup-P`, or the same `--entry` as P), and when P passes the parent checks above.
The rule is the one that the home's `follow-rule` file names, one number on one line, and a home with no such file gets no approval by rule from jbus.
`queue add` approves such a row in the same write, and so does an `approve` by your word of P, for the waiting rows that name P.
A row that names a parent and is no follow-up gets one line, `<slug> waits for the user's go, not a follow-up by rule <n>: <why>`, and waits for your go.
A row that was queued already, and waited for you, is not approved by a later `add`, and a held row stays held.
The help that `jbus queue add` prints gives the rule.

The row's `approval` field records the approval:

| Field | What it holds |
| --- | --- |
| `basis`, `ref` | `word`, `answer` or `message`, and the id, the number or the `<thread id>/<message id>`. By rule: `rule`, and the rule's number. |
| `words`, `said_at`, `said_in` | Your words, when you said them, and the title of the thread you said them in, where jbus knows it. By rule: the rule's text as `standing.md` had it then, and the other two are empty, since you said nothing of the row. |
| `checked` | `true` when jbus read the words and the time from T3 Code, `false` for a word or an answer that was typed. For a row approved by rule it is `true`, since jbus read the rule itself. |
| `follows` | By rule only: the slug of the parent row. |
| `ran_by`, `ran_at` | The session that ran the command (`CLAUDE_CODE_SESSION_ID`) with its directory, and the time by the clock. No option gives either. |
| `brief_sha` | The sha256 of the brief at the go, as `--sha` named it. |
| `meaning`, `scope` | The brief's meaning fingerprint at the go, and the sha256 of it. The go holds for any brief that means the same (below). |

`jbus queue show` prints it in the `approved` column as `your word, <said_at>, in <said_in>; run <ran_at> by <who>`, with `(time typed)` after the time where `checked` is false.
`<who>` is `the <directory> home` for a session, and `a shell in <directory>` where no session ran it.
The view's row says the same line.
A row approved by rule prints `rule <n>, follow-up of <parent>; run <ran_at> by <who>; you did not speak of this row`, and the view's row says the same and carries a `by rule <n>` mark.
`jbus queue hold <parent>` takes back the parent's go and the go of each of its queued follow-ups.
It prints their slugs on a line above the table, `held <parent>, and <slugs> with it: a follow-up approved by rule has no go without its parent's`.
`jbus queue remove` of a parent that did not merge does the same.
`jbus digest --json` lists each such row under its project's `by_rule`, as `{"slug", "rule", "follows", "at"}`, for the approvals run at or after `--since`.
The length of that list is the count of rows that launched without your word for them.
A row approved before these records existed holds only the typed string.
It keeps its go, still launches, and prints `<the string> (typed, not checked)`.
jbus reads no time out of such a string, so the view gives no time from approval to merge for it.

The sha leaves out the `Home:`, `Thread:` and `Green main:` lines of the brief's head, the lines above its first `## `.
They say whom the brief is sent to and where main last passed, not what it asks for.
jbus keeps the stored brief whole, those lines included.
A launch sends the brief without the three lines.
It writes its own `Green main: <sha>` line under the brief's first line, both in the brief it sends and in the home's `tasks/<slug>.md`.
The crew rebases onto that sha when main is red.
The sha is the last tip of main whose check passed, `green` in `main.json`.
When jbus knows no such tip, it writes no `Green main:` line.
jbus also writes the launch's own `Thread:` line.

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
The first time such a row is queued again while its go still holds for the stored brief, jbus binds the go to that brief's fingerprint, once, in the row's `rebound` column.
From then on the go holds as a fingerprint's does, so a new `Home:` or `Thread:` line, or any other edit that keeps the meaning, keeps it.

`jbus queue verify <slug>` prints, as JSON, what another reader needs to check that a brief is the one you approved.
It prints the row's `approval` record: its basis, its reference and your words, and the `brief_sha`, `meaning` and `scope` at the go.
It also prints the brief it checked, with its `brief_sha`, `meaning` and `scope`, and whether the go `holds` for it.
It prints `rebound`, the fingerprint an older go was bound to, empty for any other go.
The brief `jbus queue verify` checks is the stored one, or the file `--brief <path>` names.
It exits 0 when the go holds, and 1 when it does not or there is no such row.

`jbus queue remove` takes a row out of the queue permanently, and a batch takes the same line without `jbus queue`.
A removal is your word, so `--by` is your name.

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

If `removed.json` does not parse, jbus treats it as it treats a `queue.json` that does not parse.
jbus refuses every `queue` verb until you mend the file, and a pass records `condition <project>: removed.json does not parse`.
Such a pass cannot tell which slugs were removed, so it launches nothing, reads no brief, acts on no thread or pull request except through `jmerge`, and leaves `waiting-on-user.json` as it was.
