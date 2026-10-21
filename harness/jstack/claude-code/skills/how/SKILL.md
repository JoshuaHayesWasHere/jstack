---
name: how
description: "Use for /how, \"how does X work\", code walkthroughs before changing something, and placement / ownership / layering questions (\"where should this live\", \"which package owns this\", \"is this the right layer\"). Explains subsystem architecture, runtime flow, onboarding mental models. Use why for motivation."
tip: explains how a subsystem works before you change it | how does * work | how do * work | where should this live | which package owns | walk me through the code
disable-model-invocation: true
card: "Understand what is there | 1 | Explains how a subsystem works: its architecture, its runtime flow and where things live. | Reach for it when you are about to change something, or ask which layer owns it. | op: the operator; plain: a step of `architect`"
---

# How

Source: pstack, `pstack/skills/how/SKILL.md`

Explore the codebase to answer "how does X work?" questions. Produce architectural explanations at the level of a senior engineer onboarding onto a subsystem, enough to build a working mental model, not so much that it reads like annotated source code.

Every spawn is one call of the `Agent` tool (or, with no subagent tool, do it in this thread, working from the same prompt), this one with `prompt` set to the prompt built from its template:

```json
{
  "subagent_type": "Explore",
  "description": "how explorer",
  "prompt": "The prompt, built from its template.",
  "run_in_background": false
}
```

The type is `Explore` because it is started with no Edit, Write or NotebookEdit tool, and it runs on this session's model at this session's effort. No `model`, no `effort` and no `isolation`, for an explorer or an explainer: there is no model per role here. An explainer's call is the same with the description `how explainer`.

The two templates are beside this file, in `references/`.

## 1. Assess complexity

If the scope is ambiguous, state your interpretation and explore. The user can redirect.

- **Simple** (a single module, a small utility, a narrow question such as "how does function X work"): no explorers. Spawn one explainer that explores and explains in one pass, built from `references/explainer-prompt.md` without the explorer-findings section. That template is written for an explainer that explorers ran before, so on this path also swap its three passages about them (the second sentence of its opening paragraph, the first paragraph under Instructions, and the sentence "The explorers did the work, so you shouldn't need to re-explore from scratch") for one sentence: no explorer ran, so explore the code yourself first, then explain. Go to step 4.
- **Complex** (a subsystem spanning multiple files or services, a cross-cutting feature, a full architectural overview): go to step 2.

When in doubt, take the simple path.

## 2. Explore (complex only)

Decompose the question into 2 to 4 angles, each a distinct slice of the subsystem. Spawn all explorers in a single message, each with `references/explorer-prompt.md` and its angle filled in.

## 3. Synthesize (complex only)

Once all explorers have returned, spawn one explainer with `references/explainer-prompt.md` and every explorer's findings filled in.

## 4. Present

Present the explainer's output. Light edits for clarity or context from the conversation are fine. Do not substantially rewrite it.

## Output format

The explanation uses the sections defined in `references/explainer-prompt.md`, dropping any that do not apply: Overview, Key Concepts, How It Works, Where Things Live, Gotchas.
