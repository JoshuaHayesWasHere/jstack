---
name: interrogate
description: "Use for /interrogate, \"interrogate\", \"adversarial review\", \"challenge this\", \"stress test this code\", \"find blind spots\", or \"tear this apart\". Two reviewers that do not see each other challenge changes, and the lead filters what they found."
tip: has two reviewers who do not see each other challenge a change | adversarial review | stress test this | find blind spots | tear this apart | challenge this
disable-model-invocation: true
card: "Distrust the change | 2 | Two reviewers that do not see each other challenge a change, and the lead filters what they found. | Reach for it when a design or a change needs adversarial pressure. | op: the operator; rev: a reviewer"
---

# Interrogate

Source: pstack, `pstack/skills/interrogate/SKILL.md`

Spawn two reviewers to adversarially review code changes, each with the same prompt and neither shown the other's answer. The deliverable is a synthesized verdict. Do NOT auto-apply changes.

This is not a pull request's review.
That one is launched by the crewmate that opened the pull request and run by a reviewer in a thread of its own, as `skills/crew/SKILL.md` "The review" and `features/pr-review/SKILL.md` say.
This skill launches no reviewer thread and writes no `## Review` section and no `Finding:` line in a brief.
Run this first:

```sh
if R=$(realpath ~/.claude/skills/interrogate/../.. 2> /dev/null) && [ -f "$R/skills/pr-review/SKILL.md" ]; then
    echo "$R"
else
    echo "no root: ~/.claude/skills/interrogate is not a link into the repo this skill lives in"
fi
```

It prints the root of the repo this skill lives in. Every path below that starts with `playbooks/`, `principles/` or `skills/` is from that root, and a path that starts with `references/` is beside this file. On `no root` the skill was loaded from somewhere else: the root is two directories above the real place of this file, not of a link to it.

Every spawn is one call of the `Agent` tool (or, with no subagent tool, do it in this thread, working from the same prompt), this one with `prompt` set to the prompt built in step 3:

```json
{
  "subagent_type": "Explore",
  "description": "interrogate reviewer",
  "prompt": "The prompt, built from the template.",
  "run_in_background": false
}
```

The type is `Explore` because it is started with no Edit, Write or NotebookEdit tool, and it runs on this session's model at this session's effort. No `model`, no `effort` and no `isolation`: there is no model per role here and no second model family. The source drew its adversarial signal from two model families. Here it comes from two readers that do not see each other, which is weaker: say so in the verdict when the two agree on everything.

## Step 1, Scope

Identify what to review from context:

- If the user points at specific files or a diff, use that.
- With nothing named, the change is this checkout against the default branch, the working tree included. `git diff "$(git merge-base HEAD origin/HEAD)"` prints that diff (name the default branch where `origin/HEAD` is not set), and `git ls-files --others --exclude-standard` the files not yet added. With neither printing anything, ask which change is meant.
- If the user's message references recent work, gather the relevant files.

Package the diff or file contents with any surrounding context files the reviewers need to understand the code.

## Step 2, Intent

Before spawning reviewers, state the intent in one clear paragraph from the user's message, commit messages, the PR description if one exists, and the code. In a thread that works a brief, the intent is the brief's `Task:` and `Done when`. If you're unsure about the intent, ask the user before proceeding.

## Step 3, Spawn Reviewers

Six checks of the source's rubric and five dimensions of its code-quality lens already live in the `SCOPE` text of the pr-review skill, as its questions 4 and 5. They are not copied here. This prints them:

```sh
R=$(realpath ~/.claude/skills/interrogate/../.. 2> /dev/null)
S=${R:-no root}/skills/pr-review/the-review.md
asked=$(awk '
    /<<.SCOPE.$/ {scope = 1}
    /^SCOPE$/ {exit}
    scope && /^4\. / {on = 1}
    /^   When the remedy/ || /^6\. / {on = 0}
    on' "$S" 2> /dev/null)
if [ -n "$asked" ]; then
    printf '%s\n' "$asked"
else
    echo "no questions: $S has no questions 4 and 5 in a SCOPE text, so the reviewers get the rubric and the lens alone"
fi
```

On `no questions`, the root was not found or the `SCOPE` text has changed: fill that placeholder with "None here: the checks this section holds were not available for this review." and say under "Reviewers" in the verdict that those checks were not asked.

Read `references/reviewer-prompt.md` and fill in the same template for both reviewers with the stated intent, the diff or file contents, the rubric from `references/rubric.md`, the code-quality lens from `references/code-quality-review.md`, and what the block printed.

Launch both reviewers in a single message, labeled Reviewer A and Reviewer B. Two is the count: a third reader on the same model adds little, and a step never starts more than ten subagents.

## Step 4, Synthesize

As results come back, build a unified picture. Parse both reviewers' findings. Merge findings that describe the same issue differently, and note which reviewer raised each one. A finding both raised independently is the highest signal. Read a lone finding, but weight it accordingly. Note disagreements. If one reviewer flags something and the other explicitly says the opposite, that is context for the verdict.

## Step 5, Lead Judgment

You are the lead reviewer, a pragmatic senior engineer, not a neutral aggregator. Read `references/lead-judgment.md` for the full framework. Put every finding in one of four buckets, with the reviewer(s) that raised it and a one-line rationale.

- **Act on**. Real issues affecting correctness, security, or maintainability given the actual goals. They would block a real PR.
- **Consider**. Legitimate, but you're not sure they outweigh the cost of addressing them now. Worth the user's attention.
- **Noted**. Technically valid but not actionable. Context-dependent, premature optimization, or low-impact at this stage.
- **Dismissed**. Wrong, nitpicky, or missing context, with a brief reason.

The four buckets are how this verdict reads to the user.
A finding of a pull request's own review has two endings and no more, `Finding: fixed` and `Finding: not fixed, ..., because`, and `skills/crew/SKILL.md` "The review" is where they are written.
In a crewmate's thread the verdict still applies nothing by itself: what the crewmate then fixes stays inside the brief's **Where**, and the rest is a queued row or nothing (`templates/a-fault-outside.md`).

## Output Format

### Intent
> [The stated intent paragraph from Step 2]

### Reviewers
- Reviewer [label]: [N findings] (one bullet per reviewer)
- [One line if the two agreed on everything, and one if the review skill's questions were not asked.]

### Act On
[Each: description, which reviewers raised it, why it matters.]

### Consider
[Each: description, which reviewers raised it, the tradeoff.]

### Noted
[Brief list.]

### Dismissed
[Each with a brief rationale.]

### Agreement Map
[Where the reviewers agreed and diverged, and what that pattern tells us.]
