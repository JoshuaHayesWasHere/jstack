jstack has three layers:

1. **Modes.** `prototype`, `full-stop`, and `full-send` take a request from start to finish. See [[Modes]].
2. **Library.** [[Playbooks]] and [[Principles]] are what the modes read. You can also ask for a playbook by name.
3. **Skills.** The skills on this page. A mode calls them as it works, and you can start any of them on your own.

The groups follow the work, in order. A bug starts at [Understand](#understand) and [Triage](#triage). A feature starts at [Understand](#understand) and goes to [Design](#design). The `prototype` mode works like [Hypothesize](#hypothesize) on a larger scale. `full-stop` and `full-send` run [Prove](#prove), [Review](#review), and [Ship](#ship). [Write](#write) and [Learn](#learn) apply at any point.

In the **Starts** column:

- **Typed** means the skill runs only when you type its name, such as `/how`.
- **Phrase** means it also starts when you say its phrase.
- **Automatic** means the agent runs it on its own when it applies.

## Understand

Find out what is going on. None of these change code.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `how` | Typed | Explains how a subsystem works, where code lives, and which layer owns it. | pstack |
| `why` | Typed | Explains why code is the way it is, from the commits and PR discussions. Marks its own guesses. | pstack |
| `teach` | Typed | Runs `how` and `why`, then explains the work plainly, one diagram at a time. | pstack |
| `recall` | Typed | Rebuilds your recent context on a topic from your chat history and live state. | pstack |
| `ketchup` | Typed | Catches you up on what changed in the chat since your last message. Lists every item that waits on you. | pstack |

## Triage

Pin down what is broken.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `tdd` | Typed | Writes the failing test first, then the fix, when the bug has a cheap local test. | pstack |

## Design

Decide what to build before you build it.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `sharpen` | Typed | Rewrites your prompt to ask for more depth: what an expert would also do, the material they would start from, and how to check the result. It does not do the task. | pstack |
| `in-your-own-words` | Typed | Restates your goal and the problem behind it before any work starts. | pstack |
| `architect` | Typed | Settles types, signatures, and module shape before code crosses a function boundary. Stays involved while the code is written. | pstack |
| `statechart` | Typed | Checks a TLA+ model of a system that moves between states and draws it as a Mermaid statechart. Shows the shortest path to each state that breaks a rule. | pstack |

## Hypothesize

Try several approaches at once and compare them.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `swarm` | Typed | Starts N parallel workers on separate slices, then returns one report. | pstack |
| `arena` | Typed | Starts N parallel attempts at one task, picks the best as a base, and copies in the best parts of the others. | pstack |

`swarm` and `arena` choose their models from `docs/models.md`. See [[Models and seats]].

## Prove

Show that the change works, with evidence you can rerun.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `blast-radius` | Typed | Finds what a small change could break outside the diff. Proves the one fact that makes it safe by running code. | pstack |
| `benchmark-checklist` | Typed | Checks a measured number before anyone reports it or acts on it. | pstack |
| `create-verification-skill` | Typed | Writes a project skill that drives your app the way a user does, so agents can prove changes. | pstack |
| `maintain-verification-skill` | Typed | Brings that project skill back in line with the app. Opens at most one PR of proven corrections. | pstack |
| `create-formal-verification-skill` | Typed | Proves one property of hard code, such as a race or a retry, with a model checker or proof tool. Writes a project skill that checks it again on each change. | pstack |
| `maintain-formal-verification-skill` | Typed | Updates the formal model after the code changes. Says whether each failure is drift or a real bug. | pstack |

## Review

Get a second opinion before the change ships.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `neon-loop` | Phrase: "neon loop" | Gets review from Gemini 4 Neon (or the `neon-loop reviewer` seat) in a loop until both agents agree. | tstack |
| `council` | Phrase: "council" | Gets review from three models on three providers. Loops until all three agree. | tstack |
| `interrogate` | Typed | Has models from different vendors try to break a diff. Keeps only the findings a run proves. | pstack |
| `no-comments` | Typed | Starts the `comment-sicko` agent to strip comments from a diff, then fixes the findings you accept. | pstack |

`neon-loop`, `council`, and `interrogate` take their models from `docs/models.md`. See [[Models and seats]].

## Ship

Take the change to a pull request and through to merge.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `file-pr` | Phrase: "file a PR" | Opens a PR in jstack's standard shape for every repo: a title that says what the user gets, a screenshot first, the problem as a real situation, what changed, evidence from the real app, and what was and was not verified. Written through `unslop` and `bro`. | tstack |
| `babysit-pr` | Phrase: "babysit" | Watches a PR through CI and review bots and fixes real findings. Uses one watcher per PR. | tstack |
| `leaving-pr-comments` | Automatic | Formats any comment an agent posts on GitHub for you. | tstack |
| `show-me-your-work` | Typed | Keeps a TSV log with one row per decision on long or unattended runs, so a reviewer can follow the choices. | pstack |

`file-pr` and `babysit-pr` call `leaving-pr-comments`.

## Write

Make prose clear. Use these at any point.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `technical-writing` | Typed | The writing standard for docs, READMEs, PR descriptions, and commit messages. | pstack |
| `unslop` | Typed | Removes signs of AI writing from text. | pstack |
| `bro` | Typed | Restates the last message in plain words. | pstack |

## Learn

Make agents do better next time.

| Skill | Starts | Does | Source |
| --- | --- | --- | --- |
| `reflect` | Typed | Reads the current chat for lessons and turns each one into an edit to an existing skill. | pstack |
| `correct` | Typed | Finds mistakes that agents keep repeating in a repository and makes each one impossible. Tries architecture, then types, then a lint, then a test, and writes docs last. | pstack |
