---
name: recall
description: "Reconstruct your recent working context from your own chat history, the home's record, live state, and the shared record (user reports, prior fixes, incidents), then hand back a tight current-state brief. Use for /recall, 'recall my work on X', 'catch me up', 'what have I been working on', 'where did I leave off', before starting or resuming work."
tip: rebuilds where you left off from your chat history and the home's record | where did i leave off | what have i been working on | what was i working on | recall my work
disable-model-invocation: true
card: "Catch up and keep track | 1 | Rebuilds your recent working context from the chat history, the home's record and live state, and hands back a short current-state brief. | Reach for it when you start or resume work and ask where you left off. | op: the operator"
---

# Recall

Source: pstack, `pstack/skills/recall/SKILL.md`

**Before you start or resume work, you rebuild the user's recent working context and hand back a tight capsule of where things stand now and what to do next.**

Keep it tight and on-topic.
Read only what the in-scope threads need, then stop.

Your context lives in three records.
Your own chat history holds what you did and decided.
In a repo with a home, the home's record holds what was planned, handed out and finished: the plan, the briefs with their Results, the scouts' reports, the gates.
The shared record holds everything that happened around the same code under other names: the symptoms users keep reporting, the fixes that shipped and got reverted, the errors still firing in prod.
That third record is what the `why` skill (`../why/SKILL.md`, from this file's directory) searches, across source control, the issue tracker, chat and issue channels, long-form docs, and error tracking.
A feature with a long bug tail keeps most of its story there, so don't reconstruct it from your transcripts alone.

A thread's transcript is one `.jsonl` file under `~/.claude/projects/`, in a directory named for the directory the thread ran in, every character that is not a letter or a digit turned into "-".
Every line is one chat message.
This prints the transcripts of one directory changed in the window, newest first, without this thread's own:

```sh
DAYS=${DAYS:-7}
W=${W:-$(git rev-parse --show-toplevel 2> /dev/null || pwd)}
D=~/.claude/projects/$(printf %s "$W" | sed 's/[^A-Za-z0-9]/-/g')
found=$(find "$D" -maxdepth 1 -name '*.jsonl' -mtime "-$DAYS" -printf '%T@ %p\n' 2> /dev/null |
    sort -rn | cut -d' ' -f2- | grep -v "/${CLAUDE_CODE_SESSION_ID:-this-thread}\.jsonl$")
if [ -n "$found" ]; then
    printf '%s\n' "$found"
else
    echo "no transcript: nothing under $D changed in the last $DAYS days"
fi
```

Run as it is, it reads the directory this thread runs in over the last 7 days.
For another window put `DAYS=<n>` before it in the same call.
A crewmate's or a scout's thread ran in its own worktree (`git worktree list` prints them): put `W=<that worktree>` before it.
It lists one directory and nothing else under `~/.claude/projects/`: the rest are other projects' conversations.

This prints what the home's record holds for the same window, newest first:

```sh
DAYS=${DAYS:-7}
if ! G=$(git rev-parse --path-format=absolute --git-common-dir 2> /dev/null); then
    echo "no home record: this is not a git repository"
else
    H=~/.local/state/home/$(basename "$(dirname "$G")")
    found=$(find "$H" -maxdepth 2 -name '*.md' -mtime "-$DAYS" -printf '%T@ %p\n' 2> /dev/null |
        sort -rn | cut -d' ' -f2-)
    if [ -n "$found" ]; then
        printf '%s\n' "$found"
    else
        echo "no home record: nothing under $H changed in the last $DAYS days"
    fi
fi
```

1. Classify, then route.
   One specific prior chat to resume is not this: the home launches a thread on that chat's worktree.
   Turning habits into a durable skill is `automate-me`.
   What happened in this chat since the user's last message is `ketchup`.
   A human-readable summary of your work is a different task.
   Recall loads working context across recent chats before you act.
   If the user already gave you a full state capsule (paths, branch, the change), use it and skip the mining.
   A home that has just read its handoff has its capsule: recall adds to it only for a named topic.
2. Lock the scope before searching.
   Pin the window ("recent" is a real range, default the last 7 days), the topic if named, and the workspace (default the active one, with its worktrees.
   Never read another project's transcripts without being asked).
   State the scope back.
   Never quietly turn "all" into "recent N".
3. Read the home's record first, where there is one.
   From what the second block prints, read the handoff and the plan, then `grep` the topic over the briefs and the reports and read only the last `## Result` or `## Report` of the ones that match.
   A Result names its branch, its pull request and what is left, so it is cheaper and surer than the transcript of the thread that wrote it.
4. Fan out across your chat history, for what the record does not hold.
   Spawn parallel `Explore` subagents with the `Agent` tool, each taking a slice of what the first block printed, on this session's model: no `model` and no `effort`.
   Or, with no subagent tool, do it in this thread, one slice after another.
   Tell every subagent to keep the order the block gave (real modification time, never the UUID name), `grep` the topic first and then read only the matching chats and only their relevant regions, and skip obvious noise (subagent,
   review and test chats).
   Each returns the same schema, one block per chat: topic, the user's goal, decisions, open threads, struggles and corrections, and artifacts (PRs, briefs, branches), each citing the chat UUID.
   For one or two chats, skip the fan-out and search directly.
   The raw transcripts stay in the subagents.
   The main thread gets only their findings.
5. Sweep the shared record whenever the topic names a feature, file, subsystem, area, or bug.
   This is the default, not a judgment call, and "my work on X" does not exempt it.
   Hand it to the `why` skill's source investigators, but steer their question from "why was this built this way" to "what's the current state, what's been tried and didn't hold, and what are users still reporting".
   Reuse its per-source playbooks, run the investigators in parallel with the chat-history mining, and inherit its posture: one investigator per source, null results are findings, skip an unavailable MCP and say so.
   One step starts at most ten subagents, the miners and the investigators counted together.
   Fold what comes back into the brief.
   Skip this step only for pure activity recall with no named target ("what did I do this week"), where your own history, the home's record and live state are the entire answer.
6. Verify against live state.
   Take the PRs, branches, and briefs that the mining and the sweep surfaced and check them with `git` and `gh`.
   When the answer hinges on what an agent actually did (the tools it ran, files it read, errors it hit), read the full transcript, not a subagent's summary of it.
7. Write the brief to the contract below.
   Group by thread.
   Stay on the named topic.

## Output contract

Lead with the capsule, then the thread status, then the problems, then the next move.
Deeper detail goes below or gets cut.

- **Capsule.**
  At most 5 bullets.
  What this work is and where it stands overall.
- **Threads.**
  One line each, prefixed with exactly one status tag: `[merged #N]`, `[open PR #N]`, `[in flight <branch>]`, `[verified, uncommitted]`, `[reverted #N]`, or `[planned, not started]`.
  A thread with no tag is not done yet, so tag it.
- **Problems.**
  At most 5, the recurring ones.
  Include the symptoms users keep reporting and any fix that shipped and was reverted, so the next attempt starts where the last one failed.
- **Next move.**
  The single most useful next action, concrete.

An adjacent feature or ticket stays out unless it blocks this one.
When the capsule and thread lines outgrow a screen, cut detail before you cut threads.
Write the brief through the `unslop` skill (`../unslop/SKILL.md`), cite chat findings by UUID, the home's record by its file, and shared-record findings by their source (PR #, ticket ID, chat permalink, error-tracker issue),
and sanitize private context before any public output.

**Reply:** the brief, to the contract above.
