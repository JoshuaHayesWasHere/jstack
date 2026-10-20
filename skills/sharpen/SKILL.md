---
name: sharpen
description: "Sharpen a task before starting: the expert approach, what the user is really after, and the right level of specification. Use for /sharpen."
tip: sharpens a task the way an expert would, then does it | sharpen this | sharpen the task | how would an expert approach | is * overspecified | is * underspecified
disable-model-invocation: true
card: "Settle the shape before code | 5 | Sharpens a task before starting: the expert's raw sources, methods and outside check, what the operator is really after, and the right level of specification. Then it does the work, and hands back no rewrite. | Reach for it when a task should be done, done better, and not handed back. | op: the operator"
---

Source: pstack, `pstack/skills/sharpen/SKILL.md`

Before starting, ask how a top expert would approach this task (their raw sources, their real methods, an outside check that the result is right), what the user is really after, and whether the task is over- or underspecified.
Loosen constraints that don't serve the goal as readily as you add ones that do, and leave choices that are the user's to make open instead of deciding them.
Fold in only what makes the work better, not bigger, but always keep one outside check that the result is right, without narrating the framing, then do the work.
Don't hand back a rewritten prompt.

To get the four answers and the prompt rewritten, with no part of the work done, use `/deeper` (`skills/deeper/SKILL.md`) in place of this.
