---
name: home
description: Make this thread the home for the repo it runs in - read the repo's short handoff, plan work with the user, hand each task to a crewmate thread, and hand off to a fresh home before the context grows. Use when the user invokes /home or $home, opens a new thread to continue work in a repo, or asks to pick up where the last thread left off.
user-invocable: true
disable-model-invocation: true
card: "Run the pipeline | 1 | Makes this thread the repo's home. It reads the last home's note and what jbus holds, plans with the operator, writes each brief and launches its crewmate. It does none of the work. | Reach for it when you start or continue work in a repo. | op: the operator; cmd: the start hook"
---

# home

There are no subagents doing the work. Each task is one ordinary thread, and its pull request gets one review, by a reviewer in a new thread that the crewmate launches (`pr-review`). A fix outside `tests/` gets one scoped review, and that is the last: nothing loops. The repo's own checks and its CI decide whether the work is good.

## Where a home's state lives

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
T=$(realpath ~/.claude/skills/home/../../templates)
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
word() { awk 'NF {print $(1); exit}' "${1}" 2> /dev/null; }
was() { sed -n 's/^Was home:[[:space:]]*\([^[:space:]][^[:space:]]*\).*/\1/p' "${1}" 2> /dev/null | head -n 1; }
whose() {
    named=$(sed -n 's/^Home:[[:space:]]*\([^[:space:]]*\).*/\1/p' "${1}" 2> /dev/null | head -n 1)
    found=$H
    if [ -n "$named" ] && [ "$named" != "$(word "$H/home-id")" ] && [ "$named" != "$(was "$H/handoff.md")" ]; then
        for d in "$H"/*/; do
            d=${d%/}
            id=$(word "$d/home-id")
            old=$(was "$d/handoff.md")
            if [ -z "$id$old" ]; then continue; fi
            if [ "${d##*/}" = "$named" ] || [ "$id" = "$named" ] || [ "$old" = "$named" ]; then found=$d; fi
        done
    fi
    echo "$found"
}
```

That is **the block at the top**. Every block below is sh, and its last line makes zsh read them so: without it zsh stops a call at a pattern that matches no file. `$R` is the repo's name, the same from the main checkout and from any worktree of it. `$H` is the repo's state directory, which every home of the repo shares. `whose` prints the directory of the home a brief or a request is, by `jmerge`'s rule ("Merging a pull request that is ready"): a block below asks it whether one is this home's.

`$T` is the `templates/` directory of the repo this skill lives in. Each template there is the one copy of its text: read it when a step names it, not before.

A repo has one root home, and may have scoped homes beside it, each for one goal. A scope is a directory under `$H` that holds a `plan.md`, and never `tasks`, `scouts`, `reports` or `log`. `$M` is this home's own directory: `$H` for the root home, `$H/<scope>` for a scoped one. **The block that finds this home** sets it, from the one `home-id` that holds this thread's id:

```sh
ME='<threadId>'
M=
case $ME in
'') M=$H ;;
*'<'* | *'>'*) ;;
*)
    for f in "$H"/home-id "$H"/*/home-id; do
        if [ -f "$f" ] && [ "$(cat "$f")" = "$ME" ]; then
            M=$(dirname "$f")
            break
        fi
    done ;;
esac
if [ -z "$M" ]; then
    echo "no home: thread $ME is no home of $R now, its id is in no home-id under $H. Nothing is written."
    exit 1
fi
```

Run it after the block at the top, in the same call as each block below that names `$M`, with this thread's id in place of `<threadId>`: the id step 3 of "When a home starts" put on disk. In a session with no tool that gives the id, put nothing in its place: that home is the root's. On `no home:` the call stops there. This thread handed off, or another home took its place: write nothing, and tell the user. A message that reaches such a thread is not its to act on, whoever sent it: run the block under "After the handoff" in `$T/../skills/handoff/SKILL.md` and do what it prints.

| File | Holds | Size |
|---|---|---|
| `$M/handoff.md` | The note the last home left: what is next, what it has out that jbus does not hold, what not to redo, what is uncommitted, and each gate jbus could not take. Rewritten at every handoff, from `handoff.next.md` beside it. | Ten lines, and its gates |
| `$M/plan.md` | The work this home has planned: one entry per task, each with a "Done when" list. | Open tasks only |
| `$M/home-id` | This home's thread id. A scout, a crewmate or a reviewer reads it each time it sends: the root home's for a brief or a request with no `Home:` line, a scoped home's for one that names its scope. | One line |
| `$H/home-thread` | The merge switch, and not this home's id. Empty or missing, jbus runs `jmerge` on each pass, also while a home runs, and the home runs none: it tells the user what jbus logged. An id in it stops jbus's run for the project, and only the home merges. One of the two merges, never both: the block of "Who merges" reads it before every run ("Merging a pull request that is ready"). Set by hand only: no skill and no script writes it. | Empty, or one line |
| `$M/read-seen` | The Result and Report headings step 4 of a start has shown this home, one a line, so each is shown once. | One line per heading |
| `$M/merge-seen` | How many lines of `$H/merge.log` this home has read, so that while jbus merges each `merged` line is relayed once ("Merging a pull request that is ready"). | One number |
| `$M/log/` | Old handoffs, dated. Nobody reads these at start. | Unbounded |
| `$H/notes.md` | Facts about this repo that a new thread would otherwise relearn the hard way. Read when a step needs one of them, not whole at a start. | At most 60 lines |
| `$H/standing.md` | The user's standing rules for this repo's homes, carried from home to home. Read whole at every start. Right after any edit to it, run `jbus snapshot --why "<repo> standing rule <n> <added, changed or removed>"`, so the edit is a commit of its own in `~/.local/state/home`, pushed, and can be undone ("Undo an edit to standing.md" in `docs/state.md`). | Short |
| `$H/tasks/<slug>.md` | A crewmate's brief, and its result, whichever home wrote it. | One page |
| `$H/scouts/<slug>.md` | A scout's request, and its report, whichever home wrote it. | One page |
| `$H/reports/` | The pages a scout or a home makes for the user. | Unbounded |
| `$H/merge.log` | Every line `jmerge` printed, dated: what it merged, each with the command that opens its revert, what waits and is held, and what it swept. | Unbounded |
| `$H/merge-off` | Present when the automatic merge is switched off for the repo: `jmerge` merges nothing here. `/nohome merge` makes it and `/nohome merge on` removes it. | Empty |

## Carry on

Proceed on reversible work without asking: do it, then say what you did and why. Pause for the user's word before four things only: a force-push to a shared branch, a deploy, deleting data, and a message to a customer or to anyone outside. What the user's global instructions or the repo's own instructions tell a thread to confirm first is still confirmed first. When in doubt, act and write down what you did.

For a home, reversible work is the plan, the briefs, the launches and the merge of what is ready. A question only the user can answer does not hold any of it up: "Gates". Planning with the user is not such a question: what the work is for comes from them.

## When a home starts

At every home's start, whether the user typed `/home` or the session-start hook started it, and when a step elsewhere names a step of this section: read `$T/../skills/home/when-a-home-starts.md` now.

## Planning

Planning is a conversation with the user. Its result goes in `plan.md`, not in this thread's memory.

When the shape of the work is not settled (more than one task, or a design choice the user has not made), plan by the grilling skill: read `$T/../skills/grilling/SKILL.md` and work its rounds before writing an entry. A single task the user has already described in full needs no round.

- One entry per task. A task is one pull request's worth of work. If it is larger, split it before anything starts.
- Every entry has a **Done when** list: checks a person or a command can run. It is the stopping rule. Without one, do not start.
- Record a decision the user makes in the entry it belongs to, in their words.
- Write no status in an entry, and change none by hand. An entry has a `Stage:` line, which says where the planning is: `proposed`, `planned`, `parked` or `scouting`. Once a brief of the entry is queued, its status is counted from its queue rows by `jbus plan`, and the `Stage:` line is not read.
- Queue each brief of an entry with `jbus queue add --entry <entry>`, in a repo `jbus plan` answers for and in no other, where the brief's slug is not the entry's own: an entry is often several briefs, and the column is how a row is counted for its entry.

An entry has the shape of `$T/plan-entry.md`: read it before writing the first one.

When `jbus plan` prints `finished: close it` for an entry, run `jbus plan close <entry>` (a scoped home adds `--scope <scope>`). It moves the entry's section, as it is, from `plan.md` to `plan-done.md` beside it, and is refused while a row of the entry is not over. An entry leaves `plan.md` this way and no other: none is deleted by hand, and `plan-done.md` is never read at a start.

A plan of several entries that the user approves in one go runs as a queue: "A queue and its hourly audit" says when it starts and ends, and what the home schedules for it.

## The home does not do the work

A home plans, hands out, and keeps the record. Every task is done by a **crewmate**: a separate thread, in its own worktree, that the user can open, watch and steer. The home does not edit the repo, run its checks, or read a crewmate's diff.

The home does no research of its own: it reads only its state directory, `$H`. Not the code, not the docs, not a diff. What it needs to know from those, a scout finds out.

## Sending a scout

Before writing a brief, ask whether it can be written from what `$H` holds and what the user said. If it can, the home writes the brief itself and no scout goes out. If it cannot be written without research, in the code or in the docs, send a scout.

There are two kinds:

| | Light | Durable |
|---|---|---|
| What it is | the `Explore` agent, run inside this thread | `/scout <slug>` in a thread of its own, titled `scout: <slug>` |
| Pick it when | the home can ask it in a sentence or two, and the answer fits in about 30 lines | the research spans several areas, needs outside docs as well as code, needs anything run, or the user wants to watch |
| Who writes the brief | the home, from the answer | the scout, when the request asks for one |

When in doubt between the two, any one of the durable column's conditions decides for durable.

**A light scout.** Ask the `Explore` agent for the conclusion with its paths and lines, not for file contents, and write the brief from what comes back. Or, with no subagent tool, do it in this thread and keep only the conclusion. The brief may carry that answer in its `Read:`, `Change:` and `Rests on:` lines, so the crewmate does not look for it again. If the answer does not fit in about 30 lines, or leaves the brief still unwritable, send a durable scout instead of asking again.

**A durable scout** is launched like a crewmate:

1. Write the request, `scouts/<slug>.md`, in the shape of `$T/scout-request.md`: read it first. When the research is for a task to hand out, its "Deliver" list asks for the crewmate's brief. Its `Playbook:` line is a row `a scout` runs whose kind of question this is, from what the block in "Handing a task to a crewmate" that prints a row for each playbook prints, or `none`. Then run the block in "Handing a task to a crewmate" that asks for the deeper version, and write what it says into the request. Its `Home:` line is as "Handing a task to a crewmate" says for a brief's: the scope's name for a scoped home, and no line for the root home.

2. Start the scout thread with `t3_thread_launch`. The request must be on disk before this call.

   ```json
   {
     "title": "scout: <slug>",
     "workspaceStrategy": {"type": "worktree", "baseRef": "<default branch>", "branch": "scout-<slug>", "startFromOrigin": true},
     "message": "/scout <slug>"
   }
   ```

   Before this launch, run `uv run --project "$T/.." jroles scout` with the block at the top. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the scout on the model the role map names. When it prints nothing, the call is the one above. Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line. When it exits 75 and prints no JSON, every instance of the role's pool is capped by a usage limit and the line on stderr says until when: make no launch, and say that line. A selection it prints names the instance of the pool it chose as its `instanceId`, and the launch is made with it as printed. Leave the project and modes out, and the model unless `jroles` printed one.

   ```json
   {
     "title": "scout: <slug>",
     "workspaceStrategy": {"type": "worktree", "baseRef": "<default branch>", "branch": "scout-<slug>", "startFromOrigin": true},
     "message": "/scout <slug>",
     "modelSelection": <model selection>
   }
   ```

   The branch is `scout-<slug>`, not the slug: the crewmate that follows takes the slug for its own branch and worktree. Everything else is as "Handing a task to a crewmate" says for its launch: the default branch, what is left out, a lost reply (look for `scout: <slug>`), and a session with no such tool (the user types `/scout <slug>`).
3. Add the line `Thread: <threadId>` to the request, with the block in step 3 of "Handing a task to a crewmate", and give the user the link: `[scout: <slug>](t3-thread://v1/<threadId>)`.

A durable scout gets the check of the machine before its launch, as a crewmate does.

A scout that finishes writes its report under `## Report` in its request and sends this thread one message. It never becomes the crewmate: the crewmate starts later, in a fresh thread, from the brief.

**Launch a scout's brief without showing it** when the user approved the plan entry it is for: an entry agreed in planning or answered on a page. Launch from step 2 of "Handing a task to a crewmate": the brief is on disk already, and the home does not rewrite it. Show it first, and wait for the user's word, in two cases only: the brief changes that entry's "Done when", or the task has no entry the user approved. A brief changes the list when it drops a check, weakens one, or adds an outcome the entry does not ask for. Checks that only say how an entry's line is proven change nothing. To show it, give the path, the lines that differ and what the brief rests on, in a few lines.

## A playbook of the home's own

A row `the home` runs, in what the block in "Handing a task to a crewmate" that prints a row for each playbook prints, is steps for this thread: how to run a queue of tasks, not how to do one. Its name is kept on a `Playbook:` line in the head of `$M/plan.md`, above the first `## ` heading, so the next home works by it too. Open it when a home starts with that line in its plan, and when you take one up. Run this after the block at the top and the block that finds this home, with the playbook's name in place of `<name>`, or with nothing in its place to take the name the plan has:

```sh
name='<name>'
if [ -z "$name" ]; then
    name=$(awk '/^## / {exit} /^Playbook:/ {print $(2); exit}' "$M/plan.md" 2> /dev/null)
fi
case $name in
"" | none) ;;
*)
    f="$T/../playbooks/$name.md"
    if [ "${name#*/}" != "$name" ] || [ ! -f "$f" ]; then
        echo "no playbook: playbooks/ has no $name.md"
    else
        by=$(sed -n 's/^Run by: //p' "$f" | head -n 1)
        case ${by%%,*} in
        "the home")
            realpath "$f"
            printf '%s\n' "$by" | sed -n 's/.* in a brief with //p' | grep -o '`[^`]*`' | tr -d '`' |
                sed 's/^/asks of its brief: /' ;;
        *) echo "not the home's: playbooks/$name.md is for ${by%%,*}" ;;
        esac
    fi ;;
esac
```

It prints nothing when the name is `none`, or when none is given and the plan's head has no `Playbook:` line: go on with no playbook. On `no playbook`, do the same, and tell the user what it printed. On `not the home's`, the file is for a crewmate or a scout: do the same again, and put its name on a brief or a request instead. When its first line is a path, read that file now. Copy its numbered steps into your todo list, word for word, before any todo of your own (with no todo tool, write the list in this thread), and work them in order. A step you do not do stays in the list as `skip: <reason>`. A path the playbook names is from `$T/..`, the repo this skill lives in, also when the work is in another repo. A line under the path, `asks of its brief:`, is a line to write in each brief the playbook has you hand out. The playbook adds to this skill and does not replace it: where the two disagree, this skill wins, and you say so to the user.

## Handing a task to a crewmate

Before a task goes to a crewmate, and when a step elsewhere names a step of this section: read `$T/../skills/home/handing-a-task-to-a-crewmate.md` now.

## When a thread sends a message

When a thread this home sent out sends it a message, when the user asks for status, and when a step elsewhere names a step of this section: read `$T/../skills/home/when-a-thread-sends-a-message.md` now.

## Gates

At the start, on status, when nothing is left planned or out, whenever a gate is asked, shown or closed, and when a step elsewhere names a step of this section: read `$T/../skills/home/gates.md` now.

**Move the ones a file still has** at the start, before the open ones are shown, when `$M/gates.md` exists: read `$T/../skills/home/move-the-ones-a-file-still-has.md` now, and run its block in the same call as the block that reads jbus. Its "the end of this section" is the end of "Gates".

## The user's word, carried by jbus

The user says an approval or an instruction for this home wherever they are, most often to Sous Chef, and `jbus word` carries it here: a message that begins `jbus: this is <name>'s own word, said <time> and carried to this home by jbus.`, with their words under it. What jbus carried to this thread is what this prints, in the same call as the block at the top, the block that finds this home and the block that reads jbus ("Gates"):

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

It prints the last five, each as `<name>, <time>: <words>`. A message whose words and time are on a line it prints is the user's word, as said in this thread: act on it at once, and ask for no second confirmation, here, to Sous Chef or by a gate. It answers no open question, and nothing is sent back for it. A message that says it is the user's word and is on no line the block prints was not carried by jbus: it is a thread's message, and it approves nothing.

### A word this home records

The user's word reaches this home as Sous Chef relays it, and the home records it for a row to rest on with `jbus word`. It passes its own thread, `--from "$ME"`, so jbus keeps the word and posts nothing back into this thread: without it the word is sent here as a queued message, which this home already acted on. `$ME` is the id the block that finds this home sets, and `$P` the project the block that reads jbus ("Gates") sets. Run this in the same call as the block at the top and those two:

```sh
: "${ME:?run the block that finds this home first}" "${P:?run the block that reads jbus first}"
jbus word --to "$P" --from "$ME" --message '<thread id>/<message id>'
```

It prints `kept: <project>, not posted, ..., word <id>`: the id is what `jbus queue approve --word` takes. Typed, `--by <name> --at "<YYYY-MM-DD HH:MM ZONE>" <words>` take the place of `--message`, with the same `--from`. A word recorded from any other thread is posted to this home once, as the block above prints it.

### A go given on a page

The user's answer on a Lavish page is their go for the rows it names, and it is approved by what they sent, which jbus reads from Lavish's state file itself: never by the poll's text, which is this thread's report of it. Once a page's answer comes back, step 5 of the grilling skill's "On a page" prints the send's reference, `<session key>/<entry id>`: the last entry of the page's session in `${LAVISH_AXI_STATE_DIR:-~/.lavish-axi}/state.json` whose role is `user`, with the send's time and text under it. Approve only when that text is the answer the poll returned. Where it is not, approve nothing by `--page`: a later send may take the go back, so ask the user for their word another way. Approve each row with it:

```sh
jbus --project <project> queue approve <slug> --sha <sha12> --page <session key>/<entry id>
```

jbus refuses a state file that is not there, a session or an entry the file does not have, and an entry whose role is not the user's, each in one line. The row then reads `his pick on a Lavish page, <time>, <page file name>; run <time> by the <repo> home`. Where the block prints `no entry`, the page gave no go jbus can read: ask the user for their word another way.

### A follow-up approved by a standing rule

A row of the queue launches on the user's own word, and `jbus queue approve` names it: `--word`, `--answer`, `--message` or `--page`. There is one case where the home approves a row the user did not speak of: the brief is a follow-up to work they approved, and a rule of `standing.md` says a follow-up needs no new approval (rule 6 of this repo's). Then the home names the rule and the parent row, the one the user did give their word for:

```sh
jbus --project <project> queue approve <slug> --sha <sha12> --rule 6 --follows <parent>
```

It is never for new work: new work waits for the user's go, however small it is and whatever entry it is filed under. A follow-up finishes or repairs what the parent row asked for, and asks for no outcome the parent did not. jbus does not judge that, the home does. jbus refuses a parent that is no row of this queue, one with no approval, and one that was itself approved by a rule: a chain is one step, so a follow-up of a follow-up names the first parent or waits for the user. The row then reads `rule 6, follow-up of <parent>; run <time> by the <repo> home; he did not speak of this row`, the page marks it, and the digest counts it for the user: that is how they audit it, so a doubtful one is a gate and not a rule approval.

## Merging a pull request that is ready

At every home's start (step 5), on a `fixed and green` line, and whenever a pull request may be ready to merge: read `$T/../skills/home/merging-a-pull-request-that-is-ready.md` now.

## A queue and its hourly audit

At every home's start (step 5), when a queue playbook (`autopilot-full` or `orchestrate`) is taken up, on each audit tick, when a queue's last entry is set to done, and before a handoff: read `$T/../skills/home/queue-and-its-hourly-audit.md` now. Its "the next section" is "Picking up a thread that stopped", below.

## Picking up a thread that stopped

A thread that stopped with its task unfinished is picked up, not started over: a turn a T3 Code restart cancelled, one that failed at the plan's limit, one the audit printed as `stuck`. Its worktree and its brief hold what it did. The playbook `session-pickup` has the steps: open it with the block of "A playbook of the home's own". It ends in one of two calls.

A thread whose last turn failed on a usage limit, the text `You've hit your weekly limit · resets <time>` or its 5-hour twin, is not carried on in place: its instance is capped until that reset, and the same message fails again. `jbus` does it: its pass reads the failure, writes the cap to the ledger of the instance it ran on, moves the thread to the first instance of its role's pool with headroom with only the `instanceId` changed (`t3_thread_configure`), and sends one queued carry-on, once for the failed run. Every launch goes to that first instance with headroom as well (`jroles` says which instance it chose and why). Where every instance of the pool is capped `jbus` sends one `stall` alert and waits for the first reset. Do the same by hand only where no `jbus` runs: read the thread with `t3_thread_configuration`, call `t3_thread_configure` with that selection and the `instanceId` of the next instance of the pool, then send the carry-on below. Never send a plain carry-on to a thread that failed on a limit.

A message first, when the thread can still take one: `t3_thread_send` to the id on the brief's `Thread:` line, one line, to carry on from its brief and its worktree and to redo nothing that is there.

A new thread on the same worktree when it cannot: the send fails, the thread is archived or gone, or it was sent that message once and the next tick prints it `stuck` again. Find the worktree whose branch is the slug with `git worktree list --porcelain`, from the main checkout. With none, there is nothing to pick up: launch from step 2 of "Handing a task to a crewmate". Add one line to the brief, above its first `## ` heading, so the new thread knows it resumes: `Resume: <date>, the thread before this one stopped. Its work is in this worktree and in the last Result below: redo nothing that is there, and carry on from <the resume point>`. The crew skill reads the brief at its start, and a brief is trusted. Then, on `go` from `room`, the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first):

```json
{
  "title": "crew: <slug>",
  "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<slug>"},
  "message": "/crew <slug>"
}
```

Before this launch, run `uv run --project "$T/.." jroles crew` with the block at the top. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the crewmate on the model the role map names. When it prints nothing, the call is the one above. Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line. When it exits 75 and prints no JSON, every instance of the role's pool is capped by a usage limit and the line on stderr says until when: make no launch, and say that line. A selection it prints names the instance of the pool it chose as its `instanceId`, and the launch is made with it as printed. Leave the project and modes out, and the model unless `jroles` printed one.

```json
{
  "title": "crew: <slug>",
  "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<slug>"},
  "message": "/crew <slug>",
  "modelSelection": <model selection>
}
```

Put the new thread's id on the brief's `Thread:` line with the block of step 3 of "Handing a task to a crewmate", which takes the old line's place, and give the user the link. One writer per worktree: never launch on a worktree whose last thread is `running`.

## A stack the user lands

When the head of `$M/plan.md` names `autopilot-stack` on its `Playbook:` line, or the user lands a stack: read `$T/../skills/home/stack-the-user-lands.md` now.

## Scoped homes

When the root home is asked for status, when the repo has more than one home, or when the user asks for a home scoped to one goal: read `$T/../skills/home/scoped-homes.md` now.

## When to hand off

Read `$T/../skills/handoff/SKILL.md` and do its steps, then stop working in this thread, when any of these is true:

- The planning the user came for is done and the tasks are handed out.
- The user moves to a different piece of work.
- The context is past 300,000 tokens, or this thread has been compacted once. `hooks/home-gauge.sh` tells this thread its count after every tool call from then on, and at 350,000 it refuses every tool call but the ones the handoff makes: only the handoff runs.
- The user says so.

Before the handoff, end the audit of a queue, as "A queue and its hourly audit" says for a home that hands off: it posts into this thread, and the next home schedules its own.

Say it plainly when one of them is reached: "This is a good point to hand off." Do not wait to be asked.
