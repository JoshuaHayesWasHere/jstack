# jmerge says ready, wait or hold

`jmerge` prints one line for each open pull request: `ready` when it is reviewed, fixed and green, `wait` with the reason when it is short of that, and `hold` when it touches a path only the user merges. With `--check` it prints the decision and merges nothing. `jmerge --claims` prints the files each brief still out holds.

Paths:
- `features/jmerge/src/jmerge/`
- `features/jmerge/docs/`
- `features/jsettings/`
Tests: none

## Sub-features

- `decision-no-review` waits on a green pull request whose brief has no review.
- `decision-ready` is ready at the head a clean review names.
- `decision-hold` holds a pull request that changes a protected path, for the user.
- `decision-no-go` waits on a pull request whose queue row has no go, and names `jbus plan go`.
- `decision-review-after` reads a brief that still says `Review: after` as `review`: its findings hold the merge.
- `decision-review-proof` reads a brief that still says `Review: twice` as `review`, holds a blocking finding with no `(proof: ...)` tag under a reason that names it until it has any answer, and holds one whose proof is a run that exited non-zero until its decline cites a path:line, a command or a gate.
- `decision-red` waits while the check named `check` has not passed.
- `decision-over-main` is ready on a green pull request whose check main moved past on none of its files, and waits for GitHub's update of its branch once main moved on one of them.
- `decision-base` holds a pull request into another branch than the default.
- `decision-tool-follows` reinstalls the tool after a merge that changes pyproject.toml's package list, and says so on the `merged` line (not reachable from a sandbox: the stand-in `gh` refuses a merge, and `features/home/tests/test_home_merge.py` drives it).
- `decision-install-follows` runs `sh install.sh` in the main checkout after a merge that changes what the install assembles (`skills.json`, a skill's files), where the machine's layouts were assembled from that checkout, and says so on the `merged` line, or says loudly that it failed (not reachable from a sandbox: the stand-in `gh` refuses a merge, and `features/jmerge/tests/test_jmerge_follow.py` drives it; [jinstall's page](../jinstall/verify.md) drives the install it runs).
- `decision-claims` lists the briefs that still hold files.
- `decision-check-merges-nothing` asks GitHub and merges nothing.

## How to get to it (user POV)

- Run `jmerge --check` in the repo's main checkout.
- Run `jmerge --claims` there.
- Run `jmerge` there to merge what is ready (not reachable from a sandbox: the stand-in `gh` refuses a merge).
- Read the `jmerge` and `gate` lines a `jbus poll` sends, which runs `jmerge` where the repo's home is off.

## Driving it with verify-jstack

Needs: `demo`, `tasks`, `gh/open.json`

Preconditions:

- A new sandbox, `env.sh` sourced, `doctor: ok`.
- The shell is in `$VERIFY_JSTACK_SANDBOX/demo`, and `gh/open.json` is `[]`.

- **Open a pull request.** Run `head=$("$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py)`. `gh/open.json` has pull request 7 on the branch `beta`, green, changing `src/beta/a.py`.
- **Write its brief.** Run `printf '# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\n' > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`. The brief has a Result and no review.
- **Ask, unreviewed.** Run `record jmerge-decision jmerge --check`. It prints `wait 7 https://example.test/pull/7: it has no review yet`.
- **Add a clean review.** Run `printf '## Review\nVerdict: clean\nHead: %s   Unchanged by the run: yes\nFindings:\nnone\n' "$head" >> "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`. It prints `ready 7 <the head> beta beta`.
- **Review after.**
  Run `printf '## Review\nVerdict: findings\nHead: %s\nFindings:\n- warning src/beta/a.py:1 a made up one (bucket: Act on)\n' "$head" >> "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`.
  It prints `wait 7 https://example.test/pull/7: its findings are not handled: the Result has no Fixed line`.
  Then run `f="${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md" && awk '{print} /^Pull request: open one when done$/ {print "Review: after"}' "$f" > "$f.new" && mv "$f.new" "$f"` and `record jmerge-decision jmerge --check` again.
  It prints the same `wait` line: an `after` brief is read as `review`, and its findings hold the merge.
- **One round, a proof.**
  Run `printf '# beta: a demo task\nWhere: src/beta/\nPull request: open one when done\nReview: twice\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\nReviewer: mcp:9 #1\nFixed: none needed, declined\n\n## Review\nBy: demo #1\nVerdict: findings\nHead: %s\nFindings:\n- error src/beta/a.py:1 a made up one (bucket: Act on)\n' "$head" > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`.
  It prints `wait 7 https://example.test/pull/7: its findings are not handled: F1 block with no proof tag, so answer each by id, and a decline of one needs no cited reason`: the old `twice` brief is read as `review`, and the finding with no proof is named.
  Then run `printf 'Finding F1: not fixed, a made up one, because I disagree\n' >> "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"` and `record jmerge-decision jmerge --check` again.
  It prints `ready 7 <the head> beta beta`: no second review is owed, and a decline of a finding with no proof counts with any reason.
  Then run `printf '# beta: a demo task\nWhere: src/beta/\nPull request: open one when done\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\nReviewer: mcp:9 #1\nFixed: none needed, declined\n\n## Review\nBy: demo #1\nVerdict: findings\nHead: %s\nFindings:\n- error src/beta/a.py:1 a made up one (bucket: Act on) (proof: `sh src/beta/proof.sh`, exit 1, it loops)\n' "$head" > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"` and `record jmerge-decision jmerge --check` again.
  It prints `wait 7 https://example.test/pull/7: its findings are not handled: F1 have no answer by id`.
  Then run `printf 'Finding F1: not fixed, a made up one, because I disagree\n' >> "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"` and `record jmerge-decision jmerge --check` again.
  It prints `wait 7 https://example.test/pull/7: its findings are not handled: the decline of F1 cites no path:line, command or gate`: a proven finding holds until its decline cites one.
- **Clean it again.**
  The next two steps each need a brief with nothing else to wait on, so the line printed is the one they test.
  Run `printf '# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\nChecked: jgauge check exit 0 at %s\n\n## Review\nVerdict: clean\nHead: %s   Unchanged by the run: yes\nFindings:\nnone\n' "$head" "$head" > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`.
  It prints `ready 7 <the head> beta beta`.
- **Touch a protected path.** Run `"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta secrets/a.key`, then `record jmerge-decision jmerge --check`. It prints `hold 7 https://example.test/pull/7: needs user, touches secrets/a.key`.
- **Fail the check.**
  Run `"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py FAILURE`, then `record jmerge-decision jmerge --check`.
  It prints `wait 7 https://example.test/pull/7: check has failed`.
- **Review it clean at a real head.**
  The next step reads the pull request's head from git, so this step gives the pull request a real one.
  Run `head=$(git commit-tree -p HEAD -m beta "$(git rev-parse 'HEAD^{tree}')") && git push -q origin "${head}:refs/heads/beta" && "$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py > /dev/null && jq --arg head "$head" '.[0].headRefOid = $head' "$VERIFY_JSTACK_SANDBOX/gh/open.json" > "$VERIFY_JSTACK_SANDBOX/gh/open.json.new" && mv "$VERIFY_JSTACK_SANDBOX/gh/open.json.new" "$VERIFY_JSTACK_SANDBOX/gh/open.json" && printf '# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\n\n## Result\nStatus: done\nBranch: beta   Pull request: https://example.test/pull/7\n\n## Review\nVerdict: clean\nHead: %s   Unchanged by the run: yes\nFindings:\nnone\n' "$head" > "${VERIFY_JSTACK_SANDBOX:?}/home/.local/state/home/demo/tasks/beta.md"`, then `record jmerge-decision jmerge --check`.
  It prints `ready 7 <the head> beta beta`.
- **Over a main that moved.**
  The pull request's check started in 2000, and main gets a commit after it.
  Run `jq '(.[0].statusCheckRollup[] | select(.name == "check")).startedAt = "2000-01-01T00:00:00Z"' "$VERIFY_JSTACK_SANDBOX/gh/open.json" > "$VERIFY_JSTACK_SANDBOX/gh/open.json.new" && mv "$VERIFY_JSTACK_SANDBOX/gh/open.json.new" "$VERIFY_JSTACK_SANDBOX/gh/open.json"`, then `git switch -q -c moved && echo moved > moved.txt && git add moved.txt && git commit -qm moved && git push -q origin moved:main && git switch -q main && git branch -q -D moved`, then `record jmerge-decision jmerge --check`.
  It prints `ready 7 <the head> beta beta`: main changed none of its files, so it merges on its existing check, with no guards file in the sandbox to run on its merged tree.
  Then run `git switch -q -c moved2 origin/main && mkdir -p src/beta && echo theirs >> src/beta/a.py && git add src/beta/a.py && git commit -qm moved2 && git push -q origin moved2:main && git switch -q main && git branch -q -D moved2`, then `record jmerge-decision jmerge --check`.
  It prints `wait 7 https://example.test/pull/7: main moved after its check started: GitHub is to merge main at <the new tip's first 12> into it`: main changed `src/beta/a.py`, a file it changes.
  `--check` asks for no update: `grep -cE 'pr merge|update-branch' "$VERIFY_JSTACK_SANDBOX/gh/calls.log"` prints `0`.
  The demo checkout's `main` stays at `start`, and only origin's moved.
- **Queue it with no go.**
  Run `printf '# beta: a demo task\nTask: beta, a demo task\nDone when:\n- the demo works\nProves it: the demo test\nSize: S\nWhere: `src/beta/`\nDesign: none, a demo\nReview: none\nPlaybook: none\nPull request: open one when done\nHome: root\n' | jbus --project demo queue add beta --priority 1 > /dev/null`, then `record jmerge-decision jmerge --check`.
  It prints `wait 7 https://example.test/pull/7: its queue row has no go: the user's go (jbus plan go <entry> --message <thread>/<message>), or the bot's, lets it merge`.
  The line names the command a user gives the go with, so a stranger is not sent to a bare `jbus queue approve` that refuses.
- **Into another branch.**
  Run `"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py > /dev/null && jq --arg head "$head" '.[0].headRefOid = $head | .[0].baseRefName = "migration"' "$VERIFY_JSTACK_SANDBOX/gh/open.json" > "$VERIFY_JSTACK_SANDBOX/gh/open.json.new" && mv "$VERIFY_JSTACK_SANDBOX/gh/open.json.new" "$VERIFY_JSTACK_SANDBOX/gh/open.json"`, then `record jmerge-decision jmerge --check`.
  It prints `wait 7 https://example.test/pull/7: its base is migration, not main`.
- **List the claims.** Run `record jmerge-decision jmerge --claims`. It prints `beta pull request 7 root Where: `src/beta/``.
- **Check nothing merged.** Run `record jmerge-decision grep -c "pr merge" "$VERIFY_JSTACK_SANDBOX/gh/calls.log"`. It prints `0` (and exits 1, as `grep -c` does with no match). The demo checkout's `git log --oneline` still has the one commit `start`.
- **Proof.** Copy `gh/calls.log` and the brief into `$VERIFY_JSTACK_EVIDENCE`.

## Gotchas

- `jmerge` reads the briefs from `$JBUS_HOME_DIR/<the main checkout's directory name>`, as jbus does, or from `$HOME/.local/state/home` where it is not set.
- The recipe writes the brief through `${VERIFY_JSTACK_SANDBOX:?}`, so a shell that sourced no `env.sh` stops and writes nothing into the live briefs.
- The review's `Head:` must be the pull request's head commit, whole. `open-pull.sh` prints it.
- Only the check named `check` decides green. Another check's name in `statusCheckRollup` changes nothing.
- A plain `jmerge` on a ready pull request reaches `gh pr merge`, which the stand-in refuses with exit 64. That is the harness ending, not a jmerge failure, and it is not proof of a merge.
- The stand-in answers a branch's check runs from the key of `gh/checks.json` that is the branch's name, as it answers a commit's from its sha.
- Every line of `jmerge --check` exits 0, `wait` and `hold` included. Assert on the line, not the exit code.
- `jmerge` without `--check` appends each line to `merge.log` in the repo's state. `--check` writes nothing.
- `jmerge` reads no `fresh-check` file.
  A green pull request whose check main moved past on none of its files is ready on that check.
  One whose file main changed waits for GitHub's update of its branch: where its head merges cleanly over today's main, `jmerge --check` says `main moved after its check started: GitHub is to merge main at <tip12> into it`, and the check at the new head decides ("Merges cleanly over today's main" in [jmerge.md](docs/jmerge.md)).
