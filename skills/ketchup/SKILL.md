---
name: ketchup
description: "Catch the user up on everything in this chat since their last message, in plain words. Give each action item an executive summary with enough context to make the call. Use for /ketchup."
tip: catches you up on this chat since your last message | catch me up | what did i miss | what happened while i was away | where are we
disable-model-invocation: true
card: "Catch up and keep track | 2 | Catches the operator up on everything in this chat since their last message, with a summary for each action item. | Reach for it when a thread ran on while you were away. | op: the operator"
---

# Ketchup

Source: pstack, `pstack/skills/ketchup/SKILL.md`

Catch the user up on everything in this chat since the last message they wrote before `/ketchup`. Notifications, wakes of a watch, messages from other threads and subagent results are not their messages. Write in the plain voice of [`/bro`](../bro/SKILL.md), and skip its restating step. Assume the user remembers their last message and nothing after it. Call each PR, branch, or thread by a name they would know, not by a label you invented during the work.

## Gather what changed

Keep this turn read-only, except for visuals you make for the reply from what you already have. Do not change code, start an app or a job, or post anything to make them. Collect your own work since that message, reports from subagents, and messages from anyone else in this chat. Check the current state of each PR, CI run, or thread this chat touched: `gh pr view <number> --json state,mergeable,statusCheckRollup` for a pull request, and the T3 Code tool `t3_thread_read` for a thread this one launched. Say which are still running and which you could not check.

An action item is a decision or step only the user can take, such as a product choice, an approval, an irreversible action, or access you lack. Include any still waiting on the user, even one raised before their last message. Work you can still do yourself is not an action item.

In a repo with a home, a question that waits on the user is parked as a gate, and this prints the open ones:

```sh
if ! G=$(git rev-parse --path-format=absolute --git-common-dir 2> /dev/null); then
    echo "no gates: this is not a git repository"
else
    H=~/.local/state/home/$(basename "$(dirname "$G")")
    open=$(for f in "$H"/gates.md "$H"/*/gates.md; do
        if [ -f "$f" ]; then
            awk -v file="$f" '/^## Gate / {head = $(0)} /^Status: open/ {print head ", in " file}' "$f"
        fi
    done)
    if [ -n "$open" ]; then
        printf '%s\n' "$open"
    else
        echo "no gates: none is open in $H/gates.md or in a scoped home's, $H/*/gates.md"
    fi
fi
```

It reads the root home's gates and every scoped home's, and names the file each is in. Each gate it prints that this chat asked or built on is an action item, with the gate's `Default:` as what happens if the user does not answer.

## Write the reply

Open with one sentence that says how many action items there are, or that there are none. If nothing happened and nothing waits on the user, say so and stop.

Then say what happened, most important first. Give each result and what it means for the user. Skip steps that changed nothing. Name in one line any work left that you can do yourself.

Then give each action item a short executive summary. Cover the decision to make, why it matters now, the options and what each costs, your recommendation, and what happens if the user does not answer. If you do not know a part, say so instead of guessing. Link to the detail when there is one, and write the summary so the user can decide without opening it.

Show each action item as a before and after, side by side. For a choice, put the current state beside each option, or the options alone when there is no current state. Use screenshots or a video when the change is visible. Otherwise use another artifact, such as a table of numbers, a diff, or a diagram. If no visual exists yet, make one. If you cannot, say plainly that none exists. Never invent a number, and never draw or generate a picture of a screen you did not capture. Link only artifacts that exist.

Prefer visuals to dense prose. Use a table, a Mermaid diagram, or a chart.
