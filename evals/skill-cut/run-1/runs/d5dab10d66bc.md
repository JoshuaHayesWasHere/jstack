1. **I don't edit it myself.** Per "The home does not do the work", a home never edits the repo or reads its code. I tell you this in one line, and that a crewmate will fix it in about a minute.
2. **Plan entry ("Planning").** You described the task in full, so no grilling round is needed. I add `readme-typo` to `$M/plan.md` with `Stage: planned`, `Size: S` and `Done when: line 3 of README.md has the misspelled word corrected, and nothing else in the file changes`.
3. **Brief (step 1 of "Handing a task to a crewmate").** I write `$H/tasks/readme-typo.md` from `$T/brief.md` with these lines:
   - `Where: README.md`
   - `Review: none`, because it is text only
   - `Playbook: none`
   - `Proves it: git diff shows a one-word change on README.md line 3`
   
   Then I queue it with `jbus queue add readme-typo --priority 1 --entry readme-typo < "$H/tasks/readme-typo.md"`.
4. **Machine check, then launch (step 2).** I run `uv run --project "$T/.." jgauge room` and `uv run --project "$T/.." jroles crew`. On `go`, I call `t3_thread_launch` with `{"title":"crew: readme-typo","workspaceStrategy":{"type":"worktree","baseRef":"<default>","branch":"readme-typo","startFromOrigin":true},"message":"/crew readme-typo"}`.
5. **Record the thread (step 3).** I add `Thread: <id>` to the brief with the step-3 block and give you the link `[readme-typo](t3-thread://v1/<id>)`.
6. **Merge needs you.** Because the brief says `Review: none`, its pull request is never merged automatically. When it comes back green, I tell you it is waiting for your word to merge.
