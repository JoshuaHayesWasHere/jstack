---
name: automate-me
description: "Use for /automate-me, \"automate me\", \"create/update/refresh my -mode skill\", \"turn/capture my preferences or working style into a skill\", or wanting agents to follow how the user works. Drafts or revises a personal -mode skill by the authoring-a-skill playbook and unslop, optionally pulling fresh evidence from recent transcripts."
tip: turns how you work into a -mode skill agents follow | automate me | my working style | my preferences into a skill | mode skill
disable-model-invocation: true
card: "Make the lesson stick | 3 | Drafts or revises a personal mode skill that captures how the user works, with evidence from recent transcripts when asked. | Reach for it when you want agents to follow your working style without being told again. | op: the operator"
---

# Automate me

Source: pstack, `pstack/skills/automate-me/SKILL.md`

A guided flow for turning the user's working conventions into a skill agents will follow. The output is one `-mode` skill tailored to them (e.g. `jay-mode`, `priya-mode`).

This skill orchestrates three others: an inline mining pass (see step 1), the playbook for writing a skill (`../../playbooks/authoring-a-skill.md`, from this file's directory), and the `unslop` skill (`../unslop/SKILL.md`) for prose discipline. It sequences them. It doesn't replace them.

## Flow

### 0. Check for an existing skill

This prints every mode skill there is, the user's own and this project's:

```sh
found=
for f in ~/.claude/skills/*-mode/SKILL.md .claude/skills/*-mode/SKILL.md; do
    if [ -f "$f" ]; then
        found=yes
        echo "$(realpath "$f"), last changed $(date -r "$f" +%F)"
    fi
done
if [ -z "$found" ]; then
    echo "no mode skill: none under ~/.claude/skills or .claude/skills"
fi
```

If one matches the user's handle, confirm intent with the `AskUserQuestion` tool (unless they already said "update my skill" or similar):

- Update the existing skill (default for repeat runs)
- Start fresh (rare, ask why before doing it)

Update mode changes the rest of the flow:
- Step 1 mines only history since the date the block printed.
- Step 2 asks what's changed or missing, not what to capture from zero.
- Step 4 edits the existing file in place. Preserve sections the user hasn't contradicted. Revise ones with new evidence. Add new sections only for genuinely new rules.

### 1. Mine their history

Locate the active workspace's transcripts before fanning out: the first block of the `recall` skill (`../recall/SKILL.md`) prints them, for one directory and a window in days. Use only what it prints. Don't glob across `~/.claude/projects/*/`. That crosses workspace boundaries and reads private chats from unrelated projects.

Survey recent agent conversations within that scope for recurring patterns. Run parallel `Explore` subagents with the `Agent` tool across slices of history (e.g. last 2-4 weeks, split into 3 slices so each has enough material), on this session's model: no `model` and no `effort`, and never more than ten in a step. Or, with no subagent tool, do it in this thread, one slice after another. Each slice mining subagent reads the transcripts the parent names, looks for the signals below, and returns a short structured list of patterns it saw with evidence pointers. Default signals worth hunting:

- Response preferences (length, tone, format, "dumb it down" corrections)
- Delegation habits (subagents, specialized workflows, parallelism)
- Verification posture (what "done" means, unit tests vs live repro, reviewers)
- Code and prose discipline (style, principles cited, lint/format tools)
- Process conventions (worktrees, commits, PRs, review/merge tooling)
- Meta preferences (fixing skills mid-task, proposing new ones)

Cross-check across slices before elevating a signal. Patterns seen in 2+ slices are high-confidence. Lone signals are weak and usually get dropped.

What the user has already written down is evidence too, and stronger than a pattern: read `~/.claude/CLAUDE.md` and, in a repo with a home, its `notes.md`. A rule that is there already is pointed at from the mode skill, not written a second time.

### 2. Ask the user directly

Mining misses intent that hasn't come up yet. Use the `AskUserQuestion` tool (structured multi-choice) rather than asking the user to type from scratch.

Shape: one or two questions with up to 4 options each, which is the most the tool takes, and `multiSelect` set for category questions. Start broad ("Which areas matter most?"), then follow up on selected areas with specific options. After the structured rounds, one free-form chat question catches anything the options missed.

Don't dump 20 questions.

### 3. Cluster findings

Group the combined signals into sections. Common ones (use only what applies):

- **Response style**: length, tone, format.
- **Autonomy**: how much to do without asking, MCP tool use.
- **Understand first**: which skills to reach for when scoping or investigating a change.
- **Subagents**: default, parallelism, specialized workflows.
- **Prose / code discipline**: principles, lint tools, style guides.
- **Review and verify**: repro posture, verification skills, live-testing tools.
- **Process**: git worktrees, commits, PRs, review/merge tooling.
- **Skills**: skill-authoring habits, fix-the-skill-first, proposing new skills.

There is no mode skill in this repo to copy the shape from. A section is a heading and a few rules a reader can act on.

### 4. Draft the skill

Write the skill by the playbook for writing a skill. Placement:

- Path: preserve an existing mode skill's place. A new one is `~/.claude/skills/<handle>-mode/SKILL.md` for a personal skill, or `.claude/skills/<handle>-mode/SKILL.md` in the project when the user wants it shared with the repo.
- Handle: the user's first name or chosen identifier.
- Frontmatter `description`: trigger on their name + `/<handle>-mode` + "work in their style", not on generic keywords like "write code" or "review PR".
- Frontmatter formatting: keep `description` as one YAML scalar. Quote it when its punctuation requires it.
- Frontmatter `disable-model-invocation: true` by default. Opt out only if the user explicitly wants their mode to apply on every turn.
- The name is not a built-in command's.

### 5. Iterate on prose

Apply the `unslop` skill and step 2 of the playbook to every line.

Show the draft to the user and take feedback. Expect multiple iterations. Cut ruthlessly. A mode skill is not a manual.

### 6. Land it

A skill inside a repo lands as that repo's changes do: on a branch in a worktree, with a pull request, never on the default branch. A personal skill under `~/.claude/skills` is outside every repo this thread works in: write it only on the user's word in this thread, and say where it is.

## Guardrails

- **Don't overfit to one conversation.** A preference stated once and contradicted another time is noise. Require multiple instances before codifying it.
- **Don't be clever.** Restating other skills' contents, inventing metaphors, or writing "poetic" prose for an agent reader is cost without benefit. Keep it operational.
- **Reference, don't inline.** Other skills the user relies on should appear as path references, not pasted excerpts. Same for any principle docs they maintain elsewhere.
- **Keep sections minimal.** Only add a section if the user has a specific, non-default rule there. "Communicate clearly" is not a section. "Short paragraphs. Tables when comparing options. Bullets only when items are genuinely parallel." is.
- **Name conventions generic.** Use "the user" or "the human" in imperatives, not the author's first name.
- **Don't force symmetry.** If a user has no process rules worth writing down, skip the Process section entirely.

## Evaluation

A `-mode` skill is subjective output. A test-and-iterate benchmark loop isn't useful here. Vibe-check with the user: does it read like them? Did it miss anything? Then ship.

Tune the description only if the skill's trigger accuracy turns out to be a problem in practice.

## When not to use

- User wants a task-specific skill (not working conventions): the playbook alone, no mining required.
- User wants to capture one narrow workflow (e.g. "how I write commit messages"). That's a regular skill, not a mode skill.
- One correction to keep: that is the `correct` skill (`../correct/SKILL.md`).
