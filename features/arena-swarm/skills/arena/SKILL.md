---
name: arena
description: "Make one artifact twice, apart, as two runner crews, have a judge crew score both, and a graft crew pick a base and graft the other's best into it. Typed in a home. Use for /arena, 'arena this', or 'throw it in the arena'."
tip: makes one artifact twice apart, then judges and grafts, as crew threads | arena this | throw it in the arena | two competing attempts | build it twice
disable-model-invocation: true
card: "Settle the shape before code | 5 | Makes one artifact twice, apart, as two runner crews. A judge crew scores both, and a graft crew picks a base, grafts the other's best into it and opens the one pull request. | Reach for it in a home when one attempt would lock in the wrong shape. | op: the operator; model: a home"
---

# Arena

Source: pstack, `pstack/skills/arena/SKILL.md`

This is typed in the repo's home, and the home runs `features/arena-swarm/skills/arena/playbooks/arena.md`, from the root of the repo this skill lives in.
Open it with the block of "A playbook of the home's own" in `skills/home/SKILL.md`, with `arena` in place of `<name>`, and work its steps.
What follows `/arena` is the artifact to make, and with nothing after it, ask the user what to make.

In any other thread, start nothing: an arena is four threads, and only a home launches threads.
A crewmate or a scout writes `/arena <the artifact>` under "Noticed" for its home, and a thread with no home tells the user to type it in the repo's home.
