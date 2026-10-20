---
name: swarm
description: "Fan a task out to up to ten scout and crew threads a step, drain them, and build one table from their Reports and Results. Typed in a home. Use for /swarm, 'swarm this', or parallel coverage, races, gauntlets and exploration."
tip: fans a task out to scout and crew threads and builds one table | swarm this | parallel coverage | race several workers | split it across workers
disable-model-invocation: true
card: "Understand what is there | 4 | Fans a task out to up to ten threads a step, a scout for each slice that reads and a crewmate for each that writes, and builds one table from what they found. | Reach for it in a home when slices need no one worker to hold them together, or several workers race one brief. | op: the operator; model: a home"
---

# Swarm

Source: pstack, `pstack/skills/swarm/SKILL.md`

This is typed in the repo's home, and the home runs `playbooks/swarm.md`, from the root of the repo this skill lives in.
Open it with the block of "A playbook of the home's own" in `skills/home/SKILL.md`, with `swarm` in place of `<name>`, and work its steps.
What follows `/swarm` is the task to fan out, and with nothing after it, ask the user what to fan out.

In any other thread, start nothing: a swarm is many threads, and only a home launches threads.
A crewmate or a scout writes `/swarm <the task>` under "Noticed" for its home, and a thread with no home tells the user to type it in the repo's home.
