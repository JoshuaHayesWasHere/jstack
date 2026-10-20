---
name: reflect
description: Read one thread's transcript with three review subagents and a synthesiser, and end in proposed edits and proposed plan entries for the home to put to the user. It starts four subagents and edits nothing. Runs only when the user types /reflect or $reflect, or a brief names it.
tip: reads a thread's transcript and proposes edits and plan entries | reflect on this | retrospective | lessons learned | what went wrong in this thread
disable-model-invocation: true
card: "Make the lesson stick | 2 | Reads one thread's transcript with three review subagents and a synthesiser, and ends in proposed edits and plan entries. It edits nothing. | Reach for it when a thread went badly, or well, and the reason should outlast it. | op: the operator; plain: a step of `eval`"
---

# reflect

**This starts four subagents on this session's own model: three reviewers at once, then one synthesiser.** What a run costs is not measured. The guess is 1M to 2M tokens. What is measured (2026-10-10): the largest transcript of the jstack repo, 6.4 MB, comes to a digest of about 120 KB, near 30,000 tokens, and each of the three reviewers reads that once.

Typing `/reflect` is the user asking for those four, which is what "Ask before swarming" in `~/.claude/CLAUDE.md` wants. A brief that names this skill carries the same asking, from the home that wrote it. Nothing else starts it: not a hook, not a finished task, not the model by itself. Before step 1, say in the thread, in one line, that four subagents are about to start and the guess at their cost.

It mines one thread for what is worth keeping, and ends in proposals. It edits no skill, no playbook, no `notes.md`, no plan and no `CLAUDE.md`: the home puts the proposals to the user, and what the user takes goes out as tasks.

Skip it, and say so, when the thread is trivial or when everything that went wrong was a skill followed badly, not a skill that was wrong. A one-off is not a lesson.

## 1. Find the transcript

A thread's transcript is one `.jsonl` file under `~/.claude/projects/`, in a directory named for the directory the thread ran in. This prints it:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
P=~/.claude/projects
S=${S:-}
W=${W:-}
if [ -z "$S" ] && [ -z "$W" ]; then S=${CLAUDE_CODE_SESSION_ID:-}; fi
if [ -n "$S" ]; then
    f=$(ls "$P"/*/"$S".jsonl 2> /dev/null | head -n 1)
else
    D=$P/$(printf %s "${W:-$PWD}" | sed 's/[^A-Za-z0-9]/-/g')
    f=$(ls -t "$D"/*.jsonl 2> /dev/null | head -n 1)
fi
if [ -n "$f" ]; then
    echo "$f"
else
    echo "no transcript: nothing under $P for ${S:-${W:-$PWD}}"
fi
```

Run as it is, it prints this thread's own file. For another thread, put one line before it in the same call: `S=<its session id>`, or `W=<the directory it ran in>` for the newest thread of that directory (a crewmate's is its worktree, `~/.t3/worktrees/<repo>/<slug>`). With a session id it looks for that one file name and opens nothing else. Do not list or read other files under `~/.claude/projects/`: they are other threads' conversations.

On `no transcript`, stop and say what it printed.

## 2. Make the digest

A transcript is mostly tool output and is too long to hand to a reviewer whole. This writes what was said and done, each turn headed by its line number in the transcript, and prints where:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
F=<the file step 1 printed>
out=${TMPDIR:-/tmp}/reflect-$(basename "$F" .jsonl).txt
if jq -r '
    select(.type == "user" or .type == "assistant")
    | "line \(input_line_number), \(.type):" as $head
    | .message.content // []
    | if type == "string" then [{type: "text", text: .}] else . end
    | map(
        if .type == "text" then .text[0:4000]
        elif .type == "tool_use" then "[\(.name)] \(.input | tostring | .[0:300])"
        elif .type == "tool_result" then "[result] \(.content | tostring | .[0:300])"
        else empty end)
    | select(length > 0)
    | $head, .[], ""
' "$F" > "$out" && [ -s "$out" ]; then
    echo "$out $(wc -c < "$out") bytes"
else
    echo "no digest: jq failed on $F, or it holds no turn"
fi
```

On `no digest`, stop and say what it printed: no reviewer starts on an empty or cut-off digest.

The digest is what the reviewers read. A reviewer that needs more of one turn opens the transcript at that line. What a subagent of that thread did is in its own file under `<the transcript without .jsonl>/subagents/`, and is not in the digest.

## 3. Three reviewers at once

A reviewer changes no file. Two things hold that, and neither is a sentence in its prompt: the tools it is started with, and a check of the worktree once it is back.

The check first. This block is run before the reviewers with `when=before`, and after them with `when=after`:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
when=<before or after>
G=$(git rev-parse --absolute-git-dir 2> /dev/null)
state() (
    cd "$(git rev-parse --show-toplevel)" || exit
    git rev-parse -q --verify HEAD
    git status --porcelain
    git diff HEAD 2> /dev/null | git hash-object --stdin
    git ls-files -o --exclude-standard -z | xargs -0r git hash-object --
)
if [ -z "$G" ]; then
    echo "no worktree check: $PWD is not in a git repository"
elif [ "$when" = before ]; then
    state > "$G/reflect-before"
    echo "worktree recorded"
elif [ "$when" != after ]; then
    echo "no worktree check: when is '$when', not before or after"
elif [ ! -f "$G/reflect-before" ]; then
    echo "no worktree check: nothing was recorded before the reviewers"
elif state | cmp -s - "$G/reflect-before"; then
    echo "worktree unchanged"
else
    echo "worktree changed: the run fails"
    git status --porcelain
fi
```

It records the commit the worktree is on, its status, and what is in every changed and every new file, from the top of the worktree wherever the shell is. So a second edit to a file this thread had already changed is seen too.

Then the reviewers: one message with three calls of the `Agent` tool (or, with no subagent tool, do it in this thread, one lens after another), each this one with its lens's prompt:

```json
{
  "subagent_type": "Explore",
  "description": "reflect reviewer",
  "prompt": "<the lens's prompt>",
  "run_in_background": false
}
```

The type is `Explore` because it is started with no Edit, Write or NotebookEdit tool, and it runs on this session's model at this session's effort (both seen on 2026-10-10, Claude Code 2.1.296). Never `general-purpose` or `claude`, which have every tool, and no `model`, `effort` or `isolation`. No other model family, and no T3 thread or delegated task in place of a subagent: a reviewer needs nothing that lasts.

| Lens | Prompt |
|---|---|
| Judgment | `references/judgment-reviewer.md` |
| Tooling | `references/tooling-reviewer.md` |
| Divergent | `references/divergent-reviewer.md` |

The files are beside this one, in `~/.claude/skills/reflect/`. Pass each as the prompt, whole, with the digest's path and the transcript's path put in where marked. A reviewer reads, looks things up, and returns a numbered list.

When the three are back, run the block with `when=after`, and do not write a file yourself between the two runs:

- `worktree unchanged`: go on.
- `worktree changed`: the run fails. Start no synthesiser and show no proposals. Say what the block printed and which reviewers ran, and undo nothing: what becomes of the change is the user's to say.
- `no worktree check`: go on, and say at the end that only the reviewers' tools held them.

An `Explore` reviewer still has Bash, and the check is there for that. It is after the fact: it finds a change and does not prevent one. Neither the tools nor the check stops a command that writes outside this worktree or to a file git ignores, or one that changes something elsewhere (`gh`, `git push`, an MCP tool).

## 4. Synthesise

One more Agent call (or, with no subagent tool, do it in this thread), the same call as a reviewer's with the description `reflect synthesiser`. Pass `references/synthesizer.md` whole, with each reviewer's full output put in where marked. It returns three lists: proposed edits, proposed plan entries, rejected.

Then run step 3's block with `when=after` once more, and take what it prints the same way: the synthesiser is held as the reviewers are.

## 5. Structure before text

Read the proposed edits once more yourself. Any that a check, a test, a shell block or a script would enforce better than a sentence moves to the proposed plan entries (`principles/principle-encode-lessons-in-structure.md`, from the root of the repo this skill lives in). The order of remedies is the one in the `correct` skill: structure, then types, then a test, then a written rule.

## 6. End in proposals

Nothing is applied. Show, with no preamble:

- **Proposed edits**: the synthesiser's table. One row per edit: the problem, the change, and the file and section it would land in.
- **Proposed plan entries**: one per item, in the shape of `templates/plan-entry.md` of this skill's repo with `Status: proposed`, each with a "Done when" a crewmate could meet, the evidence, and a t-shirt size.
- **Rejected**: one line each, with the synthesiser's reason.
- The cost, if it can be read: the four subagents' token counts as the Agent results gave them.

Then stop. Where the proposals go depends on who ran this:

- A home shows them to the user in its thread, and adds to the plan only what the user takes.
- A crewmate or a scout whose brief named this skill puts them in its Result or its report, under a heading `### Reflect`, and the home takes it from there.
- Any other thread shows them and leaves them with the user.

The digest in the temporary directory can stay: it is rebuilt on the next run.
