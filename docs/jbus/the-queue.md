# The queue

The queue table is `~/.local/state/jbus/<project>/queue.json`, and `jbus queue show` prints it as Markdown. It prints the rows still open: a row that is `merged` or `done` with no reason to wait is left out, and a last line counts them, `<n> finished rows not shown: jbus queue show --all`, or `1 finished row not shown: jbus queue show --all` for one. `jbus queue show --all` prints every row. `add`, `approve`, `hold` and `remove` print the open rows after they run, with the same last line. Each column has one writer.

| Columns | Written by |
|---|---|
| `slug`, `priority`, `depends`, `merge_after`, `approved`, `approval`, `brief_sha`, `held`, `entry`, `item` | The Chef, through four verbs: `add`, `approve`, `hold` and `remove`. Only `add` writes `entry`, `item` and `merge_after`; `hold` sets `held` and `approve` clears it. |
| `status`, `thread`, `pr`, `checks`, `updated` | A pass, from T3 Code and GitHub. No command takes one, and a pass rewrites a hand edit. |

`jbus queue apply` reads a batch on stdin, one verb to a line. Under each `add` comes its brief, between two marker lines:

```
add alpha --priority 1 --depends beta,gamma --merge-after delta
--- brief alpha
# alpha: the brief, as it will be launched
--- end
approve alpha --word 0a1b2c3d4e5f --sha 1a2b3c4d5e6f
approve epsilon --rule 6 --follows alpha --sha 6f5e4d3c2b1a
hold delta
```

It applies every verb or none, under one lock, and prints one result line per verb. A verb that cannot be done is `refused: line <n>: <why>, and nothing in the batch was applied`, with exit code 1. The verbs run in order, so an `approve` can name the sha of a brief added earlier in the same batch. Each of the four verbs typed alone is a batch of one, with the brief of an `add` on stdin:

```sh
jbus queue add <slug> --priority <n> --depends <slug>,<slug> --merge-after <slug>,<slug> --entry <entry> < brief.md
jbus queue approve <slug> --sha <sha12> --word <id>
jbus queue hold <slug>
jbus queue remove <slug> --by <user> --at "<YYYY-MM-DD HH:MM zone>"
```

`add` checks the brief when a row is first queued, so a brief that could not launch is never put to you for a go.
The head must have a `Task:`, `Done when:`, `Proves it:`, `Size:`, `Where:`, `Pull request:`, `Review:` and `Playbook:` line, each filled in and not the template's own text, as `features/jbriefs/templates/brief.md` has them: a line still `<...>`, quoted or as a list item, or a `Pull request:` or `Review:` line still offering its choices (`review | none`), is not filled in.
Its `Proves it:` line must name something outside the agent, its `Size:` line a t-shirt size, its `Where:` line at least one path under the repo (in backticks, or a word with a `/`, a glob or an extension; prose and a flag are not paths), its `Playbook:` line a crewmate's file of `playbooks/` or `none`, and its `Design:` line a file or `none, <why>`.
A brief short of any of these is refused with one line for each fault, and nothing is queued:

```text
refused: alpha's brief has 2 faults, and nothing is queued
- brief has no Size: line (S, M, L or XL)
- brief's Playbook: line names autopilot-full, which is not a crewmate's playbook (name a file in playbooks/, without its .md, or none)
```

In a batch it is `refused: line <n>: <slug>'s brief has <k> faults, and nothing is queued, and nothing in the batch was applied`, with the same lines under it. A launch makes none of these checks: a row with a go is grandfathered, so a check added after the go neither refuses its brief at an `add` nor stops its launch. An `add` of a row whose go holds for the new brief is refused only for a fault the edit brought, not for one the brief already had. `jbus queue show` ends with the rows grandfathered, each with the faults a check finds in its stored brief now, `grandfathered, approved before a lint that refuses the brief now; the go stands:`, and with a line `re-asked, the go does not hold for the stored brief: <slugs>` for each row a pass gates as `brief changed after approval`. When the row had a go and its brief changed, `add` prints a line above the table, `added <slug>: priority <n>, brief <sha12>`, that ends `, its go holds` or `, its go does not hold for it: approve it again` (see [What an approval is bound to](#what-an-approval-is-bound-to)).

`--priority` is an integer, and the lowest launches first.
`--depends` is optional: the slugs that must end before this row launches, each by a merge or by a row that ended `done` with no pull request (its thread ended, and its last Result says `Status: done`, `Left: none` and a `Branch:` line that is no address).
`--merge-after` is optional too: the slugs whose pull requests merge before this row's.
It gates the merge and not the launch, so the row launches and its crew works at once, and `jmerge` leaves its pull request with `wait <number> <url>: merges after <slug> (#<n>), not merged yet` until every row it names is `merged` or `done` (`no pull request yet` stands for the `#<n>` of a row with none open).
The order is a column of the row, so a home that declares one writes it here and not in a report.
`add` refuses a slug that is the row itself, that has no row, that was removed, or whose row merges after this one or depends on it, since neither would ever merge; and `remove` refuses a row that another merges after, as it does one that depends on it.
`--entry` is optional too: the slug of the plan entry the row is work for, where that is not the row's own slug.
An `add` of a row that exists sets `--priority`, `--depends` and `--merge-after` anew and keeps the row's entry unless `--entry` is given.
`--entry <the row's own slug>` makes the row its own entry again.
`jbus queue add <slug> --item <id>` links the row to the work item `--item` names, and with no `--item` a new row gets an item of its own, with source `cli` ([Work items](work-items.md)).
An item that is not there, or that is another row's, is refused, and nothing is queued.
A row keeps its item: an `add` that names another is refused.
`hold` takes a row's approval back, which stops both its launch and its merge: a row that was never launched is not launched, and one whose pull request is open has it left unmerged by `jmerge`, with `wait <number> <url>: its queue row is held: approve it again to let it merge`, until `jbus queue approve` gives the row its go again.
A row that was never approved is not held, and its pull request is judged as any other.

An approval names its brief. `--sha` is required, and it is the first 12 characters of the sha256 of the brief you were shown. `approve` is refused unless the stored brief has that sha: `refused: <slug>'s brief is <sha12>, not <given>`.

An approval also names the words of yours it rests on. `jbus queue approve` takes one basis, `--word <id>`, `--answer <number>`, `--message <thread id>/<message id>` or `--page <session key>/<entry id>`:

| Basis | What it names |
| --- | --- |
| `--word <id>` | A word `jbus word` kept in the project's `words.json`. |
| `--answer <number>` | The answer `jbus answer` closed a question of the project's `questions.json` with. An open question, or one its home closed in a `gates.md`, is refused. |
| `--message <thread id>/<message id>` | A message of yours in a T3 Code thread, which jbus reads then, as `jbus word --message` does. |
| `--page <session key>/<entry id>` | What you sent from a Lavish page: the entry of that session's `chat` with that `id`, which jbus reads then from Lavish's state file, `state.json` under `LAVISH_AXI_STATE_DIR` or `~/.lavish-axi`, and never writes. The record keeps its `text` as the words, its `at` as when, and the page's file as where, and the row reads `his pick on a Lavish page, <time>, <page file name>`. A state file that is not there, a session or an entry it does not have, and an entry whose `role` is not `user` are each refused in one line, and so is a reference with no `/`. The grilling skill prints the reference of a page's last send. |

It takes no name and no time. With no basis, with two, or with `--by` or `--at`, it is `refused: approve takes one basis, --word <id>, --answer <number>, --message <thread id>/<message id> or --page <session key>/<entry id>, or --rule <n> with --follows <parent slug>, and no --by and no --at: jbus writes who ran it and when`.

There is one more basis, and it is not your word for the row. A home approves a follow-up to work you approved by a standing rule of yours, and names the row you did approve:

```sh
jbus queue approve <slug> --sha <sha12> --rule <n> --follows <parent slug>
```

`--rule` and `--follows` go together, and with none of the bases above: any other mix is the refusal above. jbus checks two things and judges nothing else. Whether the brief is a follow-up in substance is the home's call, and the mark on the row and the count in the digest are how you audit it.

- **The rule** is rule `<n>` of the home's `standing.md`, in the home's state directory: the line that starts `<n>. `, read up to the next numbered line or heading. jbus reads the file and never writes it. With no such rule it is `refused: <path> has no rule <n>`.
- **The parent** is a row of the same queue, or one that was removed after it merged, with an approval of its own by `--word`, `--answer`, `--message` or `--page`, or the typed string of an older row. A parent that is no row is `refused: <slug> cannot follow <parent>: the queue has no row <parent>`, and one with none is `refused: <slug> cannot follow <parent>: <parent> has no approval`. A row that another row already follows is refused too, since a rule approval would write over the word its follow-ups rest on: `refused: <slug> cannot follow <parent>: <followers> follow <slug>, and a chain is one step: take his word for <slug>`. A chain is one step: a parent that was itself approved by rule is `refused: <slug> cannot follow <parent>: <parent> was approved by rule <n> as a follow-up of <its parent>, and a chain is one step: follow <its parent>, or take his word for <slug>`.

The row's `approval` is the record of it:

| Field | What it holds |
| --- | --- |
| `basis`, `ref` | `word`, `answer` or `message`, and the id, the number or the `<thread id>/<message id>`. By rule: `rule`, and the rule's number. |
| `words`, `said_at`, `said_in` | Your words, when you said them, and the title of the thread you said them in, where jbus knows it. By rule: the rule's text as `standing.md` had it then, and the other two are empty, since you said nothing of the row. |
| `checked` | `true` when jbus read the words and the time from T3 Code, `false` for a word or an answer that was typed. By rule it is `true`: jbus read the rule itself. |
| `follows` | By rule only: the slug of the parent row. |
| `ran_by`, `ran_at` | The session that ran the command (`CLAUDE_CODE_SESSION_ID`) with its directory, and the time by the clock. No option gives either. |
| `brief_sha` | The sha256 of the brief at the go, as `--sha` named it. |
| `meaning`, `scope` | The brief's meaning fingerprint at the go, and the sha256 of it. The go holds for any brief that means the same (below). |

`jbus queue show` prints it in the `approved` column as `his word, <said_at>, in <said_in>; run <ran_at> by <who>`, with `(time typed)` after the time where `checked` is false. `<who>` is `the <directory> home` for a session, and `a shell in <directory>` where no session ran it. The view's row says the same line. A row approved by rule prints `rule <n>, follow-up of <parent>; run <ran_at> by <who>; he did not speak of this row`, and the view's row says the same and carries a `by rule <n>` mark. `jbus queue hold <parent>` takes the go of its queued follow-ups back with the parent's, and prints their slugs on a line above the table, `held <parent>, and <slugs> with it: a follow-up approved by rule has no go without its parent's`; so does `jbus queue remove` of a parent that did not merge. `jbus digest --json` lists each such row under its project's `by_rule`, as `{"slug", "rule", "follows", "at"}`, for the approvals run at or after `--since`: the length of that list is the count of rows that launched without your word for them. A row approved before this holds only the typed string: it keeps its go and still launches, and prints `<the string> (typed, not checked)`. No time is read out of such a string, so the view gives no time from approval to merge for it.

The sha leaves out the `Home:`, `Thread:` and `Green main:` lines of the brief's head, the lines above its first `## `. They say whom the brief is sent to and where main last passed, not what it asks for. The stored brief is kept whole, those lines included. A launch sends the brief without the three lines, writes its own `Green main: <sha>` under the brief's first line (the last tip of main whose check passed, `green` in `main.json`; no line where none is known) for the crew to rebase onto where main is red, in the brief it sends and in the home's `tasks/<slug>.md`, and jbus writes the launch's own `Thread:` line.

### What an approval is bound to

A go is bound to the goal, the scope and the done-when of the brief, and to nothing else: a typo fixed, a line re-wrapped, or an edit to `Skills`, `Decisions`, `Design`, `Proves it`, `Review`, `Playbook`, `Pull request` or a note keeps it, and a change to the title, the `Task`, `Done when`, `Where`, `Do not touch` or `Size` asks you again.
`approve` records the brief's meaning fingerprint (`features/jbriefs/src/jbriefs/meaning.py`), and a later brief keeps the go when its fingerprint is the same.
It is deterministic and asks no model.

The fingerprint reads six fields (`MEANING` in `features/jbriefs/src/jbriefs/meaning.py`): the title, `Task` (the goal), `Done when`, `Where`, `Do not touch` and `Size`.
It leaves out every other (`NOT_MEANING`): `Skills`, `Decisions`, `Design`, `Proves it`, `Review`, `Playbook`, `Pull request`, `Stack`, `Read`, `Change`, `Rests on`, `Sources`, `Ruled out`, `Home` and `Thread`, a field the template does not name, and anything under a `## ` in the brief.
These say how the work is done or who runs it, not what it is for.
A field starts at a line `<Label>: ` of the head, and runs to the next one.
Each field is normalised in these steps:

1. A list field, such as `Done when:`, is one line for each `- ` item, with the lines an item is wrapped over joined. Any other field is one line.
2. Kept exact, as written: every code span in backticks, every URL, and every word with a `/`, a `.` inside it or a digit, which is a path, a file name or a number.
3. Every other word is lowercased, with the markdown, the punctuation and the white space around it dropped. A `n't` is a word of its own, `not`, so `shouldn't` is `should` and `not` and a negation is never taken for a typo. A word of a short fixed list of fillers (`a`, `an`, `the`, `of`, `to`, `in`, `on`, `at`, `for`, `by`, `with`, `is`, `are`, `was`, `be`, `been`, `it`, `its`, `that`, `this`, `as`, `from`, `so`, `then`, `there`) is dropped.
4. The words and exact tokens of a line are sorted, and so are the lines of a field.
5. The value of `Size` is kept exact whole, lowercased and with its white space collapsed.
6. The fields go in a fixed order, the six above as listed, each present even where the brief has none of it.

Two fingerprints mean the same when each field has as many lines, and each approved line pairs with a line of the new brief whose exact tokens are the same and whose words are the same. A word of five letters or more within two edits of the approved word counts as the same word, so a typo fixed keeps the go. So a typo, a change of formatting, punctuation or case, and lines put in another order keep the go, and so does an edit only to the fields it leaves out. A line added, taken out or changed in the six, a path, a number or a value changed, or a field of them added, ask you again.

Its limit: it compares words, not meaning. A reword that swaps one content word for another, `must` for `may` or `all` for `any`, asks you again, by design: a check with no model cannot tell a harmless synonym from a change of intent. And two words of five letters or more within two edits of each other count as one, which is the price of keeping a fixed typo's go: `files` and `fixes`, and opposites too, `include` and `exclude`, `import` and `export`, `maximum` and `minimum`, so such a swap keeps the go.

A go recorded before the title and `Task` were read has neither in its `meaning`, and holds for any title and `Task`; the fields it recorded that are no longer read are not compared, so such a go keeps holding for the brief it was run for. A row approved before the fingerprint has no `meaning` in its record, and keeps its go while its stored brief has the sha its row holds, line for line, as before: the `brief_sha` of the text, or for a row approved before the sha left the two lines out, the sha256 of the whole text. Queued again with the same text, such a row is taken over to that text's `brief_sha`.

`jbus queue verify <slug>` prints, as JSON, what another reader needs to check that the brief it holds is the one you approved: the row's `approval` record (its basis, its reference and your words, the `brief_sha` and the `meaning` and `scope` at the go), and the brief checked, with its `brief_sha`, `meaning`, `scope` and whether the go `holds` for it. The brief checked is the stored one, or the file `--brief <path>` names. It exits 0 when the go holds, and 1 when it does not or there is no such row.

`jbus queue remove` takes a row out of the queue for good, and a batch takes the same line without `jbus queue`. It is your word, so `--by` is your name.

A pass decides that a slug is gone for good by one file: `~/.local/state/jbus/<project>/removed.json` names each removed slug, with who said so and when. From then on a pass sends no event for that slug, whatever its brief in the home's `tasks/`, its thread or a gate it asked says, and it tells no thread of that slug to carry on. A pass still settles a thread of the slug whose brief has a done Result with nothing left, or whose pull request merged. A thread that ended with no Result stays open in T3 Code until you settle it. A pull request opened for the slug later is still a pull request: `jmerge` judges it, and jbus tells its crew what it is short of. The slug is on no list: not in `jbus queue show`, not in `waiting-on-user.json`, not in the digest, and on the view only in the feed of past events. `jbus queue add` refuses the slug, as a row and in `--depends`. `jbus gate <slug>` refuses it too, and an answer to a question the slug asked before goes to no thread.

The removal is one line of `transitions.jsonl`, with the row as it was, and one `queue` event, which is quiet. No home is sent a message: a home sees the removal in the queue. jbus moves its stored copy of the brief to `removed/<slug>.<sha12>.md` in the same directory, and leaves the home's own `tasks/<slug>.md` as it is.

`remove` asks T3 Code and GitHub what is out at that moment, and is refused in these cases:

| The row | What `remove` prints |
|---|---|
| Another row that is not merged depends on it. | `refused: <slugs> wait on <slug>: remove them first` |
| Its thread is at work. | `refused: <slug> is out: its thread <id> is <status>` |
| Its pull request is open. | `refused: <slug> is out: its pull request #<n> is open` |
| Its pull request merged. | `refused: <slug> merged as #<n>, and a merged row stays` |
| A launch of it has no answer from T3 Code yet. | `refused: <slug> is out: its launch has no answer yet (<the launch record>)` |
| The slug is no row. | `refused: the queue has no row <slug>` |

A thread that ended or was settled stops no removal.

If `removed.json` does not parse, jbus treats it as it treats a `queue.json` that does not parse: every `queue` verb is refused until you mend the file, and a pass sends `gate <project>: removed.json does not parse`. Such a pass cannot tell which slugs were removed, so it launches nothing, reads no brief, acts on no thread or pull request but through `jmerge`, and leaves `waiting-on-user.json` as it was.
