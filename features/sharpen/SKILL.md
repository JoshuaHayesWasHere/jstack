---
name: sharpen
description: "Rewrite a task's prompt to ask for the deeper version, not a bigger one, without doing the task. Use for 'sharpen this', 'make this prompt better', or a long hand-typed brief or audit ask before it goes out."
tip: rewrites a task's prompt to ask for the deeper version, and does not do the task | sharpen this | sharpen the task | go deeper | deeper version | more ambitious | what would an expert do | how would an expert approach
card: "Settle the shape before code | 4 | Makes a task deeper, not bigger: what an expert would do, from what raw material, with which methods and tools, and what outside the agent shows the result is right. Then it rewrites the prompt to ask for that, and does not do the task. | Reach for it before a research, perf, analysis or outcome task goes out. | op: the operator"
---

Source: pstack, `pstack/skills/sharpen/SKILL.md`

I want a deeper version of this task, not a bigger one. Before rewriting it, do four things:

1. Say what a top professional in this field would do here that I'm not asking for.
2. Name the rawest material they would start from instead of what has already been digested for me.
3. Name the specific methods and tools they would use.
4. Say what, other than you or me, would show the result is right.

Then rewrite my prompt to ask for exactly that.

Leave choices that are mine to make open instead of deciding them.
Name the professional whose view you took in step 1, as one of those choices, so that I can swap it.
When you have listed the open choices, ask them at once, one question per choice with your recommended answer as its first option, as grilling's "Asking a round" says (`../grilling/SKILL.md`).
Fold each answer into the rewritten prompt, and show the final prompt once.
Then ask, in the same form, what to do with it: send it as one scout request, as a swarm of three scouts on the same request with their findings in one table, as an arena, or not at all.
Recommend one.
In a home the answer is the go for that step.
In any other thread, the answer gives me the line to type in the home.
