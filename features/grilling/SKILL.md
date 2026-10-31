---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea, until nothing is left assumed. Use for /grilling, or when a home plans work whose shape is not settled.
tip: questions a plan until nothing is left assumed | grill me | poke holes | what am i missing | challenge my plan
disable-model-invocation: true
card: "Settle the shape before code | 1 | Questions the operator about a plan, a decision or an idea, round after round, until nothing is left assumed. | Reach for it when the work is more than one task, or a design choice is not made yet. | op: the operator; model: a home"
---

# Grilling

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (the code, the docs, a tool), send the `Explore` agent to find it, which in a home is a light scout (or, with no subagent tool, do it in this thread); don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

## In a home

Grilling is planning, so it is the one place a home waits for the user round after round: what the work is for comes from them. It ends before anything is launched. Once a task is out, a question only the user can answer is a gate with a default, not a new round.

When the user confirms, write what was settled into `plan.md`: one entry per task, each answer under **Decisions** in the entry it belongs to, in the user's words, with the date. An answer that was "yes" is recorded as the recommended answer it accepted.

## Asking a round

Ask a round through the thread's question form, `AskUserQuestion` in Claude Code and `request_user_input` in Codex: one question for each of the round's, with your recommended answer as its first option.
A form that holds fewer questions than the round is followed at once by another, until the round is asked.
Where the provider has no question form, send the round as one plain message, in the format above.
Where a question needs a picture, write the visual as one HTML file under `~/.local/state/home/<repo>/reports/` and show it with T3 Code's `html_preview` and then `html_render`, then ask the question in the form.
Where the answer is the user's go for rows of the queue, the box is the go: the home skill's "A go given in a question box" says how the rows are approved.
