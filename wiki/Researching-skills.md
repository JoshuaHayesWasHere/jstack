These skills find things out. None of them change code.

"Typed" means the skill runs only when you type its name, such as `/how`. "Phrase" means it also starts when you say its phrase.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `sharpen` | Typed | Rewrites your prompt to ask for more depth: what an expert would also do, the material they would start from, and how to check the result. It does not do the task. | pstack |
| `how` | Typed | Explains how a subsystem works, where code lives, and which layer owns it. | pstack |
| `why` | Typed | Explains why code is the way it is, from the commits and PR discussions. Marks its own guesses. | pstack |
| `swarm` | Typed | Starts N parallel workers on separate slices, then returns one report. | pstack |
| `arena` | Typed | Starts N parallel attempts at one task, picks the best as a base, and copies in the best parts of the others. | pstack |

`swarm` and `arena` choose their models from `docs/models.md`. See [[Models and seats]].
