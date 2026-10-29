## A stack the user lands

A task is never stacked on another's branch, with one exception, in the user's words: "take it as written, and allow a stack for this one playbook". The playbook is `autopilot-stack`, and the exception holds only in a plan whose head names it on its `Playbook:` line. There the entries are the links of one linear stack: each pull request is based on the branch of the link under it, and the bottom one on the default branch. No link merges on a `fixed and green` line. The user lands the stack, by their word, and `shipping` is the playbook for it. Open either with the block of "A playbook of the home's own".

**The order** has one writer, this home, and one place: a `Stack:` line in the head of each link's brief, above its first `## ` heading, in the shape `$T/brief.md` has:

- the stack's name, the link's place, the word `on` and the branch it sits on, as in `Stack: billing 1 on main` and `Stack: billing 2 on billing-schema`;
- the name is one word no other stack has. It is the first word after `Stack:`, which is the name `--land` takes;
- the place counts from 1 at the bottom. Link 1 sits on the default branch, and each next one on the branch of the link under it, which is that link's slug.

Write the line into every link's brief before the first launch. A crewmate opens its pull request on the base its line gives, and never chooses or changes its base. To read the order back, run this with the block at the top and the stack's name in place of `<name>`. It prints a line for each link, bottom first, `<slug> <place> on <branch>`: `for f in "$H"/tasks/*.md; do sed -n "/^## /q; s/^Stack: <name> /$(basename "$f" .md) /p" "$f"; done | sort -k 2n`.

**A link is launched** on a parent that is verified, one link at a time: the parent's `fixed and green` line has arrived, and its brief has a `## Review` and a clean verdict or a `Fixed:` line. Link 1 is launched as any crewmate. Each next one starts from its parent's branch as the repo has it here, not from the remote's default branch, with the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first):

```json
{
  "title": "crew: <slug>",
  "workspaceStrategy": {"type": "worktree", "baseRef": "<the parent's branch>", "branch": "<slug>", "startFromOrigin": false},
  "message": "/crew <slug>"
}
```

Before this launch, run `uv run --project "$T/../source" jroles crew` with the block at the top.
When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the crewmate on the model the role map names.
When it prints nothing, the call is the one above.
Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line.
When it exits 75 and prints no JSON, every instance of the role's pool is capped by a usage limit and the line on stderr says until when: make no launch, and say that line.
A selection it prints names the instance of the pool it chose as its `instanceId`, and the launch is made with it as printed.
Leave the project and modes out, and the model unless `jroles` printed one.

```json
{
  "title": "crew: <slug>",
  "workspaceStrategy": {"type": "worktree", "baseRef": "<the parent's branch>", "branch": "<slug>", "startFromOrigin": false},
  "message": "/crew <slug>",
  "modelSelection": <model selection>
}
```

The rest of a launch is as "Handing a task to a crewmate" has it: the brief on disk first, `room`, the `Thread:` line, the link to the user.

**A link moves** when the link under it has merged, and not before. Its base is then a branch that is merged and kept. Only this home changes it, for one link at a time, the new bottom:

1. Change the base of its pull request: `gh pr edit <number> --base <default branch>`.
2. Write its `Stack:` line again, with the default branch after `on`. Its place stays.
3. Send its crewmate one line with `t3_thread_send`, to the id on its brief's `Thread:` line: `<slug>: <the branch it sat on> is merged, and your pull request is now based on <default branch>. Read "A link that moved" in the crew skill again, from the file, and run its block with <the branch it sat on>`.

The crewmate rebases its own branch, pushes, and sends `fixed and green` at the new head.
The home rebases and pushes nothing.
Run no sweep between the merge and that push: the sweep removes the kept branch once nothing is based on it, and the crewmate's rebase starts from it.

**A link with a conflict** is rebased on the same line, and never by its crewmate alone: its branch holds the commits of the links under it, and only the branch it sits on tells them apart. On its crewmate's line that it has a conflict, send it the line of step 3 with the branch its `Stack:` line names after `on`, the default branch for the bottom link and for one that has moved. If the base of its pull request was changed and that line not yet sent, send that one. When a link was rebased while others sit on it, each of those conflicts in turn: send them their lines from the bottom up, each after the one under it has pushed.

A crewmate that answers `not found` could not tell its own commits from the ones under them: the kept branch is gone, as after the sweep of a home that started meanwhile, or it was rewritten and git kept no record.
Send it the commit its branch started from, to run the same block with in place of the branch.
When the link under it moved or was rebased after this one was launched, that commit is the oldest head that link's crewmate kept since then under `refs/jstack/pre-rebase/<that link's slug>/`, and otherwise the head that link's `Fixed:` line or its review names.
