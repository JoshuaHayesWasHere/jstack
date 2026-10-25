## A queue and its hourly audit

A queue is a plan the user approved once, worked to its end with no further word from them. It is out when both of these hold: the head of `$M/plan.md` names a queue playbook on its `Playbook:` line (`autopilot-full` or `orchestrate`), and an entry of that plan is not done, so something is planned or out. It ends when either stops holding.

While a queue is out, and only then, the home has one scheduled run: the audit, once an hour. It is the one exception to "the home does not poll". Its id is kept in `$M/audit`, one line, the id and then the thread it posts into. Run this at the start of a home, when a queue playbook is taken up, on each tick, and when the last entry is set to done, in one call with the block at the top and the block that finds this home:

```sh
A="${M:?run the block that finds this home first}/audit"
name=$(uv run --project "$T/.." jbus playbook home "$M/plan.md" --named 2> /dev/null)
case $name in
autopilot-full | orchestrate) ;;
*) name= ;;
esac
open=$(awk '
    function entry() { if (title && !done) n++; title = done = seen = 0 }
    /^## / { entry(); title = 1; next }
    /^Status:/ && title && !seen { seen = 1; if ($(2) ~ /^done([^a-z]|$)/) done = 1 }
    END { entry(); print n + 0 }' "$M/plan.md" 2> /dev/null)
id=
by=
if [ -s "$A" ]; then read -r id by < "$A"; fi
if [ -n "$name" ] && [ "${open:-0}" -gt 0 ]; then
    if [ -z "$id" ]; then
        echo "schedule: a queue is out by $name, $open entries planned or out, and no audit is kept"
    elif [ "$by" = "$ME" ]; then
        echo "keep: audit $id posts into this thread"
    else
        echo "replace: audit $id posts into ${by:-another thread}, not this one: delete it, then schedule"
    fi
elif [ -n "$id" ] && [ -n "$name" ]; then
    echo "delete: audit $id, the queue has ended: nothing is planned or out"
elif [ -n "$id" ]; then
    echo "delete: audit $id, the queue has ended: the plan names no queue playbook"
else
    echo "no queue: nothing is scheduled, and nothing is to be"
fi
```

Its first word is what to do. `keep` and `no queue`: nothing. `schedule`: the first call below. `delete`: the second. `replace`: the second, then the first.

A schedule call and the block that keeps its id are two calls, and a turn can stop between them. So before scheduling, call the `t3-code` server's `list_scheduled_tasks` (if your harness defers it, load it first) with no arguments. A task titled `audit: <repo> queue` whose `boundThreadId` is this thread is an audit whose id was never kept: keep its id with the block below and schedule nothing. One with that title that is bound to a thread that is no home of this repo now is a home's that handed off: delete it.

**Schedule it** with the `t3-code` server's `schedule_task` (if your harness defers it, load it first), as it is but for the repo's name:

```json
{
  "title": "audit: <repo> queue",
  "prompt": "Audit tick. Read \"A queue and its hourly audit\" in the home skill again, from the file, and do what it says under \"One tick\". A tick that changed nothing ends with no reply.",
  "schedule": {"type": "interval", "everyMs": 3600000}
}
```

Leave `bindToCurrentThread` out: each run then posts into this thread.
A run in a thread of its own would start in the main checkout, as a home.
The call returns the audit's id as `scheduledTaskId`, and `nextRunAt`: write that time as a `launched:` line of the turn's end, which the user is told when they ask for status.

**Delete it** with the `t3-code` server's `delete_scheduled_task` (if your harness defers it, load it first), with the id the block printed:

```json
{"scheduledTaskId": "<scheduledTaskId>"}
```

After either call, keep what is so. In one call with the same two blocks, with the id the schedule call returned in place of `<scheduledTaskId>`, or with nothing in its place after a delete:

```sh
A="${M:?run the block that finds this home first}/audit"
id='<scheduledTaskId>'
case $id in
'') rm -f "$A" "$M/audit-seen" && echo "no audit is kept" ;;
*'<'* | *'>'* | *' '*) echo "not written: put the scheduledTaskId the call returned in place of the placeholder, or nothing after a delete" ;;
*) printf '%s %s\n' "$id" "$ME" > "$A" && echo "kept: audit $id, in $A" ;;
esac
```

**A home that hands off** deletes its audit first, whatever the first block says, and runs the block above with nothing: a schedule that posts into a settled thread is nobody's. The next home's start prints `schedule` and makes its own. It deletes no other task of its own: the next home takes those over ("The home before this one"). In a session with neither tool, there is no audit: say so to the user once, and the queue runs on messages alone.

**One tick** is a message in this thread from T3 Code, not from the user or a thread. It reads `$H`, what the merge step prints and the pushed branches, and nothing else:

1. Run the first block. On `delete`, delete the audit and stop. On `no queue`, stop. On `schedule` or `replace`, do what it says, as above, and go on: the audit this tick came from is not the one this home keeps.
2. Do steps 1 to 3 of "When a thread sends a message": read what landed, run the merge step, update the plan, launch what can start. The merge step runs no `jmerge` and prints what jbus merged since the last tick, and what each open pull request waits for. A message a restart or a limit swallowed is caught here.
3. Judge each thread out by its side effects, not by its state. In one call with the same two blocks, from the main checkout:

   ```sh
   S="${M:?run the block that finds this home first}/audit-seen"
   TICKS=2 # ticks in a row with nothing written or pushed before a thread is stuck
   mine=root
   if [ "$M" != "$H" ]; then mine=$(basename "$M"); fi
   said=$(uv run --project "$T/.." jmerge --claims)
   case $said in
   wait:*) echo "$said: nothing was judged" ;;
   *)
       printf '%s\n' "$said" |
           awk -v mine="$mine" '$(2) == "out" && $(3) == mine { print $(1) }' |
           while read -r slug; do
               mark=$({
                   cksum < "$H/tasks/$slug.md"
                   git ls-remote origin "refs/heads/$slug" 2> /dev/null
               } | cksum | cut -d' ' -f1)
               was=$(awk -v slug="$slug" '$(1) == slug { print $(2), $(3) }' "$S" 2> /dev/null)
               count=0
               if [ "${was% *}" = "$mark" ]; then count=$((${was#* } + 1)); fi
               echo "$slug $mark $count"
           done > "$S.new" && mv "$S.new" "$S"
       awk -v TICKS="$TICKS" '
           $(3) == 0 { print "moved " $(1) }
           $(3) > 0 && $(3) % TICKS == 0 { print "stuck " $(1) ": its brief and its pushed branch are as they were " $(3) " ticks ago" }
           $(3) % TICKS != 0 { print "quiet " $(1) ": " $(3) " ticks" }' "$S" ;;
   esac
   ```

   A side effect is a line in the brief (a Result, a Review, a `Finding:`) or a push to the task's branch.
   The block keeps a mark of both for each brief of this home that is out with no pull request yet, in `$M/audit-seen`, and counts the ticks it stayed the same.
   A brief with a pull request is not judged: its crewmate is on the pull request's watch, what it waits for is often another party (a reviewer, CI, the user's word), and step 2's line for it says what it is short of.
   `moved` and `quiet` ask for nothing.
   `stuck` is printed on every second such tick, so a thread that a message did not move is printed again two ticks later: look the thread up with `t3_thread_list`, as "Handing a task to a crewmate" does after a lost reply.
   `running`: leave it, a long run writes nothing.
   `waiting`: it asked the user in its own thread, which T3 Code shows them, so it is a `waits:` line.
   Anything else: pick it up, as the next section says.
4. End the turn by "How a turn ends": a merge, a launch with its link, and a stuck thread and what was done are its lines, and only a question asked reaches the user.
   A `hold` line is no line of it: jbus puts each pull request `jmerge` holds on its list of what waits on the user, from its own run or from the last line a home's run logged, and tells the user of it once.
   A tick that changed nothing runs the block with no lines, and ends with no reply at all.
