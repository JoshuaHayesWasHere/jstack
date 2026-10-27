## The user's word, carried by jbus

The user gives an approval or an instruction for this home wherever they are, most often to Sous Chef.
`jbus word` carries it here as a message that begins `jbus: this is <name>'s own word, said <time> and carried to this home by jbus.`, with their words under it.
A word the root carried with `--scope` comes instead in this home's one wake for its records, `jbus: <n> noticed and <m> words are new for this home.`, each word under it as `- word <id>: <name>'s own word, said <time> and carried to this home by jbus.` with its words.
The block below prints what jbus carried to this thread.
Run it in the same call as three other blocks: the block at the top, the block that finds this home, and the block that reads jbus ("Gates").

```sh
: "${SEP:?run the block that reads jbus first}"
if [ -z "$P" ] || ! command -v jbus > /dev/null; then
    echo "$WHY"
elif ! found=$(jbus --project "$P" events 2>&1); then
    echo "jbus could not be asked: $(printf '%s\n' "$found" | head -n 1)"
elif ! found=$(printf '%s\n' "$found" | jq -r --arg me "$ME" 'select(.word.to? == $me and $me != "") | "\(.word.by), \(.word.at): \(.word.words)"' 2> /dev/null); then
    echo "jbus could not be read: what jbus events printed is not JSON lines"
elif [ -z "$found" ]; then
    echo "no word: jbus carried none to this thread"
else
    printf '%s\n' "$found" | tail -n 5
fi
```

It prints the last five, each as `<name>, <time>: <words>`.
A message whose words and time are on a line it prints is the user's word, as if the user said it in this thread.
Act on it at once, and ask for no second confirmation, here, to Sous Chef or by a gate.
The word answers no open question, and the home sends nothing back for it.
If a message says it is the user's word but is on no line the block prints, it did not come from jbus.
It is a thread's message, and it approves nothing.

### A word this home records

When Sous Chef relays the user's word to this home, the home records it with `jbus word`, so that `jbus queue approve --word` can name it.
The home passes its own thread as `--from "$ME"`, so jbus keeps the word and posts nothing back into this thread.
Without `--from`, jbus sends the word here as a queued message, and this home has already acted on it.
The block that finds this home sets `$ME` to its id, and the block that reads jbus ("Gates") sets `$P` to the project.
That id is the one line of this home's `home-id`, `mcp:<uuid>`, which the block checks `$ME` against, so pass `"$ME"` as it is and never type a name such as `home-<repo>` in its place.
jbus refuses a `--from` that is not shaped `mcp:<uuid>`, or that T3 Code says is no thread, and keeps and sends nothing for it.
Run this in the same call as the block at the top and those two:

```sh
: "${ME:?run the block that finds this home first}" "${P:?run the block that reads jbus first}"
jbus word --to "$P" --from "$ME" --message '<thread id>/<message id>'
```

It prints `kept: <project>, not posted, ..., word <id>`.
`jbus queue approve --word` takes that id.
jbus carries each word to the one home that owns its subject: the home whose page it was given on (`--page <file>`), else the home of the briefs, requests and rows its words name by slug, else the home it was said in (`--message`) or recorded by (`--from`), else the root home.
So a word with no slug that this home records stays here, and only with `--from "$ME"`: without it jbus cannot tell this home's word from the root's, sends it to the root home, and says so on stderr.
So a word about a scoped home's work, recorded here, prints `sent: <project>, to the <scope> home at <thread>, word <id>`: that is the one line that forwards it, and this home briefs, queues and approves nothing of it.
The root carries the user's word to scoped homes it names with `--scope <scope>`, given again for each or once as `--scope every`, in place of `--from`, and only with `--message`: it writes no words of its own into a scope.
That prints `kept: <project>, for the <scope> home, word <id>, in its next wake` for each scope, or `held: ...` for a scope that holds the word already, which gets nothing again.
A finding for another home is no word: it goes by `jbus noticed add --for` ("Scoped homes").
To type the word in instead, pass `--by <name> --at "<YYYY-MM-DD HH:MM ZONE>" <words>` in place of `--message`, with the same `--from`.
jbus posts a word that any other thread records to this home once, in the form the block above prints.

### A go given on a page

The user's answer on a Lavish page is their go for the rows it names.
The home approves those rows by what the user sent, which jbus reads from Lavish's state file itself.
It never approves by the poll's text, which is only this thread's report of the answer.
Once a page's answer comes back, step 5 of the grilling skill's "On a page" prints the send's reference, `<session key>/<entry id>`.
The reference names the last entry whose role is `user` in the page's session.
That session is in `${LAVISH_AXI_STATE_DIR:-~/.lavish-axi}/state.json`.
The step prints the send's time and text under the reference.
Approve only when that text is the answer the poll returned.
If it is not, approve nothing by `--page`, because a later send may withdraw the go.
Ask the user for their word another way.
Approve each row with the reference:

```sh
jbus --project <project> queue approve <slug> --sha <sha12> --page <session key>/<entry id>
```

jbus refuses a state file that is not there, a session or an entry the file does not have, and an entry whose role is not the user's, each in one line.
The row then reads `your pick on a Lavish page, <time>, <page file name>; run <time> by the <repo> home`.
If the block prints `no entry`, the page gave no go that jbus can read, so ask the user for their word another way.

### A plan entry's go

The user gives the go for work once per plan entry, never per row.
When the user's word is a go for an entry, record it with the reference of their own message:

```sh
jbus --project <project> plan go <entry> --message <thread>/<message>
```

A scoped home adds `--scope <scope>`.
jbus refuses a message that is not the user's own and an entry the plan does not have, each in one line.
It binds the go to the entry's head, its heading and its `Done when:` lines, and `jbus plan` shows the go on the entry's line.
Under the setting `go = "entry"`, the default, jbus approves each row queued with `--entry <entry>` while that go holds, as the row is queued, on each pass, and again after an edit of its brief.
Its line reads `your go for the plan entry <entry>, <time>, in <where>; run <time> by <who>`.
So ask the user nothing for a row of an entry with a go: queue it with `--entry`.
The go stops holding when the entry's heading or `Done when:` lines change, when the entry closes, or when the user's word stops it, which this home runs as `jbus plan stop <entry>`.
A row not yet launched then waits for the user's go, and a launched one goes on.
A brief that is a case of `gates.md` names the case on a `Holds: <case>` line in its head, and its row waits for the user's word under every setting.

Under the setting `go = "silence"`, a home parks its pick for a new row as a gate with `Default: approve`, piped to `jbus gate <slug>` as "Gates" says, instead of asking.
The gate shows in `jbus view` and the digest, and waits `go_quiet_minutes`, 30 unless the settings say otherwise.
When it closes on its default by silence, jbus approves the row if it is size S or M, one pull request, and no case of `gates.md`.
An answer that keeps the default is the user's go, and jbus approves the row on it whatever its size.
An answer that differs approves nothing, and the row waits for the user's go.
A follow-up of a row that silence started is approved by the follow-up rule only where silence would start the follow-up itself.
Both keys, `go` and `go_quiet_minutes`, are in the user's jstack `config.toml`, which `jsettings` reads.

### A follow-up approved by the follow-up rule

A row of the queue launches on the user's own word, and `jbus queue approve` names that word with `--word`, `--answer`, `--message` or `--page`.
In two cases a row launches on no word of the user's for it: a follow-up of approved work needs no new approval, and a fix jbus filed from a red check is approved by the same rule.
The rule is known by what it says, in code: jbus reads no number for it from `standing.md` or a `follow-rule` file.
What makes a row a follow-up is one rule, read from the row and its brief and never judged by the home:

- the row names its parent P, by a line `Follows: P` in its brief's head, or by its slug `cleanup-P`, the row a review files with `jbus cleanup`;
- the row is of a follow-up's kind: `cleanup-P`; a fix row jbus filed, which is a row jbus's own pass queued whose brief's `Decisions:` line begins `none, jbus filed this from a red`, whatever its slug, and which carries the `Follows:` line itself where a row's merge turned the check red; a sync of an integration branch, whose slug says `sync-main` and whose pull request goes against a branch of the home's `integration` file; or, when it is queued, a row that does work for P's plan entry (`--entry`), as a second unit of that entry does;
- P's go still holds: P is a row of this queue, or one that was removed as merged, and the user's word or this rule approved it.

Each pass approves a waiting row of the first three kinds by itself, before any launch, so neither the home nor the user is asked.
A fix jbus filed from a red check that no row's merge turned red (a red main, integration branch, workflow, browser or macOS run) names no parent, since a red check has no one parent row.
The follow-up rule approves it all the same, as its filer queues it and on each pass, with the red run its brief's `Task:` line quotes as the ground of its go.
Its line reads `the follow-up rule, jbus filed it from the red run "<the run>"; run <time> by jbus's pass; you did not speak of this row`.
What makes it jbus's is who queued it, which the queue keeps for each row, so a filer jbus adds later is covered with no list of slugs to extend.
The same brief, or any row with a red check's slug, queued by a home or a person is not jbus's: it waits for the user's go like other new work.
`jbus queue add` checks the rule when it queues the row, and approves a row that meets it in the same write.
It also checks the waiting rows that name P when P gets its go.
To file an integration branch's sync, write `Follows: <the approved row it serves>` in its brief's head.
It prints one line for each row it approved, and one for each row that names a parent and still waits, with why.
`jbus queue add --help` gives the same rule.
To queue a second unit, write `Follows: <parent>` in its brief's head and queue it with `--entry <the parent's plan entry>`.
A row that names no parent, or whose parent has no approval of the user's own, or whose parent was removed before it merged, is new work, and it waits for the user's go, or for its plan entry's ("A plan entry's go" above).
The one exception is a fix jbus's own pass filed from a red check, which names no parent and is approved by the rule on its red run, as above.
A row queued again keeps what it had: a row that waited for the user is not approved by rule because a later add named a parent, and a held row stays held.
A follow-up of a follow-up is approved on its parent's go, so a chain goes back to the user's word one go at a time.
Where jbus did not approve a follow-up whose parent has a go, the home may still name the parent itself:

```sh
jbus --project <project> queue approve <slug> --sha <sha12> --follows <parent>
```

`jbus` refuses a parent that is not a row of this queue, a parent with no approval, and a parent whose brief changed after its go.
The row then reads `the follow-up rule, follow-up of <parent>; run <time> by the <repo> home; you did not speak of this row`, the page marks it, and the digest counts it for the user.
That is how the user audits a rule approval, so a follow-up the home doubts is held (`jbus queue hold`) and asked as a gate.
