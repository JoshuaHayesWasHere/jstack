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
whose() { if [ -z "${1}" ]; then echo "$H"; else uv run --project "$T/../source" jbus home --directory "${1}"; fi; }
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
```

That is **the block at the top**.
Every block below is sh, and its last line makes zsh read them so: without it zsh stops a call at a pattern that matches no file.
`$R` is the repo's name, the same from the main checkout and from any worktree of it.
`$H` is the repo's state directory, which every home of the repo shares.
`whose` prints the directory of the home a brief or a request is, by the one rule `jmerge`, jbus and every thread ask (`jbus home`, "Merging a pull request that is ready"): a block below asks it whether one is this home's.

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
        if [ -f "$f" ] && [ "$(awk 'NF {print $(1); exit}' "$f")" = "$ME" ]; then
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
| `$M/blockers.json` | Each blocker this home briefed a fix of, with each fix queued for it, which `jbus queue add` counts against the retry cap and writes: never by hand ("Clearing its own blockers"). | One entry per blocker |
| `$M/home-id` | This home's thread id. A scout, a crewmate or a reviewer reads it each time it sends: the root home's for a brief or a request with no `Home:` line, a scoped home's for one that names its scope. | One line |
| `$H/home-thread` | The sweep switch, and not this home's id. An id in it has the home run `jmerge --sweep` at its start, and empty or missing nobody sweeps ("Merging a pull request that is ready", "Who sweeps"). It decides nothing of the merge: jbus runs `jmerge` on each pass whatever it holds, and no home merges. Set by hand only: no skill and no script writes it. | Empty, or one line |
| `$M/read-seen` | The Result and Report headings step 4 of a start has shown this home, one a line, so each is shown once. | One line per heading |
| `$M/told` | Each decision and stop a turn's end told the user, one a line, so each is told once, and each `local` one is shown on status until a `cleared local` line ends it ("How a turn ends"). | One line per decision or stop |
| `$M/merge-seen` | How many lines of `$H/merge.log` this home has read, so that each `merged` line of jbus's is relayed once ("Merging a pull request that is ready"). | One number |
| `$M/log/` | Old handoffs, dated. Nobody reads these at start. | Unbounded |
| `$H/notes.md` | Facts about this repo that a new thread would otherwise relearn the hard way. Read when a step needs one of them, not whole at a start. | At most 60 lines |
| `$H/standing.md` | The user's standing rules for this repo's homes, carried from home to home. Read whole at every start. Right after any edit to it, run `jbus snapshot --why "<repo> standing rule <n> <added, changed or removed>"`, so the edit is a commit of its own in `~/.local/state/home`, pushed, and can be undone ("Undo an edit to standing.md" in `features/home/docs/state.md`). | Short |
| `$H/tasks/<slug>.md` | A crewmate's brief, and its result, whichever home wrote it. | One page |
| `$H/scouts/<slug>.md` | A scout's request, and its report, whichever home wrote it. | One page |
| `$H/reports/` | The pages a scout or a home makes for the user. | Unbounded |
| `$H/merge.log` | Every line `jmerge` printed, dated: what it merged, each with the command that opens its revert, what waits and is held, and what it swept. | Unbounded |
| `$H/merge-off` | Present when the automatic merge is switched off for the repo: `jmerge` merges nothing here. `/nohome merge` makes it and `/nohome merge on` removes it. | Empty |

## Carry on

Proceed on reversible work without asking: do it, and write down what you did and why.
Pause for the user's word before four things only: a force-push to a shared branch, a deploy, deleting data, and a message to a customer or to anyone outside.
What the user's global instructions or the repo's own instructions tell a thread to confirm first is still confirmed first.
When in doubt, act and write down what you did.
Where no rule or script decides, weigh the work by jstack's vision and the user's judgment in `features/home/docs/vision.md`.

For a home, reversible work is the plan, the briefs, the launches and the merge of what is ready. A question only the user can answer does not hold any of it up: "Gates". Planning with the user is not such a question: what the work is for comes from them.

## How a turn ends

A turn ends with no message to the user unless it asks a decision that is theirs or reports a stop nothing else can clear.
A merge, a launch, a stuck thread dealt with, a Result read, a report written and a wait are told when the user asks for status, and at no other time.
A turn the user started with a question (status, why, where, what) answers it in full, and is the one turn this section does not end.
Every other turn ends here: one a thread, jbus or an audit tick started, a home's start, and a turn the user started with an instruction ("launch it", "fix that").

Write each thing the turn did as one line, its kind first:

- `decision <key>: <the question and the default taken>`: the user has to decide it.
- `stop <key>: <what stopped and why>`: the work cannot go on, and nothing but the user can clear it.
- `merged:`, `launched:`, `handled:`, `parked:` or `waits:`, then what it was: these are told on status only.
- `cleared local <slug>: <how it ended>`: a `local` decision or stop this home told has ended.

The key names a decision or a stop so the same one has the same key on every turn:

- `question <n>`: a question jbus holds, by its number (`jbus gate`, "Show the open ones").
- `jbus`: an event jbus's wake carried, and the rest of the line is its line as jbus sent it, word for word.
- `local <slug>`: one jbus does not hold, by the slug it is about: a gate jbus could not take, or a stop this home found, such as a launch this session has no tool for.

A blocker `jbus clear` prints as `decision` is raised by jbus itself, and its wake brings it: write no line for it until then.
A wait, a hold and a stalled thread are no stop while jbus or a thread is at work on them: jbus lists each on what waits on the user ("Needs you").
Rows held by one reason that no thread works on for 30 minutes are a stop: jbus wakes their home once, with the reason, the rows and how long they have been held, and lists the hold on "Needs you" until it clears or a thread takes it up.

Run this in one call with the block at the top and the block that finds this home, with the turn's lines in place of the line in angle brackets:

```sh
the_turn() {
    cat << 'THE_TURN_ENDS_HERE'
<what this turn did, one line each>
THE_TURN_ENDS_HERE
}
said=$(the_turn)
told="${M:?run the block that finds this home first}/told"
printf '%s\n' "$said" | awk -v told="$told" '
    function key(line) {
        if (!match(line, /^(decision|stop) (question [0-9]+|local [^ :]+|jbus): ./)) return ""
        split(line, word, " ")
        return (word[2] == "jbus:") ? line : substr(line, 1, RLENGTH - 3)
    }
    BEGIN { while ((getline line < told) > 0) if (key(line) != "") kept[++k] = line }
    /^[[:space:]]*$/ { next }
    $(1) ~ /^(merged|launched|handled|parked|waits):$/ { next }
    $(1) == "cleared" && match($(0), /^cleared local [^ :]+: ./) {
        ends[substr($(3), 1, length($(3)) - 1)] = 1
        next
    }
    $(1) ~ /^(decision|stop):?$/ {
        if (key($(0)) == "") {
            bad[++b] = $(0) ": a decision or a stop names its key first: question <n>, jbus or local <slug>"
            next
        }
        mine[++m] = $(0)
        next
    }
    { bad[++b] = $(0) ": its kind is none of decision, stop, merged, launched, handled, parked, waits, cleared local <slug>" }
    END {
        if (b) {
            for (i = 1; i <= b; i++) print "refused: " bad[i]
            exit 2
        }
        for (i = 1; i <= k; i++) {
            split(kept[i], word, " ")
            if (word[2] == "local" && (substr(word[3], 1, length(word[3]) - 1) in ends)) {
                changed = 1
                continue
            }
            open[++o] = kept[i]
            seen[key(kept[i])] = 1
        }
        for (i = 1; i <= m; i++) if (!(key(mine[i]) in seen)) {
            seen[key(mine[i])] = 1
            tell[++n] = mine[i]
            open[++o] = mine[i]
            changed = 1
        }
        if (changed) {
            for (i = 1; i <= o; i++) print open[i] > (told ".new")
            close(told ".new")
            system("mv \"" told ".new\" \"" told "\"")
        }
        if (!n) print "silent: end the turn with no message"
        for (i = 1; i <= n; i++) print "say: " tell[i]
    }'
```

On `silent`, end the turn and write nothing more: no recap, no acknowledgment, no line saying nothing changed.
On `say:`, tell the user each line after `say: `, in its order, and nothing else.
On `refused:`, nothing is marked told: mend the line it names and run the block again.
A decision or a stop is told once, by its key, and the block keeps its line in `$M/told`.
A `question <n>` or `jbus` one is in jbus's list of what waits on the user from then on, and is shown again only when the user asks for status.
A `local <slug>` one is in no list of jbus's, so status shows it from `$M/told` ("When a thread sends a message") until it ends.
When it ends (the gate is answered, the stack lands, the tool is there), write `cleared local <slug>: <how it ended>` as a line of that turn: it is quiet, it takes that slug's lines out of `$M/told`, and the same stop coming back later is told again.

## When a home starts

At every home's start, whether the user typed `/home` or the session-start hook started it, and when a step elsewhere names a step of this section: read `$T/../skills/home/when-a-home-starts.md` now.

When `/home` is typed in a thread that runs in no git repo, as T3 Code's "No project" at `~/.t3/scratch`, it is a scratch home: read `$T/../skills/home/a-scratch-home.md` now, in place of the file above and the rest of this skill.

## Planning

Planning is a conversation with the user. Its result goes in `plan.md`, not in this thread's memory.

When the shape of the work is not settled (more than one task, or a design choice the user has not made), plan by the grilling skill: read `$T/../skills/grilling/SKILL.md` and work its rounds before writing an entry. A single task the user has already described in full needs no round.

- One entry per task. A task is one pull request's worth of work. If it is larger, split it before anything starts.
- Every entry has a **Done when** list: checks a person or a command can run. It is the stopping rule. Without one, do not start.
- Record a decision the user makes in the entry it belongs to, in their words.
- Write no status in an entry, and change none by hand. An entry has a `Stage:` line, which says where the planning is: `proposed`, `planned`, `parked` or `scouting`. Once a brief of the entry is queued, its status is counted from its queue rows by `jbus plan`, and the `Stage:` line is not read.
- Queue each brief of an entry with `jbus queue add --entry <entry>`, in a repo `jbus plan` answers for and in no other, where the brief's slug is not the entry's own: an entry is often several briefs, and the column is how a row is counted for its entry.
- The user gives the go once per entry, never per row: record it with `jbus plan go <entry> --message <thread>/<message>`, and under `go = "silence"` park each pick as a gate instead ("The user's word, carried by jbus" says how).

An entry has the shape of `$T/plan-entry.md`: read it before writing the first one.

When `jbus plan` prints `finished: close it` for an entry, run `jbus plan close <entry>` (a scoped home adds `--scope <scope>`). It moves the entry's section, as it is, from `plan.md` to `plan-done.md` beside it, and is refused while a row of the entry is not over. An entry leaves `plan.md` this way and no other: none is deleted by hand, and `plan-done.md` is never read at a start.

A plan of several entries that the user approves in one go runs as a queue: "A queue and its hourly audit" says when it starts and ends, and what the home schedules for it.

## The home does not do the work

A home plans, hands out, and keeps the record. Every task is done by a **crewmate**: a separate thread, in its own worktree, that the user can open, watch and steer. The home does not edit the repo, run its checks, or read a crewmate's diff.

The home does no research of its own: it reads only its state directory, `$H`. Not the code, not the docs, not a diff. What it needs to know from those, a scout finds out.

## Sending a scout

Before writing a brief, when a task may need research first, and when a step elsewhere names a step of this section: read `$T/../skills/home/sending-a-scout.md` now.

## A playbook of the home's own

A row `the home` runs, in what the block in "Handing a task to a crewmate" that prints a row for each playbook prints, is steps for this thread: how to run a queue of tasks, not how to do one. Its name is kept on a `Playbook:` line in the head of `$M/plan.md`, above the first `## ` heading, so the next home works by it too. Open it when a home starts with that line in its plan, and when you take one up. Run this after the block at the top and the block that finds this home, with the playbook's name in place of `<name>`, or with nothing in its place to take the name the plan has:

```sh
name='<name>'
uv run --project "$T/../source" jbus playbook home "$M/plan.md" --name "$name"
```

It prints nothing when the name is `none`, or when none is given and the plan's head has no `Playbook:` line: go on with no playbook. On `no playbook`, do the same, and tell the user what it printed. On `not the home's`, the file is for a crewmate or a scout: do the same again, and put its name on a brief or a request instead. When its first line is a path, read that file now. Copy its numbered steps into your todo list, word for word, before any todo of your own (with no todo tool, write the list in this thread), and work them in order. A step you do not do stays in the list as `skip: <reason>`. A path the playbook names is from `$T/..`, the repo this skill lives in, also when the work is in another repo. A line under the path, `asks of its brief:`, is a line to write in each brief the playbook has you hand out. The playbook adds to this skill and does not replace it: where the two disagree, this skill wins, and you say so to the user.

## Handing a task to a crewmate

Before a task goes to a crewmate, and when a step elsewhere names a step of this section: read `$T/../skills/home/handing-a-task-to-a-crewmate.md` now.

## When a thread sends a message

When a thread this home sent out sends it a message, when the user asks for status or runs `/ketchup`, and when a step elsewhere names a step of this section: read `$T/../skills/home/when-a-thread-sends-a-message.md` now.

## Clearing its own blockers

Each time this home wakes, at its start, on a thread's message and on an audit tick, and when a step elsewhere names this section: read `$T/../skills/home/clearing-its-own-blockers.md` now, and run its block.
No bot outside watches the homes or the queue: this home clears its own blockers, and raises to the user only what the user has to decide.

## Gates

At the start, on status, whenever a gate is asked, shown or closed, and when a step elsewhere names a step of this section: read `$T/../skills/home/gates.md` now.

**Move the ones a file still has** at the start, before the open ones are shown, when `$M/gates.md` exists: read `$T/../skills/home/move-the-ones-a-file-still-has.md` now, and run its block in the same call as the block that reads jbus. Its "the end of this section" is the end of "Gates".

## The user's word, carried by jbus

When a message says it is the user's word carried by jbus, when this home records the user's word or a plan entry's go, approves a row on a page's go or on a standing rule, and when a step elsewhere names a step of this section: read `$T/../skills/home/users-word-carried-by-jbus.md` now.

## Merging a pull request that is ready

At every home's start (step 5), on a `fixed and green` line, and whenever a pull request may be ready to merge: read `$T/../skills/home/merging-a-pull-request-that-is-ready.md` now.

## A queue and its hourly audit

At every home's start (step 5), when a queue playbook (`autopilot-full` or `orchestrate`) is taken up, on each audit tick, when a queue's last entry is set to done, and before a handoff: read `$T/../skills/home/queue-and-its-hourly-audit.md` now. Its "the next section" is "Picking up a thread that stopped", below.

## Picking up a thread that stopped

A thread that stopped with its task unfinished is picked up, not started over: a turn a T3 Code restart cancelled, one that failed at the plan's limit, one the audit printed as `stuck`. Its worktree and its brief hold what it did. The playbook `session-pickup` has the steps: open it with the block of "A playbook of the home's own". It ends in one of two calls.

`jbus` tries once first, by the wait's age (`jbus.clock`).
A pull request whose review is not written while its reviewer's thread is not at work gets that reviewer sent its line again; one that waits on its crew gets the crew one carry-on; a crew that ended with no Result has its two carry-ons.
After the second miss `jbus` sends this home one line that names the slug, the pull request and the thread, and the user is not told: that line is the home's cue to pick the thread up as this section says.
`jbus` interrupts no hung turn, so an interrupt, where one is needed, is the home's.

A thread whose last turn failed on a usage limit, the text `You've hit your weekly limit · resets <time>` or its 5-hour twin, is not carried on in place: its instance is capped until that reset, and the same message fails again.
`jbus` does it: its pass reads the failure, writes the cap to the ledger of the instance it ran on, moves the thread to the first instance of its role's pool with headroom with only the `instanceId` changed (`t3_thread_configure`), and sends one queued carry-on, once for the failed run.
Every launch goes to that first instance with headroom as well (`jroles` says which instance it chose and why).
Where every instance of the pool is capped `jbus` logs one `stall`, which is quiet and in the digest, and waits for the first reset.
Do the same by hand only where no `jbus` runs: read the thread with `t3_thread_configuration`, call `t3_thread_configure` with that selection and the `instanceId` of the next instance of the pool, then send the carry-on below.
Never send a plain carry-on to a thread that failed on a limit.

A message first, when the thread can still take one: `t3_thread_send` to the id on the brief's `Thread:` line, one line, to carry on from its brief and its worktree and to redo nothing that is there.

A new thread on the same worktree when it cannot: the send fails, the thread is archived or gone, or it was sent that message once and the next tick prints it `stuck` again. Find the worktree whose branch is the slug with `git worktree list --porcelain`, from the main checkout. With none, there is nothing to pick up: launch from step 2 of "Handing a task to a crewmate". Add one line to the brief, above its first `## ` heading, so the new thread knows it resumes: `Resume: <date>, the thread before this one stopped. Its work is in this worktree and in the last Result below: redo nothing that is there, and carry on from <the resume point>`. The crew skill reads the brief at its start, and a brief is trusted. Then, on `go` from `room`, the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first):

```json
{
  "title": "crew: <slug>",
  "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<slug>"},
  "message": "/crew <slug>"
}
```

Before this launch, run `uv run --project "$T/../source" jroles crew` with the block at the top.
When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the crewmate on the model the role map names.
When it prints nothing, the call is the one above.
Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line.
When it exits 75 and prints no JSON, every instance of the role's pool is capped by a usage limit and the line on stderr says until when: make no launch, and say that line.
A selection it prints names the instance of the pool it chose as its `instanceId`, and the launch is made with it as printed.
Leave the project and modes out, and the model unless `jroles` printed one.

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
