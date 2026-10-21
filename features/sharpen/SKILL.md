---
name: sharpen
description: "Make a task deeper, not bigger, then rewrite the prompt. Use for /sharpen."
tip: rewrites a task's prompt to ask for the deeper version, and does not do the task | sharpen this | sharpen the task | go deeper | deeper version | more ambitious | what would an expert do | how would an expert approach
disable-model-invocation: true
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
